"""Plugin: tree_sitter
Análisis sintáctico real de código fuente usando tree-sitter.
Extrae funciones, clases, imports y busca llamadas sin grep.
Más preciso que regex, especialmente en proyectos grandes con contexto limitado.

Requiere: pip install tree-sitter tree-sitter-python tree-sitter-javascript tree-sitter-c tree-sitter-cpp
          (se instalan automáticamente si no están al activar el plugin)
"""
import subprocess
import sys
from pathlib import Path

NAME        = "tree_sitter"
DESCRIPTION = "Análisis AST del código (tree-sitter): extrae funciones, clases, llamadas y firmas"
VERSION     = "1.0.0"

COMMANDS: dict = {}
TOOLS: list    = []

_LANGS: dict[str, str] = {
    ".py":  "python",
    ".js":  "javascript",
    ".ts":  "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".c":   "c",
    ".h":   "c",
    ".cpp": "cpp",
    ".cc":  "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
}


# ── Instalación lazy ──────────────────────────────────────────────────────────

def _ensure_installed(lang: str) -> str | None:
    """Intenta importar tree-sitter y el grammar del lenguaje. Devuelve error o None."""
    try:
        import tree_sitter  # noqa: F401
    except ImportError:
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-q", "tree-sitter"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            return f"No se pudo instalar tree-sitter: {e}"

    # cpp usa el mismo paquete tree-sitter-cpp para ambos .cpp y .c (tree-sitter-c para C puro)
    pkg_name = lang  # "c" → "tree-sitter-c", "cpp" → "tree-sitter-cpp"
    pkg = f"tree-sitter-{pkg_name}"
    mod_name = f"tree_sitter_{pkg_name}"
    try:
        __import__(mod_name)
    except ImportError:
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-q", pkg],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            return f"No se pudo instalar {pkg}: {e}"
    return None


def _get_parser(lang: str):
    """Devuelve un parser de tree-sitter para el lenguaje dado."""
    err = _ensure_installed(lang)
    if err:
        return None, err
    try:
        import importlib
        from tree_sitter import Language, Parser
        mod  = importlib.import_module(f"tree_sitter_{lang}")
        language = Language(mod.language())
        parser   = Parser(language)
        return parser, None
    except Exception as e:
        return None, f"Error inicializando parser de {lang}: {e}"


# ── Queries por lenguaje ──────────────────────────────────────────────────────

_FUNCTION_QUERIES: dict[str, str] = {
    "python": """
        (function_definition name: (identifier) @name
            parameters: (parameters) @params) @def
        (decorated_definition
            (function_definition name: (identifier) @name
                parameters: (parameters) @params) @def)
    """,
    "javascript": """
        (function_declaration name: (identifier) @name
            parameters: (formal_parameters) @params) @def
        (method_definition name: (property_identifier) @name
            parameters: (formal_parameters) @params) @def
        (arrow_function) @def
    """,
    "typescript": """
        (function_declaration name: (identifier) @name
            parameters: (formal_parameters) @params) @def
        (method_definition name: (property_identifier) @name
            parameters: (formal_parameters) @params) @def
    """,
    "c": """
        (function_definition
            declarator: (function_declarator
                declarator: (identifier) @name)) @def
        (declaration
            declarator: (function_declarator
                declarator: (identifier) @name)) @def
    """,
    "cpp": """
        (function_definition
            declarator: (function_declarator
                declarator: (identifier) @name)) @def
        (function_definition
            declarator: (function_declarator
                declarator: (qualified_identifier) @name)) @def
    """,
}

_CLASS_QUERIES: dict[str, str] = {
    "python":     "(class_definition name: (identifier) @name) @def",
    "javascript": "(class_declaration name: (identifier) @name) @def",
    "typescript": "(class_declaration name: (identifier) @name) @def",
    # Para C: structs, enums y typedefs como "clases"
    "c": """
        (struct_specifier name: (type_identifier) @name) @def
        (enum_specifier name: (type_identifier) @name) @def
        (type_definition declarator: (type_identifier) @name) @def
    """,
    "cpp": """
        (class_specifier name: (type_identifier) @name) @def
        (struct_specifier name: (type_identifier) @name) @def
        (enum_specifier name: (type_identifier) @name) @def
    """,
}

_IMPORT_QUERIES: dict[str, str] = {
    "python":     "(import_statement) @imp  (import_from_statement) @imp",
    "javascript": "(import_declaration) @imp",
    "typescript": "(import_declaration) @imp",
    "c":   "(preproc_include) @imp",
    "cpp": "(preproc_include) @imp",
}


def _query_nodes(source: bytes, parser, lang: str, query_str: str) -> list[dict]:
    try:
        from tree_sitter import Language
        import importlib
        mod      = importlib.import_module(f"tree_sitter_{lang}")
        language = Language(mod.language())
        tree     = parser.parse(source)
        query    = language.query(query_str)
        captures = query.captures(tree.root_node)
        results  = []
        for node, capture_name in captures:
            text = source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
            results.append({
                "capture": capture_name,
                "text":    text[:200],
                "line":    node.start_point[0] + 1,
                "col":     node.start_point[1],
            })
        return results
    except Exception:
        return []


# ── Herramientas ──────────────────────────────────────────────────────────────

def extract_functions(path: str) -> str:
    """Extrae todas las funciones y métodos de un fichero con sus firmas y número de línea.

    Args:
        path: Ruta al fichero de código fuente.
    """
    p = Path(path)
    if not p.exists():
        return f"Error: fichero no encontrado: {path}"
    ext  = p.suffix.lower()
    lang = _LANGS.get(ext)
    if not lang:
        return f"Lenguaje no soportado: '{ext}'. Soportados: {', '.join(_LANGS)}"

    parser, err = _get_parser(lang)
    if err:
        return f"Error: {err}"

    source  = p.read_bytes()
    q_str   = _FUNCTION_QUERIES.get(lang, "")
    if not q_str:
        return f"Sin query de funciones para {lang}."

    nodes   = _query_nodes(source, parser, lang, q_str)
    if not nodes:
        return f"No se encontraron funciones en '{p.name}'."

    # Agrupar por línea
    by_line: dict[int, str] = {}
    for n in nodes:
        if n["capture"] == "name":
            lno = n["line"]
            by_line[lno] = n["text"]

    lines = [f"Funciones en {p.name}:\n"]
    for lno in sorted(by_line):
        lines.append(f"  :{lno:<6} {by_line[lno]}")

    return "\n".join(lines)


def extract_classes(path: str) -> str:
    """Extrae todas las clases de un fichero.

    Args:
        path: Ruta al fichero de código fuente.
    """
    p = Path(path)
    if not p.exists():
        return f"Error: fichero no encontrado: {path}"
    ext  = p.suffix.lower()
    lang = _LANGS.get(ext)
    if not lang:
        return f"Lenguaje no soportado: '{ext}'."

    parser, err = _get_parser(lang)
    if err:
        return f"Error: {err}"

    source = p.read_bytes()
    q_str  = _CLASS_QUERIES.get(lang, "")
    if not q_str:
        return f"Sin query de clases para {lang}."

    nodes  = _query_nodes(source, parser, lang, q_str)
    names  = [n for n in nodes if n["capture"] == "name"]

    if not names:
        return f"No se encontraron clases en '{p.name}'."

    lines = [f"Clases en {p.name}:\n"]
    for n in names:
        lines.append(f"  :{n['line']:<6} {n['text']}")
    return "\n".join(lines)


def extract_imports(path: str) -> str:
    """Extrae todos los imports de un fichero.

    Args:
        path: Ruta al fichero de código fuente.
    """
    p = Path(path)
    if not p.exists():
        return f"Error: fichero no encontrado: {path}"
    ext  = p.suffix.lower()
    lang = _LANGS.get(ext)
    if not lang:
        return f"Lenguaje no soportado: '{ext}'."

    parser, err = _get_parser(lang)
    if err:
        return f"Error: {err}"

    source = p.read_bytes()
    q_str  = _IMPORT_QUERIES.get(lang, "")
    nodes  = _query_nodes(source, parser, lang, q_str)
    imps   = [n for n in nodes if n["capture"] == "imp"]

    if not imps:
        return f"Sin imports en '{p.name}'."

    lines = [f"Imports en {p.name}:\n"]
    for n in imps:
        text = n["text"].replace("\n", " ")[:120]
        lines.append(f"  :{n['line']:<6} {text}")
    return "\n".join(lines)


def ast_summary(path: str) -> str:
    """Devuelve un resumen completo del fichero: clases, funciones e imports.

    Args:
        path: Ruta al fichero de código fuente.
    """
    parts = []
    for fn in (extract_imports, extract_classes, extract_functions):
        out = fn(path)
        if "Error" not in out and "no soportado" not in out:
            parts.append(out)
    if not parts:
        return extract_functions(path)  # devuelve el error informativo
    return "\n\n".join(parts)


TOOLS = [
    (
        "extract_functions",
        extract_functions,
        {
            "name": "extract_functions",
            "description": "Extrae todas las funciones y métodos de un fichero con sus líneas. Más preciso que grep para entender la estructura del código.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta al fichero fuente (.py, .js, .ts)"},
                },
                "required": ["path"],
            },
        },
    ),
    (
        "extract_classes",
        extract_classes,
        {
            "name": "extract_classes",
            "description": "Extrae todas las clases definidas en un fichero con sus líneas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta al fichero fuente"},
                },
                "required": ["path"],
            },
        },
    ),
    (
        "extract_imports",
        extract_imports,
        {
            "name": "extract_imports",
            "description": "Extrae todos los imports/requires de un fichero.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta al fichero fuente"},
                },
                "required": ["path"],
            },
        },
    ),
    (
        "ast_summary",
        ast_summary,
        {
            "name": "ast_summary",
            "description": "Devuelve un resumen completo del fichero: imports, clases y funciones. Usar antes de read_file en ficheros grandes para entender la estructura.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta al fichero fuente"},
                },
                "required": ["path"],
            },
        },
    ),
]
