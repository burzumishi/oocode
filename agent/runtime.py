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

# Cláusula común a todos los niveles con razonamiento: el modelo (sobre todo los
# locales tipo qwen3.5) tiende a volcar TODA su comunicación en el canal <think> y a
# devolver una respuesta visible mínima o vacía → el usuario solo ve 💭 + tools y casi
# nada de texto real. Esto reencuadra el razonamiento como canal INTERNO y exige que la
# respuesta VISIBLE siga narrando — el equivalente al comportamiento de Claude (piensa
# en su bloque, pero escribe texto al usuario en cada paso).
_THINK_VISIBLE = (
    " Tu razonamiento (💭) es un canal INTERNO: el usuario NO lo ve como narración. "
    "Por eso, en CADA respuesta escribe 1-2 frases de texto VISIBLE antes de las "
    "herramientas — también al EXPLORAR (di qué buscas y qué vas hallando: 'busco la "
    "definición de X en Y', 'el error está en Z:línea'), no solo al decidir o editar. "
    "Nunca encadenes herramientas con la respuesta visible vacía confiando en que el 💭 "
    "ya lo explica: el 💭 no se lee como hilo de la conversación. Piensa todo lo que "
    "necesites, pero deja SIEMPRE una línea de texto visible en cada paso."
)

THINK_PROMPTS = {
    "off":     "",
    "minimal": "\nSé conciso y directo en tu respuesta.",
    "low":     "\nPiensa paso a paso antes de responder." + _THINK_VISIBLE,
    "on":      "\nPiensa cuidadosamente. Considera múltiples enfoques antes de responder." + _THINK_VISIBLE,
    "medium":  "\nPiensa cuidadosamente. Considera múltiples enfoques antes de responder." + _THINK_VISIBLE,
    "high":    "\nRazona en profundidad: explora casos extremos, evalúa alternativas, piensa exhaustivamente. Muestra tu razonamiento antes de la respuesta final." + _THINK_VISIBLE,
    "full":    "\nRazona en profundidad: explora casos extremos, evalúa alternativas, piensa exhaustivamente. Muestra tu razonamiento antes de la respuesta final." + _THINK_VISIBLE,
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

    # ── Plan-mode (aprobación previa) ─────────────────────────────────────────
    # Si True, plan_create presenta el plan al usuario y ESPERA su aprobación antes de
    # ejecutarlo (vía ask_user). Modo plan. Opt-in (/plan on).
    plan_approval: bool = False

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
        if not self.reasoning:
            return base
        # `reasoning` activo: el canal <think> YA está habilitado por el parámetro `think`,
        # así que NO reforzamos "muestra tu razonamiento paso a paso" — con modelos parcos
        # (9B) esa frase hacía que volcaran todo al <think> y dejaran la respuesta visible
        # vacía. Lo que falta es TEXTO visible: garantizamos _THINK_VISIBLE una sola vez
        # (los niveles != off ya lo incluyen; off/minimal no, así que lo añadimos).
        if self.think_level == "off":
            return "\nPiensa paso a paso antes de responder." + _THINK_VISIBLE
        return base if _THINK_VISIBLE in base else base + _THINK_VISIBLE
