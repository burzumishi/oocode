"""Config/state helpers y utilidades para OOCode WebUI."""
import json
import os
from pathlib import Path

# ── Rutas ─────────────────────────────────────────────────────────────────────

STATE_FILE  = Path.home() / ".oocode" / "webui_state.json"
CONFIG_FILE = Path.home() / ".oocode" / "oocode.json"


# ── OOConfig ──────────────────────────────────────────────────────────────────

def _load_ooconfig():
    """Carga OOConfig desde oocode.json. Siempre fresco."""
    try:
        from config import OOConfig
        return OOConfig.load()
    except Exception:
        return None


# ── Config JSON plana ─────────────────────────────────────────────────────────

def load_config() -> dict:
    """Devuelve oocode.json como dict plano (usado por tests y rutas legacy)."""
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
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception:
        return False


# ── State ─────────────────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(state: dict) -> bool:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception:
        return False


# ── Tema ──────────────────────────────────────────────────────────────────────

def _get_theme() -> str:
    return load_state().get("theme", "dark")


# ── Modelos ───────────────────────────────────────────────────────────────────

def _model_cards(cfg) -> list[dict]:
    """Devuelve lista de {name, context_window, max_tokens, active} desde OOConfig."""
    if cfg is None:
        return []
    cards = []
    for name, mcfg in (cfg.model_configs or {}).items():
        cards.append({
            "name":           name,
            "context_window": mcfg.get("contextWindow", "—"),
            "max_tokens":     mcfg.get("maxTokens", "—"),
            "active":         name == (cfg.model or ""),
        })
    if not cards and cfg.model:
        cards.append({"name": cfg.model, "context_window": "—", "max_tokens": "—", "active": True})
    return cards


# ── Session cookie ────────────────────────────────────────────────────────────

def _get_or_create_sid() -> str:
    """Obtiene o crea el session ID persistente para este navegador."""
    from flask import session
    if "webui_sid" not in session:
        session["webui_sid"] = os.urandom(16).hex()
        session.permanent = True
    return session["webui_sid"]


# ── Tamaño legible ────────────────────────────────────────────────────────────

def _human_size(n: int | float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
