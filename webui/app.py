#!/usr/bin/env python3
"""OOCode WebUI — coordinador mínimo que registra los Blueprints.

Toda la lógica está en los módulos:
  sessions.py   — gestión de sesiones y AgentLoop
  helpers.py    — config/state helpers y utilidades
  templates.py  — CSS, HTML base, _render
  api_config.py — /api/config*, /api/sessions, /api/status, /theme/set
  api_chat.py   — /api/chat/* (con bugfixes ghost generator y NameError sess)
  api_files.py  — /api/files/*
  api_agents.py — /api/agents/*
  page_home.py  — /
  page_config.py — /config
  page_chat.py  — /chat
  page_agents.py — /agents
  page_misc.py  — /sessions, /help, /doctor, /theme
"""
import os
import sys
from pathlib import Path
from flask import Flask

# Garantizar que el proyecto está en sys.path al importar webui desde cualquier CWD
_PROJECT_ROOT = str(Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ── Clave de sesión persistente ──────────────────────────────────────────────
_SECRET_FILE = Path.home() / ".oocode" / "webui_secret.key"
_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
if _SECRET_FILE.exists():
    _secret = _SECRET_FILE.read_bytes()
else:
    _secret = os.urandom(24)
    _SECRET_FILE.write_bytes(_secret)

# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = _secret
app.config['JSON_SORT_KEYS'] = False

# ── Blueprints ────────────────────────────────────────────────────────────────
from webui.api_config import bp as _bp_cfg;     app.register_blueprint(_bp_cfg)
from webui.api_chat   import bp as _bp_chat;    app.register_blueprint(_bp_chat)
from webui.api_files  import bp as _bp_files;   app.register_blueprint(_bp_files)
from webui.api_agents import bp as _bp_agents;  app.register_blueprint(_bp_agents)
from webui.page_home  import bp as _bp_home;    app.register_blueprint(_bp_home)
from webui.page_config import bp as _bp_pcfg;   app.register_blueprint(_bp_pcfg)
from webui.page_chat  import bp as _bp_pchat;   app.register_blueprint(_bp_pchat)
from webui.page_agents import bp as _bp_pagents; app.register_blueprint(_bp_pagents)
from webui.page_misc  import bp as _bp_misc;    app.register_blueprint(_bp_misc)

# ── Re-exports para compatibilidad con tests existentes ───────────────────────
from webui.sessions import (  # noqa: F401
    _WEBUI_SESSIONS,
    _SESSIONS_LOCK,
    _ensure_session_entry,
    _get_or_create_session,
    _evict_old_sessions,
    _create_loop_for_webui,
    _SESSION_TTL,
)
import webui.helpers as _helpers_mod
from webui.helpers import (  # noqa: F401
    _human_size,
    _model_cards,
    _get_or_create_sid,
    _load_ooconfig,
)

# Re-export mutable references — test fixtures patch these names on webui.app
STATE_FILE  = _helpers_mod.STATE_FILE
CONFIG_FILE = _helpers_mod.CONFIG_FILE


def load_config() -> dict:
    """Wrapper que usa CONFIG_FILE patched en tests."""
    import json
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    try:
        from config import DEFAULT_CONFIG
        return dict(DEFAULT_CONFIG)
    except Exception:
        return {"model": "batiai/qwen3.5-9b:latest", "models": {}}


def save_config(config: dict) -> bool:
    import json
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception:
        return False


def load_state() -> dict:
    import json
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(state: dict) -> bool:
    import json
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception:
        return False


def _get_theme() -> str:
    return load_state().get("theme", "dark")


# ── Arranque standalone ───────────────────────────────────────────────────────

def run_standalone(host: str = "0.0.0.0", port: int = 4000,
                   log_file: str = "", log_max_size_mb: int = 5) -> None:
    """Arranca el WebUI en modo standalone (sin TUI). Llamado por `oocode --webui start`."""
    import logging as _log
    import logging.handlers as _log_handlers

    log_path = (Path(log_file).expanduser() if log_file
                else Path.home() / ".oocode" / "logs" / "webserver.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    wz = _log.getLogger("werkzeug")
    wz.handlers.clear()
    fh = _log_handlers.RotatingFileHandler(
        str(log_path), encoding="utf-8",
        maxBytes=max(1, int(log_max_size_mb)) * 1024 * 1024,
        backupCount=3,
    )
    fh.setFormatter(_log.Formatter("%(asctime)s %(levelname)s %(message)s"))
    wz.addHandler(fh)
    wz.propagate = False
    app.logger.handlers.clear()
    app.logger.addHandler(fh)
    app.logger.propagate = False

    print(f"  OOCode WebUI arrancando en http://{host}:{port}")
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    run_standalone()
