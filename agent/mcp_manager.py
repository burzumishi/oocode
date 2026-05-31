"""Gestión de servidores MCP externos: catálogo, configuración y hot-add.

El catálogo (mcp_servers/catalog.json) es estático y se distribuye con OOCode.
No se realizan llamadas externas — todo funciona sin conexión a internet.

Flujo de uso:
  /mcp catalog                  → lista el catálogo
  /mcp install filesystem /ruta → añade a oocode.json + hot-add si pool activo
  /mcp add mi-srv npx mi-pkg    → añade servidor personalizado
  /mcp remove filesystem        → elimina de oocode.json
  /mcp enable / disable <name>  → activa/desactiva en oocode.json
  /mcp check filesystem         → verifica prerequisitos en el sistema
"""
import json
import shutil
from pathlib import Path
from typing import Any, Optional

_CATALOG_PATH = Path(__file__).parent.parent / "mcp_servers" / "catalog.json"
_CONFIG_FILE  = Path.home() / ".oocode" / "oocode.json"


# ── Catálogo ──────────────────────────────────────────────────────────────────

def load_catalog() -> list[dict]:
    """Carga el catálogo de servidores MCP desde catalog.json (bundled, sin API)."""
    if not _CATALOG_PATH.exists():
        return []
    try:
        return json.loads(_CATALOG_PATH.read_text())
    except Exception:
        return []


def find_in_catalog(id_or_name: str) -> Optional[dict]:
    """Busca entrada en el catálogo por id o name (case-insensitive)."""
    q = id_or_name.lower().strip()
    for srv in load_catalog():
        if srv.get("id", "").lower() == q:
            return srv
        if srv.get("name", "").lower() == q:
            return srv
    return None


def search_catalog(query: str) -> list[dict]:
    """Filtra el catálogo por texto libre (id, name, description, tags)."""
    q = query.lower().strip()
    if not q:
        return load_catalog()
    results = []
    for srv in load_catalog():
        haystack = " ".join([
            srv.get("id", ""), srv.get("name", ""),
            srv.get("description", ""),
            " ".join(srv.get("tags", [])),
        ]).lower()
        if q in haystack:
            results.append(srv)
    return results


# ── Prerequisitos ─────────────────────────────────────────────────────────────

def check_runtime(runtime: str) -> bool:
    """Verifica si el runtime (npx, node, uvx, python3...) está en PATH."""
    return shutil.which(runtime) is not None


def check_server_prerequisites(srv: dict) -> list[str]:
    """Devuelve lista de runtimes no encontrados en el sistema."""
    runtime = srv.get("runtime", "")
    if not runtime or runtime == "custom":
        return []
    # "python" y "python3" se tratan igual
    candidates = [runtime]
    if runtime == "python":
        candidates = ["python3", "python"]
    missing = []
    if not any(check_runtime(r) for r in candidates):
        missing.append(runtime)
    return missing


# ── Config (oocode.json) ──────────────────────────────────────────────────────

def _load_config(config_file: Path) -> dict:
    if config_file.exists():
        try:
            return json.loads(config_file.read_text())
        except Exception:
            pass
    return {}


def _save_config(cfg: dict, config_file: Path) -> None:
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))


def add_server(entry: dict,
               config_file: Optional[Path] = None) -> None:
    """Añade o actualiza un servidor en oocode.json (mcp.servers).

    Si ya existe un servidor con el mismo name, lo reemplaza.
    """
    f = config_file or _CONFIG_FILE
    cfg = _load_config(f)
    cfg.setdefault("mcp", {}).setdefault("servers", [])
    servers = [s for s in cfg["mcp"]["servers"]
               if s.get("name") != entry.get("name")]
    servers.append(entry)
    cfg["mcp"]["servers"] = servers
    _save_config(cfg, f)


def remove_server(name: str,
                  config_file: Optional[Path] = None) -> bool:
    """Elimina un servidor de oocode.json. Devuelve True si se encontró y borró."""
    f = config_file or _CONFIG_FILE
    if not f.exists():
        return False
    cfg = _load_config(f)
    before = cfg.get("mcp", {}).get("servers", [])
    after  = [s for s in before if s.get("name") != name]
    if len(after) == len(before):
        return False
    cfg.setdefault("mcp", {})["servers"] = after
    _save_config(cfg, f)
    return True


def set_server_enabled(name: str, enabled: bool,
                       config_file: Optional[Path] = None) -> bool:
    """Activa/desactiva un servidor en oocode.json. Devuelve True si se encontró."""
    f = config_file or _CONFIG_FILE
    if not f.exists():
        return False
    cfg = _load_config(f)
    servers = cfg.get("mcp", {}).get("servers", [])
    found = False
    for s in servers:
        if s.get("name") == name:
            s["enabled"] = enabled
            found = True
    if found:
        cfg.setdefault("mcp", {})["servers"] = servers
        _save_config(cfg, f)
    return found


# ── Construcción de cmd ───────────────────────────────────────────────────────

def build_cmd_from_catalog(srv: dict, extra_args: list[str]) -> list[str]:
    """Construye la lista cmd a partir de una entrada del catálogo + args adicionales."""
    base = list(srv.get("cmd", []))
    return base + extra_args


def build_entry_from_catalog(srv: dict, extra_args: list[str],
                             custom_name: Optional[str] = None) -> dict:
    """Construye el dict de servidor para oocode.json desde una entrada del catálogo."""
    name = custom_name or srv.get("id", srv.get("name", "mcp-server"))
    cmd  = build_cmd_from_catalog(srv, extra_args)
    return {
        "name":        name,
        "cmd":         cmd,
        "enabled":     True,
        "description": srv.get("description", ""),
    }


# ── Hot-add (sin reiniciar OOCode) ───────────────────────────────────────────

def hot_add_to_pool(entry: dict, pool: Any, registry: Any) -> tuple[bool, str]:
    """Arranca el servidor en el McpPool activo y registra sus tools inmediatamente.

    Devuelve (ok, mensaje).
    No levanta excepciones — errores se devuelven en el mensaje.
    """
    from agent.mcp_client import mcp_tool_to_oocode
    name = entry.get("name", "")
    cmd  = entry.get("cmd", [])
    env  = entry.get("env")
    cwd  = entry.get("cwd")
    desc = entry.get("description", "")

    if not cmd:
        return False, "cmd vacío — imposible arrancar el servidor."

    try:
        client = pool.start_server(name=name, cmd=cmd, env=env, cwd=cwd,
                                   description=desc)
    except Exception as exc:
        return False, f"Error arrancando servidor: {exc}"

    if client is None or not client.is_alive:
        err = client.error if client else "proceso no arrancó"
        return False, f"Servidor no disponible: {err}"

    # Registrar tools, resources y prompts en el registry activo
    existing = frozenset(registry._tools.keys())
    new_tools = 0
    for t in client.tools:
        tname, tfn, tschema = mcp_tool_to_oocode(client, t, existing_names=existing)
        if not registry.has(tname):
            registry.register(tname, tfn, tschema)
            new_tools += 1

    # Resources
    try:
        resources = client.list_resources()
        for res_name, res_fn, res_schema in _resource_tools_for(client, name):
            if not registry.has(res_name):
                registry.register(res_name, res_fn, res_schema)
    except Exception:
        pass

    # Prompts
    try:
        for prm_name, prm_fn, prm_schema in _prompt_tools_for(client, name):
            if not registry.has(prm_name):
                registry.register(prm_name, prm_fn, prm_schema)
    except Exception:
        pass

    return True, f"{len(client.tools)} tools disponibles ({new_tools} nuevas registradas)."


def _resource_tools_for(client: Any, name: str) -> list[tuple]:
    """Genera las tools list/read de resources para un cliente concreto."""
    from agent.mcp_client import McpPool
    pool = McpPool.__new__(McpPool)
    pool._clients = {name: client}
    pool._timeout = client._timeout
    return pool.resource_oocode_tools()


def _prompt_tools_for(client: Any, name: str) -> list[tuple]:
    """Genera las tools list/get de prompts para un cliente concreto."""
    from agent.mcp_client import McpPool
    pool = McpPool.__new__(McpPool)
    pool._clients = {name: client}
    pool._timeout = client._timeout
    return pool.prompt_oocode_tools()
