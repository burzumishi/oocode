"""Plugin: embeddings_search
Búsqueda semántica local sobre el workspace usando el cliente de embeddings de Ollama
que ya corre en OOCode. Indexa ficheros de código/texto y permite al agente encontrar
fragmentos relevantes sin leer todo el proyecto.
"""
import json
import os
from pathlib import Path
from config import CONFIG_DIR

NAME        = "embeddings_search"
DESCRIPTION = "Búsqueda semántica local sobre el workspace (sin API externa, usa Ollama)"
VERSION     = "1.0.0"

INDEX_DIR = CONFIG_DIR / "search_index"

_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".c", ".cpp", ".h",
    ".java", ".rb", ".php", ".cs", ".swift", ".kt", ".md", ".txt", ".sh",
    ".yaml", ".yml", ".toml", ".json", ".html", ".css", ".sql",
}
_IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    "dist", "build", ".mypy_cache", ".ruff_cache", "target",
}
_MAX_FILE_CHARS = 8000
_CHUNK_CHARS    = 600
_CHUNK_OVERLAP  = 80

_state: dict = {
    "embed_client": None,
    "workspace":    None,
}

COMMANDS: dict = {}
TOOLS: list = []


# ── Helpers ───────────────────────────────────────────────────────────────────

def _chunk_text(text: str, path: str) -> list[dict]:
    """Divide el texto en fragmentos con solapamiento."""
    lines  = text.splitlines(keepends=True)
    chunks = []
    buf   = ""
    start = 0
    for i, line in enumerate(lines):
        buf += line
        if len(buf) >= _CHUNK_CHARS:
            chunks.append({"path": path, "line": start + 1, "text": buf.strip()})
            # retroceder overlap
            overlap = ""
            for j in range(i, max(-1, i - 5), -1):
                overlap = lines[j] + overlap
                if len(overlap) >= _CHUNK_OVERLAP:
                    break
            buf   = overlap
            start = i + 1 - overlap.count("\n")
    if buf.strip():
        chunks.append({"path": path, "line": start + 1, "text": buf.strip()})
    return chunks


def _index_path(index_dir: Path) -> Path:
    return index_dir / "index.json"


def _load_index(index_dir: Path) -> dict:
    p = _index_path(index_dir)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {"chunks": [], "mtime": {}}


def _save_index(index_dir: Path, data: dict) -> None:
    index_dir.mkdir(parents=True, exist_ok=True)
    _index_path(index_dir).write_text(json.dumps(data, ensure_ascii=False))


def _embed_client():
    return _state.get("embed_client")


def _workspace() -> str:
    return _state.get("workspace") or os.getcwd()


# ── Herramientas ──────────────────────────────────────────────────────────────

def index_workspace(path: str = "", incremental: bool = True) -> str:
    """Indexa ficheros del workspace para búsqueda semántica.

    Args:
        path: Directorio a indexar (vacío = workspace del agente).
        incremental: Si True solo reindexea ficheros modificados.
    """
    ec = _embed_client()
    if ec is None or not ec.is_available():
        return "Error: cliente de embeddings no disponible (comprueba que Ollama tiene un modelo de embeddings)."

    root = Path(path or _workspace())
    if not root.is_dir():
        return f"Error: directorio no encontrado: {root}"

    index_dir = INDEX_DIR / root.name
    data = _load_index(index_dir) if incremental else {"chunks": [], "mtime": {}}

    # Recopilar ficheros
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]
        for fn in filenames:
            fp = Path(dirpath) / fn
            if fp.suffix.lower() in _EXTENSIONS:
                files.append(fp)

    new_count = 0
    skip_count = 0
    for fp in files:
        rel = str(fp)
        mtime = str(fp.stat().st_mtime)
        if incremental and data["mtime"].get(rel) == mtime:
            skip_count += 1
            continue
        try:
            text = fp.read_text(errors="replace")[:_MAX_FILE_CHARS]
        except Exception:
            continue

        chunks = _chunk_text(text, rel)
        # Borrar chunks anteriores del mismo fichero
        data["chunks"] = [c for c in data["chunks"] if c["path"] != rel]
        for chunk in chunks:
            vec = ec.embed(chunk["text"])
            if vec:
                chunk["vec"] = vec
                data["chunks"].append(chunk)
                new_count += 1
        data["mtime"][rel] = mtime

    _save_index(index_dir, data)
    return (
        f"Índice actualizado: {root.name}\n"
        f"  Ficheros procesados : {len(files) - skip_count}\n"
        f"  Fragmentos nuevos   : {new_count}\n"
        f"  Total en índice     : {len(data['chunks'])}\n"
        f"  Índice guardado en  : {index_dir}"
    )


def semantic_search(query: str, path: str = "", top_k: int = 5) -> str:
    """Busca fragmentos de código/texto semánticamente similares a la consulta.

    Args:
        query: Texto de búsqueda en lenguaje natural o código.
        path: Directorio donde buscar (vacío = workspace del agente).
        top_k: Número máximo de resultados.
    """
    ec = _embed_client()
    if ec is None or not ec.is_available():
        return "Error: cliente de embeddings no disponible."

    root    = Path(path or _workspace())
    idx_dir = INDEX_DIR / root.name
    data    = _load_index(idx_dir)
    if not data["chunks"]:
        return (
            f"El índice de '{root.name}' está vacío. "
            "Usa index_workspace() para indexarlo primero."
        )

    q_vec = ec.embed(query)
    if not q_vec:
        return "Error: no se pudo generar embedding para la consulta."

    scored = []
    for chunk in data["chunks"]:
        vec = chunk.get("vec", [])
        if not vec:
            continue
        sim = ec.similarity(q_vec, vec)
        scored.append((sim, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    if not top:
        return "Sin resultados."

    lines = [f"Resultados para: «{query}»\n"]
    for sim, chunk in top:
        rel  = chunk["path"]
        lno  = chunk.get("line", "?")
        text = chunk["text"][:300].replace("\n", "\n    ")
        lines.append(f"── {rel}:{lno}  (sim={sim:.3f})\n    {text}\n")
    return "\n".join(lines)


TOOLS = [
    (
        "index_workspace",
        index_workspace,
        {
            "name": "index_workspace",
            "description": "Indexa ficheros del workspace para búsqueda semántica. Llama esto antes de semantic_search si el proyecto no está indexado o ha cambiado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":        {"type": "string", "description": "Directorio a indexar (vacío = workspace actual)"},
                    "incremental": {"type": "boolean", "description": "Si True, solo reindexea ficheros modificados (defecto: true)"},
                },
                "required": [],
            },
        },
    ),
    (
        "semantic_search",
        semantic_search,
        {
            "name": "semantic_search",
            "description": "Busca fragmentos de código o texto semánticamente similares a la consulta. Usa esto para encontrar implementaciones, patrones o documentación relevante sin leer todos los ficheros.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query":  {"type": "string", "description": "Consulta en lenguaje natural o fragmento de código"},
                    "path":   {"type": "string", "description": "Directorio donde buscar (vacío = workspace)"},
                    "top_k":  {"type": "integer", "description": "Número de resultados (defecto: 5)"},
                },
                "required": ["query"],
            },
        },
    ),
]


def on_start(config) -> None:
    from agent.embeddings import EmbeddingClient
    try:
        ec = EmbeddingClient(
            host=config.ollama_host,
            model=config.embed_model,
            max_input_chars=config.embed_max_input_chars,
        )
        _state["embed_client"] = ec
        _state["workspace"]    = config.workspace
    except Exception:
        pass


def on_end() -> None:
    ec = _state.get("embed_client")
    if ec:
        try:
            ec.close()
        except Exception:
            pass
