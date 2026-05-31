"""Sistema de subagentes con visibilidad en tiempo real, steer y kill.

Cada subagente se ejecuta en su propio thread daemon y escribe su output
directamente al console del padre (prefijado con │ para distinguirlo).
El padre puede steer (inyectar nuevas instrucciones) o kill desde /subagents.
"""
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from agent.loop_helpers import _fmt_elapsed
from ui.console import console


@dataclass
class ActiveSubAgent:
    run_id:      str
    agent_id:    str
    agent_name:  str
    agent_emoji: str
    task:        str
    thread:      threading.Thread
    kill_event:  threading.Event
    steer_queue: queue.SimpleQueue
    started_at:  float = field(default_factory=time.time)
    status:      str   = "running"   # running | done | killed | error
    result:      Optional[str] = None
    error:       Optional[str] = None
    finished_at: Optional[float] = None   # timestamp de finalización
    steer_count:  int   = 0               # instrucciones steer enviadas
    priority:     int   = 0               # prioridad de la tarea (mayor = más urgente)
    queue_time:   float = 0.0            # tiempo en cola (para background agents)
    n_tool_uses:  int   = 0               # tool calls ejecutados por el subagente
    n_tokens_out: int   = 0               # tokens de output generados (acumulado)
    ctx_pct:      int   = 0               # % de contexto usado (actualizado por el subagente)

    def elapsed(self) -> float:
        if self.finished_at is not None:
            return self.finished_at - self.started_at
        return time.time() - self.started_at

    def finished_ago(self) -> Optional[float]:
        """Segundos desde que terminó, o None si sigue corriendo."""
        if self.finished_at is None:
            return None
        return time.time() - self.finished_at

    def short_id(self) -> str:
        return self.run_id[:6]


# Registro global de subagentes activos (accedido desde commands.py)
_registry: dict[str, "ActiveSubAgent"] = {}
_registry_lock = threading.Lock()

# Contador round-robin para distribución de hosts Ollama entre subagentes
_host_rr_lock:    threading.Lock = threading.Lock()
_host_rr_counter: int            = 0


def _pick_subagent_host(config) -> str:
    """Selecciona el host Ollama para un subagente según la política de routing.

    round-robin: distribuye entre todos los hosts disponibles (principal + extras).
    primary-only: siempre usa el host principal (comportamiento clásico).
    """
    global _host_rr_counter
    all_hosts = config.all_ollama_hosts
    if len(all_hosts) <= 1 or config.ollama_subagent_routing == "primary-only":
        return config.ollama_host
    with _host_rr_lock:
        idx = _host_rr_counter % len(all_hosts)
        _host_rr_counter += 1
    return all_hosts[idx]

# Semáforo global de concurrencia — inicializado por SubAgentRunner al primer spawn.
# Limita cuántos subagentes pueden ejecutar self.run() simultáneamente.
_concurrency_sem: Optional[threading.Semaphore] = None
_concurrency_sem_lock = threading.Lock()
_concurrency_sem_value: int = 0  # valor con el que se inicializó


def _get_concurrency_sem(max_concurrent: int) -> threading.Semaphore:
    """Devuelve el semáforo global, inicializándolo si es necesario."""
    global _concurrency_sem, _concurrency_sem_value
    max_concurrent = max(1, int(max_concurrent))
    with _concurrency_sem_lock:
        if _concurrency_sem is None or _concurrency_sem_value != max_concurrent:
            _concurrency_sem = threading.Semaphore(max_concurrent)
            _concurrency_sem_value = max_concurrent
        return _concurrency_sem


def _register(sub: "ActiveSubAgent") -> None:
    """Registra un subagente en el registro global."""
    with _registry_lock:
        _registry[sub.run_id] = sub


def list_queued() -> list[ActiveSubAgent]:
    """Subagentes en estado 'queued' (esperando slot de concurrencia), por prioridad desc."""
    with _registry_lock:
        queued = [s for s in _registry.values() if s.status == "queued"]
    return sorted(queued, key=lambda s: s.priority, reverse=True)


def _get_recent_ttl() -> int:
    """Lee recentTtl desde oocode.json o devuelve el default (1800 s)."""
    try:
        from pathlib import Path as _P
        import json as _j
        _f = _P.home() / ".oocode" / "oocode.json"
        if _f.exists():
            return int(_j.loads(_f.read_text()).get("subagents", {}).get("recentTtl", 1800))
    except Exception:
        pass
    return 1800


_RECENT_TTL = _get_recent_ttl()


def _deregister(run_id: str) -> None:
    with _registry_lock:
        if run_id in _registry:
            sub = _registry[run_id]
            sub.finished_at = time.time()
            # Solo sobreescribir si aún figura como running/queued
            if sub.status in ("running", "queued"):
                sub.status = "done"


def list_running() -> list[ActiveSubAgent]:
    """Subagentes en ejecución ahora mismo."""
    with _registry_lock:
        return [s for s in _registry.values() if s.status == "running"]


def list_recent(ttl: float = _RECENT_TTL) -> list[ActiveSubAgent]:
    """Subagentes finalizados en los últimos `ttl` segundos, más recientes primero."""
    now = time.time()
    with _registry_lock:
        recent = [
            s for s in _registry.values()
            if s.status != "running"
            and s.finished_at is not None
            and (now - s.finished_at) <= ttl
        ]
    return sorted(recent, key=lambda s: s.finished_at or 0, reverse=True)


def list_active() -> list[ActiveSubAgent]:
    """Todos los subagentes del registro. Orden: queued→running→finalizados (recientes primero)."""
    with _registry_lock:
        all_subs = list(_registry.values())
    queued  = sorted([s for s in all_subs if s.status == "queued"],
                     key=lambda s: s.priority, reverse=True)
    running = [s for s in all_subs if s.status == "running"]
    finished = sorted(
        [s for s in all_subs if s.status not in ("queued", "running")],
        key=lambda s: s.finished_at or 0, reverse=True,
    )
    return queued + running + finished


def get_by_prefix(prefix: str) -> Optional[ActiveSubAgent]:
    """Devuelve el subagente cuyo run_id empieza por `prefix` (case-insensitive)."""
    prefix = prefix.lower()
    with _registry_lock:
        for sub in _registry.values():
            if sub.run_id.lower().startswith(prefix):
                return sub
    return None


def purge_finished() -> None:
    """Elimina del registro los subagentes terminados (done/killed/error)."""
    with _registry_lock:
        dead = [rid for rid, s in _registry.items() if s.status != "running"]
        for rid in dead:
            del _registry[rid]


class SubAgentRunner:
    """Lanza subagentes con output visible al usuario, steer y kill."""

    def __init__(self, config, permissions, build_registry_fn,
                 embed_client=None, parent_plugins=None, parent_skills=None,
                 parent_client=None):
        self.config = config
        self.permissions = permissions
        self.build_registry_fn = build_registry_fn
        self._shared_embed   = embed_client
        self._parent_plugins = parent_plugins   # PluginManager del padre
        self._parent_skills  = parent_skills    # SkillManager del padre
        self._parent_client  = parent_client    # ollama.Client del padre (evita reload)
        self._parent_rt         = None   # RuntimeSettings del padre (se inyecta en oocode.py)
        self._parent_webui_queue = None  # queue del padre en modo WebUI (se inyecta en sessions.py)
        # Semáforo de concurrencia: inicializado desde config.subagents_max_concurrent
        max_c = getattr(config, "subagents_max_concurrent", 4)
        self._concurrency_sem = _get_concurrency_sem(max_c)

    # ── Herramientas bloqueadas en modo explore ───────────────────────────────

    _EXPLORE_DENY: frozenset[str] = frozenset({
        # ── Escritura de ficheros ─────────────────────────────────────────────
        "write_file", "edit_file", "edit_files",
        "regex_replace", "bulk_replace", "smart_replace", "patch_apply",
        "symlink_create", "mv_file", "cp_file", "rm_file", "rm_dir",
        "mkdir_dir", "touch_file", "chmod_file", "chmod_dir",
        "chown_file", "chown_dir", "archive_extract", "archive_create",
        # ── Git ───────────────────────────────────────────────────────────────
        "git_commit", "git_push", "git_pull", "git_add", "git_stash",
        "git_patch", "git_clone", "git_worktree",
        # ── Docker / Compose ─────────────────────────────────────────────────
        "docker_exec", "docker_stop", "docker_rm",
        "compose_up", "compose_down", "compose_stop", "compose_restart",
        "compose_build", "compose_pull", "compose_exec", "compose_run",
        # ── Sistema / Paquetes ───────────────────────────────────────────────
        "systemctl_action", "kill_process", "fw_allow", "fw_deny",
        "apt_install", "apt_remove", "apt_upgrade", "apt_update",
        "dnf_install", "dnf_remove", "dnf_update",
        # ── Ejecución y herramientas ─────────────────────────────────────────
        "strace_run", "gdb_run", "pdb_run", "valgrind_run",
        "make_run", "run_script", "format_code", "pip_tool", "npm_tool",
        "python_exec",
        # ── LSP write ────────────────────────────────────────────────────────
        "lsp_rename", "lsp_code_actions",
        # ── Misc ─────────────────────────────────────────────────────────────
        "todo_add", "todo_done", "clipboard_copy", "vault_get",
        "snippet_save", "snippet_delete",
        # ── Security MCP — ofensivas ─────────────────────────────────────────
        "nikto_scan", "gobuster_run", "hash_crack",
        # ── IoT MCP — control ────────────────────────────────────────────────
        "tapo_on_off", "tapo_set", "blink_arm", "blink_snapshot", "blink_verify",
        "alexa_speak", "alexa_command", "alexa_volume",
        "tuya_control", "ha_control", "ha_automation",
        "mqtt_publish", "esphome_control",
        # ── Home Office MCP — escritura ──────────────────────────────────────
        "doc_write", "email_send", "cal_create", "cal_update", "cal_delete",
        "note_write", "note_delete", "sheet_write", "contact_write",
    })

    _EXPLORE_RULES = """\
## Modo Explore — exploración read-only

Eres un agente explorador especializado en mapear código. Tu único objetivo es:
1. Localizar ficheros y funciones relevantes para la tarea del agente padre
2. Leer las secciones clave del código
3. Devolver un informe estructurado con: ficheros relevantes, funciones clave, dependencias y puntos de entrada

RESTRICCIONES ABSOLUTAS:
- SOLO lectura: NO modifiques ficheros, NO hagas commits, NO ejecutes código
- Herramientas preferidas: `tree`, `grep_code`, `find_files`, `read_file`, `find_symbol`, `list_symbols`
- En `bash`: SOLO comandos de lectura (cat, head, tail, wc, file, nm, strings, objdump -d)
- Sé conciso: devuelve lo que necesita el agente padre, no un análisis exhaustivo
"""

    # ── Ejecución ────────────────────────────────────────────────────────────

    def run(self, agent_id: str, task: str, silent: bool = False,
            kill_event: Optional[threading.Event] = None,
            steer_queue: Optional[queue.SimpleQueue] = None,
            explore_mode: bool = False, priority: int = 0,
            sub_ref: Optional["ActiveSubAgent"] = None) -> str:
        """Ejecuta un subagente y devuelve su resultado.

        El subagente escribe su output directamente al console del padre
        (prefijado con │). Esto funciona porque sys.stdout ya está
        redirigido al buffer de la TUI por _AppWriter.
        """
        from config import OOConfig
        from agent.embeddings import EmbeddingClient
        from agent.loop import AgentLoop
        from agent.memory import MemorySystem
        from agent.session import SessionManager
        from workspace.manager import WorkspaceManager

        sub_config = OOConfig.load(agent_id=agent_id)

        # Modelo: mismo que el padre (restricción VRAM compartida)
        # Host: round-robin entre hosts disponibles para paralelismo real
        sub_config.model                    = self.config.model
        sub_config.ollama_host              = _pick_subagent_host(self.config)
        sub_config.ollama_extra_hosts       = self.config.ollama_extra_hosts
        sub_config.ollama_embed_host        = self.config.ollama_embed_host
        sub_config.ollama_subagent_routing  = self.config.ollama_subagent_routing
        sub_config.embed_model              = self.config.embed_model
        # Heredar configs per-modelo para que el subagente use el mismo contextWindow
        sub_config.model_configs        = self.config.model_configs
        sub_config.model_system_overhead = self.config.model_system_overhead
        # Heredar project_dir para que load_oocode_md() encuentre OOCODE.md del proyecto padre
        if self.config.project_dir:
            sub_config.project_dir = self.config.project_dir

        if not silent:
            console.print()
            if explore_mode:
                console.rule(
                    "[bold green]🔍 Explore — exploración read-only[/bold green]"
                    f"  [dim]modelo: {sub_config.model}[/dim]",
                    style="green dim",
                )
            else:
                console.rule(
                    f"[bold cyan]↳ Subagente {sub_config.agent_emoji} {sub_config.agent_name}[/bold cyan]"
                    f"  [dim]modelo: {sub_config.model}[/dim]",
                    style="cyan dim",
                )

        ws_manager = WorkspaceManager(
            sub_config.workspace, sub_config.agent_name, sub_config.agent_emoji,
            ollama_host=sub_config.ollama_host,
            permissions=sub_config.permissions,
            max_memory_lines=sub_config.ws_max_memory_lines,
            max_daily_chars=sub_config.ws_max_daily_chars,
        )
        if not ws_manager.exists():
            ws_manager.init()

        session_manager = SessionManager(sub_config.agent_id)
        session_manager.start(sub_config.model or "", sub_config.workspace)

        registry = self.build_registry_fn(sub_config.workspace, sub_config)

        # ── Heredar hooks del padre ───────────────────────────────────────────
        # build_registry_fn solo registra tools; los hooks se configuran aquí
        # copiando el estado activo del padre en lugar del config guardado en disco.
        sub_config.hooks_enabled  = self.config.hooks_enabled
        sub_config.hooks_builtins = list(self.config.hooks_builtins)
        if sub_config.hooks_enabled and sub_config.hooks_builtins:
            registry.hooks.register_builtins(sub_config.hooks_builtins)
        if sub_config.hooks_enabled:
            try:
                from tools.hooks import load_oocode_md_hooks as _lmh
                _lmh(registry.hooks, sub_config)
            except Exception:
                pass

        # ── Tools MCP del padre ───────────────────────────────────────────────
        # El padre arranca los subprocesos MCP y registra sus tools.  McpClient
        # es thread-safe (_send_lock + _id_lock), por lo que podemos reutilizar
        # el mismo pool desde el thread del subagente sin conflictos.
        parent_mcp = getattr(self, "_parent_mcp_pool", None)
        if parent_mcp is not None:
            for mcp_name, mcp_fn, mcp_schema in parent_mcp.all_oocode_tools():
                if not registry.has(mcp_name):
                    registry.register(mcp_name, mcp_fn, mcp_schema)
            for res_name, res_fn, res_schema in parent_mcp.resource_oocode_tools():
                if not registry.has(res_name):
                    registry.register(res_name, res_fn, res_schema)
            for prm_name, prm_fn, prm_schema in parent_mcp.prompt_oocode_tools():
                if not registry.has(prm_name):
                    registry.register(prm_name, prm_fn, prm_schema)

        # Reutilizar embed_client del padre para no cargar segundo modelo
        embed = self._shared_embed
        if embed is None:
            embed = EmbeddingClient(
                host=sub_config.effective_embed_host,
                model=sub_config.embed_model,
                max_input_chars=sub_config.embed_max_input_chars,
                disk_cache_enabled=sub_config.embed_disk_cache_enabled,
                disk_cache_dir=sub_config.embed_disk_cache_dir,
                disk_cache_max=sub_config.embed_disk_cache_max,
                ram_cache_max=sub_config.embed_ram_cache_max,
            )

        from config import MEMORY_DIR
        sub_memory_dir = MEMORY_DIR / sub_config.agent_id
        sub_memory_dir.mkdir(parents=True, exist_ok=True)
        memory = MemorySystem(
            embed_client=embed,
            similarity_threshold=sub_config.embed_similarity_threshold,
            snippet_chars=sub_config.embed_snippet_chars,
            top_k=sub_config.embed_top_k,
            memory_dir=sub_memory_dir,
        )

        # Modo explore: PermissionManager restringido (write tools → deny)
        if explore_mode:
            from tools.permissions import PermissionManager as _PM
            explore_perms = self.permissions.get_all()
            for _tool in self._EXPLORE_DENY:
                explore_perms[_tool] = "deny"
            active_permissions = _PM(explore_perms)
            active_permissions._ask_fn = self.permissions._ask_fn
        else:
            active_permissions = self.permissions

        # Si el padre no tiene _ask_fn (no hay terminal interactiva), marcar
        # el PermissionManager del subagente como no-interactivo para que los
        # tools "ask" se auto-aprueben en lugar de bloquear con input().
        if active_permissions._ask_fn is None:
            active_permissions._non_interactive = True

        loop = AgentLoop(
            config=sub_config,
            registry=registry,
            permissions=active_permissions,
            memory=memory,
            workspace_manager=ws_manager,
            session_manager=session_manager,
            subagent_runner=None,
            capture_output=False,
            is_subagent=True,               # activa prefijo visual │
            ollama_client=self._parent_client,  # reutiliza cliente del padre
        )

        # Inyectar steer_queue, kill_event y referencia al registro de stats
        loop._steer_queue   = steer_queue
        loop._ext_kill      = kill_event
        loop._sub_stats_ref = sub_ref   # ActiveSubAgent | None — para actualizar stats

        # Propagar cola WebUI del padre: los eventos del subagente fluyen al SSE del browser
        if self._parent_webui_queue is not None:
            loop._webui_queue = self._parent_webui_queue
            loop._status_cb   = lambda _: None   # sin TUI status bar

        # Propagar modo elevated del padre al subagente
        if self._parent_rt is not None:
            loop.rt.elevated = self._parent_rt.elevated

        # Propagar project_dir del padre: el subagente trabaja en el mismo proyecto
        if hasattr(self.config, "project_dir") and self.config.project_dir:
            sub_config.project_dir = self.config.project_dir

        # Modo explore: system prompt restringido
        if explore_mode:
            loop._extra_rules = self._EXPLORE_RULES

        # Skills del padre (mismas herramientas disponibles)
        if self._parent_skills:
            from skills.manager import SkillManager
            loop.skills = SkillManager(
                enabled_override=list(self._parent_skills._enabled)
            )
            for sn, sf, ss in loop.skills.load_tools():
                if not registry.has(sn):
                    registry.register(sn, sf, ss)

        # Plugins del padre
        if self._parent_plugins:
            from plugins.manager import PluginManager
            loop.plugins = PluginManager(
                enabled_override=list(self._parent_plugins._enabled)
            )
            loop.plugins.load_all(sub_config)
            for pn, pf, ps in loop.plugins.get_tools():
                registry.register(pn, pf, ps)

        # ── Tools que requieren la instancia del loop ya creada ───────────────
        # mem_save: usa la memoria propia del subagente (namespace separado del padre)
        _sub_mem = loop.memory
        def _sub_mem_save(name: str, content: str, description: str = "") -> str:
            return _sub_mem.save(name, content, description)
        if not registry.has("mem_save"):
            registry.register("mem_save", _sub_mem_save, {
                "name": "mem_save",
                "description": (
                    "Guarda un recuerdo persistente en la memoria del agente (fichero .md con embedding). "
                    "Úsalo para guardar hechos importantes del proyecto, decisiones de arquitectura, "
                    "bugs conocidos, o preferencias del usuario que deben recordarse entre sesiones."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name":        {"type": "string", "description": "Nombre en snake_case"},
                        "content":     {"type": "string", "description": "Contenido en markdown"},
                        "description": {"type": "string", "description": "Descripción de una línea (opcional)"},
                    },
                    "required": ["name", "content"],
                },
            })

        # plan_create / task_done: el subagente también puede gestionar su propio plan de tareas
        if not registry.has("plan_create"):
            registry.register("plan_create", loop._execute_plan_create, {
                "name": "plan_create",
                "description": (
                    "Crea un plan de tareas numerado para ejecutar de forma organizada. "
                    "Úsalo cuando tengas ≥3 pasos distintos que realizar."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tasks": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Lista ordenada de tareas a ejecutar",
                        },
                        "summary": {"type": "string", "description": "Descripción breve del plan (opcional)"},
                    },
                    "required": ["tasks"],
                },
            })
        if not registry.has("task_done"):
            registry.register("task_done", loop._execute_task_done, {
                "name": "task_done",
                "description": (
                    "Marca la tarea activa del plan como completada y activa la siguiente. "
                    "Llama a esta herramienta cada vez que termines una tarea del plan (✔/◼/◻)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "Resumen de lo completado (opcional)"},
                    },
                },
            })

        loop.run(task)
        session_manager.end()

        if not silent:
            console.rule(
                f"[dim]↲ fin subagente {sub_config.agent_name}[/dim]",
                style="cyan dim",
            )
            console.print()

        # capture_output=False hace que loop.run() devuelva None, pero _last_response
        # siempre se actualiza. Lo usamos para devolver el output real del subagente.
        return loop._last_response or ""

    def spawn_background(self, agent_id: str, task: str, priority: int = 0,
                         timeout_seconds: int = 0) -> "ActiveSubAgent":
        """Lanza un subagente en background respetando el límite de concurrencia.

        El subagente empieza en estado 'queued' hasta que hay un slot disponible
        (controlado por _concurrency_sem). Al adquirir el semáforo pasa a 'running'.

        Si timeout_seconds > 0, un watchdog dispara kill_event tras ese tiempo y
        marca el subagente como 'killed' con sub.error = "Timeout: …".
        """
        sub_cfg_agents = self.config.agents
        target = next((a for a in sub_cfg_agents if a.id == agent_id), None)
        name   = target.name  if target else agent_id
        emoji  = target.emoji if target else "🤖"

        run_id      = uuid.uuid4().hex
        kill_ev     = threading.Event()
        steer_q: queue.SimpleQueue = queue.SimpleQueue()

        sub = ActiveSubAgent(
            run_id      = run_id,
            agent_id    = agent_id,
            agent_name  = name,
            agent_emoji = emoji,
            task        = task,
            thread      = None,  # type: ignore[arg-type]
            kill_event  = kill_ev,
            steer_queue = steer_q,
            status      = "queued",
            priority    = priority,
            queue_time  = 0.0,
        )
        _register(sub)

        sem = self._concurrency_sem

        def _worker():
            enqueued_at = time.time()
            # Espera slot — puede bloquearse si hay max_concurrent corriendo
            sem.acquire()
            try:
                if sub.status == "killed":
                    # Matado mientras esperaba en cola — liberar slot y salir
                    return
                sub.queue_time  = time.time() - enqueued_at
                sub.started_at  = time.time()
                sub.status      = "running"
                # Watchdog: dispara kill_ev si el subagente supera timeout_seconds
                if timeout_seconds > 0:
                    def _watchdog(ev=kill_ev, s=sub, secs=timeout_seconds):
                        signaled = ev.wait(timeout=secs)
                        if not signaled and s.status == "running":
                            s.error  = f"Timeout: subagente detenido tras {secs}s"
                            s.status = "killed"
                            ev.set()
                    threading.Thread(
                        target=_watchdog, daemon=True,
                        name=f"oocode-wdog-{run_id[:6]}",
                    ).start()
                sub.result = self.run(
                    agent_id, task, silent=True,
                    kill_event=kill_ev, steer_queue=steer_q,
                    priority=priority, sub_ref=sub,
                )
                if sub.status == "running":   # no machacar "killed"
                    sub.status = "done"
            except Exception as exc:
                sub.error  = str(exc)
                sub.status = "error"
            finally:
                sub.finished_at = time.time()
                _deregister(run_id)
                sem.release()

        t = threading.Thread(
            target=_worker, daemon=True,
            name=f"oocode-sub-{run_id[:6]}",
        )
        sub.thread = t
        t.start()
        return sub

    def spawn_with_priority(self, agent_id: str, task: str, priority: int = 0) -> "ActiveSubAgent":
        """Lanza un subagente con prioridad específica.
        
        Args:
            agent_id: ID del agente
            task: Tarea a ejecutar
            priority: Prioridad (mayor = más urgente)
        
        Returns:
            ActiveSubAgent con la prioridad configurada
        """
        return self.spawn_background(agent_id, task, priority=priority)

    def steer(self, run_id_prefix: str, instruction: str) -> bool:
        sub = get_by_prefix(run_id_prefix)
        if sub is None or sub.status != "running":
            return False
        sub.steer_queue.put(instruction)
        sub.steer_count += 1
        return True

    def kill(self, run_id_prefix: str) -> bool:
        sub = get_by_prefix(run_id_prefix)
        if sub is None or sub.status not in ("queued", "running"):
            return False
        sub.kill_event.set()
        sub.status = "killed"
        return True

    def kill_all(self) -> int:
        n = 0
        with _registry_lock:
            for sub in _registry.values():
                if sub.status in ("queued", "running"):
                    sub.kill_event.set()
                    sub.status = "killed"
                    n += 1
        return n

    # ── Tool schemas ───────────────────────────────────────────────────────────

    def as_tool_schema(self) -> tuple:
        agent_ids  = [a.id for a in self.config.agents]
        ids_str    = ", ".join(f'"{i}"' for i in agent_ids)
        model_name = self.config.model or "modelo actual"

        def spawn_subagent(agent_id: str, task: str, timeout_seconds: int = 0) -> str:
            if agent_id not in agent_ids:
                return f"Error: agente '{agent_id}' no existe. Disponibles: {ids_str}"
            sub = self.spawn_background(agent_id, task, priority=0,
                                        timeout_seconds=timeout_seconds)
            sub.thread.join()
            elapsed_str = _fmt_elapsed(sub.elapsed())
            if sub.status == "killed":
                if not self._parent_webui_queue:
                    console.print(
                        f"  [dim red]⎿  Timeout ({elapsed_str}): subagente detenido[/dim red]"
                    )
                return (
                    f"Timeout: el subagente '{agent_id}' fue detenido tras {timeout_seconds}s "
                    f"sin completar la tarea. Considera dividir la tarea o aumentar el timeout."
                )
            if sub.error:
                if not self._parent_webui_queue:
                    console.print(
                        f"  [dim red]⎿  Error ({elapsed_str}): {sub.error[:120]}[/dim red]"
                    )
                return f"Error en subagente: {sub.error}"
            # Footer con estadísticas
            n_tools     = sub.n_tool_uses
            n_tok       = sub.n_tokens_out
            tok_str     = (f" · {n_tok // 1000:.1f}k tokens" if n_tok >= 1000
                           else (f" · {n_tok} tokens" if n_tok > 0 else ""))
            tools_str   = f"{n_tools} tool use{'s' if n_tools != 1 else ''}" if n_tools > 0 else ""
            stats_inner = "  ·  ".join(filter(None, [tools_str, tok_str.lstrip(" · "), elapsed_str]))
            if not self._parent_webui_queue:
                console.print(f"  [dim]⎿  Done ({stats_inner}) (ctrl+o to expand)[/dim]")
            return sub.result or ""

        schema = {
            "name": "spawn_subagent",
            "description": (
                f"Lanza un subagente con contexto aislado para ejecutar una tarea. "
                f"El subagente usa el mismo modelo ({model_name}) y servidor Ollama. "
                f"Su output es visible en tiempo real en la conversación (prefijo │). "
                f"Agentes disponibles: {ids_str}. "
                "Útil para delegar tareas en workspaces independientes. "
                "IMPORTANTE: si hay un plan activo, llama task_done() justo después "
                "para marcar la tarea del plan como completada."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": f"ID del agente. Uno de: {ids_str}",
                    },
                    "task": {
                        "type": "string",
                        "description": "Tarea completa que debe ejecutar el subagente.",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": (
                            "Segundos máximos antes de matar el subagente automáticamente. "
                            "0 = sin timeout (por defecto). Útil para tareas acotadas "
                            "donde un cuelgue bloquearía la cola."
                        ),
                    },
                },
                "required": ["agent_id", "task"],
            },
        }
        return "spawn_subagent", spawn_subagent, schema

    def as_explore_schema(self) -> tuple:
        """Tool 'explore': subagente read-only para mapear código antes de modificarlo."""
        model_name = self.config.model or "modelo actual"
        # Usar el primer agente disponible como base del explore
        agent_ids  = [a.id for a in self.config.agents]
        base_agent = agent_ids[0] if agent_ids else "main"

        def explore(task: str) -> str:
            """Lanza un subagente read-only de exploración."""
            console.print(f"  [bold cyan]🔍 Explorando:[/bold cyan] [dim]{task}[/dim]")

            run_id  = uuid.uuid4().hex
            kill_ev = threading.Event()
            steer_q: queue.SimpleQueue = queue.SimpleQueue()

            sub = ActiveSubAgent(
                run_id      = run_id,
                agent_id    = base_agent,
                agent_name  = "Explore",
                agent_emoji = "🔍",
                task        = task,
                thread      = None,  # type: ignore[arg-type]
                kill_event  = kill_ev,
                steer_queue = steer_q,
            )
            _register(sub)

            def _worker():
                try:
                    sub.result = self.run(
                        base_agent, task, silent=False,
                        kill_event=kill_ev, steer_queue=steer_q,
                        explore_mode=True,
                    )
                    if sub.status == "running":
                        sub.status = "done"
                except Exception as exc:
                    sub.error  = str(exc)
                    sub.status = "error"
                finally:
                    sub.finished_at = time.time()
                    _deregister(run_id)

            t = threading.Thread(target=_worker, daemon=True,
                                 name=f"oocode-explore-{run_id[:6]}")
            sub.thread = t
            t.start()
            sub.thread.join()
            if sub.error:
                return f"Error en explore: {sub.error}"
            return sub.result or ""

        schema = {
            "name": "explore",
            "description": (
                "Subagente read-only para explorar código SOLO cuando NO lo has leído todavía "
                "y la tarea requiere entender la arquitectura antes de modificar. "
                "NO llames explore si ya has leído los ficheros relevantes o ya conoces la estructura. "
                "NO llames explore para tareas simples (un fichero, un símbolo conocido). "
                "USA grep_code/code_search/read_file directamente cuando ya sabes qué buscar. "
                f"Usa el modelo {model_name}. Su output es visible en tiempo real (prefijo │🔍). "
                "El subagente NO puede escribir ni editar ficheros — solo lee y busca."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": (
                            "Pregunta específica de exploración — qué arquitectura/módulos necesitas entender. "
                            "Ej: 'Mapea cómo fluye una conexión TCP desde accept() hasta el bucle de comandos en src/', "
                            "'¿Qué ficheros implementan el sistema de combate y cómo se relacionan?'"
                        ),
                    },
                },
                "required": ["task"],
            },
        }
        return "explore", explore, schema

    def as_team_schemas(self) -> list[tuple[str, object, dict]]:
        """Tools 'create_team' y 'run_team' para orquestar equipos de agentes."""
        from agent.tasks import create_team as _create_team_fn, _load_team_obj

        agent_ids = [a.id for a in self.config.agents]
        ids_str   = ", ".join(f'"{i}"' for i in agent_ids)

        default_lead = agent_ids[0] if agent_ids else "main"

        def create_team(team_id: str, subtasks: list,
                        lead_agent_id: str = default_lead) -> str:
            """Crea un equipo de agentes con subtasks asignadas a miembros."""
            if not team_id or not subtasks:
                return "Error: team_id y subtasks son obligatorios"
            if lead_agent_id not in agent_ids:
                return (f"Error: lead_agent_id '{lead_agent_id}' no existe. "
                        f"Disponibles: {ids_str}")
            invalid = [st.get("assign_to") for st in subtasks
                       if isinstance(st, dict) and st.get("assign_to") not in agent_ids]
            if invalid:
                return (f"Error: agente(s) no válidos en assign_to: {invalid}. "
                        f"Disponibles: {ids_str}")
            members = list({st.get("assign_to", lead_agent_id) for st in subtasks
                            if isinstance(st, dict)})
            members = [lead_agent_id] + [m for m in members if m != lead_agent_id]
            team = _create_team_fn(team_id, lead_agent_id, members)
            from agent.tasks import add_subtask as _add_st
            added = 0
            for st in subtasks:
                if not isinstance(st, dict):
                    continue
                desc = st.get("description", "").strip()
                assign = st.get("assign_to", lead_agent_id)
                if desc:
                    _add_st(team_id, desc, assign)
                    added += 1
            lines = [f"Equipo '{team_id}' creado — lead: {lead_agent_id}, {added} subtask(s):"]
            for st in subtasks:
                if isinstance(st, dict) and st.get("description"):
                    lines.append(f"  [{st.get('assign_to', lead_agent_id)}] {st['description']}")
            lines.append("Llama run_team(team_id) para ejecutar todas las subtasks en paralelo.")
            return "\n".join(lines)

        def run_team(team_id: str) -> str:
            """Ejecuta todas las subtasks del equipo en paralelo y devuelve los resultados."""
            team_obj = _load_team_obj(team_id)
            if team_obj is None:
                return f"Error: equipo '{team_id}' no encontrado. Créalo primero con create_team()."
            pending = team_obj.get_pending_subtasks()
            if not pending:
                if team_obj.is_all_completed():
                    return f"El equipo '{team_id}' ya completó todas sus subtasks."
                return f"El equipo '{team_id}' no tiene subtasks pendientes."
            if not self._parent_webui_queue:
                console.print(
                    f"  [bold cyan]◈ Equipo [white]{team_id}[/white]:[/bold cyan] "
                    f"ejecutando [cyan]{len(pending)}[/cyan] subtask(s) en paralelo…"
                )
            results = team_obj.execute(self)
            # Formatear resultados para que el lead agent pueda sintetizarlos
            n_ok  = sum(1 for st in team_obj.subtasks if st["status"] == "completed")
            n_err = len(team_obj.subtasks) - n_ok
            sections = [f"## Resultados del equipo '{team_id}' ({n_ok} OK, {n_err} errores)\n"]
            for st in team_obj.subtasks:
                sid  = st["id"]
                desc = st["description"]
                who  = st["assign_to"]
                stat = st["status"]
                res  = (results.get(sid, "") or "").strip()
                header = f"### [{who}] {desc}"
                if stat == "completed":
                    # Truncar resultados muy largos por subtask (≤4000 chars)
                    if len(res) > 4000:
                        res = res[:4000] + f"\n… [truncado — {len(res)-4000} chars más]"
                    sections.append(f"{header}\n{res}" if res else f"{header}\n_(sin output)_")
                else:
                    sections.append(f"{header}\n⛔ {stat}: {res}")
            sections.append(
                "\n---\n"
                "Sintetiza los resultados anteriores en una respuesta estructurada para el usuario. "
                "Combina los hallazgos de todos los agentes, destaca lo completado, "
                "y menciona cualquier error si los hay."
            )
            return "\n\n".join(sections)

        create_schema = {
            "name": "create_team",
            "description": (
                "Crea un equipo de agentes especializados con subtasks asignadas a cada miembro. "
                "Úsalo cuando la tarea tenga dominios distintos (código, documentación, búsqueda web) "
                "que pueden ejecutarse en paralelo. "
                f"Agentes disponibles: {ids_str}. "
                "Después de crear el equipo, llama run_team(team_id) para ejecutar todo en paralelo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "team_id": {
                        "type": "string",
                        "description": "Identificador único del equipo en kebab-case (ej: 'refactor-2024')",
                    },
                    "subtasks": {
                        "type": "array",
                        "description": "Lista de subtasks, cada una con 'description' y 'assign_to'",
                        "items": {
                            "type": "object",
                            "properties": {
                                "description": {
                                    "type": "string",
                                    "description": "Descripción concisa de la subtask",
                                },
                                "assign_to": {
                                    "type": "string",
                                    "description": f"ID del agente que ejecuta esta subtask: {ids_str}",
                                },
                            },
                            "required": ["description", "assign_to"],
                        },
                    },
                    "lead_agent_id": {
                        "type": "string",
                        "description": f"Agente coordinador (default: '{default_lead}'). Opciones: {ids_str}",
                    },
                },
                "required": ["team_id", "subtasks"],
            },
        }

        run_schema = {
            "name": "run_team",
            "description": (
                "Ejecuta todas las subtasks pendientes del equipo en paralelo y devuelve los resultados "
                "de cada subagente para que puedas sintetizarlos. "
                "Bloquea hasta que todas las subtasks terminen. "
                "Llama create_team() primero si el equipo no existe."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "team_id": {
                        "type": "string",
                        "description": "ID del equipo a ejecutar (creado con create_team)",
                    },
                },
                "required": ["team_id"],
            },
        }

        return [
            ("create_team", create_team, create_schema),
            ("run_team",    run_team,    run_schema),
        ]

    def as_fanout_schema(self) -> tuple:
        """Tool 'spawn_fanout': mismo agente × N chunks en paralelo (divide y vencerás)."""
        agent_ids = [a.id for a in self.config.agents]
        ids_str   = ", ".join(f'"{i}"' for i in agent_ids)

        def spawn_fanout(agent_id: str, task_chunks: list,
                         timeout_seconds: int = 0) -> str:
            if agent_id not in agent_ids:
                return f"Error: agente '{agent_id}' no existe. Disponibles: {ids_str}"
            chunks = [c for c in task_chunks if isinstance(c, str) and c.strip()]
            if not chunks:
                return "Error: task_chunks no puede estar vacío"
            if len(chunks) > 10:
                return f"Error: máximo 10 chunks (recibidos: {len(chunks)})"

            if not self._parent_webui_queue:
                console.print(
                    f"  [bold cyan]⚡ Fanout[/bold cyan] [dim]{agent_id}[/dim]  "
                    f"ejecutando [cyan]{len(chunks)}[/cyan] chunks en paralelo…"
                )

            # Lanzar todos los chunks via spawn_background:
            # hereda semáforo de concurrencia, kill_event y watchdog de timeout.
            subs: list[tuple[int, "ActiveSubAgent"]] = []
            for i, chunk in enumerate(chunks):
                sub = self.spawn_background(
                    agent_id, chunk, timeout_seconds=timeout_seconds,
                )
                # Prefijo cosmético para identificar cada worker en /agents
                sub.task = f"[fanout {i+1}/{len(chunks)}] {chunk}"
                subs.append((i, sub))
            for _, sub in subs:
                sub.thread.join()

            results: dict[int, str] = {}
            errors:  dict[int, str] = {}
            for i, sub in subs:
                if sub.status == "done":
                    results[i] = sub.result or ""
                elif sub.status == "killed":
                    errors[i] = sub.error or f"Timeout tras {timeout_seconds}s"
                else:
                    errors[i] = sub.error or "unknown error"

            n_ok  = len(results)
            n_err = len(errors)
            sections = [f"## Fanout {agent_id}: {n_ok}/{len(chunks)} chunks OK\n"]
            for i, chunk in enumerate(chunks):
                header = f"### Chunk {i+1}/{len(chunks)}: {chunk[:80]}"
                if i in results:
                    res = (results[i] or "").strip()
                    if len(res) > 4000:
                        res = res[:4000] + f"\n… [truncado — {len(res)-4000} chars más]"
                    sections.append(f"{header}\n{res}" if res else f"{header}\n_(sin output)_")
                else:
                    sections.append(f"{header}\n⛔ Error: {errors.get(i, 'unknown error')}")
            sections.append(
                "\n---\n"
                "Combina los hallazgos de todos los chunks anteriores en un análisis cohesivo. "
                "Identifica patrones comunes, diferencias importantes entre chunks, "
                "y extrae conclusiones globales."
            )
            return "\n\n".join(sections)

        schema = {
            "name": "spawn_fanout",
            "description": (
                "Lanza el MISMO agente en paralelo sobre N fragmentos del mismo problema "
                "(patrón divide y vencerás). Ideal para analizar múltiples módulos, "
                "directorios o secciones de un repo grande de forma simultánea. "
                "Diferencia con create_team: mismo agente + mismo dominio (problema fragmentado); "
                "create_team usa agentes distintos para dominios distintos (código, docs, web). "
                f"Agentes disponibles: {ids_str}. Máximo 10 chunks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": f"Agente que procesa todos los chunks. Uno de: {ids_str}",
                    },
                    "task_chunks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Lista de 1-10 chunks. Cada chunk es una tarea autónoma que el agente "
                            "puede ejecutar de forma independiente. "
                            "Ejemplo: ['Analiza src/auth/ buscando vulnerabilidades XSS', "
                            "'Analiza src/db/ buscando vulnerabilidades SQL injection', "
                            "'Analiza src/api/ buscando vulnerabilidades IDOR']"
                        ),
                        "minItems": 1,
                        "maxItems": 10,
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": (
                            "Segundos máximos por chunk antes de matarlo automáticamente. "
                            "0 = sin timeout (por defecto). Se aplica individualmente a cada chunk: "
                            "un chunk lento no bloquea los demás."
                        ),
                    },
                },
                "required": ["agent_id", "task_chunks"],
            },
        }
        return "spawn_fanout", spawn_fanout, schema


# Exportar funciones para tests
__all__ = ["SubAgentRunner", "ActiveSubAgent", "_get_concurrency_sem",
           "_register", "_deregister", "list_queued"]
