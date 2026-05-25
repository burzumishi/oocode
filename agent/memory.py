"""MemorySystem con búsqueda semántica vía embeddings.

Optimizaciones:
- Solo embede la query si hay ficheros de memoria que comparar.
- Cachea el último vector de query (evita re-embedar la misma pregunta).
- Cachea vectores de memoria en RAM (evita disco en búsquedas repetidas).
- Cachea la lista de ficheros de memoria con TTL de 5 s.
"""
import re
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING
from config import MEMORY_DIR
import agent.logger as log

if TYPE_CHECKING:
    from agent.embeddings import EmbeddingClient

_FILE_LIST_TTL = 5.0   # segundos entre re-escaneados del directorio


class MemorySystem:
    def __init__(
        self,
        embed_client: Optional["EmbeddingClient"] = None,
        similarity_threshold: float = 0.30,
        snippet_chars: int = 400,
        top_k: int = 3,
        memory_dir: Optional[Path] = None,
    ):
        self._dir       = (memory_dir if memory_dir is not None else MEMORY_DIR)
        self._index     = self._dir / "MEMORY.md"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._embed     = embed_client
        self._threshold = similarity_threshold
        self._snippet_chars = snippet_chars
        self._top_k     = top_k

        # Caché de lista de ficheros (evita glob en cada búsqueda)
        self._file_list: list[Path] = []
        self._file_list_ts: float   = 0.0

        # Caché del último vector de query
        self._last_query:     str        = ""
        self._last_query_vec: list[float] = []

        # Caché de vectores de memorias en RAM: path.name → vector
        self._vec_cache: dict[str, list[float]] = {}

        # Resultados del último context_snippet() — leído por loop.py para el indicador TUI
        self.last_hits: int = 0

    def reset_turn_cache(self) -> None:
        """Limpia el vector de query cacheado para forzar re-embed en el nuevo turno.

        Llamar al inicio de cada run() para que cada mensaje de usuario genere
        exactamente una llamada a embed (no más por iteraciones de tools, no menos
        por cache cross-turn de la misma query repetida entre turnos).
        """
        self._last_query     = ""
        self._last_query_vec = []
        self.last_hits       = 0

    # ── Lectura ──────────────────────────────────────────────────────────────

    def read_index(self) -> str:
        if self._index.exists():
            return self._index.read_text()
        return "# Memory Index\n\n(Sin recuerdos guardados todavía)"

    def load(self, name: str) -> str:
        slug = _slugify(name)
        path = self._dir / slug
        if path.exists():
            return path.read_text()
        return f"Memoria '{name}' no encontrada."

    def list_all(self) -> list[str]:
        return [p.name for p in self._dir.glob("*.md") if p.name != "MEMORY.md"]

    def has_memories(self) -> bool:
        """Comprueba si hay al menos un fichero de memoria (excepto MEMORY.md)."""
        return bool(self._get_memory_files())

    # ── Escritura ─────────────────────────────────────────────────────────────

    def save(self, name: str, content: str, description: str = "") -> str:
        slug = _slugify(name)
        path = self._dir / slug
        path.write_text(content)
        self._update_index(slug, description or name)
        # Invalidar caché de ficheros para que aparezca en próximas búsquedas
        self._file_list_ts = 0.0
        # Calcular y guardar embedding para búsquedas futuras
        if self._embed and self._embed.is_available():
            from agent.embeddings import save_embedding
            vector = self._embed.embed(content)
            if vector:
                save_embedding(path.with_suffix(".emb.json"), vector)
                self._vec_cache[path.name] = vector   # actualizar caché RAM
        return f"Memoria guardada: {path}"

    # ── Ficheros de memoria (con caché TTL) ───────────────────────────────────

    def _get_memory_files(self) -> list[Path]:
        """Lista de .md (sin MEMORY.md), con caché de 5 s."""
        now = time.monotonic()
        if (now - self._file_list_ts) >= _FILE_LIST_TTL:
            self._file_list    = [p for p in self._dir.glob("*.md")
                                  if p.name != "MEMORY.md"]
            self._file_list_ts = now
        return self._file_list

    # ── Búsqueda semántica ────────────────────────────────────────────────────

    def search(self, query: str, top_k: Optional[int] = None) -> list[tuple[float, str, str]]:
        """Busca memorias relevantes por similitud semántica.

        Devuelve lista de (score, slug, snippet) ordenada por relevancia.
        Solo llama al modelo de embeddings si hay ficheros de memoria.
        """
        if not self._embed or not self._embed.is_available():
            log.debug("embed_search_skip",
                      reason="no_embed_client" if not self._embed else "unavailable")
            return []

        mem_files = self._get_memory_files()
        if not mem_files:
            log.debug("embed_search_skip", reason="no_memory_files")
            return []

        # Reutilizar vector de query si la pregunta no ha cambiado
        if query == self._last_query and self._last_query_vec:
            query_vec = self._last_query_vec
            log.debug("embed_query_cache_hit", chars=len(query))
        else:
            query_vec = self._embed.embed(query)
            if not query_vec:
                log.debug("embed_search_empty_vec", query_chars=len(query))
                return []
            self._last_query     = query
            self._last_query_vec = query_vec

        k = top_k if top_k is not None else self._top_k
        from agent.embeddings import load_embedding, save_embedding

        results: list[tuple[float, str, str]] = []
        for md_path in mem_files:
            # 1) Caché RAM
            vec = self._vec_cache.get(md_path.name)
            if vec is None:
                # 2) Fichero .emb.json
                emb_path = md_path.with_suffix(".emb.json")
                if emb_path.exists():
                    vec = load_embedding(emb_path)
                # 3) Calcular y guardar si aún no existe
                if not vec:
                    try:
                        content = md_path.read_text()
                        vec = self._embed.embed(content)
                        if vec:
                            save_embedding(emb_path, vec)
                    except Exception:
                        continue
            if not vec:
                continue
            # Actualizar caché RAM
            self._vec_cache[md_path.name] = vec

            score = self._embed.similarity(query_vec, vec)
            if score >= self._threshold:
                try:
                    raw = md_path.read_text()
                    snippet = _extract_body(raw, self._snippet_chars)
                    results.append((score, md_path.name, snippet))
                except Exception:
                    pass

        results.sort(key=lambda x: x[0], reverse=True)
        results = results[:k]
        if results:
            log.info("memory_search_hits",
                     hits=len(results),
                     top_score=round(results[0][0], 2),
                     query_chars=len(query))
        return results

    def context_snippet(self, query: str = "") -> str:
        """Bloque de memoria para el system prompt.

        Si hay query y embeddings disponibles, usa búsqueda semántica.
        Si no, devuelve el índice MEMORY.md plano.
        """
        if query and self._embed and self._embed.is_available() and self.has_memories():
            hits = self.search(query)
            self.last_hits = len(hits)
            if hits:
                lines = ["## Memorias relevantes"]
                for score, slug, snippet in hits:
                    lines.append(f"\n### {slug} ({score:.2f})")
                    lines.append(snippet)
                return "\n".join(lines)
        self.last_hits = 0
        # Fallback al índice plano
        index = self.read_index()
        if not index.strip() or "Sin recuerdos" in index:
            return ""
        return f"\n\n## Memoria persistente\n{index}"

    def _auto_suggest_memories(self, current_query: str) -> list[str]:
        """Sugiere memorias relevantes automáticamente basándose en el query actual.

        Analiza el query para detectar patrones y sugiere memorias relacionadas.
        Útil para auto-generación de memoria similar a Claude Code.
        """
        if not self._embed or not self._embed.is_available():
            return []

        # Detectar patrones en el query
        patterns = [
            (r"(TODO|FIXME|HACK|BUG|XXX)", "task_management"),
            (r"(configuración|config|setup)", "configuration"),
            (r"(docker|container|compose)", "docker"),
            (r"(git|commit|push|pull)", "git_workflow"),
            (r"(error|exception|bug|fail)", "error_handling"),
            (r"(test|pytest|unittest)", "testing"),
            (r"(lsp|clangd|pylsp)", "lsp_integration"),
            (r"(mcp|model context protocol)", "mcp_servers"),
        ]

        suggestions = []
        for pattern, slug in patterns:
            if re.search(pattern, current_query, re.IGNORECASE):
                # Buscar memoria relacionada
                query = f"{slug} memory"
                hits = self.search(query, top_k=1)
                if hits:
                    score, slug, snippet = hits[0]
                    suggestions.append(f"\n### Sugerencia: {slug}\n{snippet}")

        return suggestions

    # ── Índice ────────────────────────────────────────────────────────────────

    def _update_index(self, slug: str, description: str) -> None:
        lines: list[str] = []
        if self._index.exists():
            lines = self._index.read_text().splitlines()
        entry = f"- [{slug}]({slug}) — {description}"
        updated = False
        for i, line in enumerate(lines):
            if f"]({slug})" in line:
                lines[i] = entry
                updated = True
                break
        if not updated:
            if not lines:
                lines = ["# Memory Index", ""]
            lines.append(entry)
        self._index.write_text("\n".join(lines))


def _slugify(name: str) -> str:
    slug = name.lower().replace(" ", "_").replace("/", "_")
    return slug if slug.endswith(".md") else slug + ".md"


def _extract_body(text: str, max_chars: int) -> str:
    """Devuelve el cuerpo de un fichero de memoria sin el frontmatter YAML.

    Los ficheros tienen frontmatter delimitado por '---'. Salta hasta el segundo
    '---' y devuelve el contenido que sigue, truncado a max_chars.
    Si no hay frontmatter, devuelve el texto directamente.
    """
    if text.startswith("---"):
        # Buscar el cierre del frontmatter (segunda línea que empieza con '---')
        second = text.find("\n---", 3)
        if second != -1:
            body = text[second + 4:].lstrip("\n")
            return body[:max_chars].strip()
    return text[:max_chars].strip()
