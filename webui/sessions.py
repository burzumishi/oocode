"""Gestión de sesiones WebUI: creación, evicción y acceso al AgentLoop."""
import logging
import queue
import threading
import time

# ── Tiempos y estructura ──────────────────────────────────────────────────────

_WEBUI_SESSIONS: dict[str, dict] = {}
_SESSIONS_LOCK = threading.Lock()
_SESSION_TTL   = 3600  # 1 hora de inactividad máxima

# Cola SSE acotada: si el consumidor SSE se desconecta y deja de leer,
# put_nowait() lanza queue.Full en lugar de acumular sin límite en memoria.
_WEBUI_QUEUE_MAX = 500


# ── Evicción de sesiones viejas ───────────────────────────────────────────────

def _evict_old_sessions() -> None:
    now = time.time()
    with _SESSIONS_LOCK:
        dead = [sid for sid, s in _WEBUI_SESSIONS.items()
                if now - s.get("last_active", now) > _SESSION_TTL]
        for sid in dead:
            try:
                loop = _WEBUI_SESSIONS[sid].get("loop")
                if loop:
                    loop.close()
            except Exception:
                pass
            del _WEBUI_SESSIONS[sid]


# ── Creación de sesión y loop ─────────────────────────────────────────────────

def _ensure_session_entry(sid: str, agent_id: str) -> "queue.Queue":
    """Devuelve la queue inmediatamente; crea el AgentLoop en background si es nueva sesión.

    Mantiene la conexión SSE rápida — el browser recibe 'connected' de inmediato
    en lugar de esperar 5-10s al arranque de subprocesos MCP.
    """
    _evict_old_sessions()
    with _SESSIONS_LOCK:
        if sid in _WEBUI_SESSIONS:
            _WEBUI_SESSIONS[sid]["last_active"] = time.time()
            return _WEBUI_SESSIONS[sid]["queue"]

        q: queue.Queue = queue.Queue(maxsize=_WEBUI_QUEUE_MAX)
        ready_evt = threading.Event()
        _WEBUI_SESSIONS[sid] = {
            "loop":        None,   # se rellena por el hilo de init
            "queue":       q,
            "thread":      None,
            "history":     [],
            "lock":        threading.Lock(),
            "created_at":  time.time(),
            "last_active": time.time(),
            "agent_id":    agent_id,
            "_ready":      ready_evt,
            "_gen":        0,       # generación SSE — para matar generadores fantasma
        }

    def _bg_init() -> None:
        try:
            loop = _create_loop_for_webui(agent_id, q)
            with _SESSIONS_LOCK:
                if sid in _WEBUI_SESSIONS:
                    _WEBUI_SESSIONS[sid]["loop"] = loop
        except Exception as exc:
            logging.getLogger("oocode.webui").error(
                "session_init_error sid=%s: %s", sid, exc
            )
            q.put_nowait({"type": "error", "error": f"Error iniciando agente: {exc}"})
        finally:
            with _SESSIONS_LOCK:
                if sid in _WEBUI_SESSIONS:
                    _WEBUI_SESSIONS[sid]["_ready"].set()

    threading.Thread(
        target=_bg_init, daemon=True, name=f"webui-init-{sid[:6]}"
    ).start()
    return q


def _get_or_create_session(sid: str, agent_id: str = "main") -> dict:
    """Devuelve el dict de sesión, esperando hasta 30s a que el loop se inicialice."""
    _ensure_session_entry(sid, agent_id)
    with _SESSIONS_LOCK:
        sess = _WEBUI_SESSIONS.get(sid)
    if not sess:
        raise RuntimeError(f"Session {sid} evicted during init")
    ready = sess.get("_ready")
    if ready and not ready.is_set():
        ready.wait(timeout=30.0)
    with _SESSIONS_LOCK:
        return _WEBUI_SESSIONS.get(sid, sess)


# ── Creación del AgentLoop completo ──────────────────────────────────────────

def _create_loop_for_webui(agent_id: str, out_queue: queue.Queue):
    """Crea un AgentLoop completo para el WebUI (igual que el TUI)."""
    import sys as _sys
    from pathlib import Path as _Path

    _PROJECT_ROOT = str(_Path(__file__).parent.parent)
    if _PROJECT_ROOT not in _sys.path:
        _sys.path.insert(0, _PROJECT_ROOT)

    from config import OOConfig
    from agent.loop import AgentLoop
    from agent.session import SessionManager
    from agent.services import (
        build_workspace_manager, build_embedding_client, build_memory_system,
    )
    from tools.permissions import PermissionManager
    from oocode import build_registry

    cfg = OOConfig.load()

    # Si se especifica un agente distinto, cargar su config
    if agent_id and agent_id != cfg.agent_id:
        target = next((a for a in cfg.agents if a.id == agent_id), None)
        if target:
            cfg.agent_id    = target.id
            cfg.agent_name  = target.name
            cfg.agent_emoji = target.emoji
            if target.workspace:
                cfg.workspace = target.workspace

    project_dir = str(_Path.cwd())

    ws_manager = build_workspace_manager(cfg)
    if not ws_manager.exists():
        ws_manager.init()

    permissions = PermissionManager(cfg.permissions)
    permissions._non_interactive = True  # WebUI no tiene terminal interactiva

    embed_client = build_embedding_client(cfg)
    memory = build_memory_system(cfg, embed_client)

    registry = build_registry(project_dir, cfg)

    from agent.subagent import SubAgentRunner
    subagent_runner = SubAgentRunner(cfg, permissions, build_registry,
                                     embed_client=embed_client)
    _n, _f, _s = subagent_runner.as_tool_schema()
    registry.register(_n, _f, _s)
    _en, _ef, _es = subagent_runner.as_explore_schema()
    registry.register(_en, _ef, _es)

    _mem_ref = memory
    def _fn_mem_save(name: str, content: str, description: str = "") -> str:
        return _mem_ref.save(name, content, description)
    registry.register("mem_save", _fn_mem_save, {
        "name": "mem_save",
        "description": "Guarda un recuerdo persistente en la memoria del agente.",
        "parameters": {"type": "object", "properties": {
            "name":        {"type": "string"},
            "content":     {"type": "string"},
            "description": {"type": "string"},
        }, "required": ["name", "content"]},
    })

    session_mgr = SessionManager(cfg.agent_id)
    session_mgr.start(cfg.model or "", project_dir)

    from agent.runtime import RuntimeSettings
    runtime = RuntimeSettings(ctx_mode=getattr(cfg, "ctx_mode", "mini"))

    loop = AgentLoop(
        config=cfg,
        registry=registry,
        permissions=permissions,
        memory=memory,
        workspace_manager=ws_manager,
        session_manager=session_mgr,
        runtime=runtime,
        subagent_runner=subagent_runner,
        capture_output=False,
    )
    loop._webui_queue = out_queue
    # Usar _status_cb para SSE en lugar del Rich Live REPL (requiere TTY interactiva)
    loop._status_cb = lambda _status: None
    # Propagar cola al SubAgentRunner para que los subagentes emitan al SSE del browser
    if subagent_runner is not None:
        subagent_runner._parent_webui_queue = out_queue
        # En primary-only o sin hosts extra: compartir cliente para evitar reload de modelo.
        # En round-robin con hosts extra: cada subagente crea su propio cliente.
        _has_extra = len(cfg.all_ollama_hosts) > 1
        _is_po     = cfg.ollama_subagent_routing == "primary-only"
        if not _has_extra or _is_po:
            subagent_runner._parent_client = loop.client

    # ── Arrancar servidores MCP ──────────────────────────────────────────────
    _mcp_pool = None
    try:
        _active_mcp_servers = [s for s in cfg.mcp_servers if s.get("enabled", True)]
        _active_names = {s.get("name") for s in _active_mcp_servers}
        # Bundled (8 servidores) vía helper compartido con el TUI (agent/services.py):
        # única fuente de verdad para que ambas rutas arranquen el mismo conjunto.
        from agent.services import bundled_mcp_servers
        _active_mcp_servers.extend(bundled_mcp_servers(cfg, _active_names))

        if _active_mcp_servers:
            from agent.mcp_client import McpPool
            _mcp_pool = McpPool(request_timeout=cfg.mcp_request_timeout)
            for _srv in _active_mcp_servers:
                _mcp_pool.start_server(
                    name=_srv.get("name", "mcp"),
                    cmd=_srv.get("cmd", []),
                    env=_srv.get("env"),
                    cwd=_srv.get("cwd"),
                    description=_srv.get("description", ""),
                )
            for _n2, _f2, _s2 in _mcp_pool.all_oocode_tools():
                if not registry.has(_n2):
                    registry.register(_n2, _f2, _s2)
            for _n2, _f2, _s2 in _mcp_pool.resource_oocode_tools():
                if not registry.has(_n2):
                    registry.register(_n2, _f2, _s2)
            for _n2, _f2, _s2 in _mcp_pool.prompt_oocode_tools():
                if not registry.has(_n2):
                    registry.register(_n2, _f2, _s2)
    except Exception as _mcp_exc:
        logging.getLogger("oocode.webui").warning("mcp_init_error: %s", _mcp_exc)

    loop._mcp_pool = _mcp_pool
    subagent_runner._parent_mcp_pool = _mcp_pool

    return loop
