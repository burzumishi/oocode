"""Cliente de embeddings vía Ollama con caché LRU y cooldown tras fallos."""
import hashlib
import math
import json
import time
from collections import OrderedDict
from pathlib import Path
from typing import Optional
import ollama
import agent.logger as log

_CACHE_MAX     = 256   # vectores en RAM (query + memoria)
_COOLDOWN_SECS = 60    # segundos sin reintentar tras un fallo

# Errores de longitud de contexto — no son fallos permanentes: reintentar con menos texto
_CTX_LEN_PHRASES = (
    "input length exceeds",
    "context length",
    "exceeds the maximum",
    "too many tokens",
    "prompt is too long",
)

def _is_ctx_overflow(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(p in msg for p in _CTX_LEN_PHRASES)


class EmbeddingClient:
    def __init__(
        self,
        host: str,
        model: str = "nomic-embed-text-v2-moe:latest",
        max_input_chars: int = 2048,
    ):
        self._host      = host
        self._model     = model
        # Límite conservador: la mayoría de modelos BERT-based soportan ≤512 tokens.
        # Con un peor caso de 1 char/token, 2048 chars caben en casi cualquier modelo.
        self._max_chars = max_input_chars
        self._client    = ollama.Client(host=host)
        # Estado de disponibilidad: None=desconocido, True=ok, False=fallo reciente
        self._available: Optional[bool] = None
        self._fail_at:   float = 0.0          # timestamp del último fallo
        # Detectar qué método usar: 'embed' (ollama >= 0.4) o 'embeddings' (legacy)
        self._use_legacy = not callable(getattr(self._client, "embed", None))
        # Caché LRU: hash(texto) → vector
        self._cache: OrderedDict[str, list[float]] = OrderedDict()

    # ── Caché ────────────────────────────────────────────────────────────────

    def _cache_key(self, text: str) -> str:
        return hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()

    def _cache_get(self, key: str) -> Optional[list[float]]:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def _cache_put(self, key: str, vec: list[float]) -> None:
        if len(self._cache) >= _CACHE_MAX:
            self._cache.popitem(last=False)  # evicta el más antiguo
        self._cache[key] = vec

    # ── Disponibilidad ────────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """True si el modelo está configurado y no ha fallado recientemente."""
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
        """Llamada directa a la API de embeddings; lanza excepción si falla."""
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

        Si el servidor rechaza la entrada por exceder el contexto del modelo,
        reintenta con la mitad del texto hasta 3 veces antes de rendirse.
        No activa el cooldown en errores de longitud (son recuperables).
        """
        if not text.strip() or not self.is_available():
            return []

        input_text = text[:self._max_chars]
        key = self._cache_key(input_text)

        # Cache hit — evita llamada a red
        cached = self._cache_get(key)
        if cached is not None:
            log.debug("embed_cache_hit", chars=len(input_text))
            return cached

        log.debug("embed_attempt", model=self._model, chars=len(input_text),
                  legacy=self._use_legacy)

        # Retry progresivo: si el modelo rechaza por contexto, reducir a la mitad
        attempt_text = input_text
        for attempt in range(4):  # máx 4 intentos: 100% → 50% → 25% → 12%
            try:
                vec = self._call_api(attempt_text)
                if not vec:
                    log.debug("embed_empty_vec", model=self._model, attempt=attempt)
                    return []
                self._mark_success()
                # Cachear con la key del texto original truncado (no el reducido)
                self._cache_put(key, vec)
                if attempt > 0:
                    # Actualizar _max_chars para futuras llamadas (aprendizaje)
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
                    # Reducir texto a la mitad y reintentar (no marcar fallo)
                    new_len = max(len(attempt_text) // 2, 64)
                    log.debug("embed_ctx_overflow_retry",
                              model=self._model,
                              attempt=attempt,
                              chars_before=len(attempt_text),
                              chars_after=new_len,
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

    # ── Similitud ─────────────────────────────────────────────────────────────

    def similarity(self, a: list[float], b: list[float]) -> float:
        """Similitud coseno entre dos vectores."""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na  = math.sqrt(sum(x * x for x in a))
        nb  = math.sqrt(sum(y * y for y in b))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return dot / (na * nb)

    def cache_stats(self) -> dict:
        return {"size": len(self._cache), "max": _CACHE_MAX,
                "available": self._available, "model": self._model}

    def close(self) -> None:
        try:
            return True
            #self._client.close()
        except Exception:
            pass


def save_embedding(path: Path, vector: list[float]) -> None:
    path.write_text(json.dumps(vector))


def load_embedding(path: Path) -> list[float]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return []
