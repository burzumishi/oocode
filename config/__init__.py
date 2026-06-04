"""Paquete de configuración de OOCode — punto de entrada.

El antiguo `config.py` se dividió aquí (constants, defaults, blocks/, model) sin
cambiar la API: `import config` y `from config import OOConfig, DEFAULT_CONFIG, …`
siguen funcionando igual.
"""
from config.constants import (
    CONFIG_DIR, CONFIG_FILE, MEMORY_DIR, HISTORY_FILE, KEYBINDINGS_FILE,
    VERSION, APP_NAME, APP_SUBTITLE, DEFAULT_AGENT_ID,
)
from config.defaults import DEFAULT_CONFIG
from config.model import AgentDef, OOConfig

__all__ = [
    "CONFIG_DIR", "CONFIG_FILE", "MEMORY_DIR", "HISTORY_FILE", "KEYBINDINGS_FILE",
    "VERSION", "APP_NAME", "APP_SUBTITLE", "DEFAULT_AGENT_ID",
    "DEFAULT_CONFIG", "AgentDef", "OOConfig",
]
