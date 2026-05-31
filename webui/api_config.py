"""Blueprint /api/config*, /api/sessions, /api/status, /theme/set."""
from flask import Blueprint, Response, jsonify, request

from webui.helpers import (
    CONFIG_FILE, STATE_FILE,
    _load_ooconfig, load_state, save_state,
)

bp = Blueprint("api_config", __name__)


# ── GET /api/config ───────────────────────────────────────────────────────────

@bp.route('/api/config', methods=['GET'])
def api_config_get():
    cfg = _load_ooconfig()
    if cfg is None:
        return jsonify({"error": "No se pudo cargar OOConfig"}), 500
    return jsonify({
        "ollama_host":              cfg.ollama_host,
        "model":                    cfg.model or "",
        "webui_enabled":            cfg.webui_enabled,
        "webui_host":               cfg.webui_host,
        "webui_port":               cfg.webui_port,
        "webui_log_file":           cfg.webui_log_file,
        "auto_continue_max":        cfg.auto_continue_max,
        "compact_threshold":        cfg.compact_threshold,
        "max_summary_chars":        cfg.max_summary_chars,
        "rag_enabled":              cfg.rag_enabled,
        "rag_top_k":                cfg.rag_top_k,
        "rag_similarity_threshold": cfg.rag_similarity_threshold,
        "rag_index_interval":       cfg.rag_index_interval,
        "searxng_enabled":          cfg.searxng_enabled,
        "searxng_url":              cfg.searxng_url,
        "searxng_max_results":      cfg.searxng_max_results,
        "hooks_enabled":            cfg.hooks_enabled,
        "hooks_builtins":           cfg.hooks_builtins,
        "subagents_max_concurrent": cfg.subagents_max_concurrent,
        "subagents_max_teams":      cfg.subagents_max_teams,
        "subagents_max_team_size":  cfg.subagents_max_team_size,
        "subagents_recent_ttl":     cfg.subagents_recent_ttl,
        "backup_enabled":           cfg.backup_enabled,
        "backup_dir":               cfg.backup_dir,
        "backup_max_files":         cfg.backup_max_files,
        "log_enabled":              cfg.log_enabled,
        "log_level":                cfg.log_level,
        "accent_color":             cfg.accent_color,
        "snapshots_enabled":        cfg.snapshots_enabled,
        "snapshots_max":            cfg.snapshots_max,
        "embed_model":              cfg.embed_model,
        "vision_enabled":           cfg.vision_enabled,
        "chatlog_enabled":          cfg.chatlog_enabled,
        "fallback_enabled":         cfg.fallback_enabled,
        "fallback_model":           cfg.fallback_model,
    })


# ── POST /api/config/save ─────────────────────────────────────────────────────

@bp.route('/api/config/save', methods=['POST'])
def api_config_save():
    cfg = _load_ooconfig()
    if cfg is None:
        return jsonify({"error": "No se pudo cargar OOConfig"}), 500

    data: dict = request.get_json(silent=True) or {}

    _str  = lambda k, a: setattr(cfg, a, str(data[k]).strip()) if k in data else None
    _int  = lambda k, a: setattr(cfg, a, int(data[k])) if k in data else None
    _flt  = lambda k, a: setattr(cfg, a, float(data[k])) if k in data else None
    _bool = lambda k, a: setattr(cfg, a, bool(data[k])) if k in data else None

    _str("ollama_host",              "ollama_host")
    _str("model",                    "model")
    _str("webui_host",               "webui_host")
    _int("webui_port",               "webui_port")
    _bool("webui_enabled",           "webui_enabled")
    _str("webui_log_file",           "webui_log_file")
    _int("auto_continue_max",        "auto_continue_max")
    _flt("compact_threshold",        "compact_threshold")
    _int("max_summary_chars",        "max_summary_chars")
    _bool("rag_enabled",             "rag_enabled")
    _int("rag_top_k",                "rag_top_k")
    _flt("rag_similarity_threshold", "rag_similarity_threshold")
    _flt("rag_index_interval",       "rag_index_interval")
    _bool("searxng_enabled",         "searxng_enabled")
    _str("searxng_url",              "searxng_url")
    _int("searxng_max_results",      "searxng_max_results")
    _bool("hooks_enabled",           "hooks_enabled")
    _int("subagents_max_concurrent", "subagents_max_concurrent")
    _int("subagents_max_teams",      "subagents_max_teams")
    _int("subagents_max_team_size",  "subagents_max_team_size")
    _int("subagents_recent_ttl",     "subagents_recent_ttl")
    _bool("backup_enabled",          "backup_enabled")
    _str("backup_dir",               "backup_dir")
    _int("backup_max_files",         "backup_max_files")
    _bool("log_enabled",             "log_enabled")
    _str("log_level",                "log_level")
    _str("accent_color",             "accent_color")
    _bool("snapshots_enabled",       "snapshots_enabled")
    _int("snapshots_max",            "snapshots_max")
    _str("embed_model",              "embed_model")
    _bool("vision_enabled",          "vision_enabled")
    _bool("chatlog_enabled",         "chatlog_enabled")
    _bool("fallback_enabled",        "fallback_enabled")
    _str("fallback_model",           "fallback_model")

    if "hooks_builtins" in data and isinstance(data["hooks_builtins"], list):
        cfg.hooks_builtins = data["hooks_builtins"]

    try:
        cfg.save()
        return jsonify({"ok": True, "message": "Configuración guardada en oocode.json"})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── GET /api/config/raw ───────────────────────────────────────────────────────

@bp.route('/api/config/raw')
def api_config_raw():
    try:
        return Response(CONFIG_FILE.read_text(encoding="utf-8"),
                        mimetype="application/json")
    except Exception:
        return Response("{}", mimetype="application/json")


# ── GET /api/sessions ─────────────────────────────────────────────────────────

@bp.route('/api/sessions')
def api_sessions():
    cfg = _load_ooconfig()
    agent_id = (cfg.agent_id if cfg else "main") or "main"
    try:
        from agent.session import SessionManager
        sm = SessionManager(agent_id)
        sessions = sm.list_sessions(limit=30)
        return jsonify({"sessions": sessions, "agent_id": agent_id})
    except Exception as exc:
        return jsonify({"sessions": [], "error": str(exc)})


# ── GET /api/status ───────────────────────────────────────────────────────────

@bp.route('/api/status')
def api_status():
    cfg = _load_ooconfig()
    if cfg is None:
        return jsonify({"error": "config unavailable"}), 500
    return jsonify({
        "agent_id":      cfg.agent_id,
        "agent_name":    cfg.agent_name,
        "agent_emoji":   cfg.agent_emoji,
        "model":         cfg.model or "—",
        "workspace":     cfg.workspace,
        "ollama_host":   cfg.ollama_host,
        "webui_port":    cfg.webui_port,
        "hooks_count":   len(cfg.hooks_builtins),
        "plugins_count": len(cfg.plugins_enabled),
        "rag_enabled":   cfg.rag_enabled,
    })


# ── POST /theme/set ───────────────────────────────────────────────────────────

@bp.route('/theme/set', methods=['POST'])
def theme_set():
    data  = request.get_json(silent=True) or {}
    theme = data.get('theme', 'dark')
    st    = load_state()
    st['theme'] = theme
    save_state(st)
    return jsonify({'ok': True, 'theme': theme})
