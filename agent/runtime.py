"""RuntimeSettings: estado de ejecución en memoria, no persiste entre sesiones."""
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


COLOR_PRESETS: dict[str, tuple[str, str]] = {
    # nombre: (hex para prompt_toolkit, hex para rich)
    "cyan":    ("#00e5ff", "#00e5ff"),
    "green":   ("#00ff88", "#00ff88"),
    "blue":    ("#4499ff", "#4499ff"),
    "magenta": ("#ff44cc", "#ff44cc"),
    "yellow":  ("#ffcc00", "#ffcc00"),
    "red":     ("#ff3355", "#ff3355"),
    "white":   ("#ddeeff", "#ddeeff"),
}

# Temas predefinidos: nombre → {accent: color_key}
BUILTIN_THEMES: dict[str, dict] = {
    "neon":    {"accent": "cyan"},
    "forest":  {"accent": "green"},
    "ocean":   {"accent": "blue"},
    "sakura":  {"accent": "magenta"},
    "sand":    {"accent": "yellow"},
    "sunset":  {"accent": "red"},
    "snow":    {"accent": "white"},
}

# Fichero de temas guardados por el usuario
_THEMES_FILE = Path.home() / ".oocode" / "themes.json"


def load_user_themes() -> dict[str, dict]:
    if _THEMES_FILE.exists():
        try:
            return json.loads(_THEMES_FILE.read_text())
        except Exception:
            pass
    return {}


def save_user_theme(name: str, theme: dict) -> None:
    themes = load_user_themes()
    themes[name] = theme
    _THEMES_FILE.parent.mkdir(parents=True, exist_ok=True)
    _THEMES_FILE.write_text(json.dumps(themes, indent=2, ensure_ascii=False))


def delete_user_theme(name: str) -> bool:
    themes = load_user_themes()
    if name not in themes:
        return False
    del themes[name]
    _THEMES_FILE.write_text(json.dumps(themes, indent=2, ensure_ascii=False))
    return True


def all_themes() -> dict[str, dict]:
    """Devuelve builtin + usuario (usuario tiene prioridad si coincide el nombre)."""
    merged = dict(BUILTIN_THEMES)
    merged.update(load_user_themes())
    return merged


def random_color(exclude: str = "") -> str:
    """Elige un color aleatorio de COLOR_PRESETS, evitando el actual si es posible."""
    options = [c for c in COLOR_PRESETS if c != exclude]
    return random.choice(options or list(COLOR_PRESETS))

THINK_PROMPTS = {
    "off":     "",
    "minimal": "\nSé conciso y directo en tu respuesta.",
    "low":     "\nPiensa paso a paso antes de responder.",
    "on":      "\nPiensa cuidadosamente. Considera múltiples enfoques antes de responder.",
    "medium":  "\nPiensa cuidadosamente. Considera múltiples enfoques antes de responder.",
    "high":    "\nRazona en profundidad: explora casos extremos, evalúa alternativas, piensa exhaustivamente. Muestra tu razonamiento antes de la respuesta final.",
    "full":    "\nRazona en profundidad: explora casos extremos, evalúa alternativas, piensa exhaustivamente. Muestra tu razonamiento antes de la respuesta final.",
}

THINK_LEVELS  = ["off", "minimal", "low", "on", "medium", "high", "full"]
ELEVATED_MODES = ("off", "on", "ask", "full")
USAGE_MODES    = ("off", "tokens", "full")


@dataclass
class RuntimeSettings:
    # ── Modos de pensamiento ────────────────────────────────────────────────
    think_level: str  = "off"     # off | minimal | low | medium | high
    reasoning:   bool = False     # chain-of-thought explícito

    # ── Velocidad / modelo ──────────────────────────────────────────────────
    fast_mode:   bool = False
    fast_model:  Optional[str] = None   # modelo para fast mode
    normal_model: Optional[str] = None  # modelo guardado antes del fast mode

    # ── Verbosidad / diagnóstico ────────────────────────────────────────────
    verbose:     bool = False     # muestra args y resultados completos de tools
    trace:       bool = False     # muestra info del system prompt cada turno

    # ── Permisos ────────────────────────────────────────────────────────────
    elevated: str = "ask"         # off | on | ask | full

    # ── Visualización de uso ────────────────────────────────────────────────
    usage_display: str = "tokens" # off | tokens | full

    # ── Activación ──────────────────────────────────────────────────────────
    activation: str = "always"   # always | mention

    # ── Modo de contexto del workspace ──────────────────────────────────────
    ctx_mode: str = "mini"        # mini (~150 tok) | full (~800 tok)

    # ── Color y tema ─────────────────────────────────────────────────────────
    accent_color: str = "cyan"    # clave de COLOR_PRESETS

    # ── Directorios adicionales de trabajo ───────────────────────────────────
    extra_dirs: list[str] = field(default_factory=list)

    def think_injection(self) -> str:
        base = THINK_PROMPTS.get(self.think_level, "")
        if self.reasoning and self.think_level == "off":
            return "\nMuestra tu razonamiento paso a paso antes de dar la respuesta final."
        if self.reasoning:
            return base + "\nMuestra tu razonamiento paso a paso."
        return base

    def elevated_permissions(self) -> dict[str, str]:
        """Obsoleto — la lógica completa vive en AgentLoop.run() usando DEFAULT_CONFIG."""
        return {}

    def summary_line(self) -> str:
        parts = []
        if self.think_level != "off":
            parts.append(f"think={self.think_level}")
        if self.reasoning:
            parts.append("reasoning=on")
        if self.fast_mode:
            parts.append("fast=on")
        if self.verbose:
            parts.append("verbose=on")
        if self.trace:
            parts.append("trace=on")
        if self.elevated != "ask":
            parts.append(f"elevated={self.elevated}")
        if self.usage_display != "tokens":
            parts.append(f"usage={self.usage_display}")
        if self.ctx_mode != "mini":
            parts.append(f"ctx={self.ctx_mode}")
        if self.accent_color != "cyan":
            parts.append(f"color={self.accent_color}")
        if self.extra_dirs:
            parts.append(f"+{len(self.extra_dirs)} dirs")
        return "  ".join(parts) if parts else "defaults"
