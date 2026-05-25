"""Bucle principal del agente: streaming, tool calls, sesiones, runtime, embeddings."""
import json
import os
import re
import random
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional
from datetime import date
import ollama
from rich.markdown import Markdown
from rich.padding import Padding
from rich.text import Text
from rich.live import Live

from ui.console import console
from agent.context import ConversationContext
import agent.logger as log
import tools.progress as _tool_progress
from agent.chatlog import ChatLogger
from agent.memory import MemorySystem
from agent.session import SessionManager
from agent.runtime import RuntimeSettings, COLOR_PRESETS
from tools.registry import ToolRegistry
from tools.permissions import PermissionManager
from workspace.manager import WorkspaceManager
from config import DEFAULT_CONFIG as _DEFAULT_CONFIG

_SPINNER_FRAMES    = ["○", "◌", "◎", "◉", "●", "◉", "◎", "◌"]
_POLL_INTERVAL     = 0.2    # segundos entre ticks del spinner (5 fps)

# Animación del header de tool en modo REPL: ciclo verde→amarillo (120 ms/frame)
_HEADER_ANIM_CODES = ["\033[32m", "\033[92m", "\033[33m", "\033[93m"]
_ANSI_BOLD  = "\033[1m"
_ANSI_RESET = "\033[0m"
_TIMEOUT_SENTINEL  = "__oocode_timeout__"  # señal de timeout de _stream_response
_FALLBACK_MIN_CHARS = 50                   # chars mínimos para considerar respuesta iniciada

_THINKING_WORDS = [
    # Españolas reales
    "Cavilando", "Cogitando", "Ruminando", "Elucubrando",
    "Maquinando", "Ponderando", "Discurriendo", "Deliberando",
    # Inventadas tech
    "Neuroneando", "Sinaptizando", "Tokenizando", "Vectorizando",
    "Inferenciando", "Transformeando", "Embedizando", "Prompteando",
    "Tensorando", "Gradientando", "Sampliando", "Decodificando",
    "Atteneando", "Softmaxeando", "Backproneando", "Halucineando",
]

# Palabras de "pensamiento" específicas para modo multi-tarea
# Se usan cuando hay un plan activo y el agente está ejecutando tareas
_MULTITASK_WORDS = [
    "Planificando", "Organizando", "Orquestando", "Coordinando",
    "Secuenciando", "Estructurando", "Implementando", "Ejecutando",
]

# Frases naturales para el indicador pre-vuelo de tareas múltiples
# El placeholder {n} se reemplaza por el número de tareas detectadas.
_TASK_PREFLIGHT_PHRASES = [
    "Voy a analizar las {n} tareas y preparar un plan de acción",
    "Detecté {n} tareas — organizando el plan antes de ejecutar",
    "Perfecto, {n} tareas en cola — elaborando estrategia",
    "Entendido: {n} objetivos — trazando el plan de ataque",
    "{n} tareas identificadas — preparando hoja de ruta",
    "Analizando las {n} tareas para estructurar el mejor plan",
    "Recibidas {n} tareas — diseñando el plan de ejecución",
    "Procesando {n} objetivos — organizando el trabajo",
]

# Colores para el ⊡ pulsante del indicador de tareas múltiples
_TASK_ICON_COLORS = ["bold cyan", "bold magenta", "bold yellow", "bold blue", "bold green"]

_DONE_WORDS = [
    # Españolas reales
    "Cavilado", "Razonado", "Procesado", "Completado",
    # Inventadas tech
    "Cogitado", "Inferido", "Generado", "Decodificado",
    "Tokenizado", "Embedizado", "Neuroneado", "Transformado",
    "Vectorizado", "Sinaptizado", "Gradientado", "Sampliado",
    "Prompteado", "Atteneado", "Maquinado",
]

# Frases rotativas que aparecen en el spinner cuando el modelo lleva mucho tiempo
_NEAR_FINISH_PHRASES = [
    "casi sinaptizado…",
    "estamos sinaptizando…",
    "sinaptizando más…",
    "casi terminado…",
    "un momento más…",
    "inferenciando a fondo…",
    "tokenizando profundo…",
    "embedizando más…",
    "vectorizando…",
    "neuroneando duro…",
    "tokeninanzo más…",
    "casi decodificado…",
    "seguimos infiriendo…"
]


def _fmt_elapsed(secs: float) -> str:
    """Formatea segundos como '28s' o '1m:32s'."""
    if secs >= 60:
        m = int(secs // 60)
        s = int(secs % 60)
        return f"{m}m:{s:02d}s"
    return f"{int(secs)}s"


def _fmt_tokens(n: int) -> str:
    """Formatea un conteo de tokens con sufijo K/M para legibilidad."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n // 1_000}K"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _rag_display(rag) -> str:
    """Genera la parte RAG del spinner: 'N rag' o 'N/M rag' si topK cortó resultados."""
    if rag is None:
        return ""
    hits      = getattr(rag, "last_hits", 0)
    available = getattr(rag, "last_available", 0)
    if hits <= 0:
        return ""
    if available > hits:
        # topK cortó más candidatos — mostrar cuántos había disponibles
        return f"  ·  ◈ {hits}/{available} rag"
    return f"  ·  ◈ {hits} rag"


def _is_complex_query(msg: str, min_chars: int) -> bool:
    """True si el mensaje sugiere una query compleja que se beneficia de más RAG.

    Criterios (OR):
    - Mensaje suficientemente largo (multi-paso, multi-fichero).
    - Menciona patrones de autoedición de OOCode (hooks, tools, loop, etc.).
    """
    if len(msg.strip()) >= min_chars:
        return True
    _OOCODE_KWS = (
        "hook", "tool", "loop", "agent", "mcp", "plugin",
        "registry", "config", "builtin", "oocode", "workspace_rag",
        "context_snippet", "permission", "slash", "repl",
    )
    lower = msg.lower()
    return sum(1 for kw in _OOCODE_KWS if kw in lower) >= 2


# Alias de nombres de herramientas: algunos modelos (qwen, deepseek, llama…)
# usan nombres distintos a los que registra OOCode, por sus datos de entrenamiento.
# Se normalizan aquí para evitar "herramienta no encontrada".
_TOOL_ALIASES: dict[str, str] = {
    "execute_bash":    "bash",
    "run_bash":        "bash",
    "run_code":        "bash",
    "execute_code":    "bash",
    "shell":           "bash",
    "terminal":        "bash",
    "execute_command": "bash",
    "read_file":       "read_file",   # igual, pero lo normalizamos por si acaso
    "write_file":      "write_file",
    "create_file":     "write_file",
    "save_file":       "write_file",
    "edit_file":       "edit_file",
    "modify_file":     "edit_file",
    "str_replace":     "edit_file",
    "str_replace_editor": "edit_file",
    "list_dir":        "list_dir",
    "list_directory":  "list_dir",
    "ls":              "list_dir",
    "web_search":      "web_search",
    "search_web":      "web_search",
    "web_fetch":       "web_fetch",
    "fetch_url":       "web_fetch",
    "browse":          "web_fetch",
    # Aliases para búsqueda de ficheros
    "find":            "find_file",
    "find_files":      "find_file",
    "search_files":    "find_file",
    "find_in_dir":     "find_file",
    # Aliases para búsqueda de código
    "grep":            "grep_code",
    "search_code":     "grep_code",
    "grep_search":     "grep_code",
    "code_search":     "grep_code",
    # Aliases para ejecución Python
    "run_python":      "python_exec",
    "execute_python":  "python_exec",
    "python":          "python_exec",
    # Aliases para wc/estadísticas
    "wc":              "file_stat",
    "stat":            "file_stat",
}


_IMG_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif"}


def _load_images_b64(paths_or_b64: list[str]) -> list[str]:
    """Convierte rutas de imagen o strings raw en base64 para Ollama."""
    import base64
    result = []
    for item in paths_or_b64:
        item = item.strip()
        if not item:
            continue
        from pathlib import Path as _Path
        p = _Path(item).expanduser()
        if p.exists() and p.suffix.lower() in _IMG_EXTENSIONS:
            try:
                result.append(base64.b64encode(p.read_bytes()).decode())
            except Exception:
                pass
        elif len(item) > 100:
            # Asumir que ya es base64
            result.append(item)
    return result


def _ctx_bar(used: int, total: int, width: int = 10, plain: bool = False) -> str:
    """Barra de progreso del contexto con chars ▰▱ y color según nivel de llenado."""
    if total <= 0:
        return "─" * width
    pct = min(used / total, 1.0)
    filled = int(pct * width)
    bar = '▰' * filled + '▱' * (width - filled)
    if plain:
        return bar
    color = "green" if pct < 0.60 else "yellow" if pct < 0.85 else "bold red"
    return f"[{color}]{bar}[/{color}]"


def _compact_hint(cpct: int, thresh_pct: int) -> str:
    if cpct >= thresh_pct:
        return "  ↻ compactando"
    if cpct >= thresh_pct - 10:
        return "  ↻ cerca compactación"
    return ""


def _pbar_thin(done: int, total: int, w: int = 20) -> str:
    """Barra de progreso fina con caracteres ▰▱ para compactación."""
    filled = int(done / max(total, 1) * w)
    return "▰" * filled + "▱" * (w - filled)


def _pbar_thin_ratio(ratio: float, w: int = 20) -> str:
    """Igual que _pbar_thin pero con ratio 0.0–1.0 para animación."""
    filled = int(max(0.0, min(1.0, ratio)) * w)
    return "▰" * filled + "▱" * (w - filled)


def _sfmt(style: str, text: str) -> str:
    """Embede un segmento con estilo para el status window de la TUI.

    Usa marcadores de control \x01STYLE\x02TEXT\x03 que app.py:_parse_status_line()
    convierte en tuplas (class:STYLE, TEXT) para prompt_toolkit.
    Invisible en rutas no-TUI donde _status_cb es None.
    """
    return f"\x01{style}\x02{text}\x03"


def _bar_style(cpct: int, thresh_pct: int) -> str:
    """Devuelve el nombre de estilo para la barra de contexto según el porcentaje."""
    if cpct >= thresh_pct:
        return "status-bar-crit"
    if cpct >= thresh_pct - 10:
        return "status-bar-near"
    if cpct >= 60:
        return "status-bar-warn"
    return "status-bar-ok"


def _hint_styled(cpct: int, thresh_pct: int) -> str:
    """Devuelve el hint de compactación envuelto en _sfmt con el estilo adecuado."""
    if cpct >= thresh_pct:
        return _sfmt("status-hint-crit", "  ↻ compactando")
    if cpct >= thresh_pct - 10:
        return _sfmt("status-hint-near", "  ↻ cerca compactación")
    return ""


# Header mínimo: solo lo que no está en el mini-context del workspace
SYSTEM_HEADER = """\
Eres {agent_name}, asistente de programación local con Ollama.
Fecha: {today}
Directorio del proyecto (CWD): {project_dir}
IMPORTANTE: el código del proyecto está en el CWD. `~/.oocode/workspace/` contiene solo identidad/memoria del agente, NO código del proyecto.
"""

# ── Grupos de tools para filtrado de schemas ─────────────────────────────────
# Reduce el overhead de tokens (~11K) enviando solo los schemas relevantes.
# Estrategia conservadora: "core" + "lsp" + "memory" siempre presentes.
# Si no se detecta ningún grupo específico → se envían todos (modo seguro).
_TOOL_GROUPS: dict[str, frozenset] = {
    "core": frozenset({
        "read_file", "write_file", "edit_file", "edit_files",
        "grep_code", "multi_grep", "find_files", "find_file", "find_dir",
        "ls_dir", "ls_file", "code_outline", "read_sections", "code_search",
        "code_compare", "diff_files", "web_search", "web_fetch", "bash",
        "run_tests", "test_file", "mem_save", "workspace_remember",
        "plan_create", "task_done", "python_exec", "spawn_subagent",
        "analyze_codebase", "symbol_lookup", "affected_files",
        "lint_file", "lint_project", "regex_replace", "bulk_replace",
        "smart_replace", "patch_apply", "file_stat", "tree", "count_lines",
        "context_before_edit", "pre_edit_check", "read_files", "grep_file",
    }),
    "git": frozenset({
        "git_status", "git_diff", "git_log", "git_commit", "git_add",
        "git_push", "git_pull", "git_branch", "git_stash", "git_blame",
        "git_rebase", "git_tag", "git_cherry_pick", "git_worktree",
        "git_patch", "git_clone",
    }),
    "docker": frozenset({
        "docker_ps", "docker_logs", "docker_exec", "docker_inspect",
        "docker_images", "docker_stop", "docker_rm", "docker_cp",
        "compose_up", "compose_down", "compose_logs", "compose_exec",
        "compose_status", "compose_services", "compose_restart",
        "compose_build", "compose_config", "compose_run", "compose_version",
        "compose_stop", "compose_images", "compose_top", "compose_pull",
    }),
    "debug": frozenset({
        "strace_run", "gdb_run", "pdb_run", "valgrind_run",
        "make_run", "run_script", "format_code", "mypy_check",
    }),
    "system": frozenset({
        "systemctl_status", "systemctl_action", "journalctl",
        "net_interfaces", "net_connections", "net_ping", "net_dns",
        "disk_usage", "disk_inodes", "dir_size", "lsblk_info",
        "user_list", "user_info", "group_list", "who_logged",
        "ps_list", "top_snapshot", "kill_process",
        "fw_status", "fw_rules", "fw_allow", "fw_deny",
        "sys_info", "sys_updates", "sys_logs", "env_vars", "cron_list",
        "process_list",
    }),
    "packages": frozenset({
        "apt_update", "apt_upgrade", "apt_install", "apt_remove",
        "apt_search", "apt_info", "apt_list_installed",
        "dnf_update", "dnf_install", "dnf_remove", "dnf_search",
        "dnf_info", "rpm_query", "pip_tool", "npm_tool",
    }),
    "lsp": frozenset({
        "lsp_definition", "lsp_references", "lsp_hover", "lsp_symbols",
        "lsp_diagnostics", "lsp_completion", "lsp_rename", "lsp_format",
        "lsp_code_actions", "lsp_type_definition", "lsp_implementation",
        "lsp_workspace_symbols", "lsp_call_hierarchy", "lsp_restart",
    }),
    "data": frozenset({
        "json_format", "json_validate", "yaml_validate", "jq_query",
        "encode_base64", "decode_base64", "url_encode", "url_decode",
        "compute_hash", "to_base", "format_json", "escape_string",
        "hex_encode", "hex_decode", "calculate", "template_fill",
        "http_get", "port_check", "env_check", "hash_text", "get_datetime",
        "system_info",
    }),
    "fs": frozenset({
        "chmod_file", "chmod_dir", "chown_file", "chown_dir",
        "mv_file", "cp_file", "rm_file", "rm_dir", "mkdir_dir",
        "touch_file", "symlink_create", "readlink",
        "archive_extract", "archive_create", "archive_list",
    }),
    "memory": frozenset({
        "snippet_save", "snippet_get", "snippet_list", "snippet_delete",
        "vault_list", "vault_get", "todo_list", "todo_add", "todo_done",
        "todo_sync", "changelog_today", "changelog_session", "changelog_week",
        "clipboard_copy", "clipboard_paste",
        "index_workspace", "semantic_search",
        "extract_functions", "extract_classes", "extract_imports", "ast_summary",
        "build_symbol_index", "find_symbol", "list_symbols",
        "search_todos", "run_quick_check", "list_recent_files", "read_project_file",
    }),
    "office": frozenset({
        "email_list", "email_read", "email_send", "email_search",
        "doc_convert", "pdf_extract_text", "doc_word_count",
        "xlsx_read", "xlsx_write", "csv_analyze",
        "cal_list", "cal_add", "cal_search",
        "notes_list", "notes_search", "notes_save",
        "image_to_text", "contact_search", "markdown_to_html",
        "doc_read_template_fields", "doc_fill_template", "doc_list_templates",
        "doc_create_rfc", "xlsx_fill_range", "xlsx_append_row", "xlsx_create_report",
        "project_context_read", "project_init_office", "doc_project_save",
        "doc_read", "doc_update_section", "doc_version_bump",
        "cmdb_search", "cmdb_update", "asset_register_add",
    }),
    "security": frozenset({
        "nmap_scan", "port_scan", "ssl_check", "whois_lookup", "dns_enum",
        "http_headers", "nikto_scan", "gobuster_run", "curl_request",
        "encode_decode", "hash_crack", "jwt_decode", "cert_inspect",
        "log_analyze", "secret_scan", "cve_lookup",
        "xor_decode", "steganography_check", "base_convert", "hex_dump",
        "fw_audit", "ssh_key_audit", "sudoers_review", "file_integrity_check",
    }),
    "iot": frozenset({
        "tapo_list", "tapo_status", "tapo_on_off", "tapo_set",
        "blink_status", "blink_arm", "blink_snapshot", "blink_clips", "blink_verify",
        "alexa_devices", "alexa_speak", "alexa_command", "alexa_volume",
        "tuya_list", "tuya_status", "tuya_control",
        "ha_entities", "ha_state", "ha_control", "ha_automation",
        "mqtt_publish", "mqtt_subscribe",
        "esphome_list", "esphome_control",
        "iot_discover",
    }),
}

_TASK_KEYWORDS: dict[str, frozenset] = {
    "git": frozenset({
        "git", "commit", "branch", "merge", "rebase", "push", "pull",
        "stash", "blame", "tag", "cherry", "worktree", "repositorio", "repo",
    }),
    "docker": frozenset({
        "docker", "container", "compose", "imagen", "image", "dockerfile",
        "kubernetes", "k8s", "pod", "service", "volumen", "volume",
    }),
    "debug": frozenset({
        "debug", "debuggear", "gdb", "valgrind", "strace", "pdb",
        "breakpoint", "compilar", "compile", "build", "make", "cmake",
        "makefile",
    }),
    "system": frozenset({
        "systemctl", "service", "daemon", "proceso", "process", "red",
        "network", "firewall", "disco", "disk", "usuario", "user",
        "cpu", "cron", "journal", "syslog",
    }),
    "packages": frozenset({
        "instalar", "install", "apt", "dnf", "pip", "npm", "paquete",
        "package", "dependencia", "dependency", "upgrade", "actualizar",
        "requirements.txt", "package.json",
    }),
    "data": frozenset({
        "json", "yaml", "base64", "hash", "encode", "decode", "url",
        "hex", "template", "calcular", "calculate", "http", "api",
    }),
    "office": frozenset({
        "email", "correo", "mail", "imap", "smtp", "calendario",
        "calendar", "evento", "event", "reunión", "meeting",
        "documento", "document", "pdf", "excel", "xlsx", "csv",
        "hoja", "spreadsheet", "nota", "note", "notas", "notes",
        "contacto", "contact", "vcard", "vcf", "ocr", "pandoc",
        "word", "docx", "libreoffice", "markdown", "informe", "report",
        "rfc", "change request", "migración", "migration", "datacenter",
        "plantilla", "template", "formulario", "form", "informe it",
        "incidencia", "incident", "post-mortem", "rollback", "firewall",
        "servidor", "server", "infraestructura", "infrastructure",
        "cmdb", "inventario", "inventory", "activo", "asset",
        "business case", "resumen ejecutivo", "executive summary",
        "proyecto", "project", "version", "sección", "section",
        "oocode.md", "naming", "client", "cliente",
    }),
    "iot": frozenset({
        "tapo", "blink", "alexa", "echo", "tuya", "smart life", "smartlife",
        "esphome", "esp8266", "esp32", "mqtt", "zigbee", "z-wave",
        "luz", "light", "luces", "bombilla", "bulb", "enchufe", "plug",
        "camara", "camera", "cámara", "timbre", "doorbell", "ring",
        "casa inteligente", "smarthome", "home assistant", "homeassistant",
        "iot", "sensor", "interruptor", "switch", "ventilador", "fan",
        "termostato", "thermostat", "temperatura", "temperature",
        "automatización", "automation", "escena", "scene", "rutina",
    }),
    "security": frozenset({
        "pentest", "pentest", "hacking", "ctf", "seguridad", "security",
        "vulnerabilidad", "vulnerability", "cve", "exploit", "nmap",
        "nikto", "gobuster", "hashcat", "hash", "crack", "brute",
        "ssl", "tls", "certificado", "certificate", "whois", "dns",
        "puerto", "port", "scan", "escaneo", "firewall", "iptables",
        "jwt", "token", "cifrado", "encrypt", "decrypt", "crypto",
        "esteganografia", "steganography", "forense", "forensic",
        "log", "audit", "auditoria", "secret", "leak", "creds",
        "xor", "hex", "base64", "decode", "encode",
        "ssh", "sudoers", "integridad", "integrity",
    }),
    "fs": frozenset({
        "chmod", "chown", "mover", "move", "copiar", "copy", "eliminar",
        "delete", "symlink", "archive", "zip", "tar", "comprimir",
        "permisos", "permissions",
    }),
}

SYSTEM_RULES = """\
## HERRAMIENTAS — USA SIEMPRE LA COLUMNA ✅

| Necesidad | ✅ USA | ❌ NO |
|-----------|--------|-------|
| Leer fichero | `read_file(path, offset=N, limit=M)` | `bash cat/head/tail/sed -n` |
| Comparar ficheros | `diff_files(a, b)` | `bash diff` |
| Tests | `run_tests(path)` | `bash pytest / npm test` |
| Estructura fichero | `code_outline(path)` **— OBLIGATORIO antes de editar ficheros >1000 líneas** | `read_file` con múltiples offsets |
| Leer secciones | `read_sections(path, ['Clase.metodo', 'funcion'])` **— OBLIGATORIO para ficheros >1000 líneas** | `read_file(offset=N)` × N |
| Buscar en código | `grep_code` / `multi_grep(patterns=[…])` | `bash grep -rn` |
| Buscar símbolo | `lsp_workspace_symbols(q, path)` o `symbol_lookup` | `bash grep -rn` |
| Impacto de cambio | `affected_files(symbol, directory)` | `grep_code` + leer cada fichero |
| Callers/callees | `lsp_call_hierarchy(path, line)` | `bash grep -rn función` |
| Comparar código | `code_compare(a, b, symbol)` | grep+read×2 |
| grep con filtros | `grep_code(exclude_pattern=, count_only=, files_with_matches=, files_without_matches=)` | `bash grep|grep -v` |
| Buscar ficheros | `find_file` / `find_files` / `find_dir` | `bash find -name` |
| Listar directorio | `ls_dir` | `bash ls -la` |
| Info fichero | `file_stat` | `bash wc -l / stat` |
| Editar fichero | `edit_file` / `regex_replace` / `smart_replace` | `bash sed -i` |
| Editar múltiples | `bulk_replace` / `edit_files` | `bash sed -i` en bucle |
| Crear fichero | `write_file` | `bash cat > f <<'EOF'` |
| Python puntual | `python_exec(code=…, workdir=…)` | `bash python3 -c/<<'EOF'` |
| Índice símbolos | `find_symbol` / `list_symbols` / `extract_functions` | `bash ctags` |
| Git | `git_status/diff/add/commit/log/branch/stash` | `bash git …` |
| Docker/compose | `docker_ps/logs/exec/inspect` / `compose_up/down/logs/exec/…` | `bash docker …` |
| Copiar a container | `docker_cp(src=…, dst=…)` | `bash docker cp` |
| Compilar | `make_run` | `bash make/gcc/cc` |
| Linting | `lint_file` / `lint_project` | `bash ruff/mypy/…` |
| Paquetes Python | `pip_tool(action='install', packages=[…])` | `bash pip install` |
| Paquetes Node | `npm_tool(action='install', packages=[…])` | `bash npm install` |
| Debug | `strace_run` / `gdb_run` / `pdb_run` / `valgrind_run` | `bash strace/gdb` |

`bash` = ÚLTIMO RECURSO — solo si ninguna tool de la tabla lo cubre.

## Planificación autónoma — OBLIGATORIA para tareas complejas

**Para cualquier consulta que implique ≥3 pasos distintos** (exploración + implementación + verificación, o múltiples ficheros, o varias fases): ANTES de ejecutar NINGUNA herramienta, emite un plan detallado en texto para que el usuario pueda revisarlo.

**Formato del plan detallado (≥3 pasos o replanificación):**
```
Plan:
1. [Acción]: [qué harás exactamente] — ficheros: [rutas exactas] — tools: [tools que usarás]
2. [Acción]: [cambios concretos] — ficheros: [rutas] — riesgo: [si puede romper algo]
...
```
Si hay bloqueadores o decisiones no claras, añade al final:
`⚠ REQUIERE REVISIÓN: [descripción — decisión de diseño, dependencia faltante, riesgo alto]`
El sistema pausa y espera al usuario. Sin ese marcador, continúa automáticamente.
El usuario puede intervenir en cualquier momento con `/steer` o `/subagents steer`.

**Flujo de planificación con `plan_create`:**
1. Emite el plan en texto (formato arriba) — SIN llamar tools aún.
2. Llama `plan_create(tasks=["Tarea 1: …", "Tarea 2: …", ...], summary="Qué vas a hacer")` — activa el panel visual.
3. Ejecuta cada tarea anunciando "Tarea N: descripción breve" al empezarla.
4. Llama `task_done()` al completar cada tarea — avanza el marcador ✔/◼/◻.
5. Al terminar TODAS, di "He completado todas las tareas." como primera frase.

**Replanificación:** si durante la ejecución descubres que el plan original es incorrecto o incompleto:
1. Anuncia `"Replanificación:"` seguido del nuevo plan antes de cambiar de estrategia.
2. Llama `plan_create(tasks=[...])` para actualizar el panel visual con las nuevas tareas.
3. Llama `workspace_remember(note="Aprendizaje: [descripción del problema] → [solución adoptada]")` para documentar el problema en OOCODE.md y evitar repetirlo en futuras sesiones.
No cambies de estrategia silenciosamente.

**Alternativa ligera (solo texto, sin panel):** si la tarea tiene exactamente 2 pasos o es puramente exploratoria, una frase de anuncio basta.

**Cuándo usar subagente (`spawn_subagent`):**
- Proyecto muy grande: exploración exhaustiva de codebase mientras el hilo principal prepara el plan.
- Tareas completamente independientes que no comparten estado (ej. explorar fichero A y explorar fichero B simultáneamente).
- Análisis read-only intensivo: `spawn_subagent(task="explorar…", explore=True)`.

**Cuándo NO usar subagente:** edición de ficheros, tests, implementación — hazlo directamente con las tools.

## Flujo de trabajo

1. **Analiza y planifica** — si la tarea es compleja (≥3 pasos), crea un plan numerado primero.
2. **Explora PRIMERO** — `read_file` + `grep_code` + `lsp_symbols` antes de editar.
   - Localiza ficheros con `find_files(directory=CWD, name="*.ext")` o `ls_dir(CWD)`.
   - NUNCA uses `edit_file` sin haber leído el fichero en este turno (el agente lo bloqueará).
   - Ante errores HTTP/API/herramienta desconocida → `web_search` primero.
3. **Implementa** — `edit_file` / `write_file` / `bulk_replace`. Anuncia qué fichero editas y por qué. Tras cada edición, describe en 1-2 frases qué cambió y qué efecto tiene.
4. **Verifica** — `run_tests` / `lint_file` / `lsp_diagnostics` / `make_run`. Reporta el resultado: "N tests pasados, M fallidos" o lista de errores con `ruta:línea:mensaje`.
5. **Finaliza y reporta** — informe estructurado: qué se hizo, ficheros cambiados (rutas exactas), resultado de tests/lint, advertencias, próximos pasos. Llama `mem_save` con hallazgos no obvios; `workspace_remember` para instrucciones persistentes.

## Reglas generales
- **Comunicación con el usuario (EL USUARIO NO VE LAS TOOLS NI SUS RESULTADOS, SOLO TU TEXTO):**
  - **Antes de actuar:** anuncia brevemente qué vas a hacer (1 frase para simple, plan detallado para ≥3 pasos).
  - **Tarea compleja (≥3 pasos) o replanificación:** emite un plan detallado en texto antes de la primera tool (ver "Planificación autónoma"). El sistema continúa automáticamente; el usuario puede redirigir con `/steer`.
  - **Bloqueo no resoluble:** añade "⚠ REQUIERE REVISIÓN: [descripción]" al plan — el sistema pausa y espera al usuario antes de continuar.
  - **Tras exploración:** describe qué encontraste — rutas de ficheros, funciones relevantes, causas identificadas, fragmentos de código con `ruta:línea`. No digas "encontré algo" sin mostrar el qué.
  - **Tras implementación:** describe el cambio — qué función/clase se modificó, qué hacía antes y qué hace ahora. Un antes/después breve si no es obvio.
  - **Al finalizar:** informe estructurado — qué se hizo, ficheros modificados (rutas exactas), resultado de tests (N pasados / M fallidos), advertencias activas, próximos pasos si procede.
- **Ficheros >1000 líneas** (cualquier lenguaje o formato): SIEMPRE empieza con `code_outline(path)` para ver la estructura y `read_sections(path, ['NombreFuncion'])` para leer solo la sección relevante. NUNCA `read_file` sin offset en ficheros grandes. Antes de editar: `read_sections` → `grep_code` para verificar old_string → `edit_file`.
- NUNCA inventes rutas, código ni resultados. NUNCA declares ✅ sin verificar con tools.
- **Verbosidad adaptada al contexto** — sin relleno ("Entendido, voy a...", "Como puedes ver...") pero SÍ con contenido cuando el contexto lo exige:
  - **Hallazgos y análisis:** detallado — fragmentos de código con `ruta:línea`, lista de ítems ordenada por severidad, causa raíz explicada. El usuario no ve los ficheros: necesita ver el contexto.
  - **Después de implementar:** describe qué cambió (fichero + función + qué y por qué). Muestra un antes/después si el cambio no es obvio.
  - **Informe de finalización:** resumen estructurado — qué se hizo, qué ficheros cambiaron (rutas exactas), resultado de tests (N pasados / M fallidos), advertencias, próximos pasos si procede.
  - Código en bloques ```language. Errores y logs en ```text.
- **El CWD es el directorio del proyecto.** Usa rutas absolutas al CWD para leer/editar código.
  `~/.oocode/workspace/` = identidad del agente (NO código del proyecto). NO busques código ahí.
- **`web_search` — escala antes de repetir estrategias que no funcionan:**
  - Error HTTP/API/import desconocido → busca el error exacto + versión + plataforma ANTES de probar nada más.
  - Símbolo, función o API no encontrada tras ≥3 búsquedas vacías en el proyecto → puede que el nombre sea externo o haya cambiado.
  - ≥3 estrategias distintas fallidas con el mismo problema → busca antes de seguir adivinando.
- **`compose_down -v` DESTRUYE VOLÚMENES (base de datos, datos persistentes)** — PROHIBIDO salvo que el usuario lo pida explícitamente. Usa `compose_stop` o `compose_restart` en su lugar.
- **Escribir ficheros DENTRO de un contenedor Docker:** `write_file` en el host → `docker_cp(src='~/.oocode/tmp/file', dst='CONTAINER:/ruta/')`. Para contenido pequeño: `docker_exec(command='printf \\'texto\\' > /ruta/fichero')`.
- **write_file Permission denied (Errno 13):** la ruta pertenece a un volumen Docker o directorio de sistema. Escribe en `~/.oocode/tmp/` y usa `docker_cp` para moverlo al contenedor.
- Si bash devuelve error: diagnostica antes de reintentar (`ls_dir(path)`/`find_files(directory=path)`); no repitas el mismo comando.
- **PROHIBIDO** (el agente bloqueará): ficheros .py/.sh temporales, heredocs bash, `bash git/grep/find/ls/cat/sed -i/make/pytest/docker exec/docker compose/docker cp`.
- Anti-bucle: si una tool falla 2 veces con el mismo argumento, CAMBIA estrategia.
- Antes de `regex_replace`: verifica con `grep_code` que el patrón existe exactamente.
- Si `regex_replace` falla: usa `read_file` para ver el texto REAL → `edit_file` con literal exacto.
- En planes multi-tarea: anuncia cada tarea con "Tarea N: descripción breve" al empezarla. Cuando hayas completado TODAS las tareas usando tools, tu primera frase debe ser "He completado todas las tareas." — el sistema lo detecta y detiene la ejecución.
- **PROHIBIDO — nunca emitas "He completado todas las tareas." si**: (1) hay tareas ◻ pendientes en el panel, (2) en la misma respuesta mencionas "Próximo paso", "fase pendiente", `(PENDIENTE)`, "🔄 en curso" u otro trabajo futuro, (3) hay errores sin resolver marcados con `❌`, `REQUIERE CORRECCIÓN` o `(PENDIENTE)`, (4) la tarea activa requería editar/crear ficheros y NO llamaste `edit_file`/`write_file`/`bulk_replace`. El sistema detecta la contradicción y fuerza la continuación.
- Cuando encuentres un error que no puedes resolver en este turno (indicado con `❌`, `REQUIERE CORRECCIÓN`, `(PENDIENTE)` u otro marcador similar): llama `workspace_remember(note="Aprendizaje: [descripción del problema encontrado] → [qué queda pendiente o cómo abordarlo]")` para documentarlo en OOCODE.md, luego explica al usuario qué falta — en lugar de declarar la tarea completada.
- **ANTES de "He completado todas las tareas."** — si la tarea modificó código (`edit_file`/`write_file`/`bulk_replace`/`patch_apply`), DEBES llamar `run_tests` o `test_file` en este mismo turno. No puedes declarar completado sin haber ejecutado los tests. Excepción única: tareas puramente de lectura/análisis/documentación sin ningún cambio de código.
- Nunca emitas una respuesta vacía. Tras recibir resultados de tools, continúa directamente con las siguientes tools o responde al usuario. Si ya has completado todo, di "He completado todas las tareas."

## LSP — usar si hay servidor activo

| Tarea | Tool |
|-------|------|
| Funciones/structs del fichero | `lsp_symbols(path)` |
| Buscar símbolo en proyecto | `lsp_workspace_symbols(query, path)` |
| Callers/callees | `lsp_call_hierarchy(path, line)` |
| Tipo de variable | `lsp_hover(path, line, col)` |
| Errores/warnings | `lsp_diagnostics(path)` |
| Renombrar en todo el código | `lsp_rename(path, line, col, new_name, apply=true)` |

**C/C++ (clangd):** `lsp_symbols` → `lsp_hover` → `lsp_call_hierarchy` → `edit_file` → `lsp_diagnostics` → `make_run`
**Python:** `lsp_diagnostics` tras editar · `lsp_references` antes de renombrar
**JS/TS/Shell/Perl/YAML:** `lsp_diagnostics` tras cada edición

## Instrucciones y memoria
- OOCODE.md + "## Instrucciones del proyecto" tienen máxima prioridad — SIEMPRE respetadas.
- Instrucciones persistentes del usuario → `workspace_remember(note)`.
- Hallazgos importantes (arquitectura, decisiones, bugs) → `mem_save(snake_case_name, content)`.
"""

_SUBAGENT_COLORS = ["cyan", "blue", "magenta", "green", "yellow", "bright_cyan"]


def _make_compact_summary(blocks: list[tuple[str, dict, str, bool]]) -> str:
    """Genera resumen compacto estilo Claude Code para un batch de tool calls TUI con metadata.

    Ejemplo: "Searched 3 patterns, read 2 files, wrote 1 file  (ctrl+o to expand)"
    Para ediciones únicas: "Updated agent/loop.py"  (nombre de fichero, no contador genérico)
    Metadata: timestamp, tokens usados, estado LSP
    """
    import os
    # Mapeo tool → (verbo, unidad_singular, unidad_plural)
    _VERBS: dict[str, tuple[str, str, str]] = {
        # búsqueda
        "code_search":       ("Searched", "pattern", "patterns"),
        "grep_code":         ("Searched", "pattern", "patterns"),
        "grep_file":         ("Searched", "pattern", "patterns"),
        "multi_grep":        ("Searched", "pattern", "patterns"),
        "find_file":         ("Found", "file", "files"),
        "find_files":        ("Found", "file", "files"),
        "find_dir":          ("Found", "directory", "directories"),
        "symbol_lookup":     ("Looked up", "symbol", "symbols"),
        "code_compare":      ("Compared", "file", "files"),
        # lectura
        "read_file":         ("Read", "file", "files"),
        "read_files":        ("Read", "file", "files"),
        "ls_dir":            ("Listed", "directory", "directories"),
        "file_stat":         ("Checked", "file", "files"),
        # escritura
        "write_file":        ("Wrote", "file", "files"),
        "edit_file":         ("Updated", "file", "files"),
        "edit_files":        ("Updated", "file", "files"),
        "regex_replace":     ("Replaced", "pattern", "patterns"),
        "bulk_replace":      ("Replaced", "pattern", "patterns"),
        "patch_apply":       ("Applied", "patch", "patches"),
        # bash / ejecución
        "bash":              ("Ran", "command", "commands"),
        "run_script":        ("Ran", "script", "scripts"),
        "python_exec":       ("Executed", "script", "scripts"),
        # LSP
        "lsp_definition":    ("Resolved", "definition", "definitions"),
        "lsp_references":    ("Found", "reference", "references"),
        "lsp_hover":         ("Checked", "hover", "hovers"),
        "lsp_symbols":       ("Listed", "symbol", "symbols"),
        "lsp_diagnostics":   ("Checked", "diagnostic", "diagnostics"),
        "lsp_completion":    ("Completed", "symbol", "symbols"),
        "lsp_rename":        ("Renamed", "symbol", "symbols"),
        "lsp_format":        ("Formatted", "file", "files"),
        "lsp_workspace_symbols": ("Searched", "symbol", "symbols"),
        "lsp_call_hierarchy":("Built", "call tree", "call trees"),
        # memoria
        "mem_save":          ("Saved", "memory", "memories"),
        "mem_search":        ("Searched", "memory", "memories"),
        "mem_list":          ("Listed", "memory", "memories"),
        # MCP / misc
        "spawn_subagent":    ("Spawned", "subagent", "subagents"),
    }

    # Herramientas que producen diff contable (+N -M líneas)
    _EDIT_TOOLS = frozenset({"edit_file", "edit_files", "write_file"})
    _REPLACE_TOOLS = frozenset({"regex_replace", "smart_replace", "bulk_replace", "patch_apply"})

    from collections import Counter
    import difflib

    counts: Counter = Counter()
    # Track ficheros editados para mostrar nombre cuando solo hay 1
    edited_files: list[str] = []
    total_added = total_removed = 0

    for name, args, result, allowed in blocks:
        if not allowed:
            counts[("Denied", "call", "calls")] += 1
            continue
        # Nombre base para MCP tools (mcp_oocode_assistant_edit_file → edit_file)
        base_name = name
        for _write in ("_edit_file", "_edit_files", "_write_file",
                       "_regex_replace", "_smart_replace", "_bulk_replace", "_patch_apply"):
            if name.startswith("mcp_") and name.endswith(_write):
                base_name = _write[1:]
                break

        verb_info = _VERBS.get(base_name, _VERBS.get(name, ("Used", "tool", "tools")))
        counts[verb_info] += 1

        # Para ediciones: intentar contar líneas y recoger nombre de fichero
        if base_name in _EDIT_TOOLS and not str(result).startswith("Error"):
            path = args.get("path") or args.get("file_path", "")
            if path:
                edited_files.append(os.path.basename(str(path)))
            old_s = args.get("old_string", "")
            new_s = args.get("new_string", "")
            if old_s or new_s:
                diff = list(difflib.unified_diff(
                    old_s.splitlines(), new_s.splitlines(), n=0
                ))
                total_added   += sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
                total_removed += sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))

    parts: list[str] = []
    # Construir partes del resumen
    for (verb, sing, plur), n in counts.most_common():
        # Para ediciones únicas: mostrar nombre del fichero si está disponible
        if verb == "Updated" and n == 1 and len(edited_files) == 1:
            entry = f"Updated {edited_files[0]}"
            if total_added or total_removed:
                entry += f" (+{total_added} -{total_removed})"
            parts.append(entry)
        elif verb == "Updated" and n > 1 and edited_files:
            entry = f"Updated {n} files"
            if total_added or total_removed:
                entry += f" (+{total_added} -{total_removed})"
            parts.append(entry)
        else:
            unit = sing if n == 1 else plur
            parts.append(f"{verb} {n} {unit}")

    if not parts:
        return "(ctrl+o to expand)"
    return ", ".join(parts) + "  (ctrl+o to expand)"




def _record_tool_metrics(tool_name: str, duration: float, success: bool) -> None:
    """Registra métricas de rendimiento de herramientas.
    
    Args:
        tool_name: Nombre de la herramienta.
        duration: Tiempo de ejecución en segundos.
        success: Si la herramienta tuvo éxito.
        cwd: Directorio de trabajo (opcional).
    """
    import time
    from pathlib import Path
    metrics_path = Path.home() / ".oocode" / "metrics" / "tool_timing.jsonl"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    
    entry = {
        "ts": time.time(),
        "tool": tool_name,
        "duration": duration,
        "success": success,
        "cwd": os.getcwd(),
        "metrics": {
            "p99": 0.0,
            "p95": 0.0,
            "p50": 0.0,
            "min": duration,
            "max": duration,
            "count": 1,
            "errors": 0,
        },
    }
    
    with metrics_path.open("a") as f:
        f.write(json.dumps(entry) + "\n")

    return None


def _retry_with_backoff(func, *args, max_retries=3, base_delay=1.0) -> None:
    """Ejecuta func con backoff exponencial."""
    import time
    import random
    
    for attempt in range(max_retries):
        try:
            return func(*args)
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            # Backoff exponencial más consistente
            delay = base_delay * (2 ** attempt) + random.uniform(0, 0.1)
            print(f"⚠ Retry {attempt + 1}/{max_retries} en {delay:.1f}s...")
            time.sleep(delay)
    
    return None

class AgentLoop:
    def __init__(
        self,
        config,
        registry: ToolRegistry,
        permissions: PermissionManager,
        memory: MemorySystem,
        workspace_manager: WorkspaceManager,
        session_manager: SessionManager,
        runtime: Optional[RuntimeSettings] = None,
        subagent_runner=None,
        capture_output: bool = False,
        is_subagent: bool = False,
        ollama_client=None,
    ):
        self.config = config
        self.registry = registry
        self.permissions = permissions
        self.memory = memory
        self.ws = workspace_manager
        self.session = session_manager
        self.rt = runtime or RuntimeSettings()
        self.subagent_runner = subagent_runner
        self.capture_output = capture_output
        self.is_subagent = is_subagent          # activa prefijo visual │ en output
        # Managers opcionales — se asignan desde oocode.py
        self.branches = None
        self.tasks = None
        self.scheduler = None
        self.skills = None
        self.plugins = None
        # Reglas adicionales inyectadas en el system prompt (p.ej. modo explore)
        self._extra_rules: str = ""
        # Última respuesta del asistente (para /copy y Ctrl+O)
        self._last_response: str = ""
        # Tool calls del último turno: lista de (nombre, args_str, resultado_completo)
        self._last_tool_calls: list[tuple[str, str, str]] = []
        # Tiempo de la última llamada LLM (segundos)
        self._last_elapsed: float = 0.0
        # Tiempo de arranque del agente — para mostrar tiempo total en la toolbar
        self._agent_start_time: float = time.time()
        self._task_start_time: Optional[float] = None   # None = sin tarea activa
        self._task_elapsed: float = 0.0                 # duración de la última tarea
        self.context = ConversationContext(
            max_tokens=config.effective_max_context_tokens,
            min_keep=config.compact_min_keep,
            compact_threshold=config.compact_threshold,
            max_summary_chars=config.max_summary_chars,
        )
        # Reutilizar cliente externo si se proporciona (subagentes comparten el del padre
        # para que Ollama no descargue/recargue el modelo entre llamadas).
        if ollama_client is not None:
            self.client = ollama_client
            self._owns_client = False
        else:
            self.client = ollama.Client(host=config.ollama_host)
            self._owns_client = True
        # Último mensaje del usuario — para búsqueda semántica de memoria
        self._last_user_msg: str = ""
        # Caché del snippet de memoria por turno: se calcula una sola vez por run()
        self._turn_mem_snippet: Optional[str] = None
        # RAG automático de workspace — asignado desde oocode.py (WorkspaceRAG | None)
        self._workspace_rag = None
        self._turn_rag_snippet: Optional[str] = None
        self._pending_usage_line: str = ""
        self._kill_requested: bool = False
        # Callback de status (spinner) para el modo Application full-screen.
        # Si es None, se usa Live de Rich (modo REPL clásico).
        self._status_cb = None
        # Tokens acumulados del turno actual (para mostrar en stats line)
        self._turn_inp: int = 0
        self._turn_out: int = 0
        # Contador de auto-continuaciones del turno actual (se resetea en run())
        self._auto_continue_count: int = 0
        # Etiqueta del separador superior: "" → muestra proyecto, "⚙ tool…" durante tool
        self._sep_label: str = ""
        # Control externo de subagentes (inyectados por SubAgentRunner)
        self._steer_queue = None    # queue.SimpleQueue con nuevas instrucciones
        self._ext_kill    = None    # threading.Event: matar desde /subagents kill
        # Contador de ciclos para animación de color del subagente
        self._subagent_color_idx: int = 0
        # Activado durante retry con modelo fallback (timeout del principal)
        self._fallback_active: bool = False
        # Cache del modo elevated aplicado — evita re-iterar 40+ tools cada turno
        self._last_elevated_applied: str = ""
        # Cache del system prompt dentro del turno actual (se invalida en run())
        self._sys_prompt_cache: Optional[str] = None
        # Chat log — solo activo si chatlog.enabled=true en oocode.json
        self.chatlog = ChatLogger(
            enabled     = getattr(config, "chatlog_enabled",     False),
            path        = getattr(config, "chatlog_path",        ""),
            max_size_mb = getattr(config, "chatlog_max_size_mb", 10),
        )
        # Detector de bucles de búsqueda vacíos: avisa al modelo cuando lleva N
        # llamadas consecutivas a tools de búsqueda sin encontrar resultados.
        self._empty_search_streak: int = 0
        self._empty_search_patterns: list[str] = []
        # Detector de bucles de edición fallida: regex_replace/bulk_replace sin coincidencias.
        self._failed_edit_streak: int = 0
        self._failed_edit_patterns: list[str] = []
        # Caché intra-turno: evita ejecutar reads idénticos más de una vez
        # y bloquea writes duplicados que pueden corromper ficheros.
        self._turn_read_cache: dict[str, str] = {}
        self._turn_write_seen: dict[str, str] = {}  # key → resultado anterior
        # Rutas leídas este turno (para exigir read antes de edit_file)
        self._turn_read_paths: set[str] = set()
        # Scripts escritos este turno: detecta bash intentando ejecutarlos
        self._turn_written_scripts: set[str] = set()
        # Contador de bloqueos bash por categoría en el turno actual.
        # Se usa para escalar el mensaje en reintentos y forzar parada.
        self._bash_block_counts: dict[str, int] = {}
        # Fase actual de una operación de memoria: el spinner lo muestra en la status bar
        self._tool_phase: str = ""
        # Ficheros leídos/editados en la sesión: se muestran en el reset visual tras compactación
        # NO se resetea en run() — acumula a nivel de sesión; se vacía al mostrar el reset
        self._session_reads: list[tuple[str, object, bool]] = []
        # Memorias guardadas en la sesión: se muestran en el reset visual tras compactación
        self._session_mems: list[str] = []
        # Tareas múltiples detectadas en el mensaje del usuario antes de enviar al modelo
        # Se inyectan en _turn_guidance() del primer LLM call y se limpia en run()
        self._pending_tasks: list[str] = []
        # Plan de tareas con tracking visual — alimenta el task progress panel del TUI
        # Cada entrada: {text: str, status: "pending"|"active"|"done", start_ts: float, end_ts: float}
        self._plan_tasks: list[dict] = []
        # True mientras _do_compact_impl está activo — suprime el task panel en el TUI
        self._compacting_ctx: bool = False
        # Event que se activa durante _do_compact_impl — permite que run() espere
        # si una compactación manual (F3) empieza mientras el agente está en pausa
        self._compact_running: threading.Event = threading.Event()
        # Callback para vaciar el área de conversación del TUI antes del reset visual
        # (inyectado por OOCodeApp; None → modo sin TUI → escape ANSI directo)
        self._clear_output_cb = None
        # Buffer compacto de tools para el TUI: acumula tools ejecutadas en paralelo
        # y se imprime al final como una línea de resumen compacto.
        # Tools secuenciales (pre_shown=True) se muestran inline y NO se añaden aquí.
        self._turn_block: list[tuple[str, dict, str, bool]] = []
        self._turn_block_has_header: bool = False  # True si el batch ya mostró un ● header
        self._turn_expanded: bool = False
        # Fichero actual procesado por tools de búsqueda (para mostrar en spinner)
        self._tool_current_file: str = ""
        # Live block callbacks (inyectados por OOCodeApp; None en modo REPL)
        self._start_live_block_cb: Optional[Callable] = None
        self._update_live_tools_cb: Optional[Callable] = None
        self._flush_live_block_cb: Optional[Callable] = None
        self._live_tool_count: int = 0   # tools completadas en el live block actual
        # True si el modelo emitió texto al usuario en el turno actual
        self._turn_text_emitted: bool = False
        # Ficheros modificados en la tarea actual (se resetea en run())
        self._task_modified_files: set = set()
        # Último resultado de tests de la tarea actual (se resetea en run())
        self._task_last_test: str = ""

    def __del__(self):
        if getattr(self, "_owns_client", True):
            try:
                self.client.close()
            except Exception:
                pass

    # ── Modelo activo ────────────────────────────────────────────────────────

    def _active_model(self) -> str:
        if self._fallback_active and self.config.fallback_model:
            return self.config.fallback_model
        if self.rt.fast_mode and self.rt.fast_model:
            return self.rt.fast_model
        return self.config.model or ""

    # ── System prompt ────────────────────────────────────────────────────────

    def _system_prompt(self) -> str:
        # Cache dentro del turno: evita releer USER.md/MEMORY.md/OOCODE.md en cada
        # iteración del while cuando el agente hace múltiples tool calls seguidos.
        if self._sys_prompt_cache is not None:
            return self._sys_prompt_cache
        import os as _os
        _project_dir = (
            getattr(self.config, "project_dir", None)
            or _os.getcwd()
        )
        header = SYSTEM_HEADER.format(
            agent_name=self.config.agent_name,
            today=date.today().isoformat(),
            project_dir=_project_dir,
        )
        # Contexto del workspace según ctx_mode (mini ~150 tok, full ~800 tok)
        if self.rt.ctx_mode == "full":
            workspace_ctx = self.ws.load_full_context()
        else:
            workspace_ctx = self.ws.load_mini_context()

        # Memorias semánticamente relevantes para este turno.
        # _turn_mem_snippet se calcula una sola vez al inicio de run() y se
        # reutiliza en las iteraciones siguientes (tool calls del mismo turno).
        if not self.is_subagent:
            if self._turn_mem_snippet is None:
                try:
                    self._turn_mem_snippet = self.memory.context_snippet(
                        self._last_user_msg
                    )
                except Exception:
                    self._turn_mem_snippet = ""
            mem_snippet = self._turn_mem_snippet
        else:
            mem_snippet = ""

        # RAG automático: fragmentos de código relevantes del workspace
        rag_snippet = ""
        if self._workspace_rag is not None and not self.is_subagent:
            if self._turn_rag_snippet is None:
                try:
                    self._workspace_rag.ensure_indexed()
                    _rag_top_k, _rag_thresh = self._rag_params_for_turn(
                        self._last_user_msg
                    )
                    self._turn_rag_snippet = self._workspace_rag.context_snippet(
                        self._last_user_msg,
                        top_k=_rag_top_k,
                        threshold=_rag_thresh,
                    )
                except Exception:
                    self._turn_rag_snippet = ""
            rag_snippet = self._turn_rag_snippet

        # OOCODE.md del proyecto (si existe)
        oocode_md = self.config.load_oocode_md()
        oocode_section = (
            f"\n## Instrucciones del proyecto\n{oocode_md}\n"
            if oocode_md else ""
        )

        # Directorios adicionales de trabajo
        extra_dirs_section = ""
        if self.rt.extra_dirs:
            dirs = "\n".join(f"- {d}" for d in self.rt.extra_dirs)
            extra_dirs_section = f"\n## Directorios de trabajo adicionales\n{dirs}\n"

        # Inyección de plugins activos
        plugin_injection = ""
        if self.plugins:
            plugin_injection = self.plugins.system_injection()

        think_section = self.rt.think_injection()
        extra_rules = f"\n{self._extra_rules}" if self._extra_rules else ""
        _agent_instr = getattr(self.config, "agent_instructions", "") or ""
        agent_instr_section = (
            f"\n## Instrucciones del agente {self.config.agent_name}\n{_agent_instr}\n"
            if _agent_instr else ""
        )
        result = (
            f"{header}\n{workspace_ctx}\n"
            f"{mem_snippet}\n"
            f"{rag_snippet}"
            f"{oocode_section}"
            f"{agent_instr_section}"
            f"{extra_dirs_section}"
            f"{plugin_injection}\n"
            f"{SYSTEM_RULES}{think_section}{extra_rules}"
        )
        self._sys_prompt_cache = result
        # _turn_guidance() se añade AQUÍ, fuera del caché: se recalcula en cada
        # iteración del bucle para reflejar el estado actual del turno.
        return result + self._turn_guidance()

    # ── Display helpers ──────────────────────────────────────────────────────

    def _print(self, *args, **kwargs):
        if not self.capture_output:
            if self.is_subagent:
                # Prefijo │ con color rotativo para distinguir el output del subagente
                col = _SUBAGENT_COLORS[self._subagent_color_idx % len(_SUBAGENT_COLORS)]
                console.print(f"  [bold {col}]│[/bold {col}]", *args, **kwargs)
            else:
                console.print(*args, **kwargs)

    # Nombres de display al estilo Claude Code: verb capitalizado en lugar del snake_case interno
    _TOOL_DISPLAY_NAMES: dict[str, str] = {
        "bash":             "Bash",
        "read_file":        "Read",
        "read_files":       "Read",
        "write_file":       "Write",
        "edit_file":        "Update",
        "edit_files":       "Update",
        "grep_code":        "Search",
        "grep_file":        "Search",
        "multi_grep":       "SearchAll",
        "symbol_lookup":    "Lookup",
        "code_search":      "CodeSearch",
        "code_compare":     "Compare",
        "find_file":        "Find",
        "find_files":       "Find",
        "find_dir":         "FindDir",
        "ls_dir":           "List",
        "file_stat":        "Stat",
        "tree":             "Tree",
        "python_exec":      "Python",
        "make_run":         "Make",
        "run_script":       "Run",
        "format_code":      "Format",
        "mypy_check":       "TypeCheck",
        "lint_file":        "Lint",
        "lint_project":     "Lint",
        "git_status":       "GitStatus",
        "git_diff":         "GitDiff",
        "git_add":          "GitAdd",
        "git_commit":       "GitCommit",
        "git_log":          "GitLog",
        "git_branch":       "GitBranch",
        "git_stash":        "GitStash",
        "regex_replace":    "Replace",
        "bulk_replace":     "ReplaceAll",
        "patch_apply":      "Patch",
        "lsp_diagnostics":  "Diagnostics",
        "lsp_hover":        "Hover",
        "lsp_references":   "References",
        "lsp_rename":       "Rename",
        "extract_functions": "Extract",
        "extract_classes":  "Extract",
        "spawn_subagent":   "Subagent",
        "pip_tool":         "Pip",
        "npm_tool":         "Npm",
        "docker_ps":        "Docker",
        "docker_logs":      "DockerLogs",
        "docker_exec":      "DockerExec",
        "strace_run":       "Strace",
        "gdb_run":          "GDB",
        "valgrind_run":     "Valgrind",
        "explore":          "Explore",
        # Memoria
        "mem_save":           "Memory",
        "workspace_remember": "OOCODE",
    }

    @staticmethod
    def _call_context(name: str, args: dict) -> str:
        """Extrae el argumento más informativo de un tool call para mostrarlo en una línea."""
        from rich.markup import escape as _esc

        def _short_path(p: str, max_len: int = 40) -> str:
            """Basename o ruta relativa corta."""
            if not p:
                return ""
            base = p.rsplit("/", 1)[-1]
            return base if len(base) <= max_len else base[:max_len] + "…"

        if name in ("read_file", "write_file"):
            p   = args.get("path", "")
            off = args.get("offset", "")
            lim = args.get("limit", "")
            rng = (f":{off}" if off else "") + (f"+{lim}" if lim else "")
            return _esc(f"({_short_path(p)}{rng})") if p else ""
        if name in ("edit_file", "edit_files"):
            p = args.get("path", "") or (
                args.get("edits", [{}])[0].get("path", "") if isinstance(args.get("edits"), list) else ""
            )
            return _esc(f"({_short_path(p)})") if p else ""
        if name in ("grep_code", "grep_file"):
            pat  = str(args.get("pattern", ""))[:50]
            d    = args.get("directory", args.get("path", ""))
            base = d.rsplit("/", 1)[-1] if d else ""
            return _esc(f'("{pat}"  {base})') if pat else ""
        if name in ("symbol_lookup",):
            return _esc(f"({args.get('symbol', '')})")
        if name == "multi_grep":
            pats = args.get("patterns", [])
            s = ", ".join(str(p) for p in (pats[:2] if isinstance(pats, list) else [str(pats)[:50]]))
            return _esc(f"([{s}…])" if len(pats) > 2 else f"([{s}])")
        if name == "bash":
            # Primera línea del comando (comandos multilinea: solo el inicio)
            cmd = args.get("command", "").splitlines()[0] if args.get("command") else ""
            cmd = cmd[:100]
            return _esc(f"({cmd})")
        if name in ("find_file", "find_files", "find_dir"):
            n = args.get("name") or args.get("extension") or args.get("glob", "")
            d = args.get("directory", "")
            base = d.rsplit("/", 1)[-1] if d else ""
            return _esc(f"({n}  {base})") if n and base else _esc(f"({n})") if n else ""
        if name in ("bulk_replace", "regex_replace"):
            pat = str(args.get("pattern", ""))[:40]
            return _esc(f'("{pat}"…)') if pat else ""
        if name == "make_run":
            target = args.get("target", "all")
            d      = args.get("directory", "").rsplit("/", 1)[-1]
            return _esc(f"({target}  {d})") if d else _esc(f"({target})")
        if name == "python_exec":
            first = str(args.get("code", "")).split("\n")[0][:60]
            return _esc(f"({first}…)") if "\n" in str(args.get("code", "")) else _esc(f"({first})")
        if name in ("git_diff", "git_log", "git_add", "git_commit"):
            msg = args.get("message") or args.get("path") or args.get("files", "")
            if isinstance(msg, list):
                msg = ", ".join(str(m) for m in msg[:2])
            return _esc(f"({str(msg)[:40]})") if msg else ""
        if name in ("lsp_diagnostics", "lint_file", "mypy_check"):
            p = args.get("path", "")
            return _esc(f"({_short_path(p)})") if p else ""
        return ""

    def _show_tool_call(self, name: str, args: dict) -> None:
        """Muestra un tool call individual (modo REPL o verbose). Internamente llamado
        solo en el bloque de resultado (_show_tool_block)."""
        if self.rt.verbose:
            args_str = json.dumps(args, ensure_ascii=False, indent=2)
            self._print(f"  [dim cyan]⚙[/dim cyan]  [bold]{name}[/bold]")
            self._print(f"[dim]{args_str}[/dim]")
        else:
            ctx = self._call_context(name, args)
            self._print(f"  [dim cyan]⚙[/dim cyan]  [bold]{name}[/bold]  [dim]{ctx}[/dim]")

    def _show_tool_result(self, result: str, allowed: bool) -> None:
        if not allowed:
            self._print("  [dim red]✗  Denegado por el usuario[/dim red]")
            return
        if self.rt.verbose:
            self._print(f"  [dim green]✓[/dim green]  [dim]{result[:800]}[/dim]")
            return
        lines = result.strip().splitlines()
        n_lines = len(lines)
        n_chars = len(result)
        preview = lines[0][:80] if lines else ""
        if n_lines > 3:
            self._print(
                f"  [dim green]✓[/dim green]  [dim]{preview}[/dim]  "
                f"[dim cyan]▸ {n_lines} líneas · {n_chars} chars[/dim cyan]  "
                f"[bold yellow](Ctrl+O para expandir)[/bold yellow]"
            )
        elif n_lines > 1:
            self._print(
                f"  [dim green]✓[/dim green]  [dim]{preview}[/dim]  "
                f"[dim]+{n_lines - 1} líneas[/dim]"
            )
        else:
            self._print(f"  [dim green]✓[/dim green]  [dim]{preview}[/dim]")

    # ── Tools de búsqueda para display compacto ────────────────────────────────
    _SEARCH_DISPLAY_TOOLS = frozenset((
        "code_search", "grep_code", "grep_file", "multi_grep",
        "symbol_lookup", "lsp_workspace_symbols", "mem_search",
        "semantic_search", "find_file", "find_files", "find_dir",
        "search_todos", "lsp_references", "lsp_symbols",
    ))
    _READ_DISPLAY_TOOLS = frozenset((
        "read_file", "read_files", "read_project_file",
        "ls_dir", "ls_file", "file_stat", "tree",
    ))

    def _show_inline_compact_result(self, name: str, args: dict,
                                    result: str, allowed: bool) -> None:
        """Muestra resultado compacto inline (una línea ⎿) para tools no-write en TUI mode."""
        from rich.markup import escape as _esc

        if not allowed:
            self._print("  [dim red]⎿  Denegado[/dim red]")
            return

        r = result.strip() if result else ""
        if not r or r in ("Sin resultados.", "No results."):
            self._print("  [dim]⎿  Sin resultados[/dim]")
            return
        if r.startswith("⛔ AGENTE BLOQUEÓ"):
            first = r.splitlines()[0][:100]
            self._print(f"  [bold yellow]⎿  {_esc(first)}[/bold yellow]")
            return
        if r.startswith("Error:") or r.startswith("Error ") or r.startswith("Timeout:"):
            self._print(f"  [dim red]⎿  {_esc(r.splitlines()[0][:100])}[/dim red]")
            return

        lines = r.splitlines()
        n_lines = len(lines)

        if name in self._SEARCH_DISPLAY_TOOLS:
            # Contar matches (▶) y ficheros únicos (líneas que son "path:line:col")
            n_matches = sum(1 for ln in lines if ln.strip().startswith("▶"))
            # Ficheros únicos: líneas sin sangría que contienen ":" y no comienzan con " "
            file_set: set[str] = set()
            for ln in lines:
                if ln and not ln.startswith(" ") and ":" in ln:
                    fp = ln.split(":")[0].strip()
                    if fp and "/" in fp or "." in fp:
                        file_set.add(fp)
            n_files = len(file_set) if file_set else max(1, n_matches)
            if n_matches > 0:
                expand = "  [dim](ctrl+o)[/dim]" if n_lines > 5 else ""
                self._print(
                    f"  [dim]⎿  {n_matches} resultado{'s' if n_matches != 1 else ''}"
                    f"  en {n_files} fichero{'s' if n_files != 1 else ''}{expand}[/dim]"
                )
            else:
                preview = lines[0][:90]
                if n_lines > 2:
                    self._print(f"  [dim]⎿  {_esc(preview)}  +{n_lines-1}[/dim]")
                else:
                    self._print(f"  [dim]⎿  {_esc(preview)}[/dim]")
        elif name in self._READ_DISPLAY_TOOLS:
            # Fichero leído: "⎿ nombre  [N líneas]"
            fname = (args.get("path") or args.get("file_path") or
                     args.get("directory") or "")
            fname_short = fname.rsplit("/", 1)[-1][:40] if fname else ""
            if fname_short:
                self._print(f"  [dim]⎿  {_esc(fname_short)}  [{n_lines} líneas][/dim]")
            else:
                preview = lines[0][:90]
                self._print(f"  [dim]⎿  {_esc(preview)}[/dim]")
        else:
            # Caso general: primera línea + count
            preview = lines[0][:90]
            if n_lines > 2:
                self._print(
                    f"  [dim]⎿  {_esc(preview)}  "
                    f"[dim cyan]+{n_lines-1}[/dim cyan][/dim]"
                )
            else:
                self._print(f"  [dim]⎿  {_esc(preview)}[/dim]")

    def _render_tool_diff_print(self, name: str, args: dict, result: str) -> None:
        """Renderiza diff de write/edit/replace via self._print (TUI-safe)."""
        if not result or "Error" in result or "fallida" in result or "rollback" in result:
            return
        try:
            import tools.diff_renderer as _dr
            _dr._dprint_fn = self._print
            from tools.diff_renderer import (
                render_edit_diff, render_write_diff,
                render_replace_diff, render_bulk_diff, render_patch_diff,
            )
            _is_edit    = name == "edit_file" or name.endswith("_edit_file")
            _is_multi   = name == "edit_files" or name.endswith("_edit_files")
            _is_replace = (name in ("regex_replace", "smart_replace") or
                           any(name.endswith(s) for s in ("_regex_replace", "_smart_replace")))
            _is_bulk    = name == "bulk_replace" or name.endswith("_bulk_replace")
            _is_patch   = name == "patch_apply" or name.endswith("_patch_apply")
            if _is_edit or _is_multi:
                render_edit_diff(args, result)
            elif _is_replace:
                render_replace_diff(args, result)
            elif _is_bulk:
                render_bulk_diff(args, result)
            elif _is_patch:
                render_patch_diff(args, result)
            else:
                render_write_diff(args, result)
        except Exception:
            pass

    def _show_tool_block(self, name: str, args: dict, result: str,
                         allowed: bool, block_mode: bool = False,
                         suppress_header: bool = False,
                         pre_shown: bool = False) -> None:
        """Muestra un tool call al estilo Claude Code:

          ● ToolName(contexto)
            ⎿  primera línea del resultado
               segunda línea
               … +N líneas (ctrl+o to expand)

        Bloqueos del agente usan ⊘ en amarillo.
        Hints del agente (⚡) se muestran en cyan al final.
        suppress_header=True → batch agrupado: muestra solo ⎿ path, sin resultados.
        pre_shown=True       → header ya impreso antes de ejecutar: salta al resultado.
        """
        if self.capture_output:
            return

        from rich.markup import escape as _esc

        display = self._TOOL_DISPLAY_NAMES.get(name, name)
        ctx     = self._call_context(name, args)

        # TUI mode — dos caminos:
        # • pre_shown=True (ejecución secuencial): header ya impreso por _show_tool_running_header;
        #   mostramos resultado compacto inline y NO añadimos a _turn_block.
        # • pre_shown=False (ejecución paralela): añadimos a _turn_block para resumen al final.
        if getattr(self, "_status_cb", None) is not None and not self.is_subagent and not block_mode:
            # Sufijos de tools nativas y MCP que modifican ficheros (muestra diff)
            _WRITE_NAMES = frozenset(("write_file", "edit_file", "edit_files"))
            _WRITE_SFXS  = ("_write_file", "_edit_file", "_edit_files")
            _REPLACE_NAMES = frozenset(("regex_replace", "smart_replace", "bulk_replace",
                                        "patch_apply"))
            _REPLACE_SFXS  = ("_regex_replace", "_smart_replace", "_bulk_replace",
                               "_patch_apply")
            _is_write   = (name in _WRITE_NAMES or any(name.endswith(s) for s in _WRITE_SFXS))
            _is_replace = (name in _REPLACE_NAMES or any(name.endswith(s) for s in _REPLACE_SFXS))
            _result_str = str(result)
            _is_ok = not _result_str.startswith("⛔") and not _result_str.startswith("⚠️ DUPLICADO")

            if pre_shown:
                # Ejecución secuencial: el header ◐ solo se mostró para write/replace/mem.
                # Write/replace: mostrar diff visual; solo mostrar errores si falla.
                if _is_write or _is_replace:
                    if not _is_ok:
                        self._print(f"  [dim red]⎿  {_esc(_result_str[:120])}[/dim red]")
                    elif allowed:
                        self._render_tool_diff_print(name, args if isinstance(args, dict) else {}, _result_str)
                elif name in self._MEM_TOOLS:
                    # Herramientas de memoria: resultado compacto inline (ya tienen ◐)
                    self._show_inline_compact_result(name, args, _result_str, allowed)
                else:
                    # Todas las demás: bufferizar en _turn_block para resumen agrupado
                    self._turn_block.append((name, args if isinstance(args, dict) else {}, _result_str, allowed))
                # Actualizar contador live (⎿ se ve actualizar en tiempo real)
                if self._update_live_tools_cb:
                    self._live_tool_count += 1
                    self._update_live_tools_cb(self._live_tool_count)
                return

            # Ejecución paralela: acumular en _turn_block para resumen compacto al final
            self._turn_block.append((name, args if isinstance(args, dict) else {}, _result_str, allowed))
            if (_is_write or _is_replace) and allowed and not suppress_header and _is_ok:
                self._print(
                    f"  [bold green]●[/bold green] [bold]{_esc(display)}[/bold][dim]{ctx}[/dim]"
                )
                self._render_tool_diff_print(name, args if isinstance(args, dict) else {}, _result_str)
                self._turn_block_has_header = True
            # Actualizar contador live (paralelo: se incrementa conforme llegan resultados)
            if self._update_live_tools_cb:
                self._live_tool_count += 1
                self._update_live_tools_cb(self._live_tool_count)
            return

        # ── Header ────────────────────────────────────────────────────────────
        is_blocked  = isinstance(result, str) and result.startswith("⛔ AGENTE BLOQUEÓ")
        is_mem_tool = name in self._MEM_TOOLS

        if suppress_header:
            # Batch agrupado: listar solo el path/ctx con sangría y volver
            self._print(f"  [dim]⎿  {_esc(ctx or display)}[/dim]")
            return  # el resultado completo no se muestra por herramienta en batch
        elif not pre_shown:
            # Header normal (alineado a 2 espacios, como el texto del asistente)
            if is_blocked:
                self._print(f"  [bold yellow]⊘[/bold yellow] [yellow]{_esc(display)}[/yellow][dim]{ctx}[/dim]")
            elif is_mem_tool:
                self._print(f"  [bold cyan]⬡[/bold cyan] [bold cyan]{_esc(display)}[/bold cyan][dim]{ctx}[/dim]")
            else:
                self._print(f"  [bold green]●[/bold green] [bold]{_esc(display)}[/bold][dim]{ctx}[/dim]")
        # pre_shown=True → el header ya se mostró en _show_tool_running_header; solo resultados

        if self.rt.verbose:
            self._print(f"  [dim]{json.dumps(args, ensure_ascii=False, indent=2)}[/dim]")

        # ── Resultado ──────────────────────────────────────────────────────────
        if not allowed:
            self._print("  [dim red]⎿  Denegado[/dim red]")
            return

        # Los hooks post-write (lint, LSP, autoformat) muestran su propio bloque
        # visual en consola Y añaden texto al resultado para el LLM.
        # Aquí cortamos esas secciones del display para no mostrarlas dos veces.
        _HOOK_MARKERS = ("\n\n[Lint] ", "\n\n[LSP Diagnósticos] ", "\n[Autoformat] ")
        display_result = result
        if isinstance(result, str):
            for _marker in _HOOK_MARKERS:
                _cut = result.find(_marker)
                if _cut != -1:
                    display_result = result[:_cut]
                    break

        all_lines    = display_result.strip().splitlines() if isinstance(display_result, str) else []
        normal_lines = []   # líneas de output real
        hint_lines   = []   # ⚡ AGENTE — mostrar en cyan dim

        for line in all_lines:
            if line.startswith("⚠️"):
                pass                        # antipatterns bash: solo para el modelo
            elif line.startswith("⚡ AGENTE"):
                hint_lines.append(line)     # hints de evaluación: mostrar en cyan
            else:
                normal_lines.append(line)

        if not normal_lines and not hint_lines:
            normal_lines = all_lines        # fallback: mostrar todo

        # ── Líneas de output (máx 5) ──────────────────────────────────────────
        MAX_SHOW     = 5
        line_color   = "yellow" if is_blocked else ("cyan" if is_mem_tool else "dim")
        visible      = normal_lines[:MAX_SHOW]

        for i, line in enumerate(visible):
            pfx = "  [dim]⎿[/dim]  " if i == 0 else "     "
            self._print(f"{pfx}[{line_color}]{_esc(line[:140])}[/{line_color}]")

        hidden = len(normal_lines) - len(visible)
        if hidden > 0:
            self._print(f"     [dim]… +{hidden} líneas (ctrl+o to expand)[/dim]")

        # ── Hints del agente (⚡) — cyan dim, máx 2 líneas ───────────────────
        if hint_lines:
            for line in hint_lines[:2]:
                self._print(f"  [dim cyan]⎿  {_esc(line[:140])}[/dim cyan]")

        # ── Diff visual para write/edit en modo no-TUI (subagente o REPL) ────
        if allowed and self.is_subagent:
            _subagent_write_names = frozenset((
                "write_file", "edit_file", "edit_files",
                "regex_replace", "smart_replace", "bulk_replace", "patch_apply",
            ))
            _subagent_write_sfx = ("_write_file", "_edit_file", "_edit_files",
                                   "_regex_replace", "_smart_replace", "_bulk_replace", "_patch_apply")
            _is_write_op = (name in _subagent_write_names or
                            any(name.endswith(s) for s in _subagent_write_sfx))
            if _is_write_op:
                self._render_tool_diff_print(name, args if isinstance(args, dict) else {},
                                             str(result))

    def _flush_turn_block(self) -> None:
        """Cierra el live block (si activo) y resetea el buffer de tools del turno.

        Llamado antes de cada nuevo ● y al final del turno. En TUI mode con live block,
        hace flush del bloque dinámico al buffer estático con el summary final.
        """
        _WRITE_NAMES = frozenset((
            "write_file", "edit_file", "edit_files",
            "regex_replace", "smart_replace", "bulk_replace", "patch_apply",
        ))
        _WRITE_SUFFIXES = ("_write_file", "_edit_file", "_edit_files",
                           "_regex_replace", "_smart_replace", "_bulk_replace", "_patch_apply")

        if self.capture_output:
            self._turn_block = []
            self._turn_block_has_header = False
            return

        # TUI con live block: cerrar el bloque dinámico con summary compacto
        if self._flush_live_block_cb:
            block = self._turn_block
            if getattr(self, "_turn_block_has_header", False):
                block = [t for t in block
                         if not (t[0] in _WRITE_NAMES or
                                 any(t[0].endswith(s) for s in _WRITE_SUFFIXES))]
            summary = _make_compact_summary(block) if block else ""
            if not summary and self._live_tool_count > 0:
                n = self._live_tool_count
                summary = f"Used {n} tool{'s' if n != 1 else ''}"
            self._flush_live_block_cb(summary)
            self._live_tool_count = 0
            self._turn_block = []
            self._turn_block_has_header = False
            return

        # REPL fallback: print ⎿ summary al buffer estático
        if not self._turn_block or self._status_cb is None:
            self._turn_block = []
            self._turn_block_has_header = False
            return

        block = self._turn_block
        if getattr(self, "_turn_block_has_header", False):
            block = [
                t for t in block
                if not (t[0] in _WRITE_NAMES or
                        any(t[0].endswith(s) for s in _WRITE_SUFFIXES))
            ]

        if block:
            summary = _make_compact_summary(block)
            self._print(f"  [dim]⎿  {summary}[/dim]")

        self._turn_block = []
        self._turn_block_has_header = False

    def _run_animated_header(self, name: str, args: dict) -> str:
        """Ejecuta la tool con header animado verde→amarillo en modo REPL.

        Mientras la tool ejecuta: cicla colores ANSI con \\r en la misma línea.
        Al terminar: limpia la línea y muestra el header definitivo en blanco (◐).
        En modo capture_output (subagentes) omite la animación.
        """
        import sys, os
        from rich.markup import escape as _esc

        if self.capture_output:
            return self._execute_tool(name, args)

        display     = self._TOOL_DISPLAY_NAMES.get(name, name)
        ctx         = self._call_context(name, args)
        is_mem_tool = name in self._MEM_TOOLS

        # ctx contiene markup Rich escapado — obtener versión plana para ANSI raw
        ctx_plain = ctx.replace("\\[", "[").replace("\\]", "]")

        try:
            _width = os.get_terminal_size().columns
        except OSError:
            _width = 100

        _done_ev = threading.Event()

        _is_prog_repl = name in (
            "code_search", "grep_code", "grep_file", "multi_grep",
            "symbol_lookup", "semantic_search",
        )
        if _is_prog_repl:
            _tool_progress.set_progress_callback(
                lambda _f, _s=self: setattr(_s, "_tool_current_file", _f)
            )
        self._tool_current_file = ""

        def _anim_thread():
            fi = 0
            bold  = _ANSI_BOLD
            reset = _ANSI_RESET
            while not _done_ev.wait(timeout=0.12):
                col    = _HEADER_ANIM_CODES[fi % len(_HEADER_ANIM_CODES)]
                _cf    = self._tool_current_file
                _sf    = ("  ⎿ " + _cf.rsplit("/", 1)[-1][:28]) if _cf else ""
                line   = f"  {col}{bold}◐{reset} {bold}{display}{reset}{ctx_plain}{_sf}"
                pad    = max(0, _width - len(line))
                sys.stdout.write(f"\r{line}{' ' * pad}")
                sys.stdout.flush()
                fi += 1

        _anim_t = threading.Thread(
            target=_anim_thread, daemon=True, name=f"oocode-hdr-{name[:8]}"
        )
        _anim_t.start()

        result = self._execute_tool(name, args)

        _done_ev.set()
        _anim_t.join(timeout=0.5)
        if _is_prog_repl:
            _tool_progress.set_progress_callback(None)
        self._tool_current_file = ""

        # Limpiar línea animada y mostrar header definitivo en blanco
        sys.stdout.write(f"\r{' ' * _width}\r")
        sys.stdout.flush()

        if is_mem_tool:
            self._print(f"  [bold white]◐[/bold white] [white]{_esc(display)}[/white][dim]{ctx}[/dim]")
        else:
            self._print(f"  [white]◐[/white] [bold white]{_esc(display)}[/bold white][dim]{ctx}[/dim]")

        return result

    def _show_tool_running_header(self, name: str, args: dict) -> None:
        """Imprime el header de tool ANTES de ejecutarla.

        Modo REPL (sin _status_cb): muestra ◐ verde; el bloque de resultado lo actualiza.
        Modo TUI (con _status_cb): muestra ● verde para write/replace tools solamente,
          con ◐ parpadeante para que el usuario sepa que está ejecutando.
          Las herramientas de lectura/bash no muestran header previo (aparecen en ⎿ al final).
        """
        if self.capture_output:
            return
        from rich.markup import escape as _esc
        display = self._TOOL_DISPLAY_NAMES.get(name, name)
        ctx     = self._call_context(name, args)
        is_mem_tool = name in self._MEM_TOOLS

        if self._status_cb is not None and not self.is_subagent:
            # TUI mode: sólo write/replace/mem muestran ◐ en la conversación.
            # El resto se bufferiza en _turn_block para resumen agrupado al final.
            _is_write = (name in ("write_file", "edit_file", "edit_files")
                         or (name.startswith("mcp_") and any(
                             name.endswith(s) for s in ("_write_file", "_edit_file", "_edit_files"))))
            _is_replace = (name in ("regex_replace", "smart_replace", "bulk_replace", "patch_apply")
                           or any(name.endswith(s) for s in
                                  ("_regex_replace", "_smart_replace", "_bulk_replace", "_patch_apply")))
            if _is_write or _is_replace:
                self._print(
                    f"  [bold green]◐[/bold green] [bold]{_esc(display)}[/bold][dim]{ctx}[/dim]"
                )
                self._turn_block_has_header = True
            elif is_mem_tool:
                self._print(
                    f"  [bold cyan]◐[/bold cyan] [bold cyan]{_esc(display)}[/bold cyan][dim]{ctx}[/dim]"
                )
            # Para todas las demás tools: sin ◐ en conversación — el status bar ya muestra el progreso
            return

        if is_mem_tool:
            self._print(f"  [bold cyan]◐[/bold cyan] [bold cyan]{_esc(display)}[/bold cyan][dim]{ctx}[/dim]")
        else:
            self._print(f"  [bold green]◐[/bold green] [bold]{_esc(display)}[/bold][dim]{ctx}[/dim]")

    def _show_usage(self, inp: int, out: int) -> None:
        """Guarda la línea de uso en _pending_usage_line para mostrarla una sola vez antes del prompt."""
        if self.capture_output or self.rt.usage_display == "off":
            return
        if self._status_cb is not None:
            return  # En App mode las stats ya están en la fila de estado

        ctx_stats  = self.context.stats()
        ctx_tok    = ctx_stats["tokens_estimate"]
        max_tok    = ctx_stats["max_tokens"]
        ctx_pct    = int(ctx_tok / max(max_tok, 1) * 100)
        thresh_pct = int(self.context.compact_threshold * 100)
        bar        = _ctx_bar(ctx_tok, max_tok, 10)
        elapsed    = f"  {self._last_elapsed:.1f}s" if self._last_elapsed > 0 else ""

        if ctx_pct >= thresh_pct:
            compact_hint = "  [bold yellow]⚠ compactando[/bold yellow]"
        elif ctx_pct >= thresh_pct - 10:
            compact_hint = "  [yellow]↻[/yellow] [bold #ff7700]cerca compactación[/bold #ff7700]"
        else:
            compact_hint = ""

        if self.rt.usage_display == "tokens":
            self._pending_usage_line = (
                f"  [dim]↳ {_fmt_tokens(inp)}↑ {_fmt_tokens(out)}↓{elapsed}  │  "
                f"ctx: {bar} {ctx_pct}%{compact_hint}[/dim]"
            )
        elif self.rt.usage_display == "full":
            total = self.session.input_tokens + self.session.output_tokens
            line1 = (
                f"  [dim]↳ turno: {_fmt_tokens(inp)}↑ {_fmt_tokens(out)}↓  "
                f"│  sesión: {_fmt_tokens(self.session.input_tokens)}↑"
                f" {_fmt_tokens(self.session.output_tokens)}↓  "
                f"│  total: {_fmt_tokens(total)}{elapsed}[/dim]"
            )
            line2 = (
                f"  [dim]   ctx: {bar} {ctx_tok}/{max_tok} ({ctx_pct}%)"
                f"{'  📝' if ctx_stats['has_summary'] else ''}{compact_hint}[/dim]"
            )
            self._pending_usage_line = f"{line1}\n{line2}"

    def _trace_header(self, messages: list) -> None:
        if self.capture_output or not self.rt.trace:
            return
        sys_len = (
            len(messages[0].get("content", ""))
            if messages and messages[0].get("role") == "system"
            else 0
        )
        ctx = self.context.stats()
        self._print(
            f"  [dim]trace: {len(messages)} msgs  |  "
            f"system {sys_len} chars (~{sys_len // 4} tok)  |  "
            f"ctx ~{ctx['tokens_estimate']} tok  |  "
            f"modelo {self._active_model()}[/dim]"
        )

    # ── Capacidades del modelo ───────────────────────────────────────────────

    def _model_supports_images(self) -> bool:
        """True si el modelo activo declara soporte de imágenes en su config."""
        return "image" in self.config.active_model_input_types

    # ── Opciones del modelo ──────────────────────────────────────────────────

    def _build_options(self) -> dict:
        """Parámetros para Ollama: per-modelo + overrides globales de modelOptions.

        Filtra keep_alive: es un parámetro top-level de la API de Ollama, no una
        option del runner. Ollama mantiene el modelo cargado automáticamente.
        """
        opts = self.config.effective_model_params()
        opts.pop("keep_alive", None)
        return opts

    def _chat_kwargs(self, opts: dict) -> dict:
        """Construye kwargs para client.chat().

        Filtra claves que Ollama rechaza dentro de options:
        - keep_alive: parámetro top-level de la API, no una option del runner.
          Ollama mantiene el modelo cargado por defecto; no hace falta enviarlo.
        """
        if not opts:
            return {}
        opts = dict(opts)
        opts.pop("keep_alive", None)
        return {"options": opts} if opts else {}

    # ── LLM call ─────────────────────────────────────────────────────────────

    def _stream_response(self, messages: list, tools: list) -> tuple[str, list, int, int]:
        opts = self._build_options()

        # Subagentes y modo captura: stream=False, sin spinner (evita Live en TUI)
        if self.capture_output or self.is_subagent:
            fb_timeout = self.config.model_timeout(self._active_model())
            try:
                if fb_timeout > 0:
                    from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutureTimeout
                    _model = self._active_model()
                    _kwargs = self._chat_kwargs(opts)
                    with ThreadPoolExecutor(max_workers=1) as _ex:
                        _fut = _ex.submit(
                            self.client.chat,
                            model=_model, messages=messages, tools=tools,
                            stream=False, **_kwargs,
                        )
                        try:
                            resp = _fut.result(timeout=fb_timeout)
                        except _FutureTimeout:
                            self._last_elapsed = fb_timeout * 1.0
                            return _TIMEOUT_SENTINEL, [], 0, 0
                else:
                    resp = self.client.chat(
                        model=self._active_model(),
                        messages=messages,
                        tools=tools,
                        stream=False,
                        **self._chat_kwargs(opts),
                    )
                msg = resp.message
                return (
                    msg.content or "",
                    msg.tool_calls or [],
                    getattr(resp, "prompt_eval_count", 0) or 0,
                    getattr(resp, "eval_count", 0) or 0,
                )
            except Exception as e:
                return f"Error: {e}", [], 0, 0

        # Modo display (agente principal): streaming para tokens en tiempo real
        from agent.runtime import COLOR_PRESETS
        rich_col      = COLOR_PRESETS.get(self.rt.accent_color, COLOR_PRESETS["cyan"])[1]
        t_start       = time.time()
        fi            = 0
        # Elegir vocabulario según si hay plan activo (multitarea) o no (single)
        _has_active_plan = any(
            t.get("status") == "active"
            for t in getattr(self, "_plan_tasks", [])
        )
        thinking_word = (random.choice(_MULTITASK_WORDS) if _has_active_plan
                         else random.choice(_THINKING_WORDS))

        text_parts:        list[str] = []
        tool_calls_result: list      = []
        inp_tokens = 0
        out_tokens = 0
        error      = None

        try:
            stream = self.client.chat(
                model=self._active_model(),
                messages=messages,
                tools=tools,
                stream=True,
                **self._chat_kwargs(opts),
            )

            if self._status_cb:
                # App mode: streaming en hilo de fondo para evitar CPU al 100%
                # El hilo bg hace el loop tight sobre el socket; el hilo principal
                # lee _out_chars_sh cada 200ms para actualizar la barra de estado.
                _out_chars_sh: list = [0]    # chars de texto acumulados (GIL suficiente)
                _tc_result:    list = [[]]   # tool_calls del último chunk con tool_calls
                _err_sh:       list = [None]
                _inp_sh:       list = [0]
                _out_sh:       list = [0]
                _done_ev = threading.Event()

                def _stream_bg() -> None:
                    try:
                        for chunk in stream:
                            msg = chunk.message
                            if msg.thinking:
                                _out_chars_sh[0] += len(msg.thinking)
                            if msg.content:
                                text_parts.append(msg.content)
                                _out_chars_sh[0] += len(msg.content)
                            if msg.tool_calls:
                                _tc_result[0] = list(msg.tool_calls)
                                # Contar JSON de tool_calls para que ↓ no muestre siempre "…"
                                try:
                                    _out_chars_sh[0] += sum(
                                        len(json.dumps(
                                            getattr(tc.function, "arguments", {})
                                            if hasattr(tc, "function") else {}
                                        ))
                                        for tc in msg.tool_calls
                                    )
                                except Exception:
                                    pass
                            if chunk.done:
                                _inp_sh[0] = getattr(chunk, "prompt_eval_count", 0) or 0
                                _out_sh[0] = getattr(chunk, "eval_count", 0) or 0
                                # Usar eval_count como fallback si no se generó texto
                                if _out_chars_sh[0] == 0 and _out_sh[0] > 0:
                                    _out_chars_sh[0] = _out_sh[0] * 4
                                break
                    except Exception as exc:
                        _err_sh[0] = exc
                    finally:
                        _done_ev.set()

                threading.Thread(target=_stream_bg, daemon=True, name="oocode-stream").start()

                fb_timeout   = self.config.model_timeout(self._active_model())
                _timeout_hit = False

                # Spinner a 200ms — no tight loop
                while not _done_ev.wait(timeout=_POLL_INTERVAL):
                    elapsed    = time.time() - t_start
                    frame      = _SPINNER_FRAMES[fi % len(_SPINNER_FRAMES)]
                    think_circ = _SPINNER_FRAMES[fi % len(_SPINNER_FRAMES)]
                    ctx_s      = self.context.stats()
                    cpct       = int(ctx_s["tokens_estimate"] / max(ctx_s["max_tokens"], 1) * 100)
                    plain_bar  = _ctx_bar(ctx_s["tokens_estimate"], ctx_s["max_tokens"], 10, plain=True)
                    thresh_pct = int(getattr(self.context, "compact_threshold", 0.85) * 100)
                    hint       = _compact_hint(cpct, thresh_pct)
                    approx_out = _out_chars_sh[0] // 4
                    out_str    = f"~{_fmt_tokens(approx_out)}" if approx_out > 0 else "…"
                    if self._turn_inp > 0:
                        tok_part = f"{_fmt_tokens(self._turn_inp)}↑ {out_str}↓  ·  "
                    else:
                        tok_part = f"{out_str}↓  ·  "
                    _time_str = _fmt_elapsed(elapsed)
                    if elapsed > 25:
                        _phrase = _NEAR_FINISH_PHRASES[(fi // 5) % len(_NEAR_FINISH_PHRASES)]
                        _time_part = f"({_time_str} · {_phrase})"
                    else:
                        _time_part = f"({_time_str})"
                    mem_part = f"  ·  ⬡ {self.memory.last_hits} mem" if self.memory.last_hits > 0 else ""
                    rag_part = _rag_display(self._workspace_rag)
                    # Spinner: modo multitarea (◈ + tarea) vs modo single (palabra pensando)
                    _active_task_txt = ""
                    _plan_tasks_s    = getattr(self, "_plan_tasks", [])
                    _plan_total      = len(_plan_tasks_s)
                    _plan_done       = sum(1 for t in _plan_tasks_s if t["status"] == "done")
                    for _pt in _plan_tasks_s:
                        if _pt["status"] == "active":
                            _active_task_txt = _pt["text"]
                            break
                    if _active_task_txt:
                        _tlabel = _active_task_txt[:38].rstrip()
                        if len(_active_task_txt) > 38:
                            _tlabel += "…"
                        # Modo multitarea: ◈ + progreso N/M + tarea activa + tiempo
                        _tok_up = f"↑{_fmt_tokens(self._turn_inp)}" if self._turn_inp > 0 else ""
                        _tok_dn = f"↓~{_fmt_tokens(approx_out)}" if approx_out > 0 else ""
                        _tok_inline = "  ·  " + "  ".join(filter(None, [_tok_up, _tok_dn])) if (_tok_up or _tok_dn) else ""
                        _prog = f"[{_plan_done + 1}/{_plan_total}]" if _plan_total > 1 else ""
                        line1 = f"{frame}  ◈ multitarea {_prog}  {_tlabel}  ({_time_str}{_tok_inline})"
                        line2 = ""  # task list se renderiza desde _plan_tasks en _get_status_text
                        self._sep_label = f"{frame} {_tlabel}"
                    else:
                        _display_word = f"{thinking_word}…"
                        # Colorear la palabra de pensamiento y la frase near-finish
                        if elapsed > 25:
                            _phrase = _NEAR_FINISH_PHRASES[(fi // 5) % len(_NEAR_FINISH_PHRASES)]
                            _tp_col = (
                                _sfmt("time-dim", f"({_time_str} · ")
                                + _sfmt("status-phrase", _phrase)
                                + _sfmt("time-dim", ")")
                            )
                        else:
                            _tp_col = _sfmt("time-dim", f"({_time_str})")
                        line1 = (
                            f"{frame}  "
                            + _sfmt("status-word", _display_word)
                            + f"  {_tp_col}"
                        )
                        # Colorear barra de contexto e hint según nivel de llenado
                        _bstyle = _bar_style(cpct, thresh_pct)
                        _cbar = _sfmt(_bstyle, plain_bar)
                        _chint = _hint_styled(cpct, thresh_pct)
                        line2 = f"↳  {tok_part}ctx: {_cbar} {cpct}%{_chint}{mem_part}{rag_part}"
                        self._sep_label = f"{think_circ} {_display_word}"
                    self._status_cb(f"{line1}\n{line2}")
                    fi += 1

                    # Timeout → señalizar para usar fallback
                    if fb_timeout > 0 and elapsed >= fb_timeout and _out_chars_sh[0] < _FALLBACK_MIN_CHARS:
                        _timeout_hit = True
                        break

                if _timeout_hit:
                    self._last_elapsed = time.time() - t_start
                    self._status_cb("")
                    return _TIMEOUT_SENTINEL, [], 0, 0

                if _err_sh[0] is not None:
                    error = _err_sh[0]
                else:
                    tool_calls_result = _tc_result[0]
                    inp_tokens = _inp_sh[0]
                    out_tokens = _out_sh[0]
            else:
                # REPL clásico: Live de Rich (con soporte timeout si fallback configurado)
                fb_timeout_r  = self.config.model_timeout(self._active_model())
                _timeout_hit_r = False

                if fb_timeout_r > 0:
                    # Background thread para poder detectar timeout incluso sin chunks
                    _out_chars_r: list = [0]
                    _tc_r:        list = [[]]
                    _err_r:       list = [None]
                    _inp_r:       list = [0]
                    _out_r:       list = [0]
                    _done_r = threading.Event()

                    def _stream_bg_repl() -> None:
                        try:
                            for chunk in stream:
                                msg = chunk.message
                                if msg.thinking:
                                    _out_chars_r[0] += len(msg.thinking)
                                if msg.content:
                                    text_parts.append(msg.content)
                                    _out_chars_r[0] += len(msg.content)
                                if msg.tool_calls:
                                    _tc_r[0] = list(msg.tool_calls)
                                    try:
                                        _out_chars_r[0] += sum(
                                            len(json.dumps(
                                                getattr(tc.function, "arguments", {})
                                                if hasattr(tc, "function") else {}
                                            ))
                                            for tc in msg.tool_calls
                                        )
                                    except Exception:
                                        pass
                                if chunk.done:
                                    _inp_r[0] = getattr(chunk, "prompt_eval_count", 0) or 0
                                    _out_r[0] = getattr(chunk, "eval_count", 0) or 0
                                    if _out_chars_r[0] == 0 and _out_r[0] > 0:
                                        _out_chars_r[0] = _out_r[0] * 4
                                    break
                        except Exception as exc:
                            _err_r[0] = exc
                        finally:
                            _done_r.set()

                    threading.Thread(target=_stream_bg_repl, daemon=True, name="oocode-repl-bg").start()

                    with Live(console=console, refresh_per_second=5, transient=True) as live:
                        while not _done_r.wait(timeout=_POLL_INTERVAL):
                            elapsed = time.time() - t_start
                            frame   = _SPINNER_FRAMES[fi % len(_SPINNER_FRAMES)]
                            txt = Text()
                            txt.append(f"  {frame}  ", style=f"bold {rich_col}")
                            if _has_active_plan:
                                txt.append("◈ multitarea  ", style="dim cyan")
                            txt.append(f"{thinking_word}…  ", style="dim italic")
                            _time_str_r = _fmt_elapsed(elapsed)
                            if elapsed > 25:
                                _phrase_r = _NEAR_FINISH_PHRASES[(fi // 5) % len(_NEAR_FINISH_PHRASES)]
                                txt.append(f"({_time_str_r} · {_phrase_r})", style="dim")
                            else:
                                txt.append(f"({_time_str_r})", style="dim")
                            live.update(txt)
                            fi += 1
                            if elapsed >= fb_timeout_r and _out_chars_r[0] < _FALLBACK_MIN_CHARS:
                                _timeout_hit_r = True
                                break

                    if _timeout_hit_r:
                        self._last_elapsed = time.time() - t_start
                        return _TIMEOUT_SENTINEL, [], 0, 0
                    if _err_r[0] is not None:
                        error = _err_r[0]
                    else:
                        tool_calls_result = _tc_r[0]
                        inp_tokens = _inp_r[0]
                        out_tokens = _out_r[0]
                else:
                    # Sin fallback: comportamiento original
                    with Live(console=console, refresh_per_second=5, transient=True) as live:
                        for chunk in stream:
                            msg = chunk.message
                            if msg.content:
                                text_parts.append(msg.content)
                            if msg.tool_calls:
                                tool_calls_result = msg.tool_calls
                            if chunk.done:
                                inp_tokens = getattr(chunk, "prompt_eval_count", 0) or 0
                                out_tokens = getattr(chunk, "eval_count", 0) or 0
                                break
                            elapsed = time.time() - t_start
                            frame   = _SPINNER_FRAMES[fi % len(_SPINNER_FRAMES)]
                            txt = Text()
                            txt.append(f"  {frame}  ", style=f"bold {rich_col}")
                            if _has_active_plan:
                                txt.append("◈ multitarea  ", style="dim cyan")
                            txt.append(f"{thinking_word}…  ", style="dim italic")
                            _time_str_nf = _fmt_elapsed(elapsed)
                            if elapsed > 25:
                                _phrase_nf = _NEAR_FINISH_PHRASES[(fi // 5) % len(_NEAR_FINISH_PHRASES)]
                                txt.append(f"({_time_str_nf} · {_phrase_nf})", style="dim")
                            else:
                                txt.append(f"({_time_str_nf})", style="dim")
                            live.update(txt)
                            fi += 1

        except Exception as exc:
            error = exc

        self._last_elapsed = time.time() - t_start
        self._sep_label    = ""

        if error:
            if self._status_cb:
                self._status_cb("")
            error_str = str(error)
            log.error("llm_error", model=self._active_model(), error=error_str)

            # Errores de parsing XML: el modelo generó tool calls en formato XML
            # en lugar de JSON nativo. Ollama devuelve status_code=-1 con
            # "XML syntax error" cuando el XML está malformado o truncado.
            _is_xml = (
                "XML syntax error" in error_str
                or "xml" in error_str.lower()
                or (hasattr(error, "status_code") and error.status_code == -1
                    and "syntax error" in error_str.lower())
            )

            # "unexpected EOF" = XML truncado por límite de tokens (≠ XML malformado).
            # Ocurre cuando thinking consume demasiados tokens y el XML del tool call
            # queda cortado antes de cerrarse. Auto-retry con /no_think.
            _is_eof_truncation = _is_xml and "unexpected EOF" in error_str

            if _is_eof_truncation:
                log.warn("xml_eof_truncation_retry", model=self._active_model(),
                         think_level=getattr(self.rt, "think_level", "off"))
                if not self.capture_output:
                    console.print(
                        "\n  [yellow]⚡[/yellow]  Thinking agotó el presupuesto de tokens "
                        "— XML de tool call truncado. Reintentando sin thinking…\n"
                    )
                # Añadir /no_think al último mensaje de usuario para que qwen3 desactive
                # su bloque <think> solo en esta llamada (no cambia rt.think_level)
                retry_messages = list(messages)
                for _i in range(len(retry_messages) - 1, -1, -1):
                    if retry_messages[_i].get("role") == "user":
                        _m = retry_messages[_i]
                        _content = (_m.get("content") or "")
                        if isinstance(_content, str):
                            retry_messages = (
                                list(retry_messages[:_i])
                                + [{**_m, "content": _content + " /no_think"}]
                                + list(retry_messages[_i + 1:])
                            )
                        break
                try:
                    resp = self.client.chat(
                        model=self._active_model(),
                        messages=retry_messages,
                        tools=tools,
                        stream=False,
                        **self._chat_kwargs(opts),
                    )
                    _rm = resp.message
                    return (
                        _rm.content or "",
                        _rm.tool_calls or [],
                        getattr(resp, "prompt_eval_count", 0) or 0,
                        getattr(resp, "eval_count", 0) or 0,
                    )
                except Exception as _retry_exc:
                    log.warn("xml_eof_retry_failed", error=str(_retry_exc))
                    # Caer al mensaje de error original

            # Intentar recuperar texto parcial generado antes del error
            partial = "".join(text_parts)
            if partial and _is_xml:
                log.warn("xml_tool_call_recovered", chars=len(partial),
                         model=self._active_model())
                console.print(
                    "\n  [yellow]⚠[/yellow]  El modelo intentó llamar a una herramienta "
                    "en formato XML en vez de JSON — Ollama no pudo procesarlo. "
                    "Respuesta parcial recuperada. Puedes repetir la pregunta si la "
                    "respuesta está incompleta.\n"
                )
                return partial, [], inp_tokens, out_tokens

            # Error de red/conexión real o XML malformado sin texto previo
            if _is_xml:
                if _is_eof_truncation:
                    msg = (
                        "El modelo truncó los tool calls XML al agotar tokens de thinking "
                        "y el retry también falló. Usa /think off o reduce el contexto."
                    )
                else:
                    msg = (
                        "El modelo generó tool calls en formato XML no válido "
                        "(bug conocido de qwen3/deepseek). Repite la pregunta o "
                        "usa /think off para reducir la complejidad de la respuesta."
                    )
            else:
                msg = f"Error conectando con Ollama: {error_str}"
            return msg, [], 0, 0

        text = "".join(text_parts)

        if self._status_cb:
            self._status_cb("")
        else:
            ctx     = self.context.stats()
            cpct    = int(ctx["tokens_estimate"] / max(ctx["max_tokens"], 1) * 100)
            bar     = _ctx_bar(ctx["tokens_estimate"], ctx["max_tokens"], 10)
            tok_str = (f"  [dim]│  {_fmt_tokens(inp_tokens)}↑ {_fmt_tokens(out_tokens)}↓[/dim]"
                       if (inp_tokens or out_tokens) else "")
            self._print(
                f"  [bold {rich_col}]✓[/bold {rich_col}]  "
                f"[dim]{self._last_elapsed:.1f}s[/dim]"
                f"{tok_str}"
                f"  [dim]│  {bar} {cpct}%[/dim]"
            )

        return text, tool_calls_result, inp_tokens, out_tokens

    # ── Compactación inteligente ──────────────────────────────────────────────

    def _summarize_messages(self, messages: list[dict]) -> str:
        """
        Llama al LLM para resumir mensajes eliminados.
        El resumen se inyecta en el system prompt para no perder contexto.
        """
        if not messages:
            return ""
        # Serializa solo user/assistant/tool (sin system) para el prompt de resumen
        lines = []
        for m in messages:
            role = m.get("role", "")
            content = str(m.get("content") or "")
            if role == "user":
                lines.append(f"Usuario: {content[:300]}")
            elif role == "assistant":
                lines.append(f"Asistente: {content[:300]}")
            elif role == "tool":
                lines.append(f"Tool({m.get('name', '')}): {content[:200]}")
        if not lines:
            return ""

        # Incluir estado del plan activo en el prompt para que el resumen lo preserve
        _plan_section = ""
        _active_plan = getattr(self, "_plan_tasks", [])
        if _active_plan and not self._all_plan_tasks_done():
            _ai_sum = next((i for i, t in enumerate(_active_plan) if t["status"] == "active"), -1)
            _total_sum = len(_active_plan)
            _done_sum  = sum(1 for t in _active_plan if t["status"] == "done")
            _task_sum  = "\n".join(
                f"  {'✔' if t['status'] == 'done' else '◼ ACTIVA' if t['status'] == 'active' else '◻'}"
                f" {i + 1}/{_total_sum}: {t['text']}"
                for i, t in enumerate(_active_plan)
            )
            _active_text = _active_plan[_ai_sum]["text"] if _ai_sum >= 0 else "?"
            _plan_section = (
                f"\n\n**IMPORTANTE — Plan de tareas activo al compactar:**\n"
                f"Progreso: {_done_sum}/{_total_sum} tareas completadas.\n"
                f"Tarea activa: \"{_active_text}\" [{_done_sum + 1}/{_total_sum}].\n"
                f"Estado completo:\n{_task_sum}\n"
                f"El resumen DEBE incluir este estado para que el agente pueda continuar tras compactación.\n"
            )

        # Estado estructurado: ficheros modificados y tests para preservar en el resumen
        _ckpt_modified = getattr(self, "_task_modified_files", set())
        _ckpt_test = getattr(self, "_task_last_test", "")
        _state_section = ""
        if _ckpt_modified or _ckpt_test:
            _mod_list = ", ".join(sorted(_ckpt_modified)[:10]) if _ckpt_modified else "ninguno"
            _test_line = f"\n- Último resultado de tests: {_ckpt_test[:300]}" if _ckpt_test else ""
            _state_section = (
                f"\n\n**Estado de tarea al compactar:**\n"
                f"- Ficheros modificados en esta tarea: {_mod_list}{_test_line}\n"
                f"El resumen DEBE incluir esta lista para que el agente sepa qué ya modificó.\n"
            )

        prompt_text = (
            "Resume en bullets concisos (en español) los puntos clave de esta conversación previa.\n"
            "IMPORTANTE: Si el usuario ha dado instrucciones especiales (estilo de código, preferencias, "
            "restricciones, 'recuerda que...', 'siempre haz X'), inclúyelas EXPLÍCITAMENTE en el resumen "
            "bajo el encabezado '**Instrucciones del usuario:**'.\n"
            "Solo hechos relevantes para continuar la tarea. Máximo 6 bullets:\n\n"
            + "\n".join(lines)
            + _plan_section
            + _state_section
        )
        try:
            opts = self._build_options()
            resp = self.client.chat(
                model=self._active_model(),
                messages=[{"role": "user", "content": prompt_text}],
                stream=False,
                **self._chat_kwargs(opts),
            )
            summary = resp.message.content or ""
            if summary:
                # Escribe en memoria diaria como checkpoint
                self.ws.write_daily_memory(
                    f"\n### Checkpoint de compactación\n{summary}\n"
                )
            return summary
        except Exception:
            return ""

    def _show_compact_reset(self, dropped: int, freed_tok: int, has_summary: bool) -> None:
        """Reset visual al estilo Claude Code tras compactación automática.

        1. Limpia el área visible (sin borrar el scroll buffer del terminal).
        2. Muestra el mini banner de OOCode (3 líneas).
        3. Muestra el aviso «Conversación compactada».
        4. Lista los ficheros leídos/editados durante la sesión compactada.
        """
        from ui.console import console as _con
        from ui.renderer import print_compact_banner

        # ── Paso 1: limpiar área visible ─────────────────────────────────────
        if self._clear_output_cb is not None:
            self._clear_output_cb()          # TUI: vacía _output_parts
        else:
            import sys as _sys
            # ESC[H = cursor inicio · ESC[2J = borrar pantalla visible (scroll buffer intacto)
            _sys.stdout.write("\033[H\033[2J")
            _sys.stdout.flush()

        # ── Paso 2: mini banner ───────────────────────────────────────────────
        print_compact_banner(self.config)

        # ── Paso 3: aviso de compactación ────────────────────────────────────
        _con.print(
            "  [bold]✻[/bold]  "
            "[dim]Conversación compactada[/dim]"
            "  [dim](ctrl+o para ver historial)[/dim]"
        )
        if has_summary:
            _con.print("  [dim]  ↻ resumen LLM preservado en contexto[/dim]")
        _con.print()

        # ── Paso 4: referencias de ficheros y memorias ────────────────────────
        ws = str(self.config.workspace or "")

        if self._session_reads:
            seen: dict[str, tuple] = {}
            for path, n_lines, is_edit in self._session_reads:
                seen[path] = (n_lines, is_edit)

            for path, (n_lines, is_edit) in list(seen.items())[-15:]:
                rel = path[len(ws):].lstrip("/") if (ws and path.startswith(ws)) else path
                if is_edit:
                    _con.print(f"  [dim]⎿  Updated {rel}[/dim]")
                elif n_lines is not None:
                    _con.print(f"  [dim]⎿  Read {rel} ({n_lines} líneas)[/dim]")
                else:
                    _con.print(f"  [dim]⎿  Referenciado {rel}[/dim]")

        if self._session_mems:
            seen_mems = list(dict.fromkeys(self._session_mems))  # deduplica preservando orden
            for mname in seen_mems[-5:]:
                _con.print(f"  [dim]⎿  Memory saved: {mname}[/dim]")

        if self._session_reads or self._session_mems:
            _con.print()

        self._session_reads = []
        self._session_mems  = []

        # Mostrar tarea que se reanuda — el LLM puede tardar minutos antes de emitir texto
        if getattr(self, "_plan_tasks", None) and not self._all_plan_tasks_done():
            _ai_idx = next(
                (i for i, t in enumerate(self._plan_tasks) if t["status"] == "active"), -1
            )
            _total  = len(self._plan_tasks)
            _done_n = sum(1 for t in self._plan_tasks if t["status"] == "done")
            if _ai_idx >= 0:
                _task_txt = self._plan_tasks[_ai_idx]["text"][:70]
                _con.print(
                    f"  [dim yellow]↻[/dim yellow]  "
                    f"[dim]Reanudando tarea {_ai_idx + 1}/{_total}"
                    f" ({_done_n} completadas): \"{_task_txt}\"...[/dim]"
                )
            else:
                _con.print(
                    f"  [dim yellow]↻[/dim yellow]  "
                    f"[dim]Reanudando plan ({_done_n}/{_total} completadas)...[/dim]"
                )
            _con.print()

    def _do_compact(self, with_summary: bool = True) -> int:
        """Compacta el contexto con barra de progreso. Devuelve msgs eliminados."""
        dropped_count = self._do_compact_impl(with_summary)
        if dropped_count > 0 and getattr(self.config, "snapshots_save_on_compact", False):
            self._save_session_snapshot()
        return dropped_count

    def _do_compact_impl(self, with_summary: bool = True) -> int:
        """Implementación real de compactación — llamada desde _do_compact."""
        if self.capture_output:
            summarize_fn = self._summarize_messages if with_summary else None
            dropped = self.context.compact(summarize_fn=summarize_fn)
            if dropped:
                self.session.log_compaction(len(dropped))
            return len(dropped)

        # Subagente dentro de la TUI: Rich Progress escribe \x1b[?25l al buffer
        # y aparece como "25l" literal. Usar ruta simple sin widgets de progreso.
        if self.is_subagent:
            ctx     = self.context
            n_msgs  = len(ctx.messages)
            cur_tok = ctx.token_estimate()
            self._print(
                f"\n  [bold yellow]↻[/bold yellow]  "
                f"[bold white]Compactando[/bold white]  "
                f"[cyan]{n_msgs} msgs · ~{cur_tok:,} tok[/cyan]"
            )
            summarize_fn = self._summarize_messages if with_summary else None
            dropped = ctx.compact(summarize_fn=summarize_fn)
            if dropped:
                self.session.log_compaction(len(dropped))
                new_tok = ctx.token_estimate()
                self._print(
                    f"  [bold green]✓[/bold green]  "
                    f"[green]{len(dropped)} msgs eliminados · ~{cur_tok - new_tok:,} tok liberados[/green]\n"
                )
            return len(dropped)

        # En modo TUI: barra de progreso en el status window (status_cb),
        # cabecera y resultado van a la conversación.
        if self._status_cb is not None:
            from ui.console import console as _con

            # Cerrar live block abierto antes de la animación de compactación
            if self._flush_live_block_cb:
                self._flush_live_block_cb("")
            # Suprimir task panel durante compactación + señalizar a run() que espere
            self._compacting_ctx = True
            self._compact_running.set()
            try:
                ctx      = self.context
                n_msgs   = len(ctx.messages)
                cur_tok  = ctx.token_estimate()
                max_tok  = ctx.max_tokens
                cur_pct  = int(cur_tok / max(max_tok, 1) * 100)

                # ── Cabecera + progreso en el status window (con colores) ──
                _hdr = (
                    _sfmt("compact-arrow", "↻") + "  "
                    + _sfmt("compact-title", "Compactando") + "  "
                    + _sfmt("compact-dim", f"{n_msgs} msgs · ~{cur_tok:,} tok · {cur_pct}%")
                )
                self._status_cb(
                    f"{_hdr}\n"
                    f"○  {_sfmt('compact-bar', _pbar_thin_ratio(0.0))}"
                    f"   {_sfmt('compact-pct', '0%')}  "
                    + _sfmt("compact-phrase", "analizando mensajes…")
                )

                # ── Fase 2 (opcional): resumen LLM con animación ─────────────
                summarize_fn = None
                if with_summary:
                    def _cb_summarize(msgs: list[dict]) -> str:
                        import threading as _th
                        _result: list = [None]
                        _done_ev = _th.Event()

                        def _bg() -> None:
                            _result[0] = self._summarize_messages(msgs)
                            _done_ev.set()

                        _th.Thread(target=_bg, daemon=True).start()

                        step = 0
                        _fi_cmp = 0
                        while not _done_ev.wait(timeout=0.4):
                            step    += 1
                            _fi_cmp += 1
                            ratio = 1.0 - 1.0 / (1 + step * 0.12)
                            ratio = min(ratio, 0.95)
                            pct   = int(ratio * 100)
                            _frame_cmp = _SPINNER_FRAMES[_fi_cmp % len(_SPINNER_FRAMES)]
                            self._status_cb(
                                f"{_hdr}\n{_frame_cmp}  "
                                + _sfmt("compact-bar", _pbar_thin_ratio(ratio))
                                + f"  {_sfmt('compact-pct', f'{pct:3d}%')}  "
                                + _sfmt("compact-phrase", f"resumiendo {len(msgs)} msgs…")
                            )
                        return _result[0] or ""

                    summarize_fn = _cb_summarize

                dropped = ctx.compact(summarize_fn=summarize_fn)
                self._status_cb("")  # Limpia status

                if dropped:
                    self.session.log_compaction(len(dropped))
                    new_tok = ctx.token_estimate()
                    freed   = cur_tok - new_tok
                    has_sum = bool(ctx.summary)
                    self._show_compact_reset(len(dropped), freed, has_sum)
                else:
                    _con.print("  [dim]sin cambios — umbral no alcanzado[/dim]")
                return len(dropped)
            finally:
                self._compacting_ctx = False
                self._compact_running.clear()

        from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn

        ctx     = self.context
        n_msgs  = len(ctx.messages)
        cur_tok = ctx.token_estimate()
        max_tok = ctx.max_tokens
        cur_pct = int(cur_tok / max(max_tok, 1) * 100)
        bar_pre = _ctx_bar(cur_tok, max_tok, 14)

        self._print()
        self._print(
            f"  [bold yellow]↻[/bold yellow]  [bold white]Compactando[/bold white]  "
            f"[cyan]{n_msgs} mensajes · ~{cur_tok:,} tok  {bar_pre}  [bold]{cur_pct}%[/bold][/cyan]"
        )

        dropped = []
        n_phases = 3 if with_summary else 2

        with Progress(
            SpinnerColumn("dots"),
            BarColumn(bar_width=18, complete_style="bold yellow", finished_style="bold green"),
            TextColumn("  [bold cyan]{task.description}[/bold cyan]"),
            console=console,
            transient=True,
        ) as progress:
            ptask = progress.add_task("analizando mensajes…", total=n_phases)

            summarize_fn = None
            if with_summary:
                def _wrap_summarize(msgs: list[dict]) -> str:
                    progress.update(ptask, description=f"resumiendo {len(msgs)} msgs con LLM…")
                    result = self._summarize_messages(msgs)
                    progress.advance(ptask)
                    return result
                summarize_fn = _wrap_summarize  # type: ignore[assignment]

            progress.update(ptask, description="eliminando mensajes…")
            progress.advance(ptask)
            dropped = ctx.compact(summarize_fn=summarize_fn)
            progress.advance(ptask)
            progress.update(ptask, description="completado ✓")

        if dropped:
            self.session.log_compaction(len(dropped))
            new_tok  = ctx.token_estimate()
            new_pct  = int(new_tok / max(max_tok, 1) * 100)
            bar_post = _ctx_bar(new_tok, max_tok, 14)
            freed    = cur_tok - new_tok
            has_sum  = bool(ctx.summary)
            self._print(
                f"  [bold green]✓[/bold green]  [bold white]Compactado[/bold white]  "
                f"[green]{len(dropped)} msgs eliminados · ~{freed:,} tok liberados[/green]"
            )
            self._print(
                f"  [bold yellow]{bar_post}[/bold yellow]  [bold green]{new_pct}%[/bold green]"
                f"{' [dim]· resumen guardado[/dim]' if has_sum else ''}"
            )
        else:
            self._print("  [dim]El contexto no necesita compactación todavía.[/dim]")

        return len(dropped)

    # ── Ejecución de tools con caché y deduplicación ─────────────────────────

    # Tools de memoria: display especial con ⬡ y fases de progreso
    _MEM_TOOLS = frozenset({"mem_save", "workspace_remember"})

    # Tools de solo lectura: resultado cacheable dentro del mismo turno
    _CACHEABLE_TOOLS = frozenset({
        "read_file", "read_files", "grep_code", "grep_file", "multi_grep",
        "find_file", "find_files", "find_dir", "ls_dir", "file_stat",
        "symbol_lookup", "list_symbols", "find_symbol", "extract_functions",
        "lsp_symbols", "lsp_hover", "lsp_references",
    })
    # Tools de escritura: bloquear si se llaman con los mismos args en el mismo turno
    _WRITE_TOOLS = frozenset({
        "edit_file", "edit_files", "write_file", "regex_replace", "bulk_replace",
        "patch_apply", "lsp_rename", "lsp_code_actions",
    })

    # Patrón para detectar scripts temporales creados por el LLM en lugar de usar tools
    _TEMP_SCRIPT_RE = re.compile(
        r'(?:^|[/\\])(?:fix|improve|update|migrate|refactor|convert|patch|'
        r'temp|tmp|test_quick|script|helper|run_|do_|make_|apply_|check_|'
        r'auto|batch|mass|bulk|proceso|arreglo|cambio|tarea)[\w._-]*\.(py|sh|bash)$',
        re.I,
    )
    _BASH_HEREDOC_PY_RE  = re.compile(r'python3?\s*<<\s*[\'"]?EOF', re.I)
    _BASH_CAT_EOF_RE     = re.compile(r'\bcat\s+>\s+\S+.*<<', re.I)
    _BASH_RUN_PY_RE      = re.compile(r'python3?\s+([\w./\\-]+\.py)', re.I)
    _BASH_RUN_SH_RE      = re.compile(r'(?:^|&&|\|[|]?|;)\s*(?:bash|sh|source|\.)\s+([\w./\\-]+\.(?:sh|bash))', re.I)
    # echo/printf redirigiendo a un fichero .py/.sh (crea un script inline)
    _BASH_ECHO_SCRIPT_RE = re.compile(r'(?:echo|printf)\b.*[>]{1,2}\s*([\w./\\-]+\.(?:py|sh|bash))', re.I)
    # tee creando un fichero .py/.sh
    _BASH_TEE_SCRIPT_RE  = re.compile(r'\btee\s+([\w./\\-]+\.(?:py|sh|bash))', re.I)
    # cat leyendo un fichero (sin redirección) — usar read_file
    _BASH_CAT_READ_RE    = re.compile(
        r'^\s*cat\s+(?!>)([/~\w.\-]+\.(?:py|js|ts|c|h|cpp|hpp|rs|go|md|txt|json|yaml|yml|sh|toml|cfg|ini|env|xml|html|css|rb|php|java|kt|swift))\s*$',
        re.I,
    )
    # rm -rf sobre rutas del sistema
    _BASH_DANGEROUS_RM_RE = re.compile(
        r'\brm\s+(?:-[a-zA-Z]*[rR][a-zA-Z]*[fF][a-zA-Z]*|-[a-zA-Z]*[fF][a-zA-Z]*[rR][a-zA-Z]*)\s*(/\s*$|/\*|~/?$|~\/\*|/home\b|/etc\b|/usr\b|/var\b|/sys\b|/proc\b|/boot\b)',
        re.I,
    )
    # ls (con cualquier flag o path)  →  usar ls_dir
    _BASH_LS_RE = re.compile(r'^\s*ls\b', re.I)
    # docker exec CONTAINER CMD  →  usar docker_exec / compose_exec
    _BASH_DOCKER_EXEC_RE = re.compile(
        r'\bdocker(?:\s+compose|\s*-compose)?\s+exec\b',
        re.I,
    )
    # docker ps/logs/inspect/images/stop/rm/kill  →  usar docker_* tools
    _BASH_DOCKER_CMD_RE = re.compile(
        r'\bdocker\s+(?:ps|logs|inspect|images|stop|rm|kill|start|restart)\b',
        re.I,
    )
    # docker compose ps/up/down/logs/restart/stop/build/pull/run/config  →  compose_* tools
    _BASH_COMPOSE_CMD_RE = re.compile(
        r'\bdocker(?:\s+compose|-compose)\s+(?:ps|up|down|logs|restart|stop|build|pull|run|config|images|top|status)\b',
        re.I,
    )
    # docker cp SRC DST  →  usar docker_cp
    _BASH_DOCKER_CP_RE = re.compile(
        r'\bdocker\s+cp\b',
        re.I,
    )
    # grep -r/-rn/-l/-L/-c o --include=  →  usar grep_code / multi_grep
    _BASH_GREP_REDIRECT_RE = re.compile(
        r'\bgrep\b[^\n]*?(?:-[a-zA-Z]{0,5}[rR][a-zA-Z]{0,5}|-[a-zA-Z]{0,5}[lL][a-zA-Z]{0,3}(?!\w)|-[a-zA-Z]{0,5}[cC](?!\w)|'
        r'--recursive|--include=|--exclude=|--files-with-matches|--files-without-matches|--count)',
        re.I,
    )
    # find ... -name/-iname/-type/-newer/-mtime/-size  →  usar find_file / find_files
    _BASH_FIND_REDIRECT_RE = re.compile(
        r'\bfind\b\s+\S+\s+.*-(?:name|iname|type|newer|mtime|mmin|size|maxdepth|mindepth)\b',
        re.I,
    )
    # sed -i (edición in-place)  →  usar edit_file / regex_replace / bulk_replace
    _BASH_SED_INPLACE_RE = re.compile(
        r'\bsed\b[^\n]*(?:-[a-zA-Z]*i[a-zA-Z]*|--in-place)\b',
        re.I,
    )

    def _classify_task_groups(self, hint: str) -> frozenset:
        """Detecta grupos de tools relevantes para el mensaje actual.

        Estrategia conservadora: si no se detecta ningún grupo específico,
        se devuelven todos los grupos (modo seguro sin filtrar).
        """
        low = hint.lower() if hint else ""
        groups: set = {"core", "lsp", "memory"}
        for group, keywords in _TASK_KEYWORDS.items():
            if any(kw in low for kw in keywords):
                groups.add(group)
        # Sin keywords específicas → incluir todo (no filtrar)
        if groups == {"core", "lsp", "memory"}:
            return frozenset(_TOOL_GROUPS.keys())
        return frozenset(groups)

    def _filtered_schemas(self, hint: str = "") -> list[dict]:
        """Schemas de tools filtrados por grupos relevantes al mensaje.

        Reduce el overhead de ~11K tokens enviando solo los schemas pertinentes.
        Devuelve todos si el filtrado resulta en <20 schemas (seguridad).
        """
        all_schemas = self.registry.ollama_schemas()
        groups = self._classify_task_groups(hint)
        if groups == frozenset(_TOOL_GROUPS.keys()):
            return all_schemas
        allowed: set = set()
        for g in groups:
            allowed.update(_TOOL_GROUPS.get(g, frozenset()))
        filtered = [
            s for s in all_schemas
            if s.get("function", {}).get("name", "") in allowed
        ]
        return filtered if len(filtered) >= 20 else all_schemas

    def _bash_block(self, category: str, base_msg: str) -> str:
        """Registra un bloqueo bash y escala el mensaje si hay reintentos.

        count=1 → mensaje estándar ⛔
        count=2 → aviso fuerte ⛔⛔ (última oportunidad)
        count≥3 → parada forzada ⛔🛑 + _kill_requested=True
        """
        count = self._bash_block_counts.get(category, 0) + 1
        self._bash_block_counts[category] = count
        if count == 2:
            return (
                f"⛔⛔ [2.º INTENTO BLOQUEADO — {category}]: "
                "Esta operación bash está PERMANENTEMENTE BLOQUEADA. Usa la tool equivalente.\n"
                "⚠️  Si lo intentas una vez más el agente se detendrá automáticamente.\n\n"
                + base_msg
            )
        if count >= 3:
            self._kill_requested = True
            return (
                f"⛔🛑 [BUCLE FATAL — {count}.er INTENTO '{category}']: "
                f"El agente se detiene — llevas {count} intentos usando bash para una operación "
                "PERMANENTEMENTE BLOQUEADA. "
                "ACCIÓN: explica al usuario qué necesitas o usa la tool correcta.\n\n"
                + base_msg
            )
        return base_msg

    def _precheck_tool_call(self, name: str, args: dict) -> "str | None":
        """Pre-flight: bloquea tool calls que indican creación/ejecución de scripts
        temporales en lugar de usar las tools disponibles.

        Devuelve None para proceder, o un string de rechazo para bloquear sin ejecutar.
        """

        # ── Detección de rutas alucinadas — verifica que el fichero existe ────
        # Solo para tools sin guard propio: read_sections, code_outline, etc.
        # edit_file tiene su propio read-before-edit guard (line ~2745).
        # OOCODE.md excluido: se inyecta en system prompt, no precisa existir en disco.
        _PATH_TOOLS_NO_OWN_GUARD = frozenset({
            "read_sections", "code_outline", "code_compare", "diff_files",
        })
        if name in _PATH_TOOLS_NO_OWN_GUARD:
            _chk = str(args.get("path", "") or args.get("file_path", ""))
            if _chk and not _chk.startswith(("http://", "https://")):
                _already_read = _chk in getattr(self, "_turn_read_paths", set())
                _is_oocode_md = os.path.basename(_chk) == "OOCODE.md"
                if not _already_read and not _is_oocode_md:
                    _exp = os.path.expanduser(_chk)
                    if not os.path.exists(_exp):
                        _bname = os.path.basename(_exp)
                        return (
                            f"⛔ RUTA NO ENCONTRADA: '{_chk}' no existe.\n"
                            f"Usa find_file(name='{_bname}') o ls_dir(directory='.') "
                            f"para localizar el fichero correcto.\n"
                            f"NUNCA inventes rutas — verifica con ls_dir o find_file antes de editar."
                        )

        # ── Verificación de old_string — evita ediciones con texto alucinado ──
        # Lee el fichero y comprueba que old_string existe literalmente antes
        # de intentar el edit. Evita el caso frecuente en modelos pequeños donde
        # el modelo alucina el contenido exacto y el edit falla silenciosamente.
        if name == "edit_file":
            _old_str = args.get("old_string", "")
            _edit_path = str(args.get("path", "") or args.get("file_path", ""))
            # Solo verificar si el fichero fue leído este turno (garantía de que existe)
            _was_read = _edit_path in getattr(self, "_turn_read_paths", set())
            if _old_str and _edit_path and _was_read:
                try:
                    _exp_edit = os.path.expanduser(_edit_path)
                    with open(_exp_edit, encoding="utf-8", errors="replace") as _ef:
                        _edit_content = _ef.read()
                    if _old_str not in _edit_content:
                        _first_line = _old_str.strip().split("\n")[0][:60]
                        _prefix20 = _first_line[:25].strip()
                        _close = [
                            f"  L{i + 1}: {l.strip()[:80]}"
                            for i, l in enumerate(_edit_content.split("\n"))
                            if _prefix20 and _prefix20 in l
                        ][:3]
                        _close_str = (
                            "\nLíneas similares encontradas:\n" + "\n".join(_close)
                        ) if _close else ""
                        return (
                            f"⛔ PRE-EDIT FALLIDO: old_string no encontrado en '{_edit_path}'.\n"
                            f"Primera línea buscada: {_first_line!r}\n"
                            f"El texto debe coincidir exactamente (espacios, indentación, "
                            f"saltos de línea).{_close_str}\n"
                            f"Usa read_sections(path='{_edit_path}', "
                            f"sections=['NombreFuncion']) para ver el texto REAL antes de editar."
                        )
                except OSError:
                    pass  # El fichero no se puede leer → dejar que edit_file lo maneje

        if name == "write_file":
            path = str(args.get("path", ""))
            if self._TEMP_SCRIPT_RE.search(path):
                self._turn_written_scripts.add(os.path.basename(path))
                self._turn_written_scripts.add(path)
                _wf_msg = (
                    f"⛔ AGENTE BLOQUEÓ write_file — script temporal detectado: '{os.path.basename(path)}'\n"
                    "NUNCA crees ficheros .py/.sh temporales para realizar operaciones.\n"
                    "Alternativas:\n"
                    "• python_exec(code=...) — ejecuta Python directamente sin fichero\n"
                    "• edit_file / regex_replace / bulk_replace — para editar ficheros\n"
                    "• edit_files([...]) — edición atómica de múltiples ficheros a la vez\n"
                    "Reformula la operación con las tools disponibles."
                )
                # Usar el mismo mecanismo de escalada que _bash_block: al 3.er intento
                # el agente se detiene automáticamente para evitar bucles infinitos.
                return self._bash_block("write_script", _wf_msg)
            # Registrar cualquier .py/.sh escrito para detectarlo si bash lo ejecuta
            if path.endswith((".py", ".sh", ".bash")):
                self._turn_written_scripts.add(os.path.basename(path))
                self._turn_written_scripts.add(path)

        elif name == "bash":
            command = str(args.get("command", ""))

            # ── Guardas de SEGURIDAD ABSOLUTA — activas incluso en /elevated on ───
            # rm -rf sobre rutas del sistema
            if self._BASH_DANGEROUS_RM_RE.search(command):
                return self._bash_block("rm", (
                    "⛔ AGENTE BLOQUEÓ bash — eliminación masiva de rutas del sistema.\n"
                    f"Comando bloqueado: {command[:120]}\n"
                    "PELIGROSO: rm -rf en /, /home, /etc, /usr, /var, ~/* está PROHIBIDO.\n"
                    "Para eliminar ficheros del proyecto usa rm_file(path=...) o rm_dir(path=...)."
                ))

            # docker compose down -v — destruye VOLÚMENES de datos
            if re.search(r'compose\s+down.*-v\b|-v.*compose\s+down', command, re.I):
                return self._bash_block("compose_down_v", (
                    "⛔ AGENTE BLOQUEÓ bash — 'docker compose down -v' destruye VOLÚMENES de datos.\n"
                    "⚠️  PELIGRO: -v elimina la base de datos y todos los datos persistentes.\n"
                    "Alternativas:\n"
                    "  • Solo parar servicios:       compose_stop(directory='...')\n"
                    "  • Parar y eliminar containers: compose_down(directory='...')  (sin -v)\n"
                    "  • Reiniciar sin borrar datos:  compose_restart(directory='...')\n"
                    "Si REALMENTE necesitas borrar volúmenes, explica por qué antes de hacerlo."
                ))

            # ── En modo /elevated on/full: omitir guardas de redirección ─────────
            # Los bloques siguientes son ORIENTATIVOS (redirigen a tools equivalentes).
            # Con elevated activado el usuario tiene control total de bash.
            _elevated = getattr(getattr(self, "rt", None), "elevated", "off")
            if _elevated in ("on", "full"):
                return None

            # ── Guardas de redirección (solo en modo normal) ──────────────────────
            # cat leyendo un fichero — redirigir a read_file
            m = self._BASH_CAT_READ_RE.match(command)
            if m:
                fpath = m.group(1)
                return self._bash_block("cat_read", (
                    f"⛔ AGENTE BLOQUEÓ bash — usa read_file en lugar de 'cat {os.path.basename(fpath)}'.\n"
                    f"CORRECTO: read_file(path='{fpath}') — soporta offset=/limit= para ficheros grandes."
                ))

            # Heredoc Python → usar python_exec
            if self._BASH_HEREDOC_PY_RE.search(command):
                return self._bash_block("heredoc", (
                    "⛔ AGENTE BLOQUEÓ bash — heredoc Python detectado.\n"
                    "BLOQUEADO: 'python3 << EOF' heredoc.\n"
                    "→ USA: python_exec(code='''...''', workdir='...')\n"
                    "→ NUNCA: bash python3/python inline scripts\n"
                    "Razón: los heredocs en bash truncan el output y producen bugs difíciles de detectar."
                ))

            # cat > fichero << EOF → usar write_file
            if self._BASH_CAT_EOF_RE.search(command):
                return self._bash_block("heredoc", (
                    "⛔ AGENTE BLOQUEÓ bash — creación de fichero con heredoc detectada.\n"
                    "PROHIBIDO: usa write_file(path=..., content=...) en lugar de 'cat > fichero << EOF'."
                ))

            # echo/printf > script.py → usar write_file o python_exec
            m = self._BASH_ECHO_SCRIPT_RE.search(command)
            if m:
                script = m.group(1)
                if self._TEMP_SCRIPT_RE.search(script):
                    return self._bash_block("script_temp", (
                        f"⛔ AGENTE BLOQUEÓ bash — creación inline de script temporal: '{os.path.basename(script)}'\n"
                        "PROHIBIDO: usa python_exec(code=...) o write_file(path=..., content=...) en lugar de echo/printf redirect."
                    ))

            # tee script_temp.py → usar write_file
            m = self._BASH_TEE_SCRIPT_RE.search(command)
            if m:
                script = m.group(1)
                if self._TEMP_SCRIPT_RE.search(script):
                    return self._bash_block("script_temp", (
                        f"⛔ AGENTE BLOQUEÓ bash — tee a script temporal: '{os.path.basename(script)}'\n"
                        "Usa write_file(path=..., content=...) en lugar de piping a tee."
                    ))

            # bash/sh ejecutando script .sh con nombre temporal
            m = self._BASH_RUN_SH_RE.search(command)
            if m:
                script = m.group(1)
                if self._TEMP_SCRIPT_RE.search(script):
                    return self._bash_block("script_temp", (
                        f"⛔ AGENTE BLOQUEÓ bash — intento de ejecutar script .sh temporal: '{os.path.basename(script)}'\n"
                        "Usa bash() directamente con los comandos en lugar de crear y ejecutar un script."
                    ))

            # python3 script_temp.py
            m = self._BASH_RUN_PY_RE.search(command)
            if m:
                script = m.group(1)
                if self._TEMP_SCRIPT_RE.search(script):
                    return self._bash_block("script_temp", (
                        f"⛔ AGENTE BLOQUEÓ bash — intento de ejecutar script temporal: '{os.path.basename(script)}'\n"
                        "Usa python_exec(code=...) directamente en lugar de crear y ejecutar .py."
                    ))

            # grep -r/-rn/-l/-L/-c / --include= → usar grep_code / multi_grep
            if self._BASH_GREP_REDIRECT_RE.search(command):
                return self._bash_block("grep", (
                    "⛔ AGENTE BLOQUEÓ bash — grep multi-fichero detectado.\n"
                    "USA grep_code o multi_grep — son más rápidos y soportan regex Python:\n"
                    "  • grep -r 'pat' dir/          → grep_code(pattern='pat', directory='dir/')\n"
                    "  • grep -rn 'p' --include='*.c' → grep_code(pattern='p', extensions=['c'], context_lines=2)\n"
                    "  • grep -l 'pat' src/           → grep_code(pattern='pat', files_with_matches=true)\n"
                    "  • grep -L 'pat' src/           → grep_code(pattern='pat', files_without_matches=true)\n"
                    "  • grep -c 'pat' src/           → grep_code(pattern='pat', count_only=true)\n"
                    "  • grep 'p1'...; grep 'p2'...   → multi_grep(patterns=['p1','p2'], directory='dir/')\n"
                    "grep_code excluye .git/__pycache__/node_modules automáticamente."
                ))

            # find ... -name/-type/-newer → usar find_file / find_files
            if self._BASH_FIND_REDIRECT_RE.search(command):
                return self._bash_block("find", (
                    "⛔ AGENTE BLOQUEÓ bash — find con filtros detectado.\n"
                    "USA find_files o find_file — más seguros y excluyen .git/__pycache__/node_modules:\n"
                    "  • find dir -name '*.c'          → find_files(directory='dir/', name='*.c')\n"
                    "  • find dir -name '*.py' -type f → find_files(directory='dir/', name='*.py')\n"
                    "  • find dir -name 'foo*'          → find_file(path='dir/', pattern='foo*')\n"
                    "  • find dir -type d               → find_dir(path='dir/', pattern='*')\n"
                    "  • find dir -name '*.py' -newer f → find_files(directory='dir/', name='*.py', max_age_days=1)\n"
                    "Para contar ficheros: usa file_stat(path) o grep_code con count_only=true."
                ))

            # sed -i → usar edit_file / regex_replace / bulk_replace
            if self._BASH_SED_INPLACE_RE.search(command):
                return self._bash_block("sed", (
                    "⛔ AGENTE BLOQUEÓ bash — sed -i (edición in-place) detectado.\n"
                    "USA las tools de edición — tienen rollback automático y son reproducibles:\n"
                    "  • sed -i 's/old/new/' file        → edit_file(path, old_string='old', new_string='new')\n"
                    "  • sed -i 's/old/new/g' file        → regex_replace(path, pattern='old', replacement='new')\n"
                    "  • sed -i 's/p/r/' *.c (todos)     → bulk_replace(directory, pattern='p', replacement='r', extensions=['c'])\n"
                    "  • sed -i '1s/^/header\\n/' files   → edit_files([{path, old_string, new_string}, ...])\n"
                    "SIEMPRE lee el fichero con read_file antes de editar para confirmar el texto exacto."
                ))

            # docker cp → usar docker_cp
            if self._BASH_DOCKER_CP_RE.search(command):
                return self._bash_block("docker_cp", (
                    "⛔ AGENTE BLOQUEÓ bash — usa docker_cp en lugar de 'docker cp'.\n"
                    "  • docker cp SRC CONTAINER:DST → docker_cp(src='SRC', dst='CONTAINER:DST')\n"
                    "  • docker cp CONTAINER:SRC DST → docker_cp(src='CONTAINER:SRC', dst='DST')"
                ))

            # docker compose exec / docker exec → usar docker_exec / compose_exec
            if self._BASH_DOCKER_EXEC_RE.search(command):
                if re.search(r'docker\s+compose|docker-compose', command, re.I):
                    return self._bash_block("compose_exec", (
                        "⛔ AGENTE BLOQUEÓ bash — usa compose_exec en lugar de 'docker compose exec'.\n"
                        "  compose_exec(service='SERVICE', command='CMD', workdir='/path', user='root')\n"
                        "  Ejemplo: compose_exec(service='wordpress', command='wp theme list')"
                    ))
                return self._bash_block("docker_exec", (
                    "⛔ AGENTE BLOQUEÓ bash — usa docker_exec en lugar de 'docker exec'.\n"
                    "  docker_exec(container='CONTAINER', command='CMD', user='root')\n"
                    "  Ejemplo: docker_exec(container='sandra-wordpress', command='php -v')"
                ))

            # docker compose ps/up/down/logs/restart/stop/build → compose_* tools
            if self._BASH_COMPOSE_CMD_RE.search(command):
                # compose down -v ya fue bloqueado arriba (guarda absoluta); aquí nunca llega con -v
                _m = re.search(
                    r'(?:docker\s+compose|docker-compose)\s+(ps|up|down|logs|restart|stop|build|pull|run|config|images|top)',
                    command, re.I,
                )
                _sub = _m.group(1).lower() if _m else "cmd"
                _tool_map = {
                    "ps": "compose_status", "up": "compose_up", "down": "compose_down",
                    "logs": "compose_logs", "restart": "compose_restart", "stop": "compose_stop",
                    "build": "compose_build", "pull": "compose_pull", "run": "compose_run",
                    "config": "compose_config", "images": "compose_images", "top": "compose_top",
                }
                _tool = _tool_map.get(_sub, f"compose_{_sub}")
                return self._bash_block("compose", (
                    f"⛔ AGENTE BLOQUEÓ bash — usa {_tool} en lugar de 'docker compose {_sub}'.\n"
                    f"  {_tool}(directory='/ruta/proyecto/', ...)  — devuelve JSON estructurado.\n"
                    "Ver tabla HERRAMIENTAS en SYSTEM_RULES para todos los subcomandos compose."
                ))

            # docker ps/logs/inspect/images/stop/rm → docker_* tools
            if self._BASH_DOCKER_CMD_RE.search(command):
                _m2 = re.search(r'\bdocker\s+(ps|logs|inspect|images|stop|rm|kill|start|restart)\b', command, re.I)
                _sub2 = _m2.group(1).lower() if _m2 else "cmd"
                _tool2 = {"ps": "docker_ps", "logs": "docker_logs", "inspect": "docker_inspect",
                          "images": "docker_images", "stop": "docker_stop", "rm": "docker_rm"}.get(_sub2, f"docker_{_sub2}")
                return self._bash_block("docker", (
                    f"⛔ AGENTE BLOQUEÓ bash — usa {_tool2} en lugar de 'docker {_sub2}'.\n"
                    f"  {_tool2}(container='NOMBRE', ...)  — devuelve JSON estructurado."
                ))

            # ls (cualquier variante) → usar ls_dir
            if self._BASH_LS_RE.search(command):
                return self._bash_block("ls", (
                    "⛔ AGENTE BLOQUEÓ bash — usa ls_dir en lugar de 'ls'.\n"
                    "  ls_dir(path='DIRECTORIO', max_entries=100) — JSON con permisos, tamaño y fecha.\n"
                    "  Para un fichero concreto: ls_file(path='FICHERO') o file_stat(path='FICHERO')."
                ))

        elif name == "edit_file":
            # Exigir que el fichero haya sido leído antes de editar
            path = str(args.get("path", ""))
            if path and path not in self._turn_read_paths:
                # OOCODE.md se inyecta en el system prompt — no requiere read previo
                if os.path.basename(path) == "OOCODE.md":
                    return None
                return (
                    f"⛔ AGENTE BLOQUEÓ edit_file — no has leído '{os.path.basename(path)}' en este turno.\n"
                    "PROTOCOLO OBLIGATORIO antes de editar:\n"
                    f"  1. read_file(path='{path}') — copia el texto EXACTO que quieres cambiar\n"
                    "  2. Luego edit_file(path=..., old_string='TEXTO EXACTO', new_string='...')\n"
                    "Esto evita errores de 'cadena no encontrada' por texto inventado."
                )

        elif name == "python_exec":
            code = str(args.get("code", ""))
            # Detectar escritura masiva de ficheros del proyecto vía open()/write
            # Solo bloqueamos cuando hay múltiples escrituras (script de modificación masiva)
            _file_writes = re.findall(
                r'open\s*\(\s*["\']([^"\']+)["\'][^)]*["\']w', code
            )
            _src_writes = [
                p for p in _file_writes
                if any(p.endswith(e) for e in (".py", ".c", ".h", ".cpp", ".js", ".ts", ".sh"))
            ]
            if len(_src_writes) >= 2:
                return (
                    "⛔ AGENTE BLOQUEÓ python_exec — escritura múltiple de ficheros fuente detectada.\n"
                    f"Ficheros detectados: {', '.join(_src_writes[:5])}\n"
                    "USA las tools de edición — tienen backup automático, diff visual y rollback:\n"
                    "  • edit_file(path, old_string='...texto exacto...', new_string='...') — edición precisa\n"
                    "  • edit_files([{path, old_string, new_string}, ...]) — múltiples ficheros atómico\n"
                    "  • regex_replace(file, pattern, replacement) — sustitución con regex\n"
                    "  • bulk_replace(directory, pattern, replacement, extensions=[...]) — masivo por directorio\n"
                    "Lee el fichero con read_file primero para copiar el texto exacto antes de editar."
                )
            # Detectar subprocess llamando a docker/compose (eludir las tools nativas)
            if re.search(r'subprocess\.\w+\s*\(\s*\[?\s*["\']docker', code):
                return self._bash_block("docker", (
                    "⛔ AGENTE BLOQUEÓ python_exec — subprocess.docker detectado.\n"
                    "Usa las tools nativas en lugar de llamar a docker via subprocess:\n"
                    "  docker_exec(container='NAME', command='CMD')\n"
                    "  compose_exec(service='SVC', command='CMD')\n"
                    "  compose_up/down/logs/status/restart — ver tabla HERRAMIENTAS en SYSTEM_RULES."
                ))

        elif name in ("docker_exec", "mcp_oocode_assistant_docker_exec"):
            command = str(args.get("command", ""))
            # Heredoc de escritura de fichero dentro de docker_exec no funciona
            # (sh -c con newlines literales). Solo bloqueamos el patrón específico
            # de write-to-file: cat > FILE << TAG o tee FILE << TAG
            _heredoc_write = re.search(
                r'(?:cat\s+>|tee)\s+\S+.*<<\s*[\'"]?\w|<<\s*[\'"]?EOF',
                command, re.I
            )
            if _heredoc_write:
                return (
                    "⛔ AGENTE BLOQUEÓ docker_exec — heredoc de escritura detectado.\n"
                    "docker_exec usa 'sh -c CMD' que no soporta heredoc para escribir ficheros.\n"
                    "Para escribir contenido en un contenedor:\n"
                    "  1. write_file(path='~/.oocode/tmp/filename', content='...') — escribe en el host\n"
                    "  2. docker_cp(src='~/.oocode/tmp/filename', dst='CONTAINER:/ruta/') — copia al contenedor\n"
                    "  O usa docker_exec(command='printf \\'contenido\\' > /ruta/fichero') "
                    "para contenido pequeño."
                )

        return None

    # ── Detección de tareas múltiples en el mensaje del usuario ─────────────

    @staticmethod
    def _detect_tasks(text: str) -> list[str]:
        """Extrae tareas top-level de una lista numerada o con bullets en *text*.

        Solo cuenta items al nivel de indentación mínimo (top-level).
        Sub-bullets/items indentados bajo otro item se ignoran.
        Devuelve lista de ≥2 items (cada uno ≥10 chars), máximo 12.
        """
        lines = text.split('\n')
        _num    = re.compile(r'^(\s*)(?:\d+[.):\-]|paso\s+\d+[).::-]?)\s+(.+)', re.I)
        _bullet = re.compile(r'^(\s*)[-*•–·]\s+(.+)')

        # Prioridad 1: items numerados al nivel mínimo de indentación
        numbered: list[tuple[int, str]] = []
        for line in lines:
            m = _num.match(line)
            if m:
                indent = len(m.group(1))
                task   = m.group(2).strip()
                if len(task) >= 10:
                    numbered.append((indent, task))
        if numbered:
            min_indent = min(ind for ind, _ in numbered)
            top = [t for ind, t in numbered if ind == min_indent]
            if len(top) >= 2:
                return top[:12]

        # Prioridad 2: bullets solo al nivel mínimo de indentación
        min_bullet: int | None = None
        bullets: list[str] = []
        for line in lines:
            m = _bullet.match(line)
            if m:
                indent = len(m.group(1))
                task   = m.group(2).strip()
                if len(task) >= 10:
                    if min_bullet is None:
                        min_bullet = indent
                    if indent == min_bullet:
                        bullets.append(task)
        if len(bullets) >= 2:
            return bullets[:12]
        return []

    _COMPLETION_REPORT_RE = re.compile(
        r'\b(?:'
        r'he\s+completado\b|'
        r'he\s+terminado\b|'
        r'he\s+finalizado\b|'
        r'he\s+(?:implementado|migrado|actualizado|corregido|añadido|eliminado)\s+(?:todo|todas?|la[s]?\s+tarea[s]?)\b|'
        r'tarea[s]?\s+(?:completada[s]?|finalizada[s]?|terminada[s]?)\b|'
        r'todo[s]?\s+(?:listo[s]?|completado[s]?|hecho[s]?|correcto[s]?)\b|'
        r'todo\s+(?:ha\s+sido|está)\s+(?:completado|actualizado|corregido)\b|'
        r'all\s+(?:tasks?\s+)?(?:done|completed|finished)\b|'
        r'todo\s+funciona\s+correctamente\b|'
        r'las\s+\d+\s+tarea[s]?\s+(?:están\s+)?complet'
        r')',
        re.IGNORECASE,
    )
    _COMPLETION_HEADER_RE = re.compile(
        r'^#{1,3}\s+(?:resumen|summary|resultado[s]?|cambios\s+realizados|tareas\s+completadas|trabajo\s+realizado)',
        re.IGNORECASE | re.MULTILINE,
    )

    @classmethod
    def _is_completion_report(cls, text: str) -> bool:
        """True si el texto parece un informe de tarea completada (no un plan futuro).

        Detecta señales en pasado/informe: "he completado", "## Resumen", etc.
        Se usa para evitar que auto-continue dispare después de un informe final.
        """
        if not text or len(text) < 40:
            return False
        return bool(
            cls._COMPLETION_REPORT_RE.search(text)
            or cls._COMPLETION_HEADER_RE.search(text)
        )

    # ── Task plan tracker ────────────────────────────────────────────────────

    def _set_plan_task_active(self, idx: int) -> None:
        """Marca tareas < idx como done, idx como active, resto pending."""
        now = time.time()
        for i, task in enumerate(self._plan_tasks):
            if i < idx:
                if task["status"] != "done":
                    task["status"] = "done"
                    if not task["end_ts"]:
                        task["end_ts"] = now
            elif i == idx:
                if task["status"] != "active":
                    task["status"] = "active"
                    if not task["start_ts"]:
                        task["start_ts"] = now
            else:
                if task["status"] == "active":
                    task["status"] = "pending"

    def _all_plan_tasks_done(self) -> bool:
        """True si hay plan y todas las tareas están completadas."""
        return bool(self._plan_tasks) and all(
            t["status"] == "done" for t in self._plan_tasks
        )

    def _mark_all_plan_tasks_done(self) -> None:
        """Marca todas las tareas del plan como done (si no lo estaban ya)."""
        now = time.time()
        for t in self._plan_tasks:
            if t["status"] != "done":
                t["status"] = "done"
                if not t["end_ts"]:
                    t["end_ts"] = now

    # Señal de completado explícita — sin mínimo de longitud (puede ser frase corta)
    _DONE_SIGNAL_RE = re.compile(
        r'\b(?:he\s+completado\s+todas|all\s+tasks?\s+(?:done|completed|finished)|'
        r'todas\s+las\s+tareas\s+(?:están\s+)?complet)',
        re.I,
    )

    # Señales de trabajo futuro — contradicen "He completado todas las tareas".
    # Si el modelo menciona próximo paso/fase pendiente EN LA MISMA respuesta en que
    # dice "He completado", la señal es prematura y se ignora.
    _PREMATURE_DONE_RE = re.compile(
        r'(?:'
        r'próximo\s+paso\s*[:\-]|next\s+step\s*[:\-]|'
        r'siguiente\s+(?:tarea|fase|paso)\s*[:\-]|'
        # pendiente/pendientes con puntuación — estructura tipo "pendiente: ..." o lista
        r'pendientes?\s*[:\-,\n]|'
        # (PENDIENTE) / (PENDING) — estado explícito entre paréntesis en tablas/listas
        r'\(PENDIENTE\)|\(PENDING\)|'
        r'🔄\s*(?:en\s+)?curso|⏳\s*pendiente|'
        r'fase\s+\d+.*?(?:en\s+curso|🔄)|'
        r'(?:en\s+curso|in\s+progress)\s*🔄|'
        # errores explícitos sin resolver (cualquier dominio)
        r'requiere\s+corrección|se\s+requiere\s+corrección|'
        r'requires?\s+(?:correction|fix(?:ing)?)|'
        # cualquier ❌ en la misma respuesta que "He completado" contradice la señal
        r'❌'
        r')',
        re.I,
    )

    def _advance_plan_task(self, text: str) -> None:
        """Avanza la tarea activa basándose en el texto del modelo.

        Capa 1: señal de completado global ("todas las tareas") → marca todas done.
        Capa 2: detecta anuncio explícito "Tarea N:" / "Paso N:".
        Capa 3 (fallback): sincroniza con _auto_continue_count, solo avanza (nunca retrocede).
        """
        if not self._plan_tasks:
            return
        # Capa 1: señal de completado global — SOLO si menciona "todas" / "all tasks"
        # NO usar _is_completion_report aquí: "he completado [un fichero]" no es completado global
        if self._DONE_SIGNAL_RE.search(text):
            _pending = sum(1 for t in self._plan_tasks if t["status"] == "pending")
            # La señal es prematura si:
            #   (a) todavía hay tareas ◻ que no han empezado, O
            #   (b) el propio texto menciona trabajo futuro (contradictorio)
            _premature_re_match = self._PREMATURE_DONE_RE.search(text)
            _is_premature = _pending > 0 or bool(_premature_re_match)
            if not _is_premature:
                self._mark_all_plan_tasks_done()
            elif _premature_re_match and _pending == 0:
                # Todas las tareas rastreadas están done, pero el texto menciona trabajo
                # pendiente (ej. "(PENDIENTE)", "❌"). El modelo puede haber ampliado el
                # plan con nuevos pasos/elementos no rastreados originalmente.
                # Intentar extraer nuevas tareas del texto y añadirlas al plan.
                _new_steps = self._detect_tasks(text)
                if _new_steps:
                    for _ns in _new_steps:
                        self._plan_tasks.append(
                            {"text": _ns, "status": "pending",
                             "start_ts": 0.0, "end_ts": 0.0}
                        )
                    # Activar la primera nueva tarea pendiente
                    for _t in self._plan_tasks:
                        if _t["status"] == "pending":
                            _t["status"] = "active"
                            break
                else:
                    # No se detectaron nuevas tareas: revertir la última done a active
                    # para evitar que _all_plan_tasks_done() detenga el bucle.
                    for _t in reversed(self._plan_tasks):
                        if _t["status"] == "done":
                            _t["status"] = "active"
                            break
            # Si es prematura, no marcar todas done — Capa 2/3 tomará el relevo
            return
        # Capa 2: anuncio de tarea específica
        _ANNOUNCE = re.compile(r'\b(?:tarea|paso|step|task)\s+(\d+)\s*[:\-]', re.I)
        m = _ANNOUNCE.search(text[:300])
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(self._plan_tasks):
                self._set_plan_task_active(idx)
                return
        # Capa 3: sincronizar con iteración actual — solo avanza, nunca retrocede
        # (evita resetear la tarea activa a 0 tras compactación cuando _auto_continue_count es 0)
        current_active = next(
            (i for i, t in enumerate(self._plan_tasks) if t["status"] == "active"), 0
        )
        target = min(self._auto_continue_count, len(self._plan_tasks) - 1)
        if target > current_active:
            self._set_plan_task_active(target)

    # ── RAG params ───────────────────────────────────────────────────────────

    def _rag_params_for_turn(self, msg: str) -> tuple[int, float]:
        """Devuelve (top_k, threshold) apropiados para el turno actual.

        Si el mensaje es complejo (largo o con keywords de autoedición), usa los
        valores de boost configurados. Si no, usa los valores base.
        """
        cfg = getattr(self, "config", None)
        top_k_base    = getattr(cfg, "rag_top_k",            5)
        thresh_base   = getattr(cfg, "rag_similarity_threshold", 0.40)
        top_k_complex = getattr(cfg, "rag_top_k_complex",    10)
        thresh_complex = getattr(cfg, "rag_threshold_complex", 0.35)
        min_chars     = getattr(cfg, "rag_complex_min_chars", 150)
        if _is_complex_query(msg, min_chars):
            return top_k_complex, thresh_complex
        return top_k_base, thresh_base

    # ── Pre-model evaluation ─────────────────────────────────────────────────

    def _turn_guidance(self) -> str:
        """Guidance dinámica basada en el historial de tool calls del turno actual.

        Se recalcula en CADA iteración del while, por eso NO está en el caché
        del system prompt. Devuelve cadena vacía si no hay nada que advertir.
        """
        hints: list[str] = []

        # ── 0. Inyección de tareas múltiples — primera llamada LLM del turno ──
        # Solo se inyecta cuando no hay historial de tool calls (primera iteración).
        # Las iteraciones siguientes ya "saben" las tareas por el contexto de mensajes.
        if self._pending_tasks and not self._last_tool_calls:
            n = len(self._pending_tasks)
            tasks_str = "\n".join(
                f"  {i + 1}. {t}" for i, t in enumerate(self._pending_tasks)
            )
            hints.append(
                f"\n⚡ PLAN OBLIGATORIO [{n} tarea{'s' if n != 1 else ''} en la solicitud]:\n"
                f"{tasks_str}\n"
                f"PROTOCOLO — responde SOLO con texto detallado (sin llamar tools todavía):\n"
                f"  0. ANALIZA: ¿tareas solapadas o dependientes entre sí? ¿alguna tarea implícita?\n"
                f"  1. EMITE UN PLAN DETALLADO con este formato para cada acción:\n"
                f"       N. [Acción]: [qué harás] — ficheros: [rutas exactas] — tools: [tools a usar]\n"
                f"     Incluye: cambios concretos, por qué, si puede romper algo existente.\n"
                f"  2. Si alguna acción tiene BLOQUEADORES (decisión de diseño no clara, dependencia\n"
                f"     faltante, riesgo alto de romper funcionalidad), añade al final del plan:\n"
                f"       ⚠ REQUIERE REVISIÓN: [descripción exacta del problema]\n"
                f"     Esto PAUSA la ejecución hasta que el usuario responda o envíe /steer.\n"
                f"  3. Sin '⚠ REQUIERE REVISIÓN', el sistema continúa automáticamente.\n"
                f"     El usuario puede redirigir en cualquier momento con /steer o /subagents steer.\n"
                f"  4. Durante la ejecución: anuncia cada tarea con 'Tarea N: descripción breve' "
                f"antes de empezarla."
            )
            return "".join(hints)  # solo la guía de tareas — no hay historial aún

        if not self._last_tool_calls:
            return ""

        # ── Plan status en iteraciones posteriores a la primera ───────────────
        _plan_tasks_g = getattr(self, "_plan_tasks", [])
        if _plan_tasks_g and not self._all_plan_tasks_done():
            _ai = next((i for i, t in enumerate(_plan_tasks_g) if t["status"] == "active"), -1)
            if _ai >= 0:
                _total_t = len(_plan_tasks_g)
                _done_t  = sum(1 for t in _plan_tasks_g if t["status"] == "done")
                _task_lines = "\n".join(
                    f"  {'✔' if t['status'] == 'done' else '◼' if t['status'] == 'active' else '◻'} "
                    f"{i + 1}. {t['text']}"
                    for i, t in enumerate(_plan_tasks_g)
                )
                _ni = _ai + 1
                _is_last = _ni >= _total_t
                _next_hint = (
                    f" Cuando termines, anuncia \"Tarea {_ni + 1}:\" y continúa."
                    if not _is_last
                    else " Ésta es la última tarea. Al terminarla: "
                         "(1) llama run_tests/test_file si modificaste código; "
                         "(2) escribe \"He completado todas las tareas.\" como primera frase."
                )
                hints.append(
                    f"\n📋 PLAN EN CURSO [{_done_t + 1}/{_total_t}]:\n{_task_lines}\n"
                    f"→ Completando ahora: \"{_plan_tasks_g[_ai]['text']}\".{_next_hint}\n"
                    f"→ NO respondas vacío. Usa tools o describe el avance.\n"
                    f"→ PROHIBIDO: no emitas \"He completado todas las tareas\" mientras haya ◻ tareas pendientes "
                    f"o si mencionas \"Próximo paso\" / trabajo futuro en la misma respuesta.\n"
                )

        total   = len(self._last_tool_calls)
        blocked = sum(1 for _, _, r in self._last_tool_calls
                      if isinstance(r, str) and r.startswith("⛔"))
        bash_n  = sum(1 for _tn, _, _ in self._last_tool_calls if _tn == "bash")
        # Calculado una vez aquí: reutilizado en hints #7, #10 y #12
        _already_searched = any(
            n in ("web_search", "search_web", "searxng_search")
            for n, _, _ in self._last_tool_calls
        )

        # ── 1. Ratio bash alto en este turno (≥3 calls, >40% bash) ──────────
        if total >= 3 and bash_n / total > 0.4:
            hints.append(
                f"\n⚡ EVALUACIÓN AGENTE [{bash_n}/{total} bash este turno]: "
                "Estás sobreusando bash. TABLA RÁPIDA:\n"
                "  grep -r/l/L/c → grep_code | find -name → find_files(directory=…,name='*.ext') | ls -la → ls_dir\n"
                "  sed -i → edit_file/regex_replace | wc -l → file_stat | git * → git_status/diff/…\n"
                "bash es el ÚLTIMO RECURSO — solo cuando ninguna tool de la tabla cubre la necesidad."
            )

        # ── 2. Bloqueos consecutivos al final del historial ──────────────────
        streak = 0
        for _, _, r in reversed(self._last_tool_calls):
            if isinstance(r, str) and r.startswith("⛔"):
                streak += 1
            else:
                break
        if streak >= 2:
            hints.append(
                f"\n⚡ EVALUACIÓN AGENTE [{streak} bloqueos consecutivos]: "
                f"El agente rechazó tus últimos {streak} intentos. "
                "CAMBIA de estrategia: NO uses scripts temporales ni heredocs. "
                "Usa python_exec(code=...) para Python, edit_file/bulk_replace para editar ficheros."
            )

        # ── 3. Bloqueos totales altos en el turno ────────────────────────────
        if blocked >= 3 and streak < 2:
            hints.append(
                f"\n⚡ EVALUACIÓN AGENTE [{blocked} bloqueos en este turno]: "
                "Muchos intentos bloqueados. Revisa la tabla de equivalencias antes de continuar."
            )

        # ── 4. Errores bash consecutivos — mismo comando fallando repetidamente
        _bash_error_kw = ("no such file", "command not found", "permission denied",
                          "traceback (most recent call last)", "error: el comando")
        bash_errors = sum(
            1 for _tn, _, r in self._last_tool_calls
            if _tn == "bash" and any(kw in str(r).lower() for kw in _bash_error_kw)
        )
        if bash_errors >= 3:
            hints.append(
                f"\n⚡ EVALUACIÓN AGENTE [{bash_errors} bash con errores]: "
                "Múltiples comandos bash están fallando. DIAGNOSTICA antes de reintentar: "
                "verifica rutas con ls_dir(path) o find_files(directory=path,name='*'), comprueba que el binario existe con bash('which cmd'), "
                "usa rutas absolutas. Considera usar las tools especializadas."
            )

        # ── 5. Re-lectura repetida del mismo fichero (≥3 veces) ──────────────
        _read_paths: dict[str, int] = {}
        for _tn, a_str, _ in self._last_tool_calls:
            if _tn == "read_file" and a_str:
                try:
                    _path = json.loads(a_str).get("path", "")
                    if _path:
                        _read_paths[_path] = _read_paths.get(_path, 0) + 1
                except Exception:
                    pass
        _repeated = [(p, c) for p, c in _read_paths.items() if c >= 3]
        if _repeated:
            _rep_str = ", ".join(
                f"'{os.path.basename(p)}'×{c}" for p, c in _repeated[:3]
            )
            hints.append(
                f"\n⚡ EVALUACIÓN AGENTE [reads repetidos: {_rep_str}]: "
                "Ya leíste estos ficheros múltiples veces. Extrae la información necesaria en lugar de releer. "
                "Si necesitas una sección específica: read_file(path, offset=N, limit=M)."
            )

        # ── 6. Exploración sin acción — muchas lecturas, ninguna escritura ───
        _reads_n  = sum(1 for n, _, _ in self._last_tool_calls
                        if n in ("read_file", "read_files", "grep_code", "find_file",
                                 "find_files", "ls_dir", "symbol_lookup", "multi_grep"))
        _writes_n = sum(1 for n, _, _ in self._last_tool_calls
                        if n in ("edit_file", "write_file", "bulk_replace",
                                 "regex_replace", "edit_files", "patch_apply"))
        if total >= 10 and _reads_n >= 8 and _writes_n == 0:
            hints.append(
                f"\n⚡ EVALUACIÓN AGENTE [{_reads_n}/{total} exploración sin escrituras]: "
                "Has explorado extensamente pero no has modificado nada. "
                "Si la tarea requiere cambios: usa edit_file, write_file o bulk_replace. "
                "Si es solo análisis: responde con lo que has encontrado."
            )

        # ── 7. Atasco total — últimas 4 acciones todas con error ─────────────
        _last4 = self._last_tool_calls[-4:]
        if len(_last4) >= 4:
            _error_kw = ("⛔", "error:", "error ejecutando", "no such file",
                         "command not found", "permission denied")
            _all_fail = all(
                any(kw in str(r).lower() for kw in _error_kw)
                for _, _, r in _last4
            )
            if _all_fail:
                _ws_stuck = (
                    "" if _already_searched
                    else " Si el fallo implica un error externo (API, librería, dependencia): "
                         "usa web_search para buscar la causa antes de seguir probando."
                )
                hints.append(
                    f"\n⚡ EVALUACIÓN AGENTE [últimas {len(_last4)} acciones fallidas]: "
                    "Todo está fallando. PARA y replantea: "
                    "¿el path es correcto? ¿existe el fichero? (usa ls_dir o find_files). "
                    "¿es la tool adecuada? ¿tienes los argumentos correctos?"
                    + _ws_stuck
                )

        # ── 8. Edición sin lectura previa — antipatrón "edición ciega" ────────
        _edit_names = ("edit_file", "edit_files", "regex_replace", "bulk_replace", "patch_apply")
        _read_names = ("read_file", "read_files", "grep_code", "grep_file",
                       "symbol_lookup", "multi_grep", "code_compare", "explore")
        _has_edits = sum(1 for n, _, _ in self._last_tool_calls if n in _edit_names)
        _has_reads = sum(1 for n, _, _ in self._last_tool_calls if n in _read_names)
        if _has_edits >= 1 and _has_reads == 0 and total <= 6:
            hints.append(
                f"\n⚡ EVALUACIÓN AGENTE [edición sin exploración previa]: "
                "Has usado edit_file/regex_replace sin leer el fichero afectado en este turno. "
                "El old_string debe coincidir exactamente — lee primero con read_file(path). "
                "Flujo correcto: read_file → analiza → edit_file."
            )

        # ── 9. Exploración prolongada sin síntesis — el modelo analiza pero no implementa
        _search_names = ("grep_code", "grep_file", "multi_grep", "symbol_lookup",
                         "code_compare", "explore", "find_file", "find_files", "ls_dir")
        _search_n = sum(1 for n, _, _ in self._last_tool_calls if n in _search_names)
        if total >= 6 and _search_n >= 4 and _writes_n == 0 and _has_edits == 0:
            hints.append(
                f"\n⚡ EVALUACIÓN AGENTE [{_search_n} búsquedas sin implementación]: "
                "Llevas mucho tiempo explorando sin aplicar cambios. "
                "Si ya tienes el cuadro claro: enumera los problemas y di 'Implemento:' antes de editar. "
                "Si no: usa explore(task) para una exploración profunda en una sola llamada."
            )

        # ── 10. Misma tool con mismos args llamada N veces (bucle exacto) ────────
        # Detecta cuando el modelo repite exactamente la misma llamada — siempre
        # improductivo: si falló/no encontró nada, repetirlo da el mismo resultado.
        from collections import Counter as _Counter
        _call_sigs = [(n, a_str) for n, a_str, _ in self._last_tool_calls]
        _dup_counts = _Counter(_call_sigs)
        _worst_dup = max(_dup_counts.items(), key=lambda x: x[1], default=(None, 0))
        if _worst_dup[1] >= 2:
            _dup_name, _dup_args_str = _worst_dup[0] or (None, "")  # type: ignore[misc]
            _dup_count = _worst_dup[1]
            try:
                _dup_args_repr = json.loads(_dup_args_str)
                _dup_pat = (_dup_args_repr.get("pattern") or _dup_args_repr.get("old_string")
                            or str(_dup_args_repr)[:60])
            except Exception:
                _dup_pat = _dup_args_str[:60]
            _ws_loop = (
                "" if _already_searched
                else "\n• Si el símbolo, API o nombre es externo al proyecto: "
                     "usa web_search(query='...') para encontrar el nombre o implementación correcta."
            )
            hints.append(
                f"\n⚡ EVALUACIÓN AGENTE [BUCLE EXACTO — '{_dup_name}' ×{_dup_count} mismos args]: "
                f"Estás repitiendo la MISMA llamada con el MISMO patrón '{str(_dup_pat)[:50]}'. "
                "Esto NUNCA producirá un resultado diferente. ACCIÓN OBLIGATORIA:\n"
                f"• Si '{_dup_name}' no encontró nada → lee el fichero: read_file(path)\n"
                f"• Usa smart_replace o context_before_edit para ver el contenido real\n"
                "• Cambia el patrón, usa edit_file con texto literal, o cambia de estrategia."
                + _ws_loop
            )

        # ── 11. Bash usado para grep/find/sed — sugerir tools especializadas ───
        _GREP_FIND_KWS = ("grep -r", "grep -R", "grep -rn", "grep -rl", "grep -l ",
                          "grep -L ", "grep -c ", "--include=", "find -name", "find -type",
                          "sed -i", "sed --in-place")
        _bash_antipattern_n = sum(
            1 for n, a_str, _ in self._last_tool_calls
            if n == "bash" and any(kw in str(a_str) for kw in _GREP_FIND_KWS)
        )
        if _bash_antipattern_n >= 1 and bash_n >= 2:
            hints.append(
                f"\n⚡ EVALUACIÓN AGENTE [{_bash_antipattern_n} bash con grep/find/sed]: "
                "Detectado uso de bash para operaciones con tools directas disponibles:\n"
                "  grep -r/rn/l/L/c → grep_code(pattern, directory, extensions=['c'])\n"
                "  find -name        → find_file(name='*.c', directory='src/')\n"
                "  sed -i            → edit_file / regex_replace / bulk_replace\n"
                "ESTAS LLAMADAS ESTÁN BLOQUEADAS — el agente las rechazará con ⛔."
            )

        # ── 12. Escalado a web_search — ≥4 errores en las últimas 6 acciones ─
        # Si el agente lleva muchos turnos fallando con errores de tecnología
        # (HTTP, API desconocida, import error, versión incompatible), debe buscar
        # la solución en internet en lugar de seguir adivinando.
        _last6 = self._last_tool_calls[-6:]
        if len(_last6) >= 4:
            _tech_err_kw = (
                "http error", "httperror", "status code", "connection refused",
                "modulenotfounderror", "importerror", "no module named",
                "attributeerror", "typeerror", "valueerror: ",
                "cannot import", "not found", "undefined", "404", "403", "500",
                "api error", "authentication failed", "invalid token",
                "permission denied", "ssl error", "certificate",
                "version", "deprecated", "unsupported",
            )
            _tech_errors = [
                r for _, _, r in _last6
                if isinstance(r, str) and any(kw in r.lower() for kw in _tech_err_kw)
            ]
            if len(_tech_errors) >= 4 and not _already_searched:
                # Extraer fragmento del error más reciente para construir la query
                _last_err = _tech_errors[-1]
                # Buscar la primera línea con contenido informativo
                _err_lines = [ln.strip() for ln in _last_err.splitlines() if ln.strip()]
                _err_snippet = next(
                    (ln for ln in _err_lines
                     if any(kw in ln.lower() for kw in _tech_err_kw)),
                    _err_lines[0] if _err_lines else "error"
                )[:120]
                hints.append(
                    f"\n⚡ EVALUACIÓN AGENTE [{len(_tech_errors)} errores técnicos sin resolver]: "
                    f"Llevas {len(_tech_errors)} intentos fallidos con errores técnicos. "
                    "OBLIGATORIO antes de reintentar: usa web_search para buscar la solución exacta.\n"
                    f"  Ejemplo: web_search(query='{_err_snippet[:80]}')\n"
                    "Busca el error exacto + versión + plataforma. "
                    "Si la búsqueda devuelve resultados, lee el más relevante antes de continuar."
                )

        # ── 13. Exploración intensa sin plan — sugerir crear plan ahora ─────────
        # Cuando el agente lleva muchas tool calls exploratorias (lecturas/búsquedas)
        # sin ninguna escritura y SIN plan activo, es señal de una tarea compleja
        # que se beneficiaría de un plan estructurado antes de implementar.
        _no_plan = not getattr(self, "_plan_tasks", [])
        _no_writes = _writes_n == 0
        _has_reads_count = sum(
            1 for n, _, _ in self._last_tool_calls
            if n in ("read_file", "read_files", "grep_code", "find_file", "find_files",
                     "find_dir", "ls_dir", "symbol_lookup", "lsp_symbols",
                     "lsp_workspace_symbols", "lsp_references", "multi_grep",
                     "code_compare", "explore", "analyze_codebase")
        )
        if _no_plan and _no_writes and _has_reads_count >= 5 and total >= 5:
            hints.append(
                f"\n⚡ EVALUACIÓN AGENTE [{_has_reads_count} exploraciones, sin plan activo]: "
                "Has realizado exploración extensiva. ANTES de implementar, crea un plan con:\n"
                "  plan_create(tasks=[\"Tarea 1: …\", \"Tarea 2: …\"], summary=\"Qué vas a hacer\")\n"
                "  • Para cada tarea: fichero exacto, qué cambiarás, por qué.\n"
                "  • Llama task_done() al completar cada tarea para avanzar el panel visual.\n"
                "Esto evita ediciones desorganizadas y hace el trabajo verificable."
            )

        # ── 14. Escrituras sin tests — recordatorio antes de declarar completado ─
        # Si el turno tiene ediciones/escrituras pero ninguna llamada a run_tests
        # o test_file, avisa para que no declare "He completado" sin verificar.
        _test_names = frozenset({"run_tests", "test_file", "run_tests_project"})
        _has_tests = any(n in _test_names for n, _, _ in self._last_tool_calls)
        _modify_names = frozenset({"edit_file", "write_file", "bulk_replace",
                                   "regex_replace", "edit_files", "patch_apply",
                                   "smart_replace"})
        _has_modifications = any(n in _modify_names for n, _, _ in self._last_tool_calls)
        if _has_modifications and not _has_tests and total >= 2:
            hints.append(
                f"\n⚡ EVALUACIÓN AGENTE [código modificado, tests no ejecutados]: "
                "Has editado ficheros en este turno pero aún no has ejecutado tests. "
                "OBLIGATORIO antes de declarar completado:\n"
                "  run_tests(path='tests/')  — suite completa\n"
                "  test_file(path='tests/test_X.py')  — fichero específico\n"
                "No puedes escribir \"He completado todas las tareas.\" sin haber verificado con tests."
            )

        # ── 15. Turno silencioso — el modelo ejecuta tools sin comunicar nada ──
        # Detecta cuando el agente lleva ≥2 tool calls en el turno sin haber
        # emitido ningún texto al usuario. El usuario no puede ver los resultados
        # de las tools, por lo que el silencio total deja al usuario sin contexto.
        if len(self._last_tool_calls) >= 2 and not getattr(self, "_turn_text_emitted", True):
            hints.append(
                f"\n⚡ EVALUACIÓN AGENTE [{len(self._last_tool_calls)} tools, sin texto al usuario]: "
                "Llevas varias tool calls sin emitir ningún mensaje al usuario. "
                "El usuario NO ve los resultados de las tools — SOLO ve tu texto. "
                "OBLIGATORIO en la siguiente respuesta: escribe al menos UNA frase describiendo "
                "qué estás haciendo o qué has encontrado. Ejemplos:\n"
                "  • 'Revisando [fichero] para localizar la función de [nombre]...'\n"
                "  • 'He encontrado el problema en [fichero], aplico el fix:'\n"
                "  • 'Explorando la estructura del módulo [nombre]...'"
            )

        # ── 16. Checkpoint de tarea — inyecta estado en auto-continúas ─────────
        # Solo se muestra a partir del 1.er auto-continue y cuando hay ficheros
        # modificados, para evitar redundancia en el primer turno.
        _ckpt_modified = getattr(self, "_task_modified_files", set())
        _ckpt_test = getattr(self, "_task_last_test", "")
        _ckpt_ac = getattr(self, "_auto_continue_count", 0)
        if _ckpt_ac > 0 and _ckpt_modified:
            _ckpt_list = "\n".join(f"  • {p}" for p in sorted(_ckpt_modified)[:8])
            _ckpt_test_line = (
                f"\n- Tests (último resultado): {_ckpt_test[:150]}" if _ckpt_test else ""
            )
            hints.append(
                f"\n📍 CHECKPOINT [auto-continúa {_ckpt_ac}]:\n"
                f"- Ficheros YA modificados en esta tarea:\n{_ckpt_list}{_ckpt_test_line}\n"
                f"No reapliques cambios ya realizados. Continúa desde donde lo dejaste."
            )

        return "".join(hints)

    # ── Operaciones de memoria con visual por fases ──────────────────────────

    def _execute_mem_save(self, args: dict) -> str:
        """Guarda una memoria con 3 fases visuales en el spinner de status.

        El spinner lee self._tool_phase en cada tick (0.2 s) y muestra la fase
        activa sin necesidad de llamadas adicionales a _status_cb.
        """
        mem_name    = str(args.get("name", "memory"))
        content     = str(args.get("content", ""))
        description = str(args.get("description", ""))

        # Fase 1: Recall — buscar memorias relacionadas
        self._tool_phase = "Recalling memories…"
        n_recalled = 0
        if self.memory._embed and self.memory._embed.is_available():
            try:
                hits = self.memory.search(content[:300], top_k=3)
                n_recalled = len(hits)
            except Exception:
                pass
        r_word = "memory" if n_recalled == 1 else "memories"

        # Fase 2: Write
        self._tool_phase = (
            f"Recalled {n_recalled} {r_word}, writing 1 memory…"
        )
        self.memory.save(mem_name, content, description)

        # Fase 3: Done
        self._tool_phase = ""
        # Registrar en _session_mems para el reset visual de compactación
        self._session_mems.append(mem_name)
        desc_line = f"\n{description}" if description else ""
        return (
            f"Recalled {n_recalled} {r_word}, wrote 1 memory"
            f"{desc_line}\nname: {mem_name}"
        )

    # ── Plan propio del agente — tools plan_create / task_done ───────────────

    def _execute_plan_create(self, tasks: list, summary: str = "") -> str:
        """Crea o reemplaza el plan de tareas del agente.

        El agente llama a esta herramienta cuando decide planificar su trabajo.
        Muestra un panel visual al usuario y activa el modo multi-tarea en el spinner.
        """
        if not isinstance(tasks, list) or not tasks:
            return "Error: 'tasks' debe ser una lista no vacía de strings."
        tasks = [str(t).strip() for t in tasks if str(t).strip()]
        if not tasks:
            return "Error: todas las tareas están vacías."

        # Crear plan
        self._plan_tasks = [
            {"text": t, "status": "pending", "start_ts": 0.0, "end_ts": 0.0}
            for t in tasks
        ]
        self._plan_tasks[0]["status"] = "active"
        self._plan_tasks[0]["start_ts"] = time.time()

        # Mostrar panel visual al usuario
        if not self.capture_output:
            from rich.markup import escape as _mesc
            _ic = _TASK_ICON_COLORS[int(time.time()) % len(_TASK_ICON_COLORS)]
            _n = len(tasks)
            self._print(
                f"\n  [{_ic}]◈[/{_ic}]  [bold]Plan de ejecución[/bold]  "
                f"[dim]({_n} tarea{'s' if _n != 1 else ''})[/dim]"
            )
            if summary:
                self._print(f"  [dim italic]{_mesc(summary[:120])}[/dim italic]")
            for i, task in enumerate(tasks[:12], 1):
                _short = (task[:80] + "…") if len(task) > 80 else task
                _icon  = "◼" if i == 1 else "◻"
                self._print(f"  [dim]  {_icon} {i}. {_mesc(_short)}[/dim]")
            if len(tasks) > 12:
                self._print(f"  [dim]  … +{len(tasks) - 12} más[/dim]")
            self._print(
                f"\n  [bold cyan]↻[/bold cyan]  "
                f"[cyan]Ejecutando tarea 1/{_n}: {_mesc(tasks[0][:60])}…[/cyan]"
            )

        first = tasks[0][:80]
        return (
            f"Plan creado: {len(tasks)} tareas. "
            f"Activa ahora [1/{len(tasks)}]: '{first}'. "
            f"Usa task_done() al completar cada tarea para avanzar."
        )

    def _execute_task_done(self, message: str = "") -> str:
        """Marca la tarea activa como completada y activa la siguiente.

        El agente llama a esta herramienta cuando termina cada tarea del plan.
        Si era la última tarea, devuelve instrucción de finalización.
        """
        if not self._plan_tasks:
            return "No hay plan activo. Usa plan_create(tasks=[...]) primero."

        active_idx = next(
            (i for i, t in enumerate(self._plan_tasks) if t["status"] == "active"), -1
        )
        if active_idx == -1:
            # Si no hay activa, buscar la primera pendiente
            pending_idx = next(
                (i for i, t in enumerate(self._plan_tasks) if t["status"] == "pending"), -1
            )
            if pending_idx == -1:
                return "Todas las tareas ya están completadas."
            active_idx = pending_idx
            self._plan_tasks[active_idx]["status"] = "active"
            self._plan_tasks[active_idx]["start_ts"] = time.time()

        # Marcar como done
        self._plan_tasks[active_idx]["status"] = "done"
        self._plan_tasks[active_idx]["end_ts"] = time.time()

        done_count = sum(1 for t in self._plan_tasks if t["status"] == "done")
        total = len(self._plan_tasks)

        # Activar la siguiente pendiente
        next_idx = next(
            (i for i, t in enumerate(self._plan_tasks) if t["status"] == "pending"), -1
        )
        if next_idx >= 0:
            self._plan_tasks[next_idx]["status"] = "active"
            self._plan_tasks[next_idx]["start_ts"] = time.time()
            next_text = self._plan_tasks[next_idx]["text"][:80]
            return (
                f"✔ Tarea {active_idx + 1}/{total} completada. "
                f"Activa ahora [{done_count + 1}/{total}]: '{next_text}'. "
                f"Continúa con ella directamente."
            )

        # Todas completadas
        return (
            f"✔ Todas las {total} tareas completadas. "
            f"Responde al usuario con un resumen conciso y di "
            f"'He completado todas las tareas.' como primera frase."
        )

    def _auto_save_task_memory(self, output_parts: list[str]) -> None:
        """Auto-guarda una memoria resumen al final de tareas significativas.

        Condiciones (todas deben cumplirse):
        - ≥ 5 tool calls en el turno
        - ≥ 1 escritura de fichero
        - No se llamó mem_save manualmente este turno
        - No estamos en modo capture_output (subagente)
        """
        if self.capture_output:
            return
        if any(n == "mem_save" for n, _, _ in self._last_tool_calls):
            return  # el LLM ya guardó memoria manualmente

        total = len(self._last_tool_calls)
        writes = sum(
            1 for n, _, _ in self._last_tool_calls
            if n in ("edit_file", "write_file", "bulk_replace", "regex_replace", "edit_files")
        )
        if total < 5 or writes < 1:
            return

        last_response = (output_parts[-1].strip() if output_parts else "").strip()
        if len(last_response) < 50:
            return  # respuesta demasiado corta para ser útil

        # Nombre basado en fecha + workspace
        from datetime import date as _date
        today  = _date.today().isoformat()
        ws     = os.path.basename(str(self.config.workspace or "")) or "workspace"
        mem_name = f"task_{today}_{ws}"

        # Resumen: primeras 600 chars de la última respuesta LLM + ficheros modificados
        summary = last_response[:600]
        modified = [
            json.loads(a_str).get("path", "?")
            for n, a_str, _ in self._last_tool_calls
            if n in ("edit_file", "write_file") and a_str
        ]
        if modified:
            files_str = ", ".join(os.path.basename(f) for f in modified[:6])
            summary += f"\n\nFicheros modificados: {files_str}"

        desc = f"Tarea {today}: {last_response.splitlines()[0][:80]}"
        save_args = {"name": mem_name, "content": summary, "description": desc}

        result = self._execute_mem_save(save_args)
        # Mostrar el bloque de memoria en la conversación (igual que una tool call normal)
        self._show_tool_block("mem_save", save_args, result, allowed=True)

    def _execute_tool(self, name: str, args: dict) -> str:
        """Ejecuta una tool con caché de reads y detección de writes duplicados.

        - Pre-flight: bloquea creación/ejecución de scripts temporales.
        - mem_save: ruta especial con fases visuales en status bar.
        - Reads idénticos dentro del turno devuelven el resultado cacheado sin re-ejecutar.
        - Writes con args idénticos dentro del turno devuelven una advertencia de duplicado
          en lugar de aplicar el cambio de nuevo (previene duplicación de código).
        """
        # Pre-flight: bloquea scripts temporales y heredocs antes de ejecutar nada
        rejection = self._precheck_tool_call(name, args)
        if rejection is not None:
            return rejection

        # mem_save: ejecución especial con fases visuales en el spinner
        if name == "mem_save":
            return self._execute_mem_save(args)

        import hashlib
        key = f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
        key_hash = hashlib.md5(key.encode()).hexdigest()

        if name in self._CACHEABLE_TOOLS:
            cached = self._turn_read_cache.get(key_hash)
            if cached is not None:
                return f"[caché] {cached}"
            result = self.registry.call(name, args)
            self._turn_read_cache[key_hash] = str(result)
            # Registrar fichero leído para el reset visual post-compactación
            # y para el guard de edit_file (exige read previo)
            if name == "read_file":
                path = args.get("path", "")
                if path and not str(result).startswith("Error"):
                    n_lines = str(result).count('\n') + 1
                    self._session_reads.append((str(path), n_lines, False))
                    self._turn_read_paths.add(str(path))
            elif name in ("read_files", "read_project_file"):
                # read_files: lista de paths
                for _p in (args.get("paths") or []):
                    if _p:
                        self._turn_read_paths.add(str(_p))
            return result

        if name in self._WRITE_TOOLS:
            prev = self._turn_write_seen.get(key_hash)
            if prev is not None:
                return (
                    f"⚠️ DUPLICADO BLOQUEADO: {name} con los mismos argumentos ya se ejecutó "
                    f"en este turno.\nResultado anterior: {prev[:300]}\n"
                    "Usa read_file para verificar el estado actual antes de repetir."
                )
            result = self.registry.call(name, args)
            result_str = str(result)
            # Añadir sugerencia cuando write_file falla por permisos (volumen Docker o sistema)
            if (name == "write_file" and "Permission denied" in result_str
                    and "Errno 13" in result_str):
                _wp = args.get("path", "")
                result_str += (
                    "\n\n💡 Tip: Permission denied suele indicar ruta de volumen Docker o "
                    "directorio de sistema. Para escribir DENTRO de un contenedor:\n"
                    f"  1. write_file(path='~/.oocode/tmp/{os.path.basename(_wp)}', content='...') "
                    "— escribe en el host\n"
                    "  2. docker_cp(src='~/.oocode/tmp/...' , dst='CONTAINER:/ruta/destino/') "
                    "— copia al contenedor\n"
                    "  O usa docker_exec(container='NAME', command='cat > /ruta << ...')"
                )
                result = result_str
            self._turn_write_seen[key_hash] = result_str
            # Registrar fichero editado para el reset visual post-compactación
            path = args.get("path", "")
            if path and not result_str.startswith(("Error", "⚠️", "⛔")):
                self._session_reads.append((str(path), None, True))
                # Invalidar el fichero en el RAG para que se re-indexe en el próximo turno
                _rag = getattr(self, "_workspace_rag", None)
                if _rag is not None:
                    try:
                        _rag.invalidate_file(path)
                    except Exception:
                        pass
                # Invalidar caché del system prompt para que el próximo call use RAG fresco
                self._sys_prompt_cache = None
                self._turn_rag_snippet = None
            return result

        return self.registry.call(name, args)

    # ── Truncación de tool results largos ────────────────────────────────────

    def _truncate_tool_result(self, result: str) -> str:
        """Trunca resultados de herramientas muy largos para no saturar el contexto."""
        max_chars = self.config.max_tool_result_tokens * 3  # ~3 chars/token
        if len(result) <= max_chars:
            return result
        lines = result.splitlines()
        kept: list[str] = []
        chars = 0
        for line in lines:
            chars += len(line) + 1
            if chars > max_chars:
                remaining = len(lines) - len(kept)
                kept.append(f"... [truncado: {remaining} líneas más — usa offset para continuar]")
                break
            kept.append(line)
        return "\n".join(kept)

    # ── Post-procesado de resultados de búsqueda ──────────────────────────────

    # Tools de búsqueda cuyo abuso de llamadas vacías se quiere detectar
    _SEARCH_TOOLS = frozenset({
        "grep_code", "multi_grep", "find_file", "find_files", "find_dir",
        "symbol_lookup", "code_search",
    })

    # Patrones de error en output bash que requieren orientación específica
    _BASH_ERR_PATTERNS: list[tuple[str, str]] = [
        ("no such file or directory",
         "⚡ AGENTE [fichero no encontrado]: verifica la ruta con ls_dir(path) o find_file(name). "
         "Usa rutas absolutas — el cwd puede no ser el esperado."),
        ("command not found",
         "⚡ AGENTE [comando no encontrado]: el binario no está instalado o no está en el PATH. "
         "Comprueba con bash('which cmd') o bash('type cmd')."),
        ("permission denied",
         "⚡ AGENTE [permiso denegado]: sin permisos para este fichero/directorio. "
         "Comprueba con file_stat(path) o ls_dir(path) para ver los permisos actuales."),
        ("traceback (most recent call last)",
         "⚡ AGENTE [excepción Python]: el script Python falló. "
         "Corrige el error antes de continuar. Para probar código usa python_exec(code=...)."),
        ("syntaxerror:",
         "⚡ AGENTE [SyntaxError Python]: error de sintaxis en el código. "
         "Revisa el código con read_file antes de ejecutarlo de nuevo."),
        ("modulenotfounderror:",
         "⚡ AGENTE [módulo no encontrado]: instala el paquete con pip_tool(action='install', packages=['nombre'])."),
    ]

    def _postprocess_tool_result(self, name: str, args: dict, result: str) -> str:
        """Post-procesado de resultados:
        1. Detecta bucles de búsqueda vacíos → hint para cambiar estrategia.
        2. Detecta errores bash comunes → orientación específica.
        """
        # ── Detección de errores bash con orientación específica ──────────────
        if name == "bash":
            result_lower = result.lower()
            # Solo actuar si hay señal clara de error (no para outputs normales largos)
            for kw, guidance in self._BASH_ERR_PATTERNS:
                if kw in result_lower:
                    result = result + f"\n\n{guidance}"
                    break  # solo el primer match — no acumular hints

        # ── Detector de ediciones regex sin coincidencias ─────────────────────
        _EDIT_TOOLS = ("regex_replace", "bulk_replace")
        _NO_MATCH_KW = "no se encontraron coincidencias"
        if name in _EDIT_TOOLS and _NO_MATCH_KW in result.lower():
            self._failed_edit_streak += 1
            pat = str(args.get("pattern", args.get("old", str(args)[:60])))[:80]
            self._failed_edit_patterns.append(pat)
            if self._failed_edit_streak == 1:
                hint = (
                    f"\n\n⚡ AGENTE [regex sin coincidencias]: El patrón '{pat}' no existe tal como está.\n"
                    "SIGUIENTE PASO OBLIGATORIO antes de reintentar:\n"
                    "• read_file(path) → ve el contenido REAL del fichero\n"
                    "• Copia el texto exacto → usa edit_file(old_string='...literal...')\n"
                    "• O usa smart_replace(file, pattern, replacement) — muestra contexto si falla\n"
                    "• Regex tip: puede que haya espacios/tabs diferentes, o el texto cambia de línea."
                )
            else:
                tried = self._failed_edit_patterns[-5:]
                hint = (
                    f"\n\n⚡ AGENTE [BUCLE DETECTADO — {self._failed_edit_streak} regex fallidas seguidas]: "
                    f"Patrones probados: {tried}.\n"
                    "⛔ PARA ahora. Proceso obligatorio:\n"
                    "1. read_file(path) — lee el fichero completo para ver el texto real\n"
                    "2. Identifica las líneas exactas a cambiar (con sus números de línea)\n"
                    "3. Usa edit_file(old_string='copia literal', new_string='...') — sin regex\n"
                    "   Si necesitas regex: verifica primero con grep_code(pattern, path)\n"
                    "   smart_replace(file, pattern, replacement) — busca + muestra contexto + aplica"
                )
            return result + hint

        # Reset si la edición tuvo éxito
        if name in _EDIT_TOOLS and _NO_MATCH_KW not in result.lower():
            self._failed_edit_streak = 0
            self._failed_edit_patterns = []

        # ── Detector de bucles de búsqueda vacíos ────────────────────────────
        is_empty = ("Sin resultados" in result or "No se encontró" in result
                    or result.strip() == "" or result.strip() == "(sin resultados)")

        if name in self._SEARCH_TOOLS and is_empty:
            self._empty_search_streak += 1
            pat = (args.get("pattern") or args.get("name") or args.get("symbol")
                   or args.get("patterns") or str(args)[:60])
            if isinstance(pat, list):
                pat = str(pat[:3])
            self._empty_search_patterns.append(str(pat)[:80])

            if self._empty_search_streak >= 2:
                tried = self._empty_search_patterns[-5:]  # últimos 5
                _ws_already = any(
                    n in ("web_search", "search_web", "searxng_search")
                    for n, _, _ in self._last_tool_calls
                )
                _ws_escalate = (
                    "" if _ws_already
                    else "\n• Si el símbolo o API no pertenece a este proyecto (es externo/librería): "
                         "usa web_search(query='nombre función o error exacto') para localizar su origen."
                )
                hint = (
                    f"\n\n⚡ AGENTE [{self._empty_search_streak} búsquedas consecutivas sin resultados]: "
                    f"Patrones probados: {tried}.\n"
                    "PARA y cambia de estrategia:\n"
                    "• Usa symbol_lookup(symbol='NOMBRE') — prueba múltiples patrones automáticamente.\n"
                    "• Lee el fichero directamente: read_file(path, offset=N, limit=50).\n"
                    "• El símbolo puede tener nombre diferente: usa multi_grep con variantes.\n"
                    "• Verifica el directorio: ls_dir(path)."
                    + _ws_escalate
                )
                return result + hint
        else:
            self._empty_search_streak = 0
            self._empty_search_patterns = []

        return result

    # ── Ciclo de vida ────────────────────────────────────────────────────────

    def _save_session_snapshot(self) -> None:
        """Guarda un snapshot del estado actual en ~/.oocode/snapshots/{agent_id}/."""
        if not self.config.snapshots_enabled:
            return
        try:
            from config import CONFIG_DIR
            snap_dir = CONFIG_DIR / "snapshots" / self.config.agent_id
            snap_dir.mkdir(parents=True, exist_ok=True)
            ctx_stats = self.context.stats()
            snap = {
                "session_id":    self.session.session_id,
                "timestamp":     time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "agent_id":      self.config.agent_id,
                "model":         self._active_model(),
                "workspace":     self.config.workspace,
                "tokens_used":   {
                    "input":  self.session.input_tokens,
                    "output": self.session.output_tokens,
                },
                "context": {
                    "messages":        ctx_stats["messages"],
                    "tokens_estimate": ctx_stats["tokens_estimate"],
                    "has_summary":     ctx_stats["has_summary"],
                    "summary":         self.context.summary or "",
                },
                "runtime": {
                    "think_level": getattr(self.rt, "think_level", "off"),
                    "reasoning":   getattr(self.rt, "reasoning", False),
                    "usage_mode":  getattr(self.rt, "usage_mode", "off"),
                },
                "plugins":  list(getattr(self.config, "plugins_enabled", [])),
                "rag_hits": getattr(getattr(self, "_workspace_rag", None), "last_hits", 0),
                "last_messages": [
                    {"role": m["role"], "content": str(m.get("content", ""))[:400]}
                    for m in self.context.messages[-6:]
                ],
            }
            import json as _json
            ts = snap["timestamp"].replace(":", "").replace("-", "")
            snap_file = snap_dir / f"snapshot_{ts}.json"
            snap_file.write_text(_json.dumps(snap, indent=2, ensure_ascii=False))
            log.debug("session_snapshot_saved", file=str(snap_file))

            # Rotación: eliminar snapshots más antiguos si se supera el límite
            max_snaps = getattr(self.config, "snapshots_max", 20)
            if max_snaps > 0:
                all_snaps = sorted(snap_dir.glob("snapshot_*.json"),
                                   key=lambda p: p.stat().st_mtime)
                for old in all_snaps[:-max_snaps]:
                    try:
                        old.unlink()
                    except Exception:
                        pass
        except Exception as exc:
            log.debug("session_snapshot_error", error=str(exc))

    def new_session(self) -> None:
        # Snapshot del estado antes de reiniciar
        self._save_session_snapshot()

        self.session.end()
        self.session = SessionManager(self.config.agent_id)
        self.session.start(self._active_model(), self.config.workspace)
        self.context.clear()

        # Escribir límite de sesión en memoria diaria: la nueva sesión no leerá
        # los summaries de compactación de sesiones anteriores del mismo día.
        try:
            self.ws.mark_new_session()
        except Exception:
            pass

        # Resetear estado interno residual (evita que _system_prompt use msg stale)
        self._last_user_msg      = ""
        self._last_response      = ""
        self._last_tool_calls    = []
        self._pending_usage_line = ""
        self._turn_mem_snippet   = None
        self._turn_rag_snippet   = None

        # Notifica al REPL/TUI para que limpie el historial de entrada en memoria
        if callable(getattr(self, '_on_new_session', None)):
            try:
                self._on_new_session()  # type: ignore[attr-defined]
            except Exception:
                pass

    def restore_session(self, session_id: str) -> int:
        messages = self.session.load_messages(session_id)
        self.context.clear()
        for msg in messages:
            self.context.messages.append(msg)
        return len(messages)

    # ── Turno principal ──────────────────────────────────────────────────────

    def run(self, user_message: str,
            images: Optional[list[str]] = None) -> Optional[str]:
        """Ejecuta un turno del agente.

        Args:
            user_message: texto del usuario.
            images: lista de rutas de imagen o strings base64 (solo si el modelo soporta visión).
        """
        if self.rt.activation == "mention" and not self.capture_output:
            if not user_message.lower().startswith(self.config.agent_name.lower()):
                return None

        # Si una compactación manual está en curso (hilo F3), esperar antes de empezar
        # el turno para evitar solapamiento con el contexto en modificación.
        if self._compact_running.is_set():
            self._compact_running.wait(timeout=30.0)

        self._last_user_msg    = user_message
        self._turn_mem_snippet = None   # recalcular snippet para este turno
        self._turn_rag_snippet = None   # recalcular RAG para este turno
        self._sys_prompt_cache = None   # invalidar cache de system prompt (lee ficheros de disco)
        self.memory.reset_turn_cache()  # 1 embed por turno, no por sesión
        self.registry.clear_cache()     # caché intra-turno: fresca cada turno
        self._task_modified_files = set()   # checkpoint: ficheros modificados en esta tarea
        self._task_last_test = ""           # checkpoint: último resultado de tests

        # Re-registrar tools de servidores MCP que hayan cambiado (notifications/tools/list_changed)
        _mcp_pool = getattr(self, "_mcp_pool", None)
        if _mcp_pool is not None:
            changed = _mcp_pool.pop_tools_changed()
            if changed:
                from agent.mcp_client import mcp_tool_to_oocode
                for srv_name in changed:
                    client = _mcp_pool.get_client(srv_name)
                    if client and client.is_alive:
                        _existing = frozenset(self.registry._tools.keys())
                        for _t in client.tools:
                            _tname, _tfn, _tschema = mcp_tool_to_oocode(
                                client, _t, existing_names=_existing)
                            self.registry.register(_tname, _tfn, _tschema)
                        log.info("mcp_tools_updated", server=srv_name, count=len(client.tools))

        # Mensaje con imágenes opcionales (solo si el modelo soporta visión)
        if images and self._model_supports_images():
            img_b64 = _load_images_b64(images)
            if img_b64:
                self.context.add("user", user_message, images=img_b64)
                self.session.log_message("user", f"[imagen×{len(img_b64)}] {user_message}")
                log.debug("user_message_with_images", chars=len(user_message),
                          images=len(img_b64))
            else:
                self.context.add("user", user_message)
                self.session.log_message("user", user_message)
        else:
            self.context.add("user", user_message)
            self.session.log_message("user", user_message)
        self.chatlog.log_user(user_message)
        log.debug("user_message", chars=len(user_message))
        # tools se calcula dentro del while para refrescar si el registry cambia
        # (p.ej. si un servidor MCP actualiza su lista durante el turno)
        _tools_cache: list[dict] | None = None

        # Actualizar permisos según elevated.
        # "full"/"on"/"off" → resolve_mode() lo maneja; aplica a CUALQUIER tool.
        # "ask"             → restaura _perms a los defaults salvo personalizaciones.
        if not self.capture_output and self.rt.elevated != self._last_elevated_applied:
            _def  = _DEFAULT_CONFIG["permissions"]
            _elev = self.rt.elevated
            # Propagar nivel a PermissionManager (aplica a todas las tools vía resolve_mode)
            self.permissions.set_elevated(_elev)
            # Solo "ask" necesita actualizar _perms: restaura defaults respetando
            # cualquier personalización explícita del usuario (auto, deny, …).
            # "on"/"full"/"off" los maneja resolve_mode() directamente sin tocar _perms,
            # lo que evita sobreescribir permisos "deny" configurados por el usuario.
            if _elev == "ask":
                for _tool in list(self.permissions._perms):
                    _bare    = self.permissions._bare_name(_tool)
                    _lookup  = _bare if _bare else _tool
                    _default = _def.get(_lookup, "ask")
                    # Respetar cualquier personalización explícita del usuario:
                    # si difiere del default (auto elevado, deny bloqueado…), no tocar.
                    user_perm = (self.config.permissions.get(_lookup)
                                 or self.config.permissions.get(_tool))
                    if user_perm is not None and user_perm != _default:
                        continue
                    self.permissions._perms[_tool] = _default
            self._last_elevated_applied = _elev

        full_output_parts: list[str] = []
        self._last_tool_calls = []  # resetea al inicio de cada turno
        self._pending_usage_line = ""  # resetea el usage pendiente
        self._auto_continue_count = 0  # resetea contador de auto-continuaciones
        self._turn_text_emitted = False  # ningún texto emitido al usuario aún

        # Conectar hooks y diff renderer al canal TUI (_print) para visualización correcta.
        # Siempre usamos self._print: funciona para TUI, REPL y subagentes (prefija │).
        import tools.hooks as _hooks_mod
        import tools.diff_renderer as _diff_mod
        _hooks_mod.set_hook_print_fn(self._print)
        _diff_mod._dprint_fn = self._print
        self._empty_search_streak = 0   # resetea detector de bucles vacíos
        self._empty_search_patterns = []
        self._failed_edit_streak = 0    # resetea detector de ediciones fallidas
        self._failed_edit_patterns = []
        self._turn_read_cache = {}      # resetea caché de reads
        self._turn_write_seen = {}      # resetea registro de writes
        self._turn_read_paths = set()   # resetea rutas leídas este turno
        self._turn_written_scripts = set()  # resetea scripts escritos este turno
        self._bash_block_counts = {}        # resetea contador de bloqueos bash
        self._tool_phase = ""               # resetea fase de operación de memoria
        self._tool_current_file = ""        # resetea fichero actual de búsqueda
        _tool_progress.set_progress_callback(None)  # limpia callback de progreso
        self._turn_block = []               # resetea buffer compacto TUI
        self._turn_block_has_header = False  # resetea flag de header mostrado
        self._turn_expanded = False
        self._plan_tasks = []               # resetea task progress panel

        # ── Detección pre-vuelo de tareas múltiples ───────────────────────────
        # Detecta listas numeradas/bullets en el mensaje del usuario y muestra
        # un indicador visual ANTES de enviar al modelo, y las inyecta en
        # _turn_guidance() para que el modelo las aborde todas de una vez.
        self._pending_tasks = self._detect_tasks(user_message)
        if self._pending_tasks:
            _n_tasks = len(self._pending_tasks)
            _s = "s" if _n_tasks != 1 else ""
            # Inicializar task progress panel
            self._plan_tasks = [
                {"text": t, "status": "pending", "start_ts": 0.0, "end_ts": 0.0}
                for t in self._pending_tasks
            ]
            self._plan_tasks[0]["status"] = "active"
            self._plan_tasks[0]["start_ts"] = time.time()
            if not self.capture_output:
                _phrase_tmpl = random.choice(_TASK_PREFLIGHT_PHRASES)
                _phrase      = _phrase_tmpl.format(n=_n_tasks)
                _icon_col    = _TASK_ICON_COLORS[int(time.time()) % len(_TASK_ICON_COLORS)]
                self._print(
                    f"\n  [{_icon_col}]⊡[/{_icon_col}]  [cyan]{_phrase}[/cyan]"
                )

        total_inp, total_out = 0, 0
        self._turn_inp = 0
        self._turn_out = 0
        t_run_start = time.time()
        self._task_start_time = t_run_start
        self._task_elapsed = 0.0
        _had_tools_prev = False        # True cuando la iteración anterior ejecutó tools
        _last_tool_call_count = 0      # número acumulado de tool calls de iteraciones previas

        while True:
            # /kill local interrumpe entre iteraciones
            if self._kill_requested:
                self._kill_requested = False
                if any(c >= 3 for c in self._bash_block_counts.values()):
                    # Parada forzada por bloqueo bash repetido
                    _cat = next(k for k, v in self._bash_block_counts.items() if v >= 3)
                    self._print(
                        f"\n  [bold red]⛔[/bold red]  Agente detenido — {self._bash_block_counts[_cat]} intentos "
                        f"de usar bash para '{_cat}' (operación permanentemente bloqueada).\n"
                        "  Usa la tool equivalente o escribe al usuario para pedir ayuda.\n"
                        "  Tip: [dim]/elevated on[/dim] amplía permisos si realmente necesitas bash."
                    )
                else:
                    self._print("\n  [yellow]↯[/yellow]  Turno interrumpido por /kill.")
                break

            # Kill externo desde /subagents kill
            if self._ext_kill is not None and self._ext_kill.is_set():
                self._print("\n  [yellow]↯[/yellow]  Subagente detenido por el usuario.")
                break

            # Steer: nueva instrucción del usuario via /subagents steer
            if self._steer_queue is not None:
                try:
                    import queue as _q
                    new_instr = self._steer_queue.get_nowait()
                    self._print(
                        f"\n  [bold cyan]⟳  Steer:[/bold cyan]  [dim]{new_instr}[/dim]\n"
                    )
                    # Prefijo [STEER] para que el modelo reconozca la instrucción
                    # como una actualización de tarea y no como input del usuario final.
                    self.context.add("user", f"[STEER] {new_instr}")
                except _q.Empty:
                    pass

            # Detectar si la iteración anterior ejecutó tools (para suprimir ↻ espurio)
            _new_count = len(self._last_tool_calls)
            _had_tools_prev = _new_count > _last_tool_call_count
            _last_tool_call_count = _new_count

            # Actualizar el color del prefijo cada iteración del while
            self._subagent_color_idx += 1

            # Compactar si el contexto supera el umbral (antes de construir el prompt)
            if self.context.should_compact():
                self._do_compact(with_summary=True)

            # Advertencia preventiva: thinking ON + contexto muy lleno = riesgo de
            # truncamiento XML. Avisar al usuario antes de que falle.
            _think_active = getattr(self.rt, "think_level", "off") != "off"
            if _think_active and not self.capture_output and not self.is_subagent:
                _ctx_s = self.context.stats()
                _ctx_pct = _ctx_s["tokens_estimate"] / max(_ctx_s["max_tokens"], 1)
                if _ctx_pct > 0.65:
                    self._print(
                        f"\n  [yellow]⚠[/yellow]  Contexto al "
                        f"{int(_ctx_pct*100)}% con thinking ON — riesgo de truncamiento XML. "
                        "Considera /think off o /compact.\n"
                    )

            # Durante llamada al LLM el separador muestra el proyecto
            self._sep_label = ""

            # Refrescar schemas de tools en cada iteración (captura cambios MCP en caliente)
            _tools_cache = self._filtered_schemas(self._last_user_msg)
            messages = self.context.get_messages(system=self._system_prompt())
            self._trace_header(messages)
            text, tool_calls, inp, out = self._stream_response(messages, _tools_cache)

            # ── Fallback por timeout ────────────────────────────────────────────
            if text == _TIMEOUT_SENTINEL:
                _actual_timeout = self.config.model_timeout(self._active_model())
                if self.config.fallback_active_config:
                    _fb_model = self.config.fallback_model
                    _to_secs  = _actual_timeout
                    self._print(
                        f"\n  [bold yellow]⚡  Timeout ({_to_secs}s) — "
                        f"usando fallback:[/bold yellow]  [cyan]{_fb_model}[/cyan]\n"
                    )
                    log.debug("fallback_trigger", timeout=_to_secs, fallback=_fb_model)
                    self._fallback_active = True
                    try:
                        text, tool_calls, inp, out = self._stream_response(messages, _tools_cache)
                    finally:
                        self._fallback_active = False
                    if text == _TIMEOUT_SENTINEL:
                        text = (
                            f"Error: el modelo de fallback '{_fb_model}' también excedió "
                            f"el tiempo de espera ({_to_secs}s). Comprueba la conexión con "
                            "Ollama o aumenta `timeoutSeconds` en `models.configs` de oocode.json."
                        )
                        tool_calls = []
                        inp = out = 0
                else:
                    text = (
                        f"Error: timeout esperando respuesta del modelo "
                        f"({_actual_timeout}s). Configura un modelo de fallback "
                        "en `fallback.model` de oocode.json para reintentar automáticamente."
                    )
                    tool_calls = []
                    inp = out = 0

            total_inp += inp
            total_out += out
            self._turn_inp = total_inp
            self._turn_out = total_out
            if inp or out:
                self.session.log_usage(inp, out)

            # Respuesta vacía: el modelo no generó texto ni herramientas.
            # No añadir al contexto (evita contaminar el historial).
            if not text.strip() and not tool_calls:
                _max_ac = self.config.auto_continue_max
                _did_tools = bool(self._last_tool_calls)
                # Parar si todas las tareas del plan están done
                if self._all_plan_tasks_done():
                    log.debug("auto_continue_skip_done", reason="all_plan_tasks_done")
                    self._flush_turn_block()
                    break
                if _did_tools and _max_ac > 0 and self._auto_continue_count < _max_ac:
                    # Comprobar si el último mensaje del asistente es un informe de completado.
                    # Si lo es, el modelo ya terminó — no continuar innecesariamente.
                    _last_asst = next(
                        (m for m in reversed(self.context.messages)
                         if m.get("role") == "assistant"),
                        None,
                    )
                    _last_asst_text = _last_asst.get("content", "") if _last_asst else ""
                    if self._is_completion_report(_last_asst_text):
                        _pending_ct = sum(
                            1 for t in self._plan_tasks if t["status"] == "pending"
                        ) if self._plan_tasks else 0
                        if _pending_ct > 0:
                            # Hay tareas ◻ pendientes — el informe es prematuro; continuar
                            pass  # fall through → auto_continue_count++ abajo
                        else:
                            log.debug("auto_continue_skip_done",
                                      reason="completion_report_in_last_message")
                            self._mark_all_plan_tasks_done()
                            self._flush_turn_block()
                            break

                    # Hay trabajo activo → auto-continuar inyectando un mensaje de usuario
                    self._auto_continue_count += 1
                    _n = self._auto_continue_count
                    # Avanzar tarea del plan según iteración
                    if self._plan_tasks:
                        _tgt = min(_n, len(self._plan_tasks) - 1)
                        self._set_plan_task_active(_tgt)
                    # Solo mostrar ↻ si el modelo está realmente atascado (no procesando results)
                    if not self.capture_output and not _had_tools_prev:
                        self._print(
                            f"\n  [bold yellow]↻[/bold yellow]  [yellow]Auto-continúa ({_n}/{_max_ac})…[/yellow]"
                        )
                    log.debug("auto_continue", count=_n, max=_max_ac,
                              model=self._active_model(),
                              tools_done=len(self._last_tool_calls))
                    # Mensaje específico por tarea o genérico
                    if self._plan_tasks:
                        _pac_i = next((i for i, t in enumerate(self._plan_tasks)
                                       if t["status"] == "active"), -1)
                        if _pac_i >= 0:
                            _pac_t = self._plan_tasks[_pac_i]
                            _pac_ni = _pac_i + 1
                            _pac_msg = (f"Continúa con la tarea activa "
                                        f"({_pac_i + 1}/{len(self._plan_tasks)}): "
                                        f"{_pac_t['text']}.")
                            if _pac_ni < len(self._plan_tasks):
                                _pac_msg += f" Cuando termines, anuncia \"Tarea {_pac_ni + 1}:\"."
                        else:
                            _pac_msg = "Continúa con la tarea."
                    else:
                        _pac_msg = "Continúa con la tarea."
                    self.context.add("user", _pac_msg)
                    continue  # reiniciar el bucle sin romperlo
                # Sin más auto-continuaciones (o desactivado, o tarea sin tools)
                if not self.capture_output:
                    self._print(
                        "\n  [dim yellow]⚠  El modelo no ha producido respuesta. "
                        "Si la tarea está incompleta, indícame qué falta.[/dim yellow]"
                    )
                log.debug("empty_response", model=self._active_model(),
                          inp=inp, out=out, iteration=len(self._last_tool_calls))
                self._flush_turn_block()
                break

            # No reseteamos _auto_continue_count aquí: solo se resetea al inicio de run().
            # Así el contador se acumula correctamente a lo largo de todo el turno del usuario.
            assistant_msg: dict = {"role": "assistant", "content": text}
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    tc.model_dump(exclude_none=True) if hasattr(tc, "model_dump") else tc
                    for tc in tool_calls
                ]
            self.context.messages.append(assistant_msg)

            if text:
                self._advance_plan_task(text)  # actualiza task tracker según anuncio del modelo
                self._turn_text_emitted = True
                full_output_parts.append(text)
                self.session.log_message("assistant", text)
                self.chatlog.log_assistant(text)
                # Flush tools acumulados de iteraciones anteriores ANTES del nuevo ●.
                # Así todos los tools entre dos ● se agrupan en una sola línea ⎿.
                self._flush_turn_block()
                if not self.capture_output:
                    from rich.markup import escape as _mesc
                    import re as _re_bullet
                    _ac = COLOR_PRESETS.get(self.rt.accent_color, COLOR_PRESETS["cyan"])[1]
                    # strip de whitespace inicial: evita que ● quede en su propia línea
                    # (lstrip() también elimina espacios/tabs antes de \n, lo que lstrip('\n')
                    # no hacía — causa de "● …" cuando el modelo emite " \nPlan: ...")
                    text_clean = text.lstrip()
                    lines   = text_clean.split('\n', 1)
                    first   = lines[0].rstrip()
                    rest    = lines[1] if len(lines) > 1 else ""
                    # Detectar si la primera línea es un bloque markdown real (heading, lista,
                    # código, quote, tabla). Negrita (**texto**) NO es bloque — el * debe ir
                    # seguido de espacio para ser lista; **bold** tiene * seguido de *.
                    _s0 = first.lstrip()
                    _is_md_block = bool(_s0 and (
                        _s0[0] == '#' or                                           # heading
                        _s0.startswith('```') or _s0.startswith('~~~') or         # code fence
                        _s0[0] in ('|', '>') or                                   # table / quote
                        (len(_s0) >= 2 and _s0[0] in ('-', '+', '!') and _s0[1] in (' ', '\t')) or
                        (len(_s0) >= 2 and _s0[0] == '*' and _s0[1] in (' ', '\t'))  # lista * item
                    ))
                    _plain_first = bool(first and not _is_md_block)
                    if _plain_first:
                        # Quitar marcadores inline de negrita/cursiva del header (** y *)
                        # para mostrar "Plan: ..." en vez de "**Plan:**" en la línea ●
                        _first_clean = _re_bullet.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', first).strip()
                        if _first_clean:
                            first = _first_clean

                    if self._start_live_block_cb and tool_calls:
                        # TUI + hay tools: live block con ● pulsante y ⎿ actualizable
                        console.print()   # línea en blanco → buffer estático
                        if _plain_first:
                            # Texto plano: mostrar inline con ●; truncar al ancho del terminal
                            # en límite de palabra para evitar cortes mid-word.
                            # Reservamos 4 cols para el prefijo "  ● ".
                            try:
                                _cols = os.get_terminal_size().columns
                            except OSError:
                                _cols = 120
                            _max_hdr = max(60, _cols - 4)
                            if len(first) <= _max_hdr:
                                _hdr       = first
                                _body_extra = ""
                            else:
                                # Cortar en el último espacio antes de _max_hdr
                                _cut = first.rfind(' ', 0, _max_hdr)
                                if _cut > _max_hdr // 2:
                                    _hdr        = first[:_cut] + "…"
                                    _body_extra = first[_cut + 1:]
                                else:
                                    _hdr        = first[:_max_hdr - 1] + "…"
                                    _body_extra = first[_max_hdr - 1:]
                            _bullet_text = _mesc(_hdr)
                        else:
                            _bullet_text = "…"
                            _body_extra = ""
                        self._start_live_block_cb(_bullet_text)
                        self._live_tool_count = 0
                        # Resto del mensaje (markdown) al cuerpo del live block
                        _body = (_body_extra + "\n" + rest).lstrip('\n') if _body_extra else rest
                        if _plain_first and _body.strip():
                            console.print(Padding(Markdown(_body.lstrip('\n')), (0, 0, 0, 2)))
                        elif not _plain_first:
                            console.print(Padding(Markdown(text_clean), (0, 0, 0, 2)))
                    else:
                        # REPL o respuesta sin tools: ● estático normal
                        console.print()
                        if _plain_first:
                            console.print(f"  [bold {_ac}]●[/bold {_ac}] {_mesc(first)}")
                            if rest.strip():
                                console.print(Padding(Markdown(rest.lstrip('\n')), (0, 0, 0, 2)))
                        else:
                            console.print(f"  [bold {_ac}]●[/bold {_ac}]")
                            console.print(Padding(Markdown(text_clean), (0, 0, 0, 2)))

            if not tool_calls:
                # ── Registrar métricas de rendimiento ──────────────
                if self._last_tool_calls:
                    for _tc, _name, _args in self._last_tool_calls:
                        _tool_name = _name
                        _record_tool_metrics(_tool_name, 0.0, True)
                # ── Parar si todas las tareas del plan están done ──────────────
                if self._all_plan_tasks_done():
                    log.debug("auto_continue_skip_done", reason="all_plan_tasks_done_no_tools")
                    self._flush_turn_block()
                    break

                # ── Auto-continue si el modelo anunció un plan sin ejecutarlo ──
                # Detecta: respuesta con lista de pasos numerados/bullets + sin
                # historial de tool calls previo (= plan forward, no resumen).
                # Excepción: si el plan contiene "⚠ REQUIERE REVISIÓN", pausar y
                # esperar respuesta del usuario en lugar de continuar automáticamente.
                _max_ac = self.config.auto_continue_max
                _requires_review = (
                    text and (
                        "⚠ REQUIERE REVISIÓN" in text
                        or "REQUIERE REVISIÓN" in text
                        or "requiere revisión" in text.lower()
                    )
                )
                if _requires_review and not self.capture_output:
                    from rich.markup import escape as _mesc
                    self._print(
                        "\n  [bold yellow]⚠[/bold yellow]  [yellow]El agente ha marcado "
                        "este plan como pendiente de revisión.[/yellow]"
                    )
                    self._print(
                        "  [dim]Responde con tus indicaciones o envía [bold]/steer[/bold] "
                        "para redirigir antes de continuar.[/dim]"
                    )
                    self._flush_turn_block()
                    break
                if (text
                        and not self._last_tool_calls
                        and _max_ac > 0
                        and self._auto_continue_count < _max_ac
                        and not self.capture_output):
                    _plan_steps = self._detect_tasks(text)
                    if _plan_steps and len(_plan_steps) >= 2 and not self._is_completion_report(text):
                        self._auto_continue_count += 1
                        _n_ac = self._auto_continue_count
                        log.debug("auto_continue_plan",
                                  steps=len(_plan_steps), count=_n_ac, max=_max_ac)
                        # Primera auto-continuación: mostrar panel de plan antes de ejecutar
                        if _n_ac == 1:
                            from rich.markup import escape as _mesc
                            _ac_col = COLOR_PRESETS.get(self.rt.accent_color, COLOR_PRESETS["cyan"])[1]
                            _icon_c = _TASK_ICON_COLORS[int(time.time()) % len(_TASK_ICON_COLORS)]
                            self._print(
                                f"\n  [{_icon_c}]◈[/{_icon_c}]  "
                                f"[bold]Plan de ejecución[/bold]  "
                                f"[dim]({len(_plan_steps)} pasos)[/dim]"
                            )
                            for _si, _step in enumerate(_plan_steps[:10], 1):
                                _step_short = (_step[:78] + "…") if len(_step) > 78 else _step
                                self._print(
                                    f"  [dim]  {_si}.[/dim]  [dim]{_mesc(_step_short)}[/dim]"
                                )
                            self._print(
                                f"\n  [bold yellow]↻[/bold yellow]  [yellow]Ejecutando plan…[/yellow]"
                            )
                        else:
                            self._print(
                                f"\n  [bold yellow]↻[/bold yellow]  [yellow]Continuando "
                                f"({_n_ac}/{_max_ac})…[/yellow]"
                            )
                        # Sincronizar _plan_tasks con el plan refinado del LLM.
                        # Primera auto-continuación: si el LLM elaboró su propio plan
                        # (puede diferir del de usuario — pasos consolidados, reordenados),
                        # reemplazar _plan_tasks con los pasos del LLM para que el panel
                        # refleje la ejecución real, no solo las frases originales del usuario.
                        if _plan_steps and _n_ac == 1:
                            self._plan_tasks = [
                                {"text": t, "status": "pending", "start_ts": 0.0, "end_ts": 0.0}
                                for t in _plan_steps
                            ]
                            self._plan_tasks[0]["status"] = "active"
                            self._plan_tasks[0]["start_ts"] = time.time()
                        # Mensaje específico con contexto de tarea
                        if self._plan_tasks:
                            _pp_i = next((i for i, t in enumerate(self._plan_tasks)
                                          if t["status"] == "active"), 0)
                            _pp_t = self._plan_tasks[_pp_i]
                            _pp_msg = (f"Continúa ejecutando el plan. "
                                       f"Tarea activa ({_pp_i + 1}/{len(self._plan_tasks)}): "
                                       f"\"{_pp_t['text']}\".")
                            if _pp_i + 1 < len(self._plan_tasks):
                                _pp_msg += f" Anuncia \"Tarea {_pp_i + 2}:\" al avanzar."
                        else:
                            _pp_msg = ("Continúa ejecutando el plan que acabas de anunciar, "
                                       "paso a paso, usando las tools necesarias.")
                        self.context.add("user", _pp_msg)
                        continue

                # ── Auto-continue si el plan tiene tareas sin ejecutar ────────────
                # El modelo puede haber declarado "done" prematuramente (señal ignorada
                # en _advance_plan_task) o simplemente no haber ejecutado la tarea activa.
                # Si hay tareas active/pending y no superamos el límite, reinyectar.
                if (self._plan_tasks and not self._all_plan_tasks_done()
                        and _max_ac > 0 and self._auto_continue_count < _max_ac
                        and not self.capture_output):
                    _resume_idx = next(
                        (i for i, t in enumerate(self._plan_tasks)
                         if t["status"] in ("active", "pending")),
                        -1,
                    )
                    if _resume_idx >= 0:
                        self._set_plan_task_active(_resume_idx)
                        self._auto_continue_count += 1
                        _n = self._auto_continue_count
                        _rt = self._plan_tasks[_resume_idx]
                        _rn = _resume_idx + 1
                        _resume_msg = (
                            f"La tarea {_rn}/{len(self._plan_tasks)} "
                            f"\"{_rt['text'][:80]}\" aún no está completada. "
                            f"Continúa ejecutando con las tools necesarias. "
                            f"NO digas \"He completado todas las tareas\" hasta haber "
                            f"ejecutado todas las acciones requeridas con tools."
                        )
                        self._print(
                            f"\n  [bold yellow]↻[/bold yellow]  "
                            f"[yellow]Tarea {_rn} pendiente — retomando "
                            f"({_n}/{_max_ac})…[/yellow]"
                        )
                        log.debug("auto_continue_pending_task",
                                  task_idx=_resume_idx, count=_n, max=_max_ac)
                        self.context.add("user", _resume_msg)
                        continue

                break

            # ── Normaliza tool calls ────────────────────────────────────────────
            parsed_calls: list[tuple] = []
            for tc in tool_calls:
                name = tc.function.name
                name = _TOOL_ALIASES.get(name, name)
                args = tc.function.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                parsed_calls.append((tc, name, args))

            # ── Permisos: siempre secuencial (interactivo con el usuario) ──────
            # El display del call se hace en el loop de resultados (_show_tool_block),
            # no aquí, para mostrarlo junto al resultado (estilo Claude Code).
            # En modo 'ask' el permiso ya incluye el nombre en el prompt.
            allowed_map: dict[int, bool] = {}
            _block_mode = len(parsed_calls) > 1
            for idx, (_tc, name, args) in enumerate(parsed_calls):
                description = f"{name}({json.dumps(args, ensure_ascii=False)[:80]})"
                allowed_map[idx] = self.permissions.check(name, description)

            # ── Ejecución: paralela si hay >1 call y ninguna es bash ──────────
            # bash tiene side-effects secuenciales (cd, exports, etc.)
            _safe_parallel = (
                len(parsed_calls) > 1
                and not any(n == "bash" for _, n, _ in parsed_calls)
                and not self.capture_output   # subagentes: siempre secuencial
            )

            results_map: dict[int, str] = {}

            if _safe_parallel:
                names_label = " + ".join(n for _, n, _ in parsed_calls)
                self._sep_label = f"⚙ {names_label}…"

                _pool_done = threading.Event()
                _pool_start = time.time()

                # Spinner que sigue animando mientras el pool trabaja
                def _parallel_spinner() -> None:
                    fi2 = 0
                    while not _pool_done.wait(timeout=_POLL_INTERVAL):
                        if self._status_cb:
                            elapsed2   = time.time() - _pool_start
                            frame2     = _SPINNER_FRAMES[fi2 % len(_SPINNER_FRAMES)]
                            ctx_s2     = self.context.stats()
                            cpct2      = int(ctx_s2["tokens_estimate"] / max(ctx_s2["max_tokens"], 1) * 100)
                            pbar2      = _ctx_bar(ctx_s2["tokens_estimate"], ctx_s2["max_tokens"], 10, plain=True)
                            tok_p2     = (f"{_fmt_tokens(total_inp)}↑ {_fmt_tokens(total_out)}↓  ·  "
                                          if (total_inp or total_out) else "")
                            _t2p = _fmt_elapsed(elapsed2)
                            if elapsed2 > 25:
                                _ph2p = _NEAR_FINISH_PHRASES[(fi2 // 5) % len(_NEAR_FINISH_PHRASES)]
                                _tp2p = f"({_t2p} · {_ph2p})"
                            else:
                                _tp2p = f"({_t2p})"
                            mem_p2 = f"  ·  ⬡ {self.memory.last_hits} mem" if self.memory.last_hits > 0 else ""
                            rag_p2 = _rag_display(self._workspace_rag)
                            # Modo plan: ✶ + tarea activa, modo normal: frame + label
                            _act2 = next(
                                (t["text"] for t in getattr(self, "_plan_tasks", [])
                                 if t["status"] == "active"), ""
                            )
                            _thresh2p = int(getattr(self.context, "compact_threshold", 0.85) * 100)
                            _cbar2p   = _sfmt(_bar_style(cpct2, _thresh2p), pbar2)
                            if _act2:
                                _lbl2 = (_act2[:40] + "…") if len(_act2) > 40 else _act2
                                _up2  = f"  ·  ↑{_fmt_tokens(total_inp)}" if total_inp > 0 else ""
                                self._status_cb(f"{frame2}  {_lbl2}  ({_t2p}{_up2})\n")
                            else:
                                self._status_cb(
                                    f"{frame2}  {names_label} [paralelo]  {_tp2p}\n"
                                    f"↳  {tok_p2}ctx: {_cbar2p} {cpct2}%{mem_p2}{rag_p2}"
                                )
                            fi2 += 1

                _spin_t = threading.Thread(
                    target=_parallel_spinner, daemon=True, name="oocode-par-spin"
                )
                _spin_t.start()

                # Enviar todas las calls permitidas al pool
                # Usamos lista de pares (future|None, idx) — sin dict para evitar
                # la colisión de None como key cuando varias calls son denegadas.
                submitted: list[tuple] = []
                with ThreadPoolExecutor(
                    max_workers=min(len(parsed_calls), 4),
                    thread_name_prefix="oocode-tool",
                ) as pool:
                    for idx, (_tc, name, args) in enumerate(parsed_calls):
                        if allowed_map[idx]:
                            submitted.append((pool.submit(self._execute_tool, name, args), idx))
                        else:
                            submitted.append((None, idx))

                    for future, idx in submitted:
                        if future is None:
                            results_map[idx] = "Operación denegada."
                        else:
                            try:
                                results_map[idx] = future.result()
                            except Exception as exc:
                                results_map[idx] = f"Error: {exc}"

                _pool_done.set()
                _spin_t.join(timeout=1.0)

            else:
                # ── Ejecución secuencial con spinner animado ────────────────────
                # _pre_shown_idxs: tools cuyo header ya se mostró antes de ejecutar
                _pre_shown_idxs: set[int] = set()

                for idx, (_tc, name, args) in enumerate(parsed_calls):
                    # Parar si el agente fue kill-requested por una call anterior del mismo batch
                    if self._kill_requested:
                        results_map[idx] = "⛔ Operación cancelada — agente detenido por bloqueo bash."
                        continue
                    self._sep_label = f"⚙ {name}…"

                    if self._status_cb and allowed_map[idx]:
                        # Mostrar header de la tool ANTES de ejecutarla (◐ amarillo)
                        # para que el usuario vea inmediatamente qué se está ejecutando.
                        self._show_tool_running_header(name, args)
                        _pre_shown_idxs.add(idx)

                        # Lanzar spinner thread para tools que pueden tardar
                        _seq_done  = threading.Event()
                        _seq_start = time.time()
                        _is_subagent_tool = (name == "spawn_subagent")
                        _seq_color_cycle  = list(_SUBAGENT_COLORS) if _is_subagent_tool else ["cyan"]
                        # spawn_subagent: 500ms (reduce CPU durante ejecuciones largas)
                        _seq_poll = 0.5 if _is_subagent_tool else _POLL_INTERVAL

                        def _seq_spinner(
                            _name=name, _done=_seq_done,
                            _colors=_seq_color_cycle, _t0=_seq_start,
                            _poll=_seq_poll,
                        ) -> None:
                            _fi = 0
                            while not _done.wait(timeout=_poll):
                                elapsed2  = time.time() - _t0
                                frame2    = _SPINNER_FRAMES[_fi % len(_SPINNER_FRAMES)]

                                ctx_s2    = self.context.stats()
                                cpct2     = int(ctx_s2["tokens_estimate"] / max(ctx_s2["max_tokens"], 1) * 100)
                                pbar2     = _ctx_bar(ctx_s2["tokens_estimate"], ctx_s2["max_tokens"], 10, plain=True)
                                tok_p2    = (f"{_fmt_tokens(total_inp)}↑ {_fmt_tokens(total_out)}↓  ·  "
                                             if (total_inp or total_out) else "")
                                _t2 = _fmt_elapsed(elapsed2)
                                if elapsed2 > 25:
                                    _ph2 = _NEAR_FINISH_PHRASES[(_fi // 5) % len(_NEAR_FINISH_PHRASES)]
                                    _tp2 = f"({_t2} · {_ph2})"
                                else:
                                    _tp2 = f"({_t2})"
                                mem_s2 = f"  ·  ⬡ {self.memory.last_hits} mem" if self.memory.last_hits > 0 else ""
                                rag_s2 = _rag_display(self._workspace_rag)
                                # Mostrar fase de memoria o fichero actual de búsqueda
                                _phase = self._tool_phase
                                _cur_f = self._tool_current_file
                                if _phase:
                                    _label  = _phase
                                    _icon   = "⬡"
                                elif _cur_f:
                                    _sf2 = _cur_f.rsplit("/", 1)[-1][:30]
                                    _label  = f"{_name}…  ⎿ {_sf2}  {_tp2}"
                                    _icon   = frame2
                                else:
                                    _label  = f"{_name}…  {_tp2}"
                                    _icon   = frame2
                                _thresh2  = int(getattr(self.context, "compact_threshold", 0.85) * 100)
                                _cbar2    = _sfmt(_bar_style(cpct2, _thresh2), pbar2)
                                self._status_cb(
                                    f"{_icon}  {_label}\n"
                                    f"↳  {tok_p2}ctx: {_cbar2} {cpct2}%{mem_s2}{rag_s2}"
                                )
                                _fi += 1

                        _seq_spin = threading.Thread(
                            target=_seq_spinner, daemon=True,
                            name=f"oocode-seq-spin-{name[:8]}",
                        )
                        _seq_spin.start()
                        # Registrar callback de progreso para búsquedas
                        _is_prog_tool = name in (
                            "code_search", "grep_code", "grep_file", "multi_grep",
                            "symbol_lookup", "semantic_search",
                        )
                        self._tool_current_file = ""
                        if _is_prog_tool:
                            _tool_progress.set_progress_callback(
                                lambda _f, _s=self: setattr(_s, "_tool_current_file", _f)
                            )
                        results_map[idx] = self._execute_tool(name, args)
                        if _is_prog_tool:
                            _tool_progress.set_progress_callback(None)
                        self._tool_current_file = ""
                        _seq_done.set()
                        _seq_spin.join(timeout=1.0)
                    elif self._status_cb:
                        # Tool denegada — actualiza status una vez
                        ctx_s      = self.context.stats()
                        cpct       = int(ctx_s["tokens_estimate"] / max(ctx_s["max_tokens"], 1) * 100)
                        plain_bar  = _ctx_bar(ctx_s["tokens_estimate"], ctx_s["max_tokens"], 10, plain=True)
                        tok_part   = (f"{_fmt_tokens(total_inp)}↑ {_fmt_tokens(total_out)}↓  ·  "
                                      if (total_inp or total_out) else "")
                        _thr_d = int(getattr(self.context, "compact_threshold", 0.85) * 100)
                        _cb_d  = _sfmt(_bar_style(cpct, _thr_d), plain_bar)
                        self._status_cb(f"⚙  {name}…\n↳  {tok_part}ctx: {_cb_d} {cpct}%")
                        results_map[idx] = "Operación denegada."
                    else:
                        # Sin status_cb (modo REPL clásico o subagente)
                        if allowed_map[idx]:
                            if self.is_subagent:
                                # Subagente en TUI: sys.stdout → _AppWriter → convierte \r→\n,
                                # así que la animación con \r crea líneas sueltas en el buffer.
                                # Usar header estático y ejecutar directamente.
                                self._show_tool_running_header(name, args)
                                results_map[idx] = self._execute_tool(name, args)
                            else:
                                # REPL clásico: header animado verde→amarillo, blanco al terminar
                                results_map[idx] = self._run_animated_header(name, args)
                            _pre_shown_idxs.add(idx)
                        else:
                            results_map[idx] = "Operación denegada."

            # ── Encabezado agrupado para lotes de lecturas paralelas ─────────
            # "Reading N files…" al estilo Claude Code cuando todas las calls
            # del batch son operaciones de lectura (sin escritura ni bash).
            _READ_GROUP = frozenset((
                "read_file", "read_files", "grep_code", "grep_file",
                "find_file", "find_files", "find_dir", "ls_dir", "file_stat",
                "symbol_lookup", "multi_grep", "code_compare",
            ))
            _WRITE_GROUP = frozenset((
                "edit_file", "edit_files", "write_file", "regex_replace",
                "bulk_replace", "patch_apply",
            ))
            # En TUI mode el resumen agrupado se genera en _flush_turn_block
            if _safe_parallel and not self.capture_output and self._status_cb is None:
                _all_names = [n for _, n, _ in parsed_calls]
                _all_reads = all(n in _READ_GROUP for n in _all_names)
                _all_writes = all(n in _WRITE_GROUP for n in _all_names)
                _n = len(_all_names)
                if _all_reads and _n > 1:
                    self._print(
                        f"[bold green]●[/bold green] [bold]Reading {_n} files…[/bold]  "
                        f"[dim](ctrl+o para expandir)[/dim]"
                    )
                elif _all_writes and _n > 1:
                    self._print(
                        f"[bold green]●[/bold green] [bold]Updating {_n} files…[/bold]"
                    )

            # ── Logging y contexto (siempre secuencial, en orden original) ─────
            for idx, (_tc, name, args) in enumerate(parsed_calls):
                result  = results_map[idx]
                allowed = allowed_map[idx]
                self.session.log_tool_call(name, args, result)
                self.chatlog.log_tool_call(name, args, str(result))
                log.debug("tool_call", tool=name, allowed=allowed,
                          args=json.dumps(args, ensure_ascii=False)[:120])
                # Determinar modo de display:
                # suppress_header → batch agrupado (muestra solo ⎿ path, sin resultado)
                # pre_shown → header ya impreso antes de ejecutar (muestra solo resultado)
                _in_read_batch  = (_safe_parallel and not self.capture_output
                                   and all(n in _READ_GROUP for _, n, _ in parsed_calls)
                                   and len(parsed_calls) > 1)
                _in_write_batch = (_safe_parallel and not self.capture_output
                                   and all(n in _WRITE_GROUP for _, n, _ in parsed_calls)
                                   and len(parsed_calls) > 1)
                _is_pre_shown   = idx in _pre_shown_idxs if not _safe_parallel else False
                self._show_tool_block(name, args, str(result), allowed,
                                      block_mode=_block_mode,
                                      suppress_header=_in_read_batch or _in_write_batch,
                                      pre_shown=_is_pre_shown)
                if self.plugins and allowed:
                    self.plugins.fire("on_tool_result", name, args, str(result))
                args_str = json.dumps(args, ensure_ascii=False)
                self._last_tool_calls.append((name, args_str, str(result)))
                # ── Checkpoint tracking ───────────────────────────────────────
                if allowed:
                    _WRITE_CKPT = frozenset({
                        "write_file", "edit_file", "edit_files", "bulk_replace",
                        "smart_replace", "regex_replace", "patch_apply",
                    })
                    _WRITE_SFX = ("_write_file", "_edit_file", "_edit_files")
                    if name in _WRITE_CKPT or any(name.endswith(s) for s in _WRITE_SFX):
                        _wp = str(args.get("path") or args.get("file_path", ""))
                        if _wp:
                            self._task_modified_files.add(_wp)
                        for _wed in args.get("edits", []):
                            if isinstance(_wed, dict) and _wed.get("path"):
                                self._task_modified_files.add(str(_wed["path"]))
                    elif name in ("run_tests", "test_file"):
                        self._task_last_test = str(result)[:400]
                result_for_ctx = self._postprocess_tool_result(name, args, str(result))
                result_for_ctx = self._truncate_tool_result(result_for_ctx)
                tool_call_id = getattr(tc, "id", None) or name
                self.context.add_tool_result(tool_call_id, name, result_for_ctx)
            # _turn_block NO se vacía aquí: los tools se acumulan entre ●●.
            # El flush ocurre antes del siguiente ● o al salir del bucle.

        # Flush final: herramientas pendientes si el bucle terminó sin nuevo ●
        self._flush_turn_block()

        # Auto-memoria: guardar resumen si fue una tarea significativa
        self._auto_save_task_memory(full_output_parts)

        # Estado final: "Finalizado" solo cuando TODAS las iteraciones y tools han terminado
        if self._status_cb:
            total_elapsed = time.time() - t_run_start
            done_word  = random.choice(_DONE_WORDS)
            ctx_s      = self.context.stats()
            cpct       = int(ctx_s["tokens_estimate"] / max(ctx_s["max_tokens"], 1) * 100)
            plain_bar  = _ctx_bar(ctx_s["tokens_estimate"], ctx_s["max_tokens"], 10, plain=True)
            thresh_pct = int(getattr(self.context, "compact_threshold", 0.85) * 100)
            hint       = _compact_hint(cpct, thresh_pct)
            tok_part   = (f"{_fmt_tokens(total_inp)}↑ {_fmt_tokens(total_out)}↓  ·  "
                          if (total_inp or total_out) else "")
            line1      = f"⚙  {done_word} durante {total_elapsed:.1f}s  ✓"
            _bstyle_f  = _bar_style(cpct, thresh_pct)
            _chint_f   = _hint_styled(cpct, thresh_pct)
            line2      = f"↳  {tok_part}ctx: {_sfmt(_bstyle_f, plain_bar)} {cpct}%{_chint_f}"
            self._status_cb(f"{line1}\n{line2}")
            self._sep_label = ""  # vuelve a mostrar el proyecto

        # Marcar tareas activas/pendientes como completadas al finalizar el turno
        _now_done = time.time()
        for _pt in self._plan_tasks:
            if _pt["status"] in ("active", "pending"):
                _pt["status"] = "done"
                if not _pt["end_ts"]:
                    _pt["end_ts"] = _now_done

        # Congelar tiempo de tarea: el elapsed queda fijo, el blink se detiene
        self._task_elapsed = time.time() - self._task_start_time
        self._task_start_time = None

        # Usage: una sola vez al final del turno completo (se mostrará antes del próximo prompt)
        self._show_usage(total_inp, total_out)

        # Desconectar canales TUI de hooks y diff renderer
        import tools.hooks as _hooks_mod_end
        import tools.diff_renderer as _diff_mod_end
        _hooks_mod_end.set_hook_print_fn(None)
        _diff_mod_end._dprint_fn = None

        self._last_response = "\n".join(full_output_parts)
        log.debug("assistant_reply", chars=len(self._last_response))
        if self.capture_output:
            return self._last_response
        return None
