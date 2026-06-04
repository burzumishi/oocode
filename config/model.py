"""Modelos de configuración: AgentDef y OOConfig (carga/guardado de oocode.json)."""
import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from config.constants import CONFIG_DIR, DEFAULT_AGENT_ID
from config.defaults import DEFAULT_CONFIG

# Host Ollama por defecto — las embeddings siempre usan protocolo Ollama, así que
# con backend de chat no-Ollama y sin embedHost explícito se cae a este local.
_DEFAULT_OLLAMA_HOST = DEFAULT_CONFIG["api"]["host"]


def _const(name: str):
    """Resuelve una ruta de configuración desde el paquete `config` en runtime.

    load()/save() la usan para que parchear `config.CONFIG_FILE` / `CONFIG_DIR` /
    `MEMORY_DIR` (como hacen los tests, igual que cuando todo vivía en config.py)
    siga surtiendo efecto pese a que las constantes ahora viven en config.constants.
    """
    import config as _pkg
    from config import constants as _c
    return getattr(_pkg, name, getattr(_c, name))


class AgentDef(BaseModel):
    id:           str
    name:         str = "OOCode"
    emoji:        str = "🤖"
    model:        Optional[str] = None
    workspace:    str = str(CONFIG_DIR / "workspace" / "main")
    # La identidad/comportamiento del agente vive en sus ficheros .md del workspace
    # (IDENTITY.md, SOUL.md, …), no en el JSON. Campos extra del JSON se ignoran.
    model_config = {"extra": "ignore"}


class OOConfig(BaseModel):
    # ── API backend (bloque "api" unificado en oocode.json) ───────────────────
    api_type:     str = "ollama"   # "ollama" | "openai" | "anthropic"
    api_key:      str = ""         # API key para OpenAI / Anthropic
    # api_base_url y ollama_host se cargan ambos del campo único api.host:
    #   backend Ollama → usa ollama_host; backend OpenAI → usa api_base_url.
    api_base_url: str = ""         # URL base para OpenAI-compat (llama.cpp, LM Studio, vLLM…)

    # ── Servidor / hosts (campos del bloque "api", específicos de Ollama) ──────
    ollama_host:             str       = "http://localhost:11434"
    ollama_extra_hosts:      list[str] = []
    ollama_embed_host:       str       = ""
    ollama_subagent_routing: str       = "round-robin"

    # ── Agente activo ─────────────────────────────────────────────────────────
    model:       Optional[str] = None
    workspace:   str  = str(CONFIG_DIR / "workspace" / "main")
    agent_id:           str  = DEFAULT_AGENT_ID
    agent_name:         str  = "OOCode"
    agent_emoji:        str  = "🤖"
    agents:      list[AgentDef] = []
    permissions: dict[str, str] = {}

    # ── Contexto ──────────────────────────────────────────────────────────────
    # max_context_tokens ya no se persiste en JSON: se calcula desde models.configs
    # (contextWindow - maxTokens - systemOverhead). Este valor es el fallback cuando
    # el modelo activo no tiene config per-modelo.
    max_context_tokens:      int   = 8000   # fallback interno, no en oocode.json
    compact_min_keep:        int   = 6
    compact_threshold:       float = 0.80
    max_summary_chars:       int   = 2100
    max_tool_result_tokens:  int   = 800
    auto_continue_max:       int   = 8   # auto-continuaciones máx. por turno (0=desactivado)
    context_high_water:      float = 0.70  # fracción de max_tokens para truncado 2ª pasada
    context_tool_max_chars:  int   = 3000  # chars máx. por tool result en 2ª pasada
    ctx_mode:                str   = "mini"  # contexto del workspace al arrancar: "mini" | "full"

    # ── Embeddings ────────────────────────────────────────────────────────────
    embed_model:                str   = "nomic-embed-text-v2-moe:latest"
    embed_max_input_chars:      int   = 8000
    embed_similarity_threshold: float = 0.30
    embed_snippet_chars:        int   = 400
    embed_top_k:                int   = 3
    memory_embed_enabled:       bool  = True   # usar embeddings vectoriales en memorias persistentes
    embed_disk_cache_enabled:   bool  = True   # persistir caché de embeddings a disco
    embed_disk_cache_dir:       str   = "~/.oocode/cache"
    embed_disk_cache_max:       int   = 2000   # máx. entradas en caché de disco
    embed_ram_cache_max:        int   = 256    # vectores máximos en caché LRU en RAM

    # ── Herramientas ──────────────────────────────────────────────────────────
    read_file_lines_default:   int = 150
    read_file_lines_warn_large: int = 500
    web_fetch_max_chars:       int = 8000
    web_fetch_timeout:         int = 15
    web_search_max_results:    int = 5
    bash_max_output_chars:     int = 20000
    mcp_max_output_chars:      int = 4000
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

    # ── Defaults globales de modelos (models.repeatPenalty / seed) ──────────────
    model_repeat_penalty: Optional[float] = None   # default global para repeat_penalty
    model_seed:           Optional[int]   = None   # default global para seed (-1=aleatorio)
    ollama_retry_count:   int             = 2      # reintentos en timeout (ollama.ollamaRetryCount)
    ollama_retry_delay:   float           = 3.0    # delay base entre reintentos en s (ollama.ollamaRetryDelay)

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
    mcp_oocode_assistant_enabled:    bool  = True
    mcp_system_assistant_enabled:    bool  = True
    mcp_devops_assistant_enabled:    bool  = True
    mcp_database_assistant_enabled:  bool  = False
    mcp_home_office_assistant_enabled: bool = False
    mcp_security_assistant_enabled:   bool = False
    mcp_iot_assistant_enabled:          bool = False
    mcp_http_client_assistant_enabled:  bool = False

    # ── Hooks ─────────────────────────────────────────────────────────────────
    hooks_enabled:  bool       = True
    hooks_builtins: list[str]  = [
        "diff_after_write", "ctags_after_write", "lint_after_write",
        "quick_syntax_after_write", "verify_after_edit", "test_suite_delta",
        "config_syntax_after_write",
        "deadlock_detection", "dead_code_detection", "performance_profiling",
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
    rag_max_file_chars:       int   = 6000   # chars por fichero antes de chunking
    rag_chunk_chars:          int   = 512    # chars por chunk de indexación
    rag_chunk_overlap:        int   = 64     # solapamiento entre chunks
    rag_max_files:            int   = 2000   # ficheros máximos a indexar
    rag_min_slot_chars:       int   = 200    # mínimo de chars por fragmento en respuesta RAG
    # Boost para queries complejas (mensaje largo o multi-fichero)
    rag_top_k_complex:            int   = 10
    rag_threshold_complex:        float = 0.35
    rag_complex_min_chars:        int   = 150   # umbral de longitud para activar boost

    # ── Visión (imágenes) ─────────────────────────────────────────────────────
    vision_enabled:        bool = True
    vision_show_indicator: bool = True

    # ── Finalización de tarea (frase canónica, idioma del agente) ──────────────
    completion_phrase:        str       = "He completado todas las tareas."
    completion_extra_phrases: list[str] = []

    # ── Chat log ──────────────────────────────────────────────────────────────
    chatlog_enabled:      bool = False
    chatlog_path:         str  = ""
    chatlog_max_size_mb:  int  = 10

    # ── WebUI ─────────────────────────────────────────────────────────────────
    webui_enabled:        bool = False
    webui_host:           str  = "0.0.0.0"
    webui_port:           int  = 4000
    webui_log_file:       str  = ""   # vacío = ~/.oocode/logs/webserver.log
    webui_log_max_size:   int  = 5

    # ── Subagentes ────────────────────────────────────────────────────────────
    subagents_max_concurrent:    int = 4
    subagents_max_teams:         int = 3
    subagents_max_team_size:     int = 5
    subagents_recent_ttl:        int = 1800
    subagents_default_priority:  int = 0
    subagents_auto_cont_max:     int = 16   # 0 = hereda auto_continue_max del agente principal
    subagents_inference_timeout: int = 0    # 0 = hereda fallback.timeoutSeconds
    subagents_default_timeout:   int = 0    # 0 = sin límite de tiempo por tarea

    # ── Backups ───────────────────────────────────────────────────────────────
    backup_enabled:     bool      = True
    backup_dir:         str       = ""   # vacío = ~/.oocode/backup/
    backup_max_files:   int       = 50
    backup_extensions:  list[str] = []   # vacío usa los defaults de DEFAULT_CONFIG

    # ── Fallback ──────────────────────────────────────────────────────────────
    fallback_enabled: bool = False
    fallback_model:   str  = ""
    fallback_timeout: int  = 120   # segundos

    # Override de runtime (no se carga del JSON): timeout de inferencia forzado.
    # Lo usa SubAgentRunner para aplicar subagents.inferenceTimeout a los subagentes
    # con máxima prioridad, independientemente de fallback/per-model. 0 = sin override.
    inference_timeout_override: int = 0

    @property
    def effective_embed_host(self) -> str:
        """Host para embeddings.

        Las embeddings SIEMPRE usan el protocolo Ollama (EmbeddingClient envuelve
        ollama.Client), independientemente del backend de chat. Por eso:

        - Si hay embedHost explícito, se respeta.
        - En modo primary-only: el host principal, centralizando el tráfico Ollama.
        - Con backend Ollama: ollama_host.
        - Con backend OpenAI/Anthropic SIN embedHost: ollama_host alimenta la misma
          URL del servidor de chat (campo unificado api.host), que NO habla Ollama.
          Caer al default local de Ollama evita apuntar el cliente de embeddings a
          un servidor OpenAI/Anthropic. Configura api.embedHost para un host propio.
        """
        # Backend de chat no-Ollama: el host de chat no habla protocolo Ollama.
        # Usa embedHost explícito o cae al default local de Ollama (nunca ollama_host,
        # que apunta al servidor OpenAI/Anthropic). primary-only no aplica aquí.
        if self.api_type != "ollama":
            return self.ollama_embed_host or _DEFAULT_OLLAMA_HOST
        # Backend Ollama: primary-only centraliza todo en el host principal (ignora embedHost).
        if self.ollama_subagent_routing == "primary-only":
            return self.ollama_host
        return self.ollama_embed_host or self.ollama_host

    @property
    def all_ollama_hosts(self) -> list[str]:
        """Todos los hosts disponibles: principal + extras (filtra vacíos)."""
        return [self.ollama_host] + [h for h in self.ollama_extra_hosts if h]

    @property
    def fallback_active_config(self) -> bool:
        """True si el fallback está habilitado y tiene modelo configurado."""
        return self.fallback_enabled and bool(self.fallback_model)

    def model_timeout(self, model_name: str) -> int:
        """Timeout en segundos para un modelo concreto. 0 = sin timeout.

        Prioridad: inference_timeout_override (subagentes) > timeoutSeconds del
        model_config > fallback.timeoutSeconds (solo si el fallback está
        configurado) > 0.
        """
        if self.inference_timeout_override > 0:
            return self.inference_timeout_override
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

    @property
    def max_thinking_tokens(self) -> int:
        """Tokens de thinking máximos para el modelo activo (0 = sin límite).

        Lee de models.configs[model].thinking.maxThinkingTokens; default 6000.
        """
        return self.active_model_config.get("thinking", {}).get("maxThinkingTokens", 6000)

    def effective_model_params(self) -> dict:
        """Parámetros para Ollama: per-modelo con defaults globales de models.repeatPenalty/seed.

        Los defaults globales sólo se aplican si el modelo no define ya el parámetro.
        """
        params: dict = dict(self.active_model_config.get("params", {}))
        for ollama_key, attr in [
            ("repeat_penalty", "model_repeat_penalty"),
            ("seed",           "model_seed"),
        ]:
            val = getattr(self, attr)
            if val is not None and ollama_key not in params:
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
        existing_t = self.model_configs[model_name].get("thinking", {})
        self.model_configs[model_name]["thinking"] = {
            "think_level":       think_level,
            "reasoning":         reasoning,
            "maxThinkingTokens": existing_t.get("maxThinkingTokens", 6000),
        }
        self.save()

    # ── Carga ─────────────────────────────────────────────────────────────────

    @classmethod
    def load(cls, agent_id: Optional[str] = None) -> "OOConfig":
        CONFIG_DIR  = _const("CONFIG_DIR")
        CONFIG_FILE = _const("CONFIG_FILE")
        MEMORY_DIR  = _const("MEMORY_DIR")
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)

        if CONFIG_FILE.exists():
            raw = json.loads(CONFIG_FILE.read_text())
        else:
            raw = DEFAULT_CONFIG.copy()
            CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False))

        def _get(section: str, key: str):
            return raw.get(section, {}).get(key, DEFAULT_CONFIG[section][key])

        # Bloque unificado "api": backend LLM + parámetros de servidor (host, embeddings, routing…)
        _api_raw    = raw.get("api", {})
        _mo_raw     = raw.get("modelOptions", {})   # solo para migración desde versión anterior
        api_type    = _api_raw.get("type", DEFAULT_CONFIG["api"]["type"])
        api_key     = _api_raw.get("key",  DEFAULT_CONFIG["api"]["key"])
        # El campo único "host" alimenta tanto ollama_host como api_base_url (OpenAI baseUrl).
        # El backend Ollama usa ollama_host; el backend OpenAI usa api_base_url. Anthropic ignora ambos.
        _api_host    = _api_raw.get("host", DEFAULT_CONFIG["api"]["host"])
        ollama_host  = _api_host
        api_base_url = _api_host
        ollama_extra_hosts   = _api_raw.get("extraHosts",      DEFAULT_CONFIG["api"]["extraHosts"])
        ollama_embed_host    = _api_raw.get("embedHost",       DEFAULT_CONFIG["api"]["embedHost"])
        ollama_subagent_routing = _api_raw.get("subagentRouting",
                                               DEFAULT_CONFIG["api"]["subagentRouting"])
        ollama_retry_count   = int(_api_raw.get("ollamaRetryCount",
                                   _mo_raw.get("ollamaRetryCount",
                                               DEFAULT_CONFIG["api"]["ollamaRetryCount"])))
        ollama_retry_delay   = float(_api_raw.get("ollamaRetryDelay",
                                     _mo_raw.get("ollamaRetryDelay",
                                                 DEFAULT_CONFIG["api"]["ollamaRetryDelay"])))
        _models_raw          = raw.get("models", {})
        model_repeat_penalty = _models_raw.get("repeatPenalty", _mo_raw.get("repeatPenalty"))
        model_seed           = _models_raw.get("seed", _mo_raw.get("seed"))
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
        else:
            model        = defaults.get("model")
            workspace    = defaults.get("workspace", str(CONFIG_DIR / "workspace" / "main"))
            a_id, a_name, a_emoji = target_id, "OOCode", "🤖"

        _cfg = cls(
            api_type                = api_type,
            api_key                 = api_key,
            api_base_url            = api_base_url,
            ollama_host             = ollama_host,
            ollama_extra_hosts      = ollama_extra_hosts,
            ollama_embed_host       = ollama_embed_host,
            ollama_subagent_routing = ollama_subagent_routing,
            model               = model,
            workspace           = workspace,
            agent_id            = a_id,
            agent_name          = a_name,
            agent_emoji         = a_emoji,
            agents              = agents_list,
            permissions  = permissions,

            compact_min_keep        = _get("context", "minKeep"),
            compact_threshold       = _get("context", "compactThreshold"),
            max_summary_chars       = _get("context", "maxSummaryChars"),
            max_tool_result_tokens  = _get("context", "maxToolResultTokens"),
            auto_continue_max       = _get("context", "autoContinueMax"),
            context_high_water      = _get("context", "highWater"),
            context_tool_max_chars  = _get("context", "toolMaxChars"),
            ctx_mode                = (_get("context", "ctxMode") if _get("context", "ctxMode") in ("mini", "full") else "mini"),

            embed_model                 = _get("embeddings", "model"),
            embed_max_input_chars       = _get("embeddings", "maxInputChars"),
            embed_similarity_threshold  = _get("embeddings", "similarityThreshold"),
            embed_snippet_chars         = _get("embeddings", "snippetChars"),
            embed_top_k                 = _get("embeddings", "topK"),
            memory_embed_enabled        = _get("embeddings", "memoryEmbedEnabled"),
            embed_disk_cache_enabled    = _get("embeddings", "diskCacheEnabled"),
            embed_disk_cache_dir        = _get("embeddings", "diskCacheDir"),
            embed_disk_cache_max        = _get("embeddings", "diskCacheMaxEntries"),
            embed_ram_cache_max         = _get("embeddings", "ramCacheMax"),

            read_file_lines_default    = _get("tools", "readFileLinesDefault"),
            read_file_lines_warn_large = _get("tools", "readFileLinesWarnLarge"),
            web_fetch_max_chars        = _get("tools", "webFetchMaxChars"),
            web_fetch_timeout          = _get("tools", "webFetchTimeout"),
            web_search_max_results     = _get("tools", "webSearchMaxResults"),
            bash_max_output_chars      = _get("tools", "bashMaxOutputChars"),
            mcp_max_output_chars       = _get("tools", "mcpMaxOutputChars"),
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

            model_repeat_penalty = model_repeat_penalty,
            model_seed           = model_seed,
            ollama_retry_count   = ollama_retry_count,
            ollama_retry_delay   = ollama_retry_delay,

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
            mcp_devops_assistant_enabled = raw.get("mcp", {}).get(
                "devopsAssistant", DEFAULT_CONFIG["mcp"]["devopsAssistant"]
            ).get("enabled", True),
            mcp_database_assistant_enabled = raw.get("mcp", {}).get(
                "databaseAssistant", DEFAULT_CONFIG["mcp"]["databaseAssistant"]
            ).get("enabled", False),
            mcp_iot_assistant_enabled = raw.get("mcp", {}).get(
                "iotAssistant", DEFAULT_CONFIG["mcp"]["iotAssistant"]
            ).get("enabled", False),
            mcp_http_client_assistant_enabled = raw.get("mcp", {}).get(
                "httpClientAssistant", DEFAULT_CONFIG["mcp"]["httpClientAssistant"]
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
            rag_max_file_chars       = _get("rag", "maxFileChars"),
            rag_chunk_chars          = _get("rag", "chunkChars"),
            rag_chunk_overlap        = _get("rag", "chunkOverlap"),
            rag_max_files            = _get("rag", "maxFiles"),
            rag_min_slot_chars       = _get("rag", "minSlotChars"),

            vision_enabled        = raw.get("vision", {}).get("enabled",
                                            DEFAULT_CONFIG["vision"]["enabled"]),
            vision_show_indicator = raw.get("vision", {}).get("showIndicator",
                                            DEFAULT_CONFIG["vision"]["showIndicator"]),

            completion_phrase        = raw.get("completion", {}).get("phrase",
                                            DEFAULT_CONFIG["completion"]["phrase"]),
            completion_extra_phrases = raw.get("completion", {}).get("extraPhrases",
                                            list(DEFAULT_CONFIG["completion"]["extraPhrases"])),

            chatlog_enabled     = raw.get("chatlog", {}).get("enabled",
                                          DEFAULT_CONFIG["chatlog"]["enabled"]),
            chatlog_path        = raw.get("chatlog", {}).get("path",
                                          DEFAULT_CONFIG["chatlog"]["path"]),
            chatlog_max_size_mb = raw.get("chatlog", {}).get("maxSizeMb",
                                          DEFAULT_CONFIG["chatlog"]["maxSizeMb"]),

            webui_enabled      = raw.get("webui", {}).get("enabled",
                                         DEFAULT_CONFIG["webui"]["enabled"]),
            webui_host         = raw.get("webui", {}).get("host",
                                         DEFAULT_CONFIG["webui"]["host"]),
            webui_port         = int(raw.get("webui", {}).get("port",
                                         DEFAULT_CONFIG["webui"]["port"])),
            webui_log_file     = raw.get("webui", {}).get("logFile",
                                         DEFAULT_CONFIG["webui"]["logFile"]),
            webui_log_max_size = raw.get("webui", {}).get("logMaxSizeMb",
                                         DEFAULT_CONFIG["webui"]["logMaxSizeMb"]),

            subagents_max_concurrent    = raw.get("subagents", {}).get("maxConcurrent",
                                               DEFAULT_CONFIG["subagents"]["maxConcurrent"]),
            subagents_max_teams         = raw.get("subagents", {}).get("maxTeams",
                                               DEFAULT_CONFIG["subagents"]["maxTeams"]),
            subagents_max_team_size     = raw.get("subagents", {}).get("maxTeamSize",
                                               DEFAULT_CONFIG["subagents"]["maxTeamSize"]),
            subagents_recent_ttl        = raw.get("subagents", {}).get("recentTtl",
                                               DEFAULT_CONFIG["subagents"]["recentTtl"]),
            subagents_default_priority  = raw.get("subagents", {}).get("defaultPriority",
                                               DEFAULT_CONFIG["subagents"]["defaultPriority"]),
            subagents_auto_cont_max     = raw.get("subagents", {}).get("autoContMax",
                                               DEFAULT_CONFIG["subagents"]["autoContMax"]),
            subagents_inference_timeout = raw.get("subagents", {}).get("inferenceTimeout",
                                               DEFAULT_CONFIG["subagents"]["inferenceTimeout"]),
            subagents_default_timeout   = raw.get("subagents", {}).get("defaultTimeout",
                                               DEFAULT_CONFIG["subagents"]["defaultTimeout"]),

            backup_enabled    = raw.get("backup", {}).get("enabled",
                                        DEFAULT_CONFIG["backup"]["enabled"]),
            backup_dir        = raw.get("backup", {}).get("dir",
                                        DEFAULT_CONFIG["backup"]["dir"]),
            backup_max_files  = raw.get("backup", {}).get("maxFiles",
                                        DEFAULT_CONFIG["backup"]["maxFiles"]),
            backup_extensions = raw.get("backup", {}).get("extensions",
                                        list(DEFAULT_CONFIG["backup"]["extensions"])),
        )

        # ── Migración automática: añadir secciones nuevas y eliminar campos deprecated ──
        _missing_sections  = [
            k for k in DEFAULT_CONFIG
            if k not in raw and k != "api"   # "api" puede no existir en configs antiguas → se añade en save()
        ]
        _has_api_gap = "api" not in raw
        # Campos deprecated eliminados de la spec pero que pueden seguir en el JSON
        _has_deprecated = "maxTokens" in raw.get("context", {})
        # modelOptions legacy: si existe en el JSON, save() lo eliminará y relocaliza los valores
        _has_model_opts_legacy = "modelOptions" in raw
        # Claves nuevas dentro de secciones existentes
        _has_mcp_gaps = (
            "systemAssistant" not in raw.get("mcp", {}) or
            "devopsAssistant" not in raw.get("mcp", {}) or
            "databaseAssistant" not in raw.get("mcp", {}) or
            "homeOfficeAssistant" not in raw.get("mcp", {}) or
            "securityAssistant" not in raw.get("mcp", {}) or
            "iotAssistant" not in raw.get("mcp", {}) or
            "httpClientAssistant" not in raw.get("mcp", {})
        )
        # embed_max_input_chars: migrar valores obsoletos (≤3000) al nuevo default (8000)
        _embed_old = raw.get("embeddings", {}).get("maxInputChars", 0)
        if isinstance(_embed_old, int) and _embed_old <= 3000:
            _cfg.embed_max_input_chars = 8000
        # Migración: añadir maxThinkingTokens a modelos con thinking block que no lo tengan
        _old_max_think = _mo_raw.get("maxThinkingTokens", 6000)
        _has_thinking_gap = False
        for _mid, _mcfg in _cfg.model_configs.items():
            if "thinking" in _mcfg and "maxThinkingTokens" not in _mcfg["thinking"]:
                _mcfg["thinking"]["maxThinkingTokens"] = _old_max_think
                _has_thinking_gap = True
        if _missing_sections or _has_deprecated or _has_mcp_gaps or _has_model_opts_legacy or _has_thinking_gap or _has_api_gap:
            _cfg.save()

        return _cfg

    def save(self) -> None:
        CONFIG_FILE = _const("CONFIG_FILE")
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

        # Bloque unificado "api": backend + parámetros de servidor en un solo sitio
        _ap = raw.setdefault("api", {})
        _ap["type"]             = self.api_type
        _ap["key"]              = self.api_key
        _ap["host"]             = self.ollama_host
        _ap["extraHosts"]       = self.ollama_extra_hosts
        _ap["embedHost"]        = self.ollama_embed_host
        _ap["subagentRouting"]  = self.ollama_subagent_routing
        _ap["ollamaRetryCount"] = self.ollama_retry_count
        _ap["ollamaRetryDelay"] = self.ollama_retry_delay
        raw.pop("ollama", None)   # bloque legacy fusionado en "api"
        raw["permissions"] = self.permissions

        # Contexto (maxTokens eliminado: se calcula desde models.configs)
        ctx = raw.setdefault("context", {})
        ctx.pop("maxTokens", None)   # limpia el campo legacy si existe
        ctx["minKeep"]             = self.compact_min_keep
        ctx["compactThreshold"]    = self.compact_threshold
        ctx["maxSummaryChars"]     = self.max_summary_chars
        ctx["maxToolResultTokens"] = self.max_tool_result_tokens
        ctx["autoContinueMax"]     = self.auto_continue_max
        ctx["highWater"]           = self.context_high_water
        ctx["toolMaxChars"]        = self.context_tool_max_chars
        ctx["ctxMode"]             = self.ctx_mode

        # Embeddings
        emb = raw.setdefault("embeddings", {})
        emb["model"]               = self.embed_model
        emb["maxInputChars"]       = self.embed_max_input_chars
        emb["similarityThreshold"] = self.embed_similarity_threshold
        emb["snippetChars"]        = self.embed_snippet_chars
        emb["topK"]                = self.embed_top_k
        emb["memoryEmbedEnabled"]  = self.memory_embed_enabled
        emb["diskCacheEnabled"]    = self.embed_disk_cache_enabled
        emb["diskCacheDir"]        = self.embed_disk_cache_dir
        emb["diskCacheMaxEntries"] = self.embed_disk_cache_max
        emb["ramCacheMax"]         = self.embed_ram_cache_max

        # Herramientas
        tools = raw.setdefault("tools", {})
        tools["readFileLinesDefault"]   = self.read_file_lines_default
        tools["readFileLinesWarnLarge"] = self.read_file_lines_warn_large
        tools["webFetchMaxChars"]       = self.web_fetch_max_chars
        tools["webFetchTimeout"]        = self.web_fetch_timeout
        tools["webSearchMaxResults"]    = self.web_search_max_results
        tools["bashMaxOutputChars"]     = self.bash_max_output_chars
        tools["mcpMaxOutputChars"]      = self.mcp_max_output_chars
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

        # Eliminar bloque legacy modelOptions si quedó del formato anterior
        raw.pop("modelOptions", None)

        # Per-model context configs + defaults globales
        models_sec = raw.setdefault("models", {})
        models_sec["systemOverhead"] = self.model_system_overhead
        if self.model_repeat_penalty is not None:
            models_sec["repeatPenalty"] = self.model_repeat_penalty
        else:
            models_sec.pop("repeatPenalty", None)
        if self.model_seed is not None:
            models_sec["seed"] = self.model_seed
        else:
            models_sec.pop("seed", None)
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
        mcp_sec.setdefault("devopsAssistant",   {})["enabled"] = self.mcp_devops_assistant_enabled
        mcp_sec.setdefault("databaseAssistant", {})["enabled"] = self.mcp_database_assistant_enabled
        mcp_sec.setdefault("iotAssistant", {})["enabled"]          = self.mcp_iot_assistant_enabled
        mcp_sec.setdefault("httpClientAssistant", {})["enabled"]  = self.mcp_http_client_assistant_enabled

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
        rag["maxFileChars"]        = self.rag_max_file_chars
        rag["chunkChars"]          = self.rag_chunk_chars
        rag["chunkOverlap"]        = self.rag_chunk_overlap
        rag["maxFiles"]            = self.rag_max_files
        rag["minSlotChars"]        = self.rag_min_slot_chars

        # Visión
        vis = raw.setdefault("vision", {})
        vis["enabled"]       = self.vision_enabled
        vis["showIndicator"] = self.vision_show_indicator

        # Finalización de tarea: ajuste interno/avanzado (señal de fin de turno +
        # auto-continue). NO se materializa en oocode.json para no exponerlo como
        # personalización de usuario. load() lo sigue leyendo si un agente multi-idioma
        # lo añade a mano; si ya existe en el JSON, no se toca (se preserva tal cual).

        # Chat log
        cl = raw.setdefault("chatlog", {})
        cl["enabled"]   = self.chatlog_enabled
        cl["path"]      = self.chatlog_path
        cl["maxSizeMb"] = self.chatlog_max_size_mb

        # WebUI
        wu = raw.setdefault("webui", {})
        wu["enabled"]      = self.webui_enabled
        wu["host"]         = self.webui_host
        wu["port"]         = self.webui_port
        wu["logFile"]      = self.webui_log_file
        wu["logMaxSizeMb"] = self.webui_log_max_size

        # Subagentes
        sa = raw.setdefault("subagents", {})
        sa["maxConcurrent"]    = self.subagents_max_concurrent
        sa["maxTeams"]         = self.subagents_max_teams
        sa["maxTeamSize"]      = self.subagents_max_team_size
        sa["recentTtl"]        = self.subagents_recent_ttl
        sa["defaultPriority"]  = self.subagents_default_priority
        sa["autoContMax"]      = self.subagents_auto_cont_max
        sa["inferenceTimeout"] = self.subagents_inference_timeout
        sa["defaultTimeout"]   = self.subagents_default_timeout

        # Backups
        bk = raw.setdefault("backup", {})
        bk["enabled"]    = self.backup_enabled
        bk["dir"]        = self.backup_dir
        bk["maxFiles"]   = self.backup_max_files
        bk["extensions"] = self.backup_extensions or list(DEFAULT_CONFIG["backup"]["extensions"])

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
            Path(self.workspace).expanduser(),
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
