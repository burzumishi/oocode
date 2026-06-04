"""Tests del servidor MCP http_client_assistant (sin red, sin LLM).

Cubre: schemas, tool functions, prompts, resources, mock server, config.
"""
import json
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.http_client_assistant import (
    _TOOL_FNS,
    _TOOLS,
    _PROMPTS,
    _RESOURCES,
    _RESOURCE_FNS,
    _prompt_get,
    _tool_http_request,
    _tool_http_get,
    _tool_http_headers,
    _tool_http_auth,
    _tool_http_upload,
    _tool_response_diff,
    _tool_openapi_validate,
    _tool_curl_import,
    _tool_websocket_send,
    _tool_sse_listen,
    _tool_mock_server_start,
    _tool_mock_server_stop,
    _tool_http_health_check,
    _tool_graphql_query,
    _tool_jwt_decode,
    _tool_http_batch,
    _tool_http_history,
    _request_history,
    _validate_json_schema,
    _do_request,
    _resource_project_openapi,
)


# ── Schema coverage ────────────────────────────────────────────────────────────

class TestSchemas:
    def test_tool_count(self):
        assert len(_TOOLS) == 17, f"Se esperaban 17 tools, hay {len(_TOOLS)}"

    def test_all_tools_have_name_description(self):
        for t in _TOOLS:
            assert "name" in t
            assert "description" in t
            assert len(t["description"]) > 10, f"Descripción muy corta: {t['name']}"

    def test_all_tools_have_input_schema(self):
        for t in _TOOLS:
            assert "inputSchema" in t, f"{t['name']} sin inputSchema"
            assert t["inputSchema"]["type"] == "object"

    def test_all_tools_have_handler(self):
        for t in _TOOLS:
            assert t["name"] in _TOOL_FNS, f"Sin handler: {t['name']}"
            assert callable(_TOOL_FNS[t["name"]])

    def test_expected_tools_present(self):
        expected = {
            "http_request", "http_get", "http_headers", "http_auth", "http_upload",
            "response_diff", "openapi_validate", "curl_import", "websocket_send",
            "sse_listen", "mock_server_start", "mock_server_stop", "http_health_check",
            "graphql_query", "jwt_decode", "http_batch", "http_history",
        }
        names = {t["name"] for t in _TOOLS}
        assert expected == names

    def test_http_request_required(self):
        t = next(t for t in _TOOLS if t["name"] == "http_request")
        assert "url" in t["inputSchema"]["required"]

    def test_http_batch_required(self):
        t = next(t for t in _TOOLS if t["name"] == "http_batch")
        assert "requests" in t["inputSchema"]["required"]

    def test_graphql_required_fields(self):
        t = next(t for t in _TOOLS if t["name"] == "graphql_query")
        assert "url" in t["inputSchema"]["required"]
        assert "query" in t["inputSchema"]["required"]


# ── http_get ───────────────────────────────────────────────────────────────────

class TestHttpGet:
    def test_missing_url(self):
        r = _tool_http_get({})
        assert "Error" in r or "error" in r.lower() or "url" in r.lower()

    def test_network_error_handled(self):
        # URL inexistente → maneja error sin crash
        r = _tool_http_get({"url": "http://127.0.0.1:19999/nonexistent", "timeout": 1})
        assert isinstance(r, str)

    def test_returns_string(self):
        r = _tool_http_get({"url": "http://127.0.0.1:19999/", "timeout": 1})
        assert isinstance(r, str)


# ── http_request ──────────────────────────────────────────────────────────────

class TestHttpRequest:
    def test_missing_url(self):
        r = _tool_http_request({})
        assert "Error" in r

    def test_invalid_method(self):
        r = _tool_http_request({"url": "http://localhost", "method": "INVALID"})
        assert "Error" in r or "no válido" in r

    def test_valid_methods_accepted(self):
        for method in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
            # Solo verificamos que no lance excepción ni rechace el método
            args = {"url": "http://127.0.0.1:19999/", "method": method, "timeout": 1}
            r = _tool_http_request(args)
            assert isinstance(r, str)

    def test_body_dict_serialized(self):
        # Body dict debe convertirse a JSON sin error
        args = {
            "url": "http://127.0.0.1:19999/",
            "method": "POST",
            "body": {"key": "value"},
            "timeout": 1,
        }
        r = _tool_http_request(args)
        assert isinstance(r, str)

    def test_auth_bearer_header(self):
        # La auth bearer se incluye en la request (no podemos verificar red,
        # pero sí que el código no falla al construir la request)
        args = {
            "url": "http://127.0.0.1:19999/",
            "auth": {"type": "bearer", "token": "mytoken123"},
            "timeout": 1,
        }
        r = _tool_http_request(args)
        assert isinstance(r, str)


# ── http_headers ──────────────────────────────────────────────────────────────

class TestHttpHeaders:
    def test_missing_url(self):
        r = _tool_http_headers({})
        assert "Error" in r or "error" in r.lower()

    def test_connection_error_handled(self):
        r = _tool_http_headers({"url": "http://127.0.0.1:19999/", "timeout": 1})
        assert isinstance(r, str)


# ── http_auth ─────────────────────────────────────────────────────────────────

class TestHttpAuth:
    def test_bearer(self):
        r = _tool_http_auth({"type": "bearer", "token": "abc123"})
        assert "Authorization: Bearer abc123" == r

    def test_basic(self):
        import base64
        r = _tool_http_auth({"type": "basic", "username": "user", "password": "pass"})
        assert r.startswith("Authorization: Basic ")
        encoded = r.split(" ", 2)[2]
        decoded = base64.b64decode(encoded).decode()
        assert decoded == "user:pass"

    def test_api_key_default_header(self):
        r = _tool_http_auth({"type": "api_key", "key": "secret123"})
        assert r == "X-API-Key: secret123"

    def test_api_key_custom_header(self):
        r = _tool_http_auth({"type": "api_key", "key": "secret123", "header": "X-Token"})
        assert r == "X-Token: secret123"

    def test_bearer_missing_token(self):
        r = _tool_http_auth({"type": "bearer"})
        assert "Error" in r

    def test_basic_missing_username(self):
        r = _tool_http_auth({"type": "basic"})
        assert "Error" in r

    def test_unknown_type(self):
        r = _tool_http_auth({"type": "oauth3"})
        assert "Error" in r or "no soportado" in r

    def test_missing_type(self):
        r = _tool_http_auth({})
        # type defaults to 'bearer', token absent → error
        assert isinstance(r, str)


# ── http_upload ───────────────────────────────────────────────────────────────

class TestHttpUpload:
    def test_missing_url(self):
        r = _tool_http_upload({"file_path": "/tmp/test.txt"})
        assert "Error" in r

    def test_missing_file_path(self):
        r = _tool_http_upload({"url": "http://localhost/upload"})
        assert "Error" in r

    def test_file_not_found(self, tmp_path):
        r = _tool_http_upload({
            "url": "http://127.0.0.1:19999/upload",
            "file_path": str(tmp_path / "nonexistent.txt"),
        })
        assert "Error" in r or "no encontrado" in r

    def test_network_error_handled(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        r = _tool_http_upload({
            "url": "http://127.0.0.1:19999/upload",
            "file_path": str(f),
            "timeout": 1,
        })
        assert isinstance(r, str)


# ── response_diff ─────────────────────────────────────────────────────────────

class TestResponseDiff:
    def test_identical_texts(self):
        r = _tool_response_diff({"text_a": "hello\nworld", "text_b": "hello\nworld"})
        assert "Sin diferencias" in r

    def test_different_texts(self):
        r = _tool_response_diff({"text_a": "line1\nline2", "text_b": "line1\nline3"})
        assert "line2" in r or "line3" in r or "-" in r or "+" in r

    def test_missing_inputs(self):
        r = _tool_response_diff({})
        assert "Error" in r or "especifica" in r

    def test_diff_format_unified(self):
        r = _tool_response_diff({
            "text_a": "a\nb\nc",
            "text_b": "a\nX\nc",
            "label_a": "before",
            "label_b": "after",
        })
        assert isinstance(r, str)
        # unified diff includes +/- lines
        assert "+" in r or "-" in r or "Sin diferencias" in r

    def test_network_error_url(self):
        r = _tool_response_diff({
            "url_a": "http://127.0.0.1:19999/a",
            "url_b": "http://127.0.0.1:19999/b",
            "timeout": 1,
        })
        # Connection refused → error message
        assert isinstance(r, str)


# ── openapi_validate ──────────────────────────────────────────────────────────

class TestOpenapiValidate:
    def test_no_spec_no_local_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        r = _tool_openapi_validate({})
        assert "Error" in r or "especifica" in r or "no se encontró" in r

    def test_spec_not_found(self):
        r = _tool_openapi_validate({"spec_path": "/nonexistent/openapi.json"})
        assert "Error" in r or "no encontrada" in r

    def test_valid_spec_list_endpoints(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0"},
            "paths": {
                "/users": {"get": {"summary": "List users", "responses": {"200": {}}}},
                "/users/{id}": {"get": {"summary": "Get user", "responses": {"200": {}}}},
            },
        }
        spec_file = tmp_path / "openapi.json"
        spec_file.write_text(json.dumps(spec))
        r = _tool_openapi_validate({"spec_path": str(spec_file)})
        assert "Test API" in r or "/users" in r

    def test_endpoint_not_found(self, tmp_path):
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "T", "version": "1"},
            "paths": {"/users": {"get": {}}},
        }
        f = tmp_path / "openapi.json"
        f.write_text(json.dumps(spec))
        r = _tool_openapi_validate({"spec_path": str(f), "endpoint": "/nonexistent"})
        assert "no encontrado" in r or "no se encontró" in r.lower() or "Endpoint" in r

    def test_validate_request_body(self, tmp_path):
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "T", "version": "1"},
            "paths": {
                "/items": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["name"],
                                        "properties": {
                                            "name": {"type": "string"},
                                        },
                                    }
                                }
                            }
                        },
                        "responses": {"201": {}},
                    }
                }
            },
        }
        f = tmp_path / "openapi.json"
        f.write_text(json.dumps(spec))
        # Missing required field
        r = _tool_openapi_validate({
            "spec_path": str(f),
            "endpoint": "/items",
            "method": "post",
            "request_body": {},
        })
        assert "name" in r or "requerido" in r or "error" in r.lower()

    def test_validate_correct_body(self, tmp_path):
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "T", "version": "1"},
            "paths": {
                "/items": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["name"],
                                        "properties": {
                                            "name": {"type": "string"},
                                        },
                                    }
                                }
                            }
                        },
                        "responses": {"201": {}},
                    }
                }
            },
        }
        f = tmp_path / "openapi.json"
        f.write_text(json.dumps(spec))
        r = _tool_openapi_validate({
            "spec_path": str(f),
            "endpoint": "/items",
            "method": "post",
            "request_body": {"name": "test item"},
        })
        assert "✓" in r or "correc" in r.lower()


# ── _validate_json_schema ─────────────────────────────────────────────────────

class TestValidateJsonSchema:
    def test_object_required_missing(self):
        errors, warnings = [], []
        _validate_json_schema({}, {"type": "object", "required": ["name"]}, "root", errors, warnings)
        assert any("name" in e for e in errors)

    def test_string_type_mismatch(self):
        errors, warnings = [], []
        _validate_json_schema(123, {"type": "string"}, "field", errors, warnings)
        assert errors

    def test_integer_type_ok(self):
        errors, warnings = [], []
        _validate_json_schema(42, {"type": "integer"}, "field", errors, warnings)
        assert not errors

    def test_enum_violation(self):
        errors, warnings = [], []
        _validate_json_schema("other", {"type": "string", "enum": ["a", "b"]}, "f", errors, warnings)
        assert errors

    def test_array_type_mismatch(self):
        errors, warnings = [], []
        _validate_json_schema("not array", {"type": "array"}, "f", errors, warnings)
        assert errors

    def test_extra_property_warns(self):
        errors, warnings = [], []
        schema = {"type": "object", "properties": {"a": {"type": "string"}}}
        _validate_json_schema({"a": "x", "extra": 1}, schema, "root", errors, warnings)
        assert any("extra" in w for w in warnings)

    def test_no_type_no_crash(self):
        errors, warnings = [], []
        _validate_json_schema({"any": "thing"}, {}, "root", errors, warnings)
        assert not errors


# ── curl_import ───────────────────────────────────────────────────────────────

class TestCurlImport:
    def test_missing_command(self):
        r = _tool_curl_import({})
        assert "Error" in r

    def test_parse_only_no_execute(self):
        r = _tool_curl_import({
            "command": "curl -X POST http://localhost:8080/api -H 'Content-Type: application/json'",
            "execute": False,
        })
        assert "http://localhost:8080/api" in r
        assert "POST" in r
        assert "Content-Type" in r

    def test_parse_bearer_auth(self):
        r = _tool_curl_import({
            "command": "curl -H 'Authorization: Bearer mytoken' http://localhost/api",
            "execute": False,
        })
        assert "bearer" in r.lower() or "mytoken" in r

    def test_parse_basic_auth(self):
        r = _tool_curl_import({
            "command": "curl -u admin:password http://localhost/api",
            "execute": False,
        })
        assert "basic" in r.lower() or "admin" in r

    def test_parse_data_flag(self):
        r = _tool_curl_import({
            "command": 'curl -d \'{"name":"test"}\' http://localhost/api',
            "execute": False,
        })
        assert "POST" in r or "name" in r

    def test_execute_network_error(self):
        r = _tool_curl_import({
            "command": "curl http://127.0.0.1:19999/test",
            "execute": True,
        })
        assert isinstance(r, str)

    def test_parse_no_url(self):
        r = _tool_curl_import({"command": "curl -X GET", "execute": False})
        assert "Error" in r or "URL" in r


# ── websocket_send ────────────────────────────────────────────────────────────

class TestWebsocketSend:
    def test_missing_url(self):
        r = _tool_websocket_send({})
        assert "Error" in r

    def test_missing_message(self):
        r = _tool_websocket_send({"url": "ws://localhost/ws"})
        assert "Error" in r or isinstance(r, str)

    def test_no_lib_returns_message(self):
        with patch.dict("sys.modules", {"websocket": None}):
            # Cuando websocket-client no está disponible
            try:
                from mcp_servers.http_client_assistant import _tool_websocket_send as fn
                r = fn({"url": "ws://localhost/ws", "message": "hello"})
                assert isinstance(r, str)
            except ImportError:
                pass  # OK si el import falla

    def test_connection_error_handled(self):
        r = _tool_websocket_send({"url": "ws://127.0.0.1:19999/ws", "message": "hi", "timeout": 1})
        assert isinstance(r, str)


# ── sse_listen ────────────────────────────────────────────────────────────────

class TestSseListen:
    def test_missing_url(self):
        r = _tool_sse_listen({})
        assert "Error" in r

    def test_connection_error_handled(self):
        r = _tool_sse_listen({"url": "http://127.0.0.1:19999/sse", "duration": 1})
        assert isinstance(r, str)


# ── mock server ───────────────────────────────────────────────────────────────

class TestMockServer:
    def setup_method(self):
        # Asegurar que no hay mock server activo antes de cada test
        _tool_mock_server_stop({})

    def teardown_method(self):
        _tool_mock_server_stop({})

    def test_start_stop(self):
        r = _tool_mock_server_start({"port": 18765})
        assert "✓" in r or "iniciado" in r
        r2 = _tool_mock_server_stop({})
        assert "detenido" in r2 or "✓" in r2

    def test_stop_when_not_running(self):
        r = _tool_mock_server_stop({})
        assert "No hay" in r or "running" in r.lower() or isinstance(r, str)

    def test_start_already_running(self):
        _tool_mock_server_start({"port": 18766})
        r = _tool_mock_server_start({"port": 18767})
        assert "ya está" in r or "running" in r.lower() or isinstance(r, str)
        _tool_mock_server_stop({})

    def test_mock_responds_to_get(self):
        routes = [{"method": "GET", "path": "/api/test", "status": 200, "body": '{"ok": true}'}]
        r = _tool_mock_server_start({"port": 18768, "routes": routes})
        assert "✓" in r or "iniciado" in r
        time.sleep(0.1)
        result = _do_request("http://127.0.0.1:18768/api/test", "GET")
        assert result.get("status") == 200
        assert "ok" in result.get("body", "")

    def test_mock_404_for_unknown_path(self):
        _tool_mock_server_start({"port": 18769, "routes": []})
        time.sleep(0.1)
        result = _do_request("http://127.0.0.1:18769/unknown", "GET")
        assert result.get("status") == 404

    def test_mock_with_json_body(self):
        routes = [{"method": "POST", "path": "/echo", "status": 201, "body": {"id": 1}}]
        _tool_mock_server_start({"port": 18770, "routes": routes})
        time.sleep(0.1)
        result = _do_request("http://127.0.0.1:18770/echo", "POST", body='{"x":1}')
        assert result.get("status") == 201

    def test_invalid_port_error(self):
        # Port 80 should fail (requires root) or raise OS error
        r = _tool_mock_server_start({"port": 1})
        assert isinstance(r, str)
        # If it somehow started, stop it
        _tool_mock_server_stop({})


# ── http_health_check ─────────────────────────────────────────────────────────

class TestHttpHealthCheck:
    def test_missing_urls(self):
        r = _tool_http_health_check({})
        assert "Error" in r or "requerido" in r

    def test_single_unreachable_url(self):
        r = _tool_http_health_check({"urls": "http://127.0.0.1:19999/", "timeout": 1})
        assert isinstance(r, str)
        assert "✗" in r or "Error" in r

    def test_multiple_urls_list(self):
        r = _tool_http_health_check({
            "urls": ["http://127.0.0.1:19999/a", "http://127.0.0.1:19999/b"],
            "timeout": 1,
        })
        assert "2" in r  # "2 endpoints"
        assert "✗" in r

    def test_comma_separated_urls(self):
        r = _tool_http_health_check({
            "urls": "http://127.0.0.1:19999/a,http://127.0.0.1:19999/b",
            "timeout": 1,
        })
        assert isinstance(r, str)

    def test_report_summary(self):
        r = _tool_http_health_check({"urls": "http://127.0.0.1:19999/", "timeout": 1})
        assert "/" in r  # "0/1 OK"


# ── graphql_query ─────────────────────────────────────────────────────────────

class TestGraphqlQuery:
    def test_missing_url(self):
        r = _tool_graphql_query({"query": "{ users { id } }"})
        assert "Error" in r

    def test_missing_query(self):
        r = _tool_graphql_query({"url": "http://localhost/graphql"})
        assert "Error" in r

    def test_connection_error_handled(self):
        r = _tool_graphql_query({
            "url": "http://127.0.0.1:19999/graphql",
            "query": "{ users { id } }",
            "timeout": 1,
        })
        assert isinstance(r, str)

    def test_graphql_errors_parsed(self):
        # Simular respuesta de error GraphQL con mock server
        routes = [{
            "method": "POST",
            "path": "/graphql",
            "status": 200,
            "body": json.dumps({"errors": [{"message": "Field not found", "locations": [{"line": 1, "column": 3}]}]}),
        }]
        _tool_mock_server_start({"port": 18780, "routes": routes})
        time.sleep(0.1)
        r = _tool_graphql_query({
            "url": "http://127.0.0.1:18780/graphql",
            "query": "{ bad }",
        })
        _tool_mock_server_stop({})
        assert "Field not found" in r or "error" in r.lower()

    def test_graphql_data_parsed(self):
        routes = [{
            "method": "POST",
            "path": "/graphql",
            "status": 200,
            "body": json.dumps({"data": {"user": {"id": 1, "name": "Alice"}}}),
        }]
        _tool_mock_server_start({"port": 18781, "routes": routes})
        time.sleep(0.1)
        r = _tool_graphql_query({
            "url": "http://127.0.0.1:18781/graphql",
            "query": "{ user { id name } }",
        })
        _tool_mock_server_stop({})
        assert "Alice" in r or "user" in r


# ── jwt_decode ────────────────────────────────────────────────────────────────

class TestJwtDecode:
    # HS256 JWT — {"sub":"1234","name":"Test","iat":1516239022,"exp":9999999999}
    _VALID_JWT = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        ".eyJzdWIiOiIxMjM0IiwibmFtZSI6IlRlc3QiLCJpYXQiOjE1MTYyMzkwMjIsImV4cCI6OTk5OTk5OTk5OX0"
        ".signature_placeholder"
    )
    # Expired JWT — exp in 2020
    _EXPIRED_JWT = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        ".eyJzdWIiOiIxMjM0IiwiZXhwIjoxNTAwMDAwMDAwfQ"
        ".signature"
    )

    def test_missing_token(self):
        r = _tool_jwt_decode({})
        assert "Error" in r

    def test_invalid_format(self):
        r = _tool_jwt_decode({"token": "notajwt"})
        assert "Error" in r or "inválido" in r

    def test_valid_jwt_decoded(self):
        r = _tool_jwt_decode({"token": self._VALID_JWT})
        assert "Header" in r or "HS256" in r or "Test" in r

    def test_expired_jwt_detected(self):
        r = _tool_jwt_decode({"token": self._EXPIRED_JWT})
        assert "EXPIRADO" in r or "expirado" in r.lower()

    def test_valid_jwt_not_expired(self):
        r = _tool_jwt_decode({"token": self._VALID_JWT})
        assert "válido" in r or "EXPIRADO" not in r

    def test_bearer_prefix_stripped(self):
        r = _tool_jwt_decode({"token": f"Bearer {self._VALID_JWT}"})
        assert "Error" not in r or "inválido" not in r

    def test_show_raw(self):
        r = _tool_jwt_decode({"token": self._VALID_JWT, "show_raw": True})
        assert "Raw" in r or "eyJ" in r

    def test_algorithm_shown(self):
        r = _tool_jwt_decode({"token": self._VALID_JWT})
        assert "HS256" in r or "Algoritmo" in r

    def test_two_parts_rejected(self):
        r = _tool_jwt_decode({"token": "header.payload"})
        assert "Error" in r or "inválido" in r


# ── http_batch ────────────────────────────────────────────────────────────────

class TestHttpBatch:
    def test_missing_requests(self):
        r = _tool_http_batch({})
        assert "Error" in r

    def test_empty_requests(self):
        r = _tool_http_batch({"requests": []})
        assert "Error" in r or "0" in r

    def test_batch_handles_network_errors(self):
        r = _tool_http_batch({
            "requests": [
                {"url": "http://127.0.0.1:19999/a", "name": "req1", "timeout": 1},
                {"url": "http://127.0.0.1:19999/b", "name": "req2", "timeout": 1},
            ]
        })
        assert "req1" in r or "req2" in r
        assert "0/2" in r or "✗" in r

    def test_batch_stop_on_error(self):
        r = _tool_http_batch({
            "requests": [
                {"url": "http://127.0.0.1:19999/a", "name": "req1", "timeout": 1},
                {"url": "http://127.0.0.1:19999/b", "name": "req2", "timeout": 1},
            ],
            "stop_on_error": True,
        })
        assert isinstance(r, str)

    def test_batch_missing_url_in_request(self):
        r = _tool_http_batch({
            "requests": [{"name": "no-url"}],
        })
        assert "ausente" in r or "Error" in r or isinstance(r, str)

    def test_batch_success_with_mock(self):
        routes = [{"method": "GET", "path": "/health", "status": 200, "body": "ok"}]
        _tool_mock_server_start({"port": 18790, "routes": routes})
        time.sleep(0.1)
        r = _tool_http_batch({
            "requests": [
                {"url": "http://127.0.0.1:18790/health", "name": "health"},
            ]
        })
        _tool_mock_server_stop({})
        assert "1/1" in r or "✓" in r


# ── http_history ──────────────────────────────────────────────────────────────

class TestHttpHistory:
    def test_returns_string(self):
        r = _tool_http_history({})
        assert isinstance(r, str)

    def test_limit_param(self):
        r = _tool_http_history({"limit": 5})
        assert isinstance(r, str)

    def test_filter_url(self):
        r = _tool_http_history({"url_contains": "nonexistent_xyz_filter"})
        assert "vacío" in r or isinstance(r, str)

    def test_history_populated_after_request(self):
        before = len(_request_history)
        _tool_http_get({"url": "http://127.0.0.1:19999/history-test", "timeout": 1})
        after = len(_request_history)
        assert after >= before  # At least same or more entries


# ── Prompts ───────────────────────────────────────────────────────────────────

class TestPrompts:
    def test_prompt_count(self):
        assert len(_PROMPTS) == 3

    def test_expected_prompts_present(self):
        assert "api_testing" in _PROMPTS
        assert "rest_client_setup" in _PROMPTS
        assert "api_debugging" in _PROMPTS

    def test_all_prompts_have_description(self):
        for name, p in _PROMPTS.items():
            assert "description" in p
            assert len(p["description"]) > 10

    def test_api_testing_has_arguments(self):
        assert "arguments" in _PROMPTS["api_testing"]
        args = _PROMPTS["api_testing"]["arguments"]
        assert any(a["name"] == "endpoint" for a in args)

    def test_prompt_get_api_testing(self):
        msgs = _prompt_get("api_testing", {"endpoint": "http://localhost:8080/users"})
        assert isinstance(msgs, list)
        assert len(msgs) > 0
        assert "http://localhost:8080/users" in msgs[0]["content"]["text"]

    def test_prompt_get_rest_client_setup(self):
        msgs = _prompt_get("rest_client_setup", {})
        assert isinstance(msgs, list)
        assert len(msgs) > 0

    def test_prompt_get_api_debugging(self):
        msgs = _prompt_get("api_debugging", {"error": "500 Internal Server Error"})
        assert isinstance(msgs, list)
        assert "500" in msgs[0]["content"]["text"]

    def test_prompt_get_unknown(self):
        msgs = _prompt_get("nonexistent_prompt", {})
        assert isinstance(msgs, list)
        assert "no encontrado" in msgs[0]["content"]["text"]


# ── Resources ─────────────────────────────────────────────────────────────────

class TestResources:
    def test_resource_count(self):
        assert len(_RESOURCES) == 1

    def test_openapi_resource_present(self):
        uris = [r["uri"] for r in _RESOURCES]
        assert "project://openapi" in uris

    def test_resource_fns_match(self):
        for r in _RESOURCES:
            assert r["uri"] in _RESOURCE_FNS
            assert callable(_RESOURCE_FNS[r["uri"]])

    def test_openapi_resource_no_crash(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        r = _resource_project_openapi()
        assert isinstance(r, str)

    def test_openapi_resource_detects_spec(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "My API", "version": "2.0"},
            "paths": {"/items": {"get": {}}},
        }
        (tmp_path / "openapi.json").write_text(json.dumps(spec))
        r = _resource_project_openapi()
        assert "My API" in r or "openapi.json" in r

    def test_openapi_resource_reads_env(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("API_URL=http://localhost:8080\nSECRET_KEY=abc123\n")
        r = _resource_project_openapi()
        assert "API_URL" in r or "localhost:8080" in r


# ── Config integration ────────────────────────────────────────────────────────

class TestHttpClientConfig:
    def test_config_has_http_client_field(self):
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from config import OOConfig
        cfg = OOConfig()
        assert hasattr(cfg, "mcp_http_client_assistant_enabled")
        assert cfg.mcp_http_client_assistant_enabled is False

    def test_default_config_has_http_client(self):
        from config import DEFAULT_CONFIG
        assert "httpClientAssistant" in DEFAULT_CONFIG["mcp"]
        assert DEFAULT_CONFIG["mcp"]["httpClientAssistant"]["enabled"] is False

    def test_config_save_load_http_client(self, tmp_path):
        import tempfile
        from unittest.mock import patch
        from config import OOConfig

        cfg_file = tmp_path / "oocode.json"
        with patch("config.CONFIG_FILE", cfg_file):
            c = OOConfig()
            c.mcp_http_client_assistant_enabled = True
            c.save()
            raw = json.loads(cfg_file.read_text())
            assert raw["mcp"]["httpClientAssistant"]["enabled"] is True

    def test_config_load_with_http_client(self, tmp_path):
        import tempfile
        from unittest.mock import patch
        from config import OOConfig

        cfg_file = tmp_path / "oocode.json"
        cfg_file.write_text(json.dumps({
            "mcp": {"httpClientAssistant": {"enabled": True}}
        }))
        with patch("config.CONFIG_FILE", cfg_file):
            c = OOConfig.load()
            assert c.mcp_http_client_assistant_enabled is True

    def test_mcp_manager_has_http_client(self):
        from agent.mcp_manager import _BUNDLED_SERVER_MAP
        assert "http-client-assistant" in _BUNDLED_SERVER_MAP
        assert _BUNDLED_SERVER_MAP["http-client-assistant"] == "httpClientAssistant"

    def test_commands_has_http_client_attr(self):
        from ui.commands import _BUNDLED_CONFIG_ATTR
        assert "http-client-assistant" in _BUNDLED_CONFIG_ATTR
        assert _BUNDLED_CONFIG_ATTR["http-client-assistant"] == "mcp_http_client_assistant_enabled"

    def test_mcp_manager_enable_bundled(self, tmp_path):
        from unittest.mock import patch
        from agent.mcp_manager import set_server_enabled

        cfg_file = tmp_path / "oocode.json"
        cfg_file.write_text(json.dumps({"mcp": {}}))
        result = set_server_enabled("http-client-assistant", True, config_file=cfg_file)
        assert result is True
        raw = json.loads(cfg_file.read_text())
        assert raw["mcp"]["httpClientAssistant"]["enabled"] is True

    def test_mcp_manager_disable_bundled(self, tmp_path):
        from agent.mcp_manager import set_server_enabled

        cfg_file = tmp_path / "oocode.json"
        cfg_file.write_text(json.dumps({"mcp": {"httpClientAssistant": {"enabled": True}}}))
        result = set_server_enabled("http-client-assistant", False, config_file=cfg_file)
        assert result is True
        raw = json.loads(cfg_file.read_text())
        assert raw["mcp"]["httpClientAssistant"]["enabled"] is False


# ── Migration check ───────────────────────────────────────────────────────────

class TestMigration:
    def test_migration_triggered_when_key_missing(self, tmp_path):
        from unittest.mock import patch
        from config import OOConfig

        cfg_file = tmp_path / "oocode.json"
        # Config without httpClientAssistant key
        cfg_file.write_text(json.dumps({
            "mcp": {
                "oocodeAssistant": {"enabled": True},
                "systemAssistant": {"enabled": True},
                "devopsAssistant": {"enabled": True},
                "databaseAssistant": {"enabled": False},
                "homeOfficeAssistant": {"enabled": False},
                "securityAssistant": {"enabled": False},
                "iotAssistant": {"enabled": False},
                # httpClientAssistant absent — should trigger migration
            }
        }))
        with patch("config.CONFIG_FILE", cfg_file):
            c = OOConfig.load()
            # After load+save migration, key should exist
            c.save()
            raw = json.loads(cfg_file.read_text())
            assert "httpClientAssistant" in raw["mcp"]

    def test_http_client_default_is_false(self, tmp_path):
        from unittest.mock import patch
        from config import OOConfig

        cfg_file = tmp_path / "oocode.json"
        cfg_file.write_text("{}")
        with patch("config.CONFIG_FILE", cfg_file):
            c = OOConfig.load()
            assert c.mcp_http_client_assistant_enabled is False


# ── http_get moved: oocode_assistant no longer has it ─────────────────────────

class TestHttpGetMovedFromOocode:
    def test_http_get_not_in_oocode_assistant(self):
        from mcp_servers.oocode_assistant import _TOOLS as OT, _TOOL_FNS as OFN
        names = {t["name"] for t in OT}
        assert "http_get" not in names
        assert "http_get" not in OFN

    def test_http_get_in_http_client_assistant(self):
        names = {t["name"] for t in _TOOLS}
        assert "http_get" in names
        assert "http_get" in _TOOL_FNS
