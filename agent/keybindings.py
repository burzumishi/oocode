"""Keybindings configurables para el REPL de OOCode."""
import json
from config import KEYBINDINGS_FILE

KB_FILE = KEYBINDINGS_FILE

# Mapa de acción → {key, desc}
# Las keys usan la notación de prompt_toolkit:
#   c-x  = Ctrl+X    s-tab = Shift+Tab    f1..f12 = función
#   escape = Escape   c-space = Ctrl+Space
DEFAULT_KB: dict[str, dict] = {
    "expand_output": {
        "key":  "c-o",
        "desc": "Expande la última salida completa (sin truncar)",
    },
    "cycle_perms": {
        "key":  "s-tab",
        "desc": "Cicla modo permisos: ask → on → full → ask  (como Shift+Tab en Claude Code)",
    },
    "clear_screen": {
        "key":  "c-l",
        "desc": "Limpia la pantalla y redibuja el prompt",
    },
    "random_tip": {
        "key":  "c-t",
        "desc": "Muestra un tip aleatorio de uso de OOCode",
    },
    "show_status": {
        "key":  "f2",
        "desc": "Estado del agente: modelo, contexto, sesión, flags",
    },
    "compact": {
        "key":  "f3",
        "desc": "Compacta el contexto con resumen LLM",
    },
    "show_keybindings": {
        "key":  "f1",
        "desc": "Lista todos los keybindings activos",
    },
    "show_context": {
        "key":  "f4",
        "desc": "Estado detallado del contexto (tokens, resumen, modo)",
    },
    "copy_last": {
        "key":  "c-y",
        "desc": "Copia la última respuesta al portapapeles",
    },
    "insert_newline": {
        "key":  "escape enter",
        "desc": "Inserta un salto de línea en el input (entrada multilínea)",
    },
}


class KeybindingManager:
    """Carga, guarda y consulta los keybindings del usuario."""

    def __init__(self) -> None:
        self._overrides: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if KB_FILE.exists():
            try:
                self._overrides = json.loads(KB_FILE.read_text())
            except Exception:
                self._overrides = {}

    def _save(self) -> None:
        KB_FILE.parent.mkdir(parents=True, exist_ok=True)
        KB_FILE.write_text(json.dumps(self._overrides, indent=2, ensure_ascii=False))

    def get(self, action: str) -> str:
        """Devuelve la key activa para una acción (override o default)."""
        return self._overrides.get(action) or DEFAULT_KB.get(action, {}).get("key", "")

    def set(self, action: str, key: str) -> bool:
        """Define un override para una acción. Devuelve False si la acción no existe."""
        if action not in DEFAULT_KB:
            return False
        self._overrides[action] = key
        self._save()
        return True

    def reset(self, action: str | None = None) -> None:
        """Elimina el override de una acción (o todos si action=None)."""
        if action is None:
            self._overrides.clear()
        else:
            self._overrides.pop(action, None)
        self._save()

    def effective(self) -> list[dict]:
        """Devuelve la tabla completa de keybindings activos."""
        result = []
        for action, info in DEFAULT_KB.items():
            active_key = self._overrides.get(action, info["key"])
            result.append({
                "action":    action,
                "key":       active_key,
                "default":   info["key"],
                "desc":      info["desc"],
                "modified":  action in self._overrides,
            })
        return result

    def actions(self) -> list[str]:
        return list(DEFAULT_KB.keys())
