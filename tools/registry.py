import inspect
import json
from collections import OrderedDict
from typing import Any, Callable, Optional

from tools.hooks import HookManager

# Tools que tienen side-effects y nunca deben cachearse intra-turno
_NO_CACHE_BASE: frozenset[str] = frozenset({
    "bash", "write_file", "edit_file", "edit_files", "smart_replace",
    "git_commit", "git_push", "git_pull", "git_add", "git_stash",
    "git_patch", "git_clone", "git_apply", "git_checkout",
    "git_reset", "git_merge", "git_rebase",
    "docker_exec", "docker_stop", "docker_rm",
    "compose_up", "compose_down", "compose_stop",
    "compose_restart", "compose_build", "compose_pull",
    "compose_exec", "compose_run",
    "todo_add", "todo_done",
    "clipboard_copy",
    "vault_get",
    "run_tests", "test_file",
    "spawn_subagent", "explore",
    "ask_user",   # pregunta interactiva: bloquea y muestra UI — nunca cachear la respuesta
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

# ── Invalidación de la caché de lecturas tras mutaciones ──────────────────────
# La caché intra-turno guarda resultados de tools de SOLO LECTURA (read_file,
# grep_code, read_sections, ls_dir, tree…). El bucle de auto-continue ejecuta
# muchas tools dentro de UN turno, así que la caché sobrevive a las escrituras
# intermedias. Sin invalidación, `read_file(path)` tras `edit_file(path)` devuelve
# el contenido VIEJO → el LLM cree que el edit no se aplicó, reintenta el mismo
# old_string y obtiene "PRE-EDIT FALLIDO" (ya estaba aplicado) → bucle de revert.
#
# Tools que mutan UNA ruta concreta (tienen arg path/file): invalidación dirigida
# de las entradas de caché que referencian esa ruta (o su directorio padre).
_FS_WRITE_PATH_TOOLS: frozenset[str] = frozenset({
    "write_file", "edit_file", "edit_files", "regex_replace", "smart_replace",
    "bulk_replace", "patch_apply", "format_code",
    "mv_file", "cp_file", "rm_file", "rm_dir", "mkdir_dir", "touch_file",
    "chmod_file", "chmod_dir", "chown_file", "chown_dir", "symlink_create",
    "archive_extract", "archive_create",
})
# Tools que pueden mutar ficheros ARBITRARIOS sin una ruta fiable en sus args
# (ejecutan comandos/scripts): invalidan TODA la caché de lecturas por seguridad.
_FS_WRITE_BROAD_TOOLS: frozenset[str] = frozenset({
    "bash", "python_exec", "make_run", "run_script", "npm_tool", "pip_tool",
    "git_patch", "git_stash", "git_pull", "git_clone", "git_add", "git_apply",
    "git_checkout", "git_reset", "git_merge", "git_rebase",
    "docker_exec", "compose_up", "compose_down", "compose_build",
    "compose_restart", "compose_run", "compose_exec",
    "strace_run", "gdb_run", "pdb_run", "valgrind_run",
    "apt_install", "apt_remove", "apt_upgrade", "dnf_install", "dnf_remove",
})
# Claves de argumento que típicamente contienen rutas de fichero/directorio.
_PATH_ARG_KEYS: tuple[str, ...] = (
    "path", "file", "filename", "filepath", "dest", "destination",
    "target", "output", "out", "src", "source", "to", "from", "dir", "directory",
)

# Familia ESTRECHA de alias que significan inequívocamente "la ruta del fichero".
# El LLM confunde el nombre entre tools (edit_file/read_file/write_file usan `path`;
# smart_replace/regex_replace usan `file`), así que llama `edit_file(file=…)` y el
# filtro de kwargs lo descarta → "missing required argument 'path'" (causa nº1 de
# fallos de edición en logs reales). No incluye dest/target/src/output (ambiguos).
_PATH_ALIAS_FAMILY: tuple[str, ...] = (
    "path", "file", "file_path", "filepath", "fpath", "filename",
)


def _normalize_path_aliases(
    arguments: dict, valid: Optional[frozenset]
) -> dict:
    """Remapea un alias de ruta al nombre canónico que la función ACEPTA.

    Si la función espera uno de `_PATH_ALIAS_FAMILY` (p.ej. `path`) y el modelo mandó
    otro de la familia (p.ej. `file`), copia el valor al nombre correcto. No toca nada
    si la función no tiene parámetro de ruta, si ya viene el canónico, o si acepta
    **kwargs (valid=None → no se conoce el canónico). Idempotente y conservador."""
    if valid is None or not isinstance(arguments, dict):
        return arguments
    canon = next((a for a in _PATH_ALIAS_FAMILY if a in valid), None)
    if canon is None or canon in arguments:
        return arguments
    for alias in _PATH_ALIAS_FAMILY:
        if alias != canon and arguments.get(alias):
            out = dict(arguments)
            out[canon] = out.pop(alias)
            return out
    return arguments


def _is_no_cache(name: str) -> bool:
    """True si la tool tiene side-effects y no debe cachearse (incluyendo MCP prefijadas)."""
    return name in _NO_CACHE_BASE or (
        name.startswith("mcp_") and any(name.endswith(s) for s in _NO_CACHE_SUFFIXES)
    )


def _affected(name: str, table: frozenset[str]) -> bool:
    """True si `name` (o su versión MCP-prefijada) está en `table`."""
    if name in table:
        return True
    if name.startswith("mcp_"):
        return any(name.endswith("_" + t) for t in table)
    return False


def _mutated_paths(args: dict) -> list[str]:
    """Extrae las rutas de fichero/directorio referenciadas en los args de una
    tool de mutación, para invalidar las lecturas cacheadas de esas rutas."""
    paths: list[str] = []

    def _collect(d: dict) -> None:
        for k in _PATH_ARG_KEYS:
            v = d.get(k)
            if isinstance(v, str) and v:
                paths.append(v)

    if isinstance(args, dict):
        _collect(args)
        # edit_files/bulk_replace: lista de dicts con su propia ruta.
        for list_key in ("files", "edits", "replacements", "items"):
            lst = args.get(list_key)
            if isinstance(lst, list):
                for it in lst:
                    if isinstance(it, dict):
                        _collect(it)
    return paths


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
        # Caché de la lista de schemas envueltos: _tools solo cambia en register()
        # (init + hot-add MCP), así que se invalida ahí. Evita reconstruir 318 dicts
        # en cada _filtered_schemas (1×/iteración de turno).
        self._schemas_cache: Optional[list[dict]] = None

    def register(self, name: str, fn: Callable, schema: dict) -> None:
        self._tools[name] = (fn, schema)
        self._schemas_cache = None   # invalida la lista cacheada
        sig = inspect.signature(fn)
        accepts_var_kw = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in sig.parameters.values()
        )
        self._valid_params[name] = None if accepts_var_kw else frozenset(sig.parameters.keys())

    def has(self, name: str) -> bool:
        return name in self._tools

    def normalized_args(self, name: str, arguments: dict) -> dict:
        """Remapea alias de ruta (file↔path…) al nombre que la tool nativa acepta.

        Expuesto para que el dispatch (agent/loop.py) normalice ANTES del precheck y
        la extracción de write-target, de modo que todo el pipeline vea el nombre
        canónico. Para tools desconocidas/MCP (valid=None) devuelve los args intactos."""
        return _normalize_path_aliases(arguments, self._valid_params.get(name))

    def get_fn(self, name: str) -> Optional[Callable]:
        entry = self._tools.get(name)
        return entry[0] if entry else None

    def tool_schemas(self) -> list[dict]:
        """Schemas de tools en formato OpenAI/Ollama: {"type":"function","function":{...}}.

        Cacheado: se reconstruye solo cuando cambian las tools (register → invalida).
        """
        if self._schemas_cache is None:
            self._schemas_cache = [
                {"type": "function", "function": schema}
                for _, schema in self._tools.values()
            ]
        return self._schemas_cache

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

    def _invalidate_after_mutation(self, name: str, arguments: dict) -> None:
        """Invalida las lecturas cacheadas que pudieron quedar obsoletas tras una
        tool de mutación, para que un `read_file` posterior no devuelva contenido
        viejo (causa del bucle edit→read-stale→reintento→PRE-EDIT FALLIDO)."""
        if not self._cache:
            return
        # Tools que ejecutan comandos/scripts: ruta no fiable → vaciar todo.
        if _affected(name, _FS_WRITE_BROAD_TOOLS):
            self._cache.clear()
            return
        # Tools con ruta concreta: invalidación dirigida (fichero + dir padre).
        if _affected(name, _FS_WRITE_PATH_TOOLS):
            paths = _mutated_paths(arguments)
            if not paths:
                # Mutación sin ruta detectable: vaciar por seguridad.
                self._cache.clear()
                return
            import os
            needles: set[str] = set()
            for p in paths:
                needles.add(p)
                parent = os.path.dirname(p.rstrip("/"))
                if parent:
                    needles.add(parent)
                # basename solo si es específico (evita matches espurios con
                # nombres cortos/comunes); cubre el caso ruta-absoluta-vs-relativa.
                base = os.path.basename(p.rstrip("/"))
                if len(base) >= 4:
                    needles.add(base)
            for key in list(self._cache):
                if any(n in key for n in needles):
                    del self._cache[key]

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
            # Remapear alias de ruta (file↔path…) ANTES del filtro: si no, un
            # edit_file(file=…) perdía `file` aquí y reventaba por `path` ausente.
            arguments = _normalize_path_aliases(arguments, valid)
            if valid is not None:
                arguments = {k: v for k, v in arguments.items() if k in valid}
            result = fn(**arguments)
        except Exception as e:
            result = f"Error ejecutando '{name}': {e}"

        result = str(result)

        # ── Post-hooks ─────────────────────────────────────────────────────
        result = self.hooks.run_post(name, arguments, result)

        # ── Invalidar lecturas obsoletas tras mutaciones ───────────────────
        # Si esta tool mutó el filesystem, las lecturas cacheadas de ese
        # fichero/dir ya no son válidas. Sin esto, un read_file posterior
        # devuelve contenido pre-edición y el LLM entra en bucle de reintentos.
        if not cacheable:
            self._invalidate_after_mutation(name, arguments)

        # ── Guardar en caché (LRU) ─────────────────────────────────────────
        if cacheable:
            if len(self._cache) >= self._cache_max_size:
                self._cache.popitem(last=False)  # desaloja la entrada menos reciente
            self._cache[cache_key] = result

        return result
