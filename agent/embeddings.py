"""Cliente de embeddings vía Ollama con caché LRU en RAM y caché SQLite en disco."""
import hashlib
import math
import struct
import sqlite3
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Optional
import ollama
import agent.logger as log

_RAM_CACHE_MAX = 256   # fallback si se crea EmbeddingClient sin config
_COOLDOWN_SECS = 60    # segundos sin reintentar tras un fallo

_CTX_LEN_PHRASES = (
    "input length exceeds",
    "context length",
    "exceeds the maximum",
    "too many tokens",
    "prompt is too long",
)

def _is_ctx_overflow(exc: Exception) -> bool:
    return any(p in str(exc).lower() for p in _CTX_LEN_PHRASES)


# ── Caché de disco ─────────────────────────────────────────────────────────────

class _DiskCache:
    """Caché SQLite de vectores de embedding.

    - Archivo único por modelo: {cache_dir}/{model_slug}.db
    - Almacenamiento binario float64 (struct.pack) — ~50 % menos que JSON
    - WAL mode: múltiples conexiones (main + subagentes) leen en paralelo
    - threading.Lock: serializa accesos desde distintos hilos a esta conexión
    - Eviction LRU por columna `seen` (UPDATE en cada GET, DELETE al superar límite)
    """

    def __init__(self, db_path: Path, max_entries: int) -> None:
        self._path = db_path
        self._max  = max_entries
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS embeddings (
                key  TEXT PRIMARY KEY,
                vec  BLOB NOT NULL,
                seen REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_seen ON embeddings(seen);
        """)
        self._conn.commit()
        log.debug("embed_disk_cache_init", path=str(db_path), max=max_entries)

    # ── Serialización ──────────────────────────────────────────────────────────

    @staticmethod
    def _pack(vec: list[float]) -> bytes:
        """Float64 binario — round-trip exacto, ~50 % del tamaño de JSON."""
        return struct.pack(f"{len(vec)}d", *vec)

    @staticmethod
    def _unpack(blob: bytes) -> list[float]:
        n = len(blob) // 8   # 8 bytes por double
        return list(struct.unpack(f"{n}d", blob))

    # ── Operaciones ────────────────────────────────────────────────────────────

    def get(self, key: str) -> Optional[list[float]]:
        with self._lock:
            try:
                row = self._conn.execute(
                    "SELECT vec FROM embeddings WHERE key=?", (key,)
                ).fetchone()
                if row is None:
                    return None
                # Actualizar timestamp para mantener orden LRU
                self._conn.execute(
                    "UPDATE embeddings SET seen=? WHERE key=?", (time.time(), key)
                )
                self._conn.commit()
                log.debug("embed_disk_hit", key=key[:8])
                return self._unpack(row[0])
            except Exception as exc:
                log.debug("embed_disk_get_error", error=str(exc))
                return None

    def put(self, key: str, vec: list[float]) -> None:
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT OR REPLACE INTO embeddings (key, vec, seen) VALUES (?,?,?)",
                    (key, self._pack(vec), time.time()),
                )
                # Evictar entradas más antiguas si superamos el límite
                count = self._conn.execute(
                    "SELECT COUNT(*) FROM embeddings"
                ).fetchone()[0]
                if count > self._max:
                    excess = count - self._max
                    self._conn.execute(
                        "DELETE FROM embeddings WHERE key IN "
                        "(SELECT key FROM embeddings ORDER BY seen ASC LIMIT ?)",
                        (excess,),
                    )
                    log.debug("embed_disk_evict", deleted=excess)
                self._conn.commit()
                log.debug("embed_disk_put", key=key[:8])
            except Exception as exc:
                log.debug("embed_disk_put_error", error=str(exc))

    def count(self) -> int:
        with self._lock:
            try:
                return self._conn.execute(
                    "SELECT COUNT(*) FROM embeddings"
                ).fetchone()[0]
            except Exception:
                return -1

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass


# ── EmbeddingClient ────────────────────────────────────────────────────────────

class EmbeddingClient:
    def __init__(
        self,
        host: str,
        model: str,
        max_input_chars: int = 8000,
        disk_cache_enabled: bool = False,
        disk_cache_dir: str = "~/.oocode/cache",
        disk_cache_max: int = 2000,
        ram_cache_max: int = _RAM_CACHE_MAX,
    ):
        self._host          = host
        self._model         = model
        self._max_chars     = max_input_chars
        self._ram_cache_max = ram_cache_max
        self._client    = ollama.Client(host=host)
        self._available: Optional[bool] = None
        self._fail_at:   float = 0.0
        self._use_legacy = not callable(getattr(self._client, "embed", None))
        # Caché LRU en RAM
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        # Caché de disco (SQLite)
        self._disk_cache: Optional[_DiskCache] = None
        if disk_cache_enabled and disk_cache_dir:
            slug = model.replace("/", "_").replace(":", "_")
            base = Path(disk_cache_dir).expanduser()
            try:
                base.mkdir(parents=True, exist_ok=True)
                self._disk_cache = _DiskCache(base / f"{slug}.db", disk_cache_max)
            except Exception as exc:
                log.debug("embed_disk_cache_init_error", error=str(exc))

    # ── Caché RAM (LRU) ───────────────────────────────────────────────────────

    def _cache_key(self, text: str) -> str:
        return hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()

    def _cache_get(self, key: str) -> Optional[list[float]]:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def _cache_put(self, key: str, vec: list[float]) -> None:
        if len(self._cache) >= self._ram_cache_max:
            self._cache.popitem(last=False)
        self._cache[key] = vec

    # ── Caché de disco (wrappers) ─────────────────────────────────────────────

    def _disk_get(self, key: str) -> Optional[list[float]]:
        if self._disk_cache is None:
            return None
        return self._disk_cache.get(key)

    def _disk_put(self, key: str, vec: list[float]) -> None:
        if self._disk_cache is not None:
            self._disk_cache.put(key, vec)

    def disk_cache_stats(self) -> dict:
        if self._disk_cache is None:
            return {"enabled": False}
        return {
            "enabled": True,
            "entries": self._disk_cache.count(),
            "max":     self._disk_cache._max,
            "path":    str(self._disk_cache._path),
        }

    # ── Disponibilidad ────────────────────────────────────────────────────────

    def is_available(self) -> bool:
        if not self._model:
            return False
        if self._available is False:
            return (time.time() - self._fail_at) >= _COOLDOWN_SECS
        return True

    def _mark_failure(self) -> None:
        self._available = False
        self._fail_at   = time.time()

    def _mark_success(self) -> None:
        self._available = True

    # ── Embedding ─────────────────────────────────────────────────────────────

    def _call_api(self, input_text: str) -> list[float]:
        if not self._use_legacy:
            resp = self._client.embed(model=self._model, input=input_text)
            vecs = getattr(resp, "embeddings", None) or []
            return list(vecs[0]) if vecs else []
        else:
            resp = self._client.embeddings(model=self._model, prompt=input_text)  # type: ignore[assignment]
            raw: dict = resp if isinstance(resp, dict) else {}
            return list(raw.get("embedding", []))

    def embed(self, text: str) -> list[float]:
        """Devuelve vector de embedding o [] si hay error/cooldown.

        Orden: RAM LRU → SQLite disco → API Ollama.
        Persiste en disco y calienta RAM tras cada llamada a la API.
        """
        if not text.strip() or not self.is_available():
            return []

        input_text = text[:self._max_chars]
        key = self._cache_key(input_text)

        # 1. Caché RAM
        cached = self._cache_get(key)
        if cached is not None:
            log.debug("embed_ram_hit", chars=len(input_text))
            return cached

        # 2. Caché de disco
        disk_vec = self._disk_get(key)
        if disk_vec is not None:
            self._cache_put(key, disk_vec)   # calentar RAM
            return disk_vec

        log.debug("embed_attempt", model=self._model, chars=len(input_text),
                  legacy=self._use_legacy)

        # 3. API Ollama con retry progresivo por overflow de contexto
        attempt_text = input_text
        for attempt in range(4):  # 100 % → 50 % → 25 % → 12 %
            try:
                vec = self._call_api(attempt_text)
                if not vec:
                    log.debug("embed_empty_vec", model=self._model, attempt=attempt)
                    return []
                self._mark_success()
                self._cache_put(key, vec)
                self._disk_put(key, vec)   # persistir en disco
                if attempt > 0:
                    self._max_chars = min(self._max_chars, len(attempt_text))
                    log.debug("embed_ctx_reduced",
                              model=self._model, new_max=self._max_chars)
                log.debug("embed_ok", model=self._model, dims=len(vec), attempt=attempt)
                return vec

            except AttributeError:
                if not self._use_legacy:
                    self._use_legacy = True
                    log.debug("embed_fallback_legacy", model=self._model)
                    return self.embed(text)
                self._mark_failure()
                return []

            except Exception as exc:
                if _is_ctx_overflow(exc):
                    new_len = max(len(attempt_text) // 2, 64)
                    log.debug("embed_ctx_overflow_retry",
                              model=self._model, attempt=attempt,
                              chars_before=len(attempt_text), chars_after=new_len,
                              error=str(exc)[:120])
                    if new_len < 64:
                        break
                    attempt_text = attempt_text[:new_len]
                    continue
                log.debug("embed_error", model=self._model, error=str(exc))
                self._mark_failure()
                return []

        log.debug("embed_ctx_overflow_give_up", model=self._model)
        return []

    # ── Utilidades ─────────────────────────────────────────────────────────────

    def similarity(self, a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na  = math.sqrt(sum(x * x for x in a))
        nb  = math.sqrt(sum(y * y for y in b))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return dot / (na * nb)

    def cache_stats(self) -> dict:
        return {
            "ram_size": len(self._cache),
            "ram_max":  self._ram_cache_max,
            "available": self._available,
            "model":    self._model,
            "disk":     self.disk_cache_stats(),
        }

    def close(self) -> None:
        if self._disk_cache is not None:
            self._disk_cache.close()


def save_embedding(path: Path, vector: list[float]) -> None:
    import json
    path.write_text(json.dumps(vector))


def load_embedding(path: Path) -> list[float]:
    import json
    try:
        return json.loads(path.read_text())
    except Exception:
        return []
