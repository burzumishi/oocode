"""Plugin LSP: definición, referencias, hover, símbolos, diagnósticos, formato y más.

Lanza servidores LSP por extensión de fichero bajo demanda.
Los servidores se mantienen vivos durante la sesión.

Config (pluginOptions.lsp en oocode.json):
  requestTimeout  float  Segundos máximos esperando respuesta LSP (default 10)
  serverCmds      dict   Overrides de comandos por extensión {".py": ["pylsp"]}
  autoStart       list   Extensiones a arrancar al inicio en vez de bajo demanda

Activar: /plugins enable lsp
"""
from pathlib import Path
from typing import Optional

from agent.lsp_client import LspPool, _ext, _which, _SERVER_CMDS, _SERVER_ALIASES

_pool:   Optional[LspPool] = None
_config_opts: dict = {}


# ── Lifecycle del plugin ───────────────────────────────────────────────────────

def on_start(config) -> None:
    global _pool, _config_opts
    opts = config.plugin_options.get("lsp", {})
    if not isinstance(opts, dict):
        opts = {}
    _config_opts = opts

    timeout  = float(opts.get("requestTimeout", 10.0))
    srv_cmds = opts.get("serverCmds", {})
    if not isinstance(srv_cmds, dict):
        srv_cmds = {}
    # serverCmds viene como {".py": ["pylsp"]} o {"py": ["pylsp"]} → normalizar
    srv_cmds = {(k if k.startswith(".") else f".{k}"): v
                for k, v in srv_cmds.items()}

    workspace = getattr(config, "project_dir", "") or config.workspace
    _pool = LspPool(workspace, request_timeout=timeout,
                    server_overrides=srv_cmds or None)

    # Auto-arrancar servidores configurados
    auto_start = opts.get("autoStart", [])
    if not isinstance(auto_start, list):
        auto_start = []
    for ext in auto_start:
        ext = ext if ext.startswith(".") else f".{ext}"
        _pool.get(ext)


def on_end() -> None:
    global _pool
    if _pool is not None:
        _pool.stop_all()
        _pool = None


def on_workspace_change(new_workspace: str) -> None:
    """Llamado cuando el usuario cambia workspace con /workspace."""
    global _pool
    if _pool is not None:
        _pool.stop_all()
    timeout   = float(_config_opts.get("requestTimeout", 10.0))
    srv_cmds  = _config_opts.get("serverCmds", {})
    if not isinstance(srv_cmds, dict):
        srv_cmds = {}
    _pool = LspPool(new_workspace, request_timeout=timeout,
                    server_overrides=srv_cmds or None)
    # Re-arrancar autoStart en el nuevo workspace
    auto_start = _config_opts.get("autoStart", [])
    if not isinstance(auto_start, list):
        auto_start = []
    for ext in auto_start:
        ext = ext if ext.startswith(".") else f".{ext}"
        _pool.get(ext)


def system_prompt_injection() -> str:
    """Texto inyectado en el system prompt cuando el plugin está activo."""
    if _pool is None:
        return ""
    available = [s for s in _pool.available_servers() if s["installed"]]
    if not available:
        return ""
    exts = []
    for s in available:
        exts.extend(s["exts"])
    ext_list = ", ".join(sorted(set(exts)))
    return (
        f"\n## LSP activo — análisis semántico preciso\n"
        f"Servidores LSP disponibles para: {ext_list}.\n"
        f"**Flujo obligatorio al editar código LSP-compatible:**\n"
        f"1. **Antes de editar**: `lsp_symbols(path)` → estructura del fichero; `lsp_hover(path, line, col)` → tipo exacto del símbolo.\n"
        f"2. **Después de escribir/editar**: `lsp_diagnostics(path)` → verifica errores de compilación/tipos. **OBLIGATORIO para C/C++** (clangd).\n"
        f"3. **Si hay errores en diagnósticos**: `lsp_code_actions(path, line, col)` → quickfixes automáticos.\n"
        f"**Navegación:**\n"
        f"- `lsp_definition` → ir a definición  |  `lsp_references` → todos los usos  |  `lsp_type_definition` → tipo de variable\n"
        f"- `lsp_implementation` → implementaciones de interfaz  |  `lsp_call_hierarchy` → callers/callees\n"
        f"- `lsp_workspace_symbols(path, query)` → buscar símbolo en todo el workspace\n"
        f"**Refactoring:**\n"
        f"- `lsp_rename(path, line, col, new_name)` → renombrar en todos los ficheros (usa `apply=true` para aplicar)\n"
        f"- `lsp_format(path)` → formatear fichero\n"
        f"**Diagnóstico:**\n"
        f"- `lsp_restart(path)` → reiniciar servidor si da errores persistentes o tras cambiar tsconfig/pyproject/Cargo.toml\n"
        f"Los servidores arrancan automáticamente al primer uso; el tiempo de inicio puede ser 1-3s.\n"
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_client(path: str):
    if _pool is None:
        return None
    return _pool.get(_ext(path))


def _fmt_locations(locs: list[dict], max_results: int = 30) -> str:
    if not locs:
        return "No se encontraron resultados."
    lines = [f"{loc['path']}:{loc['line']}:{loc['col']}" for loc in locs[:max_results]]
    if len(locs) > max_results:
        lines.append(f"... ({len(locs) - max_results} más)")
    return "\n".join(lines)


def _fmt_symbols(syms: list[dict], max_results: int = 50) -> str:
    if not syms:
        return "No se encontraron símbolos."
    lines = []
    for s in syms[:max_results]:
        loc       = f"  {s['path']}:{s['line']}" if s.get("path") else ""
        container = f" [{s['container']}]" if s.get("container") else ""
        lines.append(f"{s['kind']:14s}  {s['name']}{container}{loc}")
    if len(syms) > max_results:
        lines.append(f"... ({len(syms) - max_results} más)")
    return "\n".join(lines)


def _fmt_diagnostics(diags: list[dict]) -> str:
    if not diags:
        return "Sin diagnósticos — el fichero parece correcto."
    sev_icons = {"error": "✗", "warning": "⚠", "information": "ℹ", "hint": "·"}
    lines = []
    for d in sorted(diags, key=lambda x: (x["line"], x["col"])):
        src  = f"[{d['source']}] " if d.get("source") else ""
        icon = sev_icons.get(d["severity"], "·")
        lines.append(
            f"  {icon}  {d['path']}:{d['line']}:{d['col']}"
            f"  {d['severity'].upper()}  {src}{d['message']}"
        )
    return f"{len(diags)} diagnóstico(s):\n" + "\n".join(lines)


def _no_server_msg(path: str) -> str:
    ext = _ext(path)
    # Resolver alias para encontrar el comando correcto (.h → .c → clangd)
    canonical = _SERVER_ALIASES.get(ext, ext)
    cmd = (_SERVER_CMDS.get(canonical) or _SERVER_CMDS.get(ext, [None]))[0]
    if cmd and not _which(cmd):
        install_hints = {
            "pylsp":    "pip install python-lsp-server",
            "clangd":   "apt install clangd  /  brew install llvm",
            "gopls":    "go install golang.org/x/tools/gopls@latest",
            "rust-analyzer": "rustup component add rust-analyzer",
            "typescript-language-server": "npm i -g typescript-language-server",
            "jdtls":    "apt install jdtls  /  brew install jdtls  /  https://github.com/eclipse/eclipse.jdt.ls",
            "ruby-lsp": "gem install ruby-lsp",
            "perl-language-server": "cpan PerlLanguageServer  /  cpanm PLS",
            "sqls":     "go install github.com/sqls-server/sqls@latest  /  brew install sqls",
            "bash-language-server": "npm i -g bash-language-server",
            "yaml-language-server": "npm i -g yaml-language-server",
        }
        hint = install_hints.get(cmd, f"instala {cmd}")
        return f"Servidor LSP para '{ext}' no encontrado. {hint}"
    return f"No hay servidor LSP disponible para '{ext}'."


# ── Tools ──────────────────────────────────────────────────────────────────────

def lsp_definition(path: str, line: int, col: int = 1) -> str:
    client = _get_client(path)
    if client is None:
        return _no_server_msg(path)
    try:
        return _fmt_locations(client.definition(path, line, col))
    except Exception as exc:
        return f"Error LSP: {exc}"


def lsp_references(path: str, line: int, col: int = 1,
                   include_declaration: bool = False) -> str:
    client = _get_client(path)
    if client is None:
        return _no_server_msg(path)
    try:
        return _fmt_locations(client.references(path, line, col, include_declaration))
    except Exception as exc:
        return f"Error LSP: {exc}"


def lsp_hover(path: str, line: int, col: int = 1) -> str:
    client = _get_client(path)
    if client is None:
        return _no_server_msg(path)
    try:
        text = client.hover(path, line, col)
        return text or "Sin información hover para esta posición."
    except Exception as exc:
        return f"Error LSP: {exc}"


def lsp_symbols(path: str, query: str = "") -> str:
    client = _get_client(path)
    if client is None:
        return _no_server_msg(path)
    try:
        syms = client.workspace_symbols(query) if query else client.document_symbols(path)
        return _fmt_symbols(syms)
    except Exception as exc:
        return f"Error LSP: {exc}"


_SLOW_LSP_EXTS = frozenset({".c", ".cpp", ".cc", ".h", ".hpp", ".java", ".kt", ".swift"})


def lsp_diagnostics(path: str, wait: float = 0.0) -> str:
    """Obtiene errores y advertencias del fichero via LSP.

    `wait` controla cuántos segundos esperar por diagnósticos frescos.
    Por defecto 0 → usa 3.0s para C/C++/Java y 2.0s para el resto.
    """
    client = _get_client(path)
    if client is None:
        return _no_server_msg(path)
    try:
        from pathlib import Path as _P
        _ext_used = _P(path).suffix.lower()
        effective_wait = wait if wait > 0 else (3.0 if _ext_used in _SLOW_LSP_EXTS else 2.0)
        return _fmt_diagnostics(client.diagnostics(path, wait=effective_wait))
    except Exception as exc:
        return f"Error LSP: {exc}"


def lsp_completion(path: str, line: int, col: int = 1,
                   max_results: int = 15) -> str:
    """Devuelve completions del servidor LSP en la posición indicada."""
    client = _get_client(path)
    if client is None:
        return _no_server_msg(path)
    try:
        items = client.completion(path, line, col)
        if not items:
            return "Sin completions disponibles para esta posición."
        lines = []
        for item in items[:max_results]:
            detail = f"  — {item['detail']}" if item.get("detail") else ""
            doc    = f"\n    {item['doc'][:80]}" if item.get("doc") else ""
            lines.append(f"  {item['kind']:12s}  {item['label']}{detail}{doc}")
        if len(items) > max_results:
            lines.append(f"... ({len(items) - max_results} más)")
        return f"{len(items)} completion(s):\n" + "\n".join(lines)
    except Exception as exc:
        return f"Error LSP: {exc}"


def _apply_text_edits(text: str, edits: list[dict]) -> str:
    """Aplica una lista de LSP TextEdit a un texto, de abajo a arriba."""
    lines = text.split("\n")
    for edit in sorted(
        edits,
        key=lambda e: (
            e["range"]["start"]["line"],
            e["range"]["start"]["character"],
        ),
        reverse=True,
    ):
        sl = edit["range"]["start"]["line"]
        sc = edit["range"]["start"]["character"]
        el = edit["range"]["end"]["line"]
        ec = edit["range"]["end"]["character"]
        new_text = edit["newText"]
        start_prefix = lines[sl][:sc] if sl < len(lines) else ""
        end_suffix   = lines[el][ec:]  if el < len(lines) else ""
        replacement  = (start_prefix + new_text + end_suffix).split("\n")
        lines[sl : el + 1] = replacement
    return "\n".join(lines)


def lsp_format(path: str, tab_size: int = 4, insert_spaces: bool = True) -> str:
    """Formatea el fichero via LSP y aplica los cambios directamente."""
    client = _get_client(path)
    if client is None:
        return _no_server_msg(path)
    try:
        edits = client.format_document(path, tab_size, insert_spaces)
        if not edits:
            return "El fichero ya está formateado según el servidor LSP."
        p         = Path(path).expanduser().resolve()
        original  = p.read_text(errors="replace")
        formatted = _apply_text_edits(original, edits)
        if formatted == original:
            return "El fichero ya está formateado."
        p.write_text(formatted)
        return f"Formato LSP aplicado: {len(edits)} cambio(s) en '{path}'."
    except Exception as exc:
        return f"Error LSP: {exc}"


def lsp_code_actions(path: str, line: int, col: int = 1) -> str:
    """Lista las acciones de código disponibles en path:line:col via LSP."""
    client = _get_client(path)
    if client is None:
        return _no_server_msg(path)
    try:
        actions = client.code_actions(path, line, col)
        if not actions:
            return "No hay acciones de código disponibles en esta posición."
        lines = [f"{len(actions)} acción(es) disponible(s):"]
        for i, a in enumerate(actions, 1):
            kind = f" ({a['kind']})" if a.get("kind") else ""
            cmd  = f"  →  {a['command']}" if a.get("command") else ""
            lines.append(f"  {i}. {a['title']}{kind}{cmd}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error LSP: {exc}"


def lsp_rename(path: str, line: int, col: int, new_name: str,
               apply: bool = False) -> str:
    """Renombra el símbolo en path:line:col a new_name via LSP.

    Si apply=False devuelve el resumen de cambios sin modificar nada.
    Si apply=True aplica los TextEdit y escribe todos los ficheros afectados.
    """
    client = _get_client(path)
    if client is None:
        return _no_server_msg(path)
    try:
        changes = client.rename(path, line, col, new_name)
        if not changes:
            return "El servidor LSP no devolvió cambios para este símbolo."
        total = sum(len(v) for v in changes.values())
        if apply:
            applied = 0
            errors  = []
            for fpath, edits in changes.items():
                try:
                    p        = Path(fpath).expanduser().resolve()
                    original = p.read_text(errors="replace")
                    modified = _apply_text_edits(original, edits)
                    if modified != original:
                        p.write_text(modified)
                        applied += 1
                except Exception as exc:
                    errors.append(f"  {fpath}: {exc}")
            result = (f"Rename aplicado → '{new_name}': "
                      f"{applied} fichero(s) modificado(s).")
            if errors:
                result += "\nErrores:\n" + "\n".join(errors)
            return result
        else:
            lines = [f"Rename → '{new_name}'  ({total} cambio(s) en "
                     f"{len(changes)} fichero(s)):\n"]
            for fpath, edits in sorted(changes.items()):
                lines.append(f"  {fpath}  ({len(edits)} edición(es))")
            lines.append("\nPasa apply=true para aplicar los cambios directamente.")
            return "\n".join(lines)
    except Exception as exc:
        return f"Error LSP: {exc}"


def lsp_type_definition(path: str, line: int, col: int = 1) -> str:
    """Salta a la definición del TIPO del símbolo en path:line:col via LSP."""
    client = _get_client(path)
    if client is None:
        return _no_server_msg(path)
    try:
        return _fmt_locations(client.type_definition(path, line, col))
    except Exception as exc:
        return f"Error LSP: {exc}"


def lsp_implementation(path: str, line: int, col: int = 1) -> str:
    """Lista las implementaciones del símbolo (interfaz/clase abstracta) via LSP."""
    client = _get_client(path)
    if client is None:
        return _no_server_msg(path)
    try:
        return _fmt_locations(client.implementation(path, line, col))
    except Exception as exc:
        return f"Error LSP: {exc}"


def lsp_workspace_symbols(path: str, query: str) -> str:
    """Busca símbolos (funciones, clases, variables) en todo el workspace via LSP.

    Más amplio que lsp_symbols: cruza todos los ficheros indexados por el servidor.
    `path` solo se usa para elegir el servidor LSP correcto (por extensión).
    """
    client = _get_client(path)
    if client is None:
        return _no_server_msg(path)
    try:
        syms = client.workspace_symbols(query)
        return _fmt_symbols(syms, max_results=60)
    except Exception as exc:
        return f"Error LSP: {exc}"


def lsp_call_hierarchy(path: str, line: int, col: int = 1,
                       direction: str = "incoming") -> str:
    """Muestra la jerarquía de llamadas del símbolo en path:line:col via LSP.

    direction="incoming" → quién llama a este símbolo (callers).
    direction="outgoing" → qué llama este símbolo (callees).
    """
    client = _get_client(path)
    if client is None:
        return _no_server_msg(path)
    try:
        from agent.lsp_client import _uri_to_path as _u2p
        items = client.prepare_call_hierarchy(path, line, col)
        if not items:
            return "No hay información de jerarquía de llamadas para este símbolo."
        lines: list[str] = []
        for item in items[:3]:
            name = item.get("name", "?")
            kind = item.get("kind", "")
            lines.append(f"{'→' if direction=='outgoing' else '←'}  {name}  [{kind}]")
            if direction == "incoming":
                calls = client.incoming_calls(item)
            else:
                calls = client.outgoing_calls(item)
            for call in calls[:20]:
                cf = call.get("from") if direction == "incoming" else call.get("to", {})
                if not isinstance(cf, dict):
                    continue
                cn    = cf.get("name", "?")
                curi  = cf.get("uri", "")
                cpath = _u2p(curi) if curi else ""
                cl    = cf.get("range", {}).get("start", {}).get("line", 0) + 1
                loc   = f"  {cpath}:{cl}" if cpath else ""
                lines.append(f"    {cn}{loc}")
            if not calls:
                lines.append("    (ninguna)")
        return "\n".join(lines) if lines else "Sin resultados."
    except Exception as exc:
        return f"Error LSP: {exc}"


def lsp_restart(path: str) -> str:
    """Reinicia el servidor LSP para la extensión del fichero dado.

    Útil cuando el servidor se congela, da errores persistentes o tras cambios
    en la configuración del proyecto (pyproject.toml, tsconfig.json, etc.).
    """
    if _pool is None:
        return "LSP pool no inicializado."
    ext = _ext(path)
    ok  = _pool.restart(ext)
    return (f"Servidor LSP para '{ext}' reiniciado correctamente."
            if ok else
            f"No se pudo reiniciar el servidor LSP para '{ext}'.")


# ── Status (para /lsp command) ─────────────────────────────────────────────────

def get_status() -> dict:
    """Devuelve estado del pool para el comando /lsp."""
    if _pool is None:
        return {"active": False, "clients": [], "available": []}
    return {
        "active":    True,
        "clients":   _pool.status(),
        "available": _pool.available_servers(),
    }


# ── Registro ───────────────────────────────────────────────────────────────────

TOOLS = [
    ("lsp_definition", lsp_definition, {
        "name": "lsp_definition",
        "description": (
            "Go-to-definition: salta a la definición del símbolo en "
            "path:line:col via LSP. Devuelve ruta y número de línea."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta del fichero fuente"},
                "line": {"type": "integer", "description": "Número de línea (1-based)"},
                "col":  {"type": "integer", "description": "Columna (1-based)", "default": 1},
            },
            "required": ["path", "line"],
        },
    }),
    ("lsp_references", lsp_references, {
        "name": "lsp_references",
        "description": "Lista todas las referencias al símbolo en path:line:col via LSP.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta del fichero fuente"},
                "line": {"type": "integer", "description": "Número de línea (1-based)"},
                "col":  {"type": "integer", "description": "Columna (1-based)", "default": 1},
                "include_declaration": {
                    "type": "boolean",
                    "description": "Incluir la declaración original",
                    "default": False,
                },
            },
            "required": ["path", "line"],
        },
    }),
    ("lsp_hover", lsp_hover, {
        "name": "lsp_hover",
        "description": "Obtiene el tipo/documentación del símbolo en path:line:col via LSP.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta del fichero fuente"},
                "line": {"type": "integer", "description": "Número de línea (1-based)"},
                "col":  {"type": "integer", "description": "Columna (1-based)", "default": 1},
            },
            "required": ["path", "line"],
        },
    }),
    ("lsp_symbols", lsp_symbols, {
        "name": "lsp_symbols",
        "description": (
            "Lista símbolos del fichero (clases, funciones, variables) o "
            "busca un símbolo en todo el workspace si se da query."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path":  {"type": "string", "description": "Ruta del fichero fuente"},
                "query": {
                    "type": "string",
                    "description": "Búsqueda global en el workspace (vacío = símbolos del fichero)",
                    "default": "",
                },
            },
            "required": ["path"],
        },
    }),
    ("lsp_diagnostics", lsp_diagnostics, {
        "name": "lsp_diagnostics",
        "description": (
            "Obtiene errores y advertencias del fichero via LSP (equivalente a errores del IDE). "
            "OBLIGATORIO después de editar o escribir cualquier fichero con servidor LSP activo."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta del fichero fuente"},
                "wait": {
                    "type": "number",
                    "description": "Segundos máximos esperando diagnósticos frescos (0 = auto: 3s para C/C++/Java, 2s el resto)",
                    "default": 0.0,
                },
            },
            "required": ["path"],
        },
    }),
    ("lsp_completion", lsp_completion, {
        "name": "lsp_completion",
        "description": (
            "Completions de código en path:line:col via LSP. "
            "Útil para conocer los métodos, propiedades o imports disponibles."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path":        {"type": "string",  "description": "Ruta del fichero fuente"},
                "line":        {"type": "integer", "description": "Número de línea (1-based)"},
                "col":         {"type": "integer", "description": "Columna (1-based)", "default": 1},
                "max_results": {"type": "integer", "description": "Máximo de sugerencias a devolver", "default": 15},
            },
            "required": ["path", "line"],
        },
    }),
    ("lsp_rename", lsp_rename, {
        "name": "lsp_rename",
        "description": (
            "Renombra el símbolo en path:line:col via LSP. "
            "Con apply=false (defecto) muestra los ficheros afectados sin tocarlos. "
            "Con apply=true aplica los cambios directamente a todos los ficheros."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path":     {"type": "string",  "description": "Ruta del fichero fuente"},
                "line":     {"type": "integer", "description": "Número de línea (1-based)"},
                "col":      {"type": "integer", "description": "Columna (1-based)", "default": 1},
                "new_name": {"type": "string",  "description": "Nuevo nombre del símbolo"},
                "apply":    {"type": "boolean", "description": "Aplicar cambios directamente (default false)", "default": False},
            },
            "required": ["path", "line", "new_name"],
        },
    }),
    ("lsp_format", lsp_format, {
        "name": "lsp_format",
        "description": (
            "Formatea el fichero via LSP (textDocument/formatting) y aplica los cambios "
            "directamente. Equivalente a 'Format Document' del IDE."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path":          {"type": "string",  "description": "Ruta del fichero fuente"},
                "tab_size":      {"type": "integer", "description": "Tamaño del tab (default 4)", "default": 4},
                "insert_spaces": {"type": "boolean", "description": "Usar espacios en vez de tabs (default true)", "default": True},
            },
            "required": ["path"],
        },
    }),
    ("lsp_code_actions", lsp_code_actions, {
        "name": "lsp_code_actions",
        "description": (
            "Lista las acciones de código disponibles en path:line:col via LSP "
            "(quickfixes, refactors, imports automáticos, etc.)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string",  "description": "Ruta del fichero fuente"},
                "line": {"type": "integer", "description": "Número de línea (1-based)"},
                "col":  {"type": "integer", "description": "Columna (1-based)", "default": 1},
            },
            "required": ["path", "line"],
        },
    }),
    ("lsp_type_definition", lsp_type_definition, {
        "name": "lsp_type_definition",
        "description": (
            "Go-to-type-definition: salta a la definición del TIPO del símbolo "
            "en path:line:col via LSP. Útil para conocer el tipo de una variable."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string",  "description": "Ruta del fichero fuente"},
                "line": {"type": "integer", "description": "Número de línea (1-based)"},
                "col":  {"type": "integer", "description": "Columna (1-based)", "default": 1},
            },
            "required": ["path", "line"],
        },
    }),
    ("lsp_implementation", lsp_implementation, {
        "name": "lsp_implementation",
        "description": (
            "Lista las implementaciones concretas de una interfaz o clase abstracta "
            "en path:line:col via LSP."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string",  "description": "Ruta del fichero fuente"},
                "line": {"type": "integer", "description": "Número de línea (1-based)"},
                "col":  {"type": "integer", "description": "Columna (1-based)", "default": 1},
            },
            "required": ["path", "line"],
        },
    }),
    ("lsp_workspace_symbols", lsp_workspace_symbols, {
        "name": "lsp_workspace_symbols",
        "description": (
            "Busca símbolos (funciones, clases, variables, tipos) en todo el workspace via LSP. "
            "Devuelve coincidencias de todos los ficheros indexados por el servidor."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path":  {"type": "string", "description": "Fichero de referencia (elige el servidor por extensión)"},
                "query": {"type": "string", "description": "Nombre o patrón del símbolo a buscar"},
            },
            "required": ["path", "query"],
        },
    }),
    ("lsp_call_hierarchy", lsp_call_hierarchy, {
        "name": "lsp_call_hierarchy",
        "description": (
            "Muestra la jerarquía de llamadas del símbolo via LSP. "
            "direction='incoming' → quién llama a este símbolo (callers). "
            "direction='outgoing' → qué llama este símbolo (callees)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path":      {"type": "string",  "description": "Ruta del fichero fuente"},
                "line":      {"type": "integer", "description": "Número de línea (1-based)"},
                "col":       {"type": "integer", "description": "Columna (1-based)", "default": 1},
                "direction": {
                    "type": "string",
                    "description": "'incoming' (quién llama) o 'outgoing' (qué llama)",
                    "enum": ["incoming", "outgoing"],
                    "default": "incoming",
                },
            },
            "required": ["path", "line"],
        },
    }),
    ("lsp_restart", lsp_restart, {
        "name": "lsp_restart",
        "description": (
            "Reinicia el servidor LSP para la extensión del fichero dado. "
            "Usa cuando el servidor da errores persistentes, tras cambios de configuración "
            "(pyproject.toml, tsconfig.json, Cargo.toml) o cuando los diagnósticos parecen incorrectos."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta del fichero (elige el servidor por extensión)"},
            },
            "required": ["path"],
        },
    }),
]


def get_tools():
    return TOOLS
