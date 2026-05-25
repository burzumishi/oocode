import requests
from bs4 import BeautifulSoup


def web_search(query: str, max_results: int = 5) -> str:
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return "Sin resultados."
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. **{r.get('title', '')}**")
            lines.append(f"   {r.get('href', '')}")
            lines.append(f"   {r.get('body', '')[:200]}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error en búsqueda web: {e}"


def web_fetch(url: str, max_chars: int = 8000, timeout: int = 15) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; OOCode/0.1)"}
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        lines = [l for l in text.splitlines() if l.strip()]
        content = "\n".join(lines)
        if len(content) > max_chars:
            content = content[:max_chars] + "\n... (truncado)"
        return content
    except Exception as e:
        return f"Error descargando '{url}': {e}"


def build_search_schemas(
    web_fetch_max_chars: int = 8000,
    web_fetch_timeout: int = 15,
    web_search_max_results: int = 5,
) -> list[tuple]:
    """Devuelve schemas de búsqueda con defaults inyectados desde config."""

    def _web_search(query: str, max_results: int = web_search_max_results) -> str:
        return web_search(query, max_results)

    def _web_fetch(url: str, max_chars: int = web_fetch_max_chars) -> str:
        return web_fetch(url, max_chars, timeout=web_fetch_timeout)

    return [
        (
            "web_search",
            _web_search,
            {
                "name": "web_search",
                "description": "Busca información en internet usando DuckDuckGo. No requiere API key.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query":       {"type": "string",  "description": "Términos de búsqueda."},
                        "max_results": {"type": "integer", "description": f"Número máximo de resultados (por defecto {web_search_max_results})."},
                    },
                    "required": ["query"],
                },
            },
        ),
        (
            "web_fetch",
            _web_fetch,
            {
                "name": "web_fetch",
                "description": f"Descarga y extrae el texto de una URL (máx {web_fetch_max_chars} chars, timeout {web_fetch_timeout}s).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url":       {"type": "string",  "description": "URL a descargar."},
                        "max_chars": {"type": "integer", "description": f"Límite de caracteres (por defecto {web_fetch_max_chars})."},
                    },
                    "required": ["url"],
                },
            },
        ),
    ]


# Compatibilidad: schemas con defaults sin config
SEARCH_SCHEMAS = build_search_schemas()
