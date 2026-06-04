"""Blueprint /api/chat/* — con bugfixes para ghost generator y NameError sess."""
import json
import os
import queue
import threading
import time
from typing import Optional

from flask import Blueprint, Response, jsonify, request

from webui.sessions import _WEBUI_SESSIONS, _SESSIONS_LOCK, _ensure_session_entry, _get_or_create_session
from webui.helpers import _get_or_create_sid
from agent.session import append_input_history, load_input_history

bp = Blueprint("api_chat", __name__)

# ── Slash commands de estado ──────────────────────────────────────────────────

_ELEVATED_MODES = ("off", "on", "ask", "full")


def _restore_webui_session(loop, sess: dict, prefix: str) -> tuple[int, Optional[str]]:
    """Restaura una sesión pasada en el WebUI: contexto del LLM + historial mostrado.

    Reutiliza `AgentLoop.restore_session` (igual que el TUI) y repuebla `sess["history"]`
    desde la sesión JSONL para que el navegador pueda re-renderizar la conversación.
    Devuelve (n_mensajes, error|None). Acepta prefijo de session_id (como el TUI).
    """
    from agent.session import find_session_by_prefix
    agent_id = getattr(getattr(loop, "config", None), "agent_id", "main")
    full_id  = find_session_by_prefix(agent_id, prefix)
    if not full_id:
        return 0, f"Sesión '{prefix}' no encontrada. Usa el panel 📚 Sesiones."
    try:
        count = loop.restore_session(full_id)
        # Repoblar el historial mostrado en el navegador desde el JSONL
        restored = loop.session.load_messages(full_id)
        sess["history"].clear()
        for msg in restored:
            sess["history"].append({
                "role": msg.get("role", "assistant"),
                "text": msg.get("content", ""),
                "ts":   time.time(), "id": os.urandom(4).hex(),
            })
        return count, None
    except Exception as exc:
        return 0, f"Error restaurando sesión: {exc}"


def _handle_webui_slash(message: str, sess: dict) -> Optional[str]:
    """Intercepta slash commands de estado que no deben ir al LLM.
    Devuelve el texto de respuesta si fue manejado, None si debe ir al LLM."""
    loop = sess.get("loop")
    if not loop:
        return None

    stripped = message.strip()
    parts    = stripped.split(maxsplit=1)
    cmd      = parts[0].lower()
    args     = parts[1].strip() if len(parts) > 1 else ""

    if cmd == "/session":
        if not args:
            try:
                sid_cur = loop.session.session_id[:8]
                return f"Sesión activa: {sid_cur}…  ·  usa /session <id> o el panel 📚 Sesiones para restaurar"
            except Exception:
                return "Usa /session <id> o el panel 📚 Sesiones para restaurar una sesión."
        _t = sess.get("thread")
        if _t and _t.is_alive():
            return "⚠  El agente está activo — espera a que termine o usa /kill."
        count, err = _restore_webui_session(loop, sess, args)
        if err:
            return f"⚠ {err}"
        # El navegador re-renderiza la conversación restaurada al recibir 'done'
        # (flag _pendingSessionReload), por eso no se emite evento extra aquí.
        return f"✓  Sesión {args} restaurada — {count} mensajes en contexto"

    if cmd in ("/elevated", "/elev"):
        if not args:
            cur = getattr(getattr(loop, "rt", None), "elevated", "ask")
            return f"elevated: {cur}  │  opciones: {' | '.join(_ELEVATED_MODES)}"
        if args not in _ELEVATED_MODES:
            return f"⚠ Modo inválido. Usa: {' | '.join(_ELEVATED_MODES)}"
        loop.rt.elevated = args
        desc = {
            "off":  "solo lectura — bloquea tools 'ask'",
            "on":   "elevado — auto-aprueba 'ask', respeta 'deny'",
            "ask":  "normal — respeta configuración oocode.json",
            "full": "sin restricciones — aprueba todo incluso 'deny'",
        }[args]
        return f"✓  elevated → {args}  ({desc})"

    if cmd == "/new":
        _t = sess.get("thread")
        if _t and _t.is_alive():
            return "⚠  El agente está activo — usa /kill para detenerlo primero."
        try:
            loop.context.clear()
            sess["history"].clear()
        except Exception:
            pass
        return "✓  Nueva sesión iniciada — historial y contexto borrados"

    if cmd == "/compact":
        _t = sess.get("thread")
        if _t and _t.is_alive():
            return "⚠  El agente está activo — espera a que termine o usa /kill."
        try:
            loop.context.compact()
            ctx_pct = round(loop.context.token_estimate() / (loop.context.max_tokens or 1) * 100)
            return f"✓  Contexto compactado → {ctx_pct}%"
        except Exception as e:
            return f"⚠ Error compactando: {e}"

    return None  # no manejado → ir al LLM


# ── POST /api/chat/send ───────────────────────────────────────────────────────

@bp.route('/api/chat/send', methods=['POST'])
def api_chat_send():
    """Envía un mensaje al AgentLoop y lo procesa en background. Output vía SSE."""
    sid = _get_or_create_sid()
    data = request.get_json(silent=True) or {}
    message  = data.get("message", "").strip()
    agent_id = data.get("agent_id", "main") or "main"
    images   = data.get("images") or []   # list of file paths para visión

    if not message:
        return jsonify({"error": "Mensaje vacío"}), 400

    # Espera hasta 30s a que el loop se inicialice (solo si no está listo aún)
    sess = _get_or_create_session(sid, agent_id)
    loop = sess.get("loop")
    if loop is None:
        return jsonify({"error": "Agente no disponible — reintenta en unos segundos"}), 503

    with sess["lock"]:
        if sess.get("thread") and sess["thread"].is_alive():
            return jsonify({"error": "El agente está procesando otra petición"}), 409

    # Registrar en historial
    sess["history"].append({
        "role": "user", "text": message,
        "ts": time.time(), "id": os.urandom(4).hex(),
    })
    
    # Guardar SOLO el input del usuario en el historial compartido con el TUI
    # (~/.oocode/history, formato prompt_toolkit). La respuesta del agente NO se
    # escribe aquí — es conversación, no input del prompt.
    append_input_history(message)

    # Interceptar slash commands de estado (no van al LLM)
    if message.startswith('/'):
        slash_resp = _handle_webui_slash(message, sess)
        if slash_resp is not None:
            q = sess["queue"]
            q.put({"type": "thinking"})
            q.put({"type": "text", "text": slash_resp})
            sess["history"].append({
                "role": "assistant", "text": slash_resp,
                "ts": time.time(), "id": os.urandom(4).hex(),
            })
            q.put({"type": "done", "response": slash_resp})
            return jsonify({"ok": True, "sid": sid})

    # Lanzar en background
    _images = images if images else None

    def _run():
        try:
            sess["loop"].run_for_webui(message, images=_images)
        except Exception as exc:
            sess["loop"]._webui_emit({"type": "error", "error": str(exc)})

    t = threading.Thread(target=_run, daemon=True, name=f"webui-turn-{sid[:6]}")
    sess["thread"] = t
    t.start()

    return jsonify({"ok": True, "sid": sid})


# ── GET /api/chat/stream ─────────────────────────────────────────────────────

@bp.route('/api/chat/stream')
def api_chat_stream():
    """SSE stream de eventos del AgentLoop para este browser."""
    sid      = _get_or_create_sid()
    agent_id = request.args.get("agent_id", "main")

    # Devuelve la queue inmediatamente — el loop se inicializa en background.
    # Esto evita el bloqueo SSE de 5-10s que causaba reconexiones y pérdida del evento 'done'.
    q: queue.Queue = _ensure_session_entry(sid, agent_id)

    def gen():
        # ── Bug fix 2: Ghost generator — incrementar generación para matar el anterior
        with _SESSIONS_LOCK:
            entry = _WEBUI_SESSIONS.get(sid)
            if entry:
                entry["_gen"] = entry.get("_gen", 0) + 1
                my_gen = entry["_gen"]
            else:
                my_gen = 0

        # ── Bug fix 3: Envolver en try/except para nunca crashear y siempre enviar 'done'
        try:
            yield 'data: {"type":"connected"}\n\n'

            text_buf = []
            last_hb  = time.time()

            while True:
                # ── Bug fix 2: Ghost generator check — salir si hay un generador más nuevo
                with _SESSIONS_LOCK:
                    cur_gen = _WEBUI_SESSIONS.get(sid, {}).get("_gen", my_gen)
                if cur_gen > my_gen:
                    break

                try:
                    ev = q.get(timeout=2.0)
                    ev_type = ev.get("type", "text")

                    if ev_type == "text":
                        text_buf.append(ev.get("text", ""))
                        continue  # acumular texto antes de enviar

                    if ev_type == "stream_chunk":
                        # Chunks de streaming de Ollama: enviar inmediatamente sin acumular
                        if text_buf:
                            combined = "\n".join(text_buf).strip()
                            text_buf.clear()
                            if combined:
                                yield f"data: {json.dumps({'type': 'text', 'text': combined})}\n\n"
                        yield f"data: {json.dumps(ev)}\n\n"
                        continue

                    # Flush text buffer antes de evento estructurado
                    if text_buf:
                        combined = "\n".join(text_buf).strip()
                        text_buf.clear()
                        if combined:
                            yield f"data: {json.dumps({'type': 'text', 'text': combined})}\n\n"

                    if ev_type == "done":
                        # ── Bug fix 1: NameError sess — guardar historial ANTES de yield
                        # para que el cliente pueda consultar /api/chat/history
                        # inmediatamente tras recibir el evento done.
                        resp = ev.get("response", "")
                        if resp:
                            with _SESSIONS_LOCK:
                                _sess = _WEBUI_SESSIONS.get(sid)
                            if _sess:
                                _sess["history"].append({
                                    "role": "assistant", "text": resp,
                                    "ts": time.time(), "id": os.urandom(4).hex(),
                                })

                    yield f"data: {json.dumps(ev)}\n\n"

                except queue.Empty:
                    now = time.time()
                    # Flush pending text
                    if text_buf:
                        combined = "\n".join(text_buf).strip()
                        text_buf.clear()
                        if combined:
                            yield f"data: {json.dumps({'type': 'text', 'text': combined})}\n\n"
                    # Heartbeat cada 15s
                    if now - last_hb > 15:
                        last_hb = now
                        yield 'data: {"type":"heartbeat"}\n\n'

                except Exception:
                    pass  # nunca crashear el generador

        except Exception:
            # Último recurso: enviar done para que el browser reactive el botón de enviar
            try:
                yield 'data: {"type":"done","response":""}\n\n'
            except Exception:
                pass

    return Response(
        gen(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )


# ── GET /api/chat/history ─────────────────────────────────────────────────────

@bp.route('/api/chat/history')
def api_chat_history():
    """Devuelve el historial de conversación del servidor para este navegador."""
    sid      = _get_or_create_sid()
    agent_id = request.args.get("agent_id", "main")
    sess     = _get_or_create_session(sid, agent_id)
    return jsonify({"history": sess["history"], "sid": sid})


# ── GET /api/chat/input_history ───────────────────────────────────────────────

@bp.route('/api/chat/input_history')
def api_chat_input_history():
    """Historial de input del prompt (flecha arriba), COMPARTIDO con el TUI.

    Lee ~/.oocode/history en formato prompt_toolkit, así el recall del WebUI muestra
    las mismas indicaciones que el TUI (y sobrevive a recargas de página).
    """
    try:
        limit = int(request.args.get("limit", 200))
    except (TypeError, ValueError):
        limit = 200
    return jsonify({"history": load_input_history(limit)})


# ── POST /api/chat/load_session ───────────────────────────────────────────────

@bp.route('/api/chat/load_session', methods=['POST'])
def api_chat_load_session():
    """Restaura una sesión pasada (panel 📚 Sesiones): contexto + conversación mostrada."""
    sid      = _get_or_create_sid()
    data     = request.get_json(silent=True) or {}
    agent_id = data.get("agent_id", "main") or "main"
    session_id = (data.get("session_id") or "").strip()
    if not session_id:
        return jsonify({"error": "session_id requerido"}), 400
    sess = _get_or_create_session(sid, agent_id)
    loop = sess.get("loop")
    if loop is None:
        return jsonify({"error": "Agente no disponible — reintenta en unos segundos"}), 503
    with sess["lock"]:
        if sess.get("thread") and sess["thread"].is_alive():
            return jsonify({"error": "El agente está procesando otra petición"}), 409
    count, err = _restore_webui_session(loop, sess, session_id)
    if err:
        return jsonify({"error": err}), 404
    return jsonify({"ok": True, "count": count, "history": sess["history"], "sid": sid})


# ── GET /api/chat/status ──────────────────────────────────────────────────────

@bp.route('/api/chat/status')
def api_chat_status():
    """Devuelve el estado actual del AgentLoop (agente, modelo, contexto, tareas)."""
    sid = _get_or_create_sid()
    if sid not in _WEBUI_SESSIONS:
        return jsonify({"connected": False})
    sess = _WEBUI_SESSIONS[sid]
    loop = sess.get("loop")
    if not loop:
        return jsonify({"connected": False})
    cfg          = loop.config
    ctx_tokens   = loop.context.token_estimate()
    ctx_max      = loop.context.max_tokens or 1
    compact_thr  = loop.context.compact_threshold
    ctx_pct      = min(round(ctx_tokens / ctx_max * 100), 100)
    thresh_pct   = int(compact_thr * 100)
    _compacting  = getattr(loop, "_compacting_ctx", None)
    if _compacting and (hasattr(_compacting, "is_set") and _compacting.is_set()):
        compact_hint = "↻ compactando"
    elif ctx_pct >= thresh_pct:
        compact_hint = "↻ compactando"
    elif ctx_pct >= thresh_pct - 10:
        compact_hint = "↻ cerca compactación"
    else:
        compact_hint = ""

    # Feature indicators
    hooks_blt = getattr(cfg, "hooks_builtins", {})
    lsp_on  = hooks_blt.get("lsp_after_write", False) if isinstance(hooks_blt, dict) else False
    mem_on  = getattr(cfg, "memory_embed_enabled", False)
    rag_on  = getattr(cfg, "rag_enabled", False)
    elevated = getattr(getattr(loop, "rt", None), "elevated", "ask")

    # MCP: obtener nombres de servidores en ejecución
    mcp_pool = getattr(loop, "_mcp_pool", None)
    mcp_server_names: list[str] = []
    if mcp_pool is not None:
        try:
            mcp_server_names = [
                name for name, c in mcp_pool._clients.items() if c.is_alive
            ]
        except Exception:
            pass
    mcp_count = len(mcp_server_names) or len(getattr(cfg, "mcp_servers", []))

    # LSP: detectar language servers instalados
    lsp_installed: list[str] = []
    try:
        from agent.lsp_client import _SERVER_CMDS, _which, _EXT_TO_LANG
        seen_srv: set[str] = set()
        for ext, cmd in _SERVER_CMDS.items():
            srv = cmd[0]
            if srv not in seen_srv and _which(srv):
                seen_srv.add(srv)
                lang = _EXT_TO_LANG.get(ext, ext.lstrip("."))
                if lang not in lsp_installed:
                    lsp_installed.append(lang)
    except Exception:
        pass

    # Vision: comprobar si el modelo activo soporta imágenes
    vision_on = False
    try:
        vision_on = bool(loop._model_supports_images())
    except Exception:
        pass

    return jsonify({
        "connected":        True,
        "agent_emoji":      getattr(cfg, "agent_emoji", "🤖"),
        "agent_name":       getattr(cfg, "agent_name",  "OOCode"),
        "agent_id":         getattr(cfg, "agent_id",    "main"),
        "model":            getattr(cfg, "model",        "—"),
        "context_tokens":   ctx_tokens,
        "context_max":      ctx_max,
        "context_pct":      ctx_pct,
        "compact_hint":     compact_hint,
        "compact_threshold_pct": thresh_pct,
        "task_total":       len(getattr(loop, "_plan_tasks", [])),
        "task_done":        sum(1 for t in getattr(loop, "_plan_tasks", []) if t.get("status") == "done"),
        "busy":             bool(sess.get("thread") and sess["thread"].is_alive()),
        "mcp_count":        mcp_count,
        "mcp_server_names": mcp_server_names,
        "lsp_on":           lsp_on,
        "lsp_installed":    lsp_installed,
        "memory_on":        mem_on,
        "rag_on":           rag_on,
        "elevated":         elevated,
        "vision_on":        vision_on,
    })


# ── POST /api/chat/clear ──────────────────────────────────────────────────────

@bp.route('/api/chat/clear', methods=['POST'])
def api_chat_clear():
    """Reinicia la conversación: borra historial y contexto del agente."""
    sid = _get_or_create_sid()
    if sid in _WEBUI_SESSIONS:
        with _SESSIONS_LOCK:
            old = _WEBUI_SESSIONS.pop(sid, None)
            if old:
                try:
                    old["loop"].close()
                except Exception:
                    pass
    return jsonify({"ok": True})


# ── POST /api/chat/kill ───────────────────────────────────────────────────────

@bp.route('/api/chat/kill', methods=['POST'])
def api_chat_kill():
    """Interrumpe el turno activo del AgentLoop — equivale a `/kill all` en TUI.

    Pone _kill_requested=True, aborta la llamada LLM en curso, mata todos los
    subagentes/equipos, y además deshabilita los jobs activos del scheduler y resetea
    las tareas wip→todo (paridad con `/kill all`).
    """
    sid = _get_or_create_sid()
    if sid not in _WEBUI_SESSIONS:
        return jsonify({"ok": False, "error": "Sin sesión activa"}), 404
    sess = _WEBUI_SESSIONS[sid]
    loop = sess.get("loop")
    if not loop:
        return jsonify({"ok": False, "error": "Loop no disponible"}), 503

    # request_kill: marca _kill_requested, aborta la llamada LLM en curso cerrando a
    # la fuerza el socket (también el de los subagentes, que comparten el pool del
    # padre) y mata todos los subagentes/equipos activos vía kill_all(). Antes solo
    # ponía el flag + kill_event, sin abortar el LLM en vuelo (seguía generando).
    summary = {"subagents": 0}
    extras  = {"jobs": 0, "wip": 0}
    try:
        summary = loop.request_kill()
    except Exception:
        # Fallback defensivo si request_kill no estuviera disponible
        loop._kill_requested = True
        try:
            from agent.subagent import list_running
            for sub in list_running():
                if sub.status == "running":
                    sub.kill_event.set()
                    sub.status = "killed"
        except Exception:
            pass

    # Extras de /kill all: deshabilitar jobs del scheduler + resetear tareas wip→todo
    # (mismo helper que usa el comando /kill all del TUI).
    try:
        extras = loop.kill_all_extras()
    except Exception:
        pass

    # Emitir evento "done" para que el browser reactive el input
    try:
        sess["queue"].put_nowait({"type": "done", "response": ""})
    except Exception:
        pass

    return jsonify({
        "ok": True,
        "subagents": summary.get("subagents", 0),
        "jobs": extras.get("jobs", 0),
        "wip": extras.get("wip", 0),
    })


# ── POST /api/chat/elevated ──────────────────────────────────────────────────

_ELEVATED_CYCLE = ("ask", "off", "on", "full")
_ELEVATED_DESC  = {
    "ask":  "normal — respeta permisos de oocode.json",
    "off":  "solo lectura — bloquea operaciones peligrosas",
    "on":   "elevado — auto-aprueba 'ask', respeta 'deny'",
    "full": "sin restricciones — aprueba todo incluso 'deny'",
}

@bp.route('/api/chat/elevated', methods=['POST'])
def api_chat_elevated():
    """Establece o cicla el modo elevated del agente activo."""
    sid = _get_or_create_sid()
    if sid not in _WEBUI_SESSIONS:
        return jsonify({"ok": False, "error": "Sin sesión activa"}), 404
    sess = _WEBUI_SESSIONS[sid]
    loop = sess.get("loop")
    if not loop:
        return jsonify({"ok": False, "error": "Loop no disponible"}), 503
    rt = getattr(loop, "rt", None)
    if rt is None:
        return jsonify({"ok": False, "error": "Runtime no disponible"}), 503

    data = request.get_json(silent=True) or {}
    mode = (data.get("mode") or "").strip()

    if mode in _ELEVATED_CYCLE:
        rt.elevated = mode
    else:
        cur = getattr(rt, "elevated", "ask")
        idx = _ELEVATED_CYCLE.index(cur) if cur in _ELEVATED_CYCLE else 0
        rt.elevated = _ELEVATED_CYCLE[(idx + 1) % len(_ELEVATED_CYCLE)]

    # Notificar al WebUI para que actualice el badge
    try:
        sess["queue"].put_nowait({"type": "status", "elevated": rt.elevated})
    except Exception:
        pass

    return jsonify({"ok": True, "elevated": rt.elevated, "desc": _ELEVATED_DESC.get(rt.elevated, "")})


# ── POST /api/chat/send_sync ──────────────────────────────────────────────────

@bp.route('/api/chat/send_sync', methods=['POST'])
def api_chat_send_sync():
    """Envía un mensaje y ESPERA hasta que el AgentLoop termine. Útil para clientes CLI/vim.

    Bloquea hasta 120 segundos. Devuelve {"ok": true, "response": "<texto>", "agent_id": ...}.
    """
    sid = _get_or_create_sid()
    data = request.get_json(silent=True) or {}
    message  = data.get("message", "").strip()
    agent_id = data.get("agent_id", "main") or "main"
    timeout  = min(float(data.get("timeout", 120)), 300)

    if not message:
        return jsonify({"error": "Mensaje vacío"}), 400

    sess = _get_or_create_session(sid, agent_id)

    with sess["lock"]:
        if sess.get("thread") and sess["thread"].is_alive():
            return jsonify({"error": "El agente está procesando otra petición"}), 409

    sess["history"].append({
        "role": "user", "text": message,
        "ts": time.time(), "id": os.urandom(4).hex(),
    })
    # Input del usuario al historial compartido con el TUI (mismo helper/formato)
    append_input_history(message)

    # Interceptar slash commands de estado
    if message.startswith('/'):
        slash_resp = _handle_webui_slash(message, sess)
        if slash_resp is not None:
            sess["history"].append({
                "role": "assistant", "text": slash_resp,
                "ts": time.time(), "id": os.urandom(4).hex(),
            })
            return jsonify({
                "ok": True, "response": slash_resp, "agent_id": agent_id,
                "timeout": False, "sid": sid, "tool_events": [],
            })

    done_evt = threading.Event()

    def _run():
        try:
            sess["loop"].run_for_webui(message)
        except Exception as exc:
            sess["loop"]._webui_emit({"type": "error", "error": str(exc)})
        finally:
            done_evt.set()

    t = threading.Thread(target=_run, daemon=True, name=f"webui-sync-{sid[:6]}")
    sess["thread"] = t
    t.start()

    done_evt.wait(timeout=timeout)

    # Extraer último mensaje del asistente del historial
    response_text = ""
    for msg in reversed(sess["history"]):
        if msg.get("role") == "assistant":
            response_text = msg.get("text", "")
            break

    still_busy = t.is_alive()

    # Drenar la cola de eventos para recoger tool_start/tool_done (uso de VIM/CLI)
    tool_events: list = []
    q_ref: queue.Queue = sess["queue"]
    try:
        while True:
            ev = q_ref.get_nowait()
            if ev.get("type") in ("tool_start", "tool_done"):
                tool_events.append(ev)
    except queue.Empty:
        pass

    return jsonify({
        "ok":          True,
        "response":    response_text,
        "agent_id":    agent_id,
        "timeout":     still_busy,
        "sid":         sid,
        "tool_events": tool_events,
    })
