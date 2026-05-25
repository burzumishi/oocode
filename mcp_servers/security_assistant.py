#!/usr/bin/env python3
"""
security_assistant.py — MCP server para tareas de ciberseguridad.
24 tools: recon, web, cripto, análisis, CTF helpers, defensivo.
Protocolo: stdio JSON-RPC 2.0 newline-delimited (igual que oocode_assistant.py).

Uso: python mcp_servers/security_assistant.py
Activar: ~/.oocode/oocode.json → mcp.securityAssistant.enabled = true
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import ipaddress
import json
import os
import re
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# ── Historial de scans en memoria (para resource scan_history) ────────────────
_scan_history: list[dict] = []
_MAX_HISTORY = 50


def _add_history(tool: str, target: str, summary: str) -> None:
    entry = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "tool": tool,
        "target": target,
        "summary": summary[:200],
    }
    _scan_history.insert(0, entry)
    if len(_scan_history) > _MAX_HISTORY:
        _scan_history.pop()


# ── Helpers stdio ─────────────────────────────────────────────────────────────

def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _recv() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        return None
    return json.loads(line.strip())


def _ok(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id: Any, code: int, msg: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": msg}}


# ── Utilidades internas ───────────────────────────────────────────────────────

def _cmd_available(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _get_tmp_dir() -> Path:
    """Devuelve ~/.oocode/tmp, creándolo si no existe."""
    d = Path.home() / ".oocode" / "tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _run(args: list[str], timeout: int = 30, input_data: str | None = None) -> tuple[int, str, str]:
    """Ejecuta un comando y devuelve (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input_data,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Timeout ({timeout}s)"
    except FileNotFoundError:
        return -2, "", f"Comando no encontrado: {args[0]}"
    except Exception as exc:
        return -3, "", str(exc)


def _require(cmd: str) -> str | None:
    """Devuelve mensaje de instalación si cmd no está disponible, None si sí está."""
    if not _cmd_available(cmd):
        suggestions = {
            "nmap":       "sudo apt install nmap",
            "nikto":      "sudo apt install nikto",
            "gobuster":   "sudo apt install gobuster  # o: go install github.com/OJ/gobuster/v3@latest",
            "hashcat":    "sudo apt install hashcat",
            "whois":      "sudo apt install whois",
            "dig":        "sudo apt install dnsutils",
            "openssl":    "sudo apt install openssl",
            "trufflehog": "pip install trufflehog  # o: brew install trufflehog",
            "gitleaks":   "https://github.com/gitleaks/gitleaks/releases",
            "steghide":   "sudo apt install steghide",
            "stegdetect": "sudo apt install stegdetect",
            "xxd":        "sudo apt install xxd  # o viene con vim",
            "iptables":   "sudo apt install iptables",
            "ufw":        "sudo apt install ufw",
            "ssh-keygen": "sudo apt install openssh-client",
        }
        hint = suggestions.get(cmd, f"instala {cmd}")
        return f"Herramienta no disponible: `{cmd}`. Para instalar: {hint}"
    return None


# ══════════════════════════════════════════════════════════════════════════════
# TOOLS — Red / Recon
# ══════════════════════════════════════════════════════════════════════════════

def _tool_nmap_scan(args: dict) -> str:
    target = args.get("target", "").strip()
    if not target:
        return "Parámetro requerido: target"
    if err := _require("nmap"):
        return err
    ports  = args.get("ports", "")
    flags  = args.get("flags", "")
    cmd = ["nmap", "-v"]
    if ports:
        cmd += ["-p", ports]
    if flags:
        cmd += flags.split()
    cmd.append(target)
    rc, out, err = _run(cmd, timeout=120)
    result = out if out else err
    _add_history("nmap_scan", target, (out or err)[:200])
    if rc not in (0, 1):
        return f"Error nmap (rc={rc}):\n{err}"
    return result or "Sin resultados"


def _tool_port_scan(args: dict) -> str:
    host = args.get("host", "").strip()
    if not host:
        return "Parámetro requerido: host"
    ports_raw = args.get("ports", "")
    if not ports_raw:
        return "Parámetro requerido: ports (ej. '22,80,443' o '1-1024')"
    timeout = float(args.get("timeout", 2))

    # Parsear lista/rango de puertos
    port_list: list[int] = []
    for part in str(ports_raw).split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            port_list.extend(range(int(a), int(b) + 1))
        else:
            port_list.append(int(part))

    if len(port_list) > 10000:
        return "Demasiados puertos (máx 10000)"

    open_ports: list[int] = []
    closed: int = 0
    for port in port_list:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                open_ports.append(port)
        except (socket.timeout, ConnectionRefusedError, OSError):
            closed += 1

    _add_history("port_scan", host, f"open={open_ports}")
    lines = [f"Scan de {host} — {len(port_list)} puertos en {timeout}s timeout"]
    if open_ports:
        lines.append(f"Puertos ABIERTOS ({len(open_ports)}): {', '.join(map(str, open_ports))}")
    else:
        lines.append("No se encontraron puertos abiertos")
    lines.append(f"Cerrados/filtrados: {closed}")
    return "\n".join(lines)


def _tool_ssl_check(args: dict) -> str:
    host = args.get("host", "").strip()
    if not host:
        return "Parámetro requerido: host"
    port = int(args.get("port", 443))
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                cipher = ssock.cipher()
                version = ssock.version()
    except ssl.SSLError as exc:
        return f"Error SSL: {exc}"
    except (socket.timeout, OSError) as exc:
        return f"Error de conexión: {exc}"

    subject = dict(x[0] for x in cert.get("subject", []))
    issuer  = dict(x[0] for x in cert.get("issuer", []))
    san     = cert.get("subjectAltName", [])
    expiry  = cert.get("notAfter", "?")
    valid_from = cert.get("notBefore", "?")

    lines = [
        f"SSL/TLS: {host}:{port}",
        f"  Versión:       {version}",
        f"  Cipher:        {cipher[0]} ({cipher[2]} bits)",
        f"  CN:            {subject.get('commonName', '?')}",
        f"  Organización:  {subject.get('organizationName', '?')}",
        f"  Emisor:        {issuer.get('organizationName', '?')}",
        f"  Válido desde:  {valid_from}",
        f"  Expira:        {expiry}",
        f"  SANs:          {', '.join(v for _, v in san[:10])}",
    ]
    _add_history("ssl_check", f"{host}:{port}", f"version={version} expiry={expiry}")
    return "\n".join(lines)


def _tool_whois_lookup(args: dict) -> str:
    target = args.get("domain", "").strip() or args.get("target", "").strip()
    if not target:
        return "Parámetro requerido: domain"
    if err := _require("whois"):
        return err
    rc, out, err = _run(["whois", target], timeout=20)
    if rc != 0:
        return f"Error whois: {err}"
    _add_history("whois_lookup", target, out[:200])
    return out[:4000] if out else "Sin resultados"


def _tool_dns_enum(args: dict) -> str:
    domain = args.get("domain", "").strip()
    if not domain:
        return "Parámetro requerido: domain"
    types_raw = args.get("record_types", "A,AAAA,MX,NS,TXT,CNAME")
    record_types = [t.strip().upper() for t in str(types_raw).split(",")]

    lines = [f"DNS enum: {domain}"]
    if _cmd_available("dig"):
        for rtype in record_types:
            rc, out, _ = _run(["dig", "+short", rtype, domain], timeout=10)
            if rc == 0 and out.strip():
                lines.append(f"\n{rtype}:")
                for row in out.strip().splitlines():
                    lines.append(f"  {row}")
    elif _cmd_available("nslookup"):
        for rtype in record_types:
            rc, out, _ = _run(["nslookup", "-type=" + rtype, domain], timeout=10)
            if rc == 0:
                lines.append(f"\n{rtype}:\n{out[:500]}")
    else:
        # Fallback stdlib DNS (solo A/AAAA)
        try:
            info = socket.getaddrinfo(domain, None)
            addrs = list({r[4][0] for r in info})
            lines.append(f"\nA/AAAA (stdlib): {', '.join(addrs)}")
        except socket.gaierror as exc:
            return f"Error DNS: {exc}"

    _add_history("dns_enum", domain, str(lines[:3]))
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# TOOLS — Web
# ══════════════════════════════════════════════════════════════════════════════

def _tool_http_headers(args: dict) -> str:
    url = args.get("url", "").strip()
    if not url:
        return "Parámetro requerido: url"
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    follow = bool(args.get("follow_redirects", True))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OOCode-SecurityAssistant/1.0"})
        ctx = ssl.create_default_context() if url.startswith("https") else None
        if not follow:
            opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
            resp = opener.open(req, timeout=15, context=ctx) if ctx else opener.open(req, timeout=15)
        else:
            resp = urllib.request.urlopen(req, timeout=15, context=ctx) if ctx else urllib.request.urlopen(req, timeout=15)
        status = resp.status
        headers = dict(resp.headers)
        resp.close()
    except urllib.error.HTTPError as exc:
        status = exc.code
        headers = dict(exc.headers) if exc.headers else {}
    except Exception as exc:
        return f"Error: {exc}"

    security_headers = {
        "strict-transport-security", "content-security-policy",
        "x-content-type-options", "x-frame-options", "x-xss-protection",
        "referrer-policy", "permissions-policy", "cross-origin-opener-policy",
    }
    lines = [f"HTTP {status} — {url}", ""]
    lines.append("Headers de seguridad:")
    for h in security_headers:
        val = headers.get(h) or headers.get(h.title()) or headers.get(h.upper())
        mark = "✔" if val else "✘"
        lines.append(f"  {mark} {h}: {val or '(ausente)'}")
    lines.append("\nTodos los headers:")
    for k, v in sorted(headers.items()):
        lines.append(f"  {k}: {v}")
    _add_history("http_headers", url, f"status={status}")
    return "\n".join(lines)


def _tool_nikto_scan(args: dict) -> str:
    target = args.get("target", "").strip()
    if not target:
        return "Parámetro requerido: target"
    if err := _require("nikto"):
        return err
    flags = args.get("flags", "")
    cmd = ["nikto", "-h", target]
    if flags:
        cmd += flags.split()
    rc, out, err = _run(cmd, timeout=180)
    result = out + (f"\n[stderr]: {err}" if err else "")
    _add_history("nikto_scan", target, (out or err)[:200])
    if rc == -2:
        return err
    return result or "Sin resultados"


def _tool_gobuster_run(args: dict) -> str:
    target = args.get("target", "").strip()
    if not target:
        return "Parámetro requerido: target"
    wordlist = args.get("wordlist", "").strip()
    if not wordlist:
        return "Parámetro requerido: wordlist"
    if err := _require("gobuster"):
        return err
    if not Path(wordlist).exists():
        return f"Wordlist no encontrada: {wordlist}"
    mode  = args.get("mode", "dir")
    flags = args.get("flags", "")
    cmd = ["gobuster", mode, "-u", target, "-w", wordlist, "-q"]
    if flags:
        cmd += flags.split()
    rc, out, err = _run(cmd, timeout=300)
    result = out + (f"\n[stderr]: {err}" if err else "")
    _add_history("gobuster_run", target, (out or err)[:200])
    if rc == -2:
        return err
    return result or "Sin resultados"


def _tool_curl_request(args: dict) -> str:
    url = args.get("url", "").strip()
    if not url:
        return "Parámetro requerido: url"
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    method  = args.get("method", "GET").upper()
    headers = args.get("headers", {})
    data    = args.get("data", "")
    insecure = bool(args.get("insecure", False))

    req = urllib.request.Request(url, method=method)
    req.add_header("User-Agent", "OOCode-SecurityAssistant/1.0")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    body = data.encode() if data else None
    ctx = ssl.create_default_context()
    if insecure:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    try:
        resp = urllib.request.urlopen(req, data=body, timeout=15, context=ctx)
        status = resp.status
        resp_headers = dict(resp.headers)
        body_raw = resp.read(8192)
        resp.close()
        body_text = body_raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        resp_headers = dict(exc.headers) if exc.headers else {}
        body_text = exc.read(4096).decode("utf-8", errors="replace")
    except Exception as exc:
        return f"Error: {exc}"

    lines = [f"{method} {url} → HTTP {status}"]
    for k, v in resp_headers.items():
        lines.append(f"  {k}: {v}")
    lines.append(f"\nBody (primeros 2000 chars):\n{body_text[:2000]}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# TOOLS — Criptografía
# ══════════════════════════════════════════════════════════════════════════════

def _tool_encode_decode(args: dict) -> str:
    data      = args.get("data", "")
    operation = args.get("operation", "encode").lower()
    encoding  = args.get("encoding", "base64").lower()

    try:
        if encoding == "base64":
            if operation == "encode":
                return base64.b64encode(data.encode()).decode()
            else:
                return base64.b64decode(data).decode("utf-8", errors="replace")
        elif encoding == "base32":
            if operation == "encode":
                return base64.b32encode(data.encode()).decode()
            else:
                return base64.b32decode(data).decode("utf-8", errors="replace")
        elif encoding in ("hex", "hexadecimal"):
            if operation == "encode":
                return data.encode().hex()
            else:
                return bytes.fromhex(data).decode("utf-8", errors="replace")
        elif encoding == "url":
            if operation == "encode":
                return urllib.parse.quote(data)
            else:
                return urllib.parse.unquote(data)
        elif encoding == "rot13":
            import codecs
            return codecs.encode(data, "rot_13")
        elif encoding == "html":
            import html
            if operation == "encode":
                return html.escape(data)
            else:
                return html.unescape(data)
        elif encoding == "unicode_escape":
            if operation == "encode":
                return data.encode("unicode_escape").decode()
            else:
                return data.encode().decode("unicode_escape")
        else:
            return f"Encoding no soportado: {encoding}. Opciones: base64, base32, hex, url, rot13, html, unicode_escape"
    except Exception as exc:
        return f"Error al {operation} ({encoding}): {exc}"


def _tool_hash_crack(args: dict) -> str:
    hash_val = args.get("hash_value", "").strip()
    if not hash_val:
        return "Parámetro requerido: hash_value"
    wordlist = args.get("wordlist", "").strip()
    if not wordlist:
        return "Parámetro requerido: wordlist"
    algorithm = args.get("algorithm", "")
    if not Path(wordlist).exists():
        return f"Wordlist no encontrada: {wordlist}"

    # Intentar primero con Python puro (wordlist pequeña)
    hash_len = len(hash_val)
    algos_by_len: dict[int, list[str]] = {
        32: ["md5"],
        40: ["sha1"],
        56: ["sha224"],
        64: ["sha256"],
        96: ["sha384"],
        128: ["sha512"],
    }
    candidates = [algorithm] if algorithm else algos_by_len.get(hash_len, ["md5", "sha1", "sha256"])

    try:
        with open(wordlist, encoding="utf-8", errors="ignore") as f:
            lines_checked = 0
            for line in f:
                word = line.rstrip("\n")
                for algo in candidates:
                    try:
                        h = hashlib.new(algo, word.encode()).hexdigest()
                        if h.lower() == hash_val.lower():
                            return f"Hash crackeado ({algo}): {word!r}"
                    except ValueError:
                        pass
                lines_checked += 1
                if lines_checked >= 500_000:
                    break
            plain_result = f"No encontrado en los primeros {lines_checked} líneas de {wordlist}"
    except Exception as exc:
        plain_result = f"Error leyendo wordlist: {exc}"

    # Intentar con hashcat si está disponible
    if _cmd_available("hashcat"):
        mode_map = {"md5": "0", "sha1": "100", "sha256": "1400", "sha512": "1700", "ntlm": "1000"}
        mode = mode_map.get(algorithm or "", "0")
        rc, out, err = _run(["hashcat", "-m", mode, "-a", "0", "--quiet",
                              "--potfile-disable", hash_val, wordlist], timeout=60)
        if rc == 0 and ":" in out:
            cracked = out.strip().split("\n")[0].split(":")[-1]
            return f"Crackeado con hashcat: {cracked!r}"

    return plain_result


def _tool_jwt_decode(args: dict) -> str:
    token = args.get("token", "").strip()
    if not token:
        return "Parámetro requerido: token"
    parts = token.split(".")
    if len(parts) != 3:
        return f"Token JWT inválido: debe tener 3 partes separadas por '.', tiene {len(parts)}"

    def decode_part(part: str) -> dict:
        pad = 4 - len(part) % 4
        part += "=" * (pad % 4)
        raw = base64.urlsafe_b64decode(part)
        return json.loads(raw)

    try:
        header  = decode_part(parts[0])
        payload = decode_part(parts[1])
    except Exception as exc:
        return f"Error decodificando JWT: {exc}"

    lines = ["JWT decodificado (sin verificación de firma):"]
    lines.append(f"\nHeader:\n{json.dumps(header, indent=2)}")
    lines.append(f"\nPayload:\n{json.dumps(payload, indent=2)}")

    # Verificar expiración
    if "exp" in payload:
        exp = datetime.datetime.fromtimestamp(payload["exp"])
        now = datetime.datetime.now()
        status = "EXPIRADO" if now > exp else f"válido hasta {exp.isoformat()}"
        lines.append(f"\nExpiración: {exp.isoformat()} ({status})")
    if "iat" in payload:
        iat = datetime.datetime.fromtimestamp(payload["iat"])
        lines.append(f"Emitido:    {iat.isoformat()}")
    if "nbf" in payload:
        nbf = datetime.datetime.fromtimestamp(payload["nbf"])
        lines.append(f"No antes:   {nbf.isoformat()}")

    lines.append(f"\nFirma (base64url): {parts[2][:40]}...")
    lines.append(f"Algoritmo: {header.get('alg', '?')}")
    if header.get("alg") in ("none", "None", "NONE"):
        lines.append("⚠ ALERTA: algoritmo 'none' — token sin firma válida")
    return "\n".join(lines)


def _tool_cert_inspect(args: dict) -> str:
    target = args.get("host_or_file", "").strip()
    if not target:
        return "Parámetro requerido: host_or_file"
    port = int(args.get("port", 443))

    if Path(target).exists():
        # Es un fichero de certificado
        if not _cmd_available("openssl"):
            return _require("openssl") or "openssl no disponible"
        rc, out, err = _run(["openssl", "x509", "-in", target, "-text", "-noout"], timeout=10)
        return out if rc == 0 else f"Error: {err}"

    # Es un hostname
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((target, port), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=target) as ssock:
                der = ssock.getpeercert(binary_form=True)
                cert = ssock.getpeercert()
    except Exception as exc:
        return f"Error de conexión: {exc}"

    if _cmd_available("openssl"):
        # Usar openssl para output detallado
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".der", delete=False, dir=_get_tmp_dir()) as f:
            f.write(der)
            tmpfile = f.name
        rc, out, err = _run(["openssl", "x509", "-inform", "DER", "-in", tmpfile, "-text", "-noout"], timeout=10)
        Path(tmpfile).unlink(missing_ok=True)
        if rc == 0:
            return out[:4000]

    # Fallback: solo info básica del peercert
    subject = dict(x[0] for x in cert.get("subject", []))
    issuer  = dict(x[0] for x in cert.get("issuer", []))
    lines = [
        f"Certificado: {target}:{port}",
        f"  CN:       {subject.get('commonName', '?')}",
        f"  Org:      {subject.get('organizationName', '?')}",
        f"  Emisor:   {issuer.get('commonName', '?')}",
        f"  Válido:   {cert.get('notBefore', '?')} → {cert.get('notAfter', '?')}",
        f"  SANs:     {', '.join(v for _, v in cert.get('subjectAltName', [])[:10])}",
    ]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# TOOLS — Análisis
# ══════════════════════════════════════════════════════════════════════════════

def _tool_log_analyze(args: dict) -> str:
    log_file = args.get("log_file", "").strip()
    if not log_file:
        return "Parámetro requerido: log_file"
    path = Path(log_file).expanduser()
    if not path.exists():
        return f"Fichero no encontrado: {path}"
    pattern = args.get("pattern", "")
    lines_n = int(args.get("lines", 200))

    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()
    except PermissionError:
        return f"Sin permisos de lectura: {path}"

    # Patrones de seguridad comunes
    security_patterns = {
        "Failed login":    re.compile(r"(fail|invalid|denied|refused|error)", re.I),
        "SSH brute-force": re.compile(r"Failed password|Invalid user|authentication failure", re.I),
        "Sudo use":        re.compile(r"sudo:", re.I),
        "Privilege esc.":  re.compile(r"(su |sudo |NOPASSWD|wheel|root)", re.I),
    }

    if pattern:
        try:
            rx = re.compile(pattern, re.I)
            matches = [l.rstrip() for l in all_lines if rx.search(l)]
        except re.error as exc:
            return f"Patrón regex inválido: {exc}"
        return "\n".join(matches[-lines_n:]) or "Sin coincidencias"

    # Análisis automático de seguridad
    results: dict[str, list[str]] = {k: [] for k in security_patterns}
    for line in all_lines:
        for label, rx in security_patterns.items():
            if rx.search(line):
                results[label].append(line.rstrip())

    lines_out = [f"Análisis de seguridad: {path} ({len(all_lines)} líneas)"]
    for label, hits in results.items():
        if hits:
            lines_out.append(f"\n{label} ({len(hits)} ocurrencias):")
            for h in hits[-5:]:
                lines_out.append(f"  {h[:200]}")
    if not any(results.values()):
        lines_out.append("\nNo se encontraron patrones de seguridad conocidos.")
        lines_out.append(f"\nÚltimas {min(lines_n, len(all_lines))} líneas:")
        for l in all_lines[-lines_n:]:
            lines_out.append(f"  {l.rstrip()[:200]}")
    return "\n".join(lines_out)


def _tool_secret_scan(args: dict) -> str:
    path = args.get("path", ".").strip()
    tool = args.get("tool", "auto").lower()
    scan_path = Path(path).expanduser()
    if not scan_path.exists():
        return f"Ruta no encontrada: {scan_path}"

    # Intentar trufflehog
    if tool in ("auto", "trufflehog") and _cmd_available("trufflehog"):
        rc, out, err = _run(["trufflehog", "filesystem", str(scan_path), "--no-update"], timeout=120)
        result = out + (f"\n[stderr]: {err[:500]}" if err else "")
        _add_history("secret_scan", path, (out or err)[:200])
        return result or "Sin secrets encontrados"

    # Intentar gitleaks
    if tool in ("auto", "gitleaks") and _cmd_available("gitleaks"):
        rc, out, err = _run(["gitleaks", "detect", "--source", str(scan_path), "--no-git", "-v"], timeout=120)
        result = out + (f"\n[stderr]: {err[:500]}" if err else "")
        _add_history("secret_scan", path, (out or err)[:200])
        return result or "Sin secrets encontrados"

    # Fallback: regex básico
    secret_patterns = [
        (re.compile(r'(?i)(password|passwd|pwd)\s*[=:]\s*["\']?([^\s"\']+)'), "Password"),
        (re.compile(r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\']?([A-Za-z0-9_\-]{16,})'), "API Key"),
        (re.compile(r'(?i)(secret[_-]?key|secret)\s*[=:]\s*["\']?([A-Za-z0-9_\-]{16,})'), "Secret"),
        (re.compile(r'(?i)(access[_-]?token|auth[_-]?token)\s*[=:]\s*["\']?([A-Za-z0-9_\-]{16,})'), "Token"),
        (re.compile(r'AKIA[0-9A-Z]{16}'), "AWS Access Key"),
        (re.compile(r'(?i)-----BEGIN (RSA|EC|DSA|OPENSSH) PRIVATE KEY-----'), "Private Key"),
        (re.compile(r'ghp_[A-Za-z0-9]{36}'), "GitHub Token"),
    ]

    findings: list[str] = []
    skipped = 0
    for f in scan_path.rglob("*"):
        if not f.is_file():
            continue
        if f.stat().st_size > 500_000:
            skipped += 1
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except (PermissionError, OSError):
            continue
        for rx, label in secret_patterns:
            for m in rx.finditer(text):
                line_no = text[:m.start()].count("\n") + 1
                findings.append(f"  [{label}] {f}:{line_no}: {m.group()[:80]}")

    _add_history("secret_scan", path, f"found={len(findings)}")
    if not findings:
        return f"Sin secrets encontrados en {scan_path} (escaneados con regex interno; instala trufflehog o gitleaks para mayor cobertura)"
    return (
        f"Posibles secrets en {scan_path} ({len(findings)} hallazgos, {skipped} ficheros omitidos por tamaño):\n"
        + "\n".join(findings[:100])
        + ("\n..." if len(findings) > 100 else "")
        + "\n\n⚠ Verificar manualmente — puede haber falsos positivos."
    )


def _tool_cve_lookup(args: dict) -> str:
    query = args.get("query", "").strip()
    if not query:
        return "Parámetro requerido: query"
    limit = int(args.get("limit", 5))

    # NVD API 2.0 — sin API key, rate-limited
    base = "https://services.nvd.nist.gov/rest/json/cves/2.0"
    params: dict[str, str] = {"resultsPerPage": str(min(limit, 20))}

    if re.match(r"CVE-\d{4}-\d{4,}", query, re.I):
        params["cveId"] = query.upper()
    else:
        params["keywordSearch"] = query
        params["keywordExactMatch"] = "false"

    url = base + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "OOCode-SecurityAssistant/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            return "NVD API rate limit alcanzado. Espera 30 segundos y vuelve a intentarlo."
        return f"Error NVD API: HTTP {exc.code}"
    except Exception as exc:
        return f"Error consultando NVD: {exc}"

    vulns = data.get("vulnerabilities", [])
    if not vulns:
        return f"Sin resultados para: {query}"

    lines = [f"CVEs para '{query}' ({data.get('totalResults', '?')} total):"]
    for item in vulns:
        cve = item.get("cve", {})
        cve_id = cve.get("id", "?")
        desc_list = cve.get("descriptions", [])
        desc = next((d["value"] for d in desc_list if d.get("lang") == "en"), "Sin descripción")
        metrics = cve.get("metrics", {})
        score = "?"
        severity = "?"
        for k in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            if k in metrics and metrics[k]:
                m = metrics[k][0].get("cvssData", {})
                score = m.get("baseScore", "?")
                severity = m.get("baseSeverity", "?")
                break
        lines.append(f"\n{cve_id} | Score: {score} ({severity})")
        lines.append(f"  {desc[:300]}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# TOOLS — CTF helpers
# ══════════════════════════════════════════════════════════════════════════════

def _tool_xor_decode(args: dict) -> str:
    data_raw = args.get("data", "").strip()
    key_raw  = args.get("key", "").strip()
    if not data_raw or not key_raw:
        return "Parámetros requeridos: data, key"
    encoding = args.get("encoding", "hex").lower()

    try:
        if encoding == "hex":
            data = bytes.fromhex(data_raw.replace(" ", "").replace("0x", ""))
        elif encoding == "base64":
            data = base64.b64decode(data_raw)
        elif encoding == "raw":
            data = data_raw.encode("latin-1")
        else:
            return f"Encoding no soportado: {encoding}. Opciones: hex, base64, raw"

        if key_raw.startswith("0x"):
            key_bytes = bytes.fromhex(key_raw[2:])
        else:
            try:
                key_bytes = bytes.fromhex(key_raw.replace(" ", ""))
            except ValueError:
                key_bytes = key_raw.encode()
    except Exception as exc:
        return f"Error decodificando input: {exc}"

    result = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data))
    printable = "".join(chr(b) if 32 <= b < 127 else "." for b in result)
    lines = [
        f"XOR decode ({len(data)} bytes con key {key_raw!r}):",
        f"  Hex:   {result.hex()}",
        f"  ASCII: {printable}",
        f"  UTF-8: {result.decode('utf-8', errors='replace')}",
    ]
    return "\n".join(lines)


def _tool_steganography_check(args: dict) -> str:
    image_file = args.get("image_file", "").strip()
    if not image_file:
        return "Parámetro requerido: image_file"
    path = Path(image_file).expanduser()
    if not path.exists():
        return f"Fichero no encontrado: {path}"

    results: list[str] = [f"Análisis de esteganografía: {path}"]

    # steghide
    if _cmd_available("steghide"):
        rc, out, err = _run(["steghide", "info", str(path), "-p", ""], timeout=10)
        output = (out + err).strip()
        results.append(f"\nsteghide: {output[:300] or 'sin resultado'}")

    # stegdetect
    if _cmd_available("stegdetect"):
        rc, out, err = _run(["stegdetect", str(path)], timeout=10)
        results.append(f"\nstegdetect: {(out or err).strip()[:300]}")

    # strings (para texto oculto)
    if _cmd_available("strings"):
        rc, out, _ = _run(["strings", "-n", "8", str(path)], timeout=5)
        if out:
            interesting = [l for l in out.splitlines() if re.search(r'[A-Za-z]{4}', l)][:20]
            results.append(f"\nstrings interesantes ({len(interesting)}):")
            for s in interesting[:10]:
                results.append(f"  {s}")

    # Metadatos EXIF con exiftool
    if _cmd_available("exiftool"):
        rc, out, _ = _run(["exiftool", str(path)], timeout=10)
        results.append(f"\nEXIF metadata:\n{out[:500]}")

    if len(results) == 1:
        results.append("\nNinguna herramienta disponible (steghide, stegdetect, strings, exiftool).")
        results.append("Instalar: sudo apt install steghide stegdetect binutils libimage-exiftool-perl")

    return "\n".join(results)


def _tool_base_convert(args: dict) -> str:
    value     = args.get("value", "").strip()
    from_base = int(args.get("from_base", 10))
    to_base   = int(args.get("to_base", 16))
    if not value:
        return "Parámetro requerido: value"
    if not (2 <= from_base <= 36 and 2 <= to_base <= 36):
        return "Las bases deben estar entre 2 y 36"
    try:
        decimal = int(value, from_base)
    except ValueError:
        return f"Valor '{value}' no es válido en base {from_base}"
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    if decimal == 0:
        return "0"
    negative = decimal < 0
    n = abs(decimal)
    result_digits: list[str] = []
    while n:
        result_digits.append(digits[n % to_base])
        n //= to_base
    result = ("−" if negative else "") + "".join(reversed(result_digits))
    return (
        f"{value} (base {from_base}) = {result} (base {to_base})\n"
        f"  Decimal: {decimal}\n"
        f"  Hex: {decimal:x}  Oct: {decimal:o}  Bin: {decimal:b}"
    )


def _tool_hex_dump(args: dict) -> str:
    source  = args.get("file_or_data", "").strip()
    length  = int(args.get("length", 256))
    offset  = int(args.get("offset", 0))
    if not source:
        return "Parámetro requerido: file_or_data"

    path = Path(source).expanduser()
    if path.exists() and path.is_file():
        if _cmd_available("xxd"):
            cmd = ["xxd", "-l", str(length), "-s", str(offset), str(path)]
            rc, out, err = _run(cmd, timeout=5)
            if rc == 0:
                return out
        # Fallback Python
        try:
            with open(path, "rb") as f:
                f.seek(offset)
                raw = f.read(length)
        except Exception as exc:
            return f"Error leyendo fichero: {exc}"
    else:
        # Tratar como string hex o texto
        try:
            raw = bytes.fromhex(source.replace(" ", ""))[:length]
        except ValueError:
            raw = source.encode("utf-8")[:length]

    # Formatear hexdump
    lines: list[str] = []
    for i in range(0, len(raw), 16):
        chunk = raw[i:i + 16]
        hex_part  = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{i + offset:08x}  {hex_part:<48}  |{ascii_part}|")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# TOOLS — Defensivo
# ══════════════════════════════════════════════════════════════════════════════

def _tool_fw_audit(args: dict) -> str:
    tool_pref = args.get("tool", "auto").lower()
    lines: list[str] = ["Auditoría de firewall:"]

    if tool_pref in ("auto", "ufw") and _cmd_available("ufw"):
        rc, out, err = _run(["ufw", "status", "verbose"], timeout=10)
        lines.append(f"\n--- UFW ---\n{out or err}")

    if tool_pref in ("auto", "iptables") and _cmd_available("iptables"):
        for table in ("filter", "nat", "mangle"):
            rc, out, err = _run(["iptables", "-t", table, "-L", "-n", "-v", "--line-numbers"], timeout=10)
            if rc == 0:
                lines.append(f"\n--- iptables ({table}) ---\n{out}")

    if tool_pref in ("auto", "nft") and _cmd_available("nft"):
        rc, out, err = _run(["nft", "list", "ruleset"], timeout=10)
        if rc == 0:
            lines.append(f"\n--- nftables ---\n{out[:2000]}")

    if len(lines) == 1:
        lines.append("Ninguna herramienta de firewall disponible (ufw, iptables, nft).")

    return "\n".join(lines)


def _tool_ssh_key_audit(args: dict) -> str:
    ssh_dir = Path(args.get("path", "~/.ssh")).expanduser()
    lines = [f"Auditoría SSH: {ssh_dir}"]

    if not ssh_dir.exists():
        return f"Directorio no encontrado: {ssh_dir}"

    # Permisos del directorio
    mode = oct(ssh_dir.stat().st_mode)[-3:]
    ok = "✔" if mode == "700" else "⚠"
    lines.append(f"\n{ok} Permisos directorio: {mode} (recomendado: 700)")

    weak_types = {"dsa", "ecdsa-sha2-nistp256", "rsa"}  # RSA <4096 también es weak
    key_exts = {".pem", ""}

    for f in sorted(ssh_dir.iterdir()):
        if not f.is_file():
            continue
        fmode = oct(f.stat().st_mode)[-3:]
        name  = f.name

        if name == "authorized_keys":
            lines.append(f"\nauthorized_keys ({fmode}):")
            try:
                for ln, line in enumerate(f.read_text().splitlines(), 1):
                    if line.strip() and not line.startswith("#"):
                        ktype = line.split()[0] if line.split() else "?"
                        lines.append(f"  [{ln}] {ktype}: {line[:80]}")
            except PermissionError:
                lines.append("  Sin permisos de lectura")

        elif name == "known_hosts":
            try:
                n = sum(1 for l in f.read_text().splitlines() if l.strip() and not l.startswith("#"))
                lines.append(f"\nknown_hosts: {n} entradas")
            except PermissionError:
                pass

        elif not name.endswith(".pub") and f.suffix not in (".cfg", ".conf", ".txt", ".log"):
            # Clave privada
            perm_ok = "✔" if fmode == "600" else f"⚠ {fmode}"
            lines.append(f"\nClave privada: {name} ({perm_ok})")
            try:
                header = f.read_text(errors="ignore")[:200]
                if "OPENSSH" in header:
                    lines.append("  Tipo: OpenSSH")
                elif "RSA" in header:
                    lines.append("  Tipo: RSA")
                elif "EC" in header:
                    lines.append("  Tipo: EC")
                elif "DSA" in header:
                    lines.append("  Tipo: DSA ⚠ (deprecado)")
                if "ENCRYPTED" in header or "Proc-Type" in header:
                    lines.append("  Protegida con passphrase: sí ✔")
                else:
                    lines.append("  Protegida con passphrase: NO ⚠")
            except PermissionError:
                lines.append("  Sin permisos de lectura")

        elif name.endswith(".pub"):
            try:
                content = f.read_text().strip()
                ktype = content.split()[0] if content.split() else "?"
                lines.append(f"\nClave pública: {name} — {ktype}")
                if ktype in ("ssh-dss",):
                    lines.append("  ⚠ DSA es obsoleto y vulnerable")
            except PermissionError:
                pass

    # ssh_config
    for cfg_file in (ssh_dir / "config", Path("/etc/ssh/sshd_config")):
        if cfg_file.exists():
            try:
                content = cfg_file.read_text(errors="ignore")
                risky = []
                if re.search(r"PermitRootLogin\s+yes", content, re.I):
                    risky.append("PermitRootLogin yes ⚠")
                if re.search(r"PasswordAuthentication\s+yes", content, re.I):
                    risky.append("PasswordAuthentication yes ⚠")
                if re.search(r"PermitEmptyPasswords\s+yes", content, re.I):
                    risky.append("PermitEmptyPasswords yes ⚠")
                if risky:
                    lines.append(f"\n{cfg_file} — Issues:")
                    for r in risky:
                        lines.append(f"  {r}")
            except PermissionError:
                pass

    return "\n".join(lines)


def _tool_sudoers_review(args: dict) -> str:
    path_raw = args.get("path", "/etc/sudoers")
    path = Path(path_raw)
    lines_out: list[str] = [f"Revisión sudoers: {path}"]

    try:
        content = path.read_text(errors="ignore")
    except PermissionError:
        return f"Sin permisos para leer {path}. Prueba con sudo o como root."
    except FileNotFoundError:
        return f"Fichero no encontrado: {path}"

    risks: list[str] = []
    entries: list[str] = []

    for ln, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        entries.append(f"  [{ln:3d}] {stripped}")
        if "NOPASSWD" in stripped:
            risks.append(f"  [{ln}] NOPASSWD: {stripped}")
        if "ALL=(ALL)" in stripped and "NOPASSWD" in stripped:
            risks.append(f"  [{ln}] ⚠ Root sin contraseña: {stripped}")
        if stripped.startswith("%") and "ALL" in stripped:
            risks.append(f"  [{ln}] Grupo con acceso amplio: {stripped}")

    lines_out.append(f"\nEntradas activas ({len(entries)}):")
    lines_out.extend(entries[:50])
    if risks:
        lines_out.append(f"\n⚠ Configuraciones de riesgo ({len(risks)}):")
        lines_out.extend(risks)
    else:
        lines_out.append("\n✔ Sin configuraciones de alto riesgo detectadas")

    # Leer /etc/sudoers.d/
    sudoers_d = Path("/etc/sudoers.d")
    if sudoers_d.exists():
        try:
            drops = list(sudoers_d.iterdir())
            lines_out.append(f"\n/etc/sudoers.d/ ({len(drops)} ficheros):")
            for f in drops:
                lines_out.append(f"  {f.name}")
        except PermissionError:
            pass

    return "\n".join(lines_out)


def _tool_file_integrity_check(args: dict) -> str:
    paths_raw = args.get("paths", "")
    algorithm = args.get("algorithm", "sha256").lower()
    if not paths_raw:
        return "Parámetro requerido: paths (string o lista de rutas)"

    # Aceptar string o lista
    if isinstance(paths_raw, list):
        path_list = paths_raw
    else:
        path_list = [p.strip() for p in str(paths_raw).split(",") if p.strip()]

    try:
        h = hashlib.new(algorithm)
    except ValueError:
        algos = ", ".join(sorted(hashlib.algorithms_available))
        return f"Algoritmo no soportado: {algorithm}. Disponibles: {algos}"

    lines: list[str] = [f"Integridad de ficheros ({algorithm.upper()}):"]
    errors = 0
    for p_raw in path_list[:200]:
        path = Path(p_raw).expanduser()
        if not path.exists():
            lines.append(f"  MISSING  {path}")
            errors += 1
            continue
        if path.is_dir():
            # Hashear recursivamente
            total = hashlib.new(algorithm)
            count = 0
            for f in sorted(path.rglob("*")):
                if not f.is_file():
                    continue
                try:
                    data = f.read_bytes()
                    total.update(f.name.encode() + data)
                    count += 1
                except (PermissionError, OSError):
                    pass
            lines.append(f"  {total.hexdigest()}  {path}/ ({count} ficheros)")
        else:
            try:
                data = path.read_bytes()
                digest = hashlib.new(algorithm, data).hexdigest()
                lines.append(f"  {digest}  {path}")
            except (PermissionError, OSError) as exc:
                lines.append(f"  ERROR    {path}: {exc}")
                errors += 1

    if errors:
        lines.append(f"\n{errors} error(s) encontrado(s)")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# SCHEMAS — 24 tools
# ══════════════════════════════════════════════════════════════════════════════

_TOOLS = [
    # ── Red / Recon ────────────────────────────────────────────────────────
    {
        "name": "nmap_scan",
        "description": "Escaneo de red con nmap. Requiere autorización del propietario del target.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Host, IP o rango CIDR"},
                "ports":  {"type": "string", "description": "Puertos: '22,80,443' o '1-1024' (opcional)"},
                "flags":  {"type": "string", "description": "Flags adicionales de nmap (ej. '-sV -O')"},
            },
            "required": ["target"],
        },
    },
    {
        "name": "port_scan",
        "description": "Escaneo de puertos TCP con Python puro (sin nmap). Rápido para listas cortas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host":    {"type": "string", "description": "Host o IP a escanear"},
                "ports":   {"type": "string", "description": "Puertos: '22,80,443' o '1-1024'"},
                "timeout": {"type": "number", "description": "Timeout en segundos por puerto (default 2)"},
            },
            "required": ["host", "ports"],
        },
    },
    {
        "name": "ssl_check",
        "description": "Inspecciona certificado SSL/TLS de un host: versión, cipher, SANs, expiración.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {"type": "string", "description": "Hostname"},
                "port": {"type": "integer", "description": "Puerto (default 443)"},
            },
            "required": ["host"],
        },
    },
    {
        "name": "whois_lookup",
        "description": "Consulta WHOIS para un dominio o IP.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Dominio o IP"},
            },
            "required": ["domain"],
        },
    },
    {
        "name": "dns_enum",
        "description": "Enumera registros DNS de un dominio (A, AAAA, MX, NS, TXT, CNAME).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain":       {"type": "string", "description": "Dominio a consultar"},
                "record_types": {"type": "string", "description": "Tipos separados por coma (default: A,AAAA,MX,NS,TXT,CNAME)"},
            },
            "required": ["domain"],
        },
    },
    # ── Web ────────────────────────────────────────────────────────────────
    {
        "name": "http_headers",
        "description": "Obtiene y analiza headers HTTP de una URL, incluyendo headers de seguridad.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url":              {"type": "string", "description": "URL a analizar"},
                "follow_redirects": {"type": "boolean", "description": "Seguir redirecciones (default true)"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "nikto_scan",
        "description": "Escaneo de vulnerabilidades web con nikto. OFENSIVO — solo en sistemas propios o con autorización.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "URL o host objetivo"},
                "flags":  {"type": "string", "description": "Flags adicionales de nikto"},
            },
            "required": ["target"],
        },
    },
    {
        "name": "gobuster_run",
        "description": "Fuerza bruta de directorios/archivos web con gobuster. OFENSIVO — solo con autorización.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target":   {"type": "string", "description": "URL base (ej. http://target.com)"},
                "wordlist": {"type": "string", "description": "Ruta a la wordlist"},
                "mode":     {"type": "string", "description": "Modo: dir, dns, vhost (default dir)"},
                "flags":    {"type": "string", "description": "Flags adicionales"},
            },
            "required": ["target", "wordlist"],
        },
    },
    {
        "name": "curl_request",
        "description": "Realiza petición HTTP con control total de método, headers y body.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url":      {"type": "string", "description": "URL destino"},
                "method":   {"type": "string", "description": "Método HTTP (default GET)"},
                "headers":  {"type": "object", "description": "Headers adicionales (objeto key-value)"},
                "data":     {"type": "string", "description": "Body de la petición"},
                "insecure": {"type": "boolean", "description": "Ignorar errores SSL (default false)"},
            },
            "required": ["url"],
        },
    },
    # ── Criptografía ──────────────────────────────────────────────────────
    {
        "name": "encode_decode",
        "description": "Codifica/decodifica datos en base64, base32, hex, URL, rot13, html, unicode_escape.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "data":      {"type": "string", "description": "Datos a procesar"},
                "operation": {"type": "string", "description": "encode o decode"},
                "encoding":  {"type": "string", "description": "Formato: base64, base32, hex, url, rot13, html, unicode_escape"},
            },
            "required": ["data", "operation"],
        },
    },
    {
        "name": "hash_crack",
        "description": "Intenta crackear un hash por diccionario (Python puro + hashcat si disponible). REQUIERE AUTORIZACIÓN.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hash_value": {"type": "string", "description": "Hash a crackear"},
                "wordlist":   {"type": "string", "description": "Ruta a la wordlist"},
                "algorithm":  {"type": "string", "description": "Algoritmo: md5, sha1, sha256, sha512 (autodetectado si vacío)"},
            },
            "required": ["hash_value", "wordlist"],
        },
    },
    {
        "name": "jwt_decode",
        "description": "Decodifica un JWT mostrando header, payload y verificando expiración (SIN verificar firma).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "token": {"type": "string", "description": "Token JWT a decodificar"},
            },
            "required": ["token"],
        },
    },
    {
        "name": "cert_inspect",
        "description": "Inspecciona un certificado SSL: conectando a host o desde fichero .pem/.crt.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host_or_file": {"type": "string", "description": "Hostname o ruta a fichero de certificado"},
                "port":         {"type": "integer", "description": "Puerto si es hostname (default 443)"},
            },
            "required": ["host_or_file"],
        },
    },
    # ── Análisis ──────────────────────────────────────────────────────────
    {
        "name": "log_analyze",
        "description": "Analiza logs en busca de patrones de seguridad (logins fallidos, sudo, escalada).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "log_file": {"type": "string", "description": "Ruta al fichero de log"},
                "pattern":  {"type": "string", "description": "Regex personalizado (opcional; si se omite, aplica patrones de seguridad)"},
                "lines":    {"type": "integer", "description": "Máximo de líneas a mostrar (default 200)"},
            },
            "required": ["log_file"],
        },
    },
    {
        "name": "secret_scan",
        "description": "Busca secrets (contraseñas, API keys, tokens) en código usando trufflehog/gitleaks o regex.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta a escanear (fichero, directorio o repositorio git)"},
                "tool": {"type": "string", "description": "Herramienta: auto, trufflehog, gitleaks (default auto)"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "cve_lookup",
        "description": "Busca CVEs en la base de datos NVD (NIST) por ID o keyword.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "ID de CVE (ej. CVE-2021-44228) o keyword (ej. 'log4j')"},
                "limit": {"type": "integer", "description": "Máximo de resultados (default 5, max 20)"},
            },
            "required": ["query"],
        },
    },
    # ── CTF helpers ───────────────────────────────────────────────────────
    {
        "name": "xor_decode",
        "description": "Aplica operación XOR a datos con una clave. Útil en CTFs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "data":     {"type": "string", "description": "Datos a XOR-ear"},
                "key":      {"type": "string", "description": "Clave (hex, ej. '0x41' o '41 42 43', o texto)"},
                "encoding": {"type": "string", "description": "Encoding de data: hex, base64, raw (default hex)"},
            },
            "required": ["data", "key"],
        },
    },
    {
        "name": "steganography_check",
        "description": "Analiza una imagen buscando datos esteganográficos ocultos (steghide, stegdetect, strings).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image_file": {"type": "string", "description": "Ruta a la imagen a analizar"},
            },
            "required": ["image_file"],
        },
    },
    {
        "name": "base_convert",
        "description": "Convierte un número entre cualquier base (2-36). Muestra también dec/hex/oct/bin.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "value":     {"type": "string", "description": "Valor a convertir"},
                "from_base": {"type": "integer", "description": "Base origen (2-36, default 10)"},
                "to_base":   {"type": "integer", "description": "Base destino (2-36, default 16)"},
            },
            "required": ["value"],
        },
    },
    {
        "name": "hex_dump",
        "description": "Muestra hexdump de un fichero o de datos hex/texto. Equivalente a xxd.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_or_data": {"type": "string", "description": "Ruta a fichero, string hex o texto"},
                "length":       {"type": "integer", "description": "Bytes a mostrar (default 256)"},
                "offset":       {"type": "integer", "description": "Offset inicial en bytes (default 0)"},
            },
            "required": ["file_or_data"],
        },
    },
    # ── Defensivo ─────────────────────────────────────────────────────────
    {
        "name": "fw_audit",
        "description": "Audita la configuración del firewall (ufw, iptables, nftables).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool": {"type": "string", "description": "Herramienta: auto, ufw, iptables, nft (default auto)"},
            },
        },
    },
    {
        "name": "ssh_key_audit",
        "description": "Audita las claves SSH: permisos, tipos débiles, passphrase, authorized_keys, sshd_config.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directorio SSH (default ~/.ssh)"},
            },
        },
    },
    {
        "name": "sudoers_review",
        "description": "Revisa /etc/sudoers y sudoers.d buscando configuraciones de riesgo (NOPASSWD, ALL).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta al fichero sudoers (default /etc/sudoers)"},
            },
        },
    },
    {
        "name": "file_integrity_check",
        "description": "Calcula hashes de ficheros o directorios para verificar integridad.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "paths":     {"type": "string", "description": "Rutas separadas por coma o lista JSON"},
                "algorithm": {"type": "string", "description": "Algoritmo: sha256, sha1, md5, sha512 (default sha256)"},
            },
            "required": ["paths"],
        },
    },
]

_TOOL_FNS = {
    "nmap_scan":           _tool_nmap_scan,
    "port_scan":           _tool_port_scan,
    "ssl_check":           _tool_ssl_check,
    "whois_lookup":        _tool_whois_lookup,
    "dns_enum":            _tool_dns_enum,
    "http_headers":        _tool_http_headers,
    "nikto_scan":          _tool_nikto_scan,
    "gobuster_run":        _tool_gobuster_run,
    "curl_request":        _tool_curl_request,
    "encode_decode":       _tool_encode_decode,
    "hash_crack":          _tool_hash_crack,
    "jwt_decode":          _tool_jwt_decode,
    "cert_inspect":        _tool_cert_inspect,
    "log_analyze":         _tool_log_analyze,
    "secret_scan":         _tool_secret_scan,
    "cve_lookup":          _tool_cve_lookup,
    "xor_decode":          _tool_xor_decode,
    "steganography_check": _tool_steganography_check,
    "base_convert":        _tool_base_convert,
    "hex_dump":            _tool_hex_dump,
    "fw_audit":            _tool_fw_audit,
    "ssh_key_audit":       _tool_ssh_key_audit,
    "sudoers_review":      _tool_sudoers_review,
    "file_integrity_check": _tool_file_integrity_check,
}

# ══════════════════════════════════════════════════════════════════════════════
# PROMPTS — 4
# ══════════════════════════════════════════════════════════════════════════════

_PROMPTS = [
    {
        "name": "pentest_report",
        "description": "Genera un informe de pentest estructurado a partir de hallazgos.",
        "arguments": [
            {"name": "target",   "description": "Sistema/aplicación evaluada", "required": True},
            {"name": "findings", "description": "Hallazgos del pentest (texto libre)", "required": True},
            {"name": "scope",    "description": "Alcance del pentest", "required": False},
        ],
    },
    {
        "name": "ctf_challenge",
        "description": "Analiza una descripción de reto CTF y sugiere técnicas y herramientas.",
        "arguments": [
            {"name": "description", "description": "Descripción del reto", "required": True},
            {"name": "category",    "description": "Categoría: web, crypto, forensics, pwn, rev, misc", "required": False},
            {"name": "hints",       "description": "Pistas disponibles", "required": False},
        ],
    },
    {
        "name": "security_audit",
        "description": "Genera un checklist de auditoría de seguridad para un sistema o aplicación.",
        "arguments": [
            {"name": "system_type", "description": "Tipo de sistema: web, linux_server, network, code_review", "required": True},
            {"name": "context",     "description": "Contexto adicional del sistema", "required": False},
        ],
    },
    {
        "name": "vulnerability_analysis",
        "description": "Analiza una vulnerabilidad o CVE y explica impacto, explotación y mitigación.",
        "arguments": [
            {"name": "vulnerability", "description": "CVE ID o descripción de la vulnerabilidad", "required": True},
            {"name": "context",       "description": "Contexto del entorno afectado", "required": False},
        ],
    },
]


def _get_prompt(name: str, args: dict) -> list[dict]:
    if name == "pentest_report":
        target   = args.get("target", "sistema evaluado")
        findings = args.get("findings", "")
        scope    = args.get("scope", "no especificado")
        text = (
            f"Genera un informe de pentest profesional para '{target}'.\n\n"
            f"Alcance: {scope}\n\n"
            f"Hallazgos:\n{findings}\n\n"
            "Estructura el informe con:\n"
            "1. Resumen ejecutivo\n"
            "2. Metodología\n"
            "3. Hallazgos por severidad (Crítico/Alto/Medio/Bajo/Informativo)\n"
            "4. Evidencias y capturas relevantes\n"
            "5. Recomendaciones de remediación priorizadas\n"
            "6. Conclusiones\n\n"
            "Usa formato Markdown con tablas para los hallazgos."
        )
    elif name == "ctf_challenge":
        desc     = args.get("description", "")
        category = args.get("category", "desconocida")
        hints    = args.get("hints", "ninguna")
        text = (
            f"Analiza este reto CTF de categoría '{category}':\n\n"
            f"Descripción: {desc}\n"
            f"Pistas disponibles: {hints}\n\n"
            "Proporciona:\n"
            "1. Análisis inicial del reto\n"
            "2. Técnicas aplicables\n"
            "3. Herramientas recomendadas (con comandos específicos)\n"
            "4. Pistas de resolución (sin spoilers completos)\n"
            "5. Recursos y referencias útiles"
        )
    elif name == "security_audit":
        stype   = args.get("system_type", "sistema")
        context = args.get("context", "")
        text = (
            f"Genera un checklist completo de auditoría de seguridad para '{stype}'.\n\n"
            f"Contexto: {context}\n\n"
            "Incluye:\n"
            "- Checklist por categorías (autenticación, autorización, red, datos, logs, etc.)\n"
            "- Comandos/queries para verificar cada punto\n"
            "- Referencias a estándares (OWASP, CIS, NIST)\n"
            "- Priorización por riesgo\n"
            "Formato: tabla Markdown con columnas [Item, Comando/Verificación, Riesgo, Estado]"
        )
    elif name == "vulnerability_analysis":
        vuln    = args.get("vulnerability", "")
        context = args.get("context", "")
        text = (
            f"Analiza la vulnerabilidad: {vuln}\n\n"
            f"Contexto del entorno: {context}\n\n"
            "Proporciona:\n"
            "1. Descripción técnica detallada\n"
            "2. Sistemas/versiones afectadas\n"
            "3. Vector de ataque y condiciones de explotación\n"
            "4. Impacto (CVSS si aplica)\n"
            "5. Ejemplo de PoC conceptual (educativo, sin código de explotación activo)\n"
            "6. Mitigaciones y parches disponibles\n"
            "7. Referencias (NVD, advisories)"
        )
    else:
        text = f"Prompt desconocido: {name}"

    return [{"role": "user", "content": {"type": "text", "text": text}}]


# ══════════════════════════════════════════════════════════════════════════════
# RESOURCES — 3
# ══════════════════════════════════════════════════════════════════════════════

_RESOURCES = [
    {
        "uri":         "security://scan_history",
        "name":        "Historial de scans",
        "description": "Scans realizados en esta sesión (nmap, ssl, whois, etc.)",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "security://tools_available",
        "name":        "Herramientas disponibles",
        "description": "Lista de herramientas de seguridad instaladas en el sistema",
        "mimeType":    "text/plain",
    },
    {
        "uri":         "security://host_info",
        "name":        "Info del host",
        "description": "Información básica de red del host local (hostname, IPs, interfaces)",
        "mimeType":    "text/plain",
    },
]

_SECURITY_TOOLS = [
    "nmap", "nikto", "gobuster", "hashcat", "whois", "dig", "nslookup",
    "openssl", "trufflehog", "gitleaks", "steghide", "stegdetect",
    "xxd", "iptables", "ufw", "nft", "ssh-keygen", "strings",
    "exiftool", "john", "hydra", "sqlmap", "burpsuite",
]


def _resource_scan_history() -> str:
    if not _scan_history:
        return "Sin scans realizados en esta sesión."
    lines = [f"Historial de scans ({len(_scan_history)} entradas):"]
    for e in _scan_history:
        lines.append(f"  {e['ts']} [{e['tool']}] {e['target']}: {e['summary']}")
    return "\n".join(lines)


def _resource_tools_available() -> str:
    lines = ["Herramientas de seguridad:"]
    present  = [t for t in _SECURITY_TOOLS if _cmd_available(t)]
    missing  = [t for t in _SECURITY_TOOLS if not _cmd_available(t)]
    lines.append(f"\nInstaladas ({len(present)}): {', '.join(present)}")
    lines.append(f"No instaladas ({len(missing)}): {', '.join(missing)}")
    return "\n".join(lines)


def _resource_host_info() -> str:
    lines = ["Host info:"]
    try:
        hostname = socket.gethostname()
        lines.append(f"  Hostname: {hostname}")
        lines.append(f"  FQDN:     {socket.getfqdn()}")
    except Exception:
        pass
    try:
        addrs = socket.getaddrinfo(socket.gethostname(), None)
        ips = list({r[4][0] for r in addrs if not r[4][0].startswith("127.")})
        lines.append(f"  IPs:      {', '.join(ips)}")
    except Exception:
        pass
    if _cmd_available("ip"):
        rc, out, _ = _run(["ip", "-br", "addr"], timeout=5)
        if rc == 0:
            lines.append(f"\nInterfaces:\n{out.strip()}")
    elif _cmd_available("ifconfig"):
        rc, out, _ = _run(["ifconfig", "-a"], timeout=5)
        if rc == 0:
            lines.append(f"\nInterfaces:\n{out[:1000]}")
    return "\n".join(lines)


_RESOURCE_FNS = {
    "security://scan_history":    _resource_scan_history,
    "security://tools_available": _resource_tools_available,
    "security://host_info":       _resource_host_info,
}


# ══════════════════════════════════════════════════════════════════════════════
# MCP dispatcher
# ══════════════════════════════════════════════════════════════════════════════

def _handle(req: dict) -> dict | None:
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params", {})

    if method == "initialize":
        return _ok(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools":     {"listChanged": False},
                "resources": {"listChanged": False},
                "prompts":   {"listChanged": False},
            },
            "serverInfo": {"name": "security-assistant", "version": "1.1.0"},
        })

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return _ok(req_id, {"tools": _TOOLS})

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        fn = _TOOL_FNS.get(tool_name)
        if not fn:
            return _err(req_id, -32601, f"Tool desconocida: {tool_name}")
        try:
            result = fn(tool_args)
        except Exception as exc:
            result = f"Error interno: {exc}"
        return _ok(req_id, {
            "content": [{"type": "text", "text": str(result)}],
            "isError": False,
        })

    if method == "resources/list":
        return _ok(req_id, {"resources": _RESOURCES})

    if method == "resources/read":
        uri = params.get("uri", "")
        fn = _RESOURCE_FNS.get(uri)
        if not fn:
            return _err(req_id, -32601, f"Resource desconocido: {uri}")
        try:
            content = fn()
        except Exception as exc:
            content = f"Error: {exc}"
        return _ok(req_id, {
            "contents": [{"uri": uri, "mimeType": "text/plain", "text": content}]
        })

    if method == "prompts/list":
        return _ok(req_id, {"prompts": _PROMPTS})

    if method == "prompts/get":
        name = params.get("name", "")
        pargs = params.get("arguments", {})
        found = next((p for p in _PROMPTS if p["name"] == name), None)
        if not found:
            return _err(req_id, -32601, f"Prompt desconocido: {name}")
        messages = _get_prompt(name, pargs)
        return _ok(req_id, {"description": found["description"], "messages": messages})

    if req_id is not None:
        return _err(req_id, -32601, f"Método desconocido: {method}")
    return None


def main() -> None:
    while True:
        req = _recv()
        if req is None:
            break
        resp = _handle(req)
        if resp is not None:
            _send(resp)


if __name__ == "__main__":
    main()
