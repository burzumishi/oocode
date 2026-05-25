"""Plugin: SearXNG Search

Motor de búsqueda local usando SearXNG — reemplaza o complementa DuckDuckGo.
Configurable desde /config edit o editando la sección "searxng" de oocode.json.
"""

import requests

NAME        = "searxng"
DESCRIPTION = "Búsqueda web mediante instancia SearXNG local"
VERSION     = "1.0.0"

_cfg: dict = {
    "url":         "",
    "enabled":     False,
    "max_results": 5,
    "categories":  "general",
    "language":    "auto",
    "safe_search": 0,
    "timeout":     10,
}

COMMANDS: dict = {}


# ── Función de búsqueda ───────────────────────────────────────────────────────

def _searxng_search(query: str, max_results: int = 0, categories: str = "") -> str:
    url = _cfg["url"]
    if not url:
        return (
            "SearXNG no está configurado. Añade la URL con:\n"
            "  /config edit  →  URL de la instancia SearXNG\n"
            "o edita ~/.oocode/oocode.json, sección \"searxng\" → \"url\"."
        )
    max_r = max_results if max_results > 0 else _cfg["max_results"]
    cats  = categories.strip() or _cfg["categories"]
    params = {
        "q":          query,
        "format":     "json",
        "categories": cats,
        "language":   _cfg["language"],
        "safesearch": _cfg["safe_search"],
    }
    try:
        resp = requests.get(
            f"{url.rstrip('/')}/search",
            params=params,
            timeout=_cfg["timeout"],
            headers={"Accept": "application/json", "User-Agent": "OOCode/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.ConnectionError:
        return f"No se puede conectar con SearXNG en {url}. ¿Está el servidor activo?"
    except requests.exceptions.Timeout:
        return f"Timeout conectando con SearXNG ({_cfg['timeout']}s). Aumenta el valor en /config."
    except Exception as e:
        return f"Error consultando SearXNG: {e}"

    results = data.get("results", [])[:max_r]
    if not results:
        infoboxes = data.get("infoboxes", [])
        if infoboxes:
            box = infoboxes[0]
            return f"**{box.get('infobox', '')}**\n{box.get('content', '')[:400]}"
        return f"Sin resultados para «{query}» en SearXNG."

    lines = []
    for i, r in enumerate(results, 1):
        title   = r.get("title", "").strip()
        url_r   = r.get("url", "")
        snippet = (r.get("content") or "").strip()[:220]
        engines = ", ".join(r.get("engines", []))
        lines.append(f"{i}. **{title}**")
        lines.append(f"   {url_r}")
        if snippet:
            lines.append(f"   {snippet}")
        if engines:
            lines.append(f"   [dim]vía {engines}[/dim]")
    return "\n".join(lines)


# ── Schemas ───────────────────────────────────────────────────────────────────

_PARAMS = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Términos de búsqueda.",
        },
        "max_results": {
            "type": "integer",
            "description": "Número máximo de resultados (0 = usar el valor configurado).",
        },
        "categories": {
            "type": "string",
            "description": (
                "Categorías de búsqueda separadas por coma. "
                "Valores: general, news, science, it, images, videos, music, files, social media."
            ),
        },
    },
    "required": ["query"],
}


def _searxng_schema(name: str, description: str) -> dict:
    return {"name": name, "description": description, "parameters": _PARAMS}


def _build_tools() -> list:
    base_url = _cfg["url"] or "sin configurar"
    tools = [
        (
            "searxng_search",
            _searxng_search,
            _searxng_schema(
                "searxng_search",
                f"Busca en internet usando SearXNG ({base_url}). "
                "Soporta categorías: general, news, science, it, images...",
            ),
        ),
    ]
    if _cfg.get("enabled") and _cfg.get("url"):
        tools.append((
            "web_search",
            _searxng_search,
            _searxng_schema(
                "web_search",
                f"Busca en internet usando SearXNG local ({base_url}). "
                "Reemplaza DuckDuckGo con motor privado.",
            ),
        ))
    return tools


TOOLS: list = _build_tools()


# ── Ciclo de vida ─────────────────────────────────────────────────────────────

def on_start(config) -> None:
    _cfg["url"]         = getattr(config, "searxng_url", "")
    _cfg["enabled"]     = getattr(config, "searxng_enabled", False)
    _cfg["max_results"] = getattr(config, "searxng_max_results", 5)
    _cfg["categories"]  = getattr(config, "searxng_categories", "general")
    _cfg["language"]    = getattr(config, "searxng_language", "auto")
    _cfg["safe_search"] = getattr(config, "searxng_safe_search", 0)
    _cfg["timeout"]     = getattr(config, "searxng_timeout", 10)

    global TOOLS
    TOOLS = _build_tools()


def on_message(role: str, content: str) -> None:
    pass


def on_tool_result(name: str, args: dict, result: str) -> None:
    pass


def system_prompt_injection() -> str:
    if _cfg.get("url") and _cfg.get("enabled"):
        return (
            f"Motor de búsqueda web activo: SearXNG en {_cfg['url']}. "
            f"Categorías disponibles: general, news, science, it, images, videos."
        )
    return ""


def on_end() -> None:
    pass
