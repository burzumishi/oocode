import inspect
import json
from collections import OrderedDict
from typing import Any, Callable, Optional

from tools.hooks import HookManager

# Tools que tienen side-effects y nunca deben cachearse intra-turno
_NO_CACHE_BASE: frozenset[str] = frozenset({
    "bash", "write_file", "edit_file", "edit_files",
    "git_commit", "git_push", "git_pull", "git_add", "git_stash",
    "git_patch", "git_clone",
    "docker_exec", "docker_stop", "docker_rm",
    "compose_up", "compose_down", "compose_stop",
    "compose_restart", "compose_build", "compose_pull",
    "compose_exec", "compose_run",
    "todo_add", "todo_done",
    "clipboard_copy",
    "vault_get",
    "run_tests", "test_file",
    "spawn_subagent", "explore",
    "snippet_save", "snippet_delete",
    # Filesystem tools con side-effects
    "mv_file", "cp_file", "rm_file", "rm_dir", "mkdir_dir", "touch_file",
    "chmod_file", "chmod_dir", "chown_file", "chown_dir",
    # System-assistant tools con side-effects
    "systemctl_action", "kill_process",
    "fw_allow", "fw_deny",
    "apt_update", "apt_upgrade", "apt_install", "apt_remove",
    "dnf_update", "dnf_install", "dnf_remove",
    # Debug y ejecución con side-effects
    "strace_run", "gdb_run", "pdb_run", "valgrind_run",
    "make_run", "run_script", "format_code",
    "python_exec", "pip_tool", "npm_tool",
    "archive_extract", "archive_create",
    "symlink_create", "patch_apply", "regex_replace", "bulk_replace",
})
_NO_CACHE_SUFFIXES: frozenset[str] = frozenset(f"_{n}" for n in _NO_CACHE_BASE)

_DEFAULT_CACHE_MAX_SIZE: int = 200  # entradas máx por defecto; anulable via config.tool_cache_max_size


def _is_no_cache(name: str) -> bool:
    """True si la tool tiene side-effects y no debe cachearse (incluyendo MCP prefijadas)."""
    return name in _NO_CACHE_BASE or (
        name.startswith("mcp_") and any(name.endswith(s) for s in _NO_CACHE_SUFFIXES)
    )


# Alias de compatibilidad para código que aún acceda al nombre antiguo
_NO_CACHE = _NO_CACHE_BASE


def _args_key(args: dict) -> str:
    """Clave canónica determinista para el caché LRU.  Sin hashing: el caché es
    intra-turno (≤200 entradas) y los args de tools cacheables son pequeños;
    la serialización exacta elimina cualquier riesgo de colisión silenciosa."""
    return json.dumps(args, sort_keys=True, ensure_ascii=False)


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, tuple[Callable, dict]] = {}
        self._cache: OrderedDict[str, str] = OrderedDict()  # LRU: más reciente al final
        # Parámetros válidos por tool, calculados una vez en register().
        # None → la función acepta **kwargs, no hay que filtrar.
        self._valid_params: dict[str, Optional[frozenset[str]]] = {}
        self.hooks = HookManager()
        self._cache_enabled:  bool = True
        self._cache_max_size: int  = _DEFAULT_CACHE_MAX_SIZE
        self._cache_hits:     int  = 0
        self._cache_misses:   int  = 0

    def register(self, name: str, fn: Callable, schema: dict) -> None:
        self._tools[name] = (fn, schema)
        sig = inspect.signature(fn)
        accepts_var_kw = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in sig.parameters.values()
        )
        self._valid_params[name] = None if accepts_var_kw else frozenset(sig.parameters.keys())

    def has(self, name: str) -> bool:
        return name in self._tools

    def get_fn(self, name: str) -> Optional[Callable]:
        entry = self._tools.get(name)
        return entry[0] if entry else None

    def tool_schemas(self) -> list[dict]:
        """Schemas de tools en formato OpenAI/Ollama: {"type":"function","function":{...}}."""
        return [
            {"type": "function", "function": schema}
            for _, schema in self._tools.values()
        ]

    def ollama_schemas(self) -> list[dict]:
        """Alias de compatibilidad de `tool_schemas()` (nombre previo a multi-backend).

        Solo lo ejercitan los tests; el código de producción usa `tool_schemas()`.
        Se mantiene como red de compatibilidad para código/tests externos que aún
        usen el nombre antiguo. Puede retirarse cuando ya no haya consumidores.
        """
        return self.tool_schemas()

    @property
    def cache_enabled(self) -> bool:
        return self._cache_enabled

    @cache_enabled.setter
    def cache_enabled(self, v: bool) -> None:
        self._cache_enabled = v

    @property
    def cache_max_size(self) -> int:
        return self._cache_max_size

    @cache_max_size.setter
    def cache_max_size(self, v: int) -> None:
        self._cache_max_size = v

    def cache_stats(self) -> dict:
        """Devuelve estadísticas de la caché intra-turno."""
        return {
            "enabled":  self._cache_enabled,
            "size":     len(self._cache),
            "max_size": self._cache_max_size,
            "hits":     self._cache_hits,
            "misses":   self._cache_misses,
        }

    def clear_cache(self) -> None:
        """Descarta la caché intra-turno. Llamar al inicio de cada run()."""
        self._cache.clear()

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        fn = self.get_fn(name)
        if fn is None:
            return f"Error: herramienta '{name}' no encontrada."

        cacheable = not _is_no_cache(name) and self._cache_enabled

        # ── Pre-hooks ──────────────────────────────────────────────────────
        ok, arguments = self.hooks.run_pre(name, arguments)
        if not ok:
            return "Cancelado por hook pre-tool."

        # ── Caché intra-turno ──────────────────────────────────────────────
        if cacheable:
            cache_key = f"{name}:{_args_key(arguments)}"
            if cache_key in self._cache:
                self._cache.move_to_end(cache_key)  # LRU: marcar como reciente
                self._cache_hits += 1
                return self._cache[cache_key]
            self._cache_misses += 1

        # ── Ejecución ──────────────────────────────────────────────────────
        try:
            # Filtrar kwargs que la función no acepta (el LLM a veces inventa parámetros).
            # _valid_params[name] fue calculado una vez en register(); None = acepta **kwargs.
            valid = self._valid_params.get(name)
            if valid is not None:
                arguments = {k: v for k, v in arguments.items() if k in valid}
            result = fn(**arguments)
        except Exception as e:
            result = f"Error ejecutando '{name}': {e}"

        result = str(result)

        # ── Post-hooks ─────────────────────────────────────────────────────
        result = self.hooks.run_post(name, arguments, result)

        # ── Guardar en caché (LRU) ─────────────────────────────────────────
        if cacheable:
            if len(self._cache) >= self._cache_max_size:
                self._cache.popitem(last=False)  # desaloja la entrada menos reciente
            self._cache[cache_key] = result

        return result
