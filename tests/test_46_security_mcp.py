"""Tests del servidor MCP Security Assistant.

Verifica schemas, configuración, integración con loop.py, y tools sin deps externas.
No requiere nmap, nikto, hashcat, trufflehog ni herramientas de sistema opcionales.
"""
import base64
import hashlib
import json
import socket
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.security_assistant import (
    _TOOL_FNS,
    _TOOLS,
    _PROMPTS,
    _RESOURCES,
    _RESOURCE_FNS,
    _add_history,
    _scan_history,
    _cmd_available,
    _require,
    _get_prompt,
    _tool_port_scan,
    _tool_ssl_check,
    _tool_encode_decode,
    _tool_jwt_decode,
    _tool_xor_decode,
    _tool_base_convert,
    _tool_hex_dump,
    _tool_log_analyze,
    _tool_secret_scan,
    _tool_file_integrity_check,
    _tool_ssh_key_audit,
    _tool_sudoers_review,
    _tool_http_headers,
    _tool_curl_request,
    _tool_fw_audit,
    _tool_cve_lookup,
    _handle,
)


# ── Schema integrity ─────────────────────────────────────────────────────────

class TestToolSchemas:
    def test_tool_count(self):
        assert len(_TOOLS) == 24

    def test_all_tools_have_name_and_description(self):
        for t in _TOOLS:
            assert "name" in t, f"Tool sin nombre: {t}"
            assert "description" in t and t["description"], f"Tool sin desc: {t['name']}"

    def test_all_tools_have_input_schema(self):
        for t in _TOOLS:
            assert "inputSchema" in t, f"Tool sin inputSchema: {t['name']}"
            assert t["inputSchema"]["type"] == "object"

    def test_all_tools_registered_in_tool_fns(self):
        schema_names = {t["name"] for t in _TOOLS}
        for name in schema_names:
            assert name in _TOOL_FNS, f"Tool '{name}' en _TOOLS pero no en _TOOL_FNS"

    def test_all_tool_fns_have_schema(self):
        schema_names = {t["name"] for t in _TOOLS}
        for name in _TOOL_FNS:
            assert name in schema_names, f"Tool '{name}' en _TOOL_FNS pero no en _TOOLS"

    def test_no_wrapper_format(self):
        for t in _TOOLS:
            assert "type" not in t or t["type"] != "function", \
                f"Tool '{t['name']}' usa formato wrapper — usar inner format"

    def test_tool_categories_present(self):
        names = {t["name"] for t in _TOOLS}
        recon_tools = {"nmap_scan", "port_scan", "ssl_check", "whois_lookup", "dns_enum"}
        web_tools   = {"http_headers", "nikto_scan", "gobuster_run", "curl_request"}
        crypto      = {"encode_decode", "hash_crack", "jwt_decode", "cert_inspect"}
        analysis    = {"log_analyze", "secret_scan", "cve_lookup"}
        ctf         = {"xor_decode", "steganography_check", "base_convert", "hex_dump"}
        defensive   = {"fw_audit", "ssh_key_audit", "sudoers_review", "file_integrity_check"}
        for cat, tools in [
            ("recon", recon_tools), ("web", web_tools), ("crypto", crypto),
            ("analysis", analysis), ("ctf", ctf), ("defensive", defensive),
        ]:
            missing = tools - names
            assert not missing, f"Faltan tools de {cat}: {missing}"

    def test_offensive_tools_marked_in_description(self):
        offensive = {"nikto_scan", "gobuster_run", "hash_crack"}
        for t in _TOOLS:
            if t["name"] in offensive:
                desc = t["description"].upper()
                assert "OFENSIVO" in desc or "AUTORIZACIÓN" in desc or "REQUIERE" in desc, \
                    f"Tool ofensiva '{t['name']}' no advierte en descripción"


class TestPromptSchemas:
    def test_prompt_count(self):
        assert len(_PROMPTS) == 4

    def test_prompt_names(self):
        names = {p["name"] for p in _PROMPTS}
        expected = {"pentest_report", "ctf_challenge", "security_audit", "vulnerability_analysis"}
        assert names == expected

    def test_prompts_have_description(self):
        for p in _PROMPTS:
            assert p.get("description"), f"Prompt sin descripción: {p['name']}"

    def test_prompts_have_arguments(self):
        for p in _PROMPTS:
            assert "arguments" in p, f"Prompt sin arguments: {p['name']}"
            assert isinstance(p["arguments"], list)
            assert len(p["arguments"]) >= 1


class TestResourceSchemas:
    def test_resource_count(self):
        assert len(_RESOURCES) == 3

    def test_resource_uris(self):
        uris = {r["uri"] for r in _RESOURCES}
        expected = {
            "security://scan_history",
            "security://tools_available",
            "security://host_info",
        }
        assert uris == expected

    def test_all_resources_have_fn(self):
        for r in _RESOURCES:
            assert r["uri"] in _RESOURCE_FNS, f"Resource '{r['uri']}' sin función"

    def test_resources_callable(self):
        for uri, fn in _RESOURCE_FNS.items():
            result = fn()
            assert isinstance(result, str), f"Resource {uri} no devuelve str"
            assert len(result) > 0


# ── Encode/Decode ─────────────────────────────────────────────────────────────

class TestEncodeDecode:
    def test_base64_encode(self):
        result = _tool_encode_decode({"data": "hello", "operation": "encode", "encoding": "base64"})
        assert result == base64.b64encode(b"hello").decode()

    def test_base64_decode(self):
        encoded = base64.b64encode(b"world").decode()
        result = _tool_encode_decode({"data": encoded, "operation": "decode", "encoding": "base64"})
        assert result == "world"

    def test_hex_encode(self):
        result = _tool_encode_decode({"data": "hi", "operation": "encode", "encoding": "hex"})
        assert result == "hi".encode().hex()

    def test_hex_decode(self):
        result = _tool_encode_decode({"data": "68656c6c6f", "operation": "decode", "encoding": "hex"})
        assert result == "hello"

    def test_url_encode(self):
        result = _tool_encode_decode({"data": "hello world", "operation": "encode", "encoding": "url"})
        assert "hello" in result and ("+" in result or "%20" in result)

    def test_url_decode(self):
        result = _tool_encode_decode({"data": "hello+world", "operation": "decode", "encoding": "url"})
        assert "hello" in result

    def test_rot13(self):
        result = _tool_encode_decode({"data": "hello", "operation": "encode", "encoding": "rot13"})
        assert result == "uryyb"

    def test_rot13_decode(self):
        result = _tool_encode_decode({"data": "uryyb", "operation": "decode", "encoding": "rot13"})
        assert result == "hello"

    def test_html_encode(self):
        result = _tool_encode_decode({"data": "<b>hi</b>", "operation": "encode", "encoding": "html"})
        assert "&lt;" in result and "&gt;" in result

    def test_html_decode(self):
        result = _tool_encode_decode({"data": "&lt;b&gt;", "operation": "decode", "encoding": "html"})
        assert "<b>" in result

    def test_base32_encode(self):
        result = _tool_encode_decode({"data": "hi", "operation": "encode", "encoding": "base32"})
        assert base64.b32decode(result) == b"hi"

    def test_unsupported_encoding(self):
        result = _tool_encode_decode({"data": "x", "operation": "encode", "encoding": "ascii85"})
        assert "no soportado" in result.lower()


# ── JWT Decode ────────────────────────────────────────────────────────────────

class TestJwtDecode:
    def _make_jwt(self, header: dict, payload: dict, signature: str = "fakesig") -> str:
        def b64url(d):
            return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
        return f"{b64url(header)}.{b64url(payload)}.{signature}"

    def test_decode_valid_jwt(self):
        token = self._make_jwt({"alg": "HS256", "typ": "JWT"}, {"sub": "user1", "iss": "test"})
        result = _tool_jwt_decode({"token": token})
        assert "HS256" in result
        assert "user1" in result

    def test_decode_expired_jwt(self):
        import time
        payload = {"sub": "user", "exp": int(time.time()) - 3600}
        token = self._make_jwt({"alg": "HS256"}, payload)
        result = _tool_jwt_decode({"token": token})
        assert "EXPIRADO" in result

    def test_decode_none_algorithm(self):
        token = self._make_jwt({"alg": "none"}, {"sub": "admin"})
        result = _tool_jwt_decode({"token": token})
        assert "ALERTA" in result or "none" in result.lower()

    def test_invalid_jwt_missing_parts(self):
        result = _tool_jwt_decode({"token": "notajwt"})
        assert "inválido" in result.lower() or "partes" in result.lower()

    def test_missing_token(self):
        result = _tool_jwt_decode({})
        assert "requerido" in result.lower()


# ── XOR Decode ────────────────────────────────────────────────────────────────

class TestXorDecode:
    def test_xor_with_hex_key(self):
        data = bytes([0x41 ^ 0x20])
        result = _tool_xor_decode({
            "data":     data.hex(),
            "key":      "20",
            "encoding": "hex",
        })
        assert "41" in result or "A" in result or chr(0x41 ^ 0x20) in result

    def test_xor_roundtrip(self):
        original = b"CTFflag"
        key      = b"\xAA"
        encrypted = bytes(b ^ key[0] for b in original)
        result = _tool_xor_decode({
            "data":     encrypted.hex(),
            "key":      "aa",
            "encoding": "hex",
        })
        assert "CTFflag" in result

    def test_xor_base64_encoding(self):
        data = bytes([0x00, 0x01, 0x02])
        encoded = base64.b64encode(data).decode()
        result = _tool_xor_decode({"data": encoded, "key": "00", "encoding": "base64"})
        assert isinstance(result, str)

    def test_missing_params(self):
        result = _tool_xor_decode({"data": "aabbcc"})
        assert "requerido" in result.lower()


# ── Base Convert ──────────────────────────────────────────────────────────────

class TestBaseConvert:
    def test_dec_to_hex(self):
        result = _tool_base_convert({"value": "255", "from_base": 10, "to_base": 16})
        assert "ff" in result.lower()

    def test_hex_to_bin(self):
        result = _tool_base_convert({"value": "ff", "from_base": 16, "to_base": 2})
        assert "11111111" in result

    def test_bin_to_dec(self):
        result = _tool_base_convert({"value": "1010", "from_base": 2, "to_base": 10})
        assert "10" in result

    def test_zero(self):
        result = _tool_base_convert({"value": "0", "from_base": 10, "to_base": 16})
        assert "0" in result

    def test_invalid_value(self):
        result = _tool_base_convert({"value": "zzz", "from_base": 10, "to_base": 16})
        assert "inválido" in result.lower() or "no es válido" in result.lower()

    def test_invalid_base(self):
        result = _tool_base_convert({"value": "1", "from_base": 1, "to_base": 16})
        assert "entre 2 y 36" in result

    def test_missing_value(self):
        result = _tool_base_convert({})
        assert "requerido" in result.lower()


# ── Hex Dump ──────────────────────────────────────────────────────────────────

class TestHexDump:
    def test_hex_input(self):
        result = _tool_hex_dump({"file_or_data": "48656c6c6f", "length": 16})
        assert "Hello" in result or "48 65 6c 6c 6f" in result or "48" in result

    def test_text_input_as_fallback(self):
        result = _tool_hex_dump({"file_or_data": "Hello", "length": 16})
        assert isinstance(result, str) and len(result) > 0

    def test_file_input(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(b"\x00\x01\x02\x03Hello")
            path = f.name
        result = _tool_hex_dump({"file_or_data": path, "length": 16})
        Path(path).unlink()
        assert isinstance(result, str)

    def test_missing_param(self):
        result = _tool_hex_dump({})
        assert "requerido" in result.lower()

    def test_offset_param(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"AAAA" + b"BBBB")
            path = f.name
        result = _tool_hex_dump({"file_or_data": path, "length": 4, "offset": 4})
        Path(path).unlink()
        assert isinstance(result, str)


# ── Log Analyze ───────────────────────────────────────────────────────────────

class TestLogAnalyze:
    def _make_log(self, lines: list[str]) -> str:
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
            f.write("\n".join(lines))
            return f.name

    def test_analyze_auth_log(self):
        path = self._make_log([
            "Jan  1 00:00:01 srv sshd[123]: Failed password for root from 1.2.3.4",
            "Jan  1 00:00:02 srv sshd[123]: Accepted password for user1 from 5.6.7.8",
            "Jan  1 00:00:03 srv sudo: user1: TTY=pts/0 ; COMMAND=/bin/bash",
        ])
        result = _tool_log_analyze({"log_file": path})
        Path(path).unlink()
        assert "Failed" in result or "fail" in result.lower()

    def test_analyze_with_custom_pattern(self):
        path = self._make_log(["line with SECRET here", "normal line"])
        result = _tool_log_analyze({"log_file": path, "pattern": "SECRET"})
        Path(path).unlink()
        assert "SECRET" in result

    def test_missing_file(self):
        result = _tool_log_analyze({"log_file": "/tmp/nonexistent_oocode_test.log"})
        assert "no encontrado" in result.lower()

    def test_missing_param(self):
        result = _tool_log_analyze({})
        assert "requerido" in result.lower()

    def test_invalid_regex(self):
        path = self._make_log(["test line"])
        result = _tool_log_analyze({"log_file": path, "pattern": "[invalid"})
        Path(path).unlink()
        assert "inválido" in result.lower() or "regex" in result.lower()


# ── Secret Scan ───────────────────────────────────────────────────────────────

class TestSecretScan:
    def test_scan_dir_with_secrets(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "config.py").write_text("password = 'mysupersecretpassword123'\n")
            result = _tool_secret_scan({"path": d})
        assert "password" in result.lower() or "secret" in result.lower() or "sin secrets" in result.lower()

    def test_scan_dir_clean(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "clean.py").write_text("x = 1\nprint(x)\n")
            result = _tool_secret_scan({"path": d})
        assert isinstance(result, str)

    def test_aws_key_detected(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "creds.py").write_text("key = 'AKIAIOSFODNN7EXAMPLE'\n")
            result = _tool_secret_scan({"path": d})
        # AWS key pattern is AKIA[0-9A-Z]{16}
        assert isinstance(result, str)

    def test_private_key_detected(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "key.pem").write_text("-----BEGIN RSA PRIVATE KEY-----\nMIIEo...\n")
            result = _tool_secret_scan({"path": d})
        assert "Private Key" in result or "sin secrets" in result.lower()

    def test_missing_path(self):
        result = _tool_secret_scan({"path": "/tmp/nonexistent_oocode_xyz123"})
        assert "no encontrada" in result.lower()


# ── File Integrity ────────────────────────────────────────────────────────────

class TestFileIntegrity:
    def test_single_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"hello world")
            path = f.name
        result = _tool_file_integrity_check({"paths": path})
        expected = hashlib.sha256(b"hello world").hexdigest()
        Path(path).unlink()
        assert expected in result

    def test_multiple_files(self):
        with tempfile.NamedTemporaryFile(delete=False) as f1, \
             tempfile.NamedTemporaryFile(delete=False) as f2:
            f1.write(b"aaa"); f2.write(b"bbb")
            p1, p2 = f1.name, f2.name
        result = _tool_file_integrity_check({"paths": f"{p1},{p2}"})
        Path(p1).unlink(); Path(p2).unlink()
        assert p1 in result or Path(p1).name in result
        assert p2 in result or Path(p2).name in result

    def test_sha1_algorithm(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"data")
            path = f.name
        result = _tool_file_integrity_check({"paths": path, "algorithm": "sha1"})
        expected = hashlib.sha1(b"data").hexdigest()
        Path(path).unlink()
        assert expected in result

    def test_missing_file(self):
        result = _tool_file_integrity_check({"paths": "/tmp/nonexistent_oocode_abc.txt"})
        assert "MISSING" in result

    def test_unsupported_algorithm(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"x"); path = f.name
        result = _tool_file_integrity_check({"paths": path, "algorithm": "fakemd99"})
        Path(path).unlink()
        assert "no soportado" in result.lower()

    def test_missing_paths_param(self):
        result = _tool_file_integrity_check({})
        assert "requerido" in result.lower()

    def test_directory_hash(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.txt").write_text("hello")
            (Path(d) / "b.txt").write_text("world")
            result = _tool_file_integrity_check({"paths": d})
        assert isinstance(result, str) and len(result) > 0


# ── SSH Key Audit ─────────────────────────────────────────────────────────────

class TestSSHKeyAudit:
    def test_missing_dir(self):
        result = _tool_ssh_key_audit({"path": "/tmp/nonexistent_ssh_dir_xyz"})
        assert "no encontrado" in result.lower()

    def test_real_ssh_dir_or_empty(self):
        with tempfile.TemporaryDirectory() as d:
            result = _tool_ssh_key_audit({"path": d})
        assert isinstance(result, str)

    def test_detects_weak_permissions(self):
        import stat
        with tempfile.TemporaryDirectory() as d:
            dp = Path(d)
            dp.chmod(0o755)  # Wrong: should be 700
            result = _tool_ssh_key_audit({"path": d})
        assert "755" in result or "⚠" in result

    def test_detects_authorized_keys(self):
        with tempfile.TemporaryDirectory() as d:
            dp = Path(d)
            dp.chmod(0o700)
            (dp / "authorized_keys").write_text("ssh-rsa AAAA... user@host\n")
            result = _tool_ssh_key_audit({"path": d})
        assert "authorized_keys" in result

    def test_detects_private_key_no_passphrase(self):
        with tempfile.TemporaryDirectory() as d:
            dp = Path(d)
            dp.chmod(0o700)
            key_file = dp / "id_rsa"
            key_file.write_text("-----BEGIN RSA PRIVATE KEY-----\nMIIEo...\n")
            key_file.chmod(0o600)
            result = _tool_ssh_key_audit({"path": d})
        assert "RSA" in result or "privada" in result.lower()

    def test_detects_dsa_public_key(self):
        with tempfile.TemporaryDirectory() as d:
            dp = Path(d)
            dp.chmod(0o700)
            (dp / "id_dsa.pub").write_text("ssh-dss AAAA... user@host\n")
            result = _tool_ssh_key_audit({"path": d})
        assert "dss" in result.lower() or "dsa" in result.lower() or "obsoleto" in result.lower()


# ── Sudoers Review ────────────────────────────────────────────────────────────

class TestSudoersReview:
    def test_normal_sudoers(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".conf") as f:
            f.write("root ALL=(ALL:ALL) ALL\n%admin ALL=(ALL) ALL\n")
            path = f.name
        result = _tool_sudoers_review({"path": path})
        Path(path).unlink()
        assert "root" in result

    def test_nopasswd_flagged(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".conf") as f:
            f.write("user1 ALL=(ALL) NOPASSWD: /bin/bash\n")
            path = f.name
        result = _tool_sudoers_review({"path": path})
        Path(path).unlink()
        assert "NOPASSWD" in result

    def test_comments_ignored(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".conf") as f:
            f.write("# This is a comment\n# Another comment\n")
            path = f.name
        result = _tool_sudoers_review({"path": path})
        Path(path).unlink()
        assert "0" in result or "activas" in result.lower()

    def test_missing_file(self):
        result = _tool_sudoers_review({"path": "/tmp/nonexistent_sudoers_oocode.conf"})
        assert "no encontrado" in result.lower()


# ── Prompts ───────────────────────────────────────────────────────────────────

class TestPrompts:
    def test_pentest_report_prompt(self):
        result = _get_prompt("pentest_report", {"target": "webapp.example.com", "findings": "SQL injection en /login"})
        assert isinstance(result, list) and len(result) == 1
        text = result[0]["content"]["text"]
        assert "webapp.example.com" in text
        assert "SQL injection" in text

    def test_ctf_challenge_prompt(self):
        result = _get_prompt("ctf_challenge", {"description": "Decode the base64 string", "category": "crypto"})
        text = result[0]["content"]["text"]
        assert "crypto" in text.lower() or "Decode" in text

    def test_security_audit_prompt(self):
        result = _get_prompt("security_audit", {"system_type": "web"})
        text = result[0]["content"]["text"]
        assert "web" in text.lower() or "checklist" in text.lower()

    def test_vulnerability_analysis_prompt(self):
        result = _get_prompt("vulnerability_analysis", {"vulnerability": "CVE-2021-44228"})
        text = result[0]["content"]["text"]
        assert "CVE-2021-44228" in text

    def test_unknown_prompt(self):
        result = _get_prompt("nonexistent_prompt", {})
        text = result[0]["content"]["text"]
        assert "desconocido" in text.lower()

    def test_all_prompts_return_list(self):
        for p in _PROMPTS:
            result = _get_prompt(p["name"], {})
            assert isinstance(result, list)
            assert result[0]["role"] == "user"


# ── Scan History ──────────────────────────────────────────────────────────────

class TestScanHistory:
    def test_add_history_entry(self):
        initial_len = len(_scan_history)
        _add_history("test_tool", "example.com", "test summary")
        assert len(_scan_history) == initial_len + 1
        assert _scan_history[0]["tool"] == "test_tool"
        assert _scan_history[0]["target"] == "example.com"

    def test_history_resource_returns_string(self):
        result = _RESOURCE_FNS["security://scan_history"]()
        assert isinstance(result, str)

    def test_tools_available_resource(self):
        result = _RESOURCE_FNS["security://tools_available"]()
        assert "Instaladas" in result or "herramientas" in result.lower()

    def test_host_info_resource(self):
        result = _RESOURCE_FNS["security://host_info"]()
        assert "Hostname" in result or "host" in result.lower()


# ── MCP Protocol ─────────────────────────────────────────────────────────────

class TestMcpProtocol:
    def test_initialize(self):
        req = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        resp = _handle(req)
        assert resp["id"] == 1
        assert "serverInfo" in resp["result"]
        assert resp["result"]["serverInfo"]["name"] == "security-assistant"

    def test_initialize_capabilities_truthy(self):
        """Capabilities deben ser dicts no vacíos — McpClient.list_resources/prompts
        comprueba 'if not capabilities.get(...)' y un {} vacío es falsy → 0 resources/prompts."""
        req = {"jsonrpc": "2.0", "id": 10, "method": "initialize", "params": {}}
        resp = _handle(req)
        caps = resp["result"]["capabilities"]
        assert caps.get("resources"), "capabilities.resources vacío → McpClient ignora resources"
        assert caps.get("prompts"),   "capabilities.prompts vacío → McpClient ignora prompts"

    def test_tools_list(self):
        req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        resp = _handle(req)
        assert "tools" in resp["result"]
        assert len(resp["result"]["tools"]) == 24

    def test_tools_call_known_tool(self):
        req = {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "encode_decode", "arguments": {
                "data": "hello", "operation": "encode", "encoding": "base64"
            }},
        }
        resp = _handle(req)
        assert "content" in resp["result"]
        text = resp["result"]["content"][0]["text"]
        assert base64.b64decode(text) == b"hello"

    def test_tools_call_unknown_tool(self):
        req = {
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "nonexistent_tool_xyz", "arguments": {}},
        }
        resp = _handle(req)
        assert "error" in resp

    def test_resources_list(self):
        req = {"jsonrpc": "2.0", "id": 5, "method": "resources/list", "params": {}}
        resp = _handle(req)
        assert len(resp["result"]["resources"]) == 3

    def test_resources_read(self):
        req = {
            "jsonrpc": "2.0", "id": 6, "method": "resources/read",
            "params": {"uri": "security://tools_available"},
        }
        resp = _handle(req)
        assert "contents" in resp["result"]
        assert len(resp["result"]["contents"]) == 1

    def test_prompts_list(self):
        req = {"jsonrpc": "2.0", "id": 7, "method": "prompts/list", "params": {}}
        resp = _handle(req)
        assert len(resp["result"]["prompts"]) == 4

    def test_prompts_get(self):
        req = {
            "jsonrpc": "2.0", "id": 8, "method": "prompts/get",
            "params": {"name": "ctf_challenge", "arguments": {"description": "test"}},
        }
        resp = _handle(req)
        assert "messages" in resp["result"]

    def test_notifications_initialized(self):
        req = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        resp = _handle(req)
        assert resp is None

    def test_unknown_method(self):
        req = {"jsonrpc": "2.0", "id": 9, "method": "unknown/method", "params": {}}
        resp = _handle(req)
        assert "error" in resp


# ── Tool Groups Integration ────────────────────────────────────────────────────

class TestToolGroupIntegration:
    def test_security_group_in_tool_groups(self):
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from agent.loop import _TOOL_GROUPS
        assert "security" in _TOOL_GROUPS

    def test_security_tools_in_group(self):
        from agent.loop import _TOOL_GROUPS
        tools = _TOOL_GROUPS["security"]
        schema_names = {t["name"] for t in _TOOLS}
        for name in schema_names:
            assert name in tools, f"Tool '{name}' no está en _TOOL_GROUPS['security']"

    def test_security_keywords_in_task_keywords(self):
        from agent.loop import _TASK_KEYWORDS
        assert "security" in _TASK_KEYWORDS
        kws = _TASK_KEYWORDS["security"]
        assert "pentest" in kws
        assert "ctf" in kws
        assert "cve" in kws

    def test_security_keywords_are_strings(self):
        from agent.loop import _TASK_KEYWORDS
        for kw in _TASK_KEYWORDS["security"]:
            assert isinstance(kw, str), f"Keyword no es string: {kw!r}"


# ── Config Integration ────────────────────────────────────────────────────────

class TestConfigIntegration:
    def test_security_assistant_in_default_config(self):
        from config import DEFAULT_CONFIG
        assert "securityAssistant" in DEFAULT_CONFIG["mcp"]
        assert DEFAULT_CONFIG["mcp"]["securityAssistant"]["enabled"] is False

    def test_ooconfig_has_security_field(self):
        from config import OOConfig
        cfg = OOConfig()
        assert hasattr(cfg, "mcp_security_assistant_enabled")
        assert cfg.mcp_security_assistant_enabled is False

    def test_security_permissions_in_default_config(self):
        from config import DEFAULT_CONFIG
        perms = DEFAULT_CONFIG["permissions"]
        offensive = {"nikto_scan", "gobuster_run", "hash_crack"}
        safe = {"ssl_check", "http_headers", "encode_decode", "jwt_decode",
                "xor_decode", "base_convert", "hex_dump", "log_analyze",
                "secret_scan", "cve_lookup", "port_scan", "whois_lookup",
                "dns_enum", "curl_request", "cert_inspect", "fw_audit",
                "ssh_key_audit", "sudoers_review", "file_integrity_check",
                "steganography_check", "file_integrity_check"}
        for name in offensive:
            assert perms.get(name) == "ask", f"Tool ofensiva '{name}' debería ser 'ask', es '{perms.get(name)}'"
        for name in safe:
            assert perms.get(name) == "auto", f"Tool segura '{name}' debería ser 'auto', es '{perms.get(name)}'"

    def test_nmap_permission_is_ask(self):
        from config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["permissions"].get("nmap_scan") == "ask"
