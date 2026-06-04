"""Backend Ollama — envuelve ollama.Client y normaliza la respuesta a Chunk/Response."""
from __future__ import annotations
from typing import Iterator

import ollama

from api.base import BackendClient, Chunk, Response, ToolCall, _ToolFunction
import agent.logger as log


def _raw_models(host: str) -> list:
    """Lista cruda de modelos de un servidor Ollama (objetos o dicts del SDK)."""
    data = ollama.Client(host=host).list()
    return data.get("models", []) if isinstance(data, dict) else list(data.models)


def ollama_model_names(host: str) -> list[str]:
    """Nombres de los modelos disponibles en un servidor Ollama.

    Fuente única para todos los listados de modelos del repo (doctor, /models,
    /fast, selector de modelo, gateway-status). Puede lanzar si el host no responde;
    el llamador decide cómo manejar el error.
    """
    return [(m.model if hasattr(m, "model") else m["name"]) for m in _raw_models(host)]


def list_ollama_models(host: str) -> list[dict]:
    """Modelos de un servidor Ollama como dicts {name, size, details}.

    Variante enriquecida de `ollama_model_names` para los listados que muestran
    familia/tamaño/cuantización (selector de modelo, /config, /models).
    """
    out: list[dict] = []
    for m in _raw_models(host):
        is_obj = hasattr(m, "model")
        out.append({
            "name":    m.model if is_obj else m["name"],
            "size":    (m.size if is_obj else m.get("size", 0)) or 0,
            "details": (m.details.model_dump() if is_obj and getattr(m, "details", None)
                        else (m.get("details", {}) if isinstance(m, dict) else {})),
        })
    return out


def model_info(host: str, model_name: str) -> dict:
    """Detalle de un modelo concreto vía ollama.show().

    Devuelve {"params", "details", "modelinfo"} parseando el modelfile. Puede
    lanzar si el host no responde o el modelo no existe; el llamador decide cómo
    manejar el error (igual que `list_ollama_models`).
    """
    info = ollama.Client(host=host).show(model_name)
    params: dict = {}
    raw_params = getattr(info, "parameters", None) or ""
    if raw_params:
        for line in raw_params.strip().splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2:
                params[parts[0].lower()] = parts[1]
    details = {}
    if hasattr(info, "details") and info.details:
        details = info.details.model_dump() if hasattr(info.details, "model_dump") else {}
    modelinfo = {}
    if hasattr(info, "modelinfo") and info.modelinfo:
        modelinfo = dict(info.modelinfo)
    return {"params": params, "details": details, "modelinfo": modelinfo}


def _norm_tool_calls(raw_tcs) -> list[ToolCall]:
    """Convierte los objetos Tool de Ollama a ToolCall normalizados."""
    if not raw_tcs:
        return []
    result = []
    for tc in raw_tcs:
        fn   = tc.function
        args = fn.arguments
        if isinstance(args, str):
            import json
            try:
                args = json.loads(args)
            except Exception:
                args = {}
        result.append(ToolCall(function=_ToolFunction(name=fn.name, arguments=args or {})))
    return result


class OllamaBackend(BackendClient):
    """Backend para Ollama (o cualquier servidor compatible con la API de Ollama)."""

    def __init__(self, host: str = "http://localhost:11434") -> None:
        self._host   = host
        self._client = ollama.Client(host=host)

    # ── Streaming ─────────────────────────────────────────────────────────────

    def chat_stream(
        self,
        model: str,
        messages: list,
        tools: list,
        model_params: dict,
    ) -> Iterator[Chunk]:
        kwargs = {"options": model_params} if model_params else {}
        stream = self._client.chat(
            model=model,
            messages=messages,
            tools=tools or [],
            stream=True,
            **kwargs,
        )
        for chunk in stream:
            msg = chunk.message
            yield Chunk(
                text=msg.content or "",
                tool_calls=_norm_tool_calls(msg.tool_calls),
                thinking=getattr(msg, "thinking", "") or "",
                done=bool(chunk.done),
                input_tokens=getattr(chunk, "prompt_eval_count", 0) or 0,
                output_tokens=getattr(chunk, "eval_count", 0) or 0,
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
        kwargs = {"options": model_params} if model_params else {}
        if timeout > 0:
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutureTimeout
            with ThreadPoolExecutor(max_workers=1) as _ex:
                _fut = _ex.submit(
                    self._client.chat,
                    model=model, messages=messages, tools=tools or [],
                    stream=False, **kwargs,
                )
                try:
                    resp = _fut.result(timeout=timeout)
                except _FutureTimeout:
                    # Señal de timeout — el caller maneja _TIMEOUT_SENTINEL
                    raise TimeoutError("ollama_timeout")
        else:
            resp = self._client.chat(
                model=model,
                messages=messages,
                tools=tools or [],
                stream=False,
                **kwargs,
            )
        msg = resp.message
        return Response(
            text=msg.content or "",
            tool_calls=_norm_tool_calls(msg.tool_calls),
            input_tokens=getattr(resp, "prompt_eval_count", 0) or 0,
            output_tokens=getattr(resp, "eval_count", 0) or 0,
        )

    # ── Control de conexión ───────────────────────────────────────────────────

    def kill_stream(self) -> None:
        try:
            if hasattr(self._client, "_client"):
                # Primero cerrar a la fuerza el socket del stream en curso: close()
                # por sí solo no desbloquea un read() colgado si Ollama está en
                # silencio (prompt-eval / pausa). Esto aborta la generación al instante.
                from api.base import force_close_httpx_sockets
                force_close_httpx_sockets(self._client._client)
                self._client._client.close()
        except Exception as e:
            log.debug("ollama_kill_stream_error", error=str(e))

    def rebuild(self, config) -> None:
        host = getattr(config, "ollama_host", self._host)
        try:
            self._client = ollama.Client(host=host)
            self._host   = host
        except Exception as e:
            log.warning("ollama_rebuild_failed", host=host, error=str(e))

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass
