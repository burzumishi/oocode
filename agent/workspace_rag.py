"""WorkspaceRAG: auto-inyección silenciosa de código relevante en cada turno.

Comparte el índice con el plugin embeddings_search (~/.oocode/search_index/).
Re-indexa en background cada `index_interval` segundos. El agente recibe los
fragmentos más pertinentes en el system prompt sin tener que pedirlos.
"""
import fnmatch
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

import agent.logger as log

_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".c", ".cpp", ".h",
    ".hpp", ".cc", ".java", ".rb", ".php", ".cs", ".swift", ".kt", ".md",
    ".txt", ".sh", ".yaml", ".yml", ".toml", ".json", ".html", ".css", ".sql",
}
_IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    "dist", "build", ".mypy_cache", ".ruff_cache", "target", ".oocode",
    ".pytest_cache", ".tox", "coverage", ".coverage", "htmlcov",
    "logs", "tmp", "temp", ".DS_Store",
}
_IGNORE_FILES = {
    "*.pyc", "*.pyo", "*.pyd", "*.so", "*.dll", "*.exe",
    "*.lock", "package-lock.json", "yarn.lock", "Pipfile.lock", "poetry.lock",
    "*.min.js", "*.min.css", "*.map", "*.egg-info",
}
_MAX_FILE_CHARS = 6000   # chars por fichero antes de chunking
_CHUNK_CHARS    = 512    # chars por chunk (≤512 tokens en casi cualquier modelo)
_CHUNK_OVERLAP  = 64     # solapamiento entre chunks
_MAX_FILES      = 2000

# Map file extensions to markdown fence language names
_EXT_TO_LANG = {
    ".py":    "python",
    ".js":    "javascript",
    ".jsx":   "jsx",
    ".ts":    "typescript",
    ".tsx":   "tsx",
    ".go":    "go",
    ".rs":    "rust",
    ".c":     "c",
    ".cpp":   "cpp",
    ".cc":    "cpp",
    ".h":     "c",
    ".hpp":   "cpp",
    ".java":  "java",
    ".rb":    "ruby",
    ".php":   "php",
    ".cs":    "csharp",
    ".swift": "swift",
    ".kt":    "kotlin",
    ".sh":    "bash",
    ".yaml":  "yaml",
    ".yml":   "yaml",
    ".toml":  "toml",
    ".json":  "json",
    ".html":  "html",
    ".css":   "css",
    ".sql":   "sql",
    ".md":    "markdown",
    ".txt":   "",
}


def _file_is_ignored(filename: str) -> bool:
    """Return True if the filename matches any pattern in _IGNORE_FILES."""
    return any(fnmatch.fnmatch(filename, pat) for pat in _IGNORE_FILES)


class WorkspaceRAG:
    """RAG automático sobre el workspace activo del agente."""

    def __init__(
        self,
        workspace: str,
        embed_client,                        # agent.embeddings.EmbeddingClient
        index_dir: Path,
        top_k: int            = 3,
        similarity_threshold: float = 0.42,
        max_snippet_chars: int = 1400,
        index_interval: float  = 300,        # segundos entre re-indexaciones
    ):
        self._workspace  = Path(workspace).expanduser().resolve()
        self._ec         = embed_client
        self._index_dir  = index_dir / self._workspace.name
        self._top_k      = top_k
        self._threshold  = similarity_threshold
        self._max_chars  = max_snippet_chars
        self._interval   = index_interval
        self._last_index    = 0.0
        self._indexing      = False
        self._files_indexed = 0
        self._last_hits: int      = 0  # fragmentos devueltos en el último context_snippet()
        self._last_available: int = 0  # fragmentos que pasaron el umbral (antes del topK)
        self._data: dict    = {"chunks": [], "mtime": {}}
        self._lock          = threading.Lock()
        self._load_index()

    # ── Propiedades ───────────────────────────────────────────────────────────

    @property
    def last_indexed(self) -> float:
        """Seconds since epoch of the last completed index, or 0.0 if never."""
        return self._last_index

    @property
    def indexed_files(self) -> int:
        """Number of files currently tracked in the index (not chunks)."""
        with self._lock:
            return len(self._data.get("mtime", {}))

    # ── Índice ────────────────────────────────────────────────────────────────

    def _load_index(self) -> None:
        p = self._index_dir / "index.json"
        if p.exists():
            try:
                with self._lock:
                    self._data = json.loads(p.read_text())
                self._last_index = p.stat().st_mtime
            except Exception:
                pass

    def _save_index(self, data: dict) -> None:
        self._index_dir.mkdir(parents=True, exist_ok=True)
        (self._index_dir / "index.json").write_text(
            json.dumps(data, ensure_ascii=False)
        )

    def _do_index(self, incremental: bool = True) -> None:
        """Indexa el workspace. Llamado siempre en hilo daemon."""
        if not self._ec.is_available():
            return
        self._files_indexed = 0
        files_seen = 0
        limit_reached = False
        try:
            with self._lock:
                base: dict[str, Any] = (
                    {"chunks": list(self._data["chunks"]),
                     "mtime":  dict(self._data["mtime"])}
                    if incremental else {"chunks": [], "mtime": {}}
                )
            for dirpath, dirnames, filenames in os.walk(self._workspace):
                if limit_reached:
                    break
                dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]
                for fn in filenames:
                    if files_seen >= _MAX_FILES:
                        log.debug(
                            "workspace_rag_limit_reached",
                            workspace=self._workspace.name,
                            limit=_MAX_FILES,
                        )
                        limit_reached = True
                        break
                    if _file_is_ignored(fn):
                        continue
                    fp = Path(dirpath) / fn
                    if fp.suffix.lower() not in _EXTENSIONS:
                        continue
                    files_seen += 1
                    rel   = str(fp)
                    mtime = str(fp.stat().st_mtime)
                    if incremental and base["mtime"].get(rel) == mtime:
                        continue
                    try:
                        text = fp.read_text(errors="replace")[:_MAX_FILE_CHARS]
                    except Exception:
                        continue
                    base["chunks"] = [c for c in base["chunks"] if c["path"] != rel]
                    for chunk in _chunk_text(text, rel):
                        vec = self._ec.embed(chunk["text"])
                        if vec:
                            chunk["vec"] = vec
                            base["chunks"].append(chunk)
                    base["mtime"][rel] = mtime
                    self._files_indexed += 1

            with self._lock:
                self._data = base
            self._save_index(base)
            self._last_index = time.time()
            log.debug("workspace_rag_indexed",
                      workspace=self._workspace.name,
                      chunks=len(base["chunks"]),
                      files_new=self._files_indexed,
                      files_total=len(base["mtime"]))
        except Exception as exc:
            log.debug("workspace_rag_index_error", error=str(exc))
        finally:
            self._indexing = False

    def ensure_indexed(self) -> None:
        """Dispara re-indexado en background si el índice está vacío o caducado."""
        if self._indexing or not self._ec.is_available():
            return
        with self._lock:
            empty = not self._data.get("chunks")
        age = time.time() - self._last_index
        if empty or age > self._interval:
            self._indexing = True
            threading.Thread(
                target=self._do_index, daemon=True, name="oocode-rag"
            ).start()

    # ── Búsqueda ──────────────────────────────────────────────────────────────

    def query(
        self,
        text: str,
        *,
        top_k: Optional[int] = None,
        threshold: Optional[float] = None,
    ) -> list[tuple[float, dict]]:
        """Busca los chunks más relevantes para `text`.

        `top_k` y `threshold` sobreescriben los valores de instancia para esta
        llamada únicamente — no modifican el estado persistente del objeto.
        """
        if not text.strip() or not self._ec.is_available():
            return []
        q_vec = self._ec.embed(text[:1200])
        if not q_vec:
            return []
        _top_k     = top_k     if top_k     is not None else self._top_k
        _threshold = threshold if threshold is not None else self._threshold
        with self._lock:
            chunks = list(self._data.get("chunks", []))
        scored = [
            (self._ec.similarity(q_vec, c.get("vec", [])), c)
            for c in chunks if c.get("vec")
        ]
        scored = [(s, c) for s, c in scored if s >= _threshold]
        scored.sort(key=lambda x: x[0], reverse=True)
        self._last_available = len(scored)   # cuántos pasaron el umbral
        return scored[:_top_k]

    @property
    def last_hits(self) -> int:
        """Fragmentos inyectados en el último turno (para el spinner)."""
        return self._last_hits

    @property
    def last_available(self) -> int:
        """Fragmentos que pasaron el umbral de similitud en el último query (antes del topK)."""
        return self._last_available

    def context_snippet(
        self,
        query: str,
        *,
        top_k: Optional[int] = None,
        threshold: Optional[float] = None,
    ) -> str:
        """Fragmentos de código relevantes listos para inyectar en el system prompt.

        `top_k` y `threshold` permiten overrides por turno sin cambiar el estado
        persistente — útil para boost en queries complejas o de autoedición.
        """
        results = self.query(query, top_k=top_k, threshold=threshold)
        self._last_hits = len(results)
        if not results:
            return ""
        slot = max(200, self._max_chars // max(len(results), 1))
        parts = []
        for sim, chunk in results:
            full_path = chunk["path"]
            filename  = Path(full_path).name
            ext       = Path(full_path).suffix.lower()
            lang      = _EXT_TO_LANG.get(ext, "")
            lno       = chunk.get("line", "?")
            text      = chunk["text"][:slot]
            header    = f"// {filename}:{lno}  (relevancia {sim:.2f})"
            parts.append(f"{header}\n```{lang}\n{text}\n```")
        joined = "\n\n---\n".join(parts)
        return f"## Código relevante del proyecto\n{joined}\n"

    def invalidate_file(self, path: str) -> None:
        """Marca un fichero como modificado para forzar su re-indexado.

        Elimina el fichero del mtime cache y sus chunks del índice actual.
        En el próximo ensure_indexed() / _do_index() el fichero se re-indexará
        incluso si el índice se actualizó hace menos de index_interval segundos.
        """
        abs_path = str(Path(path).resolve())
        with self._lock:
            if abs_path in self._data.get("mtime", {}):
                del self._data["mtime"][abs_path]
            self._data["chunks"] = [
                c for c in self._data.get("chunks", [])
                if c.get("path") != abs_path
            ]
        # Forzar re-indexado inmediato (reset del timestamp)
        self._last_index = 0.0

    def update_config(self, *, top_k: Optional[int] = None,
                      similarity_threshold: Optional[float] = None,
                      max_snippet_chars: Optional[int] = None,
                      index_interval: Optional[float] = None) -> None:
        """Actualiza parámetros del RAG en caliente sin reiniciar."""
        if top_k is not None:
            self._top_k = top_k
        if similarity_threshold is not None:
            self._threshold = similarity_threshold
        if max_snippet_chars is not None:
            self._max_chars = max_snippet_chars
        if index_interval is not None:
            self._interval = index_interval

    @property
    def index_size(self) -> int:
        with self._lock:
            return len(self._data.get("chunks", []))



    def chunk_with_metadata(self, text: str, path: str, 
                           use_intelligent: bool = True) -> list[dict]:
        """Chunking con metadata enriquecida.
        
        Args:
            text: Texto del fichero
            path: Ruta del fichero
            use_intelligent: Usar chunking inteligente (default: True)
        
        Returns:
            Lista de chunks con metadata enriquecida
        """
        chunks = []
        
        if use_intelligent:
            chunks = _chunk_code_intelligently(text, path)
        else:
            chunks = _chunk_text(text, path)
        
        # Enriquecer metadata de todos los chunks
        for chunk in chunks:
            chunk = _enrich_metadata(chunk, path)
        
        return chunks

# ── Helpers ───────────────────────────────────────────────────────────────────

def _chunk_text(text: str, path: str) -> list[dict]:
    lines  = text.splitlines(keepends=True)
    chunks = []
    buf    = ""
    start  = 0
    for i, line in enumerate(lines):
        buf += line
        if len(buf) >= _CHUNK_CHARS:
            chunks.append({"path": path, "line": start + 1, "text": buf.strip()})
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

def _chunk_code_intelligently(text: str, path: str) -> list[dict]:
    """Chunking respetando estructura de código (funciones, clases)."""
    import re
    
    chunks = []
    current_chunk = {"path": path, "line": 1, "text": "", "function": None, "class": None}
    
    func_pattern = r'^(\s*)def\s+(\w+)\s*\('
    class_pattern = r'^(\s*)class\s+(\w+)'
    
    lines = text.splitlines(keepends=True)
    current_chunk["text"] = ""
    current_chunk["line"] = 1
    
    for i, line in enumerate(lines):
        current_chunk["text"] += line
        
        func_match = re.match(func_pattern, line)
        if func_match:
            current_chunk["function"] = func_match.group(2)
        
        class_match = re.match(class_pattern, line)
        if class_match:
            current_chunk["class"] = class_match.group(2)
        
        if len(current_chunk["text"]) >= 512:
            if current_chunk["text"].strip():
                chunks.append(current_chunk)
            overlap = ""
            for j in range(i, max(-1, i - 3), -1):
                overlap = lines[j] + overlap
                if len(overlap) >= 64:
                    break
            current_chunk = {"path": path, "line": i + 1, "text": overlap, 
                          "function": current_chunk.get("function"),
                          "class": current_chunk.get("class")}
    
    if current_chunk["text"].strip():
        chunks.append(current_chunk)
    
    return chunks


def _enrich_metadata(chunk: dict, path: str) -> dict:
    """Enriquece metadata del chunk."""
    from pathlib import Path
    
    enriched = dict(chunk)
    ext = Path(path).suffix.lower()
    enriched["file_type"] = ext
    
    lines = chunk["text"].count("\n") + 1
    enriched["complexity"] = lines
    
    text_lower = chunk["text"].lower()
    keywords = []
    if "def " in text_lower:
        keywords.append("function")
    if "class " in text_lower:
        keywords.append("class")
    if "import " in text_lower:
        keywords.append("import")
    if "#" in text_lower:
        keywords.append("comment")
    if "if " in text_lower and "else" in text_lower:
        keywords.append("conditional")
    if "for " in text_lower or "while " in text_lower:
        keywords.append("loop")
    
    enriched["tags"] = keywords
    
    return enriched


def _fallback_index_chunk(chunk: dict) -> dict:
    """Fallback: indexar chunk sin embeddings (por hash de texto)."""
    import hashlib
    
    text_hash = hashlib.md5(chunk["text"].encode()).hexdigest()[:12]
    chunk["fallback_hash"] = text_hash
    chunk["index_type"] = "fallback"
    
    return chunk


def chunk_with_metadata(self, text: str, path: str, 
                       use_intelligent: bool = True) -> list[dict]:
    """Chunking con metadata enriquecida."""
    chunks = []
    
    if use_intelligent:
        chunks = _chunk_code_intelligently(text, path)
    else:
        chunks = _chunk_text(text, path)
    
    for chunk in chunks:
        chunk = _enrich_metadata(chunk, path)
    
    return chunks

