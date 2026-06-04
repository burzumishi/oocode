"""Backend OpenAI-compatible — soporta OpenAI, llama.cpp, LM Studio, vLLM, koboldcpp."""
from __future__ import annotations
import json
from typing import Iterator

from api.base import BackendClient, Chunk, Response, ToolCall, _ToolFunction
import agent.logger as log

# Mapa de parámetros de Ollama a nombre OpenAI (model_params puede venir de Ollama)
_PARAM_MAP = {
    "num_predict": "max_tokens",
    "repeat_penalty": "frequency_penalty",
}
_PARAM_DROP = {"num_ctx", "keep_alive", "seed"}   # sin equivalente directo o sin sentido en OpenAI


def _adapt_params(params: dict) -> dict:
    """Convierte parámetros de opciones de Ollama al formato OpenAI."""
    out: dict = {}
    for k, v in params.items():
        if k in _PARAM_DROP:
            continue
        out[_PARAM_MAP.get(k, k)] = v
    return out


def _norm_tool_calls(raw_tcs: list) -> list[ToolCall]:
    """Convierte tool_calls OpenAI (delta acumulado) a ToolCall normalizados."""
    result = []
    for tc in raw_tcs:
        fn_name = tc.get("function", {}).get("name", "")
        fn_args = tc.get("function", {}).get("arguments", "{}")
        if isinstance(fn_args, str):
            try:
                fn_args = json.loads(fn_args)
            except Exception:
                fn_args = {}
        result.append(ToolCall(function=_ToolFunction(name=fn_name, arguments=fn_args or {})))
    return result


class OpenAIBackend(BackendClient):
    """Backend para APIs compatibles con OpenAI (llama.cpp /v1, LM Studio, vLLM…)."""

    def __init__(self, base_url: str = "https://api.openai.com/v1", api_key: str = "",
                 max_tokens: int | None = None) -> None:
        self._base_url   = base_url.rstrip("/")
        self._api_key    = api_key
        self._max_tokens = max_tokens   # None = no enviar max_tokens (servidor decide)
        self._client     = self._make_client()

    def _make_client(self):
        try:
            import httpx
            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            return httpx.Client(headers=headers, timeout=None)
        except ImportError:
            raise ImportError("httpx es necesario para el backend openai: pip install httpx")

    def _build_payload(self, model: str, messages: list, tools: list,
                       model_params: dict, stream: bool) -> dict:
        """Construye el payload común para stream/sync, inyectando max_tokens si procede."""
        adapted = _adapt_params(model_params)
        # Inyectar max_tokens del modelo si el caller no lo especificó
        if self._max_tokens and "max_tokens" not in adapted:
            adapted["max_tokens"] = self._max_tokens
        payload: dict = {"model": model, "messages": messages, "stream": stream, **adapted}
        if tools:
            payload["tools"] = tools
        return payload

    # ── Streaming ─────────────────────────────────────────────────────────────

    def chat_stream(
        self,
        model: str,
        messages: list,
        tools: list,
        model_params: dict,
    ) -> Iterator[Chunk]:
        payload = self._build_payload(model, messages, tools, model_params, stream=True)
        # Pedir el bloque de usage en el chunk final (OpenAI lo envía tras finish_reason)
        payload["stream_options"] = {"include_usage": True}

        # Acumulador de tool calls delta (OpenAI fragmenta arguments en chunks)
        _tc_acc: dict[int, dict] = {}   # index → {id, function: {name, arguments}}
        _inp_tokens = 0
        _out_tokens = 0

        with self._client.stream("POST", f"{self._base_url}/chat/completions", json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("data: "):
                    line = line[6:]
                if line == "[DONE]":
                    break
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # usage puede llegar en cualquier chunk; el final suele traerlo con choices=[]
                usage = obj.get("usage") or {}
                if usage:
                    _inp_tokens = usage.get("prompt_tokens", _inp_tokens)
                    _out_tokens = usage.get("completion_tokens", _out_tokens)

                choices = obj.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}

                text = delta.get("content") or ""
                # Acumular tool call deltas
                for tc_delta in (delta.get("tool_calls") or []):
                    idx = tc_delta.get("index", 0)
                    if idx not in _tc_acc:
                        _tc_acc[idx] = {"id": tc_delta.get("id", ""), "function": {"name": "", "arguments": ""}}
                    fn = tc_delta.get("function") or {}
                    if fn.get("name"):
                        _tc_acc[idx]["function"]["name"] += fn["name"]
                    if fn.get("arguments"):
                        _tc_acc[idx]["function"]["arguments"] += fn["arguments"]

                if text:
                    yield Chunk(text=text)   # streaming de texto en vivo (done=False)

        # Chunk final: tool_calls completos + usage real (loop.py rompe aquí)
        yield Chunk(
            done=True,
            tool_calls=_norm_tool_calls(list(_tc_acc.values())) if _tc_acc else [],
            input_tokens=_inp_tokens,
            output_tokens=_out_tokens,
        )

    # ── Síncrono ──────────────────────────────────────────────────────────────

    def chat_sync(
        self,
        model: str,
        messages: list,
        tools: list,
        model_params: dict,
        timeout: float = 0,
    ) -> Response:
        import httpx
        payload = self._build_payload(model, messages, tools, model_params, stream=False)

        request_timeout = timeout if timeout > 0 else None
        try:
            resp = self._client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                timeout=request_timeout,
            )
            resp.raise_for_status()
        except httpx.TimeoutException:
            raise TimeoutError("openai_timeout")

        data    = resp.json()
        choice  = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage   = data.get("usage") or {}

        return Response(
            text=message.get("content") or "",
            tool_calls=_norm_tool_calls(message.get("tool_calls") or []),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )

    # ── Control de conexión ───────────────────────────────────────────────────

    def kill_stream(self) -> None:
        try:
            # Cerrar a la fuerza el socket del stream en curso antes de close():
            # close() no desbloquea un read() colgado si el servidor está en silencio.
            from api.base import force_close_httpx_sockets
            force_close_httpx_sockets(self._client)
            self._client.close()
            self._client = self._make_client()
        except Exception as e:
            log.debug("openai_kill_stream_error", error=str(e))

    def rebuild(self, config) -> None:
        base_url = getattr(config, "api_base_url", self._base_url) or self._base_url
        api_key  = getattr(config, "api_key", self._api_key)
        self._base_url = base_url
        self._api_key  = api_key
        _mt = getattr(config, "effective_max_output_tokens", None)
        if _mt:
            self._max_tokens = _mt
        try:
            self._client = self._make_client()
        except Exception as e:
            log.warning("openai_rebuild_failed", error=str(e))

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass
