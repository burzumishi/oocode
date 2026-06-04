"""Blueprint /api/agents/* — subagentes en tiempo real."""
import json
import time

from flask import Blueprint, Response, jsonify, request

bp = Blueprint("api_agents", __name__)


def _sub_to_dict(s, full: bool = False) -> dict:
    preview_len = None if full else 600
    result = s.result or ""
    return {
        "run_id":        s.run_id,
        "short_id":      s.run_id[:6],
        "agent_id":      s.agent_id,
        "agent_name":    s.agent_name,
        "agent_emoji":   s.agent_emoji,
        "task":          s.task,
        "status":        s.status,
        "elapsed":       round(s.elapsed(), 1),
        "steer_count":   s.steer_count,
        "priority":      s.priority,
        "finished_ago":  round(time.time() - s.finished_at) if s.finished_at else None,
        "result_preview": result[:preview_len] if preview_len else result,
        "result_truncated": len(result) > 600 and not full,
        "error":         s.error,
    }


@bp.route('/api/agents')
def api_agents():
    try:
        from agent.subagent import list_running, list_recent
        return jsonify({
            "running": [_sub_to_dict(s) for s in list_running()],
            "recent":  [_sub_to_dict(s) for s in list_recent()],
            "ts":      time.time(),
        })
    except Exception as exc:
        return jsonify({"running": [], "recent": [], "ts": time.time(), "error": str(exc)})


@bp.route('/api/agents/<run_id>/output')
def api_agent_output(run_id: str):
    """Devuelve la tarea y resultado completo de un subagente por run_id (prefix match)."""
    try:
        from agent.subagent import get_by_prefix
        sub = get_by_prefix(run_id)
        if sub is None:
            # Buscar también en recientes
            import agent.subagent as _sa
            with _sa._registry_lock:
                sub = _sa._registry.get(run_id)
        if sub is None:
            return jsonify({"error": "Subagente no encontrado"}), 404
        return jsonify({
            **_sub_to_dict(sub, full=True),
            "result": sub.result or "",
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.route('/api/agents/kill/<run_id>', methods=['POST'])
def api_agents_kill(run_id: str):
    try:
        from agent.subagent import get_by_prefix
        sub = get_by_prefix(run_id)
        if sub is None or sub.status != "running":
            return jsonify({"ok": False, "error": "Subagente no encontrado"}), 404
        sub.kill_event.set()
        sub.status = "killed"
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route('/api/agents/steer/<run_id>', methods=['POST'])
def api_agents_steer(run_id: str):
    data = request.get_json(silent=True) or {}
    instruction = data.get("instruction", "").strip()
    if not instruction:
        return jsonify({"ok": False, "error": "Instrucción requerida"}), 400
    try:
        from agent.subagent import get_by_prefix
        sub = get_by_prefix(run_id)
        if sub is None or sub.status != "running":
            return jsonify({"ok": False, "error": "Subagente no encontrado"}), 404
        sub.steer_queue.put(instruction)
        sub.steer_count += 1
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route('/api/agents/spawn', methods=['POST'])
def api_agents_spawn():
    data     = request.get_json(silent=True) or {}
    agent_id = data.get("agent_id", "").strip()
    task     = data.get("task", "").strip()
    if not agent_id or not task:
        return jsonify({"ok": False, "error": "agent_id y task son requeridos"}), 400
    try:
        from config import OOConfig
        from tools.permissions import PermissionManager
        from agent.subagent import SubAgentRunner
        from oocode import build_registry

        cfg    = OOConfig.load()
        perms  = PermissionManager(cfg.permissions)
        perms._non_interactive = True
        runner = SubAgentRunner(cfg, perms, build_registry)
        sub    = runner.spawn_background(agent_id, task)
        return jsonify({"ok": True, "run_id": sub.run_id, "agent_id": agent_id})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route('/api/agents/stream')
def api_agents_stream():
    def gen():
        while True:
            try:
                from agent.subagent import list_running, list_recent
                data = json.dumps({
                    "running": [_sub_to_dict(s) for s in list_running()],
                    "recent":  [_sub_to_dict(s) for s in list_recent()],
                })
            except Exception:
                data = json.dumps({"running": [], "recent": []})
            yield f"data: {data}\n\n"
            time.sleep(2)
    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
