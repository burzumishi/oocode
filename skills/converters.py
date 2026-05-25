"""Skill: converters
Herramientas de conversión y codificación para desarrolladores.
Base64, URL-encode, hashes (md5/sha1/sha256), conversión de bases numéricas,
formateo de JSON/XML y escape de strings. Todo con stdlib Python, sin dependencias.

Activa con: /skills enable converters
"""
import base64
import hashlib
import json
import urllib.parse

# ── Herramientas ──────────────────────────────────────────────────────────────

def encode_base64(text: str, url_safe: bool = False) -> str:
    """Codifica texto en Base64.

    Args:
        text: Texto a codificar (UTF-8).
        url_safe: Si True, usa variante URL-safe (- y _ en lugar de + y /).
    """
    raw = text.encode("utf-8")
    if url_safe:
        return base64.urlsafe_b64encode(raw).decode("ascii")
    return base64.b64encode(raw).decode("ascii")


def decode_base64(encoded: str) -> str:
    """Decodifica una cadena Base64 a texto.

    Args:
        encoded: Cadena Base64 (normal o URL-safe).
    """
    try:
        # intentar URL-safe primero, luego estándar
        try:
            raw = base64.urlsafe_b64decode(encoded + "==")
        except Exception:
            raw = base64.b64decode(encoded + "==")
        return raw.decode("utf-8")
    except Exception as e:
        try:
            return f"(binario) hex: {raw.hex()}"
        except Exception:
            return f"Error decodificando: {e}"


def url_encode(text: str, plus_spaces: bool = False) -> str:
    """Codifica texto para usar en URLs (percent-encoding).

    Args:
        text: Texto a codificar.
        plus_spaces: Si True, codifica espacios como '+' (application/x-www-form-urlencoded).
    """
    if plus_spaces:
        return urllib.parse.quote_plus(text)
    return urllib.parse.quote(text, safe="")


def url_decode(encoded: str) -> str:
    """Decodifica una cadena URL-encoded.

    Args:
        encoded: Cadena con percent-encoding (%XX) o '+' para espacios.
    """
    try:
        # intentar ambos formatos
        decoded = urllib.parse.unquote_plus(encoded)
        return decoded
    except Exception as e:
        return f"Error decodificando: {e}"


def compute_hash(text: str, algorithm: str = "sha256") -> str:
    """Calcula el hash de un texto.

    Args:
        text: Texto a hashear (se codifica como UTF-8).
        algorithm: Algoritmo hash: md5, sha1, sha256, sha512, sha3_256. Defecto: sha256.
    """
    algo = algorithm.lower().replace("-", "_")
    supported = {"md5", "sha1", "sha256", "sha512", "sha3_256", "sha3_512", "blake2b", "blake2s"}
    if algo not in supported:
        return f"Algoritmo '{algorithm}' no soportado. Usa: {', '.join(sorted(supported))}"
    try:
        h = hashlib.new(algo, text.encode("utf-8"))
        return f"{algo}: {h.hexdigest()}"
    except Exception as e:
        return f"Error: {e}"


def to_base(number: str, from_base: int = 10, to_base_n: int = 16) -> str:
    """Convierte un número entre bases numéricas (2, 8, 10, 16).

    Args:
        number: Número a convertir (como string, ej: "255", "0xff", "0b11111111").
        from_base: Base de origen (2, 8, 10 o 16). Defecto: 10.
        to_base_n: Base de destino (2, 8, 10 o 16). Defecto: 16.
    """
    try:
        # Detectar prefijos automáticamente
        n = number.strip().lower()
        if n.startswith("0x"):
            value = int(n, 16)
        elif n.startswith("0b"):
            value = int(n, 2)
        elif n.startswith("0o"):
            value = int(n, 8)
        else:
            value = int(n, from_base)

        converters = {
            2:  lambda v: f"0b{v:b}",
            8:  lambda v: f"0o{v:o}",
            10: lambda v: str(v),
            16: lambda v: f"0x{v:x}",
        }
        if to_base_n not in converters:
            return f"Base destino '{to_base_n}' no soportada. Usa: 2, 8, 10, 16"

        result = converters[to_base_n](value)
        return (
            f"  decimal : {value}\n"
            f"  binario : 0b{value:b}\n"
            f"  octal   : 0o{value:o}\n"
            f"  hex     : 0x{value:x}\n"
            f"  ─────────────────\n"
            f"  base {to_base_n:<4}  : {result}"
        )
    except Exception as e:
        return f"Error convirtiendo '{number}': {e}"


def format_json(json_text: str, indent: int = 2, sort_keys: bool = False) -> str:
    """Formatea y valida JSON con indentación legible.

    Args:
        json_text: JSON en formato compacto o mal indentado.
        indent: Número de espacios de indentación (defecto: 2).
        sort_keys: Si True, ordena las claves alfabéticamente.
    """
    try:
        obj = json.loads(json_text)
        return json.dumps(obj, indent=indent, ensure_ascii=False, sort_keys=sort_keys)
    except json.JSONDecodeError as e:
        return f"JSON inválido: {e}"


def escape_string(text: str, mode: str = "json") -> str:
    """Escapa caracteres especiales en un string.

    Args:
        text: Texto a escapar.
        mode: Modo de escape: json, html, sql, regex, shell. Defecto: json.
    """
    m = mode.lower()
    if m == "json":
        return json.dumps(text)
    elif m == "html":
        return (text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&#39;"))
    elif m == "sql":
        return text.replace("'", "''")
    elif m == "regex":
        import re
        return re.escape(text)
    elif m == "shell":
        return "'" + text.replace("'", "'\\''") + "'"
    else:
        return f"Modo '{mode}' no soportado. Usa: json, html, sql, regex, shell"


def hex_encode(text: str) -> str:
    """Convierte texto a su representación hexadecimal.

    Args:
        text: Texto a convertir (UTF-8).
    """
    raw = text.encode("utf-8")
    hex_str = raw.hex()
    spaced  = " ".join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
    return f"hex (sin espacios): {hex_str}\nhex (con espacios): {spaced}"


def hex_decode(hex_text: str) -> str:
    """Decodifica una cadena hexadecimal a texto.

    Args:
        hex_text: Cadena hex (con o sin espacios, con o sin prefijo 0x).
    """
    clean = hex_text.replace(" ", "").replace("0x", "").replace(":", "")
    try:
        raw = bytes.fromhex(clean)
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return f"(no es UTF-8 válido) bytes: {raw!r}"
    except ValueError as e:
        return f"Hex inválido: {e}"


# ── Registro de herramientas ──────────────────────────────────────────────────

TOOLS = [
    (
        "encode_base64",
        encode_base64,
        {
            "name": "encode_base64",
            "description": "Codifica texto en Base64 (útil para JWT, datos en URLs, configuraciones).",
            "parameters": {
                "type": "object",
                "properties": {
                    "text":      {"type": "string", "description": "Texto a codificar"},
                    "url_safe":  {"type": "boolean", "description": "Usar variante URL-safe (defecto: false)"},
                },
                "required": ["text"],
            },
        },
    ),
    (
        "decode_base64",
        decode_base64,
        {
            "name": "decode_base64",
            "description": "Decodifica una cadena Base64 a texto legible.",
            "parameters": {
                "type": "object",
                "properties": {
                    "encoded": {"type": "string", "description": "Cadena Base64 a decodificar"},
                },
                "required": ["encoded"],
            },
        },
    ),
    (
        "url_encode",
        url_encode,
        {
            "name": "url_encode",
            "description": "Codifica texto para usar en URLs (percent-encoding). Útil para parámetros de query string.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text":        {"type": "string", "description": "Texto a codificar"},
                    "plus_spaces": {"type": "boolean", "description": "Codificar espacios como '+' (form encoding)"},
                },
                "required": ["text"],
            },
        },
    ),
    (
        "url_decode",
        url_decode,
        {
            "name": "url_decode",
            "description": "Decodifica una cadena URL-encoded (%XX o +).",
            "parameters": {
                "type": "object",
                "properties": {
                    "encoded": {"type": "string", "description": "Cadena URL-encoded a decodificar"},
                },
                "required": ["encoded"],
            },
        },
    ),
    (
        "compute_hash",
        compute_hash,
        {
            "name": "compute_hash",
            "description": "Calcula el hash de un texto (md5, sha1, sha256, sha512, sha3_256). Útil para verificar integridad o generar identificadores.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text":      {"type": "string", "description": "Texto a hashear"},
                    "algorithm": {"type": "string", "description": "Algoritmo: md5, sha1, sha256 (defecto), sha512, sha3_256"},
                },
                "required": ["text"],
            },
        },
    ),
    (
        "to_base",
        to_base,
        {
            "name": "to_base",
            "description": "Convierte un número entre bases (binario, octal, decimal, hexadecimal). Muestra todas las representaciones a la vez.",
            "parameters": {
                "type": "object",
                "properties": {
                    "number":    {"type": "string", "description": "Número a convertir (ej: '255', '0xff', '0b11111111')"},
                    "from_base": {"type": "integer", "description": "Base de origen (2/8/10/16, defecto: 10)"},
                    "to_base_n": {"type": "integer", "description": "Base de destino (2/8/10/16, defecto: 16)"},
                },
                "required": ["number"],
            },
        },
    ),
    (
        "format_json",
        format_json,
        {
            "name": "format_json",
            "description": "Formatea y valida JSON con indentación legible. También detecta errores de sintaxis JSON.",
            "parameters": {
                "type": "object",
                "properties": {
                    "json_text": {"type": "string", "description": "JSON a formatear"},
                    "indent":    {"type": "integer", "description": "Espacios de indentación (defecto: 2)"},
                    "sort_keys": {"type": "boolean", "description": "Ordenar claves alfabéticamente"},
                },
                "required": ["json_text"],
            },
        },
    ),
    (
        "escape_string",
        escape_string,
        {
            "name": "escape_string",
            "description": "Escapa caracteres especiales para JSON, HTML, SQL, regex o shell. Útil para generar código seguro.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Texto a escapar"},
                    "mode": {"type": "string", "description": "Modo: json (defecto), html, sql, regex, shell"},
                },
                "required": ["text"],
            },
        },
    ),
    (
        "hex_encode",
        hex_encode,
        {
            "name": "hex_encode",
            "description": "Convierte texto a representación hexadecimal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Texto a convertir a hex"},
                },
                "required": ["text"],
            },
        },
    ),
    (
        "hex_decode",
        hex_decode,
        {
            "name": "hex_decode",
            "description": "Decodifica una cadena hexadecimal a texto UTF-8.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hex_text": {"type": "string", "description": "Cadena hex (con o sin espacios)"},
                },
                "required": ["hex_text"],
            },
        },
    ),
]
