"""Skill: snippets
Biblioteca personal de fragmentos de código. Guarda, busca y recupera snippets
localmente en ~/.oocode/snippets/. Sin dependencias externas.

Activa con: /skills enable snippets
"""
import json
import time
from config import CONFIG_DIR

_SNIPPETS_DIR = CONFIG_DIR / "snippets"
_INDEX_FILE   = _SNIPPETS_DIR / "index.json"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_index() -> dict:
    _SNIPPETS_DIR.mkdir(parents=True, exist_ok=True)
    if _INDEX_FILE.exists():
        try:
            return json.loads(_INDEX_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_index(index: dict) -> None:
    _INDEX_FILE.write_text(json.dumps(index, indent=2, ensure_ascii=False))


def _slugify(name: str) -> str:
    import re
    return re.sub(r"[^\w\-]", "_", name.lower().strip())[:50] or "snippet"


# ── Herramientas ──────────────────────────────────────────────────────────────

def snippet_save(name: str, code: str, language: str = "", description: str = "") -> str:
    """Guarda un fragmento de código en la biblioteca personal.

    Args:
        name: Nombre identificador del snippet (ej: "parse_date", "docker_run").
        code: Código a guardar.
        language: Lenguaje del snippet (ej: python, bash, sql). Vacío = auto-detectar.
        description: Descripción opcional del snippet.
    """
    slug  = _slugify(name)
    index = _load_index()

    # Auto-detectar lenguaje por palabras clave simples
    if not language:
        first = code.strip()[:100].lower()
        if first.startswith("def ") or "import " in first or "print(" in first:
            language = "python"
        elif first.startswith("#!/") or "echo " in first or "export " in first:
            language = "bash"
        elif first.startswith("select ") or "create table" in first:
            language = "sql"
        elif "{" in first and "}" in first and ("const " in first or "function " in first):
            language = "javascript"

    path = _SNIPPETS_DIR / f"{slug}.txt"
    path.write_text(code, encoding="utf-8")

    index[slug] = {
        "name":        name,
        "slug":        slug,
        "language":    language or "text",
        "description": description,
        "created":     time.strftime("%Y-%m-%d"),
        "size":        len(code),
    }
    _save_index(index)
    return f"Snippet guardado: '{name}' ({len(code)} chars, {language or 'text'})"


def snippet_get(name: str) -> str:
    """Recupera un snippet por nombre o slug.

    Args:
        name: Nombre o slug del snippet.
    """
    index = _load_index()
    slug  = _slugify(name)

    # Búsqueda exacta primero, luego parcial
    meta = index.get(slug)
    if meta is None:
        for k, v in index.items():
            if name.lower() in k or name.lower() in v.get("name", "").lower():
                meta = v
                slug = k
                break

    if meta is None:
        known = ", ".join(sorted(index.keys())[:10])
        return f"Snippet '{name}' no encontrado. Disponibles: {known or '(ninguno)'}"

    path = _SNIPPETS_DIR / f"{slug}.txt"
    if not path.exists():
        return f"Fichero del snippet '{name}' no encontrado en disco."

    code = path.read_text(encoding="utf-8")
    lang = meta.get("language", "")
    desc = meta.get("description", "")
    header = f"# {meta['name']}"
    if desc:
        header += f"  —  {desc}"
    return f"{header}\n```{lang}\n{code}\n```"


def snippet_list(language: str = "", search: str = "") -> str:
    """Lista los snippets guardados, opcionalmente filtrados.

    Args:
        language: Filtrar por lenguaje (python, bash, sql…). Vacío = todos.
        search: Buscar por texto en nombre o descripción. Vacío = todos.
    """
    index = _load_index()
    if not index:
        return "No hay snippets guardados. Usa snippet_save() para añadir el primero."

    items = list(index.values())
    if language:
        items = [i for i in items if i.get("language", "").lower() == language.lower()]
    if search:
        low = search.lower()
        items = [
            i for i in items
            if low in i.get("name", "").lower() or low in i.get("description", "").lower()
        ]

    if not items:
        return f"Sin snippets que coincidan con los filtros."

    lines = [f"Snippets ({len(items)}):\n"]
    for item in sorted(items, key=lambda x: x.get("name", "")):
        lang = item.get("language", "")
        desc = item.get("description", "")
        size = item.get("size", 0)
        line = f"  {item['name']:<30} [{lang:<10}] {size:>6} chars"
        if desc:
            line += f"  —  {desc[:50]}"
        lines.append(line)
    return "\n".join(lines)


def snippet_delete(name: str) -> str:
    """Elimina un snippet de la biblioteca.

    Args:
        name: Nombre o slug del snippet a eliminar.
    """
    index = _load_index()
    slug  = _slugify(name)
    if slug not in index:
        return f"Snippet '{name}' no encontrado."

    path = _SNIPPETS_DIR / f"{slug}.txt"
    if path.exists():
        path.unlink()
    del index[slug]
    _save_index(index)
    return f"Snippet '{name}' eliminado."


# ── Registro de herramientas ──────────────────────────────────────────────────

TOOLS = [
    (
        "snippet_save",
        snippet_save,
        {
            "name": "snippet_save",
            "description": "Guarda un fragmento de código en la biblioteca personal local. Útil para preservar soluciones reutilizables, comandos complejos o patrones frecuentes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name":        {"type": "string", "description": "Nombre identificador (ej: 'parse_iso_date', 'docker_compose_dev')"},
                    "code":        {"type": "string", "description": "Código a guardar"},
                    "language":    {"type": "string", "description": "Lenguaje: python, bash, sql, javascript… (vacío = auto)"},
                    "description": {"type": "string", "description": "Descripción corta del snippet"},
                },
                "required": ["name", "code"],
            },
        },
    ),
    (
        "snippet_get",
        snippet_get,
        {
            "name": "snippet_get",
            "description": "Recupera un snippet guardado por nombre. Usar cuando el usuario pide 'mi snippet de X' o 'el código que guardamos para Y'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nombre o slug del snippet"},
                },
                "required": ["name"],
            },
        },
    ),
    (
        "snippet_list",
        snippet_list,
        {
            "name": "snippet_list",
            "description": "Lista todos los snippets de la biblioteca personal, con filtros opcionales por lenguaje o búsqueda de texto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "language": {"type": "string", "description": "Filtrar por lenguaje"},
                    "search":   {"type": "string", "description": "Buscar en nombre o descripción"},
                },
                "required": [],
            },
        },
    ),
    (
        "snippet_delete",
        snippet_delete,
        {
            "name": "snippet_delete",
            "description": "Elimina un snippet de la biblioteca.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nombre del snippet a eliminar"},
                },
                "required": ["name"],
            },
        },
    ),
]
