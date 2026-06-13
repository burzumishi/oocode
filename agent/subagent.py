"""Sistema de subagentes con visibilidad en tiempo real, steer y kill.

Cada subagente se ejecuta en su propio thread daemon y escribe su output
directamente al console del padre (prefijado con │ para distinguirlo).
El padre puede steer (inyectar nuevas instrucciones) o kill desde /subagents.
"""
import os
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
    last_activity: float = field(default_factory=time.time)  # heartbeat: última señal de progreso (inicio de cada paso/petición LLM)
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

    def heartbeat(self) -> None:
        """Marca progreso del subagente (lo llama el AgentLoop al iniciar cada paso).

        El watchdog de timeout mide INACTIVIDAD (tiempo desde el último heartbeat),
        no tiempo total: así el timeout es efectivamente "por petición al LLM / paso"
        y un subagente que avanza de forma sostenida no se detiene por acumular tiempo.
        """
        self.last_activity = time.time()

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
    """Bootstrap de recentTtl desde oocode.json (default = DEFAULT_CONFIG).

    Se usa en import-time porque la UI puede llamar a list_recent() antes de que
    exista un SubAgentRunner. En cuanto se crea el runner, set_recent_ttl() instala
    el valor canónico de config.subagents_recent_ttl.
    """
    from config import DEFAULT_CONFIG as _DC
    _default = int(_DC["subagents"]["recentTtl"])
    try:
        from pathlib import Path as _P
        import json as _j
        _f = _P.home() / ".oocode" / "oocode.json"
        if _f.exists():
            return int(_j.loads(_f.read_text()).get("subagents", {}).get("recentTtl", _default))
    except Exception:
        pass
    return _default


_RECENT_TTL = _get_recent_ttl()


def set_recent_ttl(value: int) -> None:
    """Instala el TTL canónico (config.subagents_recent_ttl) usado por list_recent()."""
    global _RECENT_TTL
    try:
        _RECENT_TTL = int(value)
    except (TypeError, ValueError):
        pass


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


def list_recent(ttl: Optional[float] = None) -> list[ActiveSubAgent]:
    """Subagentes finalizados en los últimos `ttl` segundos, más recientes primero.

    `ttl=None` usa el valor del módulo (`_RECENT_TTL`), que el runner sincroniza
    con `config.subagents_recent_ttl` al arrancar.
    """
    if ttl is None:
        ttl = _RECENT_TTL
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
        self._parent_client  = parent_client    # BackendClient del padre (evita reload del modelo)
        self._parent_rt         = None   # RuntimeSettings del padre (se inyecta en oocode.py)
        self._parent_webui_queue = None  # queue del padre en modo WebUI (se inyecta en sessions.py)
        self._parent_live_start_cb = None  # _update_live_tool_start del padre (TUI live block)
        self._parent_live_done_cb  = None  # _subagent_update_live_tools del padre (TUI live block)
        # Semáforo de concurrencia: inicializado desde config.subagents_max_concurrent
        max_c = getattr(config, "subagents_max_concurrent", 4)
        self._concurrency_sem = _get_concurrency_sem(max_c)
        # Sincroniza el TTL de subagentes recientes con config (fuente canónica)
        set_recent_ttl(getattr(config, "subagents_recent_ttl", _RECENT_TTL))

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
        sub_config.api_type                 = self.config.api_type
        sub_config.api_key                  = self.config.api_key
        sub_config.api_base_url             = self.config.api_base_url
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
        # Límites específicos para subagentes: auto-continues e inferencia
        # (separados del agente principal para que las tareas largas no se corten)
        _ac = getattr(self.config, "subagents_auto_cont_max", 0)
        if isinstance(_ac, int) and _ac > 0:
            sub_config.auto_continue_max = _ac
        # inferenceTimeout fuerza el timeout de inferencia del subagente con máxima
        # prioridad (override de runtime), independiente de fallback/per-model.
        _it = getattr(self.config, "subagents_inference_timeout", 0)
        if isinstance(_it, int) and _it > 0:
            sub_config.inference_timeout_override = _it

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
            memory_full_max_chars=sub_config.ws_memory_full_max_chars,
        )
        if not ws_manager.exists():
            ws_manager.init()

        session_manager = SessionManager(sub_config.agent_id)
        session_manager.start(sub_config.model or "", sub_config.workspace)

        # El workdir de las tools (bash/python_exec/workspace_remember) debe ser el
        # PROYECTO del padre, NO el workspace de identidad (~/.oocode/workspace/<id>,
        # que solo contiene identidad/memoria). Sin esto, bash recibía cwd= el
        # workspace con '~' literal sin expandir y fallaba con:
        #   "No such file or directory: '~/.oocode/workspace/coding'".
        # Se alinea con el agente principal (build_registry(project_dir, …)).
        _tool_workdir = os.path.expanduser(
            sub_config.project_dir or sub_config.workspace
        )
        registry = self.build_registry_fn(_tool_workdir, sub_config)

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
            backend_client=self._parent_client,  # reutiliza cliente del padre
        )

        # Inyectar steer_queue, kill_event y referencia al registro de stats
        loop._steer_queue   = steer_queue
        loop._ext_kill      = kill_event
        loop._sub_stats_ref = sub_ref   # ActiveSubAgent | None — para actualizar stats

        # Propagar cola WebUI del padre: los eventos del subagente fluyen al SSE del browser
        if self._parent_webui_queue is not None:
            loop._webui_queue = self._parent_webui_queue
            loop._status_cb   = lambda _: None   # sin TUI status bar
        elif self._parent_live_start_cb is not None:
            # TUI: inyectar callbacks del padre para el sliding window del live block.
            # Las tools del subagente actualizan el mismo ◐/completed_tools del padre.
            loop._update_live_tool_start_cb = self._parent_live_start_cb
            loop._update_live_tools_cb      = self._parent_live_done_cb
            loop._status_cb                 = lambda _: None  # sentinel non-None

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
                        "message": {"type": "string", "description": "Narración del desenlace (qué hiciste, qué decidiste y por qué, resultado) — se muestra al usuario; no repitas solo el título"},
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

        Si timeout_seconds > 0, un watchdog por INACTIVIDAD dispara kill_event si el
        subagente pasa `timeout_seconds` SIN progreso (sin heartbeat) y marca el
        subagente como 'killed' con sub.error = "Timeout: …". Es un timeout por
        paso/petición al LLM, no por tiempo total: un subagente que avanza de forma
        sostenida no se detiene aunque la tarea completa dure más que `timeout_seconds`.
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
                sub.last_activity = sub.started_at   # primer paso arranca con presupuesto completo
                sub.status      = "running"
                # Watchdog por INACTIVIDAD (no por tiempo total): dispara kill_ev solo
                # si el subagente pasa `secs` sin progreso. El AgentLoop llama a
                # sub.heartbeat() al iniciar cada paso (cada petición al LLM), así que
                # `secs` es un timeout "por petición / paso", no un límite acumulado:
                # un subagente que avanza de forma sostenida no se detiene aunque la
                # tarea total dure más de `secs`. Si una sola petición se cuelga más de
                # `secs`, sí se mata. (Antes era ev.wait(secs) one-shot = tiempo total.)
                if timeout_seconds > 0:
                    def _watchdog(ev=kill_ev, s=sub, secs=timeout_seconds):
                        poll = min(5.0, max(1.0, secs / 4.0))
                        while not ev.wait(timeout=poll):
                            if s.status != "running":
                                return
                            idle = time.time() - s.last_activity
                            if idle >= secs:
                                s.error  = (f"Timeout: subagente sin progreso durante "
                                            f"{int(idle)}s (límite {secs}s por paso)")
                                s.status = "killed"
                                ev.set()
                                return
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
                # Liberar el hilo watchdog: en una finalización normal kill_ev nunca
                # se setea, por lo que el watchdog quedaría dormido el `secs` completo.
                # Como run() ya retornó, el AgentLoop no volverá a inspeccionar _ext_kill,
                # así que setearlo aquí solo despierta al watchdog (no dispara ningún kill).
                kill_ev.set()
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

    def _agents_descr(self) -> str:
        """Lista descriptiva de agentes disponibles: id + emoji + Rol (IDENTITY.md).

        Permite al LLM elegir el agente adecuado de forma genérica (sin depender de
        un prompt específico): p.ej. saber que 'webcrawler' sirve para búsquedas web.
        Cacheada por construcción de schemas. Cae al id solo si no hay Rol.
        """
        if getattr(self, "_agents_descr_cache", None) is not None:
            return self._agents_descr_cache
        from workspace.manager import agent_role as _agent_role
        lines: list[str] = []
        for a in self.config.agents:
            rol = _agent_role(getattr(a, "workspace", "")) or ""
            emoji = getattr(a, "emoji", "") or ""
            if rol:
                lines.append(f'- "{a.id}" {emoji}: {rol}'.rstrip())
            else:
                lines.append(f'- "{a.id}" {emoji}'.rstrip())
        self._agents_descr_cache = "\n".join(lines)
        return self._agents_descr_cache

    def as_tool_schema(self) -> tuple:
        agent_ids  = [a.id for a in self.config.agents]
        ids_str    = ", ".join(f'"{i}"' for i in agent_ids)
        model_name = self.config.model or "modelo actual"

        def spawn_subagent(agent_id: str, task: str, timeout_seconds: int = 0) -> str:
            if agent_id not in agent_ids:
                return f"Error: agente '{agent_id}' no existe. Disponibles: {ids_str}"
            # Aplicar defaultTimeout de config si el LLM no especificó uno
            _eff_timeout = timeout_seconds
            if _eff_timeout == 0:
                _def = getattr(self.config, "subagents_default_timeout", 0)
                if isinstance(_def, int) and _def > 0:
                    _eff_timeout = _def
            _dp = getattr(self.config, "subagents_default_priority", 0)
            _prio = _dp if isinstance(_dp, int) and not isinstance(_dp, bool) else 0
            sub = self.spawn_background(agent_id, task, priority=_prio,
                                        timeout_seconds=_eff_timeout)
            sub.thread.join()
            elapsed_str = _fmt_elapsed(sub.elapsed())
            if sub.status == "killed":
                # Distinguir kill por watchdog (timeout) vs kill manual del usuario
                # (/kill, /kill all): el watchdog marca sub.error="Timeout: …", el
                # kill_all manual no pone error. Sin esto, /kill reportaba "Timeout".
                _is_timeout = bool(sub.error) and str(sub.error).startswith("Timeout")
                if _is_timeout:
                    if not self._parent_webui_queue:
                        console.print(
                            f"  [dim red]⎿  Timeout ({elapsed_str}): subagente sin progreso[/dim red]"
                        )
                    return (
                        f"Timeout: el subagente '{agent_id}' se detuvo tras {_eff_timeout}s "
                        f"SIN progreso en un paso (no por tiempo total). Una sola petición al "
                        f"LLM o tool se colgó; reintenta, divide la tarea o sube "
                        f"`subagents.defaultTimeout` en oocode.json."
                    )
                if not self._parent_webui_queue:
                    console.print(
                        f"  [dim yellow]⎿  Detenido por el usuario ({elapsed_str})[/dim yellow]"
                    )
                return (
                    f"El subagente '{agent_id}' fue detenido por el usuario (/kill) "
                    f"tras {elapsed_str}."
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
                f"Agentes disponibles (elige el más afín a la tarea):\n{self._agents_descr()}\n"
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
                            "Segundos máximos SIN progreso (por paso/petición al LLM, no "
                            "tiempo total) antes de matar el subagente. Un subagente que "
                            "avanza no se detiene aunque la tarea total dure más. "
                            "0 = usa subagents.defaultTimeout (por defecto)."
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
            from rich.markup import escape as _esc
            from rich.markdown import Markdown as _Md
            from rich.padding import Padding as _Pad
            # task puede ser markdown multilínea: 1.ª línea inline (escapada para que
            # el markup Rich no se interprete), resto como Markdown renderizado.
            _t_lines = task.split('\n', 1)
            _t_head  = _t_lines[0].rstrip()
            _t_rest  = _t_lines[1] if len(_t_lines) > 1 else ""
            console.print(f"  [bold cyan]🔍 Explorando:[/bold cyan] [dim]{_esc(_t_head)}[/dim]")
            if _t_rest.strip():
                console.print(_Pad(_Md(_t_rest.strip()), (0, 0, 0, 4)))

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
                            "Ej: 'Mapea cómo fluye una conexión TCP desde accept() hasta el bucle de comandos', "
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

        _mt = getattr(self.config, "subagents_max_teams", 3)
        _mts = getattr(self.config, "subagents_max_team_size", 5)
        _max_teams     = _mt  if isinstance(_mt, int)  and not isinstance(_mt, bool)  else 3
        _max_team_size = _mts if isinstance(_mts, int) and not isinstance(_mts, bool) else 5

        def create_team(team_id: str, subtasks: list,
                        lead_agent_id: str = default_lead) -> str:
            """Crea un equipo de agentes con subtasks asignadas a miembros."""
            if not team_id or not subtasks:
                return "Error: team_id y subtasks son obligatorios"
            if lead_agent_id not in agent_ids:
                return (f"Error: lead_agent_id '{lead_agent_id}' no existe. "
                        f"Disponibles: {ids_str}")
            # Límite de equipos activos concurrentes (config.subagents.maxTeams)
            from agent.tasks import list_teams as _list_teams
            _active = [t for t in _list_teams()
                       if t.get("status") != "completed" and t.get("team_id") != team_id]
            if len(_active) >= _max_teams:
                return (f"Error: límite de equipos activos alcanzado "
                        f"({_max_teams}). Completa o elimina un equipo antes de crear otro.")
            invalid = [st.get("assign_to") for st in subtasks
                       if isinstance(st, dict) and st.get("assign_to") not in agent_ids]
            if invalid:
                return (f"Error: agente(s) no válidos en assign_to: {invalid}. "
                        f"Disponibles: {ids_str}")
            members = list({st.get("assign_to", lead_agent_id) for st in subtasks
                            if isinstance(st, dict)})
            members = [lead_agent_id] + [m for m in members if m != lead_agent_id]
            # Límite de tamaño de equipo (config.subagents.maxTeamSize)
            if len(members) > _max_team_size:
                return (f"Error: el equipo tiene {len(members)} miembros pero el máximo "
                        f"configurado es {_max_team_size} (subagents.maxTeamSize). "
                        f"Reduce el número de agentes distintos en assign_to.")
            _create_team_fn(team_id, lead_agent_id, members)
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
            lines.append(
                "Anuncia al usuario en 1 frase la composición del equipo y el reparto "
                "(quién hace qué y por qué), luego llama run_team(team_id) para ejecutar "
                "todas las subtasks en paralelo."
            )
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
                f"Agentes disponibles (asigna cada subtask al más afín):\n{self._agents_descr()}\n"
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

            # Aplicar defaultTimeout de config si el LLM no especificó uno
            _eff_timeout = timeout_seconds
            if _eff_timeout == 0:
                _def = getattr(self.config, "subagents_default_timeout", 0)
                if isinstance(_def, int) and _def > 0:
                    _eff_timeout = _def

            if not self._parent_webui_queue:
                console.print(
                    f"  [bold cyan]⚡ Fanout[/bold cyan] [dim]{agent_id}[/dim]  "
                    f"ejecutando [cyan]{len(chunks)}[/cyan] chunks en paralelo…"
                )

            # Lanzar todos los chunks via spawn_background:
            # hereda semáforo de concurrencia, kill_event y watchdog de timeout.
            _dp = getattr(self.config, "subagents_default_priority", 0)
            _prio = _dp if isinstance(_dp, int) and not isinstance(_dp, bool) else 0
            subs: list[tuple[int, "ActiveSubAgent"]] = []
            for i, chunk in enumerate(chunks):
                sub = self.spawn_background(
                    agent_id, chunk, priority=_prio, timeout_seconds=_eff_timeout,
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
                f"Agentes disponibles:\n{self._agents_descr()}\nMáximo 10 chunks."
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
                            "Ejemplo: ['Analiza el módulo de autenticación buscando vulnerabilidades XSS', "
                            "'Analiza la capa de base de datos buscando inyección SQL', "
                            "'Analiza la capa de API buscando vulnerabilidades IDOR']"
                        ),
                        "minItems": 1,
                        "maxItems": 10,
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": (
                            "Segundos máximos SIN progreso por chunk (por paso/petición al LLM, "
                            "no tiempo total) antes de matarlo. 0 = usa subagents.defaultTimeout. "
                            "Se aplica individualmente a cada chunk: un chunk lento no bloquea los demás."
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
