"""Constantes y rutas de configuración de OOCode."""
from pathlib import Path

CONFIG_DIR       = Path.home() / ".oocode"
CONFIG_FILE      = CONFIG_DIR / "oocode.json"
MEMORY_DIR       = CONFIG_DIR / "memory"
HISTORY_FILE     = CONFIG_DIR / "history"
KEYBINDINGS_FILE = CONFIG_DIR / "keybindings.json"

VERSION      = "0.4.3"
APP_NAME     = "OOCode"
APP_SUBTITLE = "Open Code Assistant"

DEFAULT_AGENT_ID = "main"
