"""Tipos normalizados y protocolo común para todos los backends LLM."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator, Optional, Union

# Valor normalizado de "think" que el AgentLoop pasa a los backends:
#   None  → omitir el parámetro (usa el default del modelo; NO error en modelos
#           sin soporte de thinking — preserva el comportamiento histórico).
#   False → desactivar pensamiento explícitamente.
#   True  → activar pensamiento (nivel por defecto del modelo).
#   "low"/"medium"/"high" → nivel graduado (gpt-oss, Anthropic budget, etc.).
ThinkValue = Optional[Union[bool, str]]

# Mapa think_level (runtime) → valor de nivel para los backends que lo gradúan.
THINK_LEVEL_MAP = {
    "minimal": "low",
    "low":     "low",
    "medium":  "medium",
    "high":    "high",
}


def force_close_httpx_sockets(httpx_client) -> int:
    """Cierra forzosamente (`shutdown(SHUT_RDWR)`) los sockets de las conexiones
    activas del pool de un `httpx.Client`. Devuelve cuántos sockets cerró.

    Por qué: `httpx.Client.close()` NO interrumpe un `read()` bloqueado sobre una
    conexión en uso (un stream en curso). Si el servidor está en silencio —p.ej. el
    LLM evaluando el prompt o pausando entre tokens— el hilo lector queda colgado
    hasta que el servidor escribe o cierra. Para que `/kill` aborte el LLM de verdad
    y de inmediato hay que cerrar el socket subyacente: el `recv()` bloqueado devuelve
    al instante y el servidor (Ollama) detecta la desconexión y aborta la generación.

    Tolerante a la versión de httpx: si la estructura interna del pool no coincide,
    no lanza (devuelve los que haya podido cerrar). Ruta validada en httpx 0.28:
    `client._transport._pool.connections[i]._connection._network_stream._sock`.
    """
    import socket as _socket
    n = 0
    try:
        transport = getattr(httpx_client, "_transport", None)
        pool = getattr(transport, "_pool", None)
        if pool is None:
            return 0
        for conn in list(getattr(pool, "connections", []) or []):
            try:
                inner  = getattr(conn, "_connection", None) or conn
                stream = getattr(inner, "_network_stream", None)
                sock   = getattr(stream, "_sock", None)
                # En TLS (https) _sock puede ser un SSLStream que envuelve el socket
                # real en su propio atributo _sock; ssl.SSLSocket ya es un socket.
                raw = getattr(sock, "_sock", None)
                if isinstance(raw, _socket.socket):
                    sock = raw
                if isinstance(sock, _socket.socket):
                    sock.shutdown(_socket.SHUT_RDWR)
                    n += 1
            except (OSError, AttributeError):
                continue
    except Exception:
        pass
    return n


@dataclass
class _ToolFunction:
    name: str
    arguments: dict


@dataclass
class ToolCall:
    """Tool call normalizado — misma interfaz de atributos que el objeto de Ollama."""
    function: _ToolFunction

    def model_dump(self, exclude_none: bool = False) -> dict:
        return {
            "type": "function",
            "function": {
                "name":      self.function.name,
                "arguments": self.function.arguments,
            },
        }


@dataclass
class Chunk:
    """Fragmento de streaming normalizado que todos los backends emiten."""
    text:          str  = ""
    tool_calls:    list = field(default_factory=list)   # list[ToolCall]
    thinking:      str  = ""
    done:          bool = False
    input_tokens:  int  = 0
    output_tokens: int  = 0


@dataclass
class Response:
    """Respuesta síncrona normalizada (stream=False)."""
    text:          str  = ""
    tool_calls:    list = field(default_factory=list)   # list[ToolCall]
    thinking:      str  = ""
    input_tokens:  int  = 0
    output_tokens: int  = 0


class BackendClient(ABC):
    """Protocolo común para todos los backends LLM."""

    @abstractmethod
    def chat_stream(
        self,
        model: str,
        messages: list,
        tools: list,
        model_params: dict,
        think: ThinkValue = None,
    ) -> Iterator[Chunk]:
        """Streaming: yield Chunk objects hasta Chunk(done=True).

        `think` controla el canal de razonamiento (ver ThinkValue). `None` omite el
        parámetro para no romper modelos sin soporte de thinking."""
        ...

    @abstractmethod
    def chat_sync(
        self,
        model: str,
        messages: list,
        tools: list,
        model_params: dict,
        timeout: float = 0,
        think: ThinkValue = None,
    ) -> Response:
        """Síncrono: devuelve un Response completo. Ver `think` en chat_stream."""
        ...

    @abstractmethod
    def kill_stream(self) -> None:
        """Interrumpe el streaming en curso (usado por kill_requested)."""
        ...

    @abstractmethod
    def rebuild(self, config) -> None:
        """Reconstruye la conexión interna tras un kill."""
        ...

    def close(self) -> None:
        """Cierra recursos. Subclases sobreescriben si es necesario."""
