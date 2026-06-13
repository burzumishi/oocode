#!/usr/bin/env python3
"""CMDB Assistant MCP Server — inventario de activos IT para OOCode.

Protocolo: MCP 2024-11-05 sobre stdio (JSON-RPC 2.0 newline-delimited JSON).

Gestión de CMDB / registro de activos en CSV/XLSX/JSON: búsqueda, actualización
y alta de activos. La CMDB se autodetecta en el cwd (cmdb.csv, inventario.csv,
servers.csv...) o en ~/Documents/.

Configuración: ~/.oocode/cmdb.json  (fallback legacy: ~/.oocode/home_office.json)

Dividido desde home_office_assistant.py (v0.4.4): documentos O365 →
office_assistant.py; email/calendario/notas → mail_assistant.py.
"""
import csv
import datetime
import json
import sys
from pathlib import Path
from typing import Any, Optional


# ── Configuración ────────────────────────────────────────────────────────────

# Config opcional (con fallback al legacy ~/.oocode/home_office.json). La CMDB se
# autodetecta en el cwd / ~/Documents; este config solo aporta overrides futuros.
_CONFIG_PATH        = Path.home() / ".oocode" / "cmdb.json"
_LEGACY_CONFIG_PATH = Path.home() / ".oocode" / "home_office.json"


def _load_config() -> dict:
    src = _CONFIG_PATH if _CONFIG_PATH.exists() else _LEGACY_CONFIG_PATH
    if src.exists():
        try:
            return json.loads(src.read_text())
        except Exception:
            pass
    return {}



# ── Protocolo MCP ──────────────────────────────────────────────────────────────

def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _recv() -> Optional[dict]:
    while True:
        line = sys.stdin.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue


def _ok(req_id: Any, result: dict) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "result": result})


def _err(req_id: Any, code: int, message: str) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})




# ── Helpers y tools ────────────────────────────────────────────────────────────

def _cmdb_path_discover(cfg: dict, path_arg: str) -> Optional[Path]:
    """Find CMDB file: explicit arg > project cwd > ~/Documents/."""
    if path_arg:
        p = Path(path_arg).expanduser()
        return p if p.exists() else None
    cwd = Path.cwd()
    candidates = (
        [cwd / n for n in ("cmdb.csv", "cmdb.xlsx", "cmdb.json",
                           "inventario.csv", "inventario.xlsx",
                           "servers.csv", "servers.xlsx")]
        + [Path.home() / "Documents" / n for n in ("cmdb.csv", "inventario.csv")]
    )
    return next((p for p in candidates if p.exists()), None)


def _cmdb_rows_csv(path: Path, query: str, field: str, limit: int) -> str:
    try:
        q = query.lower() if query != "*" else None
        with path.open(newline="", errors="replace") as f:
            reader = csv.DictReader(f)
            results = []
            for row in reader:
                if q is None or (field and q in str(row.get(field, "")).lower()) \
                   or (not field and any(q in str(v).lower() for v in row.values())):
                    results.append(dict(row))
                if len(results) >= limit:
                    break
        if not results:
            return f"Sin resultados para '{query}' en {path.name}"
        lines = [f"🖥 CMDB {path.name} — {len(results)} entrada(s):\n"]
        for row in results:
            lines.append("  " + "  |  ".join(f"{k}: {v}" for k, v in row.items() if v))
        return "\n".join(lines)
    except Exception as exc:
        return f"Error leyendo CMDB CSV: {exc}"


def _cmdb_rows_xlsx(path: Path, query: str, field: str, limit: int) -> str:
    try:
        import openpyxl
        wb  = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        ws  = wb.active
        all_rows = list(ws.iter_rows(values_only=True))
        if not all_rows:
            return f"CMDB vacío: {path.name}"
        headers = [str(c) if c is not None else "" for c in all_rows[0]]
        q = query.lower() if query != "*" else None
        field_idx: Optional[int] = None
        if field:
            try:
                field_idx = headers.index(field)
            except ValueError:
                pass
        results = []
        for row in all_rows[1:]:
            cells = [str(c) if c is not None else "" for c in row]
            if q is None or (field_idx is not None and q in cells[field_idx].lower()) \
               or (field_idx is None and any(q in c.lower() for c in cells)):
                results.append(dict(zip(headers, cells)))
            if len(results) >= limit:
                break
        if not results:
            return f"Sin resultados para '{query}' en {path.name}"
        lines = [f"🖥 CMDB {path.name} — {len(results)} entrada(s):\n"]
        for row in results:
            lines.append("  " + "  |  ".join(f"{k}: {v}" for k, v in row.items() if v))
        return "\n".join(lines)
    except ImportError:
        return "openpyxl requerido para CMDB .xlsx: pip install openpyxl"
    except Exception as exc:
        return f"Error leyendo CMDB xlsx: {exc}"


def _tool_cmdb_search(args: dict) -> str:
    """Search the CMDB (CSV/XLSX/JSON) for servers, services or assets by any field value."""
    query = args.get("query", "")
    if not query:
        return "Parámetro requerido: query (texto a buscar, o '*' para listar todo)"
    cfg   = _load_config()
    path  = _cmdb_path_discover(cfg, args.get("cmdb_path", "") or args.get("path", ""))
    if path is None:
        cwd = Path.cwd()
        return (
            "CMDB no encontrado. Crea uno de estos ficheros:\n"
            f"  {cwd}/cmdb.csv\n  {cwd}/inventario.csv\n"
            "  ~/Documents/cmdb.csv\n"
            "Usa 'project_init_office' para crear la estructura del proyecto."
        )
    field = args.get("field", "")
    limit = int(args.get("limit", 20))
    if path.suffix == ".csv":
        return _cmdb_rows_csv(path, query, field, limit)
    if path.suffix == ".xlsx":
        return _cmdb_rows_xlsx(path, query, field, limit)
    if path.suffix == ".json":
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                data = list(data.values())
            q = query.lower() if query != "*" else None
            results = [
                item for item in data
                if isinstance(item, dict) and (q is None or any(q in str(v).lower() for v in item.values()))
            ][:limit]
            if not results:
                return f"Sin resultados para '{query}'"
            lines = [f"🖥 CMDB {path.name} — {len(results)} entrada(s):\n"]
            for item in results:
                lines.append("  " + "  |  ".join(f"{k}: {v}" for k, v in item.items() if v))
            return "\n".join(lines)
        except Exception as exc:
            return f"Error leyendo CMDB JSON: {exc}"
    return f"Formato CMDB no soportado: {path.suffix}"


def _tool_cmdb_update(args: dict) -> str:
    """Update a CMDB entry (CSV only) by key field: finds row where key_field=key_value, applies updates dict."""
    key_field = args.get("key_field", "")
    key_value = args.get("key_value", "")
    updates   = args.get("updates", {})
    if not key_field or not key_value:
        return "Parámetros requeridos: key_field (p.ej. 'hostname'), key_value (p.ej. 'web-01')"
    if not updates or not isinstance(updates, dict):
        return "Parámetro requerido: updates (objeto {campo: nuevo_valor})"
    cfg  = _load_config()
    path = _cmdb_path_discover(cfg, args.get("cmdb_path", "") or args.get("path", ""))
    if path is None:
        return "CMDB no encontrado. Especifica 'cmdb_path' o crea cmdb.csv en el directorio de trabajo."
    if path.suffix != ".csv":
        return "cmdb_update solo soporta .csv. Para .xlsx usa xlsx_fill_range."
    try:
        rows: list[dict] = []
        headers: list[str] = []
        updated = 0
        with path.open(newline="", errors="replace") as f:
            reader = csv.DictReader(f)
            headers = list(reader.fieldnames or [])
            for row in reader:
                if str(row.get(key_field, "")).strip() == str(key_value).strip():
                    row.update(updates)
                    updated += 1
                rows.append(dict(row))
        if updated == 0:
            return f"No se encontró {key_field}={key_value!r} en {path.name}"
        for k in updates:
            if k not in headers:
                headers.append(k)
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        return (
            f"✅ CMDB actualizado: {path.name}\n"
            f"   Clave: {key_field}={key_value!r}\n"
            f"   Cambios: {', '.join(f'{k}={v!r}' for k, v in updates.items())}\n"
            f"   Entradas actualizadas: {updated}"
        )
    except Exception as exc:
        return f"Error actualizando CMDB: {exc}"


def _tool_asset_register_add(args: dict) -> str:
    """Add a new asset entry to the project asset register (CSV)."""
    asset = args.get("asset", {})
    if not asset or not isinstance(asset, dict):
        return 'Parámetro requerido: asset (objeto JSON con datos del activo, p.ej. {"hostname": "srv-01", "ip": "10.0.0.1"})'
    if "fecha_registro" not in asset:
        asset = {**asset, "fecha_registro": datetime.date.today().isoformat()}
    cwd = Path.cwd()
    path_arg = args.get("register_path", "") or args.get("path", "")
    if path_arg:
        ar_path = Path(path_arg).expanduser()
    else:
        candidates = [
            cwd / "asset_register.csv",
            cwd / "activos.csv",
            Path.home() / "Documents" / "asset_register.csv",
        ]
        ar_path = next((p for p in candidates if p.exists()), cwd / "asset_register.csv")
    try:
        existing_headers: list[str] = []
        existing_rows: list[dict]   = []
        if ar_path.exists():
            with ar_path.open(newline="", errors="replace") as f:
                reader = csv.DictReader(f)
                existing_headers = list(reader.fieldnames or [])
                existing_rows    = list(reader)
        all_headers = list(existing_headers)
        for k in asset:
            if k not in all_headers:
                all_headers.append(k)
        existing_rows.append(asset)
        with ar_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=all_headers, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(existing_rows)
        return (
            f"✅ Activo añadido al registro: {ar_path.name}\n"
            f"   Registro #{len(existing_rows)}\n"
            + "\n".join(f"   {k}: {v}" for k, v in asset.items())
        )
    except Exception as exc:
        return f"Error añadiendo activo: {exc}"


# ── Template and IT report tools ─────────────────────────────────────────────


# ── Tools registry ──────────────────────────────────────────────────────────────

_TOOLS = [{'name': 'cmdb_search',
  'description': 'Busca en la base de datos de gestión de configuración (CMDB) en formato '
                 'CSV/XLSX/JSON. Soporta búsqueda por texto libre o por campo específico.',
  'inputSchema': {'type': 'object',
                  'properties': {'query': {'type': 'string',
                                           'description': 'Texto a buscar (usa * para listar '
                                                          'todo)'},
                                 'field': {'type': 'string',
                                           'description': 'Columna donde buscar (opcional; sin '
                                                          'ella busca en todas)'},
                                 'cmdb_path': {'type': 'string',
                                               'description': 'Ruta al fichero CMDB (opcional; '
                                                              'auto-detectado en cwd y '
                                                              '~/Documents/)'},
                                 'limit': {'type': 'integer',
                                           'description': 'Máximo de resultados. Default: 20'}},
                  'required': ['query']}},
 {'name': 'cmdb_update',
  'description': 'Actualiza un registro en la CMDB CSV identificado por un campo clave.',
  'inputSchema': {'type': 'object',
                  'properties': {'key_field': {'type': 'string',
                                               'description': 'Nombre de la columna clave (p.ej. '
                                                              "'hostname' o 'asset_id')"},
                                 'key_value': {'type': 'string',
                                               'description': 'Valor del campo clave del registro '
                                                              'a actualizar'},
                                 'updates': {'type': 'object',
                                             'description': 'Dict con {columna: nuevo_valor} a '
                                                            'actualizar'},
                                 'cmdb_path': {'type': 'string',
                                               'description': 'Ruta al fichero CMDB CSV (opcional; '
                                                              'auto-detectado)'}},
                  'required': ['key_field', 'key_value', 'updates']}},
 {'name': 'asset_register_add',
  'description': 'Añade un nuevo activo al registro de activos CSV. Si el fichero no existe lo '
                 'crea con las cabeceras apropiadas.',
  'inputSchema': {'type': 'object',
                  'properties': {'asset': {'type': 'object',
                                           'description': 'Dict con los campos del activo: '
                                                          '{hostname, ip, type, os, location, '
                                                          'owner, status, ...}'},
                                 'register_path': {'type': 'string',
                                                   'description': 'Ruta al fichero CSV del '
                                                                  'registro (opcional; por '
                                                                  'defecto: asset_register.csv en '
                                                                  'cwd)'}},
                  'required': ['asset']}}]


_TOOL_FNS: dict[str, Any] = {
    'cmdb_search'        : _tool_cmdb_search,
    'cmdb_update'        : _tool_cmdb_update,
    'asset_register_add' : _tool_asset_register_add,
}



# ── Prompts ─────────────────────────────────────────────────────────────────────

_PROMPTS: dict[str, dict] = {}


def _get_prompt(name: str, args: dict) -> list[dict]:
    return [{"role": "user", "content": {"type": "text", "text": f"Prompt {name} no disponible."}}]


# ── Resources ───────────────────────────────────────────────────────────────────

def _resource_server_inventory() -> str:
    return _tool_cmdb_search({"query": "*", "limit": 50})


_RESOURCES = [{'uri': 'cmdb://server_inventory',
  'name': 'Inventario de servidores',
  'description': 'Listado completo de activos de la CMDB del proyecto (auto-detectada en cwd y '
                 '~/Documents/)',
  'mimeType': 'text/plain'}]


_RESOURCE_FNS = {
    'cmdb://server_inventory' : _resource_server_inventory,
}



# ── Bucle principal ─────────────────────────────────────────────────────────────

def _handle(req: dict) -> None:
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params", {})

    if method == "initialize":
        _ok(req_id, {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "cmdb-assistant", "version": "1.0.0"},
            "capabilities": {
                "tools":     {"listChanged": False},
                "resources": {"listChanged": False},
                "prompts":   {"listChanged": False},
            },
        })

    elif method == "notifications/initialized":
        pass

    elif method == "tools/list":
        _ok(req_id, {"tools": _TOOLS})

    elif method == "tools/call":
        name      = params.get("name", "")
        arguments = params.get("arguments", {})
        fn        = _TOOL_FNS.get(name)
        if fn is None:
            _err(req_id, -32601, f"Tool desconocida: {name}")
            return
        try:
            result = fn(arguments)
            _ok(req_id, {"content": [{"type": "text", "text": result}], "isError": False})
        except Exception as exc:
            _ok(req_id, {"content": [{"type": "text", "text": f"Error: {exc}"}], "isError": True})

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
            _err(req_id, -32603, f"Error leyendo recurso: {exc}")

    elif method == "prompts/list":
        prompts = [
            {"name": k, "description": v["description"], "arguments": v["arguments"]}
            for k, v in _PROMPTS.items()
        ]
        _ok(req_id, {"prompts": prompts})

    elif method == "prompts/get":
        name      = params.get("name", "")
        arguments = params.get("arguments", {})
        if name not in _PROMPTS:
            _err(req_id, -32601, f"Prompt desconocido: {name}")
            return
        messages = _get_prompt(name, arguments)
        _ok(req_id, {"description": _PROMPTS[name]["description"], "messages": messages})

    elif req_id is not None:
        _err(req_id, -32601, f"Método desconocido: {method}")


def main() -> None:
    sys.stderr.write("[cmdb-assistant] MCP server v1.0.0 iniciado (3 tools, 0 prompts, 1 resources)\n")
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
            sys.stderr.write(f"[cmdb-assistant] Error: {exc}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()

