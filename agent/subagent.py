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
    steer_count: int   = 0               # instrucciones steer enviadas
    priority:     int   = 0               # prioridad de la tarea (mayor = más urgente)
    queue_time:   float = 0.0            # tiempo en cola (para background agents)

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

# Cola de subagentes con gestión de prioridades
_subagent_queue: list[tuple[float, int, "ActiveSubAgent"]] = []  # (timestamp, priority, sub)
_queue_lock = threading.Lock()

# Worker global para procesar la cola de subagentes
_queue_worker: Optional[threading.Thread] = None
_queue_shutdown = threading.Event()


def _enqueue(sub: "ActiveSubAgent") -> None:
    """Añade subagente a la cola con gestión de prioridades."""
    global _subagent_queue
    with _queue_lock:
        _subagent_queue.append((time.time(), sub.priority, sub))
        # Ordenar por prioridad (mayor primero)
        _subagent_queue.sort(key=lambda x: x[1], reverse=True)


def _dequeue() -> Optional["ActiveSubAgent"]:
    """Extrae subagente de la cola."""
    global _subagent_queue
    with _queue_lock:
        if _subagent_queue:
            # Extraer el de mayor prioridad
            _, _, sub = _subagent_queue.pop(0)
            return sub
    return None


def _queue_worker_fn() -> None:
    """Worker global que procesa la cola de subagentes."""
    global _queue_worker
    _queue_worker = threading.current_thread()
    
    while not _queue_shutdown.is_set():
        sub = _dequeue()
        if sub is None:
            # Esperar un breve periodo antes de revisar la cola
            time.sleep(0.01)
            continue
        
        # Iniciar worker para este subagente
        def _process_sub(sub: ActiveSubAgent) -> None:
            try:
                sub.result = self.run(
                    sub.agent_id, sub.task, silent=True,
                    kill_event=sub.kill_event, steer_queue=sub.steer_queue,
                    priority=sub.priority,
                )
                if sub.status == "running":
                    sub.status = "done"
            except Exception as exc:
                sub.error = str(exc)
                sub.status = "error"
            finally:
                sub.finished_at = time.time()
                _deregister(sub.run_id)
        
        t = threading.Thread(
            target=_process_sub, daemon=True,
            name=f"oocode-sub-{sub.run_id[:6]}",
        )
        sub.thread = t
        t.start()


def _start_queue_worker() -> None:
    """Inicia el worker global de la cola."""
    global _queue_worker
    if _queue_worker is None or not _queue_worker.is_alive():
        _queue_worker = threading.Thread(target=_queue_worker_fn, daemon=True)
        _queue_worker.start()


_RECENT_TTL = 1800   # segundos que permanecen los subagentes finalizados (30 min)


def _deregister(run_id: str) -> None:
    with _registry_lock:
        if run_id in _registry:
            sub = _registry[run_id]
            sub.finished_at = time.time()
            # Solo sobreescribir si aún figura como running (el worker puede haber
            # fijado "error" o "killed" antes de llamar a _deregister)
            if sub.status == "running":
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
    """Todos los subagentes del registro (running + recientes). Orden: running primero."""
    with _registry_lock:
        all_subs = list(_registry.values())
    running = [s for s in all_subs if s.status == "running"]
    finished = sorted(
        [s for s in all_subs if s.status != "running"],
        key=lambda s: s.finished_at or 0, reverse=True,
    )
    return running + finished


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
        self._parent_rt      = None             # RuntimeSettings del padre (se inyecta en oocode.py)

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
            explore_mode: bool = False, priority: int = 0) -> str:
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

        # Forzar mismo modelo e host que el padre (restricción VRAM)
        sub_config.model                = self.config.model
        sub_config.ollama_host          = self.config.ollama_host
        sub_config.embed_model          = self.config.embed_model
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
                host=sub_config.ollama_host,
                model=sub_config.embed_model,
                max_input_chars=sub_config.embed_max_input_chars,
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

        # Inyectar steer_queue y kill_event para control externo
        loop._steer_queue = steer_queue
        loop._ext_kill    = kill_event

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

        result = loop.run(task)
        session_manager.end()

        if not silent:
            console.rule(
                f"[dim]↲ fin subagente {sub_config.agent_name}[/dim]",
                style="cyan dim",
            )
            console.print()

        return result or ""

    def spawn_background(self, agent_id: str, task: str, priority: int = 0) -> "ActiveSubAgent":
        """Lanza un subagente en background y lo registra. Devuelve el handle."""
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
            priority     = priority,  # prioridad configurada
            queue_time   = 0.0,
        )
        
        # Añadir a la cola con gestión de prioridades
        _enqueue(sub)
        
        # Iniciar worker en thread
        def _worker():
            try:
                sub.result = self.run(
                    agent_id, task, silent=True,
                    kill_event=kill_ev, steer_queue=steer_q,
                    priority=priority,
                )
                if sub.status == "running":   # no machacar "killed"
                    sub.status = "done"
            except Exception as exc:
                sub.error  = str(exc)
                sub.status = "error"
            finally:
                sub.finished_at = time.time()
                _deregister(run_id)

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
        if sub is None or sub.status != "running":
            return False
        sub.kill_event.set()
        sub.status = "killed"
        return True

    def kill_all(self) -> int:
        n = 0
        with _registry_lock:
            for sub in _registry.values():
                if sub.status == "running":
                    sub.kill_event.set()
                    sub.status = "killed"
                    n += 1
        return n

    # ── Tool schemas ───────────────────────────────────────────────────────────

    def as_tool_schema(self) -> tuple:
        agent_ids  = [a.id for a in self.config.agents]
        ids_str    = ", ".join(f'"{i}"' for i in agent_ids)
        model_name = self.config.model or "modelo actual"

        def spawn_subagent(agent_id: str, task: str) -> str:
            if agent_id not in agent_ids:
                return f"Error: agente '{agent_id}' no existe. Disponibles: {ids_str}"
            sub = self.spawn_background(agent_id, task, priority=0)
            sub.thread.join()
            if sub.error:
                return f"Error en subagente: {sub.error}"
            return sub.result or ""

        schema = {
            "name": "spawn_subagent",
            "description": (
                f"Lanza un subagente con contexto aislado para ejecutar una tarea. "
                f"El subagente usa el mismo modelo ({model_name}) y servidor Ollama. "
                f"Su output es visible en tiempo real en la conversación (prefijo │). "
                f"Agentes disponibles: {ids_str}. "
                "Útil para delegar tareas en workspaces independientes."
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
            console.print(f"  [bold cyan]🔍 Explorando:[/bold cyan] [dim]{task[:120]}[/dim]")

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
