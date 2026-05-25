"""ConversationContext: historial + compactación con resumen LLM."""
import json
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

# Configuración de prompt caching
from config import DEFAULT_CONFIG as CONFIG

# Cargar desde configuración con valores por defecto
_CHARS_PER_TOKEN = CONFIG.get("chars_per_token", 3.0)
_PROMPT_CACHE_DIR = CONFIG.get("cache_dir", "~/.oocode/cache")
_CACHE_TTL = CONFIG.get("cache_ttl", 300)
_PROMPT_CACHE_ENABLED = CONFIG.get("prompt_cache_enabled", True)
_CONTEXT_WINDOW_CONFIGURABLE = CONFIG.get("context_window_configurable", True)
_CONTEXT_WINDOW_DEFAULT = CONFIG.get("context_window_default", 262144)
_CONTEXT_WINDOW_MIN = CONFIG.get("context_window_min", 8192)
_CONTEXT_WINDOW_MAX = CONFIG.get("context_window_max", 262144)


def _cache_key(msg: dict) -> str:
    """Genera una clave única para un prompt."""
    content = msg.get("content", "")
    return f"{msg.get('role', '')}:{content[:100]}..."[:200]


def _load_cached_prompt(key: str, msg: dict) -> Optional[str]:
    """Carga un prompt cacheado."""
    try:
        import hashlib
        from pathlib import Path
        
        content = msg.get("content", "")
        cache_dir = Path(_PROMPT_CACHE_DIR)
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Hash del contenido para evitar colisiones
        content_hash = hashlib.md5(content.encode()).hexdigest()[:16]
        path = cache_dir / f"{key}_{content_hash}.txt"
        
        if path.exists():
            mtime = path.stat().st_mtime
            now = time.time()
            if now - mtime < _CACHE_TTL:
                return path.read_text()
    except Exception:
        pass
    return None


def _save_cached_prompt(key: str, content: str) -> None:
    """Guarda un prompt en caché."""
    try:
        import hashlib
        from pathlib import Path
        
        cache_dir = Path(_PROMPT_CACHE_DIR)
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        content_hash = hashlib.md5(content.encode()).hexdigest()[:16]
        path = cache_dir / f"{key}_{content_hash}.txt"
        path.write_text(content)
    except Exception:
        pass


@dataclass
class ConversationContext:
    max_tokens:        int   = 8000
    min_keep:          int   = 12     # mensajes mínimos a conservar (aumentado de 6)
    compact_threshold: float = 0.80   # fracción del límite para auto-compact (bajado de 0.85)
    max_summary_chars: int   = 4000   # chars máximos del resumen acumulado (aumentado de 2100)

    messages: list[dict] = field(default_factory=list)
    summary:  str        = ""        # resumen de msgs compactados, inyectado en el prompt

    # ── Cache de token_estimate para no re-escanear mensajes en cada render ──
    _token_cache:  int  = field(default=0,    init=False, repr=False)
    _token_dirty:  bool = field(default=True, init=False, repr=False)

    def _invalidate_token_cache(self) -> None:
        self._token_dirty = True

    # ── API pública ──────────────────────────────────────────────────────────

    def add(self, role: str, content: str,
            images: Optional[list[str]] = None) -> None:
        msg: dict = {"role": role, "content": content}
        if images:
            msg["images"] = images
        self.messages.append(msg)
        self._invalidate_token_cache()

    def add_tool_result(self, tool_call_id: str, name: str, content: str) -> None:
        self.messages.append({
            "role":         "tool",
            "tool_call_id": tool_call_id,
            "name":         name,
            "content":      content,
        })
        self._invalidate_token_cache()

    def clear(self) -> None:
        self.messages.clear()
        self.summary = ""
        self._invalidate_token_cache()

    def token_estimate(self) -> int:
        if self._token_dirty:
            total_chars = sum(_msg_chars(m) for m in self.messages)
            self._token_cache = int(total_chars / _CHARS_PER_TOKEN)
            self._token_dirty = False
        return self._token_cache

    def should_compact(self) -> bool:
        return self.token_estimate() > int(self.max_tokens * self.compact_threshold)

    def _safe_split_index(self, target: int) -> int:
        """Devuelve el índice de corte seguro para no partir pares tool-call/resultado.

        Ajusta `target` hacia adelante hasta encontrar un punto donde:
        - El primer mensaje conservado no es un resultado de tool huérfano
        - El mensaje anterior al corte no es un assistant con tool_calls pendientes

        Si no hay punto seguro con al menos 1 mensaje, devuelve 0 (no compactar).
        """
        n = len(self.messages)
        idx = max(0, min(target, n - 1))

        for _attempt in range(n):
            if idx >= n:
                return 0
            msg = self.messages[idx]
            role = msg.get("role", "")

            # No empezar en un mensaje 'tool' (sería huérfano sin su assistant)
            if role == "tool":
                idx += 1
                continue

            # No empezar justo después de un assistant con tool_calls sin resolver
            if idx > 0:
                prev = self.messages[idx - 1]
                if prev.get("role") == "assistant" and prev.get("tool_calls"):
                    idx += 1
                    continue

            return idx

        return 0  # No se encontró punto seguro — no compactar

    def compact(self, summarize_fn: Optional[Callable[[list[dict]], str]] = None) -> list[dict]:
        """Elimina mensajes antiguos conservando los `min_keep` más recientes.

        El punto de corte se ajusta para no partir pares assistant-tool_call/tool-result.
        Si se proporciona summarize_fn, resume los eliminados y acumula en self.summary.
        Devuelve la lista de mensajes eliminados.
        """
        n = len(self.messages)
        if n <= self.min_keep:
            return []

        target = n - self.min_keep
        split  = self._safe_split_index(target)
        if split <= 0:
            return []

        dropped          = self.messages[:split]
        self.messages    = self.messages[split:]
        self._invalidate_token_cache()

        if summarize_fn and dropped:
            try:
                new_summary = summarize_fn(dropped)
                if new_summary:
                    self.summary = (
                        f"{self.summary}\n\n{new_summary}" if self.summary else new_summary
                    )
                    if len(self.summary) > self.max_summary_chars:
                        # Truncar preservando el principio (tarea original) y el final (más reciente)
                        half = self.max_summary_chars // 2
                        self.summary = (
                            self.summary[:half]
                            + "\n…[resumen intermedio omitido]…\n"
                            + self.summary[-half:]
                        )
            except Exception:
                pass

        # Segunda pasada: si el contexto sigue muy lleno (>70%) tras soltar los mensajes antiguos,
        # truncar resultados de tools muy largos en los mensajes conservados. Esto libera espacio
        # cuando los ficheros leídos/escritos más recientes dominan el contexto.
        _high_water = int(self.max_tokens * 0.70)
        if self.token_estimate() > _high_water:
            _MAX_TOOL_CHARS = 3000   # conservar los primeros 2500 + marcador + últimos 300
            _KEEP_HEAD = 2500
            _KEEP_TAIL = 300
            for msg in self.messages:
                if msg.get("role") != "tool":
                    continue
                content = msg.get("content", "")
                if not isinstance(content, str) or len(content) <= _MAX_TOOL_CHARS:
                    continue
                msg["content"] = (
                    content[:_KEEP_HEAD]
                    + f"\n…[{len(content) - _KEEP_HEAD - _KEEP_TAIL:,} chars "
                    f"truncados tras compactación]…\n"
                    + content[-_KEEP_TAIL:]
                )
            self._invalidate_token_cache()

        return dropped

    def maybe_compact(
        self, summarize_fn: Optional[Callable[[list[dict]], str]] = None
    ) -> list[dict]:
        """Compacta si se supera el umbral. Devuelve mensajes eliminados."""
        if self.should_compact():
            return self.compact(summarize_fn)
        return []

    def get_messages(self, system: Optional[str] = None) -> list[dict]:
        result: list[dict] = []
        if system:
            full_system = (
                f"{system}\n\n## Resumen de contexto anterior\n{self.summary}"
                if self.summary else system
            )
            result.append({"role": "system", "content": full_system})
        result.extend(self.messages)
        return result

    def stats(self) -> dict:
        return {
            "messages":        len(self.messages),
            "tokens_estimate": self.token_estimate(),
            "max_tokens":      self.max_tokens,
            "summary_chars":   len(self.summary),
            "has_summary":     bool(self.summary),
        }

    def reset_turn_cache(self) -> None:
        """Llamado por AgentLoop al inicio de cada run() para forzar recálculo."""
        self._invalidate_token_cache()


def _msg_chars(msg: dict) -> int:
    content = msg.get("content") or ""
    n = (sum(len(str(c)) for c in content)
         if isinstance(content, list) else len(str(content)))
    # Los mensajes de assistant con tool_calls tienen el payload en ese campo,
    # no en content — hay que contarlo para que el estimado sea correcto.
    tool_calls = msg.get("tool_calls")
    if tool_calls:
        try:
            n += len(json.dumps(tool_calls))
        except Exception:
            n += len(str(tool_calls))
    # Contar contenido de thinking si está presente (Ollama thinking mode)
    thinking = msg.get("thinking") or ""
    if thinking:
        n += len(str(thinking))
    return n
