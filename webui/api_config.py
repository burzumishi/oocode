"""Blueprint /api/config*, /api/sessions, /api/status, /theme/set."""
from flask import Blueprint, Response, jsonify, request

from webui.helpers import (
    CONFIG_FILE,
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
        # Backend (bloque "api" unificado)
        "api_type":                 cfg.api_type,
        "api_key":                  cfg.api_key,
        # host alimenta tanto ollama_host (backend Ollama) como api_base_url (OpenAI baseUrl)
        "ollama_host":              cfg.ollama_host,
        "ollama_extra_hosts":       ", ".join(cfg.ollama_extra_hosts or []),
        "ollama_embed_host":        cfg.ollama_embed_host,
        "ollama_subagent_routing":  cfg.ollama_subagent_routing,
        "ollama_retry_count":       cfg.ollama_retry_count,
        "ollama_retry_delay":       cfg.ollama_retry_delay,
        # Modelo activo
        "model":                    cfg.model or "",
        # Modelo global
        "model_system_overhead":    cfg.model_system_overhead,
        "model_repeat_penalty":     cfg.model_repeat_penalty,
        "model_seed":               cfg.model_seed,
        # WebUI
        "webui_enabled":            cfg.webui_enabled,
        "webui_host":               cfg.webui_host,
        "webui_port":               cfg.webui_port,
        "webui_log_file":           cfg.webui_log_file,
        "webui_log_max_size":       cfg.webui_log_max_size,
        # Contexto
        "auto_continue_max":        cfg.auto_continue_max,
        "compact_threshold":        cfg.compact_threshold,
        "compact_min_keep":         cfg.compact_min_keep,
        "max_summary_chars":        cfg.max_summary_chars,
        "max_tool_result_tokens":   cfg.max_tool_result_tokens,
        # Herramientas
        "read_file_lines_default":  cfg.read_file_lines_default,
        "read_file_lines_warn_large": cfg.read_file_lines_warn_large,
        "web_fetch_max_chars":      cfg.web_fetch_max_chars,
        "web_fetch_timeout":        cfg.web_fetch_timeout,
        "web_search_max_results":   cfg.web_search_max_results,
        "bash_max_output_chars":    cfg.bash_max_output_chars,
        "code_search_max_results":  cfg.code_search_max_results,
        "code_search_context_lines": cfg.code_search_context_lines,
        "code_search_max_filesize": cfg.code_search_max_filesize,
        "tool_cache_enabled":       cfg.tool_cache_enabled,
        "tool_cache_max_size":      cfg.tool_cache_max_size,
        # RAG
        "rag_enabled":              cfg.rag_enabled,
        "rag_top_k":                cfg.rag_top_k,
        "rag_top_k_complex":        cfg.rag_top_k_complex,
        "rag_similarity_threshold": cfg.rag_similarity_threshold,
        "rag_threshold_complex":    cfg.rag_threshold_complex,
        "rag_max_snippet_chars":    cfg.rag_max_snippet_chars,
        "rag_index_interval":       cfg.rag_index_interval,
        # Embeddings
        "embed_model":              cfg.embed_model,
        "embed_top_k":              cfg.embed_top_k,
        "embed_similarity_threshold": cfg.embed_similarity_threshold,
        "embed_max_input_chars":    cfg.embed_max_input_chars,
        "embed_snippet_chars":      cfg.embed_snippet_chars,
        "embed_disk_cache_enabled": cfg.embed_disk_cache_enabled,
        "embed_disk_cache_dir":     cfg.embed_disk_cache_dir,
        "embed_disk_cache_max":     cfg.embed_disk_cache_max,
        # SearXNG
        "searxng_enabled":          cfg.searxng_enabled,
        "searxng_url":              cfg.searxng_url,
        "searxng_max_results":      cfg.searxng_max_results,
        "searxng_categories":       cfg.searxng_categories,
        "searxng_language":         cfg.searxng_language,
        "searxng_safe_search":      cfg.searxng_safe_search,
        "searxng_timeout":          cfg.searxng_timeout,
        # MCP
        "mcp_request_timeout":              cfg.mcp_request_timeout,
        "mcp_oocode_assistant_enabled":     cfg.mcp_oocode_assistant_enabled,
        "mcp_system_assistant_enabled":     cfg.mcp_system_assistant_enabled,
        "mcp_devops_assistant_enabled":     cfg.mcp_devops_assistant_enabled,
        "mcp_database_assistant_enabled":   cfg.mcp_database_assistant_enabled,
        "mcp_home_office_assistant_enabled": cfg.mcp_home_office_assistant_enabled,
        "mcp_security_assistant_enabled":   cfg.mcp_security_assistant_enabled,
        "mcp_iot_assistant_enabled":        cfg.mcp_iot_assistant_enabled,
        "mcp_http_client_assistant_enabled": cfg.mcp_http_client_assistant_enabled,
        # Hooks
        "hooks_enabled":            cfg.hooks_enabled,
        "hooks_builtins":           cfg.hooks_builtins,
        # Subagentes
        "subagents_max_concurrent": cfg.subagents_max_concurrent,
        "subagents_max_teams":      cfg.subagents_max_teams,
        "subagents_max_team_size":  cfg.subagents_max_team_size,
        "subagents_recent_ttl":     cfg.subagents_recent_ttl,
        "subagents_default_priority": cfg.subagents_default_priority,
        "subagents_auto_cont_max":    cfg.subagents_auto_cont_max,
        "subagents_inference_timeout": cfg.subagents_inference_timeout,
        "subagents_default_timeout":  cfg.subagents_default_timeout,
        # Backups
        "backup_enabled":           cfg.backup_enabled,
        "backup_dir":               cfg.backup_dir,
        "backup_max_files":         cfg.backup_max_files,
        # Snapshots
        "snapshots_enabled":        cfg.snapshots_enabled,
        "snapshots_max":            cfg.snapshots_max,
        "snapshots_save_on_compact": cfg.snapshots_save_on_compact,
        # Logging
        "log_enabled":              cfg.log_enabled,
        "log_level":                cfg.log_level,
        "log_file":                 cfg.log_file,
        "log_max_size":             cfg.log_max_size,
        "log_max_files":            cfg.log_max_files,
        # Vision
        "vision_enabled":           cfg.vision_enabled,
        "vision_show_indicator":    cfg.vision_show_indicator,
        # Chat log
        "chatlog_enabled":          cfg.chatlog_enabled,
        "chatlog_path":             cfg.chatlog_path,
        "chatlog_max_size_mb":      cfg.chatlog_max_size_mb,
        # Fallback
        "fallback_enabled":         cfg.fallback_enabled,
        "fallback_model":           cfg.fallback_model,
        # Apariencia
        "accent_color":             cfg.accent_color,
    })


# ── POST /api/config/save ─────────────────────────────────────────────────────

@bp.route('/api/config/save', methods=['POST'])
def api_config_save():
    cfg = _load_ooconfig()
    if cfg is None:
        return jsonify({"error": "No se pudo cargar OOConfig"}), 500

    data: dict = request.get_json(silent=True) or {}

    def _str(k, a):
        if k in data:
            setattr(cfg, a, str(data[k]).strip())

    def _int(k, a):
        if k in data:
            setattr(cfg, a, int(data[k]))

    def _flt(k, a):
        if k in data:
            setattr(cfg, a, float(data[k]))

    def _bool(k, a):
        if k in data:
            setattr(cfg, a, bool(data[k]))

    def _opt_flt(k, a):
        if k not in data:
            return
        v = data[k]
        setattr(cfg, a, float(v) if v not in (None, "", "null") else None)

    def _opt_int(k, a):
        if k not in data:
            return
        v = data[k]
        setattr(cfg, a, int(v) if v not in (None, "", "null") else None)

    def _csv(k, a):
        """Lista separada por comas → list[str] sin vacíos."""
        if k not in data:
            return
        v = data[k]
        if isinstance(v, list):
            items = v
        else:
            items = str(v or "").split(",")
        setattr(cfg, a, [h.strip() for h in items if h and h.strip()])

    # Backend (bloque "api" unificado)
    _str("api_type",                "api_type")
    _str("api_key",                 "api_key")
    # host alimenta ollama_host (Ollama) y api_base_url (OpenAI baseUrl)
    _str("ollama_host",             "ollama_host")
    if "ollama_host" in data:
        cfg.api_base_url = str(data["ollama_host"]).strip()
    _csv("ollama_extra_hosts",      "ollama_extra_hosts")
    _str("ollama_embed_host",       "ollama_embed_host")
    _str("ollama_subagent_routing", "ollama_subagent_routing")
    _int("ollama_retry_count",      "ollama_retry_count")
    _flt("ollama_retry_delay",      "ollama_retry_delay")
    # Modelo
    _str("model",                   "model")
    # Modelo global
    _int("model_system_overhead",   "model_system_overhead")
    _opt_flt("model_repeat_penalty", "model_repeat_penalty")
    _opt_int("model_seed",           "model_seed")
    # WebUI
    _bool("webui_enabled",          "webui_enabled")
    _str("webui_host",              "webui_host")
    _int("webui_port",              "webui_port")
    _str("webui_log_file",          "webui_log_file")
    _int("webui_log_max_size",      "webui_log_max_size")
    # Contexto
    _int("auto_continue_max",       "auto_continue_max")
    _flt("compact_threshold",       "compact_threshold")
    _int("compact_min_keep",        "compact_min_keep")
    _int("max_summary_chars",       "max_summary_chars")
    _int("max_tool_result_tokens",  "max_tool_result_tokens")
    # Herramientas
    _int("read_file_lines_default",   "read_file_lines_default")
    _int("read_file_lines_warn_large", "read_file_lines_warn_large")
    _int("web_fetch_max_chars",       "web_fetch_max_chars")
    _int("web_fetch_timeout",         "web_fetch_timeout")
    _int("web_search_max_results",    "web_search_max_results")
    _int("bash_max_output_chars",     "bash_max_output_chars")
    _int("code_search_max_results",   "code_search_max_results")
    _int("code_search_context_lines", "code_search_context_lines")
    _str("code_search_max_filesize",  "code_search_max_filesize")
    _bool("tool_cache_enabled",       "tool_cache_enabled")
    _int("tool_cache_max_size",       "tool_cache_max_size")
    # RAG
    _bool("rag_enabled",             "rag_enabled")
    _int("rag_top_k",                "rag_top_k")
    _int("rag_top_k_complex",        "rag_top_k_complex")
    _flt("rag_similarity_threshold", "rag_similarity_threshold")
    _flt("rag_threshold_complex",    "rag_threshold_complex")
    _int("rag_max_snippet_chars",    "rag_max_snippet_chars")
    _flt("rag_index_interval",       "rag_index_interval")
    # Embeddings
    _str("embed_model",              "embed_model")
    _int("embed_top_k",              "embed_top_k")
    _flt("embed_similarity_threshold", "embed_similarity_threshold")
    _int("embed_max_input_chars",    "embed_max_input_chars")
    _int("embed_snippet_chars",      "embed_snippet_chars")
    _bool("embed_disk_cache_enabled", "embed_disk_cache_enabled")
    _str("embed_disk_cache_dir",     "embed_disk_cache_dir")
    _int("embed_disk_cache_max",     "embed_disk_cache_max")
    # SearXNG
    _bool("searxng_enabled",         "searxng_enabled")
    _str("searxng_url",              "searxng_url")
    _int("searxng_max_results",      "searxng_max_results")
    _str("searxng_categories",       "searxng_categories")
    _str("searxng_language",         "searxng_language")
    _int("searxng_safe_search",      "searxng_safe_search")
    _int("searxng_timeout",          "searxng_timeout")
    # MCP
    _flt("mcp_request_timeout",               "mcp_request_timeout")
    _bool("mcp_oocode_assistant_enabled",     "mcp_oocode_assistant_enabled")
    _bool("mcp_system_assistant_enabled",     "mcp_system_assistant_enabled")
    _bool("mcp_devops_assistant_enabled",     "mcp_devops_assistant_enabled")
    _bool("mcp_database_assistant_enabled",   "mcp_database_assistant_enabled")
    _bool("mcp_home_office_assistant_enabled", "mcp_home_office_assistant_enabled")
    _bool("mcp_security_assistant_enabled",   "mcp_security_assistant_enabled")
    _bool("mcp_iot_assistant_enabled",        "mcp_iot_assistant_enabled")
    _bool("mcp_http_client_assistant_enabled", "mcp_http_client_assistant_enabled")
    # Hooks
    _bool("hooks_enabled",           "hooks_enabled")
    if "hooks_builtins" in data and isinstance(data["hooks_builtins"], list):
        cfg.hooks_builtins = data["hooks_builtins"]
    # Subagentes
    _int("subagents_max_concurrent",   "subagents_max_concurrent")
    _int("subagents_max_teams",        "subagents_max_teams")
    _int("subagents_max_team_size",    "subagents_max_team_size")
    _int("subagents_recent_ttl",       "subagents_recent_ttl")
    _int("subagents_default_priority", "subagents_default_priority")
    _int("subagents_auto_cont_max",     "subagents_auto_cont_max")
    _int("subagents_inference_timeout", "subagents_inference_timeout")
    _int("subagents_default_timeout",   "subagents_default_timeout")
    # Backups
    _bool("backup_enabled",          "backup_enabled")
    _str("backup_dir",               "backup_dir")
    _int("backup_max_files",         "backup_max_files")
    # Snapshots
    _bool("snapshots_enabled",       "snapshots_enabled")
    _int("snapshots_max",            "snapshots_max")
    _bool("snapshots_save_on_compact", "snapshots_save_on_compact")
    # Logging
    _bool("log_enabled",             "log_enabled")
    _str("log_level",                "log_level")
    _str("log_file",                 "log_file")
    _int("log_max_size",             "log_max_size")
    _int("log_max_files",            "log_max_files")
    # Vision
    _bool("vision_enabled",          "vision_enabled")
    _bool("vision_show_indicator",   "vision_show_indicator")
    # Chat log
    _bool("chatlog_enabled",         "chatlog_enabled")
    _str("chatlog_path",             "chatlog_path")
    _int("chatlog_max_size_mb",      "chatlog_max_size_mb")
    # Fallback
    _bool("fallback_enabled",        "fallback_enabled")
    _str("fallback_model",           "fallback_model")
    # Apariencia
    _str("accent_color",             "accent_color")

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
        "api_type":      cfg.api_type,
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
