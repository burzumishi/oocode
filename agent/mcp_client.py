"""Cliente MCP (Model Context Protocol) sobre transporte stdio.

Protocolo: JSON-RPC 2.0 con framing newline, versión 2024-11-05.

I/O no bloqueante: un hilo daemon lee stdout del servidor y deposita
mensajes en una queue. _request() usa queue.get(timeout=) — nunca
bloquea el hilo principal indefinidamente.

Soporte de reconexión automática si el servidor muere durante una llamada.
"""
import json
import os
import queue
import subprocess
import threading
import time
from typing import Any, Optional

import agent.logger as log

_PROTOCOL_VERSION = "2024-11-05"
_DEFAULT_TIMEOUT  = 15.0


class McpError(Exception):
    pass


class McpClient:
    """Cliente MCP stdio para un servidor concreto."""

    def __init__(self, name: str, cmd: list[str],
                 env: Optional[dict] = None, cwd: Optional[str] = None,
                 request_timeout: float = _DEFAULT_TIMEOUT,
                 description: str = ""):
        self.name          = name
        self.description   = description
        self._cmd          = cmd
        self._env          = env
        self._cwd          = cwd
        self._timeout      = request_timeout
        self._proc:        Optional[subprocess.Popen] = None
        self._req_id       = 0
        self._id_lock      = threading.Lock()
        self._send_lock    = threading.Lock()
        self._msg_queue:   queue.Queue = queue.Queue()
        self._reader:      Optional[threading.Thread] = None
        self._started      = False
        self._dead         = False
        self._tools:          list[dict] = []
        self._error:          str = ""      # último error de arranque
        self._tools_changed:  bool = False  # set True por notif tools/list_changed
        self._gen:            int  = 0      # generación del proceso: evita que reader viejo marque dead al nuevo
        self._capabilities:   dict = {}     # capacidades del servidor (de initialize)
        self._resource_count: int  = 0      # cacheado por resource_oocode_tools()
        self._prompt_count:   int  = 0      # cacheado por prompt_oocode_tools()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._started:
            return
        env = dict(os.environ)
        if self._env:
            env.update(self._env)
        self._proc = subprocess.Popen(
            self._cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,   # capturado para errores de arranque
            env=env,
            cwd=self._cwd,
            start_new_session=True,
        )
        self._started = True
        self._dead    = False
        self._error   = ""
        self._gen    += 1   # nueva generación: invalida cualquier reader anterior
        # Hilo lector de stdout
        self._reader = threading.Thread(
            target=self._reader_loop,
            daemon=True,
            name=f"mcp-reader-{self.name}",
        )
        self._reader.start()
        self._do_initialize()
        log.debug("mcp_started", server=self.name, cmd=self._cmd[0])

    def stop(self) -> None:
        if not self._started or self._proc is None:
            return
        self._started = False
        self._dead    = True
        self._msg_queue.put(None)   # desbloquear _request en espera
        try:
            self._proc.terminate()
            self._proc.wait(timeout=3)
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass
        log.debug("mcp_stopped", server=self.name)

    @property
    def is_alive(self) -> bool:
        return (self._started and not self._dead
                and self._proc is not None
                and self._proc.poll() is None)

    @property
    def error(self) -> str:
        return self._error

    # ── Lector de stdout (hilo daemon) ────────────────────────────────────────

    def _reader_loop(self) -> None:
        my_gen = self._gen   # captura generación al inicio: si _gen cambia, este reader ya no es el actual
        proc   = self._proc
        if proc is None or proc.stdout is None:
            return
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line.decode(errors="replace"))
                except json.JSONDecodeError:
                    continue
                # Notificación de cambio de tools: recargar en background
                if msg.get("method") == "notifications/tools/list_changed":
                    threading.Thread(
                        target=self._reload_tools_bg,
                        daemon=True,
                        name=f"mcp-reload-{self.name}",
                    ).start()
                    continue
                self._msg_queue.put(msg)
        except Exception:
            pass
        finally:
            # Solo marcar dead si somos el reader de la generación actual
            if self._gen == my_gen:
                self._dead = True
                self._msg_queue.put(None)

    # ── JSON-RPC ──────────────────────────────────────────────────────────────

    def _next_id(self) -> int:
        with self._id_lock:
            self._req_id += 1
            return self._req_id

    def _send(self, payload: dict) -> None:
        if not self._started or self._proc is None or self._proc.stdin is None:
            raise McpError("MCP process not running")
        data = json.dumps(payload, ensure_ascii=False) + "\n"
        with self._send_lock:
            self._proc.stdin.write(data.encode())
            self._proc.stdin.flush()

    def _request(self, method: str, params: Any) -> Optional[Any]:
        if self._dead:
            raise McpError(f"MCP server '{self.name}' died")
        req_id = self._next_id()
        self._send({"jsonrpc": "2.0", "id": req_id,
                    "method": method, "params": params})
        pending: list = []
        t0 = time.monotonic()
        try:
            while True:
                remaining = self._timeout - (time.monotonic() - t0)
                if remaining <= 0:
                    break
                try:
                    msg = self._msg_queue.get(timeout=min(remaining, 1.0))
                except queue.Empty:
                    if self._dead:
                        break
                    continue
                if msg is None:
                    break
                if msg.get("id") == req_id:
                    for p in pending:
                        self._msg_queue.put(p)
                    if "error" in msg:
                        raise McpError(f"MCP error: {msg['error']}")
                    return msg.get("result")
                else:
                    pending.append(msg)
        finally:
            for p in pending:
                self._msg_queue.put(p)
        return None

    def _send_notification(self, method: str, params: Any) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    # ── Inicialización ────────────────────────────────────────────────────────

    def _do_initialize(self) -> None:
        result = self._request("initialize", {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities":    {"sampling": {}, "roots": {"listChanged": False}},
            "clientInfo":      {"name": "oocode", "version": "0.1.0"},
        })
        if result is None:
            # Leer stderr de forma no bloqueante para diagnóstico
            stderr_hint = ""
            if self._proc and self._proc.stderr:
                try:
                    # read1 lee lo disponible sin bloquear (buffered IO)
                    chunk = self._proc.stderr.read1(2048)  # type: ignore[attr-defined]
                    if chunk:
                        stderr_hint = chunk.decode(errors="replace")[:200].strip()
                except (AttributeError, Exception):
                    pass
            self._error = f"no respondió al initialize{': ' + stderr_hint if stderr_hint else ''}"
            raise McpError(f"MCP server '{self.name}': {self._error}")

        self._capabilities = result.get("capabilities", {})
        self._send_notification("notifications/initialized", {})
        try:
            self._tools = self._list_tools()
        except Exception as exc:
            log.debug("mcp_tools_error", server=self.name, error=str(exc))

    # ── Tools API ─────────────────────────────────────────────────────────────

    def _list_tools(self) -> list[dict]:
        """Solicita tools/list con soporte de paginación por cursor."""
        tools: list[dict] = []
        cursor: Optional[str] = None
        while True:
            params: dict = {}
            if cursor:
                params["cursor"] = cursor
            result = self._request("tools/list", params)
            if result is None:
                break
            tools.extend(result.get("tools", []))
            cursor = result.get("nextCursor")
            if not cursor:
                break
        return tools

    def _reload_tools_bg(self) -> None:
        """Recarga tools/list tras notif tools/list_changed (ejecutado en hilo daemon)."""
        try:
            self._tools = self._list_tools()
            self._tools_changed = True
            log.debug("mcp_tools_reloaded", server=self.name, count=len(self._tools))
        except Exception as exc:
            log.debug("mcp_tools_reload_error", server=self.name, error=str(exc))

    @property
    def tools(self) -> list[dict]:
        return self._tools

    def reload_tools(self) -> int:
        """Re-solicita tools/list al servidor. Devuelve el nuevo conteo."""
        try:
            self._tools = self._list_tools()
        except Exception:
            pass
        return len(self._tools)

    def _try_restart(self) -> bool:
        """Reinicia el proceso del servidor. Devuelve True si arranca OK."""
        self._gen += 1          # invalida el reader viejo antes de pararlo
        old_proc  = self._proc
        self._started = False
        self._dead    = True
        self._msg_queue.put(None)   # desbloquear cualquier _request en espera
        if old_proc is not None:
            try:
                old_proc.terminate()
                old_proc.wait(timeout=3)
            except Exception:
                try:
                    old_proc.kill()
                except Exception:
                    pass
        self._dead      = False
        self._error     = ""
        self._msg_queue = queue.Queue()
        try:
            self.start()
            log.debug("mcp_auto_restarted", server=self.name)
            return True
        except Exception as exc:
            self._error = str(exc)
            log.debug("mcp_auto_restart_failed", server=self.name, error=str(exc))
            return False

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        if not self.is_alive:
            if not self._try_restart():
                return (f"Error: servidor MCP '{self.name}' no disponible "
                        f"({self._error or 'proceso terminado'}).")
        try:
            result = self._request("tools/call",
                                   {"name": tool_name, "arguments": arguments})
        except McpError as exc:
            # Intento de reconexión si el proceso murió durante la llamada
            if "died" in str(exc).lower() and self._try_restart():
                try:
                    result = self._request("tools/call",
                                           {"name": tool_name, "arguments": arguments})
                except McpError as exc2:
                    return f"Error MCP: {exc2}"
            else:
                return f"Error MCP: {exc}"
        if result is None:
            return "Sin respuesta del servidor MCP (timeout)."

        content = result.get("content", result)
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    t = block.get("type", "")
                    if t == "text":
                        parts.append(block.get("text", ""))
                    elif t == "image":
                        parts.append(f"[imagen: {block.get('mimeType', 'image')}]")
                    elif t == "resource":
                        uri = block.get("resource", {}).get("uri", "")
                        parts.append(f"[resource: {uri}]")
                    else:
                        parts.append(json.dumps(block, ensure_ascii=False))
                else:
                    parts.append(str(block))
            return "\n".join(parts)
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False, indent=2)


    # ── Resources API ─────────────────────────────────────────────────────────

    def list_resources(self) -> list[dict]:
        """Solicita resources/list al servidor MCP (solo si el servidor lo soporta)."""
        if not self._capabilities.get("resources"):
            return []
        result = self._request("resources/list", {})
        return (result or {}).get("resources", [])

    def read_resource(self, uri: str) -> str:
        """Lee el contenido de un resource MCP por URI."""
        result = self._request("resources/read", {"uri": uri})
        if result is None:
            return "Sin respuesta del servidor MCP (timeout)."
        contents = result.get("contents", [])
        parts = []
        for block in contents:
            if isinstance(block, dict):
                if block.get("text"):
                    parts.append(block["text"])
                elif block.get("blob"):
                    parts.append(f"[blob: {block.get('mimeType', 'binary')}]")
        return "\n".join(parts) if parts else json.dumps(result, ensure_ascii=False, indent=2)

    # ── Prompts API ───────────────────────────────────────────────────────────

    def list_prompts(self) -> list[dict]:
        """Solicita prompts/list al servidor MCP (solo si el servidor lo soporta)."""
        if not self._capabilities.get("prompts"):
            return []
        result = self._request("prompts/list", {})
        return (result or {}).get("prompts", [])

    def get_prompt(self, name: str, arguments: Optional[dict] = None) -> dict:
        """Solicita prompts/get al servidor MCP."""
        params: dict = {"name": name}
        if arguments:
            params["arguments"] = arguments
        result = self._request("prompts/get", params)
        return result or {}


# ── Conversión MCP tool → OOCode schema ───────────────────────────────────────

def mcp_tool_to_oocode(client: McpClient, tool: dict,
                       existing_names: frozenset[str] | None = None) -> tuple[str, Any, dict]:
    """Convierte una tool MCP en la tripla (name, fn, schema) de OOCode.

    Para el servidor bundled "oocode_assistant" se usa el nombre original sin prefijo
    (ej. "docker_logs") para que el modelo pueda invocarlas directamente.
    Para servidores externos se añade prefijo "mcp_{server}_" solo si el nombre
    colisiona con una tool ya registrada.
    """
    raw_name = tool.get("name", "")
    clean    = raw_name.replace("-", "_").replace(".", "_")

    # Servidores bundled → sin prefijo para máxima usabilidad
    if client.name in ("oocode_assistant", "oocode-assistant",
                       "system_assistant", "system-assistant"):
        oo_name = clean
    else:
        # Servidor externo: añadir prefijo solo si colisiona
        if existing_names is not None and clean not in existing_names:
            oo_name = clean
        else:
            oo_name = f"mcp_{client.name}_{clean}".replace("-", "_").replace(".", "_")

    input_schema = dict(tool.get("inputSchema", {}))
    if "type" not in input_schema:
        input_schema = {"type": "object", "properties": {}, **input_schema}

    schema = {
        "name":        oo_name,
        "description": tool.get("description",
                                f"MCP tool {raw_name} del servidor {client.name}"),
        "parameters":  input_schema,
    }

    def fn(**kwargs: Any) -> str:
        return client.call_tool(raw_name, kwargs)

    fn.__name__ = oo_name
    return oo_name, fn, schema


# ── Pool de clientes MCP ──────────────────────────────────────────────────────

class McpPool:
    """Gestiona todos los servidores MCP configurados."""

    def __init__(self, request_timeout: float = _DEFAULT_TIMEOUT) -> None:
        self._clients: dict[str, McpClient] = {}
        self._timeout = request_timeout

    def start_server(self, name: str, cmd: list[str],
                     env: Optional[dict] = None,
                     cwd: Optional[str] = None,
                     description: str = "") -> Optional[McpClient]:
        if name in self._clients:
            c = self._clients[name]
            if c.is_alive:
                return c
            # Muerto → reemplazar
            try:
                c.stop()
            except Exception:
                pass

        client = McpClient(name, cmd, env=env, cwd=cwd,
                           request_timeout=self._timeout,
                           description=description)
        try:
            client.start()
            self._clients[name] = client
            log.info("mcp_server_started", name=name, tools=len(client.tools))
            return client
        except Exception as exc:
            log.error("mcp_server_error", name=name, error=str(exc))
            self._clients[name] = client   # guardar igualmente para mostrar error en /mcp
            return None

    def all_oocode_tools(self) -> list[tuple[str, Any, dict]]:
        result = []
        seen_names: set[str] = set()
        for client in self._clients.values():
            if not client.is_alive:
                continue
            for tool in client.tools:
                entry = mcp_tool_to_oocode(client, tool,
                                           existing_names=frozenset(seen_names))
                seen_names.add(entry[0])
                result.append(entry)
        return result

    def get_client(self, name: str) -> Optional[McpClient]:
        return self._clients.get(name)

    def restart_server(self, name: str) -> Optional[McpClient]:
        """Para y reinicia un servidor MCP por nombre. Devuelve el cliente o None."""
        client = self._clients.get(name)
        if client is None:
            return None
        cmd = client._cmd
        env = client._env
        cwd = client._cwd
        try:
            client.stop()
        except Exception:
            pass
        del self._clients[name]
        return self.start_server(name, cmd, env=env, cwd=cwd)

    def pop_tools_changed(self) -> list[str]:
        """Devuelve nombres de servidores con tools modificadas y resetea el flag."""
        changed = []
        for name, client in self._clients.items():
            if client._tools_changed:
                client._tools_changed = False
                changed.append(name)
        return changed

    def resource_oocode_tools(self) -> list[tuple[str, Any, dict]]:
        """Genera tools list/read para servidores MCP con soporte de resources."""
        result = []
        for name, client in self._clients.items():
            if not client.is_alive:
                continue
            try:
                resources = client.list_resources()
            except Exception:
                continue
            if not resources:
                continue
            client._resource_count = len(resources)

            # Tool: listar resources
            list_name = f"mcp_{name}_list_resources".replace("-", "_")

            def _list_fn(c: McpClient = client, **_: Any) -> str:
                try:
                    res = c.list_resources()
                    if not res:
                        return "No hay resources disponibles."
                    lines = [
                        f"{r.get('uri', '?')}  — {r.get('name', '')}  {r.get('description', '')}"
                        for r in res
                    ]
                    return f"{len(res)} resource(s):\n" + "\n".join(lines)
                except Exception as exc:
                    return f"Error MCP resources: {exc}"

            _list_fn.__name__ = list_name
            result.append((list_name, _list_fn, {
                "name": list_name,
                "description": f"Lista los resources disponibles en el servidor MCP '{name}'.",
                "parameters": {"type": "object", "properties": {}},
            }))

            # Tool: leer resource
            read_name = f"mcp_{name}_read_resource".replace("-", "_")

            def _read_fn(uri: str, c: McpClient = client, **_: Any) -> str:
                try:
                    return c.read_resource(uri)
                except Exception as exc:
                    return f"Error MCP read_resource: {exc}"

            _read_fn.__name__ = read_name
            result.append((read_name, _read_fn, {
                "name": read_name,
                "description": f"Lee el contenido de un resource del servidor MCP '{name}'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "uri": {"type": "string", "description": "URI del resource a leer"},
                    },
                    "required": ["uri"],
                },
            }))
        return result

    def prompt_oocode_tools(self) -> list[tuple[str, Any, dict]]:
        """Genera tools list/get para servidores MCP con soporte de prompts."""
        result = []
        for name, client in self._clients.items():
            if not client.is_alive:
                continue
            try:
                prompts = client.list_prompts()
            except Exception:
                continue
            if not prompts:
                continue
            client._prompt_count = len(prompts)

            # Tool: listar prompts
            list_name = f"mcp_{name}_list_prompts".replace("-", "_")

            def _list_fn(c: McpClient = client, **_: Any) -> str:
                try:
                    ps = c.list_prompts()
                    if not ps:
                        return "No hay prompts disponibles."
                    lines = [
                        f"{p.get('name', '?')}  — {p.get('description', '')}"
                        for p in ps
                    ]
                    return f"{len(ps)} prompt(s):\n" + "\n".join(lines)
                except Exception as exc:
                    return f"Error MCP prompts: {exc}"

            _list_fn.__name__ = list_name
            result.append((list_name, _list_fn, {
                "name": list_name,
                "description": f"Lista los prompts disponibles en el servidor MCP '{name}'.",
                "parameters": {"type": "object", "properties": {}},
            }))

            # Tool: obtener prompt por nombre
            get_name = f"mcp_{name}_get_prompt".replace("-", "_")

            def _get_fn(prompt_name: str, arguments: Optional[dict] = None,
                        c: McpClient = client, **_: Any) -> str:
                try:
                    res = c.get_prompt(prompt_name, arguments or {})
                    if not res:
                        return "Sin respuesta del servidor MCP (timeout)."
                    description = res.get("description", "")
                    messages    = res.get("messages", [])
                    lines = []
                    if description:
                        lines.append(f"Descripción: {description}")
                    for msg in messages:
                        role    = msg.get("role", "")
                        content = msg.get("content", {})
                        if isinstance(content, dict):
                            text = content.get("text", json.dumps(content,
                                               ensure_ascii=False))
                        else:
                            text = str(content)
                        lines.append(f"\n[{role}]\n{text}")
                    return "\n".join(lines) if lines else json.dumps(
                        res, ensure_ascii=False, indent=2)
                except Exception as exc:
                    return f"Error MCP get_prompt: {exc}"

            _get_fn.__name__ = get_name
            result.append((get_name, _get_fn, {
                "name": get_name,
                "description": f"Obtiene el contenido de un prompt del servidor MCP '{name}'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt_name": {
                            "type": "string",
                            "description": "Nombre del prompt a obtener",
                        },
                        "arguments": {
                            "type": "object",
                            "description": "Argumentos opcionales del prompt",
                            "additionalProperties": {"type": "string"},
                        },
                    },
                    "required": ["prompt_name"],
                },
            }))
        return result

    def stop_all(self) -> None:
        for client in self._clients.values():
            try:
                client.stop()
            except Exception:
                pass
        self._clients.clear()

    def status(self) -> list[dict]:
        return [
            {
                "name":        name,
                "alive":       c.is_alive,
                "tools":       len(c.tools),
                "resources":   c._resource_count,
                "prompts":     c._prompt_count,
                "error":       c.error,
                "cmd":         c._cmd[0] if c._cmd else "",
                "description": c.description,
            }
            for name, c in self._clients.items()
        ]

    @property
    def client_count(self) -> int:
        return len(self._clients)

    @property
    def tool_count(self) -> int:
        return sum(len(c.tools) for c in self._clients.values() if c.is_alive)
