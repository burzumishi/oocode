"""Backend Anthropic — usa el SDK anthropic y convierte mensajes/tools al formato Anthropic."""
from __future__ import annotations
import json
from typing import Iterator

from api.base import BackendClient, Chunk, Response, ToolCall, _ToolFunction
import agent.logger as log

# Parámetros de Ollama que no existen en Anthropic
_PARAM_DROP = {"num_ctx", "keep_alive", "repeat_penalty", "seed"}
# num_predict (límite de salida de Ollama) → max_tokens de Anthropic
_PARAM_MAP  = {"num_predict": "max_tokens", "temperature": "temperature",
               "top_p": "top_p", "top_k": "top_k"}


def _adapt_params(params: dict) -> dict:
    return {_PARAM_MAP.get(k, k): v for k, v in params.items() if k not in _PARAM_DROP}


def _tools_to_anthropic(tools: list) -> list:
    """Convierte schemas OpenAI/Ollama a formato Anthropic."""
    result = []
    for t in tools:
        fn = t.get("function", t)   # soporta {"type":"function","function":{...}} y {"name":...}
        result.append({
            "name":         fn.get("name", ""),
            "description":  fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return result


def _messages_to_anthropic(messages: list) -> tuple[str, list]:
    """Convierte mensajes OpenAI a formato Anthropic.

    Devuelve (system_prompt, anthropic_messages).
    - Los mensajes 'system' se concatenan en un solo bloque de sistema.
    - Los mensajes 'tool' (resultados) se convierten a content blocks.
    - Los mensajes 'assistant' con tool_calls se convierten a content blocks.
    """
    system_parts: list[str] = []
    out: list[dict] = []

    for msg in messages:
        role    = msg.get("role", "user")
        content = msg.get("content") or ""

        if role == "system":
            if isinstance(content, str) and content:
                system_parts.append(content)
            continue

        if role == "user":
            if isinstance(content, str):
                if content:
                    out.append({"role": "user", "content": content})
            elif isinstance(content, list):
                # content blocks (imágenes, etc.)
                out.append({"role": "user", "content": content})
            continue

        if role == "assistant":
            blocks: list[dict] = []
            if isinstance(content, str) and content:
                blocks.append({"type": "text", "text": content})
            for tc in (msg.get("tool_calls") or []):
                fn   = tc.get("function", {})
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                blocks.append({
                    "type":  "tool_use",
                    "id":    tc.get("id", f"tool_{fn.get('name', 'unknown')}"),
                    "name":  fn.get("name", ""),
                    "input": args,
                })
            if blocks:
                out.append({"role": "assistant", "content": blocks})
            continue

        if role == "tool":
            tool_use_id = msg.get("tool_call_id") or msg.get("name", "tool")
            out.append({
                "role": "user",
                "content": [{
                    "type":        "tool_result",
                    "tool_use_id": tool_use_id,
                    "content":     str(content),
                }],
            })
            continue

    system = "\n\n".join(system_parts)
    return system, out


def _norm_tool_calls(content_blocks: list) -> list[ToolCall]:
    result = []
    for block in content_blocks:
        if block.get("type") == "tool_use":
            result.append(ToolCall(function=_ToolFunction(
                name=block.get("name", ""),
                arguments=block.get("input") or {},
            )))
    return result


class AnthropicBackend(BackendClient):
    """Backend para la API de Anthropic (Claude)."""

    def __init__(self, api_key: str = "", max_tokens: int | None = None) -> None:
        self._api_key    = api_key
        # max_tokens es obligatorio en la API de Anthropic; 8192 es un fallback seguro.
        self._max_tokens = max_tokens or 8192
        self._client     = self._make_client()

    def _make_client(self):
        try:
            import anthropic
            return anthropic.Anthropic(api_key=self._api_key or None)
        except ImportError:
            raise ImportError("anthropic es necesario para el backend anthropic: pip install anthropic")

    # ── Streaming ─────────────────────────────────────────────────────────────

    def chat_stream(
        self,
        model: str,
        messages: list,
        tools: list,
        model_params: dict,
    ) -> Iterator[Chunk]:
        system, ant_messages = _messages_to_anthropic(messages)
        ant_tools = _tools_to_anthropic(tools) if tools else []
        params    = _adapt_params(model_params)

        kwargs: dict = dict(
            model=model,
            messages=ant_messages,
            max_tokens=params.pop("max_tokens", self._max_tokens),
            **params,
        )
        if system:
            kwargs["system"] = system
        if ant_tools:
            kwargs["tools"] = ant_tools

        text_acc      = ""
        thinking_acc  = ""
        content_blocks: list = []
        inp_tokens    = 0
        out_tokens    = 0

        with self._client.messages.stream(**kwargs) as stream:
            for event in stream:
                etype = type(event).__name__

                if etype == "RawContentBlockDeltaEvent":
                    delta = event.delta
                    dtype = type(delta).__name__
                    if dtype == "TextDelta":
                        text_acc += delta.text
                        yield Chunk(text=delta.text)
                    elif dtype == "ThinkingDelta":
                        thinking_acc += delta.thinking
                        yield Chunk(thinking=delta.thinking)
                    elif dtype == "InputJSONDelta":
                        # JSON delta de tool_use — acumular en content_blocks
                        if content_blocks and content_blocks[-1].get("type") == "tool_use":
                            content_blocks[-1].setdefault("_raw_input", "")
                            content_blocks[-1]["_raw_input"] += delta.partial_json

                elif etype == "RawContentBlockStartEvent":
                    block = event.content_block
                    btype = getattr(block, "type", "")
                    if btype == "tool_use":
                        content_blocks.append({
                            "type":  "tool_use",
                            "id":    getattr(block, "id", ""),
                            "name":  getattr(block, "name", ""),
                            "input": {},
                        })

                elif etype == "RawContentBlockStopEvent":
                    if content_blocks and "_raw_input" in content_blocks[-1]:
                        raw = content_blocks[-1].pop("_raw_input", "{}")
                        try:
                            content_blocks[-1]["input"] = json.loads(raw)
                        except Exception:
                            content_blocks[-1]["input"] = {}

                elif etype == "RawMessageDeltaEvent":
                    usage = getattr(event.usage, "__dict__", {})
                    out_tokens = usage.get("output_tokens", out_tokens)

                elif etype == "RawMessageStartEvent":
                    usage = getattr(getattr(event, "message", None), "usage", None)
                    if usage:
                        inp_tokens = getattr(usage, "input_tokens", 0)

        tool_calls = _norm_tool_calls(content_blocks)
        yield Chunk(
            done=True,
            tool_calls=tool_calls,
            input_tokens=inp_tokens,
            output_tokens=out_tokens,
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
        system, ant_messages = _messages_to_anthropic(messages)
        ant_tools = _tools_to_anthropic(tools) if tools else []
        params    = _adapt_params(model_params)

        kwargs: dict = dict(
            model=model,
            messages=ant_messages,
            max_tokens=params.pop("max_tokens", self._max_tokens),
            **params,
        )
        if system:
            kwargs["system"] = system
        if ant_tools:
            kwargs["tools"] = ant_tools

        try:
            import anthropic
            if timeout > 0:
                import httpx
                with anthropic.Anthropic(api_key=self._api_key or None,
                                         timeout=httpx.Timeout(timeout)) as cl:
                    resp = cl.messages.create(**kwargs)
            else:
                resp = self._client.messages.create(**kwargs)
        except Exception as e:
            if "timeout" in str(e).lower():
                raise TimeoutError("anthropic_timeout")
            raise

        text       = ""
        content_blocks: list = []
        for block in (resp.content or []):
            btype = getattr(block, "type", "")
            if btype == "text":
                text += getattr(block, "text", "")
            elif btype == "tool_use":
                content_blocks.append({
                    "type":  "tool_use",
                    "id":    getattr(block, "id", ""),
                    "name":  getattr(block, "name", ""),
                    "input": getattr(block, "input", {}),
                })

        usage = getattr(resp, "usage", None)
        return Response(
            text=text,
            tool_calls=_norm_tool_calls(content_blocks),
            input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
        )

    # ── Control de conexión ───────────────────────────────────────────────────

    def kill_stream(self) -> None:
        # El SDK de Anthropic no expone un cierre directo del stream, pero envuelve
        # un httpx.Client en self._client._client. Cerramos a la fuerza su socket
        # para abortar un stream colgado (close() solo no lo desbloquea en silencio).
        try:
            inner = getattr(self._client, "_client", None)
            if inner is not None:
                from api.base import force_close_httpx_sockets
                force_close_httpx_sockets(inner)
        except Exception as e:
            log.debug("anthropic_kill_stream_error", error=str(e))

    def rebuild(self, config) -> None:
        api_key = getattr(config, "api_key", self._api_key)
        self._api_key = api_key
        _mt = getattr(config, "effective_max_output_tokens", None)
        if _mt:
            self._max_tokens = _mt
        try:
            self._client = self._make_client()
        except Exception as e:
            log.warning("anthropic_rebuild_failed", error=str(e))

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass
