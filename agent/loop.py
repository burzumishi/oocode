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
from tools.hooks import _is_write_tool, _is_modify_tool
from workspace.manager import WorkspaceManager
from config import DEFAULT_CONFIG as _DEFAULT_CONFIG


# ── Helpers y constantes (re-exportadas para compatibilidad hacia atrás) ───────
from agent.loop_helpers import (  # noqa: F401
    _SPINNER_FRAMES, _POLL_INTERVAL, _HEADER_ANIM_CODES, _ANSI_BOLD, _ANSI_RESET,
    _TIMEOUT_SENTINEL, _FALLBACK_MIN_CHARS, _THINKING_WORDS, _MULTITASK_WORDS,
    _TASK_PREFLIGHT_PHRASES, _TASK_ICON_COLORS, _PREFLIGHT_USER_GREETINGS,
    _SINGLE_PREFLIGHT_GENERIC, _PF_ACTIONS, _PF_DOMAINS, _PF_PHRASES,
    _MULTI_ICON_STYLES, _COMPACT_LOCK, _DONE_WORDS, _NEAR_FINISH_PHRASES,
    _TOOL_ALIASES, _IMG_EXTENSIONS,
    _SUBAGENT_COLORS, _TOOL_LIVE_VERBS,
    SYSTEM_HEADER, _TOOL_GROUPS, _TASK_KEYWORDS, SYSTEM_RULES,
    _pick_preflight_phrase, _fmt_elapsed, _fmt_tokens, _rag_display,
    _is_complex_query, _load_images_b64, _ctx_bar, _compact_hint,
    _pbar_thin_ratio, _sfmt, _bar_style, _hint_styled,
    _make_compact_summary,
    _make_tool_preview, _pick_file_switch_phrase,
    _SUBAGENT_SPINNER_POLL, _MAX_PLAN_TASKS, _BASH_OVERUSE_RATIO,
)
from webui.loop_webui import WebUIMixin
from ui.loop_tui import TUIDisplayMixin

class AgentLoop(TUIDisplayMixin, WebUIMixin):
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
            high_water=config.context_high_water,
            tool_max_chars=config.context_tool_max_chars,
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
        self._client_needs_rebuild: bool = False  # True después de kill: reconstruir httpx antes del próximo request
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
        # WebUI SSE output queue — set by WebUI to capture loop output for browser streaming
        self._webui_queue = None    # queue.SimpleQueue | None
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
        self._current_write_target: str = ""   # Último fichero editado/escrito (para auto-split)
        # Fichero actual procesado por tools de búsqueda (para mostrar en spinner)
        self._tool_current_file: str = ""
        # Live block callbacks (inyectados por OOCodeApp; None en modo REPL)
        self._start_live_block_cb: Optional[Callable] = None
        self._update_live_tools_cb: Optional[Callable] = None
        self._update_live_current_tool_cb: Optional[Callable] = None  # muestra tool en ⎿ durante ejecución
        self._update_live_preview_cb: Optional[Callable] = None       # líneas de preview (1-4) mientras corre
        self._update_live_tool_start_cb: Optional[Callable] = None    # atómico: label + preview (sin double-flash)
        self._flush_live_block_cb: Optional[Callable] = None
        self._set_plan_header_mode_cb: Optional[Callable] = None  # inyectado por OOCodeApp
        self._live_tool_count: int = 0   # tools completadas en el live block actual
        # True si el modelo emitió texto al usuario en el turno actual
        self._turn_text_emitted: bool = False
        # Buffer de salida para subagentes: max 12 líneas visibles por turno
        self._sub_lines_shown: int = 0
        _MAX_SUB_LINES_PER_TURN = 12
        self._MAX_SUB_LINES = _MAX_SUB_LINES_PER_TURN
        # Referencia al ActiveSubAgent para actualizar stats (None = no es subagente)
        self._sub_stats_ref = None
        # Último resultado de tests de la tarea actual (se resetea en run())
        self._task_last_test: str = ""

    def close(self) -> None:
        """Libera recursos de forma determinista: cierra el httpx.Client de Ollama
        si este AgentLoop es su propietario.  Llamar explícitamente antes de salir;
        __del__ actúa solo como red de seguridad."""
        if not getattr(self, "_owns_client", True):
            return
        client = getattr(self, "client", None)
        if client is None:
            return
        try:
            client.close()
        except Exception as e:
            log.debug("client_close_error", error=str(e))
        self._owns_client = False  # evita doble cierre si __del__ se invoca después

    def __del__(self):
        self.close()

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
                    self._webui_emit({"type": "embed_flash", "op": "read"})
                    self._turn_mem_snippet = self.memory.context_snippet(
                        self._last_user_msg
                    )
                except Exception as e:
                    log.debug("mem_snippet_error", error=str(e))
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
                except Exception as e:
                    log.debug("rag_snippet_error", error=str(e))
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

    _RICH_TAG_RE = re.compile(r'\[/?[^\]]+\]')   # sync con ui/app.py: strip Rich + residuos ANSI numéricos

    @staticmethod
    def _strip_rich(text: str) -> str:
        return AgentLoop._RICH_TAG_RE.sub('', text)

    def _print(self, *args, **kwargs):
        if not self.capture_output:
            if self.is_subagent:
                # Prefijo │ con color rotativo; buffer máximo de _MAX_SUB_LINES por turno
                col = _SUBAGENT_COLORS[self._subagent_color_idx % len(_SUBAGENT_COLORS)]
                if self._sub_lines_shown < self._MAX_SUB_LINES:
                    console.print(f"  [bold {col}]│[/bold {col}]", *args, **kwargs)
                    self._sub_lines_shown += 1
                    if self._sub_lines_shown == self._MAX_SUB_LINES:
                        console.print(f"  [dim {col}]│   … buffer lleno (ctrl+o para ver completo)[/dim {col}]")
            else:
                console.print(*args, **kwargs)
        # WebUI SSE: emit stripped text
        if getattr(self, "_webui_queue", None) is not None and args:
            text = " ".join(str(a) for a in args)
            plain = self._strip_rich(text).strip()
            if plain:
                self._webui_emit({"type": "text", "text": plain})

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
        "smart_replace":    "Replace",
        "regex_replace":    "Replace",
        "bulk_replace":     "ReplaceAll",
        "patch_apply":      "Patch",
        "read_sections":    "Read",
        "code_outline":     "Outline",
        "diff_files":       "Diff",
        "run_tests":        "Test",
        "test_file":        "Test",
        "analyze_codebase": "Analyze",
        "affected_files":   "CheckUsage",
        "lsp_diagnostics":  "Diagnostics",
        "lsp_hover":        "Hover",
        "lsp_references":   "References",
        "lsp_rename":       "Rename",
        "lsp_type_definition": "TypeDef",
        "lsp_implementation":  "Impl",
        "extract_functions": "Extract",
        "extract_classes":  "Extract",
        "spawn_subagent":   "Subagent",
        "pip_tool":         "Pip",
        "npm_tool":         "Npm",
        "docker_ps":        "Docker",
        "docker_logs":      "DockerLogs",
        "docker_exec":      "DockerExec",
        "docker_inspect":   "DockerInspect",
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
            pat  = str(args.get("pattern", ""))
            d    = args.get("directory", args.get("path", ""))
            base = d.rsplit("/", 1)[-1] if d else ""
            return _esc(f'("{pat}"  {base})') if pat else ""
        if name in ("symbol_lookup",):
            return _esc(f"({args.get('symbol', '')})")
        if name == "multi_grep":
            pats = args.get("patterns", [])
            s = ", ".join(str(p) for p in (pats if isinstance(pats, list) else [str(pats)]))
            return _esc(f"([{s}])")
        if name == "bash":
            # Primera línea del comando (comandos multilinea: solo el inicio)
            cmd = args.get("command", "").splitlines()[0] if args.get("command") else ""
            return _esc(f"({cmd})")
        if name in ("find_file", "find_files", "find_dir"):
            n = args.get("name") or args.get("extension") or args.get("glob", "")
            d = args.get("directory", "")
            base = d.rsplit("/", 1)[-1] if d else ""
            return _esc(f"({n}  {base})") if n and base else _esc(f"({n})") if n else ""
        if name in ("bulk_replace", "regex_replace", "smart_replace"):
            pat = str(args.get("pattern", "") or args.get("search", ""))
            return _esc(f'("{pat}")') if pat else ""
        if name == "make_run":
            target = args.get("target", "all")
            d      = args.get("directory", "").rsplit("/", 1)[-1]
            return _esc(f"({target}  {d})") if d else _esc(f"({target})")
        if name == "python_exec":
            first = str(args.get("code", "")).split("\n")[0]
            return _esc(f"({first}…)") if "\n" in str(args.get("code", "")) else _esc(f"({first})")
        if name in ("git_diff", "git_log", "git_add", "git_commit"):
            msg = args.get("message") or args.get("path") or args.get("files", "")
            if isinstance(msg, list):
                msg = ", ".join(str(m) for m in msg)
            return _esc(f"({str(msg)})") if msg else ""
        if name in ("lsp_diagnostics", "lint_file", "mypy_check"):
            p = args.get("path", "")
            return _esc(f"({_short_path(p)})") if p else ""
        return ""



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



    def _show_tool_block(self, name: str, args: dict, result: str,
                         allowed: bool, block_mode: bool = False,
                         suppress_header: bool = False,
                         pre_shown: bool = False,
                         batch_idx: int = -1) -> None:
        """Muestra un tool call al estilo Claude Code:

          ● ToolName(contexto)
            ⎿  primera línea del resultado
               segunda línea
               … +N líneas (ctrl+o to expand)

        Bloqueos del agente usan ⊘ en amarillo.
        Hints del agente (⚡) se muestran en cyan al final.
        suppress_header=True → batch agrupado: Name(ctx_brief) con ⎿ /spaces.
        batch_idx >= 0       → posición en batch (0=⎿ , >0=spaces, >=3=oculto).
        pre_shown=True       → header ya impreso antes de ejecutar: salta al resultado.
        """
        if self.capture_output:
            return

        # spawn_subagent: el header ● y el footer ⎿ Done ya se imprimieron dentro
        # del closure spawn_subagent() — no mostrar resultado estándar
        if name == "spawn_subagent" and not self.is_subagent:
            self._webui_emit({"type": "subagent_done", "agent_id": args.get("agent_id", "")})
            return

        # plan_create: ya emitió su propio evento 'plan' — no emitir tool_done
        if name == "plan_create" and getattr(self, "_webui_queue", None) is not None:
            return

        # WebUI: emitir tool_done estructurado y salir — _print() contaminaría el chat
        if getattr(self, "_webui_queue", None) is not None:
            _result_str = str(result)
            _disp  = self._TOOL_DISPLAY_NAMES.get(name, name)
            _ctx   = self._strip_rich(self._call_context(name, args)).strip()
            _is_ok = allowed and not _result_str.startswith("⛔")
            _prev  = _result_str.splitlines()[0] if _result_str else ""
            _ev: dict = {
                "type":    "tool_done",
                "tool":    _disp,
                "raw":     name,
                "context": _ctx,
                "ok":      _is_ok,
                "n_lines": len(_result_str.splitlines()),
                "preview": _prev,
            }
            # Detectar fichero creado/editado para mostrar tarjeta de descarga
            if _is_ok:
                import os as _ose, re as _re_fp
                _FC = frozenset((
                    "write_file", "create_file", "save_file",
                    "doc_create", "doc_create_rfc", "doc_project_save",
                    "doc_create_from_template", "doc_fill_template",
                    "doc_fill_corporate_template", "doc_convert",
                    "xlsx_create_report", "xlsx_create_table",
                    "pptx_create", "pptx_create_from_template",
                ))
                _FE = frozenset((
                    "edit_file", "edit_files", "regex_replace",
                    "smart_replace", "bulk_replace", "patch_apply",
                    "doc_update_section", "xlsx_fill_range",
                ))
                _FSC = ("_write_file", "_create_file", "_save_file",
                        "_doc_create", "_spreadsheet_create",
                        "_presentation_create", "_export_pdf",
                        "_create_report", "_create_table",
                        "_fill_template", "_corporate_template")
                _FSE = ("_edit_file", "_edit_files", "_regex_replace",
                        "_smart_replace", "_bulk_replace", "_patch_apply",
                        "_update_section", "_fill_range")
                _is_fc = name in _FC or any(name.endswith(s) for s in _FSC)
                _is_fe = name in _FE or any(name.endswith(s) for s in _FSE)
                if _is_fc or _is_fe:
                    _p = (args.get("path") or args.get("file_path") or
                          args.get("output_path") or args.get("filepath") or
                          args.get("dest") or "")
                    if not _p and "edits" in args and isinstance(args["edits"], list):
                        _paths = [e.get("path", "") for e in args["edits"] if e.get("path")]
                        _p = _paths[0] if _paths else ""
                    # Fallback: extraer ruta del texto de resultado (ej. "✅ Guardado: /ruta/f.docx")
                    if not _p and _result_str:
                        _ext_p = r'\.(?:docx|xlsx|pptx|pdf|odt|csv|md|txt|json|yaml|yml)'
                        _fm = _re_fp.search(r'(/\S+' + _ext_p + r')', _result_str)
                        if _fm:
                            _p = _fm.group(1).rstrip('.,;)')
                    if isinstance(_p, str) and _p:
                        _abs = _ose.path.abspath(_ose.path.expanduser(str(_p)))
                        if _ose.path.isfile(_abs):
                            _ev["file_path"]   = _abs
                            _ev["file_name"]   = _ose.path.basename(_abs)
                            _ev["file_size"]   = _ose.path.getsize(_abs)
                            _ev["file_action"] = "created" if _is_fc else "edited"
            self._webui_emit(_ev)
            self._webui_emit(self._webui_status())
            return

        from rich.markup import escape as _esc

        display = self._TOOL_DISPLAY_NAMES.get(name, name)
        ctx     = self._call_context(name, args)

        # TUI mode — dos caminos:
        # • pre_shown=True (ejecución secuencial): header ya impreso por _show_tool_running_header;
        #   mostramos resultado compacto inline y NO añadimos a _turn_block.
        # • pre_shown=False (ejecución paralela): añadimos a _turn_block para resumen al final.
        if getattr(self, "_status_cb", None) is not None and not self.is_subagent and not block_mode:
            # Tools que modifican ficheros (write/edit/replace/patch, nativas y MCP)
            _is_modify  = _is_modify_tool(name)
            _result_str = str(result)
            _is_ok = not _result_str.startswith("⛔") and not _result_str.startswith("⚠️ DUPLICADO")

            if pre_shown:
                # Ejecución secuencial: el header ◐ solo se mostró para write/replace/mem.
                # Write/replace: mostrar diff visual; solo mostrar errores si falla.
                if _is_modify:
                    if not _is_ok:
                        self._print(f"  [dim red]⎿ {_esc(_result_str.splitlines()[0])}[/dim red]")
                    elif allowed:
                        self._render_tool_diff_print(name, args if isinstance(args, dict) else {}, _result_str)
                elif name in self._MEM_TOOLS:
                    # Herramientas de memoria: resultado compacto inline (ya tienen ◐)
                    self._show_inline_compact_result(name, args, _result_str, allowed)
                else:
                    # Todas las demás: bufferizar en _turn_block para resumen agrupado
                    self._turn_block.append((name, args if isinstance(args, dict) else {}, _result_str, allowed))
                # Actualizar contador live y limpiar label de tool actual (⎿ se ve actualizar en tiempo real)
                if self._update_live_tools_cb:
                    self._live_tool_count += 1
                    self._update_live_tools_cb(self._live_tool_count)
                if getattr(self, "_update_live_current_tool_cb", None):
                    self._update_live_current_tool_cb("")
                return

            # Ejecución paralela: acumular en _turn_block para resumen compacto al final
            self._turn_block.append((name, args if isinstance(args, dict) else {}, _result_str, allowed))
            if _is_modify and allowed and not suppress_header and _is_ok:
                _ctx_pl = self._strip_rich(ctx).strip() if ctx else ""
                _ctx_bl = (_ctx_pl.splitlines()[0].strip() if _ctx_pl else "")
                _ctx_brf = (_ctx_bl[:65] + "…" if len(_ctx_bl) > 65 else _ctx_bl) if _ctx_bl else ""
                _h = f"[bold]{_esc(display)}({_ctx_brf})[/bold]" if _ctx_brf else f"[bold]{_esc(display)}[/bold]"
                self._print(f"  [bold green]●[/bold green] {_h}")
                self._render_tool_diff_print(name, args if isinstance(args, dict) else {}, _result_str)
                self._turn_block_has_header = True
            # Actualizar contador live y limpiar label (paralelo: se incrementa conforme llegan resultados)
            if self._update_live_tools_cb:
                self._live_tool_count += 1
                self._update_live_tools_cb(self._live_tool_count)
            if getattr(self, "_update_live_current_tool_cb", None):
                self._update_live_current_tool_cb("")
            return

        # ── Header ────────────────────────────────────────────────────────────
        is_blocked  = isinstance(result, str) and result.startswith("⛔ AGENTE BLOQUEÓ")
        is_mem_tool = name in self._MEM_TOOLS

        if suppress_header:
            # Batch agrupado: Name(ctx_brief) con ⎿ en el primero, spaces en el resto
            _ctx_pl = self._strip_rich(ctx).strip() if ctx else ""
            _ctx_brief = (_ctx_pl[:45] + "…") if len(_ctx_pl) > 45 else _ctx_pl
            _label = f"{_esc(display)}({_esc(_ctx_brief)})" if _ctx_brief else _esc(display)
            if batch_idx < 0:
                # Fallback sin posición: ⎿ clásico
                self._print(f"  [dim]⎿ {_label}[/dim]")
            elif batch_idx < 3:
                if batch_idx == 0:
                    self._print(f"  [dim]⎿ {_label}[/dim]")
                else:
                    self._print(f"     [dim]{_label}[/dim]")
            # batch_idx >= 3: herramienta oculta, no imprimir
            return
        elif not pre_shown:
            # Header normal (alineado a 2 espacios, como el texto del asistente)
            # Subagentes: sin negrita para no saturar el output del padre
            if is_blocked:
                self._print(f"  [bold yellow]⊘[/bold yellow] [yellow]{_esc(display)}[/yellow][dim]{ctx}[/dim]")
            elif is_mem_tool:
                if self.is_subagent:
                    self._print(f"  [cyan]⬡[/cyan] [dim]{_esc(display)}{ctx}[/dim]")
                else:
                    self._print(f"  [bold cyan]⬡[/bold cyan] [bold cyan]{_esc(display)}[/bold cyan][dim]{ctx}[/dim]")
            elif self.is_subagent:
                self._print(f"  [dim]●  {_esc(display)}{ctx}[/dim]")
            else:
                _ctx_plain = self._strip_rich(ctx).strip() if ctx else ""
                _ctx_line1 = _ctx_plain.splitlines()[0].strip() if _ctx_plain else ""
                _ctx_brief = (_ctx_line1[:65] + "…" if len(_ctx_line1) > 65 else _ctx_line1) if _ctx_line1 else ""
                _hdr = f"[bold]{_esc(display)}({_ctx_brief})[/bold]" if _ctx_brief else f"[bold]{_esc(display)}[/bold]"
                self._print(f"  [bold green]●[/bold green] {_hdr}")
        # pre_shown=True → el header ya se mostró en _show_tool_running_header; solo resultados

        if self.rt.verbose:
            self._print(f"  [dim]{json.dumps(args, ensure_ascii=False, indent=2)}[/dim]")

        # ── Resultado ──────────────────────────────────────────────────────────
        if not allowed:
            self._print("  [dim red]⎿ Denegado[/dim red]")
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

        # ── Líneas de output (máx 5) con │ al estilo subagente ─────────────────
        MAX_SHOW   = 5
        line_color = "yellow" if is_blocked else ("cyan" if is_mem_tool else "dim")
        visible    = normal_lines[:MAX_SHOW]

        for line in visible:
            self._print(f"  [dim]│[/dim]  [{line_color}]{_esc(line)}[/{line_color}]")

        hidden = len(normal_lines) - len(visible)
        if hidden > 0:
            self._print(f"  [dim]│  … +{hidden} lines (ctrl+o to expand)[/dim]")

        # ── Hints del agente (⚡) — cyan dim ─────────────────────────────────
        if hint_lines:
            for line in hint_lines:
                self._print(f"  [dim cyan]│  {_esc(line)}[/dim cyan]")

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
        if self.capture_output:
            self._turn_block = []
            self._turn_block_has_header = False
            self._current_write_target = ""
            return

        # TUI con live block: cerrar el bloque dinámico con summary compacto
        if self._flush_live_block_cb:
            block = self._turn_block
            if getattr(self, "_turn_block_has_header", False):
                block = [t for t in block if not _is_modify_tool(t[0])]
            summary = _make_compact_summary(block) if block else ""
            if not summary and self._live_tool_count > 0:
                n = self._live_tool_count
                summary = f"Used {n} tool{'s' if n != 1 else ''} (ctrl+o to expand)"
            self._flush_live_block_cb(summary)
            self._live_tool_count = 0
            self._turn_block = []
            self._turn_block_has_header = False
            self._current_write_target = ""
            return

        # REPL fallback: print ⎿ summary al buffer estático
        if not self._turn_block or self._status_cb is None:
            self._turn_block = []
            self._turn_block_has_header = False
            return

        block = self._turn_block
        if getattr(self, "_turn_block_has_header", False):
            block = [t for t in block if not _is_modify_tool(t[0])]

        if block:
            summary = _make_compact_summary(block)
            self._print(f"  [dim]{summary}[/dim]")

        self._turn_block = []
        self._turn_block_has_header = False
        self._current_write_target = ""


    def _extract_write_target(self, name: str, args: dict) -> str:
        """Extrae la ruta del fichero destino de una write/replace tool."""
        p = (args.get("path") or args.get("file_path") or
             args.get("filepath") or args.get("output_path") or "")
        if not p and "edits" in args and isinstance(args["edits"], list):
            edits = args["edits"]
            p = edits[0].get("path", "") if edits else ""
        return str(p) if p else ""

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

        _in_webui = getattr(self, "_webui_queue", None) is not None

        # WebUI: plan_create se representa con el evento 'plan' — no emitir tool_start
        if _in_webui and name == "plan_create":
            return

        # WebUI: emitir evento estructurado tool_start
        if _in_webui:
            ctx_plain = self._strip_rich(ctx).strip()
            self._webui_emit({"type": "tool_start", "tool": display, "raw": name,
                              "context": ctx_plain})

        # Live block TUI: actualizar la línea |◐ con nombre de tool y preview de args
        if getattr(self, "_update_live_tool_start_cb", None) and self._status_cb:
            # Actualización atómica label+preview en una sola operación (evita double-flash)
            self._update_live_tool_start_cb(f"{display}:", _make_tool_preview(name, args))
            # ●: actualizar con verbo en gerundio + contexto breve
            if getattr(self, "_update_live_bullet_cb", None):
                _ctx_plain2 = self._strip_rich(ctx).strip()
                _verb = _TOOL_LIVE_VERBS.get(name, "Using")
                _ctx_brief = (_ctx_plain2[:45] if _ctx_plain2 else display).strip()
                self._update_live_bullet_cb(
                    f"{_verb} {_ctx_brief}…  (ctrl+o to expand)"
                )
        # spawn_subagent: header especial ● [emoji nombre]: tarea
        if name == "spawn_subagent" and not self.is_subagent:
            _sid   = args.get("agent_id", "")
            _stask = args.get("task", "")
            _tgt   = next((a for a in self.config.agents if a.id == _sid), None)
            _semoji = _tgt.emoji if _tgt else "🤖"
            _sname  = _tgt.name  if _tgt else _sid
            if not _in_webui:
                # TUI/REPL: mostrar cabecera inline; WebUI lo gestiona con subagent_start
                self._print(
                    f"\n  [bold green]●[/bold green] "
                    f"[bold][{_esc(_semoji)} {_esc(_sname)}]:[/bold] [dim]{_esc(_stask)}[/dim]"
                )
            self._webui_emit({"type": "subagent_start",
                              "agent_id": _sid, "agent_emoji": _semoji, "agent_name": _sname})
            self._sub_lines_shown = 0   # resetear buffer para este subagente
            return

        # WebUI: tool_start event ya emitido arriba; _print() aquí contaminaría el chat
        if _in_webui:
            return

        if self._status_cb is not None and not self.is_subagent:
            # TUI puro (no WebUI): sólo write/replace/mem muestran ◐ en la conversación.
            # El resto se bufferiza en _turn_block para resumen agrupado al final.
            _is_modify = _is_modify_tool(name)
            if _is_modify:
                # Auto-split: si el target es un fichero diferente al anterior, cerrar el bloque
                # actual con ⎿ y abrir uno nuevo con ● "Updating <nuevo-fichero>".
                _new_tgt = self._extract_write_target(name, args)
                if (_new_tgt and getattr(self, "_current_write_target", "") and
                        _new_tgt != self._current_write_target and
                        (self._turn_block or
                         getattr(self, "_turn_block_has_header", False) or
                         self._live_tool_count > 0)):
                    self._flush_turn_block()
                    import os as _ost
                    _bn = _ost.path.basename(_new_tgt)
                    _switch_phrase = _pick_file_switch_phrase(_bn)
                    if getattr(self, "_start_live_block_cb", None):
                        self._start_live_block_cb(_switch_phrase)
                        self._live_tool_count = 0
                    else:
                        self._print(
                            f"\n  [bold green]●[/bold green] {_esc(_switch_phrase)}"
                        )
                if _new_tgt:
                    self._current_write_target = _new_tgt
                self._print(
                    f"  [bold green]◐[/bold green] [bold]{_esc(display)}[/bold][dim]{ctx}[/dim]"
                )
                self._turn_block_has_header = True
            elif is_mem_tool:
                self._print(
                    f"  [bold cyan]◐[/bold cyan] [bold cyan]{_esc(display)}[/bold cyan][dim]{ctx}[/dim]"
                )
            # Para todas las demás tools: sin ◐ en conversación — el status bar y el live block muestran el progreso
            return

        # Subagentes en modo REPL: usar formato más compacto (sin negrita) para no saturar
        if self.is_subagent:
            if is_mem_tool:
                self._print(f"  [cyan]◐[/cyan] [dim]{_esc(display)}{ctx}[/dim]")
            else:
                self._print(f"  [dim]◐  {_esc(display)}{ctx}[/dim]")
        elif is_mem_tool:
            self._print(f"  [bold cyan]◐[/bold cyan] [bold cyan]{_esc(display)}[/bold cyan][dim]{ctx}[/dim]")
        else:
            self._print(f"  [bold green]◐[/bold green] [bold]{_esc(display)}[/bold][dim]{ctx}[/dim]")


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
            f"  [dim]trace: {len(messages)} msgs  │  "
            f"system {sys_len} chars (~{sys_len // 4} tok)  │  "
            f"ctx ~{ctx['tokens_estimate']} tok  │  "
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
        """Construye kwargs para client.chat() a partir del dict ya filtrado de _build_options."""
        if not opts:
            return {}
        return {"options": opts}

    # ── LLM call ─────────────────────────────────────────────────────────────

    def _close_stream_connection(self) -> None:
        """Cierra el httpx.Client interno de ollama para interrumpir cualquier
        streaming en curso.  Marca el cliente para reconstrucción antes del
        próximo request."""
        try:
            if hasattr(self.client, "_client"):
                self.client._client.close()
        except Exception as e:
            log.debug("stream_close_error", error=str(e))
        self._client_needs_rebuild = True

    def _rebuild_client_if_needed(self) -> None:
        """Reconstruye el ollama.Client si el anterior fue cerrado por kill."""
        if not self._client_needs_rebuild:
            return
        try:
            self.client = ollama.Client(host=self.config.ollama_host)
            self._client_needs_rebuild = False  # solo en éxito: un fallo preserva el flag para reintentar
        except Exception as e:
            log.warning("client_rebuild_failed", host=self.config.ollama_host, error=str(e))

    def _stream_response(self, messages: list, tools: list) -> tuple[str, list, int, int]:
        self._rebuild_client_if_needed()
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
                            self._close_stream_connection()  # aborta el thread del executor y marca rebuild
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
                self._close_stream_connection()  # marca rebuild: la conexión puede haber quedado rota
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
                _kill_ev = threading.Event()   # señal para abortar stream_bg antes de tiempo

                _think_chars_sh: list = [0]    # chars de thinking acumulados
                _max_think_chars = (self.config.max_thinking_tokens * 4
                                    if getattr(self.config, "max_thinking_tokens", 0) > 0
                                    else 0)

                def _stream_bg() -> None:
                    try:
                        for chunk in stream:
                            if _kill_ev.is_set():
                                break   # kill solicitado: dejar de emitir chunks
                            msg = chunk.message
                            if msg.thinking:
                                _think_chars_sh[0] += len(msg.thinking)
                                if _max_think_chars > 0 and _think_chars_sh[0] > _max_think_chars:
                                    _kill_ev.set()
                                    break  # thinking excesivo: abortar y reintentar sin thinking
                            if msg.content:
                                text_parts.append(msg.content)
                                _out_chars_sh[0] += len(msg.content)
                                # Streaming en tiempo real al WebUI (SSE stream_chunk)
                                self._webui_emit({"type": "stream_chunk", "text": msg.content})
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
                                except Exception as e:
                                    log.debug("tool_call_token_count_error", error=str(e))
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

                fb_timeout       = self.config.model_timeout(self._active_model())
                _timeout_hit     = False
                _last_alive_emit = t_start   # watchdog: última vez que emitimos "aún vivo"
                _alive_interval  = 60.0      # emitir cada 60s si no hay output visible

                # Spinner a 200ms — no tight loop
                while not _done_ev.wait(timeout=_POLL_INTERVAL):
                    elapsed    = time.time() - t_start
                    frame      = _SPINNER_FRAMES[fi % len(_SPINNER_FRAMES)]
                    ctx_s      = self.context.stats()
                    cpct       = int(ctx_s["tokens_estimate"] / max(ctx_s["max_tokens"], 1) * 100)
                    plain_bar  = _ctx_bar(ctx_s["tokens_estimate"], ctx_s["max_tokens"], 10, plain=True)
                    thresh_pct = int(self.context.compact_threshold * 100)
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
                        _tlabel = _active_task_txt.rstrip()
                        # Modo multitarea: ◈ animado + "Multitarea:" coloreado + progreso + tarea
                        _tok_up = f"↑{_fmt_tokens(self._turn_inp)}" if self._turn_inp > 0 else ""
                        _tok_dn = f"↓~{_fmt_tokens(approx_out)}" if approx_out > 0 else ""
                        _tok_inline = "  ·  " + "  ".join(filter(None, [_tok_up, _tok_dn])) if (_tok_up or _tok_dn) else ""
                        _prog = f"[{_plan_done + 1}/{_plan_total}]" if _plan_total > 1 else ""
                        _mic_st = _MULTI_ICON_STYLES[(fi // 2) % len(_MULTI_ICON_STYLES)]
                        _diamond = _sfmt(_mic_st, "◈")
                        _multi_lbl = _sfmt("status-word", "Multitarea:")
                        line1 = f"{frame}  {_diamond} {_multi_lbl} {_prog}  {_tlabel}  ({_time_str}{_tok_inline})"
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
                        self._sep_label = f"{frame} {_display_word}"
                    self._status_cb(f"{line1}\n{line2}")
                    fi += 1

                    # Watchdog "aún vivo": avisar al WebUI cada 60s si no hay output
                    # y enviar t/s si hay tokens generándose
                    if elapsed - _last_alive_emit >= _alive_interval:
                        _last_alive_emit = elapsed
                        _tps = approx_out / max(elapsed, 1)
                        if approx_out > 0:
                            _alive_msg = f"Generando… ({_fmt_elapsed(elapsed)} · ~{_tps:.1f} t/s)"
                        else:
                            _alive_msg = f"Procesando… ({_fmt_elapsed(elapsed)})"
                        self._webui_emit({"type": "preflight", "label": _alive_msg})

                    # Kill solicitado: detener stream y salir inmediatamente
                    if self._kill_requested:
                        _kill_ev.set()              # señalizar _stream_bg
                        self._close_stream_connection()  # cierra HTTP → desbloquea _stream_bg
                        self._status_cb("")
                        return "", [], 0, 0

                    # Timeout → señalizar para usar fallback
                    if fb_timeout > 0 and elapsed >= fb_timeout and _out_chars_sh[0] < _FALLBACK_MIN_CHARS:
                        _timeout_hit = True
                        break

                if _timeout_hit:
                    _kill_ev.set()                   # detiene _stream_bg
                    self._close_stream_connection()  # cierra HTTP y marca rebuild para el retry
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
                    _done_r  = threading.Event()
                    _kill_r  = threading.Event()   # señal para abortar _stream_bg_repl

                    def _stream_bg_repl() -> None:
                        try:
                            for chunk in stream:
                                if _kill_r.is_set():
                                    break
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
                                    except Exception as e:
                                        log.debug("tool_call_token_count_error", error=str(e))
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
                            # Kill solicitado: detener stream y salir
                            if self._kill_requested:
                                _kill_r.set()
                                self._close_stream_connection()  # cierra HTTP → desbloquea _stream_bg_repl
                                return "", [], 0, 0
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
                        _kill_r.set()                    # detiene _stream_bg_repl
                        self._close_stream_connection()  # cierra HTTP y marca rebuild para el retry
                        self._last_elapsed = time.time() - t_start
                        return _TIMEOUT_SENTINEL, [], 0, 0
                    if _err_r[0] is not None:
                        error = _err_r[0]
                    else:
                        tool_calls_result = _tc_r[0]
                        inp_tokens = _inp_r[0]
                        out_tokens = _out_r[0]
                else:
                    # Sin fallback: comportamiento original + check kill por chunk
                    with Live(console=console, refresh_per_second=5, transient=True) as live:
                        for chunk in stream:
                            if self._kill_requested:
                                self._close_stream_connection()
                                break
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

            # Para errores XML no-EOF: retry simple antes de rendirse.
            # "element <function> closed by </parameter>" es no-determinístico:
            # el modelo a veces genera cierre erróneo; un retry suele producir XML válido.
            partial = "".join(text_parts)
            if _is_xml and not _is_eof_truncation:
                log.warn("xml_malformed_retry", model=self._active_model(),
                         error=error_str[:120])
                if not self.capture_output:
                    console.print(
                        "\n  [yellow]⚡[/yellow]  XML de tool call malformado "
                        "(tag incorrecto) — reintentando…\n"
                    )
                try:
                    resp2 = self.client.chat(
                        model=self._active_model(),
                        messages=messages,
                        tools=tools,
                        stream=False,
                        **self._chat_kwargs(opts),
                    )
                    _rm2 = resp2.message
                    return (
                        _rm2.content or "",
                        _rm2.tool_calls or [],
                        getattr(resp2, "prompt_eval_count", 0) or 0,
                        getattr(resp2, "eval_count", 0) or 0,
                    )
                except Exception as _rx2:
                    log.warn("xml_malformed_retry_failed", error=str(_rx2)[:80])
                    # Si el retry también falló pero tenemos texto parcial, devolverlo
                    if partial:
                        return partial, [], inp_tokens, out_tokens

            # Fallback: devolver texto parcial si existe
            if partial and _is_xml:
                log.warn("xml_tool_call_recovered", chars=len(partial),
                         model=self._active_model())
                if not self.capture_output:
                    console.print(
                        "\n  [yellow]⚠[/yellow]  El modelo generó tool calls en XML no válido "
                        "y el retry falló. Respuesta parcial recuperada.\n"
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
                self._close_stream_connection()  # error de red: marca rebuild para el siguiente intento
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
                lines.append(f"Usuario: {content}")
            elif role == "assistant":
                lines.append(f"Asistente: {content}")
            elif role == "tool":
                lines.append(f"Tool({m.get('name', '')}): {content}")
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
        _ckpt_modified = {p for p, _, is_edit in getattr(self, "_session_reads", []) if is_edit and p}
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
        # Bloque estructurado de estado — se inyecta siempre en el summary, sin depender
        # del LLM para preservar los paths. Garantiza que tras compactación el agente
        # conoce los ficheros activos y el directorio de proyecto.
        _structured_lines: list[str] = []
        _pdir = getattr(self.config, "project_dir", "") or ""
        if _pdir:
            _structured_lines.append(f"- Directorio de proyecto activo: {_pdir}")
        # Paths de ficheros editados/escritos (rutas absolutas desde _task_modified_files)
        _mod_paths = sorted(p for p in _ckpt_modified if p)
        if _mod_paths:
            _structured_lines.append(
                "- Ficheros modificados (rutas absolutas): "
                + ", ".join(_mod_paths[:10])
            )
        # Paths de ficheros leídos/editados esta sesión (desde _session_reads)
        # Usamos orden de última aparición: pop+reinsertar para que ficheros
        # re-accedidos queden al final del dict y aparezcan en [-10:].
        _sreads = getattr(self, "_session_reads", [])
        if _sreads:
            _seen_sr: dict[str, bool] = {}
            for _srpath, _, _sr_edit in _sreads:
                if _srpath:
                    _seen_sr.pop(_srpath, None)   # reubica al final si ya existía
                    _seen_sr[_srpath] = _sr_edit
            # Separar editados de solo-leídos y priorizar los editados
            _edited_abs = [p for p, ed in _seen_sr.items() if ed and p.startswith("/")]
            _read_only_abs = [p for p, ed in _seen_sr.items() if not ed and p.startswith("/")]
            # Últimos 6 editados + últimos 4 solo-leídos (máx 10 en total)
            _read_abs = _edited_abs[-6:] + _read_only_abs[-4:]
            if _read_abs:
                _structured_lines.append(
                    "- Ficheros accedidos recientemente (rutas absolutas): "
                    + ", ".join(_read_abs)
                )
        _structured_block = (
            "\n**Estado estructurado al compactar (conservar en el resumen):**\n"
            + "\n".join(_structured_lines)
            + "\n"
        ) if _structured_lines else ""

        try:
            opts = self._build_options()
            resp = self.client.chat(
                model=self._active_model(),
                messages=[{"role": "user", "content": prompt_text}],
                stream=False,
                **self._chat_kwargs(opts),
            )
            llm_summary = resp.message.content or ""
            # Combinar: bloque estructurado (siempre fiable) + resumen LLM (narrativo)
            summary = (_structured_block + "\n" + llm_summary).strip() if llm_summary else _structured_block.strip()
            if summary:
                # Escribe en memoria diaria como checkpoint
                self.ws.write_daily_memory(
                    f"\n### Checkpoint de compactación\n{summary}\n"
                )
            return summary
        except Exception:
            # Sin LLM: al menos preservar el bloque estructurado
            return _structured_block.strip()


    def _do_compact(self, with_summary: bool = True) -> int:
        """Compacta el contexto con barra de progreso. Devuelve msgs eliminados."""
        # Garantiza cliente fresco antes de cualquier llamada LLM del resumen,
        # independientemente del caller (turn loop, /compact, atajo de teclado).
        self._rebuild_client_if_needed()
        dropped_count = self._do_compact_impl(with_summary)
        if dropped_count > 0 and getattr(self.config, "snapshots_save_on_compact", False):
            self._save_session_snapshot()
        return dropped_count

    def _do_compact_impl(self, with_summary: bool = True) -> int:
        """Implementación real de compactación — llamada desde _do_compact.

        El _COMPACT_LOCK global asegura que solo un agente (principal o subagente)
        compacta a la vez. Esto evita saturar el LLM con múltiples llamadas de
        resumen simultáneas cuando varios subagentes necesitan compactar a la vez.
        """
        with _COMPACT_LOCK:
            return self._do_compact_locked(with_summary)


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
                    "  Ejemplo: docker_exec(container='myapp-web', command='php -v')"
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
                return top[:_MAX_PLAN_TASKS]

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
            return bullets[:_MAX_PLAN_TASKS]
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


    def _all_plan_tasks_done(self) -> bool:
        """True si hay plan y todas las tareas están completadas."""
        return bool(self._plan_tasks) and all(
            t["status"] == "done" for t in self._plan_tasks
        )



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
        Imprime _print_plan_panel_update() cuando la tarea activa cambia.
        """
        if not self._plan_tasks:
            return
        _prev_active = next(
            (i for i, t in enumerate(self._plan_tasks) if t["status"] == "active"), -1
        )
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
            # El panel de plan se actualiza en la status window automáticamente;
            # no imprimir bloque estático aquí (evita reprint por cada respuesta).
            return
        # Capa 2: anuncio de tarea específica
        _ANNOUNCE = re.compile(r'\b(?:tarea|paso|step|task)\s+(\d+)\s*[:\-]', re.I)
        m = _ANNOUNCE.search(text[:300])
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(self._plan_tasks):
                self._set_plan_task_active(idx)
                return
        # Capa 3: sincronizar con iteración actual — solo avanza, nunca retrocede.
        # Si el plan ya está completo no tocamos nada (evita regresión cuando
        # _auto_continue_count < índice de la última tarea y current_active cae a 0).
        if self._all_plan_tasks_done():
            return
        current_active = next(
            (i for i, t in enumerate(self._plan_tasks) if t["status"] == "active"),
            # Si no hay activa, anclar al índice del último "done" para que nunca
            # retroceda al 0 por defecto.
            max((i for i, t in enumerate(self._plan_tasks) if t["status"] == "done"),
                default=0),
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
            _review_note = (
                " Si hay ambigüedad o riesgo alto, añade '⚠ REQUIERE REVISIÓN: [motivo]' "
                "al final del plan para pausar y esperar confirmación."
            ) if not self.is_subagent else ""
            hints.append(
                f"\n[{n} tarea{'s' if n != 1 else ''} en la solicitud]:\n"
                f"{tasks_str}\n"
                f"Aborda TODAS en orden.{_review_note}\n"
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
        if total >= 3 and bash_n / total > _BASH_OVERUSE_RATIO:
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
                except Exception as e:
                    log.debug("read_path_parse_error", error=str(e))
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
        _ckpt_modified = {p for p, _, is_edit in getattr(self, "_session_reads", []) if is_edit and p}
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
            except Exception as e:
                log.debug("mem_search_error", error=str(e))
        r_word = "memory" if n_recalled == 1 else "memories"

        # Fase 2: Write
        self._tool_phase = (
            f"Recalled {n_recalled} {r_word}, writing 1 memory…"
        )
        self._webui_emit({"type": "embed_flash", "op": "save"})
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

        # Panel visual: impresión inmediata en formato simple MD — una sola vez al crear el plan.
        # No se repite tras compactación ni con cada cambio de tarea.
        # En modo app (live block activo), se activa _set_plan_header_mode_cb para que el output
        # vaya al header del live block y aparezca ENCIMA del ● en lugar de dentro del body.
        # En WebUI, _print() no se llama — solo se emite el evento estructurado 'plan'.
        if not self.capture_output:
            from rich.markup import escape as _mesc
            _ic = _TASK_ICON_COLORS[int(time.time()) % len(_TASK_ICON_COLORS)]
            _n = len(tasks)
            _hdr = summary[:100] if summary else f"{_n} tareas"
            _in_webui_plan = getattr(self, "_webui_queue", None) is not None
            if not _in_webui_plan:
                _pmode = getattr(self, "_set_plan_header_mode_cb", None)
                if _pmode:
                    _pmode(True)
                self._print(
                    f"\n  [{_ic}]◈[/{_ic}]  [bold]Plan de ejecución:[/bold] "
                    f"[dim]{_mesc(_hdr)}[/dim]"
                )
                for task in tasks[:_MAX_PLAN_TASKS]:
                    _short = (task[:80] + "…") if len(task) > 80 else task
                    self._print(f"  [dim]  - {_mesc(_short)}[/dim]")
                if len(tasks) > _MAX_PLAN_TASKS:
                    self._print(f"  [dim]  … +{len(tasks) - _MAX_PLAN_TASKS} más[/dim]")
                self._print("")
                if _pmode:
                    _pmode(False)
            else:
                # WebUI: emitir evento estructurado (sin _print() para evitar duplicación)
                self._webui_emit({"type": "plan", "tasks": tasks[:_MAX_PLAN_TASKS], "n": _n,
                                  "summary": summary,
                                  "extra": max(0, len(tasks) - _MAX_PLAN_TASKS)})

        first = tasks[0][:80]
        return (
            f"Plan creado: {len(tasks)} tareas. "
            f"Activa ahora [1/{len(tasks)}]: '{first}'. "
            f"Emite ahora un nuevo mensaje anunciando 'Tarea 1: ...' y luego ejecuta sus herramientas. "
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
        now_ts = time.time()
        self._plan_tasks[active_idx]["status"] = "done"
        self._plan_tasks[active_idx]["end_ts"] = now_ts

        done_count = sum(1 for t in self._plan_tasks if t["status"] == "done")
        total = len(self._plan_tasks)

        # Activar la siguiente pendiente
        next_idx = next(
            (i for i, t in enumerate(self._plan_tasks) if t["status"] == "pending"), -1
        )
        if next_idx >= 0:
            self._plan_tasks[next_idx]["status"] = "active"
            self._plan_tasks[next_idx]["start_ts"] = now_ts
            next_text = self._plan_tasks[next_idx]["text"][:80]
            # Emitir progreso al WebUI y actualizar panel TUI
            self._webui_emit({
                "type":   "plan_progress",
                "done":   done_count,
                "total":  total,
                "active": next_idx,
                "active_text": self._plan_tasks[next_idx]["text"],
                "tasks":  [{"text": t["text"], "status": t["status"]}
                           for t in self._plan_tasks],
            })
            # 1. Flush ⎿ de tools de esta tarea (va al cuerpo del live block si está activo)
            self._flush_task_intermediate_summary()
            # 2. Cerrar live block actual para crear frontera visual de tarea.
            #    _flush_live_block_cb("") es no-op si no había live block activo.
            if not self.capture_output and self._flush_live_block_cb:
                self._flush_live_block_cb("")
            # 3. Panel ◈ Plan [N/total] al buffer estático (live block ya cerrado)
            if not self.capture_output:
                self._print_plan_panel_update()
            # 4. Abrir nuevo live block con ● para la siguiente tarea,
            #    creando el mismo efecto visual que Claude Code entre tareas.
            if not self.capture_output and self._start_live_block_cb:
                from rich.markup import escape as _td_esc
                self._start_live_block_cb(_td_esc(next_text))
                self._live_tool_count = 0
            return (
                f"✔ Tarea {active_idx + 1}/{total} completada. "
                f"Activa ahora [{done_count + 1}/{total}]: '{next_text}'. "
                f"Continúa con ella directamente."
            )

        # Todas completadas → marcar todas las activas/pending como done también
        self._mark_all_plan_tasks_done()
        # Flush ⎿ final y cerrar live block de la última tarea
        self._flush_task_intermediate_summary()
        if not self.capture_output and self._flush_live_block_cb:
            self._flush_live_block_cb("")
        if not self.capture_output:
            self._print_plan_panel_update()
        return (
            f"✔ Todas las {total} tareas completadas.\n"
            f"⚠️ Responde al usuario con un resumen conciso y di "
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
                return cached
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
                # read_files: lista de paths — también persistir en _session_reads
                _paths_arg = args.get("paths") or []
                if isinstance(_paths_arg, str):
                    # si el modelo pasa "a.c,b.c" como string, separar individualmente
                    _paths_arg = [p.strip() for p in _paths_arg.split(",") if p.strip()]
                for _p in _paths_arg:
                    if _p:
                        self._turn_read_paths.add(str(_p))
                        if not str(result).startswith("Error"):
                            self._session_reads.append((str(_p), None, False))
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
                    except Exception as e:
                        log.debug("rag_invalidate_error", path=str(path), error=str(e))
                # Invalidar caché del system prompt para que el próximo call use RAG fresco
                self._sys_prompt_cache = None
                self._turn_rag_snippet = None
            return result

        result = self.registry.call(name, args)
        # Actualizar estadísticas del subagente activo (si estamos en modo subagente)
        _sub = getattr(self, "_sub_stats_ref", None)
        if _sub is not None:
            _sub.n_tool_uses += 1
        return result

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
        except Exception as e:
            log.debug("mark_new_session_error", error=str(e))

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
            except Exception as e:
                log.debug("on_new_session_error", error=str(e))

    def restore_session(self, session_id: str) -> int:
        messages = self.session.load_messages(session_id)
        self.context.clear()
        for msg in messages:
            self.context.messages.append(msg)
        self.context._invalidate_token_cache()
        return len(messages)

    # ── Turno principal ──────────────────────────────────────────────────────

    def _turn_reset_state(self, user_message: str, images: Optional[list[str]]) -> None:
        """Inicializa el estado del turno: resets, MCP hot-reload, contexto, permisos, hooks."""
        self._last_user_msg    = user_message
        self._turn_mem_snippet = None
        self._turn_rag_snippet = None
        self._sys_prompt_cache = None
        self.memory.reset_turn_cache()
        self.registry.clear_cache()
        self._task_last_test = ""

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

        # Actualizar permisos según elevated.
        if not self.capture_output and self.rt.elevated != self._last_elevated_applied:
            _def  = _DEFAULT_CONFIG["permissions"]
            _elev = self.rt.elevated
            self.permissions.set_elevated(_elev)
            if _elev == "ask":
                for _tool in list(self.permissions._perms):
                    _bare    = self.permissions._bare_name(_tool)
                    _lookup  = _bare if _bare else _tool
                    _default = _def.get(_lookup, "ask")
                    user_perm = (self.config.permissions.get(_lookup)
                                 or self.config.permissions.get(_tool))
                    if user_perm is not None and user_perm != _default:
                        continue
                    self.permissions._perms[_tool] = _default
            self._last_elevated_applied = _elev

        self._last_tool_calls = []
        self._pending_usage_line = ""
        self._auto_continue_count = 0
        self._turn_text_emitted = False
        self._sub_lines_shown  = 0

        import tools.hooks as _hooks_mod
        import tools.diff_renderer as _diff_mod
        _hooks_mod.set_hook_print_fn(self._print)
        _diff_mod.set_dprint_fn(self._print)
        self._empty_search_streak = 0
        self._empty_search_patterns = []
        self._failed_edit_streak = 0
        self._failed_edit_patterns = []
        self._turn_read_cache = {}
        self._turn_write_seen = {}
        self._turn_read_paths = set()
        self._turn_written_scripts = set()
        self._bash_block_counts = {}
        self._tool_phase = ""
        self._tool_current_file = ""
        _tool_progress.set_progress_callback(None)
        self._turn_block = []
        self._turn_block_has_header = False
        self._turn_expanded = False
        self._current_write_target = ""
        self._plan_tasks = []

    def _turn_start(self, user_message: str) -> tuple[list[str], float]:
        """Detección preflight, display inicial, emisión de thinking. Devuelve (output_parts, t_start)."""
        self._pending_tasks = self._detect_tasks(user_message)
        if self._pending_tasks:
            _n_tasks = len(self._pending_tasks)
            self._plan_tasks = [
                {"text": t, "status": "pending", "start_ts": 0.0, "end_ts": 0.0}
                for t in self._pending_tasks
            ]
            self._plan_tasks[0]["status"] = "active"
            self._plan_tasks[0]["start_ts"] = time.time()
            if not self.capture_output and not self.is_subagent:
                _uname       = getattr(self.ws, "user_name", "") if self.ws else ""
                _phrase_tmpl = random.choice(_TASK_PREFLIGHT_PHRASES)
                _phrase      = _phrase_tmpl.format(n=_n_tasks)
                if _uname and random.random() < 0.35:
                    _greet  = random.choice(_PREFLIGHT_USER_GREETINGS).format(user=_uname)
                    _phrase = f"{_greet} {_phrase[0].lower()}{_phrase[1:]}"
                _icon_col = _TASK_ICON_COLORS[int(time.time()) % len(_TASK_ICON_COLORS)]
                if not getattr(self, "_webui_queue", None):
                    self._print(
                        f"\n  [{_icon_col}]●[/{_icon_col}]  [cyan]{_phrase}[/cyan]"
                    )
                self._webui_emit({"type": "preflight", "label": _phrase})
        elif not self.capture_output and not self.is_subagent:
            _uname  = getattr(self.ws, "user_name", "") if self.ws else ""
            _pf     = _pick_preflight_phrase(user_message, _uname)
            _pf_cols = ["cyan", "magenta", "yellow", "blue", "green"]
            _pf_col  = _pf_cols[hash(user_message[:24]) % len(_pf_cols)]
            if not getattr(self, "_webui_queue", None):
                self._print(f"\n  [bold {_pf_col}]●[/bold {_pf_col}]  [dim]{_pf}[/dim]")
            self._webui_emit({"type": "preflight", "label": _pf})

        if not self.capture_output:
            self._webui_emit(self._webui_status())
            self._webui_emit({"type": "thinking"})

        t_run_start = time.time()
        self._task_start_time = t_run_start
        self._task_elapsed = 0.0
        return [], t_run_start

    def _turn_loop_guard(self) -> bool:
        """Comprueba señales de kill/steer al inicio de cada iteración. Devuelve True si hay que romper."""
        if self._kill_requested:
            self._kill_requested = False
            if any(c >= 3 for c in self._bash_block_counts.values()):
                _cat = next(k for k, v in self._bash_block_counts.items() if v >= 3)
                self._print(
                    f"\n  [bold red]⛔[/bold red]  Agente detenido — {self._bash_block_counts[_cat]} intentos "
                    f"de usar bash para '{_cat}' (operación permanentemente bloqueada).\n"
                    "  Usa la tool equivalente o escribe al usuario para pedir ayuda.\n"
                    "  Tip: [dim]/elevated on[/dim] amplía permisos si realmente necesitas bash."
                )
            else:
                self._print("\n  [yellow]↯[/yellow]  Turno interrumpido por /kill.")
            return True

        if self._ext_kill is not None and self._ext_kill.is_set():
            self._print("\n  [yellow]↯[/yellow]  Subagente detenido por el usuario.")
            return True

        if self._steer_queue is not None:
            try:
                import queue as _q
                new_instr = self._steer_queue.get_nowait()
                self._print(
                    f"\n  [bold cyan]⟳  Steer:[/bold cyan]  [dim]{new_instr}[/dim]\n"
                )
                self.context.add("user", f"[STEER] {new_instr}")
            except _q.Empty:
                pass

        return False

    def _turn_iter_prepare(self) -> tuple[list, list]:
        """Compacta contexto, emite avisos de contexto, refresca schemas y mensajes. Devuelve (messages, tools_cache)."""
        # Reconstruir cliente antes de cualquier llamada LLM del turno (compactación incluida).
        # Si el turno anterior cerró la conexión por error/timeout, _summarize_messages usaría
        # un cliente cerrado desde el hilo _bg. _stream_response también llama este método,
        # pero si hay compactación ocurre primero — el segundo check es siempre no-op.
        self._rebuild_client_if_needed()
        if self.context.should_compact():
            self._do_compact(with_summary=True)

        _think_active = getattr(self.rt, "think_level", "off") != "off"
        if _think_active and not self.capture_output and not self.is_subagent:
            _ctx_s = self.context.stats()
            _ctx_pct = _ctx_s["tokens_estimate"] / max(_ctx_s["max_tokens"], 1)
            if _ctx_pct > 0.65 and not getattr(self, "_webui_queue", None):
                self._print(
                    f"\n  [yellow]⚠[/yellow]  Contexto al "
                    f"{int(_ctx_pct*100)}% con thinking ON — riesgo de truncamiento XML. "
                    "Considera /think off o /compact.\n"
                )

        self._sep_label = ""
        _tools_cache = self._filtered_schemas(self._last_user_msg)
        messages = self.context.get_messages(system=self._system_prompt())
        self._trace_header(messages)
        return messages, _tools_cache

    def _turn_llm_call(
        self,
        messages: list,
        tools_cache: list,
        total_inp: int,
        total_out: int,
    ) -> tuple[str, list, int, int]:
        """Llama al LLM con retry automático y fallback por timeout. Devuelve (text, tool_calls, inp, out)."""
        _retry_max   = self.config.ollama_retry_count
        _retry_delay = self.config.ollama_retry_delay
        for _retry_n in range(_retry_max + 1):
            text, tool_calls, inp, out = self._stream_response(messages, tools_cache)
            if text != _TIMEOUT_SENTINEL or _retry_n >= _retry_max:
                break
            _retry_wait = _retry_delay * (2 ** _retry_n)
            if not getattr(self, "_webui_queue", None):
                self._print(
                    f"\n  [yellow]⟳[/yellow]  Timeout — reintentando "
                    f"({_retry_n + 1}/{_retry_max}) en {_retry_wait:.0f}s…"
                )
            self._webui_emit({"type": "preflight",
                              "label": f"Timeout — reintentando ({_retry_n+1}/{_retry_max})…"})
            time.sleep(_retry_wait)

        _sub_s = getattr(self, "_sub_stats_ref", None)
        if _sub_s is not None and out > 0:
            _sub_s.n_tokens_out += out
            try:
                _cs = self.context.stats()
                _sub_s.ctx_pct = int(_cs["tokens_estimate"] / max(_cs["max_tokens"], 1) * 100)
            except Exception as e:
                log.debug("subagent_stats_error", error=str(e))

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
                    text, tool_calls, inp, out = self._stream_response(messages, tools_cache)
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

        return text, tool_calls, inp, out

    def _turn_print_kill_stopped(self) -> None:
        """Imprime el mensaje de stop tras kill post-LLM."""
        if any(c >= 3 for c in self._bash_block_counts.values()):
            _cat = next(k for k, v in self._bash_block_counts.items() if v >= 3)
            self._print(
                f"\n  [bold red]⛔[/bold red]  Agente detenido — {self._bash_block_counts[_cat]} intentos "
                f"de usar bash para '{_cat}'.\n"
            )
        else:
            self._print("\n  [yellow]↯[/yellow]  Turno interrumpido por /kill.")

    def _turn_handle_empty(
        self,
        text: str,
        tool_calls: list,
        had_tools_prev: bool,
    ) -> Optional[str]:
        """Maneja respuesta vacía (sin texto ni tool_calls). Devuelve 'break', 'continue' o None."""
        if text.strip() or tool_calls:
            return None

        _max_ac = self.config.auto_continue_max
        _did_tools = bool(self._last_tool_calls)
        if self._all_plan_tasks_done():
            log.debug("auto_continue_skip_done", reason="all_plan_tasks_done")
            self._flush_turn_block()
            return "break"
        if _did_tools and _max_ac > 0 and self._auto_continue_count < _max_ac:
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
                    pass  # fall through → auto_continue
                else:
                    log.debug("auto_continue_skip_done",
                              reason="completion_report_in_last_message")
                    self._mark_all_plan_tasks_done()
                    self._flush_turn_block()
                    return "break"

            self._auto_continue_count += 1
            _n = self._auto_continue_count
            if self._plan_tasks and not self._all_plan_tasks_done():
                _tgt = min(_n, len(self._plan_tasks) - 1)
                _prev_tgt = next(
                    (i for i, t in enumerate(self._plan_tasks)
                     if t["status"] == "active"), -1
                )
                if _tgt > _prev_tgt:
                    self._set_plan_task_active(_tgt)
            if not self.capture_output and not had_tools_prev and not getattr(self, "_webui_queue", None):
                self._print(
                    f"\n  [bold yellow]↻[/bold yellow]  [yellow]Auto-continúa ({_n}/{_max_ac})…[/yellow]"
                )
            self._webui_emit({"type": "thinking"})
            log.debug("auto_continue", count=_n, max=_max_ac,
                      model=self._active_model(),
                      tools_done=len(self._last_tool_calls))
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
            return "continue"

        if not self.capture_output:
            self._print(
                "\n  [dim yellow]⚠  El modelo no ha producido respuesta. "
                "Si la tarea está incompleta, indícame qué falta.[/dim yellow]"
            )
        log.debug("empty_response", model=self._active_model(),
                  inp=self._turn_inp, out=self._turn_out,
                  iteration=len(self._last_tool_calls))
        self._flush_turn_block()
        return "break"

    def _turn_display_bullet(self, text: str, tool_calls: list) -> None:
        """Renderiza el ● con el texto del LLM y arranca el live block si hay tools."""
        from rich.markup import escape as _mesc
        import re as _re_bullet
        _ac = COLOR_PRESETS.get(self.rt.accent_color, COLOR_PRESETS["cyan"])[1]
        text_clean = text.lstrip()
        lines   = text_clean.split('\n', 1)
        first   = lines[0].rstrip()
        rest    = lines[1] if len(lines) > 1 else ""
        _s0 = first.lstrip()
        _is_md_block = bool(_s0 and (
            _s0[0] == '#' or
            _s0.startswith('```') or _s0.startswith('~~~') or
            _s0[0] in ('|', '>') or
            (len(_s0) >= 2 and _s0[0] in ('-', '+', '!') and _s0[1] in (' ', '\t')) or
            (len(_s0) >= 2 and _s0[0] == '*' and _s0[1] in (' ', '\t'))
        ))
        _plain_first = bool(first and not _is_md_block)
        if _plain_first:
            _first_clean = _re_bullet.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', first).strip()
            if _first_clean:
                first = _first_clean

        if self._start_live_block_cb and tool_calls:
            # ── Multi-párrafo: primer(os) párrafos → ● estático, último → ● live block ──
            # Cuando el LLM manda varias frases separadas por línea en blanco antes de
            # ejecutar tools, cada bloque de párrafos merece su propio ●.
            # El live block usa el ÚLTIMO párrafo para que el ⎿ quede debajo del contexto
            # inmediato (en vez de bajo la frase introductoria lejana).
            _mp_paras = [_p for _p in text_clean.split('\n\n') if _p.strip()]
            if len(_mp_paras) > 1:
                # Primer párrafo → ● estático (antes de activar el live block)
                _mp0 = _mp_paras[0]
                _mp0_sp = _mp0.split('\n', 1)
                _mp0_f  = _re_bullet.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1',
                                         _mp0_sp[0]).strip() or _mp0_sp[0].rstrip()
                _mp0_r  = _mp0_sp[1] if len(_mp0_sp) > 1 else ""
                console.print()
                console.print(f"  [bold {_ac}]●[/bold {_ac}] {_mesc(_mp0_f)}")
                if _mp0_r.strip():
                    console.print(Padding(Markdown(_mp0_r.lstrip('\n')), (0, 0, 0, 2)))
                # Párrafos intermedios → Markdown estático sin ●
                for _mp_mid in _mp_paras[1:-1]:
                    console.print()
                    console.print(Padding(Markdown(_mp_mid.strip()), (0, 0, 0, 2)))
                # Último párrafo → ● del live block
                _mp_last = _mp_paras[-1]
                _mp_last_sp = _mp_last.split('\n', 1)
                _mp_last_f  = _re_bullet.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1',
                                             _mp_last_sp[0]).strip() or _mp_last_sp[0].rstrip()
                _mp_last_r  = _mp_last_sp[1] if len(_mp_last_sp) > 1 else ""
                self._start_live_block_cb(_mesc(_mp_last_f or "…"))
                self._live_tool_count = 0
                if _mp_last_r.strip():
                    # El resto va a _live_block_body → se preserva para el flush
                    console.print(Padding(Markdown(_mp_last_r.lstrip('\n')), (0, 0, 0, 2)))
                return  # el bloque else al final no se ejecuta
            if _plain_first:
                try:
                    _cols = os.get_terminal_size().columns
                except OSError:
                    _cols = 120
                _max_hdr = max(60, _cols - 4)
                if len(first) <= _max_hdr:
                    _hdr        = first
                    _body_extra = ""
                else:
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
                _body_extra  = ""

            # ── Auto-split: planning text largo + write tools sin mención de fichero ──
            _write_tool_names = frozenset((
                "write_file", "edit_file", "edit_files",
                "regex_replace", "smart_replace", "bulk_replace", "patch_apply",
            ))
            _write_sfxs = ("_edit_file", "_edit_files", "_write_file",
                           "_smart_replace", "_regex_replace", "_bulk_replace",
                           "_patch_apply")
            _write_files_auto: list[str] = []
            for _wtc in tool_calls:
                try:
                    _wfn = getattr(getattr(_wtc, "function", None), "name", "") or ""
                    _wfn = _TOOL_ALIASES.get(_wfn, _wfn)
                    _wfa = getattr(getattr(_wtc, "function", None), "arguments", {}) or {}
                    if isinstance(_wfa, str):
                        try:
                            _wfa = json.loads(_wfa)
                        except Exception:
                            _wfa = {}
                    if _wfn in _write_tool_names or any(_wfn.endswith(s) for s in _write_sfxs):
                        if _wfn in ("edit_files",) or _wfn.endswith("_edit_files"):
                            for _we in (_wfa.get("edits") or []):
                                _wp = (_we.get("path", "") if isinstance(_we, dict) else "")
                                if _wp:
                                    _wb = _wp.rsplit("/", 1)[-1]
                                    if _wb and _wb not in _write_files_auto:
                                        _write_files_auto.append(_wb)
                        else:
                            _wp = _wfa.get("path", "")
                            if _wp:
                                _wb = _wp.rsplit("/", 1)[-1]
                                if _wb and _wb not in _write_files_auto:
                                    _write_files_auto.append(_wb)
                except Exception as e:
                    log.debug("bullet_args_parse_error", error=str(e))
            _first_lower = first.lower()
            _files_mentioned = any(_f.lower() in _first_lower for _f in _write_files_auto)
            _should_split = (
                _plain_first and _write_files_auto
                and len(first) > 60
                and not _files_mentioned
            )
            if _should_split:
                console.print()
                console.print(f"  [bold {_ac}]●[/bold {_ac}] {_mesc(first)}")
                if rest.strip():
                    console.print(Padding(Markdown(rest.lstrip('\n')), (0, 0, 0, 2)))
                if len(_write_files_auto) == 1:
                    _wh = f"Updating {_write_files_auto[0]}:"
                elif len(_write_files_auto) == 2:
                    _wh = f"Updating {_write_files_auto[0]}, {_write_files_auto[1]}:"
                else:
                    _wh = f"Updating {_write_files_auto[0]} (+{len(_write_files_auto)-1} more):"
                self._start_live_block_cb(_wh)
                self._live_tool_count = 0
            else:
                self._start_live_block_cb(_bullet_text)
                self._live_tool_count = 0
                _body = (_body_extra + "\n" + rest).lstrip('\n') if _body_extra else rest
                if _plain_first and _body.strip():
                    console.print(Padding(Markdown(_body.lstrip('\n')), (0, 0, 0, 2)))
                elif not _plain_first:
                    console.print(Padding(Markdown(text_clean), (0, 0, 0, 2)))
        else:
            # REPL o respuesta sin tools: ● estático normal
            console.print()
            if _plain_first:
                console.print(f"[bold {_ac}]●[/bold {_ac}] {_mesc(first)}")
                if rest.strip():
                    console.print(Padding(Markdown(rest.lstrip('\n')), (0, 0, 0, 2)))
            else:
                console.print(f"[bold {_ac}]●[/bold {_ac}]")
                console.print(Padding(Markdown(text_clean), (0, 0, 0, 2)))

    def _turn_no_tools(self, text: str) -> str:
        """Decide si auto-continuar o parar cuando el LLM no generó tool_calls. Devuelve 'break' o 'continue'."""
        if self._all_plan_tasks_done():
            log.debug("auto_continue_skip_done", reason="all_plan_tasks_done_no_tools")
            self._flush_turn_block()
            return "break"

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
            return "break"

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
                if _n_ac == 1:
                    from rich.markup import escape as _mesc
                    _icon_c = _TASK_ICON_COLORS[int(time.time()) % len(_TASK_ICON_COLORS)]
                    if not getattr(self, "_webui_queue", None):
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
                        self._webui_emit({"type": "plan",
                                          "tasks": _plan_steps[:_MAX_PLAN_TASKS],
                                          "n": len(_plan_steps), "summary": "",
                                          "extra": max(0, len(_plan_steps) - _MAX_PLAN_TASKS)})
                elif not getattr(self, "_webui_queue", None):
                    self._print(
                        f"\n  [bold yellow]↻[/bold yellow]  [yellow]Continuando "
                        f"({_n_ac}/{_max_ac})…[/yellow]"
                    )
                if _plan_steps and _n_ac == 1:
                    self._plan_tasks = [
                        {"text": t, "status": "pending", "start_ts": 0.0, "end_ts": 0.0}
                        for t in _plan_steps
                    ]
                    self._plan_tasks[0]["status"] = "active"
                    self._plan_tasks[0]["start_ts"] = time.time()
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
                self._webui_emit({"type": "thinking"})
                return "continue"

        if (self._plan_tasks and not self._all_plan_tasks_done()
                and _max_ac > 0 and self._auto_continue_count < _max_ac
                and not self.capture_output):
            _resume_idx = next(
                (i for i, t in enumerate(self._plan_tasks)
                 if t["status"] in ("active", "pending")),
                -1,
            )
            if _resume_idx >= 0:
                if text and self._is_completion_report(text):
                    self._mark_all_plan_tasks_done()
                    self._flush_turn_block()
                    return "break"
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
                if not getattr(self, "_webui_queue", None):
                    self._print(
                        f"\n  [bold yellow]↻[/bold yellow]  "
                        f"[yellow]Tarea {_rn} pendiente — retomando "
                        f"({_n}/{_max_ac})…[/yellow]"
                    )
                log.debug("auto_continue_pending_task",
                          task_idx=_resume_idx, count=_n, max=_max_ac)
                self.context.add("user", _resume_msg)
                return "continue"

        return "break"

    def _turn_dispatch_tools(
        self,
        tool_calls: list,
        total_inp: int,
        total_out: int,
    ) -> tuple[list, dict, dict, set, bool]:
        """Parsea, verifica permisos y ejecuta tool calls. Devuelve (parsed_calls, allowed_map, results_map, pre_shown_idxs, safe_parallel)."""
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

        _block_mode = len(parsed_calls) > 1
        allowed_map: dict[int, bool] = {}
        for idx, (_tc, name, args) in enumerate(parsed_calls):
            description = f"{name}({json.dumps(args, ensure_ascii=False)[:80]})"
            allowed_map[idx] = self.permissions.check(name, description)

        _safe_parallel = (
            len(parsed_calls) > 1
            and not any(n == "bash" for _, n, _ in parsed_calls)
            and not self.capture_output
        )

        results_map: dict[int, str] = {}
        _pre_shown_idxs: set[int] = set()

        if _safe_parallel:
            names_label = " + ".join(n for _, n, _ in parsed_calls)
            self._sep_label = f"⚙ {names_label}…"

            if getattr(self, "_update_live_bullet_cb", None):
                _SEARCH_N = frozenset(("grep_code", "grep_file", "multi_grep",
                                       "code_search", "symbol_lookup"))
                _READ_N   = frozenset(("read_file", "read_files", "read_sections", "ls_dir"))
                _FIND_N   = frozenset(("find_file", "find_files", "find_dir", "file_stat"))
                _pn_list  = [n for _, n, _ in parsed_calls]
                _ns = sum(1 for n in _pn_list if n in _SEARCH_N)
                _nr = sum(1 for n in _pn_list if n in _READ_N)
                _nf = sum(1 for n in _pn_list if n in _FIND_N)
                _no = len(_pn_list) - _ns - _nr - _nf
                _pp = []
                if _ns: _pp.append(f"Searching for {_ns} pattern{'s' if _ns != 1 else ''}")
                if _nr: _pp.append(f"reading {_nr} file{'s' if _nr != 1 else ''}")
                if _nf: _pp.append(f"finding {_nf} path{'s' if _nf != 1 else ''}")
                if _no: _pp.append(f"running {_no} tool{'s' if _no != 1 else ''}")
                if _pp:
                    self._update_live_bullet_cb(", ".join(_pp) + " (ctrl+o to expand)")

            if getattr(self, "_webui_queue", None) is not None:
                for _pidx, (_, _pn, _pa) in enumerate(parsed_calls):
                    if allowed_map[_pidx]:
                        _pd = self._TOOL_DISPLAY_NAMES.get(_pn, _pn)
                        _pc = self._strip_rich(self._call_context(_pn, _pa)).strip()
                        self._webui_emit({"type": "tool_start", "tool": _pd,
                                          "raw": _pn, "context": _pc})

            _pool_done  = threading.Event()
            _pool_start = time.time()

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
                        _act2  = next(
                            (t["text"] for t in getattr(self, "_plan_tasks", [])
                             if t["status"] == "active"), ""
                        )
                        _thresh2p = int(self.context.compact_threshold * 100)
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
                            while True:
                                try:
                                    results_map[idx] = future.result(timeout=0.25)
                                    break
                                except TimeoutError:
                                    if self._kill_requested:
                                        future.cancel()
                                        results_map[idx] = "⛔ Cancelado por kill."
                                        break
                        except Exception as exc:
                            results_map[idx] = f"Error: {exc}"

            _pool_done.set()
            _spin_t.join(timeout=1.0)

        else:
            # ── Ejecución secuencial con spinner animado ────────────────────
            for idx, (_tc, name, args) in enumerate(parsed_calls):
                if self._kill_requested:
                    results_map[idx] = "⛔ Operación cancelada — agente detenido por bloqueo bash."
                    continue
                self._sep_label = f"⚙ {name}…"

                if self._status_cb and allowed_map[idx]:
                    self._show_tool_running_header(name, args)
                    _pre_shown_idxs.add(idx)

                    _seq_done  = threading.Event()
                    _seq_start = time.time()
                    _is_subagent_tool = (name == "spawn_subagent")
                    _seq_color_cycle  = list(_SUBAGENT_COLORS) if _is_subagent_tool else ["cyan"]
                    _seq_poll = _SUBAGENT_SPINNER_POLL if _is_subagent_tool else _POLL_INTERVAL

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
                            _phase = self._tool_phase
                            _cur_f = self._tool_current_file
                            if _phase:
                                _label = _phase
                                _icon  = "⬡"
                            elif _cur_f:
                                _sf2   = _cur_f.rsplit("/", 1)[-1][:30]
                                _label = f"{_name}…  ⎿ {_sf2}  {_tp2}"
                                _icon  = frame2
                            else:
                                _label = f"{_name}…  {_tp2}"
                                _icon  = frame2
                            _thresh2 = int(self.context.compact_threshold * 100)
                            _cbar2   = _sfmt(_bar_style(cpct2, _thresh2), pbar2)
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
                    ctx_s      = self.context.stats()
                    cpct       = int(ctx_s["tokens_estimate"] / max(ctx_s["max_tokens"], 1) * 100)
                    plain_bar  = _ctx_bar(ctx_s["tokens_estimate"], ctx_s["max_tokens"], 10, plain=True)
                    tok_part   = (f"{_fmt_tokens(total_inp)}↑ {_fmt_tokens(total_out)}↓  ·  "
                                  if (total_inp or total_out) else "")
                    _thr_d = int(self.context.compact_threshold * 100)
                    _cb_d  = _sfmt(_bar_style(cpct, _thr_d), plain_bar)
                    self._status_cb(f"⚙  {name}…\n↳  {tok_part}ctx: {_cb_d} {cpct}%")
                    results_map[idx] = "Operación denegada."
                else:
                    if allowed_map[idx]:
                        if self.is_subagent:
                            self._show_tool_running_header(name, args)
                            results_map[idx] = self._execute_tool(name, args)
                        else:
                            results_map[idx] = self._run_animated_header(name, args)
                        _pre_shown_idxs.add(idx)
                    else:
                        results_map[idx] = "Operación denegada."

        return parsed_calls, allowed_map, results_map, _pre_shown_idxs, _safe_parallel

    def _turn_log_results(
        self,
        parsed_calls: list,
        allowed_map: dict,
        results_map: dict,
        pre_shown_idxs: set,
        safe_parallel: bool,
    ) -> None:
        """Registra resultados, actualiza contexto, checkpoints y auto-avanza el plan."""
        _READ_GROUP = frozenset((
            "read_file", "read_files", "grep_code", "grep_file",
            "find_file", "find_files", "find_dir", "ls_dir", "file_stat",
            "symbol_lookup", "multi_grep", "code_compare",
        ))
        _WRITE_GROUP = frozenset((
            "edit_file", "edit_files", "write_file", "regex_replace",
            "bulk_replace", "patch_apply",
        ))
        _block_mode = len(parsed_calls) > 1
        _batch_names = [n for _, n, _ in parsed_calls]
        _in_read_batch  = (safe_parallel and not self.capture_output
                           and all(n in _READ_GROUP for n in _batch_names)
                           and len(parsed_calls) > 1)
        _in_write_batch = (safe_parallel and not self.capture_output
                           and all(n in _WRITE_GROUP for n in _batch_names)
                           and len(parsed_calls) > 1)
        _in_batch = _in_read_batch or _in_write_batch

        # En TUI mode el resumen agrupado se genera en _flush_turn_block
        if safe_parallel and not self.capture_output and self._status_cb is None:
            _all_reads  = all(n in _READ_GROUP for n in _batch_names)
            _all_writes = all(n in _WRITE_GROUP for n in _batch_names)
            _n = len(_batch_names)
            if _all_reads and _n > 1:
                self._print(
                    f"  [bold green]●[/bold green] [bold]Reading {_n} files…[/bold]"
                )
            elif _all_writes and _n > 1:
                self._print(
                    f"  [bold green]●[/bold green] [bold]Updating {_n} files…[/bold]"
                )

        for idx, (_tc, name, args) in enumerate(parsed_calls):
            result  = results_map[idx]
            allowed = allowed_map[idx]
            self.session.log_tool_call(name, args, result)
            self.chatlog.log_tool_call(name, args, str(result))
            log.debug("tool_call", tool=name, allowed=allowed,
                      args=json.dumps(args, ensure_ascii=False)[:120])
            _is_pre_shown = idx in pre_shown_idxs if not safe_parallel else False
            self._show_tool_block(name, args, str(result), allowed,
                                  block_mode=_block_mode,
                                  suppress_header=_in_batch,
                                  pre_shown=_is_pre_shown,
                                  batch_idx=idx if _in_batch else -1)
            if self.plugins and allowed:
                self.plugins.fire("on_tool_result", name, args, str(result))
            args_str = json.dumps(args, ensure_ascii=False)
            self._last_tool_calls.append((name, args_str, str(result)))
            if allowed:
                if _is_modify_tool(name):
                    _wp = str(args.get("path") or args.get("file_path", ""))
                    if _wp:
                        self._session_reads.append((_wp, None, True))
                    for _wed in args.get("edits", []):
                        if isinstance(_wed, dict) and _wed.get("path"):
                            self._session_reads.append((str(_wed["path"]), None, True))
                elif name in ("run_tests", "test_file"):
                    self._task_last_test = str(result)[:400]
            result_for_ctx = self._postprocess_tool_result(name, args, str(result))
            result_for_ctx = self._truncate_tool_result(result_for_ctx)
            tool_call_id = getattr(_tc, "id", None) or name
            self.context.add_tool_result(tool_call_id, name, result_for_ctx)

        # Truncación de batch en REPL mode (… +N tool uses)
        if (_in_batch and len(parsed_calls) > 3
                and not self.capture_output
                and getattr(self, "_webui_queue", None) is None
                and self._status_cb is None):
            _n_hidden = len(parsed_calls) - 3
            self._print(
                f"     [dim]… +{_n_hidden} tool use{'s' if _n_hidden != 1 else ''}"
                f" (ctrl+o to expand)[/dim]"
            )

        # Auto-advance plan tras spawn_subagent/explore exitosos sin task_done() explícito
        _SPAWN_NAMES = frozenset({"spawn_subagent", "explore"})
        _spawn_ok = [
            (i, n) for i, (_, n, _) in enumerate(parsed_calls)
            if n in _SPAWN_NAMES
            and allowed_map.get(i, False)
            and not str(results_map.get(i, "")).startswith("Error")
            and not str(results_map.get(i, "")).startswith("⛔")
        ]
        _has_explicit_task_done = any(n == "task_done" for _, n, _ in parsed_calls)
        if (_spawn_ok
                and not _has_explicit_task_done
                and self._plan_tasks
                and not self._all_plan_tasks_done()
                and not self.capture_output):
            self._execute_task_done("")

    def _turn_finish(
        self,
        full_output_parts: list[str],
        total_inp: int,
        total_out: int,
        t_run_start: float,
    ) -> Optional[str]:
        """Teardown del turno: flush, auto-memoria, status final, usage y limpieza."""
        self._flush_turn_block()
        self._auto_save_task_memory(full_output_parts)

        if self._status_cb:
            total_elapsed = time.time() - t_run_start
            done_word  = random.choice(_DONE_WORDS)
            ctx_s      = self.context.stats()
            cpct       = int(ctx_s["tokens_estimate"] / max(ctx_s["max_tokens"], 1) * 100)
            plain_bar  = _ctx_bar(ctx_s["tokens_estimate"], ctx_s["max_tokens"], 10, plain=True)
            thresh_pct = int(self.context.compact_threshold * 100)
            tok_part   = (f"{_fmt_tokens(total_inp)}↑ {_fmt_tokens(total_out)}↓  ·  "
                          if (total_inp or total_out) else "")
            line1      = f"⚙  {done_word} durante {total_elapsed:.1f}s  ✓"
            _bstyle_f  = _bar_style(cpct, thresh_pct)
            _chint_f   = _hint_styled(cpct, thresh_pct)
            line2      = f"↳  {tok_part}ctx: {_sfmt(_bstyle_f, plain_bar)} {cpct}%{_chint_f}"
            self._status_cb(f"{line1}\n{line2}")
            self._sep_label = ""

        _now_done = time.time()
        for _pt in self._plan_tasks:
            if _pt["status"] in ("active", "pending"):
                _pt["status"] = "done"
                if not _pt["end_ts"]:
                    _pt["end_ts"] = _now_done

        self._task_elapsed = time.time() - self._task_start_time
        self._task_start_time = None

        self._show_usage(total_inp, total_out)

        import tools.hooks as _hooks_mod_end
        import tools.diff_renderer as _diff_mod_end
        _hooks_mod_end.set_hook_print_fn(None)
        _diff_mod_end.set_dprint_fn(None)

        self._last_response = "\n".join(full_output_parts)
        log.debug("assistant_reply", chars=len(self._last_response))
        if self.capture_output:
            return self._last_response
        return None

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
        if self._compact_running.is_set():
            self._compact_running.wait(timeout=30.0)

        self._turn_reset_state(user_message, images)
        full_output_parts, t_run_start = self._turn_start(user_message)

        total_inp = total_out = 0
        _had_tools_prev    = False
        _last_tool_call_count = 0

        while True:
            if self._turn_loop_guard():
                break

            _new_count = len(self._last_tool_calls)
            _had_tools_prev       = _new_count > _last_tool_call_count
            _last_tool_call_count = _new_count
            self._subagent_color_idx += 1

            messages, _tools_cache = self._turn_iter_prepare()

            text, tool_calls, inp, out = self._turn_llm_call(
                messages, _tools_cache, total_inp, total_out)

            if self._kill_requested:
                self._kill_requested = False
                self._turn_print_kill_stopped()
                break

            total_inp += inp
            total_out += out
            self._turn_inp = total_inp
            self._turn_out = total_out
            if inp or out:
                self.session.log_usage(inp, out)

            ctrl = self._turn_handle_empty(text, tool_calls, _had_tools_prev)
            if ctrl == "break":
                break
            if ctrl == "continue":
                continue

            assistant_msg: dict = {"role": "assistant", "content": text}
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    tc.model_dump(exclude_none=True) if hasattr(tc, "model_dump") else tc
                    for tc in tool_calls
                ]
            self.context.messages.append(assistant_msg)
            self.context._invalidate_token_cache()

            if text:
                self._advance_plan_task(text)
                self._turn_text_emitted = True
                full_output_parts.append(text)
                self.session.log_message("assistant", text)
                self.chatlog.log_assistant(text)
                self._flush_turn_block()
                if not self.capture_output:
                    self._turn_display_bullet(text, tool_calls)

            if not tool_calls:
                ctrl = self._turn_no_tools(text)
                if ctrl == "break":
                    break
                if ctrl == "continue":
                    continue
                break

            parsed, allowed_map, results_map, pre_shown, safe_parallel = \
                self._turn_dispatch_tools(tool_calls, total_inp, total_out)
            self._turn_log_results(parsed, allowed_map, results_map, pre_shown, safe_parallel)

        return self._turn_finish(full_output_parts, total_inp, total_out, t_run_start)
