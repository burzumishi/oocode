"""Gestión de plugins: extensiones con ciclo de vida, herramientas y comandos /slash."""
import importlib.util
import json
import re
import sys
from pathlib import Path
from config import CONFIG_DIR

PLUGINS_DIR       = CONFIG_DIR / "plugins"    # ~/.oocode/plugins/  (principal)
INSTALL_PLUGINS_DIR = Path(__file__).parent   # oocode/plugins/     (instalación)
ENABLED_FILE      = PLUGINS_DIR / "enabled.json"

PLUGIN_TEMPLATE = '''\
"""Plugin: {name}

{description}
"""

NAME        = "{name}"
DESCRIPTION = "{description}"
VERSION     = "0.1.0"

# ── Herramientas adicionales ──────────────────────────────────────────────────
# Lista de tuplas (nombre, función, schema_openai)
TOOLS: list = []

# ── Comandos /slash adicionales ───────────────────────────────────────────────
# Mapa {{"/cmd": handler_fn}}  — handler recibe (args: str, agent_loop, config)
COMMANDS: dict = {{}}

# ── Hooks ────────────────────────────────────────────────────────────────────

def on_start(config) -> None:
    """Llamado al arrancar OOCode con la config activa."""
    pass


def on_message(role: str, content: str) -> None:
    """Llamado en cada mensaje (user/assistant)."""
    pass


def on_tool_result(name: str, args: dict, result: str) -> None:
    """Llamado tras ejecutar una herramienta."""
    pass


def system_prompt_injection() -> str:
    """Texto adicional inyectado en el system prompt. Retorna "" para nada."""
    return ""


def on_end() -> None:
    """Llamado al salir de OOCode."""
    pass
'''


class PluginManager:
    def __init__(self, enabled_override: list[str] | None = None):
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        if enabled_override is not None:
            self._enabled: set[str] = set(enabled_override)
            # Sincroniza enabled.json con lo que viene de oocode.json
            _save_set(ENABLED_FILE, self._enabled)
        else:
            self._enabled = _load_set(ENABLED_FILE)
        self._loaded: dict[str, object] = {}

    # ── Gestión ───────────────────────────────────────────────────────────────

    def _find_plugin_path(self, name: str) -> Path | None:
        """Busca un plugin primero en ~/.oocode/plugins/, luego en la instalación."""
        for d in (PLUGINS_DIR, INSTALL_PLUGINS_DIR):
            p = d / f"{name}.py"
            if p.exists():
                return p
        return None

    def all_plugins(self) -> list[dict]:
        seen: set[str] = set()
        result = []
        for d in (PLUGINS_DIR, INSTALL_PLUGINS_DIR):
            for path in sorted(d.glob("*.py")):
                if path.name.startswith("_") or path.stem == "manager":
                    continue
                name = path.stem
                if name in seen:
                    continue
                seen.add(name)
                meta = _read_meta(path)
                result.append({
                    "name": name,
                    "path": str(path),
                    "enabled": name in self._enabled,
                    "loaded": name in self._loaded,
                    **meta,
                })
        return result

    def create(self, name: str, description: str = "") -> str:
        slug = _slugify(name)
        path = PLUGINS_DIR / f"{slug}.py"
        if path.exists():
            return f"ya_existe:{path}"
        path.write_text(PLUGIN_TEMPLATE.format(
            name=name, slug=slug,
            description=description or f"Plugin {name}",
        ))
        return str(path)

    def enable(self, name: str) -> bool:
        path = PLUGINS_DIR / f"{_slugify(name)}.py"
        if not path.exists():
            return False
        self._enabled.add(path.stem)
        _save_set(ENABLED_FILE, self._enabled)
        return True

    def disable(self, name: str) -> bool:
        slug = _slugify(name)
        if slug not in self._enabled:
            return False
        self._enabled.discard(slug)
        self._loaded.pop(slug, None)
        _save_set(ENABLED_FILE, self._enabled)
        return True

    # ── Carga y uso ───────────────────────────────────────────────────────────

    def load_all(self, config) -> list[str]:
        errors = []
        for name in sorted(self._enabled):
            path = self._find_plugin_path(name)
            if path is None:
                errors.append(f"{name}: fichero no encontrado en plugins/")
                continue
            try:
                mod = _import_file(path)
                self._loaded[name] = mod
                if hasattr(mod, "on_start"):
                    mod.on_start(config)
            except Exception as e:
                errors.append(f"{name}: {e}")
        return errors

    def get_tools(self) -> list[tuple]:
        tools = []
        for mod in self._loaded.values():
            for t in getattr(mod, "TOOLS", []):
                if isinstance(t, (list, tuple)) and len(t) == 3:
                    tools.append(tuple(t))
        return tools

    def get_commands(self) -> dict[str, object]:
        cmds: dict = {}
        for mod in self._loaded.values():
            cmds.update(getattr(mod, "COMMANDS", {}))
        return cmds

    def system_injection(self) -> str:
        parts = []
        for mod in self._loaded.values():
            fn = getattr(mod, "system_prompt_injection", None)
            if callable(fn):
                try:
                    s = fn()
                    if s:
                        parts.append(s)
                except Exception:
                    pass
        return "\n".join(parts)

    def fire(self, hook: str, *args, **kwargs) -> None:
        for mod in self._loaded.values():
            fn = getattr(mod, hook, None)
            if callable(fn):
                try:
                    fn(*args, **kwargs)
                except Exception:
                    pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    return re.sub(r"[^\w]", "_", name.lower().strip()) or "plugin"


def _import_file(path: Path):
    key = f"_oocode_plugin_{path.stem}"
    spec = importlib.util.spec_from_file_location(key, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


def _read_meta(path: Path) -> dict:
    meta = {"description": "", "version": ""}
    try:
        content = path.read_text()
        for var in ("DESCRIPTION", "VERSION"):
            m = re.search(rf'^{var}\s*=\s*["\']([^"\']*)["\']', content, re.MULTILINE)
            if m:
                meta[var.lower()] = m.group(1)
    except Exception:
        pass
    return meta


def _load_set(path: Path) -> set[str]:
    if path.exists():
        try:
            return set(json.loads(path.read_text()))
        except Exception:
            pass
    return set()


def _save_set(path: Path, s: set[str]) -> None:
    path.write_text(json.dumps(sorted(s), indent=2))
