import json
from pathlib import Path
from typing import Optional
from pydantic import BaseModel

CONFIG_DIR       = Path.home() / ".oocode"
CONFIG_FILE      = CONFIG_DIR / "oocode.json"
MEMORY_DIR       = CONFIG_DIR / "memory"
HISTORY_FILE     = CONFIG_DIR / "history"
KEYBINDINGS_FILE = CONFIG_DIR / "keybindings.json"

VERSION     = "0.1.0"
APP_NAME    = "OOCode"
APP_SUBTITLE = "Ollama Open Code"

DEFAULT_AGENT_ID = "main"

DEFAULT_CONFIG: dict = {
    "ollama": {
        "host": "http://localhost:11434"
    },
    "agents": {
        "defaults": {
            "model": None,
            "workspace": str(CONFIG_DIR / "workspace" / "main")
        },
        "list": [
            {
                "id":        "main",
                "name":      "OOCode",
                "emoji":     "🤖",
                "model":     None,
                "workspace": str(CONFIG_DIR / "workspace" / "main")
            }
        ]
    },
    "permissions": {
        # Core tools
        "bash":              "ask",
        "write_file":        "ask",
        "edit_file":         "ask",
        "read_file":         "auto",
        "list_dir":          "auto",
        "web_search":        "auto",
        "web_fetch":         "auto",
        "searxng_search":    "auto",
        "spawn_subagent":    "ask",
        "explore":           "auto",
        # Linting (MCP tools)
        "lint_file":         "auto",
        "lint_project":      "auto",
        # Git (MCP tools — read-only → auto, write → ask)
        "git_status":        "auto",
        "git_diff":          "auto",
        "git_log":           "auto",
        "git_commit":        "ask",
        "git_push":          "ask",
        "git_pull":          "ask",
        "git_add":           "ask",
        "git_branch":        "auto",
        "git_stash":         "ask",
        "git_patch":         "ask",
        "git_clone":         "ask",
        "git_worktree":      "ask",
        # Tests (plugin test_runner) — solo verifican, no modifican ficheros
        "run_tests":         "auto",
        "test_file":         "auto",
        # Docker (MCP tools — read-only → auto, write → ask)
        "docker_ps":         "auto",
        "docker_logs":       "auto",
        "docker_inspect":    "auto",
        "docker_images":     "auto",
        "docker_exec":       "ask",
        "docker_stop":       "ask",
        "docker_rm":         "ask",
        "docker_cp":         "ask",
        # Docker Compose (MCP tools — read-only → auto, write → ask)
        "compose_version":   "auto",
        "compose_services":  "auto",
        "compose_status":    "auto",
        "compose_config":    "auto",
        "compose_images":    "auto",
        "compose_top":       "auto",
        "compose_logs":      "auto",
        "compose_up":        "ask",
        "compose_down":      "ask",
        "compose_stop":      "ask",
        "compose_restart":   "ask",
        "compose_build":     "ask",
        "compose_pull":      "ask",
        "compose_exec":      "ask",
        "compose_run":       "ask",
        # Embeddings (plugin embeddings_search)
        "index_workspace":   "auto",
        "semantic_search":   "auto",
        # code_search (read-only)
        "code_search":       "auto",
        # edit_files (atómico — requiere confirmación)
        "edit_files":        "ask",
        # Búsqueda de código (MCP bundled — read-only)
        "grep_code":         "auto",
        "multi_grep":        "auto",
        "code_outline":      "auto",
        "read_sections":     "auto",
        "affected_files":    "auto",
        "symbol_lookup":     "auto",
        "code_compare":      "auto",
        "find_files":        "auto",
        "read_files":        "auto",
        "diff_files":        "auto",
        "http_get":          "auto",   # solo permite URLs locales
        "calculate":         "auto",
        "env_check":         "auto",
        "json_format":       "auto",
        "hash_text":         "auto",
        "port_check":        "auto",
        "search_todos":      "auto",
        "run_quick_check":   "auto",
        "system_info":       "auto",
        "list_recent_files": "auto",
        "read_project_file": "auto",
        "get_datetime":      "auto",
        "process_list":      "auto",
        # LSP plugin (read-only → auto; escribe fichero → ask)
        "lsp_definition":      "auto",
        "lsp_references":      "auto",
        "lsp_hover":           "auto",
        "lsp_symbols":         "auto",
        "lsp_diagnostics":     "auto",
        "lsp_completion":      "auto",
        "lsp_type_definition":    "auto",
        "lsp_implementation":     "auto",
        "lsp_code_actions":       "auto",
        "lsp_workspace_symbols":  "auto",
        "lsp_call_hierarchy":     "auto",
        "lsp_rename":             "ask",   # puede modificar múltiples ficheros
        "lsp_format":             "ask",   # modifica el fichero
        "lsp_restart":            "auto",  # solo reinicia el servidor, no modifica ficheros
        # ctags plugin
        "build_symbol_index": "ask",
        "find_symbol":        "auto",
        "list_symbols":       "auto",
        # Filesystem tools (MCP) — lectura → auto, escritura/destructivo → ask
        "ls_file":            "auto",
        "ls_dir":             "auto",
        "find_file":          "auto",
        "find_dir":           "auto",
        "grep_file":          "auto",
        "chmod_file":         "ask",
        "chmod_dir":          "ask",
        "chown_file":         "ask",
        "chown_dir":          "ask",
        "mv_file":            "ask",
        "cp_file":            "ask",
        "rm_file":            "ask",
        "rm_dir":             "ask",
        "mkdir_dir":          "ask",
        "touch_file":         "ask",
        # Debug de procesos (ask por impacto)
        "strace_run":         "ask",
        "gdb_run":            "ask",
        "pdb_run":            "ask",
        "valgrind_run":       "ask",
        # Build y ejecución
        "make_run":           "ask",
        "run_script":         "ask",
        "format_code":        "ask",
        "mypy_check":         "auto",
        # Python tools
        "python_exec":        "auto",
        "pip_tool":           "ask",
        # Node.js tools
        "npm_tool":           "ask",
        # Archive
        "archive_extract":    "ask",
        "archive_create":     "ask",
        "archive_list":       "auto",
        # Metadatos de ficheros
        "file_stat":          "auto",
        "symlink_create":     "ask",
        "readlink":           "auto",
        # Parches y edición avanzada
        "patch_apply":        "ask",
        "regex_replace":      "ask",
        "bulk_replace":       "ask",
        # Edición segura compuesta
        "smart_replace":      "ask",
        "context_before_edit":"auto",
        "pre_edit_check":     "auto",
        # Visualización y análisis
        "tree":               "auto",
        "analyze_codebase":   "auto",   # meta-tool: tree+count+grep en una llamada (lectura)
        # Markdown y XML
        "render_markdown":    "auto",   # lectura/validación Markdown
        "xml_format":         "auto",   # formato XML (puede escribir si se pasa output)
        "xml_validate":       "auto",   # validación XML (solo lectura)
        # Linters especializados
        "gitlint_check":      "auto",   # solo lectura git + gitlint
        "ansible_lint":       "auto",   # solo lectura + ansible-lint
        "efm_config_update":  "auto",   # escribe ~/.oocode/efm-langserver.yaml
        "count_lines":        "auto",   # lectura — cuenta líneas de un fichero
        "template_fill":      "auto",   # renderizado de plantillas (no escribe)
        # System Assistant MCP — lectura → auto, escritura/acción → ask
        "systemctl_status":   "auto",
        "systemctl_action":   "ask",
        "journalctl":         "auto",
        "net_interfaces":     "auto",
        "net_connections":    "auto",
        "net_ping":           "auto",
        "net_dns":            "auto",
        "disk_usage":         "auto",
        "disk_inodes":        "auto",
        "dir_size":           "auto",
        "lsblk_info":         "auto",
        "user_list":          "auto",
        "user_info":          "auto",
        "group_list":         "auto",
        "who_logged":         "auto",
        "ps_list":            "auto",
        "top_snapshot":       "auto",
        "kill_process":       "ask",
        "fw_status":          "auto",
        "fw_rules":           "auto",
        "fw_allow":           "ask",
        "fw_deny":            "ask",
        "sys_info":           "auto",
        "sys_updates":        "auto",
        "sys_logs":           "auto",
        "env_vars":           "auto",
        "cron_list":          "auto",
        "apt_update":         "ask",
        "apt_upgrade":        "ask",
        "apt_install":        "ask",
        "apt_remove":         "ask",
        "apt_search":         "auto",
        "apt_info":           "auto",
        "apt_list_installed": "auto",
        "dnf_update":         "auto",
        "dnf_install":        "ask",
        "dnf_remove":         "ask",
        "dnf_search":         "auto",
        "dnf_info":           "auto",
        "rpm_query":          "auto",
        # Tree-sitter plugin (read-only)
        "extract_functions": "auto",
        "extract_classes":   "auto",
        "extract_imports":   "auto",
        "ast_summary":       "auto",
        # Todo plugin
        "todo_list":         "auto",
        "todo_add":          "ask",
        "todo_done":         "auto",
        "todo_sync":         "auto",
        # Changelog plugin (read-only)
        "changelog_today":   "auto",
        "changelog_session": "auto",
        "changelog_week":    "auto",
        # Clipboard plugin
        "clipboard_copy":    "auto",
        "clipboard_paste":   "auto",
        # Vault plugin
        "vault_list":        "auto",
        "vault_get":         "auto",
        # Workspace — guardar instrucciones persistentes
        "workspace_remember": "auto",
        # Memoria persistente del agente
        "mem_save":           "auto",
        # Planificación autónoma del agente
        "plan_create":        "auto",
        "task_done":          "auto",
        # Git nuevas tools
        "git_blame":          "auto",
        "git_rebase":         "ask",
        "git_tag":            "ask",
        "git_cherry_pick":    "ask",
        # Validación y procesado
        "json_validate":      "auto",
        "yaml_validate":      "auto",
        "jq_query":           "auto",
        # Skills (converters + snippets — pure computation)
        "encode_base64":     "auto",
        "decode_base64":     "auto",
        "url_encode":        "auto",
        "url_decode":        "auto",
        "compute_hash":      "auto",
        "to_base":           "auto",
        "format_json":       "auto",
        "escape_string":     "auto",
        "hex_encode":        "auto",
        "hex_decode":        "auto",
        "snippet_save":      "auto",
        "snippet_get":       "auto",
        "snippet_list":      "auto",
        "snippet_delete":    "auto",
        # IoT assistant
        "tapo_list":       "auto",
        "tapo_status":     "auto",
        "tapo_on_off":     "ask",
        "tapo_set":        "ask",
        "blink_status":    "auto",
        "blink_arm":       "ask",
        "blink_snapshot":  "ask",
        "blink_clips":     "auto",
        "blink_verify":    "auto",
        "alexa_devices":   "auto",
        "alexa_speak":     "ask",
        "alexa_command":   "ask",
        "alexa_volume":    "ask",
        "tuya_list":       "auto",
        "tuya_status":     "auto",
        "tuya_control":    "ask",
        "ha_entities":     "auto",
        "ha_state":        "auto",
        "ha_control":      "ask",
        "ha_automation":   "ask",
        "mqtt_publish":    "ask",
        "mqtt_subscribe":  "auto",
        "esphome_list":    "auto",
        "esphome_control": "ask",
        "iot_discover":    "auto",
        # Security assistant (read-only/analysis = auto; offensive = ask)
        "nmap_scan":           "ask",
        "port_scan":           "auto",
        "ssl_check":           "auto",
        "whois_lookup":        "auto",
        "dns_enum":            "auto",
        "http_headers":        "auto",
        "nikto_scan":          "ask",
        "gobuster_run":        "ask",
        "curl_request":        "auto",
        "encode_decode":       "auto",
        "hash_crack":          "ask",
        "jwt_decode":          "auto",
        "cert_inspect":        "auto",
        "log_analyze":         "auto",
        "secret_scan":         "auto",
        "cve_lookup":          "auto",
        "xor_decode":          "auto",
        "steganography_check": "auto",
        "base_convert":        "auto",
        "hex_dump":            "auto",
        "fw_audit":            "auto",
        "ssh_key_audit":       "auto",
        "sudoers_review":      "auto",
        "file_integrity_check": "auto",
    },
    "context": {
        "minKeep":            6,      # mensajes mínimos a conservar tras compactar
        "compactThreshold":   0.85,   # fracción del límite que dispara auto-compactación
        "maxSummaryChars":    2100,   # chars máximos del resumen acumulado (~600 tok)
        "maxToolResultTokens": 800,   # tokens máximos de un resultado de tool en contexto
        "autoContinueMax":    8       # auto-continuaciones máx. por turno (0 = desactivado)
    },
    "context_cache": {
        "chars_per_token":    3.0,    # chars por token (por defecto ~3)
        "cache_dir":          "~/.oocode/cache",
        "cache_ttl":          300,    # segundos de caché (5 min por defecto)
        "prompt_cache_enabled": True,  # activar/desactivar caché de prompts
        "context_window_configurable": True,  # permitir configurar context window
        "context_window_default": 262144,  # context window por defecto
        "context_window_min": 8192,  # mínimo context window
        "context_window_max": 262144  # máximo context window
    },
    "embeddings": {
        "model":               "nomic-embed-text-v2-moe:latest",
        "maxInputChars":       8000,  # chars máximos de texto a embedar
        "similarityThreshold": 0.30,  # score mínimo para devolver un resultado
        "snippetChars":        400,   # chars del snippet por resultado
        "topK":                3,     # resultados máximos por búsqueda
        "memoryEmbedEnabled":  True   # usar embeddings para búsqueda semántica en memorias
    },
    "tools": {
        "readFileLinesDefault":  150,   # líneas por defecto en read_file
        "readFileLinesWarnLarge": 500,  # a partir de cuántas líneas avisar
        "webFetchMaxChars":      8000,  # chars máximos de web_fetch
        "webFetchTimeout":       15,    # timeout en segundos de web_fetch
        "webSearchMaxResults":   5,     # resultados por defecto de web_search
        "bashMaxOutputChars":    20000, # chars máximos de salida de bash
        "codeSearchMaxResults":   50,   # resultados máximos de code_search
        "codeSearchContextLines": 2,    # líneas de contexto en code_search
        "codeSearchMaxFilesize":  "500K", # tamaño máximo de fichero en rg
        "toolCacheEnabled":       True,  # activar caché intra-turno de tools
        "toolCacheMaxSize":       200    # entradas máximas en la caché intra-turno
    },
    "workspace": {
        "maxMemoryLines": 50,   # líneas de MEMORY.md en el mini-context
        "maxDailyChars":  2000  # chars del log diario en el mini-context
    },
    "searxng": {
        "url":        "",         # URL de la instancia SearXNG (vacío = desactivado)
        "enabled":    False,      # True = reemplaza web_search con SearXNG
        "maxResults": 5,          # resultados máximos por búsqueda
        "categories": "general",  # categorías por defecto
        "language":   "auto",     # idioma (auto, es, en, ...)
        "safeSearch": 0,          # 0=off, 1=moderate, 2=strict
        "timeout":    10          # timeout en segundos
    },
    "logging": {
        "enabled":    True,       # activar/desactivar logs a fichero
        "file":       "",         # ruta del fichero (vacío = ~/.oocode/logs/oocode.log)
        "level":      "info",     # debug | info | warn | error
        "maxSizeMb":  5,          # tamaño máximo antes de rotar
        "maxFiles":   3           # ficheros rotados a conservar
    },
    "appearance": {
        "accentColor": "cyan"     # color del prompt y del banner (clave de COLOR_PRESETS)
    },
    "plugins": {
        "enabled": []             # lista de plugins activos (sincronizado con /plugins enable)
    },
    "pluginOptions": {
        "searxng": {
            "enabled":    False   # usar SearXNG como buscador en el plugin
        },
        "lsp": {
            "requestTimeout": 10,   # segundos máximos esperando respuesta LSP
            "serverCmds":     {},   # overrides de comandos por extensión {".py": ["pylsp"]}
            "autoStart":      []    # extensiones a arrancar al inicio (p.ej. [".py", ".ts"])
        }
    },
    "skills": {
        "enabled": []             # lista de skills activos (sincronizado con /skills enable)
    },
    "modelOptions": {
        "temperature":   None,   # 0.0–2.0  (None = usar default del modelo)
        "topP":          None,   # 0.0–1.0
        "topK":          None,   # entero ≥1
        "numCtx":        None,   # tokens de contexto del modelo (override global)
        "numPredict":    None,   # tokens máximos a generar (-1 = ilimitado)
        "repeatPenalty": None,   # 1.0 = sin penalización
        "seed":          None    # -1 = aleatorio
    },
    "models": {
        "systemOverhead": 2000,  # tokens reservados para system prompt + tool schemas
        "configs": {}            # {model_id: {contextWindow, maxTokens, params}}
    },
    "fallback": {
        "enabled":        False,  # activar agente de fallback
        "model":          "",     # modelo alternativo, p.ej. "phi3:mini"
        "timeoutSeconds": 120     # segundos sin tokens antes de usar el fallback
    },
    "mcp": {
        "servers":        [],    # lista de {name, cmd, env?, cwd?} — servidores MCP a arrancar al inicio
        "requestTimeout": 15.0,  # segundos máximos esperando respuesta MCP
        "oocodeAssistant": {
            "enabled": True      # arrancar el MCP server bundled oocode_assistant.py
        },
        "systemAssistant": {
            "enabled": True      # arrancar el MCP server bundled system_assistant.py
        },
        "homeOfficeAssistant": {
            "enabled": False     # arrancar el MCP server bundled home_office_assistant.py
        },
        "securityAssistant": {
            "enabled": False     # arrancar el MCP server bundled security_assistant.py
        },
        "iotAssistant": {
            "enabled": False     # arrancar el MCP server bundled iot_assistant.py
        },
    },
    "hooks": {
        "enabled":  True,                  # activar sistema de hooks
        "builtins": [
            "diff_after_write", "ctags_after_write", "lint_after_write",
            "quick_syntax_after_write", "verify_after_edit", "test_suite_delta",
            "config_syntax_after_write",
        ]
    },
    "snapshots": {
        "enabled":         True,   # guardar snapshot al iniciar nueva sesión
        "maxSnapshots":    20,     # máximo de snapshots a conservar por agente
        "saveOnCompact":   False   # guardar snapshot también al compactar contexto
    },
    "rag": {
        "enabled":             True,   # inyectar código relevante del workspace en el system prompt
        "topK":                5,      # top_k base (queries cortas/simples)
        "similarityThreshold": 0.40,   # threshold base
        "maxSnippetChars":     4000,   # chars totales máximos del bloque inyectado
        "indexInterval":       300,    # segundos entre re-indexaciones en background
        "topKComplex":         10,     # top_k para queries largas/autoedición (>complexMinChars)
        "thresholdComplex":    0.35,   # threshold más permisivo para queries complejas
        "complexMinChars":     150     # longitud mínima del mensaje para activar boost
    },
    "vision": {
        "enabled":       True,   # activar detección de imágenes en el input
        "showIndicator": True    # mostrar indicador de visión en la toolbar
    },
    "chatlog": {
        "enabled":    False,               # activar/desactivar registro de conversaciones
        "path":       "",                  # ruta del fichero (vacío = ~/.oocode/logs/chat.log)
        "maxSizeMb":  10                   # tamaño máximo antes de rotar
    }
}


class AgentDef(BaseModel):
    id:           str
    name:         str = "OOCode"
    emoji:        str = "🤖"
    model:        Optional[str] = None
    workspace:    str = str(CONFIG_DIR / "workspace" / "main")
    instructions: str = ""


class OOConfig(BaseModel):
    # ── Ollama ────────────────────────────────────────────────────────────────
    ollama_host: str = "http://localhost:11434"

    # ── Agente activo ─────────────────────────────────────────────────────────
    model:       Optional[str] = None
    workspace:   str  = str(CONFIG_DIR / "workspace" / "main")
    agent_id:           str  = DEFAULT_AGENT_ID
    agent_name:         str  = "OOCode"
    agent_emoji:        str  = "🤖"
    agent_instructions: str  = ""
    agents:      list[AgentDef] = []
    permissions: dict[str, str] = {}

    # ── Contexto ──────────────────────────────────────────────────────────────
    # max_context_tokens ya no se persiste en JSON: se calcula desde models.configs
    # (contextWindow - maxTokens - systemOverhead). Este valor es el fallback cuando
    # el modelo activo no tiene config per-modelo.
    max_context_tokens:      int   = 8000   # fallback interno, no en oocode.json
    compact_min_keep:        int   = 6
    compact_threshold:       float = 0.85
    max_summary_chars:       int   = 2100
    max_tool_result_tokens:  int   = 800
    auto_continue_max:       int   = 8   # auto-continuaciones máx. por turno (0=desactivado)

    # ── Embeddings ────────────────────────────────────────────────────────────
    embed_model:                str   = "nomic-embed-text-v2-moe:latest"
    embed_max_input_chars:      int   = 8000
    embed_similarity_threshold: float = 0.30
    embed_snippet_chars:        int   = 400
    embed_top_k:                int   = 3
    memory_embed_enabled:       bool  = True   # usar embeddings vectoriales en memorias persistentes

    # ── Herramientas ──────────────────────────────────────────────────────────
    read_file_lines_default:   int = 150
    read_file_lines_warn_large: int = 500
    web_fetch_max_chars:       int = 8000
    web_fetch_timeout:         int = 15
    web_search_max_results:    int = 5
    bash_max_output_chars:     int = 20000
    code_search_max_results:   int = 50
    code_search_context_lines: int = 2
    code_search_max_filesize:  str = "500K"
    tool_cache_enabled:        bool = True
    tool_cache_max_size:       int  = 200

    # ── Workspace ─────────────────────────────────────────────────────────────
    ws_max_memory_lines: int = 50    # líneas de MEMORY.md en el mini-context
    ws_max_daily_chars:  int = 2000  # chars del log diario en el mini-context

    # ── SearXNG ───────────────────────────────────────────────────────────────
    searxng_url:         str  = ""
    searxng_enabled:     bool = False
    searxng_max_results: int  = 5
    searxng_categories:  str  = "general"
    searxng_language:    str  = "auto"
    searxng_safe_search: int  = 0
    searxng_timeout:     int  = 10

    # ── Logging ───────────────────────────────────────────────────────────────
    log_enabled:   bool = True
    log_file:      str  = ""
    log_level:     str  = "info"
    log_max_size:  int  = 5
    log_max_files: int  = 3

    # ── Apariencia ────────────────────────────────────────────────────────────
    accent_color: str = "cyan"    # persiste entre sesiones; clave de COLOR_PRESETS

    # ── Plugins / Skills enabled lists ────────────────────────────────────────
    plugins_enabled: list[str] = []
    skills_enabled:  list[str] = []
    plugin_options:  dict      = {}

    # ── Opciones del modelo (None = usar default del modelo) ──────────────────
    model_temperature:    Optional[float] = None
    model_top_p:          Optional[float] = None
    model_top_k:          Optional[int]   = None
    model_num_ctx:        Optional[int]   = None   # override global de num_ctx
    model_num_predict:    Optional[int]   = None
    model_repeat_penalty: Optional[float] = None
    model_seed:           Optional[int]   = None

    # ── Configuración por modelo ───────────────────────────────────────────────
    # {model_id: {"contextWindow": int, "maxTokens": int, "params": dict}}
    model_configs:        dict = {}
    model_system_overhead: int = 2000   # tokens reservados para system + schemas

    # ── Directorio de proyecto (runtime, no persiste) ─────────────────────────
    project_dir: str = ""   # cwd o args.dir; separa el proyecto del workspace de identidad

    # ── MCP ───────────────────────────────────────────────────────────────────
    # Lista de configs de servidores MCP: [{name, cmd, env?, cwd?}]
    mcp_servers:                    list  = []
    mcp_request_timeout:            float = 15.0
    mcp_oocode_assistant_enabled:   bool  = True
    mcp_system_assistant_enabled:   bool  = True
    mcp_home_office_assistant_enabled: bool = False
    mcp_security_assistant_enabled:   bool = False
    mcp_iot_assistant_enabled:        bool = False

    # ── Hooks ─────────────────────────────────────────────────────────────────
    hooks_enabled:  bool       = True
    hooks_builtins: list[str]  = [
        "diff_after_write", "ctags_after_write", "lint_after_write",
        "quick_syntax_after_write", "verify_after_edit", "test_suite_delta",
        "config_syntax_after_write",
    ]

    # ── Snapshots ─────────────────────────────────────────────────────────────
    snapshots_enabled:         bool = True
    snapshots_max:             int  = 20
    snapshots_save_on_compact: bool = False

    # ── RAG automático ────────────────────────────────────────────────────────
    rag_enabled:              bool  = True
    rag_top_k:                int   = 5
    rag_similarity_threshold: float = 0.40
    rag_max_snippet_chars:    int   = 4000
    rag_index_interval:       float = 300.0
    # Boost para queries complejas (mensaje largo o multi-fichero)
    rag_top_k_complex:            int   = 10
    rag_threshold_complex:        float = 0.35
    rag_complex_min_chars:        int   = 150   # umbral de longitud para activar boost

    # ── Visión (imágenes) ─────────────────────────────────────────────────────
    vision_enabled:        bool = True
    vision_show_indicator: bool = True

    # ── Chat log ──────────────────────────────────────────────────────────────
    chatlog_enabled:      bool = False
    chatlog_path:         str  = ""
    chatlog_max_size_mb:  int  = 10

    # ── Fallback ──────────────────────────────────────────────────────────────
    fallback_enabled: bool = False
    fallback_model:   str  = ""
    fallback_timeout: int  = 120   # segundos

    @property
    def fallback_active_config(self) -> bool:
        """True si el fallback está habilitado y tiene modelo configurado."""
        return self.fallback_enabled and bool(self.fallback_model)

    def model_timeout(self, model_name: str) -> int:
        """Timeout en segundos para un modelo concreto. 0 = sin timeout.

        Prioridad: timeoutSeconds del model_config > fallback.timeoutSeconds
        (solo si el fallback está configurado) > 0.
        """
        per_model = self.model_configs.get(model_name, {}).get("timeoutSeconds")
        if per_model is not None:
            return int(per_model)
        if self.fallback_active_config:
            return self.fallback_timeout
        return 0

    # ── Propiedades derivadas del modelo activo ────────────────────────────────

    @property
    def active_model_config(self) -> dict:
        """Config del modelo activo, o {} si no hay entrada per-modelo."""
        return self.model_configs.get(self.model or "", {})

    @property
    def effective_context_window(self) -> Optional[int]:
        """Contexto total del modelo (num_ctx a enviar a Ollama)."""
        return self.active_model_config.get("contextWindow")

    @property
    def effective_max_output_tokens(self) -> Optional[int]:
        """Tokens máximos de salida configurados para el modelo activo."""
        return self.active_model_config.get("maxTokens")

    @property
    def effective_max_context_tokens(self) -> int:
        """Tokens disponibles para el historial de conversación.

        = contextWindow - maxTokens - systemOverhead
        Fallback a context.maxTokens si el modelo no tiene configuración per-modelo.
        """
        ctx_win = self.effective_context_window
        if ctx_win:
            out_tok = self.effective_max_output_tokens or 2048
            computed = ctx_win - out_tok - self.model_system_overhead
            return max(computed, 2000)
        return self.max_context_tokens

    def effective_model_params(self) -> dict:
        """Parámetros para Ollama: per-modelo + overrides globales (modelOptions).

        Los overrides globales (modelOptions) tienen prioridad sobre los per-modelo.
        """
        params: dict = dict(self.active_model_config.get("params", {}))
        for ollama_key, attr in [
            ("temperature",    "model_temperature"),
            ("top_p",          "model_top_p"),
            ("top_k",          "model_top_k"),
            ("num_ctx",        "model_num_ctx"),
            ("num_predict",    "model_num_predict"),
            ("repeat_penalty", "model_repeat_penalty"),
            ("seed",           "model_seed"),
        ]:
            val = getattr(self, attr)
            if val is not None:
                params[ollama_key] = val
        return params

    def set_model_config(
        self,
        model_name: str,
        context_window: int,
        max_tokens: int,
        extra_params: Optional[dict] = None,
        input_types: Optional[list] = None,
    ) -> None:
        """Guarda la configuración de un modelo (contextWindow, maxTokens, params y input types)."""
        existing = self.model_configs.get(model_name, {})
        existing["contextWindow"] = context_window
        existing["maxTokens"]     = max_tokens
        params: dict = {"num_ctx": context_window}
        if extra_params:
            params.update({k: v for k, v in extra_params.items() if v is not None})
        existing["params"] = params
        if input_types is not None:
            existing["input"] = input_types
        self.model_configs[model_name] = existing

    def get_model_input_types(self, model_name: str) -> list[str]:
        """Devuelve los tipos de input soportados por el modelo: ['text'] o ['text', 'image']."""
        return self.model_configs.get(model_name, {}).get("input", ["text"])

    @property
    def active_model_input_types(self) -> list[str]:
        """Tipos de input del modelo activo."""
        return self.get_model_input_types(self.model or "")

    def get_model_thinking(self, model_name: str) -> tuple[str, bool]:
        """Devuelve (think_level, reasoning) guardados para el modelo."""
        t = self.model_configs.get(model_name, {}).get("thinking", {})
        return t.get("think_level", "off"), bool(t.get("reasoning", False))

    def save_model_thinking(self, model_name: str, think_level: str, reasoning: bool) -> None:
        """Persiste think_level y reasoning de un modelo en oocode.json."""
        if not model_name:
            return
        if model_name not in self.model_configs:
            self.model_configs[model_name] = {}
        self.model_configs[model_name]["thinking"] = {
            "think_level": think_level,
            "reasoning":   reasoning,
        }
        self.save()

    # ── Carga ─────────────────────────────────────────────────────────────────

    @classmethod
    def load(cls, agent_id: Optional[str] = None) -> "OOConfig":
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)

        if CONFIG_FILE.exists():
            raw = json.loads(CONFIG_FILE.read_text())
        else:
            raw = DEFAULT_CONFIG.copy()
            CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False))

        def _get(section: str, key: str):
            return raw.get(section, {}).get(key, DEFAULT_CONFIG[section][key])

        ollama_host  = raw.get("ollama", {}).get("host", DEFAULT_CONFIG["ollama"]["host"])
        # Merge de permisos: mantiene los del usuario y añade los nuevos del DEFAULT
        _default_perms = DEFAULT_CONFIG["permissions"].copy()
        _user_perms    = raw.get("permissions", {})
        permissions    = {**_default_perms, **_user_perms}

        # Merge de pluginOptions: mismo patrón (preserva lo que el usuario ha cambiado)
        _default_plugin_opts = DEFAULT_CONFIG.get("pluginOptions", {})
        _user_plugin_opts    = raw.get("pluginOptions", {})
        plugin_options: dict = {}
        for plugin_name, plugin_defaults in _default_plugin_opts.items():
            plugin_options[plugin_name] = {**plugin_defaults, **_user_plugin_opts.get(plugin_name, {})}
        for plugin_name, plugin_cfg in _user_plugin_opts.items():
            if plugin_name not in plugin_options:
                plugin_options[plugin_name] = plugin_cfg

        # Sanear datos LSP corruptos (serverCmds como string, autoStart con chars)
        _lsp = plugin_options.get("lsp", {})
        if isinstance(_lsp, dict):
            if not isinstance(_lsp.get("serverCmds"), dict):
                _lsp["serverCmds"] = {}
            _as = _lsp.get("autoStart", [])
            if not isinstance(_as, list):
                _lsp["autoStart"] = []
            else:
                _lsp["autoStart"] = [s for s in _as if isinstance(s, str) and s.startswith(".")]
            plugin_options["lsp"] = _lsp

        # Agentes
        agents_raw  = raw.get("agents", DEFAULT_CONFIG["agents"])
        defaults    = agents_raw.get("defaults", {})
        agents_list = [AgentDef(**a) for a in agents_raw.get("list", [])]

        target_id = agent_id or DEFAULT_AGENT_ID
        agent = next((a for a in agents_list if a.id == target_id), None)
        if agent is None and agents_list:
            agent = agents_list[0]

        if agent:
            model        = agent.model or defaults.get("model")
            workspace    = agent.workspace or defaults.get("workspace", str(CONFIG_DIR / "workspace" / "main"))
            a_id, a_name, a_emoji = agent.id, agent.name, agent.emoji
            a_instructions = agent.instructions
        else:
            model        = defaults.get("model")
            workspace    = defaults.get("workspace", str(CONFIG_DIR / "workspace" / "main"))
            a_id, a_name, a_emoji = target_id, "OOCode", "🤖"
            a_instructions = ""

        _cfg = cls(
            ollama_host         = ollama_host,
            model               = model,
            workspace           = workspace,
            agent_id            = a_id,
            agent_name          = a_name,
            agent_emoji         = a_emoji,
            agent_instructions  = a_instructions,
            agents              = agents_list,
            permissions  = permissions,

            compact_min_keep        = _get("context", "minKeep"),
            compact_threshold       = _get("context", "compactThreshold"),
            max_summary_chars       = _get("context", "maxSummaryChars"),
            max_tool_result_tokens  = _get("context", "maxToolResultTokens"),
            auto_continue_max       = _get("context", "autoContinueMax"),

            embed_model                 = _get("embeddings", "model"),
            embed_max_input_chars       = _get("embeddings", "maxInputChars"),
            embed_similarity_threshold  = _get("embeddings", "similarityThreshold"),
            embed_snippet_chars         = _get("embeddings", "snippetChars"),
            embed_top_k                 = _get("embeddings", "topK"),
            memory_embed_enabled        = _get("embeddings", "memoryEmbedEnabled"),

            read_file_lines_default    = _get("tools", "readFileLinesDefault"),
            read_file_lines_warn_large = _get("tools", "readFileLinesWarnLarge"),
            web_fetch_max_chars        = _get("tools", "webFetchMaxChars"),
            web_fetch_timeout          = _get("tools", "webFetchTimeout"),
            web_search_max_results     = _get("tools", "webSearchMaxResults"),
            bash_max_output_chars      = _get("tools", "bashMaxOutputChars"),
            code_search_max_results    = _get("tools", "codeSearchMaxResults"),
            code_search_context_lines  = _get("tools", "codeSearchContextLines"),
            code_search_max_filesize   = _get("tools", "codeSearchMaxFilesize"),
            tool_cache_enabled         = _get("tools", "toolCacheEnabled"),
            tool_cache_max_size        = _get("tools", "toolCacheMaxSize"),

            ws_max_memory_lines = _get("workspace", "maxMemoryLines"),
            ws_max_daily_chars  = _get("workspace", "maxDailyChars"),

            searxng_url         = _get("searxng", "url"),
            searxng_enabled     = _get("searxng", "enabled"),
            searxng_max_results = _get("searxng", "maxResults"),
            searxng_categories  = _get("searxng", "categories"),
            searxng_language    = _get("searxng", "language"),
            searxng_safe_search = _get("searxng", "safeSearch"),
            searxng_timeout     = _get("searxng", "timeout"),

            log_enabled   = _get("logging", "enabled"),
            log_file      = _get("logging", "file"),
            log_level     = _get("logging", "level"),
            log_max_size  = _get("logging", "maxSizeMb"),
            log_max_files = _get("logging", "maxFiles"),

            accent_color    = raw.get("appearance", {}).get("accentColor", "cyan"),

            plugins_enabled = raw.get("plugins", {}).get("enabled", []),
            skills_enabled  = raw.get("skills",  {}).get("enabled", []),
            plugin_options  = plugin_options,

            model_temperature    = raw.get("modelOptions", {}).get("temperature"),
            model_top_p          = raw.get("modelOptions", {}).get("topP"),
            model_top_k          = raw.get("modelOptions", {}).get("topK"),
            model_num_ctx        = raw.get("modelOptions", {}).get("numCtx"),
            model_num_predict    = raw.get("modelOptions", {}).get("numPredict"),
            model_repeat_penalty = raw.get("modelOptions", {}).get("repeatPenalty"),
            model_seed           = raw.get("modelOptions", {}).get("seed"),

            model_configs         = raw.get("models", {}).get("configs", {}),
            model_system_overhead = raw.get("models", {}).get("systemOverhead", 2000),

            fallback_enabled = raw.get("fallback", {}).get("enabled",        DEFAULT_CONFIG["fallback"]["enabled"]),
            fallback_model   = raw.get("fallback", {}).get("model",          DEFAULT_CONFIG["fallback"]["model"]),
            fallback_timeout = raw.get("fallback", {}).get("timeoutSeconds",  DEFAULT_CONFIG["fallback"]["timeoutSeconds"]),

            mcp_servers         = raw.get("mcp", {}).get("servers", []),
            mcp_request_timeout = float(raw.get("mcp", {}).get("requestTimeout",
                                        DEFAULT_CONFIG["mcp"]["requestTimeout"])),
            mcp_oocode_assistant_enabled = raw.get("mcp", {}).get(
                "oocodeAssistant", DEFAULT_CONFIG["mcp"]["oocodeAssistant"]
            ).get("enabled", True),
            mcp_system_assistant_enabled = raw.get("mcp", {}).get(
                "systemAssistant", DEFAULT_CONFIG["mcp"]["systemAssistant"]
            ).get("enabled", True),
            mcp_home_office_assistant_enabled = raw.get("mcp", {}).get(
                "homeOfficeAssistant", DEFAULT_CONFIG["mcp"]["homeOfficeAssistant"]
            ).get("enabled", False),
            mcp_security_assistant_enabled = raw.get("mcp", {}).get(
                "securityAssistant", DEFAULT_CONFIG["mcp"]["securityAssistant"]
            ).get("enabled", False),
            mcp_iot_assistant_enabled = raw.get("mcp", {}).get(
                "iotAssistant", DEFAULT_CONFIG["mcp"]["iotAssistant"]
            ).get("enabled", False),

            hooks_enabled  = raw.get("hooks", {}).get("enabled",
                                     DEFAULT_CONFIG["hooks"]["enabled"]),
            hooks_builtins = raw.get("hooks", {}).get("builtins",
                                     list(DEFAULT_CONFIG["hooks"]["builtins"])),

            snapshots_enabled         = raw.get("snapshots", {}).get("enabled",
                                                DEFAULT_CONFIG["snapshots"]["enabled"]),
            snapshots_max             = raw.get("snapshots", {}).get("maxSnapshots",
                                                DEFAULT_CONFIG["snapshots"]["maxSnapshots"]),
            snapshots_save_on_compact = raw.get("snapshots", {}).get("saveOnCompact",
                                                DEFAULT_CONFIG["snapshots"]["saveOnCompact"]),

            rag_enabled              = _get("rag", "enabled"),
            rag_top_k                = _get("rag", "topK"),
            rag_similarity_threshold = _get("rag", "similarityThreshold"),
            rag_max_snippet_chars    = _get("rag", "maxSnippetChars"),
            rag_index_interval       = float(_get("rag", "indexInterval")),
            rag_top_k_complex        = _get("rag", "topKComplex"),
            rag_threshold_complex    = _get("rag", "thresholdComplex"),
            rag_complex_min_chars    = _get("rag", "complexMinChars"),

            vision_enabled        = raw.get("vision", {}).get("enabled",
                                            DEFAULT_CONFIG["vision"]["enabled"]),
            vision_show_indicator = raw.get("vision", {}).get("showIndicator",
                                            DEFAULT_CONFIG["vision"]["showIndicator"]),

            chatlog_enabled     = raw.get("chatlog", {}).get("enabled",
                                          DEFAULT_CONFIG["chatlog"]["enabled"]),
            chatlog_path        = raw.get("chatlog", {}).get("path",
                                          DEFAULT_CONFIG["chatlog"]["path"]),
            chatlog_max_size_mb = raw.get("chatlog", {}).get("maxSizeMb",
                                          DEFAULT_CONFIG["chatlog"]["maxSizeMb"]),
        )

        # ── Migración automática: añadir secciones nuevas y eliminar campos deprecated ──
        # "modelOptions" se excluye porque save() la omite cuando todos sus valores son None.
        _OPTIONAL_SECTIONS = {"modelOptions"}
        _missing_sections  = [
            k for k in DEFAULT_CONFIG
            if k not in raw and k not in _OPTIONAL_SECTIONS
        ]
        # Campos deprecated eliminados de la spec pero que pueden seguir en el JSON
        _has_deprecated = "maxTokens" in raw.get("context", {})
        # Claves nuevas dentro de secciones existentes
        _has_mcp_gaps = (
            "systemAssistant" not in raw.get("mcp", {}) or
            "homeOfficeAssistant" not in raw.get("mcp", {}) or
            "securityAssistant" not in raw.get("mcp", {}) or
            "iotAssistant" not in raw.get("mcp", {})
        )
        # embed_max_input_chars: migrar valores obsoletos (≤3000) al nuevo default (8000)
        _embed_old = raw.get("embeddings", {}).get("maxInputChars", 0)
        if isinstance(_embed_old, int) and _embed_old <= 3000:
            _cfg.embed_max_input_chars = 8000
        if _missing_sections or _has_deprecated or _has_mcp_gaps:
            _cfg.save()

        return _cfg

    def save(self) -> None:
        # Backup con rotación antes de sobreescribir
        if CONFIG_FILE.exists():
            import shutil
            from datetime import datetime
            bak = CONFIG_FILE.with_name("oocode.json.bak")
            if bak.exists():
                dated = CONFIG_FILE.with_name(
                    f"oocode.json.{bak.stat().st_mtime and datetime.fromtimestamp(bak.stat().st_mtime).strftime('%Y%m%d_%H%M%S')}.bak"
                )
                bak.rename(dated)
            shutil.copy2(CONFIG_FILE, bak)

        raw: dict = {}
        if CONFIG_FILE.exists():
            raw = json.loads(CONFIG_FILE.read_text())

        raw.setdefault("ollama", {})["host"] = self.ollama_host
        raw["permissions"] = self.permissions

        # Contexto (maxTokens eliminado: se calcula desde models.configs)
        ctx = raw.setdefault("context", {})
        ctx.pop("maxTokens", None)   # limpia el campo legacy si existe
        ctx["minKeep"]             = self.compact_min_keep
        ctx["compactThreshold"]    = self.compact_threshold
        ctx["maxSummaryChars"]     = self.max_summary_chars
        ctx["maxToolResultTokens"] = self.max_tool_result_tokens
        ctx["autoContinueMax"]     = self.auto_continue_max

        # Embeddings
        emb = raw.setdefault("embeddings", {})
        emb["model"]               = self.embed_model
        emb["maxInputChars"]       = self.embed_max_input_chars
        emb["similarityThreshold"] = self.embed_similarity_threshold
        emb["snippetChars"]        = self.embed_snippet_chars
        emb["topK"]                = self.embed_top_k
        emb["memoryEmbedEnabled"]  = self.memory_embed_enabled

        # Herramientas
        tools = raw.setdefault("tools", {})
        tools["readFileLinesDefault"]   = self.read_file_lines_default
        tools["readFileLinesWarnLarge"] = self.read_file_lines_warn_large
        tools["webFetchMaxChars"]       = self.web_fetch_max_chars
        tools["webFetchTimeout"]        = self.web_fetch_timeout
        tools["webSearchMaxResults"]    = self.web_search_max_results
        tools["bashMaxOutputChars"]     = self.bash_max_output_chars
        tools["codeSearchMaxResults"]   = self.code_search_max_results
        tools["codeSearchContextLines"] = self.code_search_context_lines
        tools["codeSearchMaxFilesize"]  = self.code_search_max_filesize
        tools["toolCacheEnabled"]       = self.tool_cache_enabled
        tools["toolCacheMaxSize"]       = self.tool_cache_max_size

        # Workspace
        ws = raw.setdefault("workspace", {})
        ws["maxMemoryLines"] = self.ws_max_memory_lines
        ws["maxDailyChars"]  = self.ws_max_daily_chars

        # SearXNG
        sx = raw.setdefault("searxng", {})
        sx["url"]        = self.searxng_url
        sx["enabled"]    = self.searxng_enabled
        sx["maxResults"] = self.searxng_max_results
        sx["categories"] = self.searxng_categories
        sx["language"]   = self.searxng_language
        sx["safeSearch"] = self.searxng_safe_search
        sx["timeout"]    = self.searxng_timeout

        # Logging
        lg = raw.setdefault("logging", {})
        lg["enabled"]   = self.log_enabled
        lg["file"]      = self.log_file
        lg["level"]     = self.log_level
        lg["maxSizeMb"] = self.log_max_size
        lg["maxFiles"]  = self.log_max_files

        # Apariencia
        raw.setdefault("appearance", {})["accentColor"] = self.accent_color

        # Plugins / Skills enabled lists
        raw.setdefault("plugins", {})["enabled"] = sorted(self.plugins_enabled)
        raw.setdefault("skills",  {})["enabled"] = sorted(self.skills_enabled)

        # Plugin options
        if self.plugin_options:
            raw["pluginOptions"] = self.plugin_options

        # Model options — omitir claves con valor None para no saturar el JSON
        mo = raw.setdefault("modelOptions", {})
        for json_key, attr in [
            ("temperature",   "model_temperature"),
            ("topP",          "model_top_p"),
            ("topK",          "model_top_k"),
            ("numCtx",        "model_num_ctx"),
            ("numPredict",    "model_num_predict"),
            ("repeatPenalty", "model_repeat_penalty"),
            ("seed",          "model_seed"),
        ]:
            val = getattr(self, attr)
            if val is None:
                mo.pop(json_key, None)
            else:
                mo[json_key] = val
        if not mo:
            raw.pop("modelOptions", None)

        # Per-model context configs
        models_sec = raw.setdefault("models", {})
        models_sec["systemOverhead"] = self.model_system_overhead
        models_sec["configs"] = self.model_configs

        # Fallback
        fb = raw.setdefault("fallback", {})
        fb["enabled"]        = self.fallback_enabled
        fb["model"]          = self.fallback_model
        fb["timeoutSeconds"] = self.fallback_timeout

        # MCP
        mcp_sec = raw.setdefault("mcp", {})
        mcp_sec["servers"]        = self.mcp_servers
        mcp_sec["requestTimeout"] = self.mcp_request_timeout
        mcp_sec.setdefault("oocodeAssistant", {})["enabled"] = self.mcp_oocode_assistant_enabled
        mcp_sec.setdefault("systemAssistant", {})["enabled"] = self.mcp_system_assistant_enabled
        mcp_sec.setdefault("homeOfficeAssistant", {})["enabled"] = self.mcp_home_office_assistant_enabled
        mcp_sec.setdefault("securityAssistant", {})["enabled"]   = self.mcp_security_assistant_enabled
        mcp_sec.setdefault("iotAssistant", {})["enabled"]        = self.mcp_iot_assistant_enabled

        # Hooks
        hooks_sec = raw.setdefault("hooks", {})
        hooks_sec["enabled"]  = self.hooks_enabled
        hooks_sec["builtins"] = self.hooks_builtins

        # Snapshots
        snap_sec = raw.setdefault("snapshots", {})
        snap_sec["enabled"]       = self.snapshots_enabled
        snap_sec["maxSnapshots"]  = self.snapshots_max
        snap_sec["saveOnCompact"] = self.snapshots_save_on_compact

        # RAG
        rag = raw.setdefault("rag", {})
        rag["enabled"]             = self.rag_enabled
        rag["topK"]                = self.rag_top_k
        rag["similarityThreshold"] = self.rag_similarity_threshold
        rag["maxSnippetChars"]     = self.rag_max_snippet_chars
        rag["indexInterval"]       = self.rag_index_interval
        rag["topKComplex"]         = self.rag_top_k_complex
        rag["thresholdComplex"]    = self.rag_threshold_complex
        rag["complexMinChars"]     = self.rag_complex_min_chars

        # Visión
        vis = raw.setdefault("vision", {})
        vis["enabled"]       = self.vision_enabled
        vis["showIndicator"] = self.vision_show_indicator

        # Chat log
        cl = raw.setdefault("chatlog", {})
        cl["enabled"]   = self.chatlog_enabled
        cl["path"]      = self.chatlog_path
        cl["maxSizeMb"] = self.chatlog_max_size_mb

        # Modelo del agente activo
        agents_raw = raw.setdefault("agents", {})
        for a in agents_raw.get("list", []):
            if a.get("id") == self.agent_id:
                if self.model:
                    a["model"] = self.model
                a["workspace"] = self.workspace
                break

        CONFIG_FILE.write_text(json.dumps(raw, indent=2, ensure_ascii=False))

    def load_oocode_md(self) -> Optional[str]:
        """Carga OOCODE.md: workspace → project_dir → cwd, en ese orden."""
        seen: set[str] = set()
        candidates: list[Path] = []
        for base in [
            Path(self.workspace),
            Path(self.project_dir) if self.project_dir else None,
            Path.cwd(),
        ]:
            if base is None:
                continue
            p = base / "OOCODE.md"
            key = str(p.resolve())
            if key not in seen:
                seen.add(key)
                candidates.append(p)
        for path in candidates:
            if path.exists():
                return path.read_text()
        return None
