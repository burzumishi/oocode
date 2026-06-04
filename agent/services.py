"""Factories compartidas para montar los servicios de un agente.

Centralizan la construcción de WorkspaceManager, EmbeddingClient y MemorySystem
para el agente del `config` actual, de modo que el bootstrap del TUI (oocode.py),
del WebUI (webui/sessions.py) y del cambio en caliente (/switch en ui/commands.py)
usen exactamente la misma configuración y no diverjan.

Motivación: estas tres rutas duplicaban el mismo montaje y derivaron — p.ej. /switch
llegó a crear el EmbeddingClient con `ollama_host` en vez de `effective_embed_host`,
rompiendo las embeddings con backend no-Ollama. Con una sola fuente el bug no puede
reaparecer en una de las copias.
"""
import sys as _sys
from pathlib import Path as _Path

from config import MEMORY_DIR
from workspace.manager import WorkspaceManager
from agent.embeddings import EmbeddingClient
from agent.memory import MemorySystem


# Los 8 servidores MCP bundled: (atributo del flag en config, nombre, fichero).
# Orden = orden de arranque. ÚNICA fuente de verdad — la usan el bootstrap del TUI
# (oocode.py) y el del WebUI (webui/sessions.py). Antes cada ruta duplicaba la lista
# y derivaron: el WebUI se quedó sin devops/database/http-client (devops-assistant
# está activo por defecto, así que la WebUI perdía 66 tools git/docker/fs).
_BUNDLED_MCP = (
    ("mcp_oocode_assistant_enabled",      "oocode-assistant",        "oocode_assistant.py"),
    ("mcp_system_assistant_enabled",      "system-assistant",        "system_assistant.py"),
    ("mcp_devops_assistant_enabled",      "devops-assistant",        "devops_assistant.py"),
    ("mcp_database_assistant_enabled",    "database-assistant",      "database_assistant.py"),
    ("mcp_home_office_assistant_enabled", "home-office-assistant",   "home_office_assistant.py"),
    ("mcp_security_assistant_enabled",    "security-assistant",      "security_assistant.py"),
    ("mcp_iot_assistant_enabled",         "iot-assistant",           "iot_assistant.py"),
    ("mcp_http_client_assistant_enabled", "http-client-assistant",   "http_client_assistant.py"),
)


def bundled_mcp_servers(config, existing_names=None) -> list[dict]:
    """Servidores MCP bundled activos en `config`, como dicts {name, cmd}.

    `existing_names`: nombres ya presentes (servidores de usuario en oocode.json) que
    no deben duplicarse. Solo se incluye un bundled si su flag está activo, el fichero
    existe y su nombre no está ya listado. Mantiene la paridad TUI ↔ WebUI: ambas rutas
    deben arrancar exactamente el mismo conjunto.
    """
    existing = set(existing_names or ())
    mcp_dir = _Path(__file__).resolve().parent.parent / "mcp_servers"
    out: list[dict] = []
    for flag_attr, name, fname in _BUNDLED_MCP:
        if not getattr(config, flag_attr, False) or name in existing:
            continue
        path = mcp_dir / fname
        if path.exists():
            out.append({"name": name, "cmd": [_sys.executable, str(path)]})
            existing.add(name)
    return out


def build_workspace_manager(config) -> WorkspaceManager:
    """WorkspaceManager para el agente del `config` actual.

    No inicializa el workspace: el llamador decide (el output al inicializar varía
    entre TUI/WebUI/switch). Construir-vs-inicializar quedan separados a propósito.
    """
    return WorkspaceManager(
        config.workspace,
        config.agent_name,
        config.agent_emoji,
        ollama_host=config.ollama_host,
        permissions=config.permissions,
        max_memory_lines=config.ws_max_memory_lines,
        max_daily_chars=config.ws_max_daily_chars,
    )


def build_embedding_client(config) -> EmbeddingClient:
    """EmbeddingClient apuntando al host de embeddings efectivo.

    Usa SIEMPRE `config.effective_embed_host` (protocolo Ollama), nunca `ollama_host`
    crudo: con backend OpenAI/Anthropic ese host apunta al servidor de chat.
    """
    return EmbeddingClient(
        host=config.effective_embed_host,
        model=config.embed_model,
        max_input_chars=config.embed_max_input_chars,
        disk_cache_enabled=config.embed_disk_cache_enabled,
        disk_cache_dir=config.embed_disk_cache_dir,
        disk_cache_max=config.embed_disk_cache_max,
        ram_cache_max=config.embed_ram_cache_max,
    )


def build_memory_system(config, embed_client) -> MemorySystem:
    """MemorySystem del agente actual (memoria por agente en MEMORY_DIR/<agent_id>).

    Crea el directorio de memoria del agente y desactiva las embeddings (pasa None)
    si `config.memory_embed_enabled` es False.
    """
    agent_memory_dir = MEMORY_DIR / config.agent_id
    agent_memory_dir.mkdir(parents=True, exist_ok=True)
    return MemorySystem(
        embed_client=embed_client if config.memory_embed_enabled else None,
        similarity_threshold=config.embed_similarity_threshold,
        snippet_chars=config.embed_snippet_chars,
        top_k=config.embed_top_k,
        memory_dir=agent_memory_dir,
    )
