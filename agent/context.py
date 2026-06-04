"""ConversationContext: historial + compactación con resumen LLM."""
import json
from dataclasses import dataclass, field
from typing import Callable, Optional

import agent.logger as log

# Chars por token según tipo de contenido (Llama/Qwen, estimaciones empíricas)
_CPT_TOOL   = 2.5   # tool results: JSON/código, muy denso
_CPT_CALLS  = 2.5   # assistant tool_calls: payload JSON
_CPT_THINK  = 4.0   # thinking blocks: lenguaje natural fluido, menos denso
_CPT_TEXT   = 3.5   # user/assistant text: mezcla código+lenguaje
_CPT_SYS    = 3.0   # system: plantillas con keywords
_CPT_DEFLT  = 3.0   # fallback


@dataclass
class ConversationContext:
    max_tokens:        int   = 8000
    min_keep:          int   = 6
    compact_threshold: float = 0.80   # fracción de max_tokens para auto-compact; siempre sobreescrito por config.compact_threshold
    max_summary_chars: int   = 2100
    high_water:        float = 0.70   # fracción para truncar tool results en 2ª pasada
    tool_max_chars:    int   = 3000   # chars máx. por tool result en 2ª pasada

    messages: list[dict] = field(default_factory=list)
    summary:  str        = ""        # resumen de msgs compactados, inyectado en prompt aparte

    # ── Cache de token_estimate para no re-escanear mensajes en cada render ──
    _token_cache:  int  = field(default=0,    init=False, repr=False)
    _token_dirty:  bool = field(default=True, init=False, repr=False)

    # ── E: Calibración dinámica de CPT con prompt_eval_count real de Ollama ──
    # Factor multiplicativo sobre la estimación cruda. Converge vía smoothing α=0.15.
    _calibration_factor:  float = field(default=1.0, init=False, repr=False)
    _calibration_samples: int   = field(default=0,   init=False, repr=False)

    # ── G: Contador de compactaciones (para meta-header en el summary) ──
    _compact_count: int = field(default=0, init=False, repr=False)

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
            raw = sum(_msg_tokens(m) for m in self.messages)
            self._token_cache = int(raw * self._calibration_factor)
            self._token_dirty = False
        return self._token_cache

    def calibrate(self, actual_prompt_tokens: int, system_chars: int = 0) -> None:
        """Ajusta _calibration_factor con prompt_eval_count real de Ollama.

        Se invoca en el primer call LLM de cada turno. Usa exponential smoothing
        α=0.15 para suavizar variaciones turno a turno. Descarta outliers fuera
        del rango (0.4, 2.5) para ignorar mediciones anómalas (contexto vacío,
        llamadas de resumen LLM, etc.).
        """
        _est_sys = int(system_chars / _CPT_SYS) if system_chars > 0 else 0
        _est_sum = int(len(self.summary) / _CPT_SYS) if self.summary else 0
        _est_total = self.token_estimate() + _est_sys + _est_sum
        if _est_total < 50 or actual_prompt_tokens <= 0:
            return
        ratio = actual_prompt_tokens / _est_total
        if not (0.4 < ratio < 2.5):
            return
        self._calibration_factor = 0.85 * self._calibration_factor + 0.15 * ratio
        self._calibration_samples += 1
        self._invalidate_token_cache()

    def should_compact(self) -> bool:
        return self.token_estimate() > int(self.max_tokens * self.compact_threshold)

    def _safe_split_index(self, target: int) -> int:
        """Devuelve el índice de corte seguro para no partir pares tool-call/resultado.

        Ajusta `target` hacia adelante hasta encontrar un punto donde:
        - El primer mensaje conservado no es un resultado de tool huérfano
        - El mensaje anterior al corte no es un assistant con tool_calls pendientes

        Una vez encontrado el primer candidato válido, retrocede hasta 5 posiciones
        para preferir un corte en límite de turno 'user' (más natural).

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

            break
        else:
            return 0  # No se encontró punto seguro — no compactar

        # Retroceder hasta 12 posiciones para preferir split en límite 'user'
        for look_back in range(1, min(13, idx + 1)):
            candidate = idx - look_back
            if candidate <= 0:
                break
            if self.messages[candidate].get("role") != "user":
                continue
            # Verificar que el candidato no deja al corte anterior un assistant con tool_calls pendientes
            prev = self.messages[candidate - 1]
            if prev.get("role") == "assistant" and prev.get("tool_calls"):
                continue
            idx = candidate
            break

        return idx

    def compact(
        self,
        summarize_fn:  Optional[Callable[[list[dict]], str]] = None,
        resummary_fn:  Optional[Callable[[str], str]]        = None,
    ) -> list[dict]:
        """Elimina mensajes antiguos conservando los `min_keep` más recientes.

        El punto de corte se ajusta para no partir pares assistant-tool_call/tool-result.
        Si se proporciona summarize_fn, resume los eliminados y acumula en self.summary.
        Si el summary acumulado supera max_summary_chars y se proporciona resummary_fn,
        se condensa con una llamada LLM en lugar de truncar con head+tail.
        Devuelve la lista de mensajes eliminados.
        """
        n = len(self.messages)
        if n <= self.min_keep:
            return []
        self._compact_count += 1   # G: tracking para meta-header

        target = n - self.min_keep
        split  = self._safe_split_index(target)
        if split <= 0:
            return []

        dropped          = self.messages[:split]
        self.messages    = self.messages[split:]
        self._invalidate_token_cache()

        # Extraer el primer mensaje user de los descartados para anclarlo en el summary
        _first_user_content = ""
        if "Tarea original:" not in self.summary:
            for m in dropped:
                if m.get("role") == "user":
                    _raw = m.get("content", "")
                    _text = (str(_raw[0].get("text", "")) if isinstance(_raw, list) and _raw else str(_raw or "")).strip()
                    if _text:
                        _first_user_content = _text[:600]
                    break

        if summarize_fn and dropped:
            try:
                new_summary = summarize_fn(dropped)
                if _first_user_content:
                    new_summary = f"**Tarea original:** {_first_user_content}\n\n{new_summary}"
                if new_summary:
                    self.summary = (
                        f"{self.summary}\n\n{new_summary}" if self.summary else new_summary
                    )
                    if len(self.summary) > self.max_summary_chars:
                        if resummary_fn:
                            try:
                                condensed = resummary_fn(self.summary)
                                if condensed:
                                    self.summary = condensed
                            except Exception:
                                pass
                        # Fallback: truncar si sigue largo o no hay resummary_fn
                        if len(self.summary) > self.max_summary_chars:
                            half = self.max_summary_chars // 2
                            self.summary = (
                                self.summary[:half]
                                + "\n…[resumen intermedio omitido]…\n"
                                + self.summary[-half:]
                            )
            except Exception as e:
                log.debug("context_compact_error", error=str(e))

        # Segunda pasada: si el contexto sigue muy lleno (>high_water) tras soltar mensajes,
        # truncar resultados de tools largos en los mensajes conservados.
        # Las últimas 4 tool results se protegen (más recientes = más relevantes).
        _high_water = int(self.max_tokens * self.high_water)
        if self.token_estimate() > _high_water:
            _MAX_TOOL_CHARS = self.tool_max_chars
            _KEEP_HEAD = max(0, _MAX_TOOL_CHARS - 500)
            _KEEP_TAIL = min(300, _MAX_TOOL_CHARS // 10)
            _tool_indices = [i for i, m in enumerate(self.messages) if m.get("role") == "tool"]
            _protected = set(_tool_indices[-4:])
            for i, msg in enumerate(self.messages):
                if msg.get("role") != "tool" or i in _protected:
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

    def get_messages(self, system: Optional[str] = None) -> list[dict]:
        result: list[dict] = []
        if system:
            result.append({"role": "system", "content": system})
            # D: summary como mensaje system separado — mejor salience en Qwen/DeepSeek
            # ya que el modelo lo procesa sin quedar enterrado en las SYSTEM_RULES.
            if self.summary:
                result.append({
                    "role":    "system",
                    "content": f"## Resumen de contexto anterior\n{self.summary}",
                })
        result.extend(self.messages)
        return result

    def stats(self) -> dict:
        return {
            "messages":            len(self.messages),
            "tokens_estimate":     self.token_estimate(),
            "max_tokens":          self.max_tokens,
            "summary_chars":       len(self.summary),
            "has_summary":         bool(self.summary),
            "calibration_factor":  round(self._calibration_factor, 3),
            "calibration_samples": self._calibration_samples,
        }

    def reset_turn_cache(self) -> None:
        """Llamado por AgentLoop al inicio de cada run() para forzar recálculo."""
        self._invalidate_token_cache()


def _msg_tokens(msg: dict) -> int:
    """Estima los tokens de un mensaje usando ratios por tipo de contenido."""
    role = msg.get("role", "")
    content = msg.get("content") or ""
    n_chars = (sum(len(str(c)) for c in content)
               if isinstance(content, list) else len(str(content)))

    # Elegir ratio según role
    if role == "tool":
        cpt = _CPT_TOOL
    elif role == "system":
        cpt = _CPT_SYS
    else:
        cpt = _CPT_TEXT  # user / assistant

    tokens = int(n_chars / cpt)

    # tool_calls (JSON): el payload está en este campo aparte del content
    tool_calls = msg.get("tool_calls")
    if tool_calls:
        try:
            tc_chars = len(json.dumps(tool_calls))
        except Exception:
            tc_chars = len(str(tool_calls))
        tokens += int(tc_chars / _CPT_CALLS)

    # thinking blocks: lenguaje natural, ratio más bajo de tokens
    thinking = msg.get("thinking") or ""
    if thinking:
        tokens += int(len(str(thinking)) / _CPT_THINK)

    return tokens
