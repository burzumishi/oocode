#!/usr/bin/env python3
"""
http_client_assistant.py — MCP server para desarrollo y testing de APIs HTTP.
17 tools: http_request, http_get, http_headers, http_auth, http_upload,
          response_diff, openapi_validate, curl_import, websocket_send,
          sse_listen, mock_server_start, mock_server_stop, http_health_check,
          graphql_query, jwt_decode, http_batch, http_history.
Protocolo: stdio JSON-RPC 2.0 newline-delimited (igual que oocode_assistant.py).

Uso: python mcp_servers/http_client_assistant.py
Activar: ~/.oocode/oocode.json → mcp.httpClientAssistant.enabled = true
"""

from __future__ import annotations

import base64
import datetime
import difflib
import json
import re
import shlex
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# Límite de truncado de salida (configurable: tools.mcpMaxOutputChars en oocode.json)
def _mcp_max_output(default: int = 4000) -> int:
    try:
        from pathlib import Path as _P
        import json as _j
        _f = _P.home() / ".oocode" / "oocode.json"
        if _f.exists():
            return int(_j.loads(_f.read_text()).get("tools", {}).get("mcpMaxOutputChars", default))
    except Exception:
        pass
    return default


_MAX_OUTPUT = _mcp_max_output()
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

# ── Estado global ─────────────────────────────────────────────────────────────

_request_history: list[dict] = []
_MAX_HISTORY = 100
_mock_server: HTTPServer | None = None
_mock_server_thread: threading.Thread | None = None
_mock_routes: list[dict] = []


def _record_history(method: str, url: str, status: int | None, duration_ms: float,
                    error: str | None = None) -> None:
    entry = {
        "ts":          datetime.datetime.now().isoformat(timespec="seconds"),
        "method":      method.upper(),
        "url":         url,
        "status":      status,
        "duration_ms": round(duration_ms, 1),
        "error":       error,
    }
    _request_history.insert(0, entry)
    if len(_request_history) > _MAX_HISTORY:
        _request_history.pop()


# ── Helpers stdio ─────────────────────────────────────────────────────────────

def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _recv() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        return None
    return json.loads(line.strip())


def _ok(req_id: Any, result: Any) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "result": result})


def _err(req_id: Any, code: int, msg: str) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": msg}})


# ── HTTP core ─────────────────────────────────────────────────────────────────

def _build_request(url: str, method: str, headers: dict, body_str: str | None,
                   auth: dict | None, timeout: int) -> urllib.request.Request:
    req = urllib.request.Request(url, method=method.upper())
    req.add_header("User-Agent", "oocode-http-client/1.0")
    if auth:
        auth_type = str(auth.get("type", "")).lower()
        if auth_type == "bearer":
            token = auth.get("token", "")
            req.add_header("Authorization", f"Bearer {token}")
        elif auth_type == "basic":
            user = auth.get("username", "")
            pwd  = auth.get("password", "")
            cred = base64.b64encode(f"{user}:{pwd}".encode()).decode()
            req.add_header("Authorization", f"Basic {cred}")
    if isinstance(headers, dict):
        for k, v in headers.items():
            req.add_header(str(k), str(v))
    if body_str:
        req.data = body_str.encode("utf-8")
        if "Content-Type" not in {k.title() for k in (headers or {})}:
            req.add_header("Content-Type", "application/json")
    return req


def _do_request(url: str, method: str = "GET", headers: dict | None = None,
                body: str | None = None, auth: dict | None = None,
                timeout: int = 10, verify_ssl: bool = True,
                follow_redirects: bool = True) -> dict:
    """Executes an HTTP request and returns a result dict."""
    t0 = time.monotonic()
    headers = headers or {}
    timeout = min(int(timeout), 120)

    ctx = ssl.create_default_context() if verify_ssl else ssl._create_unverified_context()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ctx),
        urllib.request.HTTPRedirectHandler() if follow_redirects
        else urllib.request.BaseHandler(),
    )

    try:
        req = _build_request(url, method, headers, body, auth, timeout)
        with opener.open(req, timeout=timeout) as resp:
            status  = resp.status
            ct      = resp.headers.get("Content-Type", "")
            resp_headers = dict(resp.headers)
            raw_body = resp.read(64_000).decode(errors="replace")
            duration = (time.monotonic() - t0) * 1000
            _record_history(method, url, status, duration)
            return {"ok": True, "status": status, "content_type": ct,
                    "headers": resp_headers, "body": raw_body, "duration_ms": round(duration, 1)}
    except urllib.error.HTTPError as e:
        duration = (time.monotonic() - t0) * 1000
        body_err = e.read(8_000).decode(errors="replace")
        _record_history(method, url, e.code, duration)
        return {"ok": False, "status": e.code, "content_type": e.headers.get("Content-Type", ""),
                "headers": dict(e.headers), "body": body_err, "duration_ms": round(duration, 1)}
    except Exception as exc:
        duration = (time.monotonic() - t0) * 1000
        _record_history(method, url, None, duration, error=str(exc))
        return {"ok": False, "status": None, "error": str(exc), "duration_ms": round(duration, 1)}


def _format_response(r: dict, max_body: int = _MAX_OUTPUT) -> str:
    lines = []
    if "error" in r and r.get("status") is None:
        lines.append(f"Error: {r['error']}  ({r.get('duration_ms', 0):.0f}ms)")
        return "\n".join(lines)
    icon = "✓" if r.get("ok") else "✗"
    lines.append(f"{icon} HTTP {r.get('status')}  ({r.get('duration_ms', 0):.0f}ms)")
    ct = r.get("content_type", "")
    if ct:
        lines.append(f"Content-Type: {ct}")
    body = r.get("body", "")
    if "json" in ct.lower():
        try:
            body = json.dumps(json.loads(body), indent=2, ensure_ascii=False)
        except Exception:
            pass
    if body:
        lines.append("")
        lines.append(body[:max_body])
        if len(body) > max_body:
            lines.append(f"… [truncado, {len(body)} chars total]")
    return "\n".join(lines)


# ── Tool implementations ───────────────────────────────────────────────────────

def _tool_http_request(args: dict) -> str:
    """Realiza una petición HTTP (GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS)."""
    url    = args.get("url", "")
    method = str(args.get("method", "GET")).upper()
    if not url:
        return "Error: 'url' requerido."
    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
        return f"Error: método '{method}' no válido. Usa GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS."

    headers = args.get("headers") or {}
    body    = args.get("body")
    auth    = args.get("auth")
    timeout = int(args.get("timeout", 10))
    verify  = bool(args.get("verify_ssl", True))
    follow  = bool(args.get("follow_redirects", True))

    if isinstance(body, dict):
        body = json.dumps(body, ensure_ascii=False)

    r = _do_request(url, method, headers, body, auth, timeout, verify, follow)
    return _format_response(r)


def _tool_http_get(args: dict) -> str:
    """GET a una URL (desarrollo de APIs, health checks, servicios locales y remotos)."""
    url     = args.get("url", "")
    timeout = min(int(args.get("timeout", 10)), 60)
    headers = args.get("headers") or {}
    if not url:
        return "Error: 'url' requerido."
    r = _do_request(url, "GET", headers, None, None, timeout)
    return _format_response(r)


def _tool_http_headers(args: dict) -> str:
    """Obtiene solo los headers de respuesta de una URL (HEAD request)."""
    url     = args.get("url", "")
    timeout = min(int(args.get("timeout", 10)), 30)
    if not url:
        return "Error: 'url' requerido."
    r = _do_request(url, "HEAD", {}, None, None, timeout)
    if "error" in r and r.get("status") is None:
        return f"Error: {r['error']}"
    lines = [f"HTTP {r.get('status')}  ({r.get('duration_ms', 0):.0f}ms)"]
    for k, v in sorted((r.get("headers") or {}).items()):
        lines.append(f"{k}: {v}")
    return "\n".join(lines)


def _tool_http_auth(args: dict) -> str:
    """Genera un header Authorization (bearer/basic/api_key). Solo formatea — no envía datos."""
    auth_type = str(args.get("type", "bearer")).lower()
    if auth_type == "bearer":
        token = args.get("token", "")
        if not token:
            return "Error: 'token' requerido para bearer."
        return f"Authorization: Bearer {token}"
    elif auth_type == "basic":
        user = args.get("username", "")
        pwd  = args.get("password", "")
        if not user:
            return "Error: 'username' requerido para basic."
        cred = base64.b64encode(f"{user}:{pwd}".encode()).decode()
        return f"Authorization: Basic {cred}"
    elif auth_type == "api_key":
        key    = args.get("key", "")
        header = args.get("header", "X-API-Key")
        if not key:
            return "Error: 'key' requerido para api_key."
        return f"{header}: {key}"
    elif auth_type == "digest_info":
        return (
            "Digest Auth requiere múltiples rondas (nonce challenge/response).\n"
            "Usa http_request con headers Authorization manual o una librería como requests."
        )
    else:
        return f"Error: tipo '{auth_type}' no soportado. Usa bearer, basic, api_key."


def _tool_http_upload(args: dict) -> str:
    """Sube un fichero vía multipart/form-data a una URL."""
    url       = args.get("url", "")
    file_path = args.get("file_path", "")
    field     = args.get("field", "file")
    method    = str(args.get("method", "POST")).upper()
    headers   = args.get("headers") or {}
    extra     = args.get("extra_fields") or {}
    timeout   = min(int(args.get("timeout", 30)), 120)

    if not url:
        return "Error: 'url' requerido."
    if not file_path:
        return "Error: 'file_path' requerido."

    p = Path(file_path)
    if not p.exists():
        return f"Error: fichero no encontrado: {file_path}"

    # Build multipart/form-data manually (no external deps)
    boundary = f"----OOCodeBoundary{int(time.time())}"
    parts    = []

    for k, v in extra.items():
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{k}"\r\n\r\n'
            f"{v}\r\n"
        )

    file_data = p.read_bytes()
    parts.append(
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{p.name}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    )
    body_bytes = (
        "".join(parts).encode("utf-8")
        + file_data
        + f"\r\n--{boundary}--\r\n".encode("utf-8")
    )

    req = urllib.request.Request(url, data=body_bytes, method=method)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("User-Agent", "oocode-http-client/1.0")
    for k, v in headers.items():
        req.add_header(str(k), str(v))

    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status   = resp.status
            ct       = resp.headers.get("Content-Type", "")
            body_raw = resp.read(8_000).decode(errors="replace")
            duration = (time.monotonic() - t0) * 1000
            _record_history(method, url, status, duration)
            return f"✓ HTTP {status}  ({duration:.0f}ms)\nFichero: {p.name} ({len(file_data)} bytes)\n\n{body_raw[:2000]}"
    except urllib.error.HTTPError as e:
        duration = (time.monotonic() - t0) * 1000
        body_err = e.read(4_000).decode(errors="replace")
        _record_history(method, url, e.code, duration)
        return f"✗ HTTP {e.code}  ({duration:.0f}ms)\n{body_err}"
    except Exception as exc:
        return f"Error en upload: {exc}"


def _tool_response_diff(args: dict) -> str:
    """Compara dos respuestas HTTP (por URL o texto inline) y muestra el diff."""
    url_a  = args.get("url_a", "")
    url_b  = args.get("url_b", "")
    text_a = args.get("text_a", "")
    text_b = args.get("text_b", "")
    method = str(args.get("method", "GET")).upper()
    body   = args.get("body")
    headers= args.get("headers") or {}
    timeout= int(args.get("timeout", 10))
    label_a= args.get("label_a", url_a or "A")
    label_b= args.get("label_b", url_b or "B")

    if isinstance(body, dict):
        body = json.dumps(body, ensure_ascii=False)

    if url_a and not text_a:
        r = _do_request(url_a, method, headers, body, None, timeout)
        if "error" in r and r.get("status") is None:
            return f"Error en URL A: {r['error']}"
        text_a = r.get("body", "")
        if "json" in r.get("content_type", "").lower():
            try:
                text_a = json.dumps(json.loads(text_a), indent=2, ensure_ascii=False)
            except Exception:
                pass
        label_a = f"{url_a} (HTTP {r.get('status')})"

    if url_b and not text_b:
        r = _do_request(url_b, method, headers, body, None, timeout)
        if "error" in r and r.get("status") is None:
            return f"Error en URL B: {r['error']}"
        text_b = r.get("body", "")
        if "json" in r.get("content_type", "").lower():
            try:
                text_b = json.dumps(json.loads(text_b), indent=2, ensure_ascii=False)
            except Exception:
                pass
        label_b = f"{url_b} (HTTP {r.get('status')})"

    if not text_a and not text_b:
        return "Error: especifica (url_a, url_b) o (text_a, text_b)."

    lines_a = (text_a or "").splitlines(keepends=True)
    lines_b = (text_b or "").splitlines(keepends=True)
    diff    = list(difflib.unified_diff(lines_a, lines_b, fromfile=label_a, tofile=label_b, lineterm=""))

    if not diff:
        return "Sin diferencias entre A y B."

    return "\n".join(diff[:300]) + ("\n… [diff truncado]" if len(diff) > 300 else "")


def _tool_openapi_validate(args: dict) -> str:
    """Valida un request o response contra una spec OpenAPI/Swagger (JSON o YAML)."""
    spec_path   = args.get("spec_path", "")
    spec_url    = args.get("spec_url", "")
    endpoint    = args.get("endpoint", "")
    method      = str(args.get("method", "GET")).lower()
    req_body    = args.get("request_body")
    resp_body   = args.get("response_body")
    resp_status = args.get("response_status", 200)

    # Cargar spec
    spec_raw = ""
    if spec_path:
        p = Path(spec_path)
        if not p.exists():
            return f"Error: spec no encontrada: {spec_path}"
        spec_raw = p.read_text(errors="replace")
    elif spec_url:
        r = _do_request(spec_url, "GET", {}, None, None, 15)
        if "error" in r and r.get("status") is None:
            return f"Error obteniendo spec: {r['error']}"
        spec_raw = r.get("body", "")
    else:
        # Buscar spec en el directorio actual
        cwd = Path.cwd()
        candidates = list(cwd.glob("openapi*.json")) + list(cwd.glob("openapi*.yaml")) + \
                     list(cwd.glob("swagger*.json")) + list(cwd.glob("swagger*.yaml")) + \
                     list(cwd.glob("api*.json")) + list(cwd.glob("api*.yaml")) + \
                     list(cwd.glob("*.openapi.json")) + list(cwd.glob("*.openapi.yaml"))
        if not candidates:
            return "Error: especifica 'spec_path' o 'spec_url'. No se encontró spec en el directorio actual."
        spec_raw = candidates[0].read_text(errors="replace")
        spec_path = str(candidates[0])

    # Parsear spec
    try:
        if spec_raw.strip().startswith("{"):
            spec = json.loads(spec_raw)
        else:
            try:
                import yaml
                spec = yaml.safe_load(spec_raw)
            except ImportError:
                return "Error: spec YAML requiere PyYAML (pip install pyyaml). Usa spec JSON."
    except Exception as exc:
        return f"Error parseando spec: {exc}"

    results = []
    spec_title = spec.get("info", {}).get("title", "OpenAPI spec")
    spec_ver   = spec.get("info", {}).get("version", "?")
    results.append(f"Spec: {spec_title} v{spec_ver}  ({spec_path or spec_url})")

    # Buscar endpoint
    paths = spec.get("paths", {})
    if endpoint and endpoint not in paths:
        # Intentar match con path params
        matched = None
        for p in paths:
            pattern = re.sub(r"\{[^}]+\}", "[^/]+", re.escape(p))
            if re.fullmatch(pattern, endpoint):
                matched = p
                break
        if matched:
            results.append(f"Endpoint: {endpoint} → {matched}")
            endpoint = matched
        else:
            available = list(paths.keys())[:20]
            results.append(f"Endpoint '{endpoint}' no encontrado en spec.")
            results.append("Endpoints disponibles: " + ", ".join(available))
            return "\n".join(results)
    elif not endpoint:
        results.append(f"Endpoints en spec: {len(paths)}")
        for p, methods in list(paths.items())[:15]:
            ms = ", ".join(k.upper() for k in methods if k in ("get","post","put","patch","delete","head"))
            results.append(f"  {p}  [{ms}]")
        return "\n".join(results)

    path_def = paths[endpoint]
    method_def = path_def.get(method.lower())
    if not method_def:
        avail_methods = [k.upper() for k in path_def if k in ("get","post","put","patch","delete","head")]
        return f"Método {method.upper()} no definido para {endpoint}. Disponibles: {', '.join(avail_methods)}"

    results.append(f"Método: {method.upper()} {endpoint}")
    if "summary" in method_def:
        results.append(f"Summary: {method_def['summary']}")

    errors = []
    warnings = []

    # Validar request body
    if req_body is not None:
        rb_def = method_def.get("requestBody", {})
        if not rb_def:
            warnings.append("Spec no define requestBody para este endpoint.")
        else:
            ct_schema = rb_def.get("content", {}).get("application/json", {}).get("schema", {})
            if ct_schema:
                _validate_json_schema(req_body if isinstance(req_body, dict)
                                      else json.loads(req_body), ct_schema, "requestBody", errors, warnings)

    # Validar response body
    if resp_body is not None:
        responses = method_def.get("responses", {})
        resp_def = responses.get(str(resp_status)) or responses.get("default", {})
        if not resp_def:
            warnings.append(f"Spec no define respuesta {resp_status} para este endpoint.")
        else:
            ct_schema = resp_def.get("content", {}).get("application/json", {}).get("schema", {})
            if ct_schema:
                _validate_json_schema(resp_body if isinstance(resp_body, dict)
                                      else json.loads(resp_body), ct_schema, f"response/{resp_status}", errors, warnings)

    if errors:
        results.append(f"\n✗ {len(errors)} error(es):")
        results.extend(f"  - {e}" for e in errors)
    if warnings:
        results.append(f"\n⚠ {len(warnings)} aviso(s):")
        results.extend(f"  - {w}" for w in warnings)
    if not errors and not warnings:
        results.append("\n✓ Validación correcta.")

    return "\n".join(results)


def _validate_json_schema(data: Any, schema: dict, path: str,
                          errors: list, warnings: list) -> None:
    """Validación básica de JSON Schema (type, required, properties)."""
    schema_type = schema.get("type")
    if schema_type == "object":
        if not isinstance(data, dict):
            errors.append(f"{path}: se esperaba object, se obtuvo {type(data).__name__}")
            return
        required = schema.get("required", [])
        for field in required:
            if field not in data:
                errors.append(f"{path}.{field}: campo requerido ausente")
        props = schema.get("properties", {})
        for k, v in data.items():
            if props and k not in props:
                warnings.append(f"{path}.{k}: campo extra no definido en spec")
            elif k in props:
                _validate_json_schema(v, props[k], f"{path}.{k}", errors, warnings)
    elif schema_type == "array":
        if not isinstance(data, list):
            errors.append(f"{path}: se esperaba array, se obtuvo {type(data).__name__}")
        elif "items" in schema and data:
            _validate_json_schema(data[0], schema["items"], f"{path}[0]", errors, warnings)
    elif schema_type == "string":
        if not isinstance(data, str):
            errors.append(f"{path}: se esperaba string, se obtuvo {type(data).__name__}")
        elif "enum" in schema and data not in schema["enum"]:
            errors.append(f"{path}: valor '{data}' no en enum {schema['enum']}")
    elif schema_type == "integer":
        if not isinstance(data, int) or isinstance(data, bool):
            errors.append(f"{path}: se esperaba integer, se obtuvo {type(data).__name__}")
    elif schema_type == "number":
        if not isinstance(data, (int, float)) or isinstance(data, bool):
            errors.append(f"{path}: se esperaba number, se obtuvo {type(data).__name__}")
    elif schema_type == "boolean":
        if not isinstance(data, bool):
            errors.append(f"{path}: se esperaba boolean, se obtuvo {type(data).__name__}")


def _tool_curl_import(args: dict) -> str:
    """Parsea y ejecuta un comando curl. Extrae URL, método, headers, body y auth."""
    curl_cmd = args.get("command", "").strip()
    execute  = bool(args.get("execute", True))

    if not curl_cmd:
        return "Error: 'command' requerido. Ej: curl -X POST http://localhost:8080/api -H 'Content-Type: application/json' -d '{\"key\": \"value\"}'"

    # Normalizar — eliminar line continuations
    curl_cmd = re.sub(r"\\\s*\n\s*", " ", curl_cmd)
    if curl_cmd.startswith("curl "):
        curl_cmd = curl_cmd[5:]

    try:
        tokens = shlex.split(curl_cmd)
    except ValueError as exc:
        return f"Error parseando comando: {exc}"

    url     = ""
    method  = "GET"
    headers: dict[str, str] = {}
    body    = None
    auth    = None

    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in ("-X", "--request") and i + 1 < len(tokens):
            method = tokens[i + 1].upper()
            i += 2
        elif t in ("-H", "--header") and i + 1 < len(tokens):
            hdr = tokens[i + 1]
            if ":" in hdr:
                k, _, v = hdr.partition(":")
                headers[k.strip()] = v.strip()
            i += 2
        elif t in ("-d", "--data", "--data-raw", "--data-binary") and i + 1 < len(tokens):
            body = tokens[i + 1]
            if method == "GET":
                method = "POST"
            i += 2
        elif t == "--data-urlencode" and i + 1 < len(tokens):
            body = urllib.parse.quote_plus(tokens[i + 1])
            if method == "GET":
                method = "POST"
            i += 2
        elif t in ("-u", "--user") and i + 1 < len(tokens):
            user_pass = tokens[i + 1]
            if ":" in user_pass:
                user, pwd = user_pass.split(":", 1)
                auth = {"type": "basic", "username": user, "password": pwd}
            i += 2
        elif t in ("-L", "--location", "--compressed", "--silent", "-s"):
            i += 1
        elif t in ("-o", "--output", "--max-time", "--connect-timeout",
                   "--retry", "--proxy", "--cacert", "--cert") and i + 1 < len(tokens):
            i += 2  # skip value
        elif not t.startswith("-") and not url:
            url = t
            i += 1
        else:
            i += 1

    if not url:
        return "Error: no se encontró URL en el comando curl."

    # Extract Bearer from headers if present
    if "Authorization" in headers:
        auth_hdr = headers.pop("Authorization")
        if auth_hdr.lower().startswith("bearer "):
            auth = {"type": "bearer", "token": auth_hdr[7:]}
        else:
            headers["Authorization"] = auth_hdr  # restore

    summary = [
        f"Comando parseado:",
        f"  URL:     {url}",
        f"  Método:  {method}",
    ]
    if headers:
        summary.append(f"  Headers: {json.dumps(headers, ensure_ascii=False)}")
    if body:
        summary.append(f"  Body:    {body[:200]}")
    if auth:
        summary.append(f"  Auth:    {auth.get('type')}")

    if not execute:
        return "\n".join(summary)

    summary.append("")
    r = _do_request(url, method, headers, body, auth, timeout=30)
    summary.append(_format_response(r))
    return "\n".join(summary)


def _tool_websocket_send(args: dict) -> str:
    """Envía un mensaje por WebSocket y recibe la respuesta. Requiere websocket-client."""
    url     = args.get("url", "")
    message = args.get("message", "")
    timeout = min(int(args.get("timeout", 10)), 60)
    if not url:
        return "Error: 'url' requerido (ej. ws://localhost:8080/ws)."

    if isinstance(message, dict):
        message = json.dumps(message, ensure_ascii=False)

    try:
        import websocket  # websocket-client
    except ImportError:
        return (
            "websocket-client no instalado.\n"
            "Instala con: pip install websocket-client\n\n"
            "Alternativa: usa http_request con Upgrade: websocket header manualmente."
        )

    received: list[str] = []
    error_msg: list[str] = []

    def on_message(ws, msg):
        received.append(str(msg))

    def on_error(ws, err):
        error_msg.append(str(err))

    def on_open(ws):
        ws.send(message)

    t0 = time.monotonic()
    try:
        ws = websocket.WebSocketApp(url, on_message=on_message, on_error=on_error, on_open=on_open)
        wst = threading.Thread(target=ws.run_forever, daemon=True)
        wst.start()
        # Wait for at least one message or timeout
        deadline = t0 + timeout
        while time.monotonic() < deadline and not received and not error_msg:
            time.sleep(0.1)
        ws.close()
        wst.join(timeout=2)
    except Exception as exc:
        return f"Error WebSocket: {exc}"

    duration = (time.monotonic() - t0) * 1000
    if error_msg:
        return f"Error WebSocket: {error_msg[0]}"
    if not received:
        return f"Timeout WebSocket ({timeout}s) — sin respuesta."

    lines = [f"WebSocket {url}  ({duration:.0f}ms)", f"Mensaje enviado: {message[:200]}",
             f"Respuestas recibidas: {len(received)}", ""]
    for i, msg in enumerate(received[:10], 1):
        try:
            pretty = json.dumps(json.loads(msg), indent=2, ensure_ascii=False)
            lines.append(f"[{i}] {pretty[:1000]}")
        except Exception:
            lines.append(f"[{i}] {msg[:1000]}")
    return "\n".join(lines)


def _tool_sse_listen(args: dict) -> str:
    """Escucha un stream Server-Sent Events durante N segundos."""
    url      = args.get("url", "")
    duration = min(int(args.get("duration", 10)), 60)
    headers  = args.get("headers") or {}
    if not url:
        return "Error: 'url' requerido."

    req = urllib.request.Request(url)
    req.add_header("Accept", "text/event-stream")
    req.add_header("Cache-Control", "no-cache")
    req.add_header("User-Agent", "oocode-http-client/1.0")
    for k, v in headers.items():
        req.add_header(str(k), str(v))

    events: list[str] = []
    t0 = time.monotonic()

    try:
        with urllib.request.urlopen(req, timeout=duration + 2) as resp:
            status = resp.status
            if status != 200:
                return f"Error HTTP {status} al conectar a SSE."
            current_event: list[str] = []
            while time.monotonic() - t0 < duration:
                line = resp.readline().decode("utf-8", errors="replace").rstrip("\n\r")
                if line == "":
                    if current_event:
                        events.append("\n".join(current_event))
                        current_event = []
                else:
                    current_event.append(line)
                if len(events) >= 50:
                    break
    except Exception as exc:
        elapsed = time.monotonic() - t0
        if events:
            pass  # Timeout expected
        else:
            return f"Error conectando a SSE: {exc}"

    elapsed = time.monotonic() - t0
    lines = [f"SSE {url}  ({elapsed:.1f}s, {len(events)} eventos)"]
    for i, ev in enumerate(events[:20], 1):
        lines.append(f"\n[Evento {i}]")
        lines.append(ev[:500])
    if len(events) > 20:
        lines.append(f"\n… [{len(events) - 20} eventos más no mostrados]")
    if not events:
        lines.append("(sin eventos recibidos)")
    return "\n".join(lines)


# ── Mock server ────────────────────────────────────────────────────────────────

class _MockHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # Silenciar logs

    def _dispatch(self) -> None:
        global _mock_routes
        path = self.path.split("?")[0]
        method = self.command
        matched = None
        for route in _mock_routes:
            if (route.get("method", "GET").upper() == method and
                    re.fullmatch(route.get("path", ""), path)):
                matched = route
                break
            if route.get("method", "GET").upper() == "*":
                matched = route
                break
        if matched is None:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "not found", "path": path}).encode())
            return
        status = int(matched.get("status", 200))
        body   = matched.get("body", "")
        if isinstance(body, dict):
            body = json.dumps(body, ensure_ascii=False)
        body_bytes = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        resp_headers = matched.get("headers") or {}
        if "Content-Type" not in resp_headers:
            self.send_header("Content-Type", "application/json")
        for k, v in resp_headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body_bytes)

    def do_GET(self):    self._dispatch()
    def do_POST(self):   self._dispatch()
    def do_PUT(self):    self._dispatch()
    def do_PATCH(self):  self._dispatch()
    def do_DELETE(self): self._dispatch()
    def do_HEAD(self):   self._dispatch()
    def do_OPTIONS(self):self._dispatch()


def _tool_mock_server_start(args: dict) -> str:
    """Inicia un servidor HTTP mock en localhost para simular APIs durante el desarrollo."""
    global _mock_server, _mock_server_thread, _mock_routes
    port   = int(args.get("port", 8099))
    routes = args.get("routes") or []

    if _mock_server is not None:
        return f"El mock server ya está corriendo en puerto {_mock_server.server_address[1]}. Usa mock_server_stop primero."

    if not isinstance(routes, list):
        return "Error: 'routes' debe ser una lista de objetos {method, path, status, body, headers}."

    _mock_routes = routes

    try:
        _mock_server = HTTPServer(("127.0.0.1", port), _MockHandler)
        _mock_server_thread = threading.Thread(target=_mock_server.serve_forever, daemon=True)
        _mock_server_thread.start()
    except OSError as exc:
        _mock_server = None
        return f"Error iniciando mock server en puerto {port}: {exc}"

    lines = [f"✓ Mock server iniciado en http://127.0.0.1:{port}",
             f"  Rutas configuradas: {len(routes)}"]
    for r in routes[:10]:
        lines.append(f"  {r.get('method', 'GET').upper():6} {r.get('path', '/')}  → {r.get('status', 200)}")
    return "\n".join(lines)


def _tool_mock_server_stop(args: dict) -> str:
    """Detiene el servidor HTTP mock."""
    global _mock_server, _mock_server_thread, _mock_routes
    if _mock_server is None:
        return "No hay mock server en ejecución."
    port = _mock_server.server_address[1]
    _mock_server.shutdown()
    _mock_server = None
    _mock_server_thread = None
    _mock_routes = []
    return f"✓ Mock server detenido (puerto {port})."


def _tool_http_health_check(args: dict) -> str:
    """Comprueba el estado de múltiples endpoints (batch health check)."""
    urls_raw      = args.get("urls", "")
    timeout       = min(int(args.get("timeout", 5)), 30)
    expected      = int(args.get("expected_status", 200))
    show_body     = bool(args.get("show_body", False))

    if isinstance(urls_raw, list):
        urls = [u.strip() for u in urls_raw if u.strip()]
    else:
        urls = [u.strip() for u in str(urls_raw).split(",") if u.strip()]

    if not urls:
        return "Error: 'urls' requerido. Lista separada por comas o array JSON."

    results = [f"Health check  ({len(urls)} endpoint{'s' if len(urls) != 1 else ''})"]
    ok_count = 0
    for url in urls:
        r = _do_request(url, "GET", {}, None, None, timeout, verify_ssl=False)
        status   = r.get("status")
        duration = r.get("duration_ms", 0)
        error    = r.get("error")
        if error:
            results.append(f"  ✗  {url}  — Error: {error}")
        elif status == expected:
            ok_count += 1
            results.append(f"  ✓  {url}  HTTP {status}  ({duration:.0f}ms)")
        else:
            results.append(f"  ✗  {url}  HTTP {status}  ({duration:.0f}ms)  [esperado {expected}]")
        if show_body and r.get("body"):
            results.append(f"       {r['body'][:200]}")

    results.append(f"\n{ok_count}/{len(urls)} OK")
    return "\n".join(results)


def _tool_graphql_query(args: dict) -> str:
    """Ejecuta una query o mutation GraphQL."""
    url       = args.get("url", "")
    query     = args.get("query", "")
    variables = args.get("variables") or {}
    operation = args.get("operation_name", "")
    headers   = args.get("headers") or {}
    auth      = args.get("auth")
    timeout   = min(int(args.get("timeout", 15)), 60)

    if not url:
        return "Error: 'url' requerido."
    if not query:
        return "Error: 'query' requerido (GraphQL query o mutation string)."

    payload: dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables
    if operation:
        payload["operationName"] = operation

    body = json.dumps(payload, ensure_ascii=False)
    all_headers = {"Content-Type": "application/json", "Accept": "application/json"}
    all_headers.update(headers)

    r = _do_request(url, "POST", all_headers, body, auth, timeout)
    if "error" in r and r.get("status") is None:
        return f"Error: {r['error']}"

    lines = [f"GraphQL {url}  HTTP {r.get('status')}  ({r.get('duration_ms', 0):.0f}ms)"]
    raw_body = r.get("body", "")
    try:
        parsed = json.loads(raw_body)
        if "errors" in parsed:
            lines.append("\n✗ Errores GraphQL:")
            for e in parsed["errors"][:5]:
                msg = e.get("message", str(e))
                loc = e.get("locations", [{}])[0] if e.get("locations") else {}
                if loc:
                    lines.append(f"  [{loc.get('line', '?')}:{loc.get('column', '?')}] {msg}")
                else:
                    lines.append(f"  {msg}")
        if "data" in parsed:
            lines.append("\nData:")
            lines.append(json.dumps(parsed["data"], indent=2, ensure_ascii=False)[:3000])
    except Exception:
        lines.append(raw_body[:3000])
    return "\n".join(lines)


def _tool_jwt_decode(args: dict) -> str:
    """Decodifica y analiza un JWT (sin verificar firma). Útil para debugging de tokens."""
    token    = args.get("token", "").strip()
    show_raw = bool(args.get("show_raw", False))

    if not token:
        return "Error: 'token' requerido."

    # Remove Bearer prefix if present
    if token.lower().startswith("bearer "):
        token = token[7:].strip()

    parts = token.split(".")
    if len(parts) != 3:
        return f"Error: JWT inválido ({len(parts)} partes, se esperaban 3)."

    def _b64_decode(s: str) -> dict:
        # Add padding
        padded = s + "=" * (4 - len(s) % 4)
        raw = base64.urlsafe_b64decode(padded)
        return json.loads(raw)

    lines = []
    try:
        header = _b64_decode(parts[0])
        lines.append("=== Header ===")
        lines.append(json.dumps(header, indent=2, ensure_ascii=False))

        payload = _b64_decode(parts[1])
        lines.append("\n=== Payload ===")
        lines.append(json.dumps(payload, indent=2, ensure_ascii=False))

        # Análisis temporal
        now = int(time.time())
        if "exp" in payload:
            exp = int(payload["exp"])
            if exp < now:
                diff = now - exp
                _ts = datetime.datetime.fromtimestamp(exp, tz=datetime.timezone.utc).isoformat()
                lines.append(f"\n⚠ Token EXPIRADO hace {diff}s ({_ts})")
            else:
                diff = exp - now
                _ts = datetime.datetime.fromtimestamp(exp, tz=datetime.timezone.utc).isoformat()
                lines.append(f"\n✓ Token válido por {diff}s más (expira {_ts})")
        if "iat" in payload:
            iat = int(payload["iat"])
            _ts = datetime.datetime.fromtimestamp(iat, tz=datetime.timezone.utc).isoformat()
            lines.append(f"  Emitido:  {_ts}")
        if "nbf" in payload:
            nbf = int(payload["nbf"])
            if nbf > now:
                _ts = datetime.datetime.fromtimestamp(nbf, tz=datetime.timezone.utc).isoformat()
                lines.append(f"⚠ Token no válido hasta: {_ts}")

        alg = header.get("alg", "?")
        lines.append(f"\n  Algoritmo: {alg}")
        if alg.startswith("HS"):
            lines.append("  (Symmetric — la firma requiere el secret para verificar)")
        elif alg.startswith("RS") or alg.startswith("ES"):
            lines.append("  (Asymmetric — la firma puede verificarse con la clave pública)")
        elif alg == "none":
            lines.append("  ⚠ alg=none — sin firma (inseguro)")

        if show_raw:
            lines.append(f"\n=== Raw parts ===")
            lines.append(f"Header:    {parts[0]}")
            lines.append(f"Payload:   {parts[1]}")
            lines.append(f"Signature: {parts[2][:40]}…")

    except Exception as exc:
        return f"Error decodificando JWT: {exc}"

    return "\n".join(lines)


def _tool_http_batch(args: dict) -> str:
    """Ejecuta múltiples requests HTTP en secuencia y muestra un resumen."""
    requests_list = args.get("requests") or []
    stop_on_error = bool(args.get("stop_on_error", False))
    delay_ms      = min(int(args.get("delay_ms", 0)), 5000)

    if not requests_list:
        return "Error: 'requests' requerido (lista de {url, method, body, headers, name})."

    results = [f"Batch HTTP  ({len(requests_list)} requests)"]
    ok_count = 0
    for i, req_def in enumerate(requests_list, 1):
        url     = req_def.get("url", "")
        method  = str(req_def.get("method", "GET")).upper()
        name    = req_def.get("name", f"req{i}")
        body    = req_def.get("body")
        headers = req_def.get("headers") or {}
        auth    = req_def.get("auth")
        timeout = int(req_def.get("timeout", 10))

        if not url:
            results.append(f"\n[{i}] {name}: Error — 'url' ausente")
            if stop_on_error:
                break
            continue

        if isinstance(body, dict):
            body = json.dumps(body, ensure_ascii=False)

        r = _do_request(url, method, headers, body, auth, timeout)
        status = r.get("status")
        dur    = r.get("duration_ms", 0)
        err    = r.get("error")

        if err:
            results.append(f"\n[{i}] {name}: ✗ Error — {err}")
            if stop_on_error:
                break
        else:
            icon = "✓" if r.get("ok") else "✗"
            ok_count += (1 if r.get("ok") else 0)
            results.append(f"\n[{i}] {name}: {icon} HTTP {status}  ({dur:.0f}ms)  {method} {url}")
            raw_body = r.get("body", "")
            if raw_body:
                if "json" in r.get("content_type", "").lower():
                    try:
                        raw_body = json.dumps(json.loads(raw_body), indent=2, ensure_ascii=False)
                    except Exception:
                        pass
                results.append(f"    {raw_body[:300]}" + (" …" if len(raw_body) > 300 else ""))
            if stop_on_error and not r.get("ok"):
                break

        if delay_ms > 0 and i < len(requests_list):
            time.sleep(delay_ms / 1000)

    results.append(f"\n{ok_count}/{len(requests_list)} exitosos")
    return "\n".join(results)


def _tool_http_history(args: dict) -> str:
    """Muestra el historial de requests HTTP de la sesión actual."""
    limit  = min(int(args.get("limit", 20)), 100)
    filter_url = args.get("url_contains", "")

    history = _request_history
    if filter_url:
        history = [h for h in history if filter_url in h.get("url", "")]

    if not history:
        return "Historial HTTP vacío."

    lines = [f"Historial HTTP  ({min(limit, len(history))} de {len(history)} requests)"]
    for h in history[:limit]:
        status = h.get("status")
        dur    = h.get("duration_ms", 0)
        icon   = "✓" if status and 200 <= status < 400 else "✗"
        error  = f"  ERROR: {h['error']}" if h.get("error") else ""
        lines.append(
            f"  {icon}  {h['ts']}  {h['method']:6} {status or '---'}  "
            f"({dur:.0f}ms)  {h['url']}{error}"
        )
    return "\n".join(lines)


# ── Resources ─────────────────────────────────────────────────────────────────

def _resource_project_openapi() -> str:
    """Detecta specs OpenAPI/Swagger en el proyecto."""
    cwd = Path.cwd()
    parts = [f"## OpenAPI / Swagger specs en {cwd}\n"]

    patterns = ["openapi*.json", "openapi*.yaml", "openapi*.yml",
                "swagger*.json", "swagger*.yaml", "swagger*.yml",
                "api*.json", "api*.yaml", "api*.yml",
                "*.openapi.json", "*.openapi.yaml",
                "docs/api*.json", "docs/api*.yaml",
                "spec/*.json", "spec/*.yaml"]

    found = set()
    for pat in patterns:
        for f in list(cwd.glob(pat))[:3]:
            if ".venv" not in str(f) and "node_modules" not in str(f):
                found.add(f)

    if found:
        for spec_file in sorted(found):
            rel = spec_file.relative_to(cwd)
            try:
                raw = spec_file.read_text(errors="replace")
                try:
                    spec = json.loads(raw)
                    title   = spec.get("info", {}).get("title", "?")
                    version = spec.get("info", {}).get("version", "?")
                    paths   = len(spec.get("paths", {}))
                    openapi = spec.get("openapi") or spec.get("swagger", "?")
                    parts.append(f"### {rel}")
                    parts.append(f"  Título:    {title} v{version}")
                    parts.append(f"  OpenAPI:   {openapi}")
                    parts.append(f"  Endpoints: {paths}")
                    if paths:
                        for ep, methods in list(spec.get("paths", {}).items())[:8]:
                            ms = ", ".join(k.upper() for k in methods
                                          if k in ("get","post","put","patch","delete"))
                            parts.append(f"    {ep}  [{ms}]")
                except Exception:
                    size = len(raw)
                    parts.append(f"### {rel}  ({size} bytes, no parseado)")
            except Exception:
                pass
    else:
        parts.append("(no se encontraron ficheros OpenAPI/Swagger en el directorio actual)")
        parts.append("Busca: openapi.json, swagger.yaml, api.yaml en el raíz o en docs/")

    # También buscar URLs de API en .env
    env_file = cwd / ".env"
    if env_file.exists():
        env_text = env_file.read_text(errors="replace")
        api_lines = [ln for ln in env_text.splitlines()
                     if re.search(r"(API_URL|BASE_URL|ENDPOINT|HOST|SERVER)", ln, re.I)
                     and "=" in ln]
        if api_lines:
            parts.append("\n## Variables de entorno relacionadas con API")
            for ln in api_lines[:10]:
                k, _, v = ln.partition("=")
                # Mask tokens/keys
                v = re.sub(r'(?i)(token|key|secret|password)[^=]*=\s*\S+', r'\1=***', v)
                parts.append(f"  {k.strip()} = {v.strip()}")

    return "\n".join(parts)


_RESOURCES = [
    {
        "uri":         "project://openapi",
        "name":        "Specs OpenAPI / Swagger",
        "description": "Ficheros OpenAPI/Swagger detectados en el proyecto + variables de entorno de API",
        "mimeType":    "text/plain",
    },
]

_RESOURCE_FNS = {
    "project://openapi": _resource_project_openapi,
}


# ── Prompts ────────────────────────────────────────────────────────────────────

_PROMPTS: dict[str, dict] = {
    "api_testing": {
        "description": "Plantilla para probar un endpoint REST (happy path + edge cases + errores)",
        "arguments": [
            {"name": "endpoint", "description": "URL del endpoint, ej. http://localhost:8080/api/users", "required": True},
            {"name": "method",   "description": "Método HTTP (GET/POST/PUT/PATCH/DELETE)",              "required": False},
        ],
    },
    "rest_client_setup": {
        "description": "Guía para configurar un flujo de trabajo HTTP con el agente (base URL, auth, colección de requests)",
        "arguments": [],
    },
    "api_debugging": {
        "description": "Checklist y herramientas para debuggear problemas en una API HTTP",
        "arguments": [
            {"name": "error", "description": "Descripción del error o comportamiento inesperado", "required": False},
        ],
    },
}


def _prompt_get(name: str, arguments: dict) -> list[dict]:
    if name == "api_testing":
        endpoint = arguments.get("endpoint", "http://localhost:8080/api/example")
        method   = arguments.get("method", "GET").upper()
        return [{"role": "user", "content": {"type": "text", "text": f"""Prueba el endpoint `{method} {endpoint}` usando las herramientas HTTP disponibles:

1. **Happy path** — request básico con `http_request` o `http_get`, verifica status 2xx
2. **Response structure** — usa `openapi_validate` si hay spec disponible (`project://openapi`)
3. **Edge cases** — prueba con parámetros límite, vacíos, inválidos
4. **Autenticación** — si el endpoint requiere auth, prueba sin token (esperado 401) y con token inválido (esperado 401/403)
5. **Errores esperados** — verifica que los errores retornan el status code correcto

Empieza con `http_get` o `http_request` para ver la respuesta base."""}}]

    elif name == "rest_client_setup":
        return [{"role": "user", "content": {"type": "text", "text": """Configura un flujo de trabajo para probar la API de este proyecto:

1. **Detecta la spec** — usa `project://openapi` para ver si hay OpenAPI/Swagger
2. **Identifica base URL** — busca en .env (API_URL, BASE_URL) o configuración del proyecto
3. **Prueba conectividad** — `http_health_check` en el endpoint base
4. **Autenticación** — si se requiere, configura el header con `http_auth` y úsalo en requests
5. **Colección de requests** — usa `http_batch` para ejecutar múltiples endpoints a la vez

Si tienes un comando curl de ejemplo, usa `curl_import` para ejecutarlo directamente."""}}]

    elif name == "api_debugging":
        error = arguments.get("error", "(describe el error)")
        return [{"role": "user", "content": {"type": "text", "text": f"""Debugging de API: {error}

Checklist:
1. `http_health_check` — ¿el servidor responde?
2. `http_headers` — ¿qué headers devuelve? (CORS, Content-Type, WWW-Authenticate)
3. `http_request` con método correcto y body completo — ¿reproduce el error?
4. `jwt_decode` — si hay token, ¿está expirado?
5. `http_history` — ¿muestra el patrón de errores?
6. `response_diff` — ¿cambió el response entre entorno local y staging?
7. `openapi_validate` — ¿el request/response cumple la spec?

Empieza con `http_health_check` para confirmar que el servidor está activo."""}}]

    return [{"role": "user", "content": {"type": "text", "text": f"(prompt '{name}' no encontrado)"}}]


# ── Tools catalog ─────────────────────────────────────────────────────────────

_TOOLS = [
    {
        "name": "http_request",
        "description": "Realiza una petición HTTP completa: GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS con body, headers, auth y timeout. Ideal para desarrollo y testing de APIs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url":              {"type": "string",  "description": "URL completa del endpoint"},
                "method":           {"type": "string",  "description": "Método HTTP: GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS (default: GET)"},
                "body":             {"type": ["string", "object"], "description": "Body de la petición: string JSON o objeto (se serializa automáticamente)"},
                "headers":          {"type": "object",  "description": "Headers HTTP adicionales como objeto JSON"},
                "auth":             {"type": "object",  "description": "Auth: {type: 'bearer', token: '...'} o {type: 'basic', username: '...', password: '...'}"},
                "timeout":          {"type": "integer", "description": "Timeout en segundos (max 120, default 10)"},
                "verify_ssl":       {"type": "boolean", "description": "Verificar certificado SSL (default: true)"},
                "follow_redirects": {"type": "boolean", "description": "Seguir redirecciones 3xx (default: true)"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "http_get",
        "description": "GET rápido a una URL. Formatea automáticamente JSON. Útil para APIs locales, health checks y endpoints de desarrollo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url":     {"type": "string",  "description": "URL a consultar"},
                "timeout": {"type": "integer", "description": "Timeout en segundos (max 60, default 10)"},
                "headers": {"type": "object",  "description": "Headers HTTP adicionales"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "http_headers",
        "description": "Obtiene solo los headers de respuesta de una URL sin descargar el body (HEAD request).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url":     {"type": "string",  "description": "URL a inspeccionar"},
                "timeout": {"type": "integer", "description": "Timeout en segundos (max 30, default 10)"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "http_auth",
        "description": "Genera el valor del header Authorization para bearer, basic o api_key. No realiza ninguna petición — solo formatea la credencial.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "type":     {"type": "string", "description": "Tipo de auth: bearer, basic, api_key"},
                "token":    {"type": "string", "description": "Token (para bearer)"},
                "username": {"type": "string", "description": "Usuario (para basic)"},
                "password": {"type": "string", "description": "Contraseña (para basic)"},
                "key":      {"type": "string", "description": "Clave API (para api_key)"},
                "header":   {"type": "string", "description": "Nombre del header (para api_key, default: X-API-Key)"},
            },
            "required": ["type"],
        },
    },
    {
        "name": "http_upload",
        "description": "Sube un fichero a un endpoint mediante multipart/form-data.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url":          {"type": "string",  "description": "URL del endpoint de upload"},
                "file_path":    {"type": "string",  "description": "Ruta absoluta del fichero a subir"},
                "field":        {"type": "string",  "description": "Nombre del campo multipart (default: file)"},
                "method":       {"type": "string",  "description": "Método HTTP (default: POST)"},
                "headers":      {"type": "object",  "description": "Headers adicionales"},
                "extra_fields": {"type": "object",  "description": "Campos de formulario adicionales"},
                "timeout":      {"type": "integer", "description": "Timeout en segundos (max 120, default 30)"},
            },
            "required": ["url", "file_path"],
        },
    },
    {
        "name": "response_diff",
        "description": "Compara dos respuestas HTTP (por URL o texto inline) y muestra el diff. Útil para verificar que un cambio no rompe la API.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url_a":   {"type": "string", "description": "Primera URL a comparar"},
                "url_b":   {"type": "string", "description": "Segunda URL a comparar"},
                "text_a":  {"type": "string", "description": "Primer texto inline (alternativa a url_a)"},
                "text_b":  {"type": "string", "description": "Segundo texto inline (alternativa a url_b)"},
                "method":  {"type": "string", "description": "Método HTTP para ambas URLs (default: GET)"},
                "body":    {"type": ["string", "object"], "description": "Body para ambas requests (si aplica)"},
                "headers": {"type": "object", "description": "Headers para ambas requests"},
                "label_a": {"type": "string", "description": "Etiqueta para el lado A del diff"},
                "label_b": {"type": "string", "description": "Etiqueta para el lado B del diff"},
                "timeout": {"type": "integer","description": "Timeout en segundos (default: 10)"},
            },
        },
    },
    {
        "name": "openapi_validate",
        "description": "Valida un request o response contra una spec OpenAPI/Swagger. Detecta specs en el proyecto automáticamente si no se especifica.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "spec_path":     {"type": "string",  "description": "Ruta al fichero OpenAPI JSON/YAML"},
                "spec_url":      {"type": "string",  "description": "URL de la spec OpenAPI (alternativa a spec_path)"},
                "endpoint":      {"type": "string",  "description": "Path del endpoint, ej. /api/users/{id}"},
                "method":        {"type": "string",  "description": "Método HTTP (default: GET)"},
                "request_body":  {"type": ["object", "string"], "description": "Body del request a validar (objeto o string JSON)"},
                "response_body": {"type": ["object", "string"], "description": "Body del response a validar (objeto o string JSON)"},
                "response_status":{"type": "integer","description": "Status code del response (default: 200)"},
            },
        },
    },
    {
        "name": "curl_import",
        "description": "Parsea un comando curl completo y lo ejecuta. Extrae método, headers, body y auth automáticamente.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string",  "description": "Comando curl completo (con o sin 'curl' al inicio)"},
                "execute": {"type": "boolean", "description": "Ejecutar el request tras parsear (default: true)"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "websocket_send",
        "description": "Envía un mensaje por WebSocket y recibe la respuesta. Requiere pip install websocket-client.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url":     {"type": "string",  "description": "URL WebSocket: ws://... o wss://..."},
                "message": {"type": ["string", "object"], "description": "Mensaje a enviar (string o objeto JSON)"},
                "timeout": {"type": "integer", "description": "Tiempo de espera en segundos (max 60, default 10)"},
            },
            "required": ["url", "message"],
        },
    },
    {
        "name": "sse_listen",
        "description": "Escucha un stream Server-Sent Events (SSE) durante N segundos y muestra los eventos recibidos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url":      {"type": "string",  "description": "URL del endpoint SSE"},
                "duration": {"type": "integer", "description": "Segundos de escucha (max 60, default 10)"},
                "headers":  {"type": "object",  "description": "Headers adicionales (ej. Authorization)"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "mock_server_start",
        "description": "Inicia un servidor HTTP mock en localhost para simular respuestas de API durante el desarrollo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "port":   {"type": "integer", "description": "Puerto local (default: 8099)"},
                "routes": {
                    "type":        "array",
                    "description": "Lista de rutas: [{method, path, status, body, headers}]. path acepta regex.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "method":  {"type": "string",  "description": "Método HTTP o '*' para cualquiera"},
                            "path":    {"type": "string",  "description": "Path (regex)"},
                            "status":  {"type": "integer", "description": "HTTP status code (default: 200)"},
                            "body":    {                   "description": "Body de respuesta (string o objeto JSON)"},
                            "headers": {"type": "object",  "description": "Headers de respuesta"},
                        },
                    },
                },
            },
        },
    },
    {
        "name": "mock_server_stop",
        "description": "Detiene el servidor HTTP mock iniciado con mock_server_start.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "http_health_check",
        "description": "Comprueba el estado de múltiples endpoints en una sola llamada. Ideal para monitorización o validación tras un deploy.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "urls":            {"type": ["string", "array"], "description": "URLs a verificar: string separado por comas o array JSON"},
                "timeout":         {"type": "integer", "description": "Timeout por URL en segundos (max 30, default 5)"},
                "expected_status": {"type": "integer", "description": "Status code esperado (default: 200)"},
                "show_body":       {"type": "boolean", "description": "Mostrar fragmento del body (default: false)"},
            },
            "required": ["urls"],
        },
    },
    {
        "name": "graphql_query",
        "description": "Ejecuta una query o mutation GraphQL contra un endpoint.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url":            {"type": "string",  "description": "URL del endpoint GraphQL"},
                "query":          {"type": "string",  "description": "Query o mutation GraphQL"},
                "variables":      {"type": "object",  "description": "Variables de la query"},
                "operation_name": {"type": "string",  "description": "Nombre de la operación (si la query tiene múltiples)"},
                "headers":        {"type": "object",  "description": "Headers adicionales"},
                "auth":           {"type": "object",  "description": "Auth: {type: 'bearer', token: '...'}"},
                "timeout":        {"type": "integer", "description": "Timeout en segundos (max 60, default 15)"},
            },
            "required": ["url", "query"],
        },
    },
    {
        "name": "jwt_decode",
        "description": "Decodifica y analiza un JWT (sin verificar la firma). Muestra header, payload, expiración y algoritmo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "token":    {"type": "string",  "description": "Token JWT o 'Bearer <token>'"},
                "show_raw": {"type": "boolean", "description": "Mostrar las partes base64 raw (default: false)"},
            },
            "required": ["token"],
        },
    },
    {
        "name": "http_batch",
        "description": "Ejecuta múltiples requests HTTP en secuencia y muestra un resumen. Útil para smoke tests o flows de API.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "requests": {
                    "type":        "array",
                    "description": "Lista de requests: [{url, method, body, headers, auth, timeout, name}]",
                    "items": {
                        "type": "object",
                        "properties": {
                            "url":     {"type": "string", "description": "URL"},
                            "method":  {"type": "string", "description": "Método HTTP (default: GET)"},
                            "body":    {                  "description": "Body"},
                            "headers": {"type": "object", "description": "Headers"},
                            "auth":    {"type": "object", "description": "Auth"},
                            "name":    {"type": "string", "description": "Nombre descriptivo"},
                            "timeout": {"type": "integer","description": "Timeout (default: 10)"},
                        },
                        "required": ["url"],
                    },
                },
                "stop_on_error": {"type": "boolean", "description": "Parar al primer error (default: false)"},
                "delay_ms":      {"type": "integer", "description": "Espera entre requests en ms (max 5000, default 0)"},
            },
            "required": ["requests"],
        },
    },
    {
        "name": "http_history",
        "description": "Muestra el historial de requests HTTP realizados en esta sesión.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit":       {"type": "integer", "description": "Número máximo de entradas (max 100, default 20)"},
                "url_contains": {"type": "string", "description": "Filtrar por fragmento de URL"},
            },
        },
    },
]

_TOOL_FNS: dict[str, Any] = {
    "http_request":      _tool_http_request,
    "http_get":          _tool_http_get,
    "http_headers":      _tool_http_headers,
    "http_auth":         _tool_http_auth,
    "http_upload":       _tool_http_upload,
    "response_diff":     _tool_response_diff,
    "openapi_validate":  _tool_openapi_validate,
    "curl_import":       _tool_curl_import,
    "websocket_send":    _tool_websocket_send,
    "sse_listen":        _tool_sse_listen,
    "mock_server_start": _tool_mock_server_start,
    "mock_server_stop":  _tool_mock_server_stop,
    "http_health_check": _tool_http_health_check,
    "graphql_query":     _tool_graphql_query,
    "jwt_decode":        _tool_jwt_decode,
    "http_batch":        _tool_http_batch,
    "http_history":      _tool_http_history,
}


# ── MCP handle loop ───────────────────────────────────────────────────────────

def _handle(req: dict) -> None:
    method  = req.get("method", "")
    params  = req.get("params") or {}
    req_id  = req.get("id")

    if method == "initialize":
        _ok(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}, "prompts": {}, "resources": {}},
            "serverInfo": {"name": "http-client-assistant", "version": "1.0"},
        })

    elif method == "tools/list":
        _ok(req_id, {"tools": _TOOLS})

    elif method == "tools/call":
        name      = params.get("name", "")
        tool_args = params.get("arguments") or {}
        fn = _TOOL_FNS.get(name)
        if fn is None:
            _err(req_id, -32601, f"Tool desconocida: {name}")
            return
        try:
            result = fn(tool_args)
            _ok(req_id, {"content": [{"type": "text", "text": str(result)}]})
        except Exception as exc:
            _err(req_id, -32603, f"Error en tool '{name}': {exc}")

    elif method == "prompts/list":
        _ok(req_id, {"prompts": [
            {"name": k, "description": v["description"], "arguments": v.get("arguments", [])}
            for k, v in _PROMPTS.items()
        ]})

    elif method == "prompts/get":
        name      = params.get("name", "")
        arguments = params.get("arguments") or {}
        if name not in _PROMPTS:
            _err(req_id, -32601, f"Prompt desconocido: {name}")
            return
        messages = _prompt_get(name, arguments)
        _ok(req_id, {"description": _PROMPTS[name]["description"], "messages": messages})

    elif method == "resources/list":
        _ok(req_id, {"resources": _RESOURCES})

    elif method == "resources/read":
        uri = params.get("uri", "")
        fn  = _RESOURCE_FNS.get(uri)
        if fn is None:
            _err(req_id, -32601, f"Recurso desconocido: {uri}")
            return
        try:
            content = fn()
            _ok(req_id, {"contents": [{"uri": uri, "mimeType": "text/plain", "text": content}]})
        except Exception as exc:
            _err(req_id, -32603, f"Error leyendo recurso '{uri}': {exc}")

    elif req_id is not None:
        _err(req_id, -32601, f"Método desconocido: {method}")


def main() -> None:
    sys.stderr.write(
        f"[http-client-assistant] MCP server v1.0 iniciado  "
        f"tools: {len(_TOOLS)}  prompts: {len(_PROMPTS)}  resources: {len(_RESOURCES)}\n"
    )
    sys.stderr.flush()
    while True:
        try:
            req = _recv()
            if req is None:
                break
            _handle(req)
        except (EOFError, BrokenPipeError):
            break
        except Exception as exc:
            sys.stderr.write(f"[http-client-assistant] Error: {exc}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()
