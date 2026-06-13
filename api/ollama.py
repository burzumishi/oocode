"""Backend Ollama — envuelve ollama.Client y normaliza la respuesta a Chunk/Response."""
from __future__ import annotations
from typing import Iterator

import ollama

from api.base import BackendClient, Chunk, Response, ToolCall, _ToolFunction
import agent.logger as log


def _is_unsupported_think_error(exc: Exception) -> bool:
    """True si el error de Ollama indica que el modelo no soporta el parámetro `think`.

    Permite reintentar sin `think` en modelos sin canal de razonamiento (en vez de
    propagar el error al usuario). Ollama responde algo como "model does not support
    thinking" / "thinking is not supported"."""
    m = str(exc).lower()
    return "think" in m and ("not support" in m or "does not" in m or "unsupported" in m)


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
        think=None,
    ) -> Iterator[Chunk]:
        kwargs = {"options": model_params} if model_params else {}
        # `think` controla el canal de razonamiento de Ollama (bool o 'low'/'medium'/
        # 'high'). None = omitir → default del modelo, sin error en modelos sin
        # soporte de thinking. SIN esto, /think y /reasoning no llegaban al servidor.
        if think is not None:
            kwargs["think"] = think

        def _open_stream(kw: dict):
            return self._client.chat(
                model=model, messages=messages, tools=tools or [],
                stream=True, **kw,
            )
        try:
            stream = _open_stream(kwargs)
            first = next(stream, None)
        except Exception as exc:
            # Modelo sin soporte de thinking → reintentar sin el parámetro.
            if "think" in kwargs and _is_unsupported_think_error(exc):
                log.debug("ollama_think_unsupported_retry", model=model)
                kwargs.pop("think", None)
                stream = _open_stream(kwargs)
                first = next(stream, None)
            else:
                raise

        import itertools
        for chunk in (itertools.chain([first], stream) if first is not None else stream):
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
        think=None,
    ) -> Response:
        kwargs = {"options": model_params} if model_params else {}
        if think is not None:
            kwargs["think"] = think

        def _call(kw: dict):
            if timeout > 0:
                from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutureTimeout
                with ThreadPoolExecutor(max_workers=1) as _ex:
                    _fut = _ex.submit(
                        self._client.chat,
                        model=model, messages=messages, tools=tools or [],
                        stream=False, **kw,
                    )
                    try:
                        return _fut.result(timeout=timeout)
                    except _FutureTimeout:
                        # Señal de timeout — el caller maneja _TIMEOUT_SENTINEL
                        raise TimeoutError("ollama_timeout")
            return self._client.chat(
                model=model, messages=messages, tools=tools or [],
                stream=False, **kw,
            )

        try:
            resp = _call(kwargs)
        except TimeoutError:
            raise
        except Exception as exc:
            # Modelo sin soporte de thinking → reintentar sin el parámetro.
            if "think" in kwargs and _is_unsupported_think_error(exc):
                log.debug("ollama_think_unsupported_retry", model=model)
                kwargs.pop("think", None)
                resp = _call(kwargs)
            else:
                raise
        msg = resp.message
        return Response(
            text=msg.content or "",
            tool_calls=_norm_tool_calls(msg.tool_calls),
            thinking=getattr(msg, "thinking", "") or "",
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
