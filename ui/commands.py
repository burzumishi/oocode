"""Handlers de /slash commands."""
import importlib.metadata
import json
import os
from pathlib import Path
from datetime import datetime
from rich.prompt import Prompt
from rich.markdown import Markdown
from rich.padding import Padding
from rich.table import Table
from rich import box
import requests

import agent.logger as log
from agent.runtime import (
    RuntimeSettings, THINK_LEVELS, ELEVATED_MODES, USAGE_MODES,
    COLOR_PRESETS, BUILTIN_THEMES, all_themes, save_user_theme,
    delete_user_theme, random_color,
)
from ui.renderer import (
    print_help, print_config, print_model_selector,
    print_agents, print_spawn_header, print_spawn_footer,
    print_usage, print_sessions,
    print_status, print_gateway_status, print_commands, print_runtime,
    print_ctx_status, print_mem_list, print_mem_search,
    print_branches, print_tasks, print_schedule,
    print_skills, print_plugins, print_config_full,
    print_splash, _random_tip,
    print_keybindings,
)

from ui.console import console

# Referencia al agent_loop activo — la fija handle_slash() en cada llamada.
# La usan _tui_ask() y otras funciones para acceder a request_input del TUI.
_agent_loop_ref = None


def _tui_ask(prompt: str, default: str = "",
             choices: list[str] | None = None,
             secret: bool = False) -> str:
    """Pide input al usuario usando el TUI (request_input) si está disponible.
    En REPL mode o si el TUI no está listo, usa Prompt.ask() como fallback.
    """
    al = _agent_loop_ref
    if al is not None:
        fn = getattr(al, "_request_input", None)
        if callable(fn):
            hint = ""
            if choices:
                hint += f"  ({'/'.join(choices)})"
            if default:
                hint += f"  [{default}]"
            result = fn(f"{prompt}{hint}", secret).strip()
            if not result:
                return default
            if choices:
                if result in choices:
                    return result
                rl = result.lower()
                for c in choices:
                    if c.lower() == rl:
                        return c
                return default
            return result
    # Fallback: Prompt.ask() estándar para REPL mode
    kwargs: dict = {"default": default}
    if choices:
        kwargs["choices"] = choices
    return Prompt.ask(prompt, **kwargs)


CTX_MODES = ("mini", "full")

SLASH_HELP: dict[str, dict[str, str]] = {
    "Sesión y contexto": {
        "/new  /reset":         "Nueva sesión (guarda la actual, limpia contexto)",
        "/session [id]":        "Sesión activa o restaurar por ID",
        "/sessions":            "Historial de sesiones del agente",
        "/context":             "Estado detallado del contexto (tokens, resumen, modo)",
        "/ctx [mini|full]":     "Modo de contexto del workspace (mini: compacto, full: todos los ficheros sin límite)",
        "/plan [on|off]":       "Plan-mode: el agente pide tu aprobación antes de ejecutar cada plan (Aprobar/Editar/Cancelar)",
        "/compact [fast]":      "Compacta contexto con resumen LLM (fast: sin resumen)",
        "/suggest [on|off]":    "Sugerencia contextual del siguiente mensaje en el prompt (franja idle)",
        "/resume":              "Resume contexto actual y lo limpia (mantiene resumen)",
        "/checkpoint":          "Guarda checkpoint manual del contexto en memoria diaria",
        "/branch [subcmd]":     "Ramas de conversación: save|load|list|rm <nombre>",
        "/usage [modo]":        "Uso de tokens  (off | tokens | full)",
        "/clear":               "Limpia historial sin nueva sesión",
        "/copy [n]":            "Copia la última respuesta al portapapeles",
        "/btw <pregunta>":      "Pregunta rápida fuera del contexto principal",
        "/abort":               "Interrumpe la operación actual (Ctrl+C)",
    },
    "Tareas y planificación": {
        "/tasks [subcmd]":      "Gestión de tareas: add|done|wip|rm|clear <id/título>",
        "/schedule [subcmd]":   "Jobs periódicos: add <min> <cmd>|run|toggle|rm <id>",
        "/kill [all]":          "Interrumpe el turno actual del agente; /kill all mata todos los jobs/tareas activos",
    },
    "Memoria": {
        "/mem [list]":          "Lista todas las memorias guardadas",
        "/mem search <query>":  "Búsqueda semántica en memorias (requiere embeddings)",
        "/mem show <nombre>":   "Muestra el contenido de una memoria",
        "/mem save <nombre>":   "Guarda texto del próximo mensaje como memoria",
        "/mem rm <nombre>":     "Elimina una memoria permanentemente",
        "/mem rebuild":         "Recalcula embeddings de todas las memorias",
        "/mem clear":           "Elimina TODAS las memorias (pide confirmación)",
    },
    "Extensiones": {
        "/skills [subcmd]":     "Skills personalizados: list|create|enable|disable <nombre>",
        "/plugins [subcmd]":    "Plugins con hooks: list|create|enable|disable|reload <nombre>",
        "/add-dir [ruta]":      "Añade directorio adicional al contexto de trabajo",
    },
    "Modos de respuesta": {
        "/think <nivel>":       "Profundidad de razonamiento  (off|minimal|low|medium|high)",
        "/reasoning <on|off>":  "Cadena de razonamiento explícita",
        "/fast <on|off>":       "Modo rápido: cambia a modelo ligero",
        "/verbose <on|off>":    "Muestra args y resultados completos de tools",
        "/trace <on|off>":      "Muestra info del system prompt en cada turno",
        "/color [nombre]":      "Esquema de color: aleatorio sin args, o save|list|rm|<nombre>",
    },
    "Permisos y activación": {
        "/elevated <modo>":     "Permisos: off(solo lectura) | ask(normal) | on(elevado) | full(sin restricciones)",
        "/elev <modo>":         "Alias de /elevated",
        "/activation <modo>":   "Cuándo responde el agente  (always|mention)",
    },
    "Agentes y modelos": {
        "/agents":                          "Lista agentes definidos en oocode.json",
        "/agent <id>":                      "Muestra info del agente especificado (workspace, modelo)",
        "/agent new <id> [nombre] [desc]":  "Crea nuevo agente con workspace propio (usa LLM para personalizar)",
        "/agent reset <id> [descripción]":  "Resetea workspace del agente a plantillas originales",
        "/switch <id>":                     "Cambia el agente activo en runtime (recarga workspace y sesión)",
        "/agent team":                      "Lista equipos de agentes (AgentTeam) persistidos",
        "/agent team <id>":                 "Estado detallado de un equipo",
        "/agent team create <id> <lead> <members>": "Crea equipo: lead=coding members=coding,reasoning",
        "/agent team add <id> <tarea> <agente>":    "Añade subtask a un equipo existente",
        "/agent team done <id> <stid> [resultado]": "Marca subtask como completada",
        "/agent team run <id>":             "Ejecuta todas las subtasks pendientes del equipo",
        "/agent team delete <id>":          "Elimina un equipo del disco",
        "/model [nombre]":                  "Muestra o cambia modelo principal (auto-detecta config)",
        "/model timeout [segundos]":        "Configura el timeout del modelo activo en oocode.json",
        "/model fallback [nombre]":         "Configura modelo de reserva por timeout (auto-detecta config)",
        "/models":                          "Lista y selecciona modelos del servidor",
        "/workspace [ruta]":                "Muestra o cambia workspace (se guarda)",
"/webserver":                      "Levanta el WebUI en puerto 4000 (ver /help para comandos)",
"/webserver status":               "Estado del WebUI",
"/webserver start":                "Levanta el WebUI en puerto 4000",
"/webserver stop":                 "Para el WebUI",
"/webserver restart":              "Reinicia el WebUI",
        "/subagents":                       "Sin args: lista subagentes activos y recientes",
        "/subagents spawn <id> <tarea>":    "Lanza subagente con tarea específica",
        "/subagents status [id]":           "Estado detallado de un subagente (o todos)",
        "/steer <tarea>":                   "Actualiza la tarea/contexto del agente principal en curso",
        "/subagents steer <id> <instr>":    "Inyecta nueva instrucción a un subagente en curso",
        "/subagents kill <id|all>":         "Detiene un subagente (o todos)",
        "/subagents output <id>":           "Muestra resultado completo de un subagente",
        "/spawn <id> <tarea>":              "Alias de /subagents spawn",
        "/crestodian [req]":                "Gestión del workspace (editar ficheros de identidad)",
    },
    "Hooks": {
        "/hooks":                   "Lista hooks PreToolUse/PostToolUse registrados",
        "/hooks clear":             "Elimina todos los hooks registrados",
        "/hooks builtin <nombre>":  "Activa/desactiva un hook built-in (diff_after_write, lint_after_write, autoformat_after_write, backup_before_write…)",
    },
    "Herramientas de código": {
        "/diff":                    "Historial de diffs visuales de la sesión",
        "/diff <fichero>":          "Muestra el diff completo de un fichero concreto",
        "/symbols":                 "Genera o actualiza el índice de símbolos ctags del workspace",
        "/symbols <fichero>":       "Lista los símbolos definidos en un fichero",
        "/symbols <nombre>":        "Busca un símbolo por nombre en el proyecto",
        "/lint":                    "Lanza linters sobre el workspace",
        "/lint <ruta>":             "Lanza linters sobre un fichero o directorio",
    },
    "Integraciones": {
        "/lsp":                          "Estado del servidor LSP: clientes activos y disponibles",
        "/lsp start <ext|nombre>":      "Arranca el servidor LSP para esa extensión o servidor",
        "/lsp stop <ext|nombre>":       "Para el servidor LSP de la extensión o servidor indicado",
        "/lsp restart <ext|nombre>":    "Reinicia el servidor LSP de la extensión o servidor",
        "/lsp enable <nombre>":         "Habilita el servidor en autoStart (se inicia con OOCode)",
        "/lsp disable <nombre>":        "Deshabilita el servidor del autoStart",
        "/mcp":                         "Estado del pool MCP: servidores y tools registradas",
        "/mcp catalog [query]":         "Lista servidores MCP del catálogo (filtro opcional)",
        "/mcp install <id> [args...]":  "Añade servidor del catálogo a oocode.json y lo arranca",
        "/mcp add <name> <cmd...>":     "Añade servidor MCP personalizado (cmd libre)",
        "/mcp remove <nombre>":         "Elimina servidor de oocode.json",
        "/mcp enable/disable <nombre>": "Activa/desactiva servidor en oocode.json",
        "/mcp check <id>":              "Verifica prerequisitos del servidor en el catálogo",
        "/mcp reload <nombre>":         "Recarga la lista de tools de un servidor MCP",
        "/mcp restart <nombre>":        "Para y reinicia un servidor MCP",
        "/rag":                 "Estado del índice RAG del workspace",
        "/rag reindex":         "Fuerza re-indexación completa del workspace",
        "/rag enable":          "Activa la inyección RAG en el system prompt",
        "/rag disable":         "Desactiva la inyección RAG",
        "/snapshots":           "Lista snapshots de sesión guardados",
        "/snapshots show <n>":  "Muestra el contenido del snapshot N",
        "/snapshots clear":     "Elimina todos los snapshots del agente activo",
    },
    "Sistema": {
        "/status":              "Estado general: agente, modelo, contexto, flags (incluye fallback)",
        "/gateway-status":      "Estado del servidor Ollama y modelos disponibles",
        "/config [edit]":       "Configuración completa; /config edit para panel interactivo",
        "/keybindings [subcmd]":"Keybindings: list | set <acción> <key> | reset [acción]",
        "/doctor":              "Diagnóstico: conectividad, modelos, plugins, dependencias",
        "/logs [n]":            "Últimas n líneas del fichero de log (defecto 40)",
        "/chatlog":             "Estado del registro de conversación (chat.log)",
        "/chatlog enable":      "Activa el registro de conversaciones",
        "/chatlog disable":     "Desactiva el registro de conversaciones",
        "/chatlog tail [n]":    "Últimas n líneas del chat.log (defecto 50)",
        "/chatlog clear":       "Vacía el chat.log",
        "/commands":            "Lista compacta de todos los comandos",
        "/init [ruta]":         "Genera OOCODE.md en el workspace o directorio indicado",
        "/review":              "Revisión de los cambios git actuales",
        "/splash":              "Muestra el logo animado y un tip aleatorio",
        "/tip":                 "Muestra un tip aleatorio de uso de OOCode",
        "/help":                "Esta ayuda",
        "/exit  /quit  /q":     "Sale de OOCode (guarda la sesión)",
    },
}


def handle_slash(command: str, agent_loop, config) -> bool:
    """Devuelve True para continuar el REPL, False para salir."""
    global _agent_loop_ref
    _agent_loop_ref = agent_loop  # permite que _tui_ask() use request_input del TUI
    parts = command.strip().split(maxsplit=1)
    cmd   = parts[0].lower()
    args  = parts[1].strip() if len(parts) > 1 else ""
    rt    = agent_loop.rt

    # ── Salida ───────────────────────────────────────────────────────────────
    if cmd in ("/exit", "/quit", "/q"):
        agent_loop.session.end()
        console.print("\n  [dim]Sesión guardada. Hasta pronto.[/dim]\n")
        return False

    # ── Sesión y contexto ─────────────────────────────────────────────────────
    elif cmd in ("/new", "/reset"):
        _cmd_new(agent_loop)
    elif cmd == "/session":
        _cmd_session(args, agent_loop)
    elif cmd == "/sessions":
        _cmd_sessions(agent_loop)
    elif cmd == "/context":
        print_ctx_status(agent_loop.context, config, rt)
    elif cmd == "/ctx":
        _cmd_ctx(args, rt)
    elif cmd == "/plan":
        _cmd_plan(args, rt)
    elif cmd == "/compact":
        _cmd_compact(args, agent_loop)
    elif cmd == "/suggest":
        _cmd_suggest(args, agent_loop, config)
    elif cmd == "/resume":
        _cmd_resume(agent_loop)
    elif cmd == "/checkpoint":
        _cmd_checkpoint(agent_loop)
    elif cmd == "/branch":
        _cmd_branch(args, agent_loop)
    elif cmd == "/usage":
        _cmd_usage(args, agent_loop, rt)
    elif cmd == "/clear":
        agent_loop.context.clear()
        console.print("  [green]✓[/green]  Historial borrado  [dim](summary conservado)[/dim]")
    elif cmd == "/copy":
        _cmd_copy(args, agent_loop)
    elif cmd == "/btw":
        _cmd_btw(args, agent_loop)
    elif cmd == "/abort":
        console.print("  [yellow]↯[/yellow]  Usa [bold]Ctrl+C[/bold] para interrumpir una operación en curso.")

    # ── Tareas y planificación ────────────────────────────────────────────────
    elif cmd == "/tasks":
        _cmd_tasks(args, agent_loop)
    elif cmd == "/schedule":
        _cmd_schedule(args, agent_loop, config)
    elif cmd == "/kill":
        _cmd_kill(args, agent_loop)

    # ── Memoria ───────────────────────────────────────────────────────────────
    elif cmd in ("/mem", "/memory"):
        _cmd_mem(args, agent_loop)

    # ── Extensiones ───────────────────────────────────────────────────────────
    elif cmd == "/skills":
        _cmd_skills(args, agent_loop, config)
    elif cmd == "/plugins":
        _cmd_plugins(args, agent_loop, config)
    elif cmd in ("/add-dir", "/adddir"):
        _cmd_add_dir(args, rt)

    # ── Modos de respuesta ────────────────────────────────────────────────────
    elif cmd == "/think":
        _cmd_think(args, rt, config=config, model=config.model or "")
    elif cmd == "/reasoning":
        _cmd_reasoning(args, rt, config=config, model=config.model or "")
    elif cmd == "/fast":
        _cmd_fast(args, config, rt)
    elif cmd == "/verbose":
        _cmd_toggle(args, rt, "verbose", "modo verbose")
    elif cmd == "/trace":
        _cmd_toggle(args, rt, "trace", "modo trace")
    elif cmd == "/color":
        _cmd_color(args, rt, config)

    # ── Permisos y activación ─────────────────────────────────────────────────
    elif cmd in ("/elevated", "/elev"):
        _cmd_elevated(args, config, rt)
    elif cmd == "/activation":
        _cmd_activation(args, rt)

    # ── Agentes y modelos ─────────────────────────────────────────────────────
    elif cmd in ("/agents", "/agent"):
        _cmd_agent(args, config, agent_loop)
    elif cmd == "/switch":
        _cmd_switch(args, config, agent_loop)
    elif cmd == "/model":
        _cmd_model(args, config, agent_loop)
    elif cmd == "/models":
        _cmd_models(config, agent_loop)
    elif cmd == "/workspace":
        _cmd_workspace(args, config, agent_loop)
    elif cmd == "/webserver":
        _cmd_webserver(args, config, agent_loop)
    elif cmd == "/spawn":
        _cmd_spawn(args, agent_loop, config)
    elif cmd == "/subagents":
        _cmd_subagents(args, agent_loop, config)
    elif cmd == "/crestodian":
        _cmd_crestodian(args, agent_loop, config)

    # ── Sistema ───────────────────────────────────────────────────────────────
    elif cmd == "/status":
        print_status(config, agent_loop.session, rt, agent_loop.context)
        _print_integrations_status(agent_loop, config)
    elif cmd in ("/gateway-status", "/gwstatus"):
        print_gateway_status(config)
    elif cmd == "/settings":
        print_config(config)
        print_runtime(rt)
    elif cmd == "/config":
        _cmd_config_panel(args, config, rt)
    elif cmd == "/doctor":
        _cmd_doctor(config, agent_loop)
    elif cmd == "/logs":
        _cmd_logs(args)
    elif cmd == "/chatlog":
        _cmd_chatlog(args, agent_loop, config)
    elif cmd == "/commands":
        print_commands(SLASH_HELP)
    elif cmd == "/init":
        _cmd_init(args, config, agent_loop)
    elif cmd == "/review":
        _cmd_review(agent_loop, config)
    elif cmd == "/keybindings":
        _cmd_keybindings(args, agent_loop)
    elif cmd == "/hooks":
        _cmd_hooks(args, agent_loop)
    elif cmd == "/diff":
        _cmd_diff(args)
    elif cmd == "/symbols":
        _cmd_symbols(args)
    elif cmd == "/lint":
        _cmd_lint(args, config)
    elif cmd == "/lsp":
        _cmd_lsp(args, agent_loop)
    elif cmd == "/steer":
        _cmd_steer(args, agent_loop)
    elif cmd == "/mcp":
        _cmd_mcp(args, agent_loop)
    elif cmd == "/rag":
        _cmd_rag(args, agent_loop, config)
    elif cmd == "/snapshots":
        _cmd_snapshots(args, agent_loop)
    elif cmd == "/splash":
        print_splash(config)
    elif cmd == "/tip":
        console.print(f"\n  [dim]✦[/dim]  {_random_tip()}\n")
    elif cmd in ("/help", "/?"):
        print_help(SLASH_HELP)

    # ── Comandos de plugins + desconocidos ────────────────────────────────────
    else:
        if agent_loop.plugins:
            plugin_cmds = agent_loop.plugins.get_commands()
            if cmd in plugin_cmds:
                try:
                    plugin_cmds[cmd](args, agent_loop, config)
                except Exception as e:
                    console.print(f"  [red]✗[/red]  Error en plugin: {e}")
                return True
        console.print(
            f"  [red]✗[/red]  Comando desconocido: [bold]{cmd}[/bold]  —  "
            f"escribe [cyan]/help[/cyan] o [cyan]/commands[/cyan]"
        )
    return True


# ── Integraciones: bloque extra para /status ──────────────────────────────────

def _print_integrations_status(agent_loop, config) -> None:
    """Muestra RAG, MCP, LSP y Hooks en /status."""
    import time as _time

    def row(label: str, value: str) -> None:
        console.print(f"  [dim]{label:<18}[/dim]{value}")

    console.print()
    console.rule("[bold cyan]Integraciones[/bold cyan]", style="blue")
    console.print()

    # RAG
    rag = getattr(agent_loop, "_workspace_rag", None)
    if config.rag_enabled and rag:
        last = rag.last_indexed
        if last > 0:
            ela = _time.time() - last
            age = f"hace {ela:.0f}s" if ela < 120 else f"hace {ela/60:.0f}m"
        else:
            age = "pendiente"
        row("RAG", f"[green]●[/green]  {rag.index_size} chunks · {rag.indexed_files} ficheros · {age}")
    elif config.rag_enabled:
        row("RAG", "[yellow]⚠[/yellow]  habilitado pero sin inicializar  [dim](/doctor)[/dim]")
    else:
        row("RAG", "[dim]desactivado[/dim]  [dim](/rag enable)[/dim]")

    # MCP
    mcp = getattr(agent_loop, "_mcp_pool", None)
    if mcp:
        alive  = sum(1 for c in mcp._clients.values() if c.is_alive)
        total  = mcp.client_count
        tools  = mcp.tool_count
        color  = "green" if alive == total else "yellow"
        row("MCP", f"[{color}]●[/{color}]  {alive}/{total} servidores · {tools} tools")
    else:
        row("MCP", "[dim]sin servidores configurados[/dim]  [dim](mcp.servers en oocode.json)[/dim]")

    # LSP
    lsp_plugin = None
    if agent_loop.plugins:
        lsp_plugin = agent_loop.plugins._loaded.get("lsp")
    if lsp_plugin:
        pool  = getattr(lsp_plugin, "_pool", None)
        alive = pool.active_count if pool else 0
        total = len(pool._clients) if pool else 0
        avail = [s["name"] for s in (pool.available_servers() if pool else []) if s["installed"]]
        color = "green" if alive > 0 else "dim"
        row("LSP", f"[{color}]●[/{color}]  {alive} activos · "
                   + (f"instalados: {', '.join(avail)}" if avail else "ningún servidor instalado"))
    else:
        row("LSP", "[dim]plugin no activo[/dim]  [dim](/plugins enable lsp)[/dim]")

    # Hooks
    hooks = agent_loop.registry.hooks
    n_pre  = hooks.pre_count
    n_post = hooks.post_count
    if n_pre + n_post > 0:
        row("Hooks", f"[cyan]●[/cyan]  {n_pre} pre · {n_post} post")
    else:
        row("Hooks", "[dim]sin hooks registrados[/dim]")

    console.print()


# ── Sesión ────────────────────────────────────────────────────────────────────

def _cmd_new(agent_loop) -> None:
    old_id = agent_loop.session.session_id[:8]
    agent_loop.new_session()
    new_id = agent_loop.session.session_id[:8]
    try:
        from tools.diff_renderer import clear_history
        clear_history()
    except Exception:
        pass
    try:
        from tools.hooks import reset_suite_snapshot, reset_icd_snapshots
        reset_suite_snapshot()
        reset_icd_snapshots()
    except Exception:
        pass
    console.print(
        f"  [green]✓[/green]  Sesión [dim]{old_id}…[/dim] cerrada "
        f"→ nueva [cyan]{new_id}…[/cyan]"
    )


def _cmd_session(args: str, agent_loop) -> None:
    if not args:
        stats = agent_loop.session.stats()
        console.print(
            f"  Sesión: [bold cyan]{stats['session_id'][:8]}…[/bold cyan]  "
            f"[dim]{stats['message_count']} msgs · {stats['input_tokens']}↑ {stats['output_tokens']}↓ tokens[/dim]"
        )
        return
    sessions = agent_loop.session.list_sessions(100)
    target = next((s for s in sessions if s["session_id"].startswith(args)), None)
    if not target:
        console.print(f"  [red]✗[/red]  Sesión [bold]{args}[/bold] no encontrada. Usa /sessions.")
        return
    count = agent_loop.restore_session(target["session_id"])
    console.print(
        f"  [green]✓[/green]  Sesión [cyan]{target['session_id'][:8]}…[/cyan] restaurada "
        f"— [white]{count}[/white] mensajes en contexto."
    )


def _cmd_sessions(agent_loop) -> None:
    print_sessions(agent_loop.session.list_sessions(15), agent_loop.session.session_id)


def _cmd_usage(args: str, agent_loop, rt: RuntimeSettings) -> None:
    if args in USAGE_MODES:
        rt.usage_display = args
        console.print(f"  [green]✓[/green]  Modo usage → [bold cyan]{args}[/bold cyan]")
    elif not args:
        print_usage(agent_loop.session)
    else:
        console.print(f"  [yellow]Uso:[/yellow]  /usage [off|tokens|full]")


# ── Contexto ──────────────────────────────────────────────────────────────────

def _cmd_ctx(args: str, rt: RuntimeSettings) -> None:
    """Cambia el modo de contexto del workspace: mini (~150 tok) o full (~800 tok)."""
    if not args:
        color = "yellow" if rt.ctx_mode == "full" else "green"
        console.print(
            f"  ctx_mode: [{color}]{rt.ctx_mode}[/{color}]  "
            f"[dim]opciones: mini | full[/dim]\n"
            f"  [dim]mini: identidad + memoria compacta — para modelos pequeños[/dim]\n"
            f"  [dim]full: todos los ficheros del workspace sin límite — recomendado[/dim]"
        )
        return
    if args not in CTX_MODES:
        console.print(f"  [yellow]Modos válidos:[/yellow]  mini | full")
        return
    rt.ctx_mode = args
    color = "yellow" if args == "full" else "green"
    desc = "todos los ficheros sin límite" if args == "full" else "identidad + memoria compacta"
    console.print(
        f"  [green]✓[/green]  ctx → [{color}]{args}[/{color}]  "
        f"[dim]({desc})[/dim]"
    )


def _cmd_plan(args: str, rt: RuntimeSettings) -> None:
    """Plan-mode: si está ON, plan_create presenta el plan y espera tu aprobación.

    /plan          — muestra el estado
    /plan on|off   — activa/desactiva la aprobación previa de planes
    """
    arg = args.strip().lower()
    if arg in ("on", "off"):
        rt.plan_approval = (arg == "on")
        if rt.plan_approval:
            console.print(
                "  [green]✓[/green]  plan-mode [bold green]ON[/bold green]  "
                "[dim]— el agente pedirá tu aprobación antes de ejecutar cada plan "
                "(Aprobar / Editar / Cancelar)[/dim]"
            )
        else:
            console.print(
                "  [green]✓[/green]  plan-mode [bold]OFF[/bold]  "
                "[dim]— los planes se ejecutan directamente[/dim]"
            )
        return
    state = "ON" if rt.plan_approval else "OFF"
    color = "green" if rt.plan_approval else "dim"
    console.print(
        f"  plan-mode: [{color}]{state}[/{color}]  [dim]opciones: on | off[/dim]\n"
        f"  [dim]ON: plan_create presenta el plan y espera tu aprobación antes de ejecutarlo.[/dim]"
    )


def _cmd_compact(args: str, agent_loop) -> None:
    """
    /compact        — compactación inteligente con resumen LLM
    /compact fast   — compactación rápida sin resumen (libera tokens inmediatamente)
    """
    with_summary = args != "fast"
    agent_loop._do_compact(with_summary=with_summary)
    if not with_summary:
        console.print("  [dim](sin resumen LLM — usa /compact para resumen completo)[/dim]")


def _cmd_suggest(args: str, agent_loop, config) -> None:
    """
    /suggest         — muestra el estado de la sugerencia contextual del prompt
    /suggest on|off  — activa/desactiva la sugerencia del siguiente mensaje (persiste)
    """
    arg = args.strip().lower()
    if arg in ("on", "off"):
        val = (arg == "on")
        config.suggestions_enabled = val
        try:
            config.save()
        except Exception:
            pass
        estado = "activada" if val else "desactivada"
        console.print(f"  [dim]Sugerencia contextual {estado}.[/dim]")
    else:
        estado = "on" if getattr(config, "suggestions_enabled", True) else "off"
        console.print(
            f"  Sugerencia contextual del prompt: [bold]{estado}[/bold]\n"
            f"  [dim]Tras cada turno propone, en la franja idle, el siguiente "
            f"mensaje probable (llamada LLM corta).[/dim]\n"
            f"  [dim]/suggest on  ·  /suggest off[/dim]"
        )


def _cmd_checkpoint(agent_loop) -> None:
    """Guarda un checkpoint del contexto actual en la memoria diaria sin compactar."""
    ctx = agent_loop.context
    if not ctx.messages:
        console.print("  [dim]Contexto vacío, nada que guardar.[/dim]")
        return
    console.print("  [dim cyan]Generando checkpoint…[/dim cyan]")
    try:
        summary = agent_loop._summarize_messages(ctx.messages)
        if summary:
            agent_loop.ws.write_daily_memory(
                f"\n### Checkpoint manual\n{summary}\n"
            )
            console.print("  [green]✓[/green]  Checkpoint guardado en memoria diaria.")
            console.print(f"  [dim]{summary}[/dim]")
        else:
            console.print("  [yellow]⚠[/yellow]  El modelo no generó resumen. Intenta de nuevo.")
    except Exception as e:
        console.print(f"  [red]✗[/red]  Error generando checkpoint: {e}")


# ── Kill ──────────────────────────────────────────────────────────────────────

def _cmd_kill(args: str, agent_loop) -> None:
    """/kill — interrumpe el turno actual + subagentes/equipos al momento (aborta la
    llamada LLM en vuelo). /kill all — además deshabilita jobs del scheduler y resetea
    tareas wip."""
    is_all = args.strip().lower() == "all"

    # request_kill: marca _kill_requested, cierra a la fuerza el socket del LLM en
    # curso (también el de los subagentes, que comparten el pool del padre) y mata
    # todos los subagentes/equipos activos vía kill_all().
    summary = agent_loop.request_kill()
    killed_parts = []
    if summary.get("subagents"):
        killed_parts.append(f"{summary['subagents']} subagente(s)/equipo(s)")

    if is_all:
        # Extras de /kill all (scheduler + tareas wip), compartidos con el botón Kill
        # de la WebUI vía AgentLoop.kill_all_extras().
        extras = agent_loop.kill_all_extras()
        if extras.get("jobs"):
            killed_parts.append(f"{extras['jobs']} jobs del scheduler deshabilitados")
        if extras.get("wip"):
            killed_parts.append(f"{extras['wip']} tareas wip → todo")

        summary_str = "  ·  ".join(killed_parts) if killed_parts else "sin tareas activas"
        console.print(
            f"\n  [bold yellow]↯[/bold yellow]  [bold]Kill all[/bold]  "
            f"[dim]{summary_str}[/dim]\n"
        )
    else:
        extra = ("  ·  " + "  ·  ".join(killed_parts)) if killed_parts else ""
        console.print(
            f"\n  [yellow]↯[/yellow]  Kill enviado — turno y subagentes detenidos "
            f"al momento.{extra}\n"
        )


# ── Memoria ───────────────────────────────────────────────────────────────────

def _cmd_mem(args: str, agent_loop) -> None:
    """Dispatcher para /mem <subcomando> [argumentos]."""
    parts = args.split(maxsplit=1)
    sub   = parts[0].lower() if parts else ""
    rest  = parts[1].strip() if len(parts) > 1 else ""

    if sub in ("", "list"):
        _mem_list(agent_loop.memory)
    elif sub == "search":
        _mem_search(rest, agent_loop.memory)
    elif sub == "show":
        _mem_show(rest, agent_loop.memory)
    elif sub == "save":
        _mem_save(rest, agent_loop)
    elif sub == "rm":
        _mem_rm(rest, agent_loop.memory)
    elif sub == "rebuild":
        _mem_rebuild(agent_loop.memory)
    elif sub == "clear":
        _mem_clear(agent_loop.memory)
    else:
        console.print(
            f"  [red]✗[/red]  Subcomando desconocido: [bold]{sub}[/bold]\n"
            "  [dim]Disponibles: list · search · show · save · rm · rebuild · clear[/dim]"
        )


def _mem_list(memory) -> None:
    mems = []
    for md_path in sorted(memory._dir.glob("*.md")):
        if md_path.name == "MEMORY.md":
            continue
        emb_exists = md_path.with_suffix(".emb.json").exists()
        size = md_path.stat().st_size
        try:
            desc = next(
                (l.strip().lstrip("#").strip() for l in md_path.read_text().splitlines()
                 if l.strip() and not l.startswith("_")),
                ""
            )[:60]
        except Exception:
            desc = ""
        mems.append({
            "name": md_path.name,
            "size": size,
            "has_embedding": emb_exists,
            "desc": desc,
        })
    embed_ok = bool(memory._embed and memory._embed.is_available())
    print_mem_list(mems, embed_ok)


def _mem_search(query: str, memory) -> None:
    if not query:
        console.print("  [yellow]Uso:[/yellow]  /mem search <consulta>")
        return
    if not memory._embed or not memory._embed.is_available():
        _em = getattr(memory._embed, "_model", "embed model") if memory._embed else "embed model"
        console.print(
            f"  [red]✗[/red]  Embeddings no disponibles. "
            f"Comprueba que [cyan]{_em}[/cyan] está en el servidor Ollama."
        )
        return
    console.print(f"  [dim cyan]Buscando: {query[:60]}…[/dim cyan]")
    hits = memory.search(query, top_k=5)
    print_mem_search(hits, query)


def _mem_show(name: str, memory) -> None:
    if not name:
        console.print("  [yellow]Uso:[/yellow]  /mem show <nombre>")
        return
    content = memory.load(name)
    if "no encontrada" in content:
        console.print(f"  [red]✗[/red]  {content}")
        _hint_mem_names(memory)
        return
    console.print()
    console.rule(f"[bold cyan]{name}[/bold cyan]", style="blue")
    console.print(Padding(Markdown(content), (0, 0, 0, 2)))
    console.print()


def _mem_save(name: str, agent_loop) -> None:
    """
    /mem save <nombre>
    Pide al usuario el contenido por líneas (vacío para terminar).
    """
    if not name:
        console.print("  [yellow]Uso:[/yellow]  /mem save <nombre>")
        return
    console.print(f"  Escribe el contenido de [cyan]{name}[/cyan]:")
    console.print("  [dim](Escape+Enter para múltiples líneas; Enter para enviar)[/dim]")
    content = _tui_ask("Contenido", default="")
    if not content:
        console.print("  [dim]Cancelado — contenido vacío.[/dim]")
        return
    desc = _tui_ask("Descripción (Enter para omitir)", default="")
    result = agent_loop.memory.save(name, content, description=desc)
    console.print(f"  [green]✓[/green]  {result}")


def _mem_rm(name: str, memory) -> None:
    if not name:
        console.print("  [yellow]Uso:[/yellow]  /mem rm <nombre>")
        return
    slug = name.lower().replace(" ", "_")
    if not slug.endswith(".md"):
        slug += ".md"
    md_path = memory._dir / slug
    emb_path = md_path.with_suffix(".emb.json")
    if not md_path.exists():
        console.print(f"  [red]✗[/red]  Memoria [bold]{slug}[/bold] no encontrada.")
        _hint_mem_names(memory)
        return
    confirm = _tui_ask(f"¿Eliminar {slug}?", choices=["s", "n"], default="n")
    if confirm != "s":
        console.print("  [dim]Cancelado.[/dim]")
        return
    md_path.unlink()
    if emb_path.exists():
        emb_path.unlink()
    # Invalida cachés RAM
    memory._vec_cache.pop(md_path.name, None)
    memory._file_list_ts = 0.0
    # Elimina del índice
    _remove_from_index(slug, memory)
    console.print(f"  [green]✓[/green]  Memoria [bold]{slug}[/bold] eliminada.")


def _mem_rebuild(memory) -> None:
    """Recalcula embeddings de todas las memorias (útil si se cambia de modelo embed)."""
    if not memory._embed or not memory._embed.is_available():
        console.print("  [red]✗[/red]  Embeddings no disponibles.")
        return
    from agent.embeddings import save_embedding
    mds = [p for p in memory._dir.glob("*.md") if p.name != "MEMORY.md"]
    if not mds:
        console.print("  [dim]Sin memorias para recalcular.[/dim]")
        return
    console.print(f"  Recalculando {len(mds)} embeddings…")
    ok, fail = 0, 0
    for md_path in mds:
        try:
            content = md_path.read_text()
            vec = memory._embed.embed(content)
            if vec:
                save_embedding(md_path.with_suffix(".emb.json"), vec)
                memory._vec_cache[md_path.name] = vec   # actualiza caché RAM
                ok += 1
            else:
                fail += 1
        except Exception:
            fail += 1
        console.print(f"  [dim]  {md_path.name}[/dim]")
    memory._file_list_ts = 0.0   # fuerza re-escaneo de ficheros en próxima búsqueda
    console.print(
        f"  [green]✓[/green]  {ok} embeddings recalculados"
        + (f"  [yellow]({fail} errores)[/yellow]" if fail else "")
    )


def _mem_clear(memory) -> None:
    mds = [p for p in memory._dir.glob("*.md") if p.name != "MEMORY.md"]
    embs = list(memory._dir.glob("*.emb.json"))
    total = len(mds)
    if total == 0:
        console.print("  [dim]Sin memorias que eliminar.[/dim]")
        return
    confirm = _tui_ask(f"¿Eliminar TODAS las {total} memorias?", choices=["s", "n"], default="n")
    if confirm != "s":
        console.print("  [dim]Cancelado.[/dim]")
        return
    for p in mds + embs:
        p.unlink(missing_ok=True)
    # Reinicia índice y cachés RAM
    memory._index.write_text("# Memory Index\n\n(Sin recuerdos guardados todavía)")
    memory._vec_cache.clear()
    memory._file_list_ts = 0.0
    console.print(f"  [green]✓[/green]  {total} memorias eliminadas.")


# ── Modos de respuesta ────────────────────────────────────────────────────────

def _cmd_think(args: str, rt: RuntimeSettings, config=None, model: str = "") -> None:
    if not args:
        console.print(
            f"  think: [bold cyan]{rt.think_level}[/bold cyan]  "
            f"[dim]opciones: {' | '.join(THINK_LEVELS)}[/dim]"
        )
        return
    if args not in THINK_LEVELS:
        console.print(f"  [yellow]Niveles válidos:[/yellow]  {' | '.join(THINK_LEVELS)}")
        return
    rt.think_level = args
    label = {"off": "desactivado", "minimal": "mínimo", "low": "bajo",
             "on": "activado", "medium": "medio", "high": "alto",
             "full": "máximo"}.get(args, args)
    console.print(f"  [green]✓[/green]  Think → [bold cyan]{args}[/bold cyan]  [dim]({label})[/dim]")
    if config and model:
        config.save_model_thinking(model, rt.think_level, rt.reasoning)
        console.print(f"  [dim]Preferencia guardada para {model}[/dim]")


def _cmd_reasoning(args: str, rt: RuntimeSettings, config=None, model: str = "") -> None:
    if not args:
        status = "[bold cyan]on[/bold cyan]" if rt.reasoning else "[dim]off[/dim]"
        console.print(f"  razonamiento explícito: {status}")
        return
    if args not in ("on", "off"):
        console.print("  [yellow]Uso:[/yellow]  /reasoning on|off")
        return
    rt.reasoning = (args == "on")
    icon = "[bold cyan]on[/bold cyan]" if rt.reasoning else "[dim]off[/dim]"
    console.print(f"  [green]✓[/green]  Razonamiento explícito → {icon}")
    if config and model:
        config.save_model_thinking(model, rt.think_level, rt.reasoning)
        console.print(f"  [dim]Preferencia guardada para {model}[/dim]")


def _cmd_toggle(args: str, rt: RuntimeSettings, attr: str, label: str) -> None:
    if not args:
        val = getattr(rt, attr)
        status = "[bold cyan]on[/bold cyan]" if val else "[dim]off[/dim]"
        console.print(f"  {label}: {status}")
        return
    if args == "on":
        setattr(rt, attr, True)
        console.print(f"  [green]✓[/green]  {label} → [bold cyan]on[/bold cyan]")
    elif args == "off":
        setattr(rt, attr, False)
        console.print(f"  [green]✓[/green]  {label} → [dim]off[/dim]")
    else:
        console.print(f"  [yellow]Uso:[/yellow]  /{attr} on|off")


def _cmd_fast(args: str, config, rt: RuntimeSettings) -> None:
    if args == "status" or not args:
        status = "[bold cyan]on[/bold cyan]" if rt.fast_mode else "[dim]off[/dim]"
        model = rt.fast_model or "[dim](no configurado)[/dim]"
        console.print(f"  fast: {status}  [dim]modelo fast: {model}[/dim]")
        return
    if args == "on":
        if not rt.fast_model:
            try:
                from api.ollama import list_ollama_models
                models = list_ollama_models(config.ollama_host)
                if models:
                    smallest = min(models, key=lambda m: m["size"] or 9e18)
                    rt.fast_model = smallest["name"]
            except Exception:
                console.print("  [red]✗[/red]  No se pudo detectar modelo fast.")
                return
        rt.normal_model = config.model
        rt.fast_mode = True
        console.print(f"  [green]✓[/green]  fast → [bold cyan]on[/bold cyan]  [dim]usando {rt.fast_model}[/dim]")
    elif args == "off":
        rt.fast_mode = False
        if rt.normal_model:
            config.model = rt.normal_model
        console.print(f"  [green]✓[/green]  fast → [dim]off[/dim]  [dim]modelo: {config.model}[/dim]")
    else:
        console.print("  [yellow]Uso:[/yellow]  /fast on | off | status")


# ── Permisos ──────────────────────────────────────────────────────────────────

def _cmd_elevated(args: str, config, rt: RuntimeSettings) -> None:
    if not args:
        console.print(
            f"  elevated: [bold cyan]{rt.elevated}[/bold cyan]  "
            f"[dim]opciones: {' | '.join(ELEVATED_MODES)}[/dim]"
        )
        return
    if args not in ELEVATED_MODES:
        console.print(f"  [yellow]Modos válidos:[/yellow]  {' | '.join(ELEVATED_MODES)}")
        return
    rt.elevated = args
    desc = {
        "off":  "solo lectura — tools 'ask' bloqueadas, solo 'auto' permitidas",
        "on":   "elevado — auto-aprueba 'ask', respeta 'deny' explícitos",
        "ask":  "normal — respeta permisos de oocode.json (auto/ask/deny)",
        "full": "sin restricciones — auto-aprueba todo, incluso 'deny'",
    }[args]
    color = {"off": "red", "on": "yellow", "ask": "cyan", "full": "green"}[args]
    console.print(
        f"  [green]✓[/green]  elevated → [{color}]{args}[/{color}]  [dim]({desc})[/dim]"
    )


def _cmd_activation(args: str, rt: RuntimeSettings) -> None:
    if not args:
        console.print(f"  activation: [bold cyan]{rt.activation}[/bold cyan]  [dim](always | mention)[/dim]")
        return
    if args in ("always", "mention"):
        rt.activation = args
        console.print(f"  [green]✓[/green]  activation → [bold cyan]{args}[/bold cyan]")
    else:
        console.print("  [yellow]Uso:[/yellow]  /activation always | mention")


# ── Agentes y modelos ─────────────────────────────────────────────────────────

def _cmd_agent(args: str, config, agent_loop=None) -> None:
    parts = args.strip().split(maxsplit=1) if args.strip() else []

    # ── /agent team … ────────────────────────────────────────────────────────
    if parts and parts[0].lower() == "team":
        _cmd_agent_team(parts[1] if len(parts) > 1 else "", config, agent_loop)
        return

    # ── /agent new <id> [nombre] [descripción] ───────────────────────────────
    if parts and parts[0].lower() == "new":
        _cmd_agent_new(parts[1] if len(parts) > 1 else "", config, agent_loop)
        return

    # ── /agent reset <id> [descripción] ─────────────────────────────────────
    if parts and parts[0].lower() == "reset":
        _cmd_agent_reset(parts[1] if len(parts) > 1 else "", config, agent_loop)
        return

    # ── /agent <id> ──────────────────────────────────────────────────────────
    if parts:
        target = next((a for a in config.agents if a.id == parts[0]), None)
        if not target:
            ids = ", ".join(a.id for a in config.agents)
            console.print(f"  [red]✗[/red]  Agente [bold]{parts[0]}[/bold] no existe. Disponibles: {ids}")
            console.print(f"  [dim]Crea uno nuevo con:[/dim] [cyan]/agent new <id> [nombre] [descripción][/cyan]")
            return
        console.print(
            f"  [bold cyan]{target.emoji} {target.name}[/bold cyan]  [dim]({target.id})[/dim]\n"
            f"  [dim]modelo:[/dim]    {target.model or '(heredado)'}\n"
            f"  [dim]workspace:[/dim] {target.workspace}"
        )
    else:
        print_agents(config.agents, config.agent_id)


def _emoji_for_role(desc: str) -> str:
    """Elige emoji automáticamente según la descripción del rol."""
    desc_l = desc.lower()
    if any(w in desc_l for w in ("security", "seguridad", "pentest", "hacking")):
        return "🔐"
    if any(w in desc_l for w in ("home", "office", "ofici", "document", "excel", "word")):
        return "🏠"
    if any(w in desc_l for w in ("iot", "hardware", "device", "sensor", "arduino", "esp")):
        return "⚡"
    if any(w in desc_l for w in ("web", "frontend", "react", "vue", "html", "css")):
        return "🌐"
    if any(w in desc_l for w in ("data", "analysis", "analisis", "ml", "machine", "ai", "model")):
        return "📊"
    if any(w in desc_l for w in ("devops", "docker", "kubernetes", "deploy", "ci", "infra")):
        return "⚙️"
    if any(w in desc_l for w in ("test", "qa", "quality", "calidad")):
        return "🧪"
    if any(w in desc_l for w in ("reason", "think", "logic", "analytic", "analysis", "razon")):
        return "🧠"
    if any(w in desc_l for w in ("write", "writer", "doc", "text", "content", "escri")):
        return "✍️"
    return "🤖"


# Perfiles de dominio: guían la personalización de la persona del agente para que
# su flujo de trabajo encaje con su función (no asume programación). Cada perfil
# describe el ciclo Reúne→Actúa→Verifica en términos del dominio.
_AGENT_DOMAIN_PROFILES: dict[str, dict] = {
    "code": {
        "label":  "programación",
        "gather": "lee ficheros y busca con grep_code/lsp_symbols",
        "act":    "edita o crea código con edit_file/write_file",
        "verify": "ejecuta tests y linters (run_tests/lint_file/lsp_diagnostics)",
        "areas":  "código fuente, tests, dependencias, git",
    },
    "office": {
        "label":  "ofimática y documentos",
        "gather": "revisa plantillas, datos de origen y requisitos del documento",
        "act":    "genera o edita documentos (Word/Excel/PowerPoint/PDF)",
        "verify": "comprueba formato, datos, fórmulas y que no queden campos sin rellenar",
        "areas":  "documentos, hojas de cálculo, presentaciones, correo, calendario",
    },
    "security": {
        "label":  "seguridad y análisis defensivo",
        "gather": "reconoce el objetivo y reúne información (recon, fuentes)",
        "act":    "analiza, audita o aplica controles según la tarea autorizada",
        "verify": "contrasta hallazgos, valora severidad y documenta evidencias",
        "areas":  "recon, análisis web, criptografía, CTF, controles defensivos",
    },
    "iot": {
        "label":  "IoT y domótica",
        "gather": "consulta el estado de dispositivos y su configuración",
        "act":    "controla o configura dispositivos (luces, sensores, MQTT, HA)",
        "verify": "confirma el nuevo estado del dispositivo tras cada acción",
        "areas":  "dispositivos, sensores, MQTT, Home Assistant, ESPHome",
    },
    "web": {
        "label":  "investigación web y extracción de datos",
        "gather": "busca fuentes, hace fetch/crawl de páginas y consulta APIs",
        "act":    "extrae, sintetiza y estructura la información encontrada",
        "verify": "contrasta varias fuentes y verifica la fiabilidad de los datos",
        "areas":  "páginas web, APIs, feeds, documentos online",
    },
    "data": {
        "label":  "datos y análisis",
        "gather": "explora los datos y su esquema (consultas, estadísticas)",
        "act":    "transforma, consulta o modela los datos",
        "verify": "valida resultados con cifras concretas y comprueba consistencia",
        "areas":  "bases de datos, CSV/hojas, métricas, modelos",
    },
    "devops": {
        "label":  "DevOps e infraestructura",
        "gather": "revisa el estado de servicios, contenedores y configuración",
        "act":    "despliega, configura o gestiona la infraestructura",
        "verify": "comprueba salud de servicios, logs y readiness tras cada cambio",
        "areas":  "Docker/compose, despliegues, servicios, CI/CD, redes",
    },
    "general": {
        "label":  "asistencia general",
        "gather": "reúne el contexto necesario para la tarea",
        "act":    "realiza la acción solicitada con las herramientas adecuadas",
        "verify": "comprueba que el resultado es correcto y completo",
        "areas":  "según la tarea del usuario",
    },
}


def _classify_agent_domain(desc: str) -> str:
    """Clasifica el dominio principal de un agente a partir de su descripción/nombre.

    Devuelve una clave de `_AGENT_DOMAIN_PROFILES`. Determinista, sin LLM.
    """
    d = (desc or "").lower()
    if any(w in d for w in ("security", "seguridad", "pentest", "hacking", "ctf",
                            "vuln", "exploit", "forense", "malware")):
        return "security"
    if any(w in d for w in ("iot", "domotica", "domótica", "sensor", "arduino",
                            "esp", "mqtt", "home assistant", "tapo", "alexa", "device")):
        return "iot"
    if any(w in d for w in ("office", "ofici", "document", "informe", "word",
                            "excel", "powerpoint", "ppt", "pdf", "ofimática", "ofimatica",
                            "correo", "email", "calendar", "report")):
        return "office"
    if any(w in d for w in ("crawl", "scrap", "webcrawler", "research", "investiga",
                            "buscador", "noticias", "feed", "fetch", "extrae")):
        return "web"
    if any(w in d for w in ("devops", "docker", "kubernetes", "k8s", "deploy",
                            "despliegue", "infra", "ci/cd", "pipeline", "nginx")):
        return "devops"
    if any(w in d for w in ("data", "datos", "analysis", "análisis", "analisis",
                            "sql", "database", "base de datos", "métrica", "metrica",
                            "ml", "machine learning", "modelo", "estadístic")):
        return "data"
    if any(w in d for w in ("code", "código", "codigo", "program", "develop",
                            "desarrollo", "software", "backend", "frontend", "api",
                            "refactor", "bug", "test", "compil")):
        return "code"
    return "general"


def _cmd_agent_new(args: str, config, agent_loop=None) -> None:  # noqa: C901
    """Crea un nuevo agente con workspace propio.

    Uso: /agent new <id> [nombre] [descripción de la función]
    """
    from config import CONFIG_DIR
    from workspace.manager import WorkspaceManager

    parts = args.strip().split(maxsplit=2) if args.strip() else []
    if not parts:
        console.print("  [yellow]Uso:[/yellow]  /agent new <id> [nombre] [descripción]")
        console.print("  [dim]Ejemplo:[/dim]  /agent new devops DevOps \"gestión de infraestructura y Docker\"")
        return

    agent_id  = parts[0].strip().lower().replace(" ", "-")
    agent_name = parts[1].strip() if len(parts) > 1 else agent_id.capitalize()
    description = parts[2].strip() if len(parts) > 2 else ""

    # Validar id
    if not agent_id.replace("-", "").replace("_", "").isalnum():
        console.print(f"  [red]✗[/red]  ID inválido: [bold]{agent_id}[/bold] — solo letras, números, guiones")
        return
    if any(a.id == agent_id for a in config.agents):
        console.print(f"  [red]✗[/red]  Agente [bold]{agent_id}[/bold] ya existe. Usa [cyan]/agent reset {agent_id}[/cyan] para resetear.")
        return

    emoji = _emoji_for_role(description or agent_name)
    ws_path = str(CONFIG_DIR / "workspace" / agent_id)

    console.print(f"\n  Creando agente [bold cyan]{emoji} {agent_name}[/bold cyan]  [dim]({agent_id})[/dim]")
    if description:
        console.print(f"  [dim]Función:[/dim] {description}")
    console.print(f"  [dim]Workspace:[/dim] {ws_path}\n")

    # Crear workspace desde templates
    ws = WorkspaceManager(
        ws_path,
        agent_name=agent_name,
        agent_emoji=emoji,
        ollama_host=config.ollama_host,
        permissions=config.permissions,
        max_memory_lines=config.ws_max_memory_lines,
        max_daily_chars=config.ws_max_daily_chars,
    )
    created = ws.init(overwrite=False, use_examples=False)

    # Clasificar dominio para adaptar la persona (no asumir programación).
    domain = _classify_agent_domain(description or agent_name)
    if domain != "general":
        console.print(f"  [dim]Dominio detectado:[/dim] {_AGENT_DOMAIN_PROFILES[domain]['label']}")

    # Si hay descripción y hay LLM disponible, personalizar con LLM (consciente del dominio).
    personalized = False
    if description and agent_loop is not None:
        console.print("  [dim]Consultando LLM para personalizar workspace…[/dim]")
        try:
            _personalize_workspace_with_llm(ws_path, agent_id, agent_name, emoji, description, config)
            personalized = True
        except Exception as _e:
            console.print(f"  [yellow]⚠[/yellow]  LLM no disponible para personalización: {_e}")

    # Fallback sin LLM: si el agente NO es de programación y no se personalizó,
    # escribir un SOUL.md adaptado al dominio en lugar de la plantilla code-céntrica.
    if not personalized and domain not in ("code", "general"):
        if _write_domain_soul(ws_path, agent_name, emoji, description, domain):
            console.print(f"    [dim green]✦[/dim green] SOUL.md adaptado a {_AGENT_DOMAIN_PROFILES[domain]['label']}")
        else:
            console.print("  [dim]Workspace creado con plantillas estándar.[/dim]")
    elif not personalized:
        console.print("  [dim]Workspace creado con plantillas estándar.[/dim]")

    # Registrar agente en oocode.json
    _add_agent_to_config(agent_id, agent_name, emoji, ws_path, config)

    console.print(f"\n  [green]✓[/green]  Agente [bold]{agent_id}[/bold] creado — {len(created)} ficheros")
    for f in created:
        console.print(f"    [dim cyan]+[/dim cyan] {ws_path}/{f}")
    console.print(f"\n  [dim]Usa[/dim] [cyan]/switch {agent_id}[/cyan] para activarlo.")


def _cmd_agent_reset(args: str, config, agent_loop=None) -> None:  # noqa: C901
    """Resetea el workspace de un agente a las plantillas originales.

    Uso: /agent reset <id> [nueva_descripción]
    """
    parts = args.strip().split(maxsplit=1) if args.strip() else []
    if not parts:
        ids = ", ".join(a.id for a in config.agents)
        console.print("  [yellow]Uso:[/yellow]  /agent reset <id> [nueva descripción]")
        console.print(f"  [dim]Agentes disponibles:[/dim] {ids}")
        return

    agent_id = parts[0].strip()
    new_desc  = parts[1].strip() if len(parts) > 1 else ""
    target = next((a for a in config.agents if a.id == agent_id), None)
    if not target:
        ids = ", ".join(a.id for a in config.agents)
        console.print(f"  [red]✗[/red]  Agente [bold]{agent_id}[/bold] no existe. Disponibles: {ids}")
        return

    console.print(
        f"\n  [bold yellow]⚠  ¿Resetear workspace de [cyan]{target.emoji} {target.name}[/cyan]?[/bold yellow]\n"
        f"  Esto sobreescribirá IDENTITY.md, SOUL.md, USER.md, TOOLS.md, HEARTBEAT.md y AGENTS.md.\n"
        f"  [dim]MEMORY.md y memory/ se conservan.[/dim]\n"
    )
    try:
        confirm = Prompt.ask("  Confirma", choices=["s", "n"], default="n")
    except (KeyboardInterrupt, EOFError):
        console.print("  Cancelado.")
        return
    if confirm != "s":
        console.print("  Cancelado.")
        return

    # Regenerar ficheros de identidad por el MISMO camino que la creación
    # (WorkspaceManager.init → workspace/templates/ con fallback a generadores).
    # Antes el reset usaba SIEMPRE los generadores Python → escribía contenido
    # divergente del de un agente recién creado y perdía las mejoras de las
    # plantillas (patrón de conversación, Core…). MEMORY.md se preserva.
    from workspace.manager import WORKSPACE_FILES, WorkspaceManager
    ws_path = Path(target.workspace).expanduser()
    old_contents = {
        fn: ((ws_path / fn).read_text() if (ws_path / fn).exists() else "")
        for fn in WORKSPACE_FILES
    }
    ws = WorkspaceManager(
        workspace_path=target.workspace,
        agent_name=target.name,
        agent_emoji=target.emoji,
        ollama_host=config.ollama_host,
        permissions=config.permissions,
    )
    ws.init(overwrite=True, preserve=("MEMORY.md",))

    regenerated = []
    for filename in WORKSPACE_FILES:
        if filename == "MEMORY.md":
            continue  # Preservada
        fpath = ws_path / filename
        content = fpath.read_text() if fpath.exists() else ""
        if content != old_contents[filename]:
            regenerated.append((filename, old_contents[filename], content))

    # Mostrar diffs de los ficheros cambiados
    if regenerated:
        import difflib
        console.print()
        for fname, old_c, new_c in regenerated:
            old_lines = old_c.splitlines(keepends=True)
            new_lines = new_c.splitlines(keepends=True)
            diff = list(difflib.unified_diff(old_lines, new_lines,
                                             fromfile=f"{fname} (antes)",
                                             tofile=f"{fname} (después)",
                                             n=1))
            if diff:
                console.print(f"  [bold dim]  {fname}[/bold dim]")
                for dl in diff[:40]:  # máx 40 líneas por fichero para no saturar
                    dl_s = dl.rstrip("\n")
                    if dl_s.startswith("+++") or dl_s.startswith("---"):
                        console.print(f"    [dim]{dl_s}[/dim]")
                    elif dl_s.startswith("+"):
                        console.print(f"    [green]{dl_s}[/green]")
                    elif dl_s.startswith("-"):
                        console.print(f"    [red]{dl_s}[/red]")
                    elif dl_s.startswith("@@"):
                        console.print(f"    [dim cyan]{dl_s}[/dim cyan]")
                    else:
                        console.print(f"    [dim]{dl_s}[/dim]")
                if len(diff) > 40:
                    console.print(f"    [dim](… {len(diff)-40} líneas más)[/dim]")
        console.print()

    # Si hay descripción y LLM disponible, personalizar
    if new_desc and agent_loop is not None:
        console.print("  [dim]Consultando LLM para personalizar workspace…[/dim]")
        try:
            _personalize_workspace_with_llm(target.workspace, agent_id, target.name, target.emoji, new_desc, config)
        except Exception as _e:
            console.print(f"  [yellow]⚠[/yellow]  LLM no disponible: {_e}")

    console.print(f"\n  [green]✓[/green]  Workspace de [bold]{agent_id}[/bold] reseteado")
    for fname, _, _ in regenerated:
        console.print(f"    [dim yellow]↻[/dim yellow] {fname}")
    if not regenerated:
        console.print("  [dim]Sin cambios (los ficheros ya eran los predeterminados).[/dim]")


def _personalize_workspace_with_llm(
    ws_path: str, agent_id: str, agent_name: str, emoji: str,
    description: str, config
) -> None:
    """Llama al LLM para personalizar los ficheros del workspace según la descripción del agente."""
    domain = _classify_agent_domain(description or agent_name)
    prof = _AGENT_DOMAIN_PROFILES[domain]
    _domain_guidance = (
        f"DOMINIO PRINCIPAL de este agente: {prof['label']}.\n"
        f"Adapta el \"## Flujo de Trabajo\" y las \"## Reglas\" de SOUL.md a ESTE dominio:\n"
        f"- Reúne contexto: {prof['gather']}.\n"
        f"- Actúa: {prof['act']}.\n"
        f"- Verifica: {prof['verify']}.\n"
        f"- Áreas de trabajo: {prof['areas']}.\n"
        f"IMPORTANTE: NO asumas que es un agente de programación salvo que el dominio sea "
        f"'programación'. Si el dominio NO es programación, NO incluyas reglas de tests, "
        f"linters, git ni edición de código fuente — usa el flujo y la verificación propios "
        f"del dominio indicado.\n\n"
    )
    prompt = (
        f"Eres un asistente de configuración de OOCode. Genera el contenido personalizado para un agente con:\n"
        f"- ID: {agent_id}\n"
        f"- Nombre: {agent_name}\n"
        f"- Emoji: {emoji}\n"
        f"- Función/Descripción: {description}\n\n"
        f"{_domain_guidance}"
        f"Genera los siguientes ficheros de workspace en formato Markdown. "
        f"Sé conciso, práctico y especializado en la función indicada.\n\n"
        f"Responde con exactamente este formato (usa los separadores exactos):\n\n"
        f"===IDENTITY.md===\n"
        f"[contenido de IDENTITY.md personalizado para este agente]\n\n"
        f"===SOUL.md===\n"
        f"[contenido de SOUL.md con la personalidad y enfoque del agente]\n\n"
        f"===HEARTBEAT.md===\n"
        f"[contenido de HEARTBEAT.md con tareas de mantenimiento relevantes para este agente]\n\n"
        f"===TOOLS.md===\n"
        f"[sección inicial de TOOLS.md con notas de entorno específicas para este agente]\n"
    )
    # Usa la abstracción de backend para funcionar con cualquier api_type
    # (ollama | openai | anthropic), no solo Ollama.
    from api import build_client
    client = build_client(config)
    try:
        resp = client.chat_sync(
            model=config.model or "qwen3:latest",
            messages=[{"role": "user", "content": prompt}],
            tools=[],
            model_params={"temperature": 0.7, "num_predict": 2000},
        )
        content = resp.text
    finally:
        client.close()

    # Parsear respuesta y escribir ficheros
    ws = Path(ws_path)
    sections = {"IDENTITY.md": "", "SOUL.md": "", "HEARTBEAT.md": "", "TOOLS.md": ""}
    current = None
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("===") and stripped.endswith("==="):
            fname = stripped[3:-3].strip()
            if fname in sections:
                current = fname
                continue
        if current:
            sections[current] += line + "\n"

    for fname, body in sections.items():
        body = body.strip()
        if body and len(body) > 50:  # solo escribir si hay contenido real
            (ws / fname).write_text(body + "\n")
            console.print(f"    [dim green]✦[/dim green] {fname} personalizado por LLM")


def _write_domain_soul(ws_path: str, agent_name: str, emoji: str,
                       description: str, domain: str) -> bool:
    """Escribe un SOUL.md adaptado al dominio SIN LLM (fallback determinista).

    Se usa cuando el agente NO es de programación y no hubo personalización por
    LLM, para que un agente de oficina/seguridad/web no herede la plantilla
    code-céntrica por defecto. Devuelve True si escribió el fichero.
    """
    prof = _AGENT_DOMAIN_PROFILES.get(domain)
    if not prof or domain == "code":
        return False
    desc_line = description.strip() or prof["label"]
    soul = f"""# SOUL.md — {emoji} {agent_name}

_Eres {agent_name}, un agente especializado en {prof['label']}. Un compañero de trabajo, no un chatbot._

## Core

1. **Ayuda genuinamente, no performativamente.** Cálido y cercano, como un compañero que va contando lo que hace; la amabilidad va en explicar y acompañar, no en acuses huecos ("¡Claro!", "¡Por supuesto!").
2. **Sé proactivo.** Reúne el contexto antes de preguntar.
3. **Comunica y justifica lo que decides.** Narra de forma continua qué haces y qué encuentras, y al decidir di el veredicto, el motivo y la acción. Nunca trabajes en silencio ni cierres una tarea solo con su título.
4. **Honesto > cortés.** Si algo es mala idea, dilo directamente con alternativas.
5. **Deja al usuario sus decisiones.** Cuando hay varias opciones válidas o la elección es del usuario, pregunta con `ask_user` (no en texto plano).
6. **El contexto lo es todo.** Entiende antes de actuar.

## Tu función

{desc_line}

Áreas de trabajo: {prof['areas']}.

## Límites

- **Privado = privado siempre.** No revelo información sensible sin permiso explícito.
- **Pregunta antes de acciones externas e irreversibles** (enviar, publicar, borrar, sobrescribir).
- **Nunca envíes respuestas a medias.** Si la respuesta es larga, la completo.

## Flujo de Trabajo

1. **Clasifica** — ¿basta una frase + acción, o necesita un plan numerado (≥3 pasos)?
2. **Reúne contexto** — {prof['gather']}. Errores o datos desconocidos → `web_search` primero.
3. **Actúa** — antes de cada acción que cambia algo, anuncia el objeto concreto en una frase; después describe qué cambió. {prof['act'].capitalize()}.
4. **Verifica** — {prof['verify']}. Reporta el resultado con datos concretos.
5. **Finaliza y reporta** — qué se hizo · qué se produjo o cambió · resultado de la verificación · advertencias.

## Reglas de Oro

- **Nunca inventes datos, rutas ni resultados.**
- **El usuario NO ve las tools ni sus resultados — solo tu texto.** Comunica qué encuentras y qué haces.
- **Nunca declares completado sin verificar** con los medios de tu dominio.
- **Anti-bucle:** si una tool falla 2 veces con el mismo argumento, CAMBIA de estrategia.

## Continuidad

Estos ficheros son tu memoria. Léelos al arrancar. Actualízalos cuando aprendas algo nuevo.

- **Diario:** `memory/YYYY-MM-DD.md` — logs de lo que pasó hoy
- **Largo plazo:** `MEMORY.md` — recuerdos curados, decisiones, lecciones
"""
    try:
        (Path(ws_path) / "SOUL.md").write_text(soul)
        return True
    except Exception:
        return False


def _add_agent_to_config(agent_id: str, agent_name: str, emoji: str, ws_path: str, config) -> None:
    """Añade el nuevo agente a ~/.oocode/oocode.json."""
    from config import CONFIG_FILE
    raw = json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}
    agents_sec = raw.setdefault("agents", {})
    agents_list = agents_sec.setdefault("list", [])
    # Evitar duplicados
    if not any(a.get("id") == agent_id for a in agents_list):
        agents_list.append({
            "id":        agent_id,
            "name":      agent_name,
            "emoji":     emoji,
            "workspace": ws_path,
        })
    CONFIG_FILE.write_text(json.dumps(raw, indent=2, ensure_ascii=False))
    # Actualizar la lista en el config en memoria
    from config import AgentDef
    new_def = AgentDef(id=agent_id, name=agent_name, emoji=emoji, workspace=ws_path)
    if not any(a.id == agent_id for a in config.agents):
        config.agents.append(new_def)


def _cmd_switch(args: str, config, agent_loop) -> None:
    """Cambia el agente activo en runtime recargando workspace, sesión y memoria."""
    from config import OOConfig
    from agent.session import SessionManager
    from agent.services import (
        build_workspace_manager, build_embedding_client, build_memory_system,
    )

    if not args.strip():
        ids = ", ".join(a.id for a in config.agents)
        console.print(f"  [yellow]Uso:[/yellow]  /switch <id>   Disponibles: {ids}")
        return

    new_id = args.strip().split()[0]
    target = next((a for a in config.agents if a.id == new_id), None)
    if not target:
        ids = ", ".join(a.id for a in config.agents)
        console.print(f"  [red]✗[/red]  Agente [bold]{new_id}[/bold] no existe. Disponibles: {ids}")
        return

    if new_id == config.agent_id:
        console.print(f"  [dim]Ya estás en el agente [bold]{new_id}[/bold][/dim]")
        return

    # Guardar sesión actual antes de cambiar
    try:
        agent_loop.session.end()
    except Exception:
        pass

    # Cargar config del nuevo agente
    new_cfg = OOConfig.load(agent_id=new_id)

    # Crear nuevo WorkspaceManager
    new_ws = build_workspace_manager(new_cfg)
    if not new_ws.exists():
        created = new_ws.init()
        console.print(f"  [green]✓[/green]  Workspace inicializado: {', '.join(created)}")

    # Crear nueva sesión y memoria para el nuevo agente
    new_session = SessionManager(new_id)
    embed_client = build_embedding_client(new_cfg)
    new_memory = build_memory_system(new_cfg, embed_client)

    # Actualizar agent_loop con el nuevo agente
    agent_loop.config  = new_cfg
    agent_loop.ws      = new_ws
    agent_loop.session = new_session
    agent_loop.memory  = new_memory

    # Resetear contexto para empezar limpio con el nuevo agente
    agent_loop.context.clear()
    agent_loop._last_response  = ""
    agent_loop._last_tool_calls = []
    agent_loop._turn_mem_snippet = None
    agent_loop._turn_rag_snippet = None

    # Actualizar config global para el REPL (la referencia compartida)
    for attr in ("agent_id", "agent_name", "agent_emoji", "model", "workspace",
                 "ollama_host"):
        setattr(config, attr, getattr(new_cfg, attr))

    # Iniciar nueva sesión
    new_ws.mark_new_session()
    new_session.start(new_cfg.model or "", new_cfg.workspace)

    console.print(
        f"\n  [bold cyan]{target.emoji} Cambiado a {target.name}[/bold cyan]  "
        f"[dim]({new_id})[/dim]\n"
        f"  [dim]workspace:[/dim] {target.workspace}\n"
        f"  [dim]modelo:[/dim]    {target.model or '(heredado)'}\n"
    )


def _cmd_agent_team(args: str, config, agent_loop=None) -> None:  # noqa: C901
    """Gestión de AgentTeams: list, status, create, add, done, run, delete."""
    from agent.tasks import (
        create_team, load_team, add_subtask as _add_subtask,
        complete_subtask as _complete_subtask, get_team_status,
        list_teams, delete_team,
    )
    from rich.table import Table
    from rich import box as rbox

    parts = args.strip().split(maxsplit=1) if args.strip() else []
    sub   = parts[0].lower() if parts else "list"
    rest  = parts[1] if len(parts) > 1 else ""

    STATUS_STYLE = {"idle": "dim", "active": "bold green", "completed": "cyan", "failed": "bold red"}
    STATUS_ICON  = {"idle": "·", "active": "⚡", "completed": "✓", "failed": "✗"}

    # ── list ──────────────────────────────────────────────────────────────────
    if sub in ("", "list"):
        teams = list_teams()
        console.print()
        if not teams:
            console.print("  [dim]No hay equipos de agentes creados.[/dim]")
            console.print("  [dim]Usa[/dim] [cyan]/agent team create <id> <lead> <miembros>[/cyan]")
            console.print()
            return
        t = Table(box=rbox.SIMPLE, show_header=True, padding=(0, 1))
        t.add_column("ID",       style="bold cyan", width=28)
        t.add_column("Lead",     style="white",      width=12)
        t.add_column("Miembros", style="dim",         width=24)
        t.add_column("Estado",   style="bold",        width=12)
        t.add_column("Subtasks", style="dim",         width=10, justify="right")
        for team in teams:
            col  = STATUS_STYLE.get(team["status"], "dim")
            icon = STATUS_ICON.get(team["status"], "·")
            pending_str = f"[yellow]{team['pending']} pendientes[/yellow]" if team["pending"] else "—"
            t.add_row(
                team["team_id"],
                team["lead"],
                ", ".join(team["members"]),
                f"[{col}]{icon} {team['status']}[/{col}]",
                f"{team['subtasks']} ({pending_str})",
            )
        console.print(t)
        console.print("  [dim]→  /agent team <id>  ·  /agent team run <id>  ·  /agent team delete <id>[/dim]")
        console.print()
        return

    # ── create <id> <lead> <members> ─────────────────────────────────────────
    if sub == "create":
        cparts = rest.strip().split(maxsplit=2)
        if len(cparts) < 2:
            console.print("  [yellow]Uso:[/yellow]  /agent team create <id> <lead> [miembro1,miembro2]")
            return
        team_id = cparts[0]
        lead    = cparts[1]
        members = [m.strip() for m in cparts[2].split(",")] if len(cparts) > 2 else [lead]
        valid   = [a.id for a in config.agents]
        bad     = [m for m in [lead] + members if m not in valid]
        if bad:
            console.print(
                f"  [red]✗[/red]  Agentes desconocidos: {', '.join(bad)}\n"
                f"  [dim]Disponibles: {', '.join(valid)}[/dim]"
            )
            return
        create_team(team_id, lead, list(dict.fromkeys([lead] + members)))
        console.print(
            f"  [green]✓[/green]  Equipo [bold cyan]{team_id}[/bold cyan] creado.\n"
            f"  [dim]Lead: {lead} | Miembros: {', '.join(members)}[/dim]\n"
            f"  [dim]→  /agent team add {team_id} <tarea> <agente>[/dim]"
        )
        return

    # ── add <id> <tarea> <agente> ─────────────────────────────────────────────
    if sub == "add":
        aparts = rest.strip().split(maxsplit=2)
        if len(aparts) < 3:
            console.print("  [yellow]Uso:[/yellow]  /agent team add <id> <descripción tarea> <agente>")
            return
        team_id, description, assignee = aparts[0], aparts[1], aparts[2]
        result = _add_subtask(team_id, description, assignee)
        if "error" in result:
            console.print(f"  [red]✗[/red]  {result['error']}")
            return
        console.print(
            f"  [green]✓[/green]  Subtask [bold cyan]{result['id']}[/bold cyan] añadida.\n"
            f"  [dim]→ {description} [asignada: {assignee}][/dim]"
        )
        return

    # ── done <id> <subtask_id> [resultado] ───────────────────────────────────
    if sub == "done":
        dparts = rest.strip().split(maxsplit=2)
        if len(dparts) < 2:
            console.print("  [yellow]Uso:[/yellow]  /agent team done <team-id> <subtask-id> [resultado]")
            return
        team_id   = dparts[0]
        subtask_id = dparts[1]
        result_str = dparts[2] if len(dparts) > 2 else "completado manualmente"
        r = _complete_subtask(team_id, subtask_id, result_str)
        if "error" in r:
            console.print(f"  [red]✗[/red]  {r['error']}")
            return
        console.print(f"  [green]✓[/green]  Subtask [bold cyan]{subtask_id}[/bold cyan] completada.")
        return

    # ── run <id> ──────────────────────────────────────────────────────────────
    if sub == "run":
        team_id = rest.strip().split()[0] if rest.strip() else ""
        if not team_id:
            console.print("  [yellow]Uso:[/yellow]  /agent team run <id>")
            return
        runner = getattr(agent_loop, "subagent_runner", None) if agent_loop else None
        if runner is None:
            console.print("  [red]✗[/red]  SubAgentRunner no disponible en este contexto.")
            return
        from agent.tasks import _load_team_obj as _lt
        team = _lt(team_id)
        if team is None:
            console.print(f"  [red]✗[/red]  Equipo [bold]{team_id}[/bold] no encontrado.")
            return
        pending = team.get_pending_subtasks()
        if not pending:
            console.print(f"  [dim]Equipo [bold]{team_id}[/bold] no tiene subtasks pendientes.[/dim]")
            return
        console.print(
            f"  [bold cyan]⚡  Ejecutando equipo {team_id}[/bold cyan]  "
            f"[dim]{len(pending)} subtask(s) pendiente(s)[/dim]"
        )
        results = team.execute(runner)
        console.print()
        for st_id, res in results.items():
            icon = "[red]✗[/red]" if res.startswith("[error]") else "[green]✓[/green]"
            preview = res[:80].strip()
            console.print(f"  {icon}  [dim]{st_id}[/dim]  {preview}")
        console.print()
        return

    # ── delete <id> ──────────────────────────────────────────────────────────
    if sub == "delete":
        team_id = rest.strip().split()[0] if rest.strip() else ""
        if not team_id:
            console.print("  [yellow]Uso:[/yellow]  /agent team delete <id>")
            return
        if delete_team(team_id):
            console.print(f"  [green]✓[/green]  Equipo [bold cyan]{team_id}[/bold cyan] eliminado.")
        else:
            console.print(f"  [red]✗[/red]  Equipo [bold]{team_id}[/bold] no encontrado.")
        return

    # ── <id> → detalle del equipo ─────────────────────────────────────────────
    status_data = get_team_status(sub)
    if "error" in status_data:
        console.print(f"  [red]✗[/red]  {status_data['error']}")
        console.print("  [dim]Subcomandos disponibles: list | create | add | done | run | delete[/dim]")
        return

    team_data = load_team(sub)
    col  = STATUS_STYLE.get(status_data["status"], "dim")
    icon = STATUS_ICON.get(status_data["status"], "·")
    console.print()
    console.print(
        f"  [bold cyan]{sub}[/bold cyan]  "
        f"[{col}]{icon} {status_data['status']}[/{col}]"
    )
    console.print(f"  [dim]Lead:[/dim] {status_data['lead']}  [dim]Miembros:[/dim] {', '.join(status_data['members'])}")
    console.print(
        f"  [dim]Subtasks:[/dim] {status_data['completed_subtasks']} completadas / "
        f"[yellow]{status_data['pending_subtasks']} pendientes[/yellow]"
    )

    if team_data and team_data.get("subtasks"):
        console.print()
        t = Table(box=rbox.SIMPLE, show_header=True, padding=(0, 1))
        t.add_column("ID",       style="bold cyan", width=10)
        t.add_column("Agente",   style="white",      width=12)
        t.add_column("Estado",   style="bold",        width=12)
        t.add_column("Tarea",    style="dim",         width=50)
        for st in team_data["subtasks"]:
            sc   = STATUS_STYLE.get(st["status"], "dim")
            si   = STATUS_ICON.get(st["status"], "·")
            task = st["description"]
            t.add_row(st["id"], st.get("assign_to", "?"), f"[{sc}]{si} {st['status']}[/{sc}]", task)
        console.print(t)

    if status_data["pending_subtasks"] > 0:
        console.print(f"  [dim]→  /agent team run {sub}  para ejecutar subtasks pendientes[/dim]")
    console.print()


def _detect_input_types(minfo: dict, model_name: str) -> list[str]:
    """Detecta los tipos de input soportados por el modelo.

    Indicadores de visión en ollama.show():
    - modelinfo keys con '.vision.' o '*image_token_id'  → visor de imágenes integrado
    - modelinfo keys con 'clip.' o 'projector.'          → proyector visual (LLaVA-style)
    - modelinfo keys con 'mllama.'                       → Llama 3.2 Vision
    - details.families con 'clip', 'llava', 'mllama'…
    - nombre del modelo con keywords de visión
    """
    modelinfo = minfo.get("modelinfo", {})
    details   = minfo.get("details", {})

    for k in modelinfo:
        kl = k.lower()
        if (
            ".vision." in kl
            or kl.endswith("image_token_id")
            or kl.endswith("vision_start_token_id")
            or kl.endswith("vision_end_token_id")
            or "clip." in kl
            or "projector." in kl
            or kl.startswith("mllama.")
        ):
            return ["text", "image"]

    families = details.get("families") or []
    if isinstance(families, list):
        for f in families:
            if any(kw in f.lower() for kw in ("clip", "llava", "mllama", "minicpm", "moondream")):
                return ["text", "image"]

    family = (details.get("family") or "").lower()
    if any(kw in family for kw in ("llava", "clip", "mllama")):
        return ["text", "image"]

    _VISION_KEYWORDS = (
        "llava", "-vl", ":vl", "vision", "moondream",
        "minicpm-v", "bakllava", "llava-phi", "qwen-vl",
    )
    if any(kw in model_name.lower() for kw in _VISION_KEYWORDS):
        return ["text", "image"]

    return ["text"]


def _auto_detect_model_config(config, model_name: str) -> None:
    """Detecta contextWindow, maxTokens e input types vía ollama.show().

    Solo aplica al backend Ollama: openai/anthropic no exponen estos metadatos por
    ese protocolo. Para esos backends se sugiere configurar contextWindow/maxTokens
    manualmente (models.configs en oocode.json o /model timeout para el timeout).
    """
    if getattr(config, "api_type", "ollama") != "ollama":
        console.print(
            f"  [dim]Backend [cyan]{config.api_type}[/cyan]: sin autodetección de parámetros.  "
            f"Configura contextWindow/maxTokens en models.configs si hace falta.[/dim]"
        )
        return
    console.print(f"  [dim]Detectando parámetros de {model_name}…[/dim]")
    minfo    = _fetch_model_info(config, model_name)
    modelinfo = minfo.get("modelinfo", {})
    details   = minfo.get("details", {})
    mparams   = minfo.get("params", {})

    # contextWindow — buscar en modelinfo ("*.context_length")
    ctx_win: int | None = None
    for k, v in modelinfo.items():
        if "context_length" in k.lower():
            try:
                ctx_win = int(v)
                break
            except (ValueError, TypeError):
                pass

    # Fallback: num_ctx del Modelfile
    if ctx_win is None and "num_ctx" in mparams:
        try:
            ctx_win = int(mparams["num_ctx"])
        except (ValueError, TypeError):
            pass

    if ctx_win is None:
        console.print("  [dim yellow]No se detectó context_length — usando valores globales[/dim yellow]")
        return

    # maxTokens — heurística por número de parámetros
    param_size = (details.get("parameter_size") or "").lower()
    try:
        n_b = float(param_size.replace("b", "").strip())
    except ValueError:
        n_b = 0.0
    if n_b > 0:
        if n_b <= 5:
            max_tok = min(ctx_win // 8, 8192)
        elif n_b <= 10:
            max_tok = min(ctx_win // 4, 16384)
        else:
            max_tok = min(ctx_win // 4, 32768)
    else:
        max_tok = min(ctx_win // 4, 16384)
    max_tok = max(max_tok, 2048)

    # Extraer parámetros numéricos del Modelfile para guardarlos per-modelo
    _FLOAT_KEYS = {"temperature", "top_p", "repeat_penalty"}
    _INT_KEYS   = {"top_k", "num_predict", "seed"}
    extra: dict = {}
    for key, raw_val in mparams.items():
        if key in _FLOAT_KEYS:
            try:
                extra[key] = float(raw_val)
            except (ValueError, TypeError):
                pass
        elif key in _INT_KEYS:
            try:
                extra[key] = int(raw_val)
            except (ValueError, TypeError):
                pass

    # Detectar tipos de input (text / image)
    input_types = _detect_input_types(minfo, model_name)

    config.set_model_config(model_name, ctx_win, max_tok, extra_params=extra,
                            input_types=input_types)
    # Añadir timeoutSeconds si no existe aún (hereda del fallback global como default)
    if "timeoutSeconds" not in config.model_configs.get(model_name, {}):
        config.model_configs[model_name]["timeoutSeconds"] = config.fallback_timeout
    config.save()
    hist_tok    = config.effective_max_context_tokens
    final_params = config.model_configs[model_name].get("params", {})
    param_str   = "  ".join(
        f"{k}: {v}" for k, v in final_params.items() if k != "num_ctx"
    )
    input_str = ", ".join(input_types)
    console.print(
        f"  [green]✓[/green]  [dim]contextWindow: [white]{ctx_win:,}[/white]"
        f"  maxTokens: [white]{max_tok:,}[/white]"
        f"  →  historial: [white]{hist_tok:,}[/white] tokens"
        f"  ·  input: [white]{input_str}[/white][/dim]"
    )
    if param_str:
        console.print(f"  [dim]params: {param_str}[/dim]")


def _cmd_model(args: str, config, agent_loop=None) -> None:
    # ── /model fallback [nombre] ───────────────────────────────────────────────
    if args.lower().startswith("fallback"):
        fb_arg = args[len("fallback"):].strip()
        if fb_arg:
            # Configurar modelo fallback y auto-detectar su config
            config.fallback_model   = fb_arg
            config.fallback_enabled = True
            console.print(
                f"  [green]✓[/green]  Fallback → [bold cyan]{fb_arg}[/bold cyan]"
                f"  [dim](timeout: {config.fallback_timeout}s)[/dim]"
            )
            _auto_detect_model_config(config, fb_arg)
            config.save()
            # Mostrar la config detectada
            fb_cfg = config.model_configs.get(fb_arg, {})
            if fb_cfg:
                ctx_w = fb_cfg.get("contextWindow", "—")
                max_t = fb_cfg.get("maxTokens", "—")
                overhead = config.model_system_overhead
                hist = max(ctx_w - max_t - overhead, 2000) if isinstance(ctx_w, int) else "—"
                console.print(
                    f"  [dim]contextWindow: {ctx_w:,}  maxTokens: {max_t:,}"
                    f"  →  historial: {hist:,} tokens[/dim]"
                    if isinstance(hist, int) else
                    f"  [dim]contextWindow: {ctx_w}  maxTokens: {max_t}[/dim]"
                )
        else:
            # Sin nombre: mostrar info del fallback actual
            fb = config.fallback_model
            if not fb:
                console.print(
                    "  [dim]Sin modelo fallback configurado.[/dim]  "
                    "[dim]Usa[/dim] [cyan]/model fallback <nombre>[/cyan] [dim]para activarlo.[/dim]"
                )
            else:
                estado = "[green]activo[/green]" if config.fallback_active_config else "[yellow]desactivado[/yellow]"
                console.print(f"  Fallback: [bold cyan]{fb}[/bold cyan]  ({estado})")
                fb_cfg = config.model_configs.get(fb, {})
                if fb_cfg:
                    ctx_w = fb_cfg.get("contextWindow", "—")
                    max_t = fb_cfg.get("maxTokens", "—")
                    console.print(
                        f"  [dim]contextWindow: {ctx_w}  maxTokens: {max_t}"
                        f"  timeout: {config.fallback_timeout}s[/dim]"
                    )
                else:
                    console.print(
                        f"  [yellow]⚠[/yellow]  [dim]Sin config detectada — "
                        f"ejecuta /model fallback {fb} para detectar.[/dim]"
                    )
        return

    # ── /model timeout [segundos] ────────────────────────────────────────────────
    if args.lower().startswith("timeout"):
        timeout_arg = args[len("timeout"):].strip()
        model = config.model
        if not model:
            console.print("  [red]No hay modelo activo.[/red]  Usa /model <nombre> primero.")
            return
        if timeout_arg:
            try:
                secs = int(timeout_arg)
                if model not in config.model_configs:
                    config.model_configs[model] = {}
                config.model_configs[model]["timeoutSeconds"] = secs
                config.save()
                console.print(
                    f"  [green]✓[/green]  timeout de [cyan]{model}[/cyan] → [bold]{secs}s[/bold]  "
                    f"[dim](0 = sin timeout)[/dim]"
                )
            except ValueError:
                console.print(f"  [red]Valor inválido:[/red] usa un entero (p.ej. /model timeout 120)")
        else:
            t = config.model_configs.get(model, {}).get("timeoutSeconds")
            if t is None:
                console.print(
                    f"  [dim]timeout de [cyan]{model}[/cyan]: no configurado  "
                    f"(usa /model timeout <segundos>)[/dim]"
                )
            else:
                console.print(
                    f"  timeout de [cyan]{model}[/cyan]: [bold]{t}s[/bold]  "
                    f"[dim](0 = sin timeout)[/dim]"
                )
        return

    # ── /model <nombre> ────────────────────────────────────────────────────────
    if args:
        config.model = args
        if agent_loop:
            agent_loop.session.log_model_change(args)
        console.print(f"  [green]✓[/green]  Modelo → [bold cyan]{config.model}[/bold cyan]")
        _auto_detect_model_config(config, args)
        # Actualizar límite de contexto del loop activo sin reiniciar sesión
        if agent_loop and config.effective_context_window:
            agent_loop.context.max_tokens = config.effective_max_context_tokens
            console.print(
                f"  [dim]Contexto ajustado a {agent_loop.context.max_tokens:,} tokens[/dim]"
            )
        # Cargar preferencias de razonamiento guardadas para el nuevo modelo
        if agent_loop and hasattr(agent_loop, "rt") and agent_loop.rt:
            tl, r = config.get_model_thinking(args)
            agent_loop.rt.think_level = tl
            agent_loop.rt.reasoning   = r
            if tl != "off" or r:
                console.print(
                    f"  [dim]Think: [bold]{tl}[/bold]  "
                    f"Reasoning: {'[bold cyan]on[/bold cyan]' if r else 'off'}[/dim]"
                )
        return

    # ── /model (sin args): mostrar info del modelo activo + fallback ───────────
    model_name = config.model or "(ninguno)"
    cfg = config.active_model_config
    _api_type = getattr(config, "api_type", "ollama")
    console.print()
    _backend_note = "" if _api_type == "ollama" else f"  [dim](backend: {_api_type})[/dim]"
    console.print(f"  [bold]Modelo principal:[/bold]  [bold cyan]{model_name}[/bold cyan]{_backend_note}")
    if cfg:
        ctx_w      = cfg.get("contextWindow", "—")
        max_t      = cfg.get("maxTokens", "—")
        hist       = config.effective_max_context_tokens
        inp_types  = ", ".join(cfg.get("input", ["text"]))
        inp_icon   = "🖼 " if "image" in cfg.get("input", []) else ""
        console.print(
            f"  [dim]contextWindow: {ctx_w:,}  maxTokens: {max_t:,}"
            f"  →  historial: {hist:,} tokens"
            f"  ·  input: {inp_icon}{inp_types}[/dim]"
        )
    else:
        console.print(f"  [dim](Sin config detectada — usa /model {model_name} para detectar)[/dim]")

    fb = config.fallback_model
    if fb:
        estado = "[green]⚡ activo[/green]" if config.fallback_active_config else "[yellow]desactivado[/yellow]"
        console.print()
        console.print(f"  [bold]Modelo fallback:[/bold]  [bold cyan]{fb}[/bold cyan]  ({estado})")
        fb_cfg = config.model_configs.get(fb, {})
        if fb_cfg:
            ctx_w = fb_cfg.get("contextWindow", "—")
            max_t = fb_cfg.get("maxTokens", "—")
            console.print(
                f"  [dim]contextWindow: {ctx_w}  maxTokens: {max_t}"
                f"  timeout: {config.fallback_timeout}s[/dim]"
            )
        else:
            console.print(
                f"  [yellow]⚠[/yellow]  [dim]Sin config detectada — "
                f"ejecuta /model fallback {fb} para detectar.[/dim]"
            )
    else:
        console.print()
        console.print(
            "  [dim]Sin fallback configurado.  "
            "Usa[/dim] [cyan]/model fallback <nombre>[/cyan] [dim]para activarlo.[/dim]"
        )
    console.print()


def _cmd_models(config, agent_loop=None) -> None:
    # /models lista modelos del servidor Ollama; openai/anthropic no exponen listado.
    if getattr(config, "api_type", "ollama") != "ollama":
        console.print(
            f"  [yellow]/models solo está disponible con el backend Ollama.[/yellow]\n"
            f"  [dim]Backend actual: [cyan]{config.api_type}[/cyan].  "
            f"Usa[/dim] [cyan]/model <nombre>[/cyan] [dim]para fijar el modelo manualmente.[/dim]"
        )
        return
    try:
        from api.ollama import list_ollama_models
        model_list = list_ollama_models(config.ollama_host)
        if not model_list:
            console.print("  [yellow]No hay modelos en el servidor Ollama.[/yellow]")
            return
        print_model_selector(model_list)
        choice = _tui_ask("Nombre del modelo (Enter para cancelar)", default="")
        if choice.strip():
            config.model = choice.strip()
            if agent_loop:
                agent_loop.session.log_model_change(choice.strip())
            console.print(f"  [green]✓[/green]  Modelo → [bold cyan]{config.model}[/bold cyan]")
            # Auto-detectar contextWindow, maxTokens y params del modelo seleccionado
            _auto_detect_model_config(config, choice.strip())
            # Actualizar contexto del loop activo sin reiniciar sesión
            if agent_loop and config.effective_context_window:
                agent_loop.context.max_tokens = config.effective_max_context_tokens
                console.print(
                    f"  [dim]Contexto ajustado a {agent_loop.context.max_tokens:,} tokens[/dim]"
                )
    except Exception as e:
        console.print(f"  [red]✗[/red]  Error listando modelos: {e}")


def _cmd_workspace(args: str, config, agent_loop) -> None:
    if args:
        new_ws = str(Path(args).expanduser().resolve())
        config.workspace = new_ws
        config.save()
        from workspace.manager import WorkspaceManager
        agent_loop.ws = WorkspaceManager(
            new_ws,
            config.agent_name,
            config.agent_emoji,
            ollama_host=config.ollama_host,
            permissions=config.permissions,
            max_memory_lines=config.ws_max_memory_lines,
            max_daily_chars=config.ws_max_daily_chars,
        )
        if not agent_loop.ws.exists():
            created = agent_loop.ws.init()
            console.print(f"  [green]✓[/green]  Workspace creado: {', '.join(created)}")
        console.print(f"  [green]✓[/green]  Workspace → [bold]{new_ws}[/bold]")
    else:
        console.print(f"  Workspace: [bold]{config.workspace}[/bold]")


def _cmd_spawn(args: str, agent_loop, config) -> None:
    """Alias de /subagents spawn."""
    _cmd_subagents(f"spawn {args}" if args else "spawn", agent_loop, config)


def _fmt_ago(seconds: float) -> str:
    """Formatea 'hace N unidades' para tiempo transcurrido."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds/60:.0f}m"
    return f"{int(seconds/3600)}h"


def _subagent_status_table(s) -> None:
    """Muestra info detallada de un subagente en una tabla compacta."""
    from rich.table import Table
    from rich import box as rbox

    STATUS_STYLE = {"running": "bold green", "done": "dim", "killed": "bold yellow", "error": "bold red"}
    STATUS_ICON  = {"running": "⚡", "done": "✓", "killed": "↯", "error": "✗"}
    col  = STATUS_STYLE.get(s.status, "dim")
    icon = STATUS_ICON.get(s.status, "·")

    duration = f"{s.elapsed():.1f}s"
    if s.finished_at is not None:
        ago = _fmt_ago(s.finished_ago() or 0)
        time_str = f"{duration}  [dim](hace {ago})[/dim]"
    else:
        time_str = f"{duration}  [dim](en curso)[/dim]"

    rows = [
        ("ID",      s.run_id),
        ("Agente",  f"{s.agent_emoji} {s.agent_name}  [dim]({s.agent_id})[/dim]"),
        ("Estado",  f"[{col}]{icon} {s.status}[/{col}]"),
        ("Tiempo",  time_str),
        ("Tarea",   s.task),
    ]
    if s.steer_count > 0:
        rows.append(("Steers", f"{s.steer_count} instrucción(es) enviada(s)"))
    if s.error:
        rows.append(("Error", f"[red]{s.error}[/red]"))
    if s.result and s.status != "running":
        preview = s.result[:120].strip()
        if len(s.result) > 120:
            preview += "…"
        rows.append(("Resultado", f"[dim]{preview}[/dim]"))

    t = Table(box=rbox.SIMPLE, show_header=False, padding=(0, 1))
    t.add_column("k", style="dim", width=10)
    t.add_column("v", style="white")
    for k, v in rows:
        t.add_row(k, v)
    console.print(t)


def _cmd_subagents(args: str, agent_loop, config) -> None:
    """Gestión de subagentes: spawn, list, status, steer, kill, output."""
    from agent.subagent import list_running, list_recent, get_by_prefix
    from rich.markdown import Markdown as _Markdown
    from rich.table import Table
    from rich import box as rbox

    runner = agent_loop.subagent_runner

    parts = args.strip().split(maxsplit=2) if args.strip() else []
    sub   = parts[0].lower() if parts else "list"

    # ── /subagents spawn <id> <tarea> ─────────────────────────────────────────
    if sub == "spawn":
        spawn_args = " ".join(parts[1:]) if len(parts) > 1 else ""
        if not spawn_args:
            console.print("  [yellow]Uso:[/yellow]  /subagents spawn <agent-id> <tarea>")
            print_agents(config.agents, config.agent_id)
            return
        spawn_parts = spawn_args.split(maxsplit=1)
        if len(spawn_parts) < 2:
            console.print("  [yellow]Uso:[/yellow]  /subagents spawn <agent-id> <tarea>")
            return
        agent_id, task = spawn_parts[0], spawn_parts[1]
        valid_ids = [a.id for a in config.agents]
        if agent_id not in valid_ids:
            console.print(
                f"  [red]✗[/red]  Agente [bold]{agent_id}[/bold] no existe. "
                f"Disponibles: {', '.join(valid_ids)}"
            )
            return
        target = next(a for a in config.agents if a.id == agent_id)
        print_spawn_header(target.name, target.emoji, task)
        if runner is None:
            console.print("  [red]✗[/red]  Subagentes no disponibles en este contexto.")
            return
        result = runner.run(agent_id, task, silent=True)
        print_spawn_footer(target.name)
        if result:
            console.print(_Markdown(result))
        return

    # ── /subagents  o  /subagents list ────────────────────────────────────────
    if sub in ("", "list"):
        running = list_running()
        recent  = list_recent()
        console.print()

        STATUS_STYLE = {"running": "bold green", "done": "dim", "killed": "bold yellow", "error": "bold red"}
        STATUS_ICON  = {"running": "⚡", "done": "✓", "killed": "↯", "error": "✗"}

        if not running and not recent:
            console.print("  [dim]No hay subagentes activos ni recientes.[/dim]")
            console.print(
                "  [dim]Usa[/dim] [cyan]/subagents spawn <id> <tarea>[/cyan] "
                "[dim]o pide al agente que lance uno con[/dim] spawn_subagent."
            )
            console.print()
            return

        # ── Activos ──────────────────────────────────────────────────────────
        if running:
            console.print("  [bold green]⚡  Subagentes activos[/bold green]")
            t = Table(box=rbox.SIMPLE, show_header=True, padding=(0, 1))
            t.add_column("ID",      style="bold cyan",  width=8)
            t.add_column("Agente",  style="white",       width=16)
            t.add_column("Elapsed", style="dim",         width=8,  justify="right")
            t.add_column("Steers",  style="dim",         width=7,  justify="right")
            t.add_column("Tarea",   style="dim",         width=52)
            for s in running:
                t.add_row(
                    s.short_id(),
                    f"{s.agent_emoji} {s.agent_name}",
                    f"{s.elapsed():.0f}s",
                    str(s.steer_count) if s.steer_count else "—",
                    s.task,
                )
            console.print(t)

        # ── Recientes (últimos 30 min) ────────────────────────────────────────
        if recent:
            label = "  [dim]Recientes (últimos 30 min)[/dim]"
            if running:
                console.print()
            console.print(label)
            t2 = Table(box=rbox.SIMPLE, show_header=True, padding=(0, 1))
            t2.add_column("ID",       style="bold cyan",  width=8)
            t2.add_column("Agente",   style="white",       width=16)
            t2.add_column("Estado",   style="bold",        width=12)
            t2.add_column("Duración", style="dim",         width=9,  justify="right")
            t2.add_column("Hace",     style="dim",         width=6,  justify="right")
            t2.add_column("Tarea",    style="dim",         width=40)
            for s in recent:
                col  = STATUS_STYLE.get(s.status, "dim")
                icon = STATUS_ICON.get(s.status, "·")
                ago  = _fmt_ago(s.finished_ago() or 0)
                t2.add_row(
                    s.short_id(),
                    f"{s.agent_emoji} {s.agent_name}",
                    f"[{col}]{icon} {s.status}[/{col}]",
                    f"{s.elapsed():.0f}s",
                    ago,
                    s.task,
                )
            console.print(t2)

        console.print(
            "  [dim]→  /subagents status <id>  ·  "
            "/subagents steer <id> <instrucción>  ·  "
            "/subagents kill <id|all>  ·  "
            "/subagents output <id>[/dim]"
        )
        console.print()
        return

    # ── /subagents status <id> ────────────────────────────────────────────────
    if sub == "status":
        run_id_prefix = parts[1] if len(parts) > 1 else ""
        if not run_id_prefix:
            # Sin ID: mostrar resumen de todos
            running = list_running()
            recent  = list_recent()
            if not running and not recent:
                console.print("  [dim]No hay subagentes activos ni recientes.[/dim]")
            for s in running + recent:
                console.print()
                console.print(f"  [bold cyan]{s.agent_emoji} {s.agent_name}[/bold cyan]  [dim]{s.short_id()}[/dim]")
                _subagent_status_table(s)
            return
        s = get_by_prefix(run_id_prefix)
        if s is None:
            console.print(f"  [red]✗[/red]  Subagente [bold]{run_id_prefix}[/bold] no encontrado.")
            return
        console.print()
        console.print(
            f"  [bold cyan]{s.agent_emoji} {s.agent_name}[/bold cyan]"
            f"  [dim]{s.run_id}[/dim]"
        )
        _subagent_status_table(s)
        if s.status == "running":
            console.print(
                f"  [dim]→  /subagents steer {s.short_id()} <instrucción>  ·  "
                f"/subagents kill {s.short_id()}  ·  "
                f"/subagents output {s.short_id()}[/dim]"
            )
        console.print()
        return

    # ── /subagents steer <id> <instrucción> ───────────────────────────────────
    if sub == "steer":
        if len(parts) < 3:
            console.print("  [yellow]Uso:[/yellow]  /subagents steer <id> <nueva instrucción>")
            return
        run_id_prefix = parts[1]
        instruction   = parts[2]
        if runner is None:
            console.print("  [red]✗[/red]  SubAgentRunner no disponible.")
            return
        s = get_by_prefix(run_id_prefix)
        if s is None or s.status != "running":
            console.print(
                f"  [red]✗[/red]  Subagente [bold]{run_id_prefix}[/bold] "
                f"{'no activo (status: ' + s.status + ')' if s else 'no encontrado'}."
            )
            return
        runner.steer(run_id_prefix, instruction)
        console.print(
            f"  [green]✓[/green]  Steer #{s.steer_count} → [bold cyan]{s.short_id()}[/bold cyan]"
            f"  [dim]{s.agent_emoji} {s.agent_name}[/dim]"
        )
        console.print(f"  [dim]↳ {instruction}[/dim]")
        console.print(f"  [dim]El subagente procesará la instrucción en el próximo ciclo.[/dim]")
        return

    # ── /subagents kill <id|all> ───────────────────────────────────────────────
    if sub == "kill":
        if runner is None:
            console.print("  [red]✗[/red]  SubAgentRunner no disponible.")
            return
        target = parts[1] if len(parts) > 1 else ""
        if target.lower() == "all":
            n = runner.kill_all()
            console.print(f"  [yellow]↯[/yellow]  {n} subagente(s) detenido(s).")
        elif target:
            if runner.kill(target):
                console.print(f"  [yellow]↯[/yellow]  Subagente [bold]{target}[/bold] detenido.")
            else:
                console.print(f"  [red]✗[/red]  Subagente [bold]{target}[/bold] no encontrado o ya terminado.")
        else:
            console.print("  [yellow]Uso:[/yellow]  /subagents kill <id|all>")
        return

    # ── /subagents output <id> ────────────────────────────────────────────────
    if sub == "output":
        run_id_prefix = parts[1] if len(parts) > 1 else ""
        if not run_id_prefix:
            console.print("  [yellow]Uso:[/yellow]  /subagents output <id>")
            return
        s = get_by_prefix(run_id_prefix)
        if s is None:
            console.print(f"  [red]✗[/red]  Subagente [bold]{run_id_prefix}[/bold] no encontrado.")
            return
        console.print()
        console.rule(
            f"[bold cyan]{s.agent_emoji} {s.agent_name}[/bold cyan]"
            f"  [dim]{s.short_id()}  ·  {s.status}  ·  {s.elapsed():.0f}s[/dim]",
            style="cyan dim",
        )
        if s.result:
            from rich.markdown import Markdown
            from rich.padding import Padding
            console.print(Padding(Markdown(s.result), (0, 0, 0, 2)))
        else:
            console.print("  [dim](en ejecución — sin resultado todavía)[/dim]")
        console.print()
        return

    # ── /subagents <id> → alias de status <id> ────────────────────────────────
    s = get_by_prefix(sub)
    if s is not None:
        console.print()
        console.print(
            f"  [bold cyan]{s.agent_emoji} {s.agent_name}[/bold cyan]"
            f"  [dim]{s.run_id}[/dim]"
        )
        _subagent_status_table(s)
        if s.status == "running":
            console.print(
                f"  [dim]→  /subagents steer {s.short_id()} <instrucción>  ·  "
                f"/subagents kill {s.short_id()}[/dim]"
            )
        console.print()
    else:
        console.print(
            f"  [red]✗[/red]  Subcomando o ID desconocido: [bold]{sub}[/bold]\n"
            "  [dim]Uso:[/dim]  /subagents [list | status <id> | steer <id> <instr>"
            " | kill <id|all> | output <id>]"
        )


def _cmd_crestodian(args: str, agent_loop, config) -> None:
    """Gestor del workspace: muestra y permite editar ficheros de identidad."""
    from workspace.manager import WORKSPACE_FILES
    ws_path = Path(config.workspace).expanduser()

    if not args:
        console.print()
        console.print(f"  [bold cyan]Workspace:[/bold cyan] {config.workspace}")
        console.print()
        for fname in WORKSPACE_FILES:
            fpath = ws_path / fname
            exists = fpath.exists()
            size = fpath.stat().st_size if exists else 0
            status = f"[green]{size} bytes[/green]" if exists else "[red]falta[/red]"
            console.print(f"  {'[cyan]●[/cyan]' if exists else '[dim]○[/dim]'}  [white]{fname:<16}[/white]  {status}")
        console.print()
        console.print(
            "  [dim]Usa[/dim] [cyan]/crestodian <fichero>[/cyan] [dim]para editar.[/dim]  "
            "[dim]O pide al agente que lo actualice.[/dim]"
        )
        return

    target = args.strip().upper()
    if not target.endswith(".MD"):
        target += ".MD"
    fpath = ws_path / target
    if not fpath.exists():
        console.print(f"  [red]✗[/red]  {target} no existe en el workspace.")
        return
    agent_loop.run(
        f"El usuario quiere revisar y actualizar el fichero de workspace '{target}' "
        f"ubicado en '{fpath}'. Lee su contenido actual con read_file, "
        f"luego pregunta qué cambios quiere hacer y aplícalos con edit_file o write_file."
    )


# ── /resume ──────────────────────────────────────────────────────────────────

def _cmd_resume(agent_loop) -> None:
    """Resume el contexto actual con el LLM y limpia los mensajes conservando el resumen."""
    ctx = agent_loop.context
    if not ctx.messages:
        console.print("  [dim]Contexto vacío, nada que resumir.[/dim]")
        return
    console.print("  [dim cyan]Resumiendo conversación…[/dim cyan]")
    try:
        summary = agent_loop._summarize_messages(ctx.messages)
        if not summary:
            console.print("  [yellow]⚠[/yellow]  El modelo no generó resumen.")
            return
        ctx.summary = (
            f"{ctx.summary}\n\n{summary}".strip() if ctx.summary else summary
        )
        if len(ctx.summary) > ctx.max_summary_chars:
            ctx.summary = ctx.summary[-ctx.max_summary_chars:]
        ctx.messages.clear()
        console.print("  [green]✓[/green]  Conversación resumida y contexto limpiado.")
        console.print(f"  [dim]{summary}[/dim]")
        console.print("  [dim](El resumen se inyecta en el próximo turno)[/dim]")
    except Exception as e:
        console.print(f"  [red]✗[/red]  Error: {e}")


# ── /branch ───────────────────────────────────────────────────────────────────

def _cmd_branch(args: str, agent_loop) -> None:
    if agent_loop.branches is None:
        console.print("  [red]✗[/red]  BranchManager no inicializado.")
        return
    parts = args.split(maxsplit=1)
    sub   = parts[0].lower() if parts else ""
    name  = parts[1].strip() if len(parts) > 1 else ""

    if sub in ("", "list"):
        print_branches(agent_loop.branches.all_branches(), len(agent_loop.context.messages))
    elif sub == "save":
        if not name:
            console.print("  [yellow]Uso:[/yellow]  /branch save <nombre>")
            return
        agent_loop.branches.save(
            name,
            list(agent_loop.context.messages),
            agent_loop.context.summary,
        )
        console.print(
            f"  [green]✓[/green]  Rama [cyan]{name}[/cyan] guardada "
            f"— {len(agent_loop.context.messages)} mensajes."
        )
    elif sub == "load":
        if not name:
            console.print("  [yellow]Uso:[/yellow]  /branch load <nombre>")
            return
        data = agent_loop.branches.load(name)
        if not data:
            console.print(f"  [red]✗[/red]  Rama [bold]{name}[/bold] no encontrada.")
            return
        agent_loop.context.messages = data["messages"]
        agent_loop.context.summary  = data.get("summary", "")
        console.print(
            f"  [green]✓[/green]  Rama [cyan]{name}[/cyan] restaurada "
            f"— {len(agent_loop.context.messages)} mensajes en contexto."
        )
    elif sub == "rm":
        if not name:
            console.print("  [yellow]Uso:[/yellow]  /branch rm <nombre>")
            return
        if agent_loop.branches.delete(name):
            console.print(f"  [green]✓[/green]  Rama [cyan]{name}[/cyan] eliminada.")
        else:
            console.print(f"  [red]✗[/red]  Rama [bold]{name}[/bold] no encontrada.")
    else:
        console.print(
            "  [dim]Subcomandos: list · save <nombre> · load <nombre> · rm <nombre>[/dim]"
        )


# ── /copy ─────────────────────────────────────────────────────────────────────

def _cmd_copy(args: str, agent_loop) -> None:
    text = agent_loop._last_response
    if not text:
        console.print("  [dim]Sin respuesta para copiar.[/dim]")
        return
    if _copy_to_clipboard(text):
        preview = text[:80].replace("\n", " ")
        console.print(
            f"  [green]✓[/green]  Copiado al portapapeles  "
            f"[dim]({len(text)} chars)[/dim]\n"
            f"  [dim]{preview}{'…' if len(text) > 80 else ''}[/dim]"
        )
    else:
        console.print(
            "  [yellow]⚠[/yellow]  No se pudo acceder al portapapeles.\n"
            "  [dim]Instala xclip, xsel o wl-clipboard según tu entorno.[/dim]"
        )
        console.print()
        console.print(text)


def _copy_to_clipboard(text: str) -> bool:
    import subprocess, platform
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["pbcopy"], input=text.encode(), check=True, capture_output=True)
            return True
        if system == "Linux":
            for cmd in [
                ["wl-copy"],
                ["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"],
            ]:
                try:
                    subprocess.run(cmd, input=text.encode(), check=True, capture_output=True)
                    return True
                except (FileNotFoundError, subprocess.CalledProcessError):
                    continue
    except Exception:
        pass
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception:
        pass
    return False


# ── /btw ──────────────────────────────────────────────────────────────────────

def _cmd_btw(args: str, agent_loop) -> None:
    """Pregunta rápida en contexto aislado; no altera la conversación principal."""
    if not args:
        console.print("  [yellow]Uso:[/yellow]  /btw <pregunta rápida>")
        return
    from agent.context import ConversationContext
    cfg = agent_loop.config
    # Guarda estado
    saved_messages = list(agent_loop.context.messages)
    saved_summary  = agent_loop.context.summary
    saved_last     = agent_loop._last_user_msg
    # Contexto temporal vacío
    agent_loop.context = ConversationContext(
        max_tokens=min(cfg.max_context_tokens, 4000),
        min_keep=cfg.compact_min_keep,
        compact_threshold=cfg.compact_threshold,
        max_summary_chars=cfg.max_summary_chars,
        high_water=cfg.context_high_water,
        tool_max_chars=cfg.context_tool_max_chars,
    )
    console.print(f"  [dim cyan]↯ btw:[/dim cyan]  [dim]{args[:80]}[/dim]")
    try:
        agent_loop.run(args)
    finally:
        # Restaura estado
        agent_loop.context.messages = saved_messages
        agent_loop.context.summary  = saved_summary
        agent_loop._last_user_msg   = saved_last
    console.print("  [dim]↩ Contexto principal restaurado.[/dim]")


# ── /tasks ────────────────────────────────────────────────────────────────────

def _cmd_tasks(args: str, agent_loop) -> None:
    if agent_loop.tasks is None:
        console.print("  [red]✗[/red]  TaskManager no inicializado.")
        return
    tm = agent_loop.tasks
    parts = args.split(maxsplit=1)
    sub   = parts[0].lower() if parts else ""
    rest  = parts[1].strip() if len(parts) > 1 else ""

    if sub in ("", "list"):
        status_filter = rest if rest in ("todo", "wip", "done") else None
        print_tasks(tm.all_tasks(status=status_filter))
    elif sub == "add":
        if not rest:
            console.print("  [yellow]Uso:[/yellow]  /tasks add <título>")
            return
        t = tm.add(rest)
        console.print(f"  [green]✓[/green]  Tarea añadida  [dim][{t['id']}][/dim]  {t['title']}")
    elif sub in ("done", "wip", "todo"):
        if not rest:
            console.print(f"  [yellow]Uso:[/yellow]  /tasks {sub} <id>")
            return
        t = tm.update(rest, status=sub)
        if t:
            console.print(f"  [green]✓[/green]  [{t['id']}] → {sub}  [dim]{t['title']}[/dim]")
        else:
            console.print(f"  [red]✗[/red]  Tarea [bold]{rest}[/bold] no encontrada.")
    elif sub == "rm":
        if not rest:
            console.print("  [yellow]Uso:[/yellow]  /tasks rm <id>")
            return
        if tm.delete(rest):
            console.print(f"  [green]✓[/green]  Tarea eliminada.")
        else:
            console.print(f"  [red]✗[/red]  Tarea [bold]{rest}[/bold] no encontrada.")
    elif sub == "clear":
        n = tm.clear_done()
        console.print(f"  [green]✓[/green]  {n} tareas completadas eliminadas.")
    else:
        console.print(
            "  [dim]Subcomandos: list [todo|wip|done] · add <título> · "
            "done|wip|todo <id> · rm <id> · clear[/dim]"
        )


# ── /schedule ─────────────────────────────────────────────────────────────────

def _cmd_schedule(args: str, agent_loop, config) -> None:
    if agent_loop.scheduler is None:
        console.print("  [red]✗[/red]  Scheduler no inicializado.")
        return
    sc = agent_loop.scheduler
    parts = args.split(maxsplit=1)
    sub   = parts[0].lower() if parts else ""
    rest  = parts[1].strip() if len(parts) > 1 else ""

    if sub in ("", "list"):
        print_schedule(sc.all_jobs(), sc)
    elif sub == "add":
        # /schedule add <minutos> <comando>
        sp = rest.split(maxsplit=1)
        if len(sp) < 2 or not sp[0].isdigit():
            console.print("  [yellow]Uso:[/yellow]  /schedule add <minutos> <comando>")
            return
        mins, cmd_str = int(sp[0]), sp[1]
        job = sc.add(cmd_str, mins)
        console.print(
            f"  [green]✓[/green]  Job [dim][{job['id']}][/dim] añadido  "
            f"— cada {mins} min: [cyan]{cmd_str[:60]}[/cyan]"
        )
    elif sub == "rm":
        if not rest:
            console.print("  [yellow]Uso:[/yellow]  /schedule rm <id>")
            return
        if sc.delete(rest):
            console.print(f"  [green]✓[/green]  Job eliminado.")
        else:
            console.print(f"  [red]✗[/red]  Job [bold]{rest}[/bold] no encontrado.")
    elif sub == "toggle":
        if not rest:
            console.print("  [yellow]Uso:[/yellow]  /schedule toggle <id>")
            return
        result = sc.toggle(rest)
        if result is None:
            console.print(f"  [red]✗[/red]  Job [bold]{rest}[/bold] no encontrado.")
        else:
            state = "[green]activado[/green]" if result else "[dim]desactivado[/dim]"
            console.print(f"  [green]✓[/green]  Job {state}.")
    elif sub == "run":
        due = sc.due()
        if not due:
            console.print("  [dim]Sin jobs pendientes de ejecutar.[/dim]")
            return
        console.print(f"  Ejecutando {len(due)} job(s)…")
        for job in due:
            console.print(f"  [dim cyan]▶[/dim cyan]  {job['command'][:60]}")
            try:
                from tools.bash import bash_execute
                result = bash_execute(
                    job["command"],
                    timeout=60,
                    max_output_chars=config.bash_max_output_chars,
                )
                sc.mark_run(job["id"])
                lines = result.strip().splitlines()
                preview = lines[0][:100] if lines else "(sin salida)"
                console.print(f"  [dim green]✓[/dim green]  [dim]{preview}[/dim]")
            except Exception as e:
                console.print(f"  [red]✗[/red]  {e}")
    else:
        console.print(
            "  [dim]Subcomandos: list · add <min> <cmd> · toggle <id> · run · rm <id>[/dim]"
        )


# ── /color ────────────────────────────────────────────────────────────────────

def _cmd_color(args: str, rt: RuntimeSettings, config=None) -> None:
    parts = args.split(maxsplit=1)
    sub   = parts[0].lower() if parts else ""
    rest  = parts[1].strip() if len(parts) > 1 else ""

    def _apply(color: str) -> None:
        rt.accent_color = color
        if config is not None:
            config.accent_color = color
            config.save()
        # Re-estilar la TUI full-screen en caliente (toolbar/prompt prompt_toolkit).
        # El ● de la conversación (Rich) ya se recalcula por turno desde rt.accent_color.
        _restyle = getattr(_agent_loop_ref, "_restyle_cb", None)
        if callable(_restyle):
            try:
                _restyle(color)
            except Exception as e:
                log.debug("restyle_cb_error", error=str(e))
        rich_c = COLOR_PRESETS[color][1]
        console.print(
            f"  [green]✓[/green]  Tema → [bold {rich_c}]{color}[/bold {rich_c}]"
        )

    # /color  o  /color random — color aleatorio
    if not sub or sub == "random":
        color = random_color(exclude=rt.accent_color)
        _apply(color)
        return

    # /color list — muestra todos los temas
    if sub == "list":
        themes = all_themes()
        user_themes = set(themes) - set(BUILTIN_THEMES)
        console.print()
        console.print("  [bold dim]Colores base[/bold dim]")
        base_line = "  ".join(
            f"[{COLOR_PRESETS[c][1]}]{c}[/{COLOR_PRESETS[c][1]}]"
            for c in COLOR_PRESETS
        )
        console.print(f"  {base_line}")
        console.print()
        console.print("  [bold dim]Temas predefinidos[/bold dim]")
        for name, theme in BUILTIN_THEMES.items():
            acc = theme.get("accent", "cyan")
            rich_c = COLOR_PRESETS.get(acc, ("", "white"))[1]
            marker = " ← actual" if acc == rt.accent_color else ""
            console.print(f"  [{rich_c}]■[/{rich_c}]  [bold]{name}[/bold]  [dim]{acc}{marker}[/dim]")
        if user_themes:
            console.print()
            console.print("  [bold dim]Temas guardados[/bold dim]")
            for name in sorted(user_themes):
                theme = themes[name]
                acc = theme.get("accent", "cyan")
                rich_c = COLOR_PRESETS.get(acc, ("", "white"))[1]
                marker = " ← actual" if acc == rt.accent_color else ""
                console.print(f"  [{rich_c}]■[/{rich_c}]  [bold]{name}[/bold]  [dim]{acc}{marker}[/dim]")
        console.print()
        console.print(f"  [dim]Actual: {rt.accent_color}  |  /color random  /color save <nombre>[/dim]")
        console.print()
        return

    # /color save [nombre] — guarda el esquema actual
    if sub == "save":
        name = rest or rt.accent_color
        if not name:
            console.print("  [yellow]Uso:[/yellow]  /color save <nombre>")
            return
        theme = {"accent": rt.accent_color}
        save_user_theme(name, theme)
        rich_c = COLOR_PRESETS.get(rt.accent_color, ("", "cyan"))[1]
        console.print(
            f"  [green]✓[/green]  Tema [bold]{name}[/bold] guardado"
            f"  [dim](accent=[{rich_c}]{rt.accent_color}[/{rich_c}])[/dim]"
        )
        return

    # /color rm <nombre> — elimina un tema guardado
    if sub in ("rm", "del", "delete"):
        name = rest
        if not name:
            console.print("  [yellow]Uso:[/yellow]  /color rm <nombre>")
            return
        if name in BUILTIN_THEMES:
            console.print(f"  [red]✗[/red]  No se pueden eliminar los temas predefinidos.")
            return
        if delete_user_theme(name):
            console.print(f"  [green]✓[/green]  Tema [bold]{name}[/bold] eliminado.")
        else:
            console.print(f"  [red]✗[/red]  Tema [bold]{name}[/bold] no encontrado.")
        return

    # /color <nombre_tema_o_color_base>
    themes = all_themes()
    if sub in themes:
        acc = themes[sub].get("accent", "cyan")
        if acc not in COLOR_PRESETS:
            console.print(f"  [yellow]⚠[/yellow]  Color '{acc}' en tema '{sub}' no reconocido.")
            return
        _apply(acc)
        return

    if sub in COLOR_PRESETS:
        _apply(sub)
        return

    available = ", ".join(list(COLOR_PRESETS) + list(themes))
    console.print(
        f"  [yellow]Color/tema '[bold]{sub}[/bold]' no reconocido.[/yellow]\n"
        f"  Disponibles: {available}\n"
        f"  Usa [cyan]/color list[/cyan] para ver todos los esquemas."
    )


# ── /add-dir ──────────────────────────────────────────────────────────────────

def _cmd_add_dir(args: str, rt: RuntimeSettings) -> None:
    parts = args.split(maxsplit=1)
    sub   = parts[0].lower() if parts else ""

    if not args or sub == "list":
        if not rt.extra_dirs:
            console.print("  [dim]Sin directorios adicionales. Usa /add-dir <ruta>.[/dim]")
        else:
            console.print("  [bold dim]Directorios adicionales:[/bold dim]")
            for d in rt.extra_dirs:
                console.print(f"    [cyan]●[/cyan]  {d}")
        return

    if sub == "rm":
        target = parts[1].strip() if len(parts) > 1 else ""
        if not target:
            console.print("  [yellow]Uso:[/yellow]  /add-dir rm <ruta>")
            return
        resolved = str(Path(target).expanduser().resolve())
        if resolved in rt.extra_dirs:
            rt.extra_dirs.remove(resolved)
            console.print(f"  [green]✓[/green]  Directorio eliminado: [dim]{resolved}[/dim]")
        else:
            console.print(f"  [red]✗[/red]  Directorio no encontrado en la lista.")
        return

    # Añadir directorio
    resolved = str(Path(args).expanduser().resolve())
    if not Path(resolved).exists():
        console.print(f"  [red]✗[/red]  Ruta no existe: {resolved}")
        return
    if resolved in rt.extra_dirs:
        console.print(f"  [dim]Ya añadido: {resolved}[/dim]")
        return
    rt.extra_dirs.append(resolved)
    console.print(
        f"  [green]✓[/green]  Directorio añadido: [cyan]{resolved}[/cyan]\n"
        f"  [dim](Se incluye en el contexto del agente)[/dim]"
    )


# ── /skills ───────────────────────────────────────────────────────────────────

def _cmd_skills(args: str, agent_loop, config) -> None:
    if agent_loop.skills is None:
        console.print("  [red]✗[/red]  SkillManager no inicializado.")
        return
    sm = agent_loop.skills
    parts = args.split(maxsplit=1)
    sub   = parts[0].lower() if parts else ""
    name  = parts[1].strip() if len(parts) > 1 else ""

    if sub in ("", "list"):
        print_skills(sm.all_skills())
    elif sub == "create":
        if not name:
            console.print("  [yellow]Uso:[/yellow]  /skills create <nombre>")
            return
        desc = _tui_ask("Descripción (Enter para omitir)", default="")
        result = sm.create(name, desc)
        if result.startswith("ya_existe:"):
            console.print(f"  [yellow]⚠[/yellow]  Ya existe: {result[10:]}")
        else:
            console.print(f"  [green]✓[/green]  Skill creado: [cyan]{result}[/cyan]")
            console.print(f"  [dim]Edítalo y usa /skills enable {name} para activarlo.[/dim]")
    elif sub == "enable":
        if not name:
            console.print("  [yellow]Uso:[/yellow]  /skills enable <nombre>")
            return
        if sm.enable(name):
            for n, fn, schema in sm.load_tools():
                if not agent_loop.registry.has(n):
                    agent_loop.registry.register(n, fn, schema)
            config.skills_enabled = sorted(sm._enabled)
            config.save()
            log.info("skill_enabled", name=name)
            console.print(f"  [green]✓[/green]  Skill [cyan]{name}[/cyan] activado y guardado en oocode.json.")
        else:
            console.print(f"  [red]✗[/red]  Skill [bold]{name}[/bold] no encontrado.")
    elif sub == "disable":
        if not name:
            console.print("  [yellow]Uso:[/yellow]  /skills disable <nombre>")
            return
        if sm.disable(name):
            config.skills_enabled = sorted(sm._enabled)
            config.save()
            log.info("skill_disabled", name=name)
            console.print(f"  [green]✓[/green]  Skill [cyan]{name}[/cyan] desactivado y guardado en oocode.json.")
        else:
            console.print(f"  [red]✗[/red]  Skill [bold]{name}[/bold] no estaba activo.")
    else:
        console.print("  [dim]Subcomandos: list · create <nombre> · enable <nombre> · disable <nombre>[/dim]")


# ── /plugins ──────────────────────────────────────────────────────────────────

def _cmd_plugins(args: str, agent_loop, config) -> None:
    if agent_loop.plugins is None:
        console.print("  [red]✗[/red]  PluginManager no inicializado.")
        return
    pm = agent_loop.plugins
    parts = args.split(maxsplit=1)
    sub   = parts[0].lower() if parts else ""
    name  = parts[1].strip() if len(parts) > 1 else ""

    if sub in ("", "list"):
        print_plugins(pm.all_plugins())
    elif sub == "create":
        if not name:
            console.print("  [yellow]Uso:[/yellow]  /plugins create <nombre>")
            return
        desc = _tui_ask("Descripción (Enter para omitir)", default="")
        result = pm.create(name, desc)
        if result.startswith("ya_existe:"):
            console.print(f"  [yellow]⚠[/yellow]  Ya existe: {result[10:]}")
        else:
            console.print(f"  [green]✓[/green]  Plugin creado: [cyan]{result}[/cyan]")
            console.print(f"  [dim]Edítalo y usa /plugins enable {name} para activarlo.[/dim]")
    elif sub == "enable":
        if not name:
            console.print("  [yellow]Uso:[/yellow]  /plugins enable <nombre>")
            return
        if pm.enable(name):
            errors = pm.load_all(config)
            for t in pm.get_tools():
                agent_loop.registry.register(*t)
            config.plugins_enabled = sorted(pm._enabled)
            config.save()
            log.info("plugin_enabled", name=name)
            msg = f"  [green]✓[/green]  Plugin [cyan]{name}[/cyan] activado y guardado en oocode.json."
            if errors:
                msg += f"  [yellow]({len(errors)} errores)[/yellow]"
            console.print(msg)
        else:
            console.print(f"  [red]✗[/red]  Plugin [bold]{name}[/bold] no encontrado.")
    elif sub == "disable":
        if not name:
            console.print("  [yellow]Uso:[/yellow]  /plugins disable <nombre>")
            return
        if pm.disable(name):
            config.plugins_enabled = sorted(pm._enabled)
            config.save()
            log.info("plugin_disabled", name=name)
            console.print(f"  [green]✓[/green]  Plugin [cyan]{name}[/cyan] desactivado y guardado en oocode.json.")
        else:
            console.print(f"  [red]✗[/red]  Plugin [bold]{name}[/bold] no estaba activo.")
    elif sub == "reload":
        errors = pm.load_all(config)
        for t in pm.get_tools():
            agent_loop.registry.register(*t)
        config.plugins_enabled = sorted(pm._enabled)
        config.save()
        console.print(
            f"  [green]✓[/green]  Plugins recargados."
            + (f"  [yellow]({len(errors)} errores)[/yellow]" if errors else "")
        )
    else:
        console.print(
            "  [dim]Subcomandos: list · create <nombre> · enable <nombre> · "
            "disable <nombre> · reload[/dim]"
        )


# ── /logs ─────────────────────────────────────────────────────────────────────

def _cmd_logs(args: str) -> None:
    n = 40
    if args.strip().isdigit():
        n = max(1, min(int(args.strip()), 500))

    if not log.is_enabled():
        console.print("  [yellow]⚠[/yellow]  Logging desactivado. Actívalo con [cyan]/config edit[/cyan].")
        return

    lines = log.recent(n)
    path  = log.log_file_path()

    if not lines:
        console.print(f"  [dim]Log vacío:[/dim] {path}")
        return

    console.print()
    console.print(f"  [bold dim]Últimas {len(lines)} líneas de[/bold dim] [dim cyan]{path}[/dim cyan]")
    console.print()
    for line in lines:
        # Colorear por nivel
        if "[ERROR" in line:
            console.print(f"  [red]{line}[/red]")
        elif "[WARN" in line:
            console.print(f"  [yellow]{line}[/yellow]")
        elif "[DEBUG" in line:
            console.print(f"  [dim]{line}[/dim]")
        else:
            console.print(f"  [dim white]{line}[/dim white]")
    console.print()


# ── /chatlog ─────────────────────────────────────────────────────────────────

def _cmd_chatlog(sub: str, agent_loop, config) -> None:
    cl = agent_loop.chatlog
    log_path = cl._path

    if sub == "enable":
        config.chatlog_enabled = True
        cl.enabled = True
        config.save()
        console.print(f"  [green]✓[/green]  Chat log activado → [cyan]{log_path}[/cyan]")
        return

    if sub == "disable":
        config.chatlog_enabled = False
        cl.enabled = False
        config.save()
        console.print("  [yellow]◎[/yellow]  Chat log desactivado.")
        return

    if sub.startswith("tail"):
        n = 50
        parts = sub.split()
        if len(parts) > 1 and parts[1].isdigit():
            n = max(1, min(int(parts[1]), 2000))
        if not log_path.exists():
            console.print("  [dim]Chat log vacío o no existe aún.[/dim]")
            return
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        tail  = lines[-n:]
        console.print()
        console.print(f"  [bold dim]Últimas {len(tail)} líneas de[/bold dim] [dim cyan]{log_path}[/dim cyan]")
        console.print()
        for line in tail:
            if line.startswith("[") and "] USUARIO" in line:
                console.print(f"  [bold cyan]{line}[/bold cyan]")
            elif line.startswith("[") and "] AGENTE" in line:
                console.print(f"  [bold green]{line}[/bold green]")
            elif line.startswith("[") and "] TOOL:" in line:
                console.print(f"  [bold yellow]{line}[/bold yellow]")
            elif line.startswith("===") or line.startswith("─" * 10):
                console.print(f"  [dim]{line}[/dim]")
            else:
                console.print(f"  [dim white]{line}[/dim white]")
        console.print()
        return

    if sub == "clear":
        if log_path.exists():
            log_path.write_text("", encoding="utf-8")
            console.print(f"  [green]✓[/green]  Chat log vaciado: [cyan]{log_path}[/cyan]")
        else:
            console.print("  [dim]Chat log ya está vacío.[/dim]")
        return

    # default: status
    enabled_str = "[green]activo[/green]" if cl.enabled else "[dim]desactivado[/dim]"
    size_str    = f"{log_path.stat().st_size / 1024:.1f} KB" if log_path.exists() else "—"
    console.print()
    console.print(f"  Chat log: {enabled_str}")
    console.print(f"  Fichero:  [cyan]{log_path}[/cyan]")
    console.print(f"  Tamaño:   {size_str}  (máx {cl._max_size_mb} MB)")
    console.print(f"  Sesión:   {cl._session_id}")
    console.print()
    console.print("  [dim]/chatlog enable · /chatlog disable · /chatlog tail [n] · /chatlog clear[/dim]")
    console.print()


# ── /doctor ───────────────────────────────────────────────────────────────────

_REQUIRED_PACKAGES = [
    "ollama", "rich", "prompt_toolkit", "requests",
    "beautifulsoup4", "ddgs", "pydantic", "pydantic-settings", "pyperclip",
    "cryptography",
]

# ── WebUI ────────────────────────────────────────────────────────────────
_WEBUI_PACKAGES = [
    "flask", "werkzeug",
]

# ── Home Office O365 Python packages ─────────────────────────────────────
_HO_PY_PKGS_ALL = [
    ("openpyxl",    ["openpyxl"],           "openpyxl",     "Home Office — hojas Excel            pip install openpyxl"),
    ("docx",        ["python-docx"],        "docx",         "Home Office — documentos .docx       pip install python-docx"),
    ("pptx",        ["python-pptx"],        "pptx",         "Home Office — presentaciones .pptx   pip install python-pptx"),
    ("matplotlib",  ["matplotlib"],         "matplotlib",   "Home Office — gráficas dinámicas     pip install matplotlib"),
    ("markdown",    ["Markdown","markdown"],"markdown",     "Home Office — Markdown→HTML          pip install markdown"),
]


def _doctor_llm_backend_checks(config, ok, warn, fail) -> None:  # noqa: C901
    """Chequeos del backend LLM + embeddings, conscientes de `api.type`.

    - ollama: conecta a ollama_host, lista modelos y verifica modelo/embeddings/
      fallback/hosts extra (routing de subagentes).
    - openai/anthropic: verifica configuración (tipo, baseUrl, key, modelo) y
      conectividad ligera. Las embeddings SIEMPRE usan protocolo Ollama, así que
      se prueban contra effective_embed_host independientemente del backend de chat.

    Compartido por run_doctor_standalone (--doctor) y _cmd_doctor (/doctor).
    """
    from api.ollama import ollama_model_names
    api_type = getattr(config, "api_type", "ollama")

    if api_type == "ollama":
        try:
            _mn = ollama_model_names(config.ollama_host)
            ok("Ollama", f"Conectado en {config.ollama_host}  ({len(_mn)} modelos)")
            if config.model:
                if config.model in _mn:
                    ok("Ollama", f"Modelo [cyan]{config.model}[/cyan] disponible")
                else:
                    fail("Ollama", f"Modelo configurado no encontrado: {config.model}")
            else:
                warn("Ollama", "Sin modelo configurado — usa /model")
            if config.fallback_active_config:
                if config.fallback_model in _mn:
                    ok("Ollama", f"Fallback [cyan]{config.fallback_model}[/cyan] disponible  "
                                 f"[dim](timeout {config.fallback_timeout}s)[/dim]")
                else:
                    fail("Ollama", f"Fallback model no encontrado: {config.fallback_model}")
            elif config.fallback_model:
                warn("Ollama", f"Fallback configurado pero desactivado: {config.fallback_model}")
        except Exception as _e:
            fail("Ollama", f"No se puede conectar con {config.ollama_host}: {_e}")

        # Routing de subagentes + hosts extra (solo tiene sentido con Ollama)
        _routing = getattr(config, "ollama_subagent_routing", "round-robin")
        _extra_hosts = getattr(config, "ollama_extra_hosts", [])
        if _routing == "primary-only":
            if _extra_hosts:
                ok("Ollama+", f"Routing subagentes: [cyan]{_routing}[/cyan]  "
                              f"[dim]({len(_extra_hosts)} host(s) extra — no se prueban en primary-only)[/dim]")
            else:
                warn("Ollama+", "Sin hosts extra configurados  [dim](api.extraHosts en oocode.json)[/dim]")
        else:
            for _xhost in _extra_hosts:
                if not _xhost:
                    continue
                try:
                    _xmn = ollama_model_names(_xhost)
                    ok("Ollama+", f"Host extra {_xhost}  ({len(_xmn)} modelos)")
                except Exception as _xe:
                    warn("Ollama+", f"Host extra no responde — {_xhost}: {_xe}")
            if _extra_hosts:
                ok("Ollama+", f"Routing subagentes: [cyan]{_routing}[/cyan]  "
                              f"[dim]({len(_extra_hosts)} host(s) extra)[/dim]")
            else:
                warn("Ollama+", "Sin hosts extra configurados  [dim](api.extraHosts en oocode.json)[/dim]")
    else:
        # ── Backend OpenAI-compatible / Anthropic (experimentales) ──────────────
        _label = "OpenAI-compatible" if api_type == "openai" else "Anthropic"
        ok("Backend LLM", f"Tipo: [cyan]{api_type}[/cyan]  [dim]({_label} — experimental)[/dim]")
        if config.model:
            ok("Backend LLM", f"Modelo configurado: [cyan]{config.model}[/cyan]")
        else:
            warn("Backend LLM", "Sin modelo configurado — usa /model")

        if api_type == "anthropic":
            if config.api_key:
                ok("Backend LLM", "API key configurada  [dim](api.key)[/dim]")
            else:
                fail("Backend LLM", "Falta API key (api.key) — requerida por Anthropic")
            try:
                import anthropic  # noqa: F401
                ok("Backend LLM", "Paquete [cyan]anthropic[/cyan] instalado")
            except ImportError:
                fail("Backend LLM", "Paquete anthropic no instalado  [dim]pip install anthropic[/dim]")
        else:  # openai-compatible
            if config.api_base_url:
                ok("Backend LLM", f"baseUrl: [dim]{config.api_base_url}[/dim]")
            else:
                warn("Backend LLM", "Sin baseUrl configurado  [dim](api.host en oocode.json)[/dim]")
            if config.api_key:
                ok("Backend LLM", "API key configurada  [dim](api.key)[/dim]")
            else:
                warn("Backend LLM", "Sin API key  [dim](OK para servidores locales: llama.cpp/LM Studio/vLLM)[/dim]")
            # Conectividad ligera contra /models del servidor OpenAI-compatible
            if config.api_base_url:
                try:
                    import httpx as _hx
                    _hdr = {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}
                    _r = _hx.get(f"{config.api_base_url.rstrip('/')}/models", headers=_hdr, timeout=5)
                    if _r.status_code < 400:
                        ok("Backend LLM", f"Conectado en {config.api_base_url}")
                    elif _r.status_code in (401, 403):
                        warn("Backend LLM", f"baseUrl responde pero rechaza la key (HTTP {_r.status_code})")
                    else:
                        warn("Backend LLM", f"baseUrl respondió HTTP {_r.status_code} en /models")
                except ImportError:
                    warn("Backend LLM", "httpx no instalado — no se verifica conectividad  [dim]pip install httpx[/dim]")
                except Exception as _e:
                    warn("Backend LLM", f"No se pudo verificar baseUrl: {_e}")

    # ── Embeddings (siempre protocolo Ollama, sea cual sea el backend de chat) ──
    if getattr(config, "memory_embed_enabled", True):
        _eh = config.effective_embed_host
        _dedic = " [dim](host dedicado)[/dim]" if config.ollama_embed_host else ""
        try:
            _emn = ollama_model_names(_eh)
            if config.embed_model in _emn:
                ok("Embeddings", f"[cyan]{config.embed_model}[/cyan] disponible en {_eh}{_dedic}")
            else:
                warn("Embeddings", f"{config.embed_model} no encontrado en {_eh}{_dedic}  "
                                   f"[dim](ollama pull {config.embed_model})[/dim]")
        except Exception as _e:
            warn("Embeddings", f"Host Ollama de embeddings no responde — {_eh}: {_e}  "
                               f"[dim](memoria/RAG semántico degradado)[/dim]")
    else:
        warn("Embeddings", "Desactivados  [dim](memory.embed.enabled=false)[/dim]")


def run_doctor_standalone(config) -> bool:  # noqa: C901
    """Doctor sin agent_loop — para oocode --doctor antes de entrar al REPL."""
    import importlib.metadata
    import shutil as _sh
    from pathlib import Path as _P

    console.print()
    console.rule("[bold cyan]OOCode Doctor — Diagnóstico del sistema[/bold cyan]", style="blue")
    console.print()

    checks: list[tuple[str, str, str]] = []

    def ok(s: str, m: str)   -> None: checks.append((s, "ok",   m))
    def warn(s: str, m: str) -> None: checks.append((s, "warn", m))
    def fail(s: str, m: str) -> None: checks.append((s, "fail", m))

    def _which(cmd): return _sh.which(cmd)

    # ── Backend LLM (ollama | openai | anthropic) + embeddings ─────────────────
    _doctor_llm_backend_checks(config, ok, warn, fail)

    # ── Python packages requeridos ─────────────────────────────────────────────
    for _pkg in _REQUIRED_PACKAGES:
        try:
            _ver = importlib.metadata.version(_pkg)
            ok("Python", f"{_pkg} {_ver}")
        except importlib.metadata.PackageNotFoundError:
            fail("Python", f"{_pkg} no instalado  [dim]pip install {_pkg}[/dim]")

    # ── Python packages opcionales por MCP habilitado ─────────────────────────
    def _pkg_ok(names: list, import_path: str) -> tuple[bool, str]:
        for n in names:
            try:
                return True, importlib.metadata.version(n)
            except importlib.metadata.PackageNotFoundError:
                pass
        try:
            importlib.import_module(import_path.split(".")[0])
            return True, "apt"
        except ImportError:
            return False, ""

    if any(getattr(config, f"mcp_{_s}_assistant_enabled", False) for _s in ("word", "excel", "pptx")):
        for _disp, _meta, _imp, _desc in _HO_PY_PKGS_ALL:
            _found, _ver = _pkg_ok(_meta, _imp)
            if _found:
                ok("Office Python", f"{_disp} {_ver}")
            else:
                warn("Office Python", f"{_disp} no instalado  [dim]{_desc}[/dim]")
        for _cmd, _cdesc, _cinst in [
            ("pandoc",    "conversión de documentos", "apt install pandoc"),
            ("tesseract", "OCR imagen→texto",         "apt install tesseract-ocr"),
            ("pdftotext", "texto desde PDF",           "apt install poppler-utils"),
        ]:
            if _which(_cmd):
                ok("Office Tools", f"{_cmd}  [dim]{_cdesc}[/dim]")
            else:
                warn("Office Tools", f"{_cmd} no encontrado  [dim]{_cdesc}  →  {_cinst}[/dim]")

    if getattr(config, "webui_enabled", False):
        for _wpkg in _WEBUI_PACKAGES:
            try:
                _wver = importlib.metadata.version(_wpkg)
                ok("WebUI Python", f"{_wpkg} {_wver}")
            except importlib.metadata.PackageNotFoundError:
                fail("WebUI Python", f"{_wpkg} no instalado  [dim]pip install {_wpkg}[/dim]")

    # ── CLI tools esenciales ───────────────────────────────────────────────────
    for _cmd, _desc, _req in [
        ("git",      "git_status/commit/…",        True),
        ("rg",       "grep_code — ripgrep",         False),
        ("python3",  "python_exec",                 True),
        ("pip",      "pip_tool",                    True),
        ("make",     "make_run",                    True),
        ("patch",    "patch_apply",                 True),
        ("tar",      "archive_extract/create",      True),
        ("docker",   "docker_ps/exec/…",            False),
        ("ctags",    "build_symbol_index",          False),
        ("jq",       "json_format",                 False),
        ("curl",     "http_get",                    False),
    ]:
        if _which(_cmd):
            ok("Tools", f"{_cmd}  [dim]{_desc}[/dim]")
        elif _req:
            fail("Tools", f"{_cmd} no encontrado  [dim]{_desc}[/dim]")
        else:
            warn("Tools", f"{_cmd} no encontrado (opcional)  [dim]{_desc}[/dim]")

    # ── Linters ────────────────────────────────────────────────────────────────
    _LINTERS_SA = [
        ("ruff",         ".py",                "pip install ruff"),
        ("mypy",         ".py",                "pip install mypy"),
        ("eslint",       ".js .ts .jsx .tsx",  "npm i -g eslint"),
        ("shellcheck",   ".sh .bash",          "apt install shellcheck"),
        ("cargo",        ".rs",                "rustup"),
        ("go",           ".go",                "apt install golang"),
        ("cppcheck",     ".c .cpp .h",         "apt install cppcheck"),
        ("splint",       ".c .h",              "apt install splint"),
        ("rubocop",      ".rb",                "gem install rubocop"),
        ("sqlfluff",     ".sql",               "pip install sqlfluff"),
        ("ktlint",       ".kt",                "brew install ktlint  o  https://github.com/pinterest/ktlint"),
        ("perl",         ".pl .pm",            "apt install perl"),
        ("perlcritic",   ".pl .pm",            "cpan Perl::Critic"),
        ("yamllint",     ".yaml .yml",         "pip install yamllint"),
        ("ansible-lint", ".yaml .yml",         "apt install ansible-lint"),
        ("jsonlint",     ".json",              "apt install jsonlint  (o npm i -g jsonlint)"),
    ]
    _lint_ok_sa = [b for b, _, _ in _LINTERS_SA if _which(b)]
    _lint_miss_sa = [(b, e, i) for b, e, i in _LINTERS_SA if not _which(b)]
    if _lint_ok_sa:
        ok("Linters", f"Instalados: {', '.join(_lint_ok_sa)}")
    for _lb, _le, _li in _lint_miss_sa:
        warn("Linters", f"{_lb} no encontrado  [dim]{_le}  →  {_li}[/dim]")

    # ── efm-langserver backends ────────────────────────────────────────────────
    _EFM_SA = [
        ("efm-langserver",  "LSP general",           "apt install efm-langserver"),
        ("xmllint",         ".xml .xsl .svg",         "apt install libxml2-utils"),
        ("markdownlint",    ".md",                    "npm i -g markdownlint-cli"),
        ("rpmlint",         ".spec",                  "apt install rpmlint"),
        ("rstcheck",        ".rst",                   "pip install rstcheck"),
        ("chktex",          ".tex",                   "apt install chktex"),
        ("hadolint",        ".dockerfile",            "apt install hadolint"),
        ("tflint",          ".tf",                    "ver tflint.io"),
        ("gitlint",         "git commits",            "apt install gitlint"),
    ]
    _efm_ok_sa = [b for b, _, _ in _EFM_SA if _which(b)]
    _efm_miss_sa = [(b, e, i) for b, e, i in _EFM_SA if not _which(b)]
    if _efm_ok_sa:
        ok("efm-langserver", f"Backends instalados: {', '.join(_efm_ok_sa)}")
    for _eb, _ee, _ei in _efm_miss_sa:
        warn("efm-langserver", f"{_eb} no encontrado  [dim]{_ee}  →  {_ei}[/dim]")

    # ── Formatters ─────────────────────────────────────────────────────────────
    _FMTS_SA = [
        ("black",        ".py",               "pip install black"),
        ("isort",        ".py imports",       "pip install isort"),
        ("prettier",     ".js .ts .css .html","npm i -g prettier"),
        ("gofmt",        ".go",               "apt install golang"),
        ("rustfmt",      ".rs",               "rustup component add rustfmt"),
        ("clang-format", ".c .cpp .h",        "apt install clang-format"),
        ("ktlint",       ".kt",               "https://github.com/pinterest/ktlint"),
        ("rubocop",      ".rb",               "gem install rubocop"),
        ("sqlfluff",     ".sql",              "pip install sqlfluff"),
    ]
    _fmt_ok_sa = [b for b, _, _ in _FMTS_SA if _which(b)]
    _fmt_miss_sa = [(b, e, i) for b, e, i in _FMTS_SA if not _which(b)]
    if _fmt_ok_sa:
        ok("Formatters", f"Instalados: {', '.join(_fmt_ok_sa)}")
    for _fb, _fe, _fi in _fmt_miss_sa:
        warn("Formatters", f"{_fb} no encontrado  [dim]{_fe}  →  {_fi}[/dim]")

    # ── MCP server files ───────────────────────────────────────────────────────
    _mcp_dir = _P(__file__).parent.parent / "mcp_servers"
    for _srv_name, _enabled_attr in [
        ("oocode_assistant",      "mcp_oocode_assistant_enabled"),
        ("system_assistant",      "mcp_system_assistant_enabled"),
        ("word_assistant",        "mcp_word_assistant_enabled"),
        ("excel_assistant",       "mcp_excel_assistant_enabled"),
        ("pptx_assistant",        "mcp_pptx_assistant_enabled"),
        ("mail_assistant",        "mcp_mail_assistant_enabled"),
        ("cmdb_assistant",        "mcp_cmdb_assistant_enabled"),
        ("security_assistant",    "mcp_security_assistant_enabled"),
        ("iot_assistant",         "mcp_iot_assistant_enabled"),
    ]:
        _f = _mcp_dir / f"{_srv_name}.py"
        _en = getattr(config, _enabled_attr, False)
        if _f.exists():
            if _en:
                ok("MCP files", f"{_srv_name}.py  [dim]habilitado[/dim]")
            else:
                warn("MCP files", f"{_srv_name}.py  [dim]desactivado en config[/dim]")
        else:
            if _en:
                fail("MCP files", f"{_srv_name}.py no encontrado (habilitado en config)")
            else:
                warn("MCP files", f"{_srv_name}.py no encontrado")

    # ── Config ─────────────────────────────────────────────────────────────────
    from config import CONFIG_FILE
    if CONFIG_FILE.exists():
        ok("Config", f"oocode.json  [dim]{CONFIG_FILE}[/dim]")
    else:
        fail("Config", f"oocode.json no encontrado: {CONFIG_FILE}")
    _ws = _P(config.workspace).expanduser()
    ok("Config", f"Workspace  [dim]{_ws}[/dim]") if _ws.exists() else warn("Config", f"Workspace no existe: {_ws}")
    if config.project_dir:
        _pd = _P(config.project_dir)
        ok("Config", f"Proyecto  [dim]{_pd}[/dim]  "
                     + ("[green]OOCODE.md[/green]" if (_pd / "OOCODE.md").exists() else "[dim]sin OOCODE.md[/dim]"))

    _oocode_warn = config.oocode_md_warning()
    if _oocode_warn:
        warn("Config", _oocode_warn)

    # ── IoT MCP Python + CLI ───────────────────────────────────────────────────
    if getattr(config, "mcp_iot_assistant_enabled", False):
        for _pkg, _meta, _imp, _desc in [
            ("kasa",     ["kasa"],      "kasa",      "IoT MCP — TAPO luces/enchufes TP-Link  (sudo apt install python3-kasa)"),
            ("blinkpy",  ["blinkpy"],   "blinkpy",   "IoT MCP — cámaras Blink/Amazon Ring   (sudo apt install python3-blinkpy)"),
            ("aiohttp",  ["aiohttp"],   "aiohttp",   "IoT MCP — HTTP async (requerido por blinkpy)"),
            ("tinytuya", ["tinytuya"],  "tinytuya",  "IoT MCP — dispositivos Tuya/Smart Life  (pip install tinytuya)"),
            ("paho",     ["paho-mqtt"], "paho.mqtt", "IoT MCP — broker MQTT  (sudo apt install python3-paho-mqtt)"),
        ]:
            _f, _v = _pkg_ok(_meta, _imp)
            if _f:
                ok("IoT MCP Python", f"{_pkg} {_v}")
            else:
                warn("IoT MCP Python", f"{_pkg} no instalado  [dim]{_desc}[/dim]")
        if _which("avahi-browse"):
            ok("IoT MCP Tools", "avahi-browse  [dim]descubrimiento mDNS[/dim]")
        else:
            warn("IoT MCP Tools", "avahi-browse no encontrado  [dim]apt install avahi-utils[/dim]")

    # ── Security MCP CLI ────────────────────────────────────────────────────────
    if getattr(config, "mcp_security_assistant_enabled", False):
        for _cmd, _desc, _inst in [
            ("nmap",       "escaneo de puertos",     "apt install nmap"),
            ("nikto",      "análisis web",           "apt install nikto"),
            ("gobuster",   "fuerza bruta dirs",      "apt install gobuster"),
            ("hashcat",    "cracking de hashes",     "apt install hashcat"),
            ("whois",      "info de dominio",        "apt install whois"),
            ("dig",        "consultas DNS",          "apt install dnsutils"),
            ("openssl",    "certificados y crypto",  "apt install openssl"),
            ("trufflehog", "secrets en git",         "pip install trufflehog"),
            ("gitleaks",   "secrets en código",      "https://github.com/gitleaks/gitleaks"),
            ("steghide",   "esteganografía",         "apt install steghide"),
            ("xxd",        "hex dump",               "apt install xxd"),
        ]:
            if _which(_cmd):
                ok("Security MCP Tools", f"{_cmd}  [dim]{_desc}[/dim]")
            else:
                warn("Security MCP Tools", f"{_cmd} no encontrado  [dim]{_desc}  →  {_inst}[/dim]")

    # ── Office packages — siempre verificar (no solo si está habilitado) ──
    if not any(getattr(config, f"mcp_{_s}_assistant_enabled", False) for _s in ("word", "excel", "pptx")):
        for _disp, _meta, _imp, _desc in _HO_PY_PKGS_ALL:
            _found, _ver = _pkg_ok(_meta, _imp)
            if _found:
                ok("Office Python (opcional)", f"{_disp} {_ver}")
            else:
                warn("Office Python (opcional)", f"{_disp} no instalado  [dim]{_desc}[/dim]")

    # ── LSP servers ────────────────────────────────────────────────────────────
    _LSP_SA = {
        "pylsp":                       ("pip install python-lsp-server",           ".py"),
        "typescript-language-server":  ("npm i -g typescript-language-server",     ".js .ts .jsx .tsx"),
        "gopls":                       ("go install golang.org/x/tools/gopls@latest", ".go"),
        "rust-analyzer":               ("rustup component add rust-analyzer",       ".rs"),
        "clangd":                      ("apt install clangd",                       ".c .cpp .h"),
        "jdtls":                       ("apt install default-jdk + sdk install jdtls", ".java"),
        "ruby-lsp":                    ("gem install ruby-lsp",                     ".rb"),
        "csharp-ls":                   ("dotnet tool install -g csharp-ls",         ".cs"),
        "kotlin-language-server":      ("sdk install kotlin  (sdkman.io)",          ".kt"),
        "bash-language-server":        ("npm i -g bash-language-server",            ".sh .bash .mk"),
        "yaml-language-server":        ("npm i -g yaml-language-server",            ".yaml .yml"),
        "vscode-json-language-server": ("npm i -g vscode-langservers-extracted",    ".json"),
        "vscode-css-language-server":  ("npm i -g vscode-langservers-extracted",    ".css .scss .less"),
        "vscode-html-language-server": ("npm i -g vscode-langservers-extracted",    ".html"),
        "perl-language-server":        ("cpan PLS",                                ".pl .pm"),
        "sql-language-server":         ("npm i -g sql-language-server",             ".sql"),
        "lua-language-server":         ("apt install lua-language-server",          ".lua"),
        "intelephense":                ("npm i -g intelephense",                    ".php"),
        "taplo":                       ("cargo install taplo-cli",                  ".toml"),
        "efm-langserver":              ("apt install efm-langserver",               ".xml .md .spec .rst .tex"),
        "marksman":                    ("snap install marksman",                    ".md extra"),
    }
    _lsp_ok_sa = []
    _lsp_miss_sa = []
    for _lcmd, (_lhint, _lexts) in _LSP_SA.items():
        if _which(_lcmd):
            _lsp_ok_sa.append(_lcmd)
        else:
            _lsp_miss_sa.append((_lcmd, _lexts, _lhint))
    if _lsp_ok_sa:
        ok("LSP servers", f"Instalados: {', '.join(_lsp_ok_sa)}")
    for _lcmd, _lexts, _lhint in _lsp_miss_sa:
        warn("LSP servers", f"{_lcmd} no encontrado  [dim]{_lexts}  →  {_lhint}[/dim]")

    # ── Agentes y workspaces ───────────────────────────────────────────────────
    for _ag in config.agents:
        _ws_p = _P(_ag.workspace).expanduser()
        _has_id = (_ws_p / "IDENTITY.md").exists()
        if _ws_p.exists() and _has_id:
            ok("Agentes", f"{_ag.emoji} {_ag.id}  [dim]{_ag.workspace}[/dim]")
        elif _ws_p.exists():
            warn("Agentes", f"{_ag.emoji} {_ag.id}  workspace sin IDENTITY.md  [dim]→  /switch {_ag.id}  para inicializar[/dim]")
        else:
            warn("Agentes", f"{_ag.emoji} {_ag.id}  workspace no existe  [dim]{_ag.workspace}[/dim]")

    # ── Hooks ─────────────────────────────────────────────────────────────────
    if config.hooks_enabled:
        try:
            from tools.hooks import _BUILTINS
            _active_hooks_sa = set(config.hooks_builtins) if config.hooks_builtins else set()
            _hook_on_sa  = [h for h in _BUILTINS if h in _active_hooks_sa]
            _hook_off_sa = [h for h in _BUILTINS if h not in _active_hooks_sa]
            ok("Hooks", f"{len(_hook_on_sa)} activos · {len(_hook_off_sa)} inactivos  "
                        f"[dim](de {len(_BUILTINS)} built-ins)[/dim]")
        except Exception as _e:
            warn("Hooks", f"No se pudo verificar hooks: {_e}")
    else:
        warn("Hooks", "Sistema de hooks desactivado  [dim](hooks.enabled=false)[/dim]")

    # ── Logging y chatlog ──────────────────────────────────────────────────────
    try:
        if log.is_enabled():
            ok("Config", f"Log activo  [dim]{log.log_file_path()}[/dim]")
        else:
            warn("Config", "Logging desactivado  [dim](logging.enabled=false)[/dim]")
    except Exception:
        pass
    if config.chatlog_enabled:
        ok("Config", "Chatlog activo  [dim](chatlog.enabled=true)[/dim]")
    else:
        warn("Config", "Chatlog desactivado  [dim](chatlog.enabled=false en oocode.json)[/dim]")

    # ── SearXNG ────────────────────────────────────────────────────────────────
    if config.searxng_url:
        try:
            import requests as _req
            _r = _req.get(f"{config.searxng_url.rstrip('/')}/search",
                          params={"q":"test","format":"json"}, timeout=4,
                          headers={"Accept":"application/json"})
            _r.raise_for_status()
            ok("SearXNG", f"Conectado en {config.searxng_url}")
        except Exception as _e:
            fail("SearXNG", f"Error conectando con {config.searxng_url}: {_e}")
    else:
        warn("SearXNG", "No configurado  [dim](searxng.url en oocode.json)[/dim]")

    # ── Sesiones ────────────────────────────────────────────────────────────────
    try:
        from agent.session import SESSIONS_ROOT
        if SESSIONS_ROOT.exists():
            _agent_dirs = [d for d in SESSIONS_ROOT.iterdir() if d.is_dir()]
            _total_sess = sum(len(list(d.glob("*.jsonl"))) for d in _agent_dirs)
            ok("Sesiones", f"Directorio OK  [dim]{SESSIONS_ROOT}[/dim]  ({_total_sess} sesiones en {len(_agent_dirs)} agente(s))")
        else:
            warn("Sesiones", f"Directorio no existe  [dim]{SESSIONS_ROOT}[/dim]  (se creará al iniciar)")
    except Exception as _e:
        warn("Sesiones", f"No se pudo verificar: {_e}")

    # ── Visión / portapapeles ──────────────────────────────────────────────────
    _clip_found = False
    for _cmd, _desc, _inst in [
        ("xclip",    "portapapeles X11 — Ctrl+P en TUI para pegar imágenes",    "apt install xclip"),
        ("xsel",     "portapapeles X11 alternativo",                              "apt install xsel"),
        ("wl-paste", "portapapeles Wayland — Ctrl+P en TUI para pegar imágenes", "apt install wl-clipboard"),
    ]:
        if _which(_cmd):
            ok("Vision / Portapapeles", f"{_cmd}  [dim]{_desc}[/dim]")
            _clip_found = True
    if not _clip_found:
        warn("Vision / Portapapeles",
             "Sin herramienta de portapapeles  [dim]apt install xclip  (X11) o apt install wl-clipboard  (Wayland)[/dim]")
    try:
        _pil_ver = importlib.metadata.version("Pillow")
        ok("Vision / Portapapeles", f"Pillow {_pil_ver}  [dim]procesamiento de imágenes[/dim]")
    except importlib.metadata.PackageNotFoundError:
        warn("Vision / Portapapeles",
             "Pillow no instalado (opcional)  [dim]pip install Pillow[/dim]")

    # ── Render ─────────────────────────────────────────────────────────────────
    _ICONS = {"ok": "[green]✓[/green]", "warn": "[yellow]⚠[/yellow]", "fail": "[red]✗[/red]"}
    _cur = ""
    for _s, _st, _m in checks:
        if _s != _cur:
            console.print(f"  [bold dim]{_s}[/bold dim]")
            _cur = _s
        console.print(f"    {_ICONS[_st]}  {_m}")

    n_ok   = sum(1 for _, s, _ in checks if s == "ok")
    n_warn = sum(1 for _, s, _ in checks if s == "warn")
    n_fail = sum(1 for _, s, _ in checks if s == "fail")
    console.print()
    console.print(
        f"  [dim]Resultado:[/dim]  "
        f"[green]{n_ok} OK[/green]  "
        f"[yellow]{n_warn} avisos[/yellow]  "
        f"[red]{n_fail} errores[/red]"
    )
    console.print()
    return n_fail == 0


def _cmd_doctor(config, agent_loop) -> None:  # noqa: C901
    import shutil as _sh
    import os as _env_os

    console.print()
    console.rule("[bold cyan]OOCode Doctor — Diagnóstico del sistema[/bold cyan]", style="blue")
    console.print()

    checks: list[tuple[str, str, str]] = []

    def ok(section: str, msg: str)   -> None: checks.append((section, "ok",   msg))
    def warn(section: str, msg: str) -> None: checks.append((section, "warn", msg))
    def fail(section: str, msg: str) -> None: checks.append((section, "fail", msg))

    def _which(cmd: str): return _sh.which(cmd)

    # ── 1. Backend LLM (ollama | openai | anthropic) + embeddings ─────────────
    _doctor_llm_backend_checks(config, ok, warn, fail)

    # ── 2. MCP — servidores bundled y externos ────────────────────────────────
    _mcp_pool = getattr(agent_loop, "_mcp_pool", None)
    if config.mcp_oocode_assistant_enabled:
        if _mcp_pool is not None:
            _bundled = _mcp_pool.get_client("oocode-assistant")
            if _bundled and _bundled.is_alive:
                _n_t = len(_bundled.tools)
                _n_p = getattr(_bundled, "_prompt_count", 0)
                _n_r = getattr(_bundled, "_resource_count", 0)
                ok("MCP", f"oocode_assistant  [dim]●[/dim]  "
                          f"{_n_t} tools · {_n_p} prompts · {_n_r} recursos")
            elif _bundled:
                fail("MCP", f"oocode_assistant caído: {_bundled.error or 'error desconocido'}")
            else:
                warn("MCP", "oocode_assistant no inicializado aún")
        else:
            warn("MCP", "MCP pool no inicializado")
    else:
        warn("MCP", "oocode_assistant desactivado  [dim](mcp.oocodeAssistant.enabled=false)[/dim]")

    # Bundled MCP: system, office, mail, cmdb, security, iot
    _BUNDLED_MCP_EXTRA = [
        ("systemAssistant",     "system-assistant",
         getattr(config, "mcp_system_assistant_enabled", False)),
        ("wordAssistant",       "word-assistant",
         getattr(config, "mcp_word_assistant_enabled", False)),
        ("excelAssistant",      "excel-assistant",
         getattr(config, "mcp_excel_assistant_enabled", False)),
        ("pptxAssistant",       "pptx-assistant",
         getattr(config, "mcp_pptx_assistant_enabled", False)),
        ("mailAssistant",       "mail-assistant",
         getattr(config, "mcp_mail_assistant_enabled", False)),
        ("cmdbAssistant",       "cmdb-assistant",
         getattr(config, "mcp_cmdb_assistant_enabled", False)),
        ("securityAssistant",   "security-assistant",
         getattr(config, "mcp_security_assistant_enabled", False)),
        ("iotAssistant",        "iot-assistant",
         getattr(config, "mcp_iot_assistant_enabled", False)),
    ]
    for _cfg_key, _srv_name, _srv_enabled in _BUNDLED_MCP_EXTRA:
        if _srv_enabled:
            if _mcp_pool is not None:
                _bcli = _mcp_pool.get_client(_srv_name)
                if _bcli and _bcli.is_alive:
                    _bn_t = len(_bcli.tools)
                    _bn_p = getattr(_bcli, "_prompt_count", 0)
                    _bn_r = getattr(_bcli, "_resource_count", 0)
                    ok("MCP", f"{_srv_name}  [dim]●[/dim]  "
                              f"{_bn_t} tools · {_bn_p} prompts · {_bn_r} recursos")
                elif _bcli:
                    fail("MCP", f"{_srv_name} caído: {_bcli.error or 'error desconocido'}")
                else:
                    warn("MCP", f"{_srv_name} no inicializado aún")
            else:
                warn("MCP", f"{_srv_name} habilitado pero MCP pool no inicializado")
        else:
            warn("MCP", f"{_srv_name} desactivado  "
                        f"[dim](mcp.{_cfg_key}.enabled=false)[/dim]")

    if config.mcp_servers:
        for _srv in config.mcp_servers:
            _sname = _srv.get("name", "?")
            if _mcp_pool:
                _cli = _mcp_pool.get_client(_sname)
                if _cli and _cli.is_alive:
                    ok("MCP", f"{_sname}  [dim]●[/dim]  {len(_cli.tools)} tools")
                elif _cli:
                    fail("MCP", f"{_sname}  [dim]✗[/dim]  {_cli.error or 'error'}")
                else:
                    warn("MCP", f"{_sname}  [dim]no conectado[/dim]")
            else:
                warn("MCP", f"{_sname}  configurado pero MCP pool no inicializado")
    else:
        warn("MCP", "Sin servidores MCP externos configurados  [dim](mcp.servers en oocode.json)[/dim]")

    # ── 3. LSP — servidores de lenguaje ──────────────────────────────────────
    _lsp_plugin = None
    _lsp_pool   = None
    if agent_loop.plugins:
        _lsp_plugin = agent_loop.plugins._loaded.get("lsp")
        if _lsp_plugin:
            _lsp_pool = getattr(_lsp_plugin, "_pool", None)

    if not _lsp_plugin:
        warn("LSP", "Plugin LSP no activo  [dim](/plugins enable lsp)[/dim]")
    else:
        # Servidores activos en esta sesión
        _active_exts = _lsp_pool.active_extensions if _lsp_pool else []
        if _active_exts:
            ok("LSP", f"Activos: {', '.join(_active_exts)}")
        else:
            warn("LSP", "Ningún servidor LSP activo en esta sesión")

        # Servidores instalados en el sistema
        _lsp_servers: list[dict] = []
        if _lsp_pool:
            _lsp_servers = _lsp_pool.available_servers()
        else:
            # Fallback: comprobar binarios del _SERVER_CMDS
            try:
                from agent.lsp_client import _SERVER_CMDS as _SC, _which as _lw
                _seen: set[str] = set()
                for _ext_k, _cmd_l in _SC.items():
                    _n = _cmd_l[0]
                    if _n not in _seen:
                        _seen.add(_n)
                        _exts_l = [e for e, c in _SC.items() if c[0] == _n]
                        _lsp_servers.append({"name": _n, "installed": _lw(_n), "exts": _exts_l})
            except Exception:
                pass

        # Servidores esenciales (warn si faltan) y opcionales
        _LSP_INSTALL = {
            "pylsp":                           "pip install python-lsp-server",
            "typescript-language-server":      "npm i -g typescript-language-server typescript",
            "gopls":                           "go install golang.org/x/tools/gopls@latest",
            "rust-analyzer":                   "rustup component add rust-analyzer",
            "clangd":                          "apt install clangd",
            # jdtls NO está en apt — requiere Java + descarga manual
            "jdtls":                           "apt install default-jdk  &&  sdk install jdtls  (sdkman.io)",
            "ruby-lsp":                        "gem install ruby-lsp",
            "perl-language-server":            "cpan PLS",
            "sql-language-server":             "npm i -g sql-language-server",
            "bash-language-server":            "npm i -g bash-language-server",
            "yaml-language-server":            "npm i -g yaml-language-server",
            "vscode-json-language-server":     "npm i -g vscode-langservers-extracted",
            "vscode-css-language-server":      "npm i -g vscode-langservers-extracted",
            "vscode-html-language-server":     "npm i -g vscode-langservers-extracted",
            # vscode-markdown-language-server roto en Node 22 → se usa efm-langserver+markdownlint
            # cmake-language-server roto con pygls v2 → no hay LSP cmake disponible
            # csharp-ls reemplaza OmniSharp — requiere dotnet SDK
            "csharp-ls":                       "apt install dotnet-sdk-8.0  &&  dotnet tool install -g csharp-ls",
            "kotlin-language-server":          "sdk install kotlin  (sdkman.io)",
            "sourcekit-lsp":                   "xcode-select --install  (solo macOS)",
            "lua-language-server":             "apt install lua-language-server",
            "intelephense":                    "npm i -g intelephense",
            "taplo":                           "cargo install taplo-cli",
            # efm-langserver — LSP para xml/md/rst/tex/dockerfile/tf/spec/office
            "efm-langserver":                  "apt install efm-langserver",
        }
        for _srv in _lsp_servers:
            _exts_s = " ".join(_srv["exts"][:4])
            if _srv.get("installed"):
                ok("LSP", f"{_srv['name']}  [dim]{_exts_s}[/dim]")
            else:
                _hint = _LSP_INSTALL.get(_srv["name"], "")
                warn("LSP", f"{_srv['name']} no instalado  [dim]{_exts_s}"
                            + (f"  →  {_hint}" if _hint else "") + "[/dim]")

    # ── 4. Linters — lint_after_write (subprocess directo) ───────────────────
    _LINTERS_DOC = [
        # (binary,       extensiones,          install hint)
        ("ruff",         ".py",                "pip install ruff"),
        ("mypy",         ".py",                "pip install mypy"),
        ("eslint",       ".js .ts .jsx .tsx",  "npm i -g eslint"),
        ("shellcheck",   ".sh .bash",          "apt install shellcheck"),
        ("cargo",        ".rs",                "rustup"),
        ("go",           ".go",                "apt install golang"),
        ("cppcheck",     ".c .cpp .h .cc .hpp","apt install cppcheck"),
        ("splint",       ".c .h",              "apt install splint"),
        ("rubocop",      ".rb",                "gem install rubocop"),
        ("sqlfluff",     ".sql",               "pip install sqlfluff"),
        ("ktlint",       ".kt",                "brew install ktlint  o  https://github.com/pinterest/ktlint"),
        ("perl",         ".pl .pm",            "apt install perl"),
        ("perlcritic",   ".pl .pm",            "cpan Perl::Critic"),
        ("yamllint",     ".yaml .yml",         "pip install yamllint"),
        ("ansible-lint", ".yaml .yml",         "apt install ansible-lint"),
        ("jsonlint",     ".json",              "apt install jsonlint  (o npm i -g jsonlint)"),
    ]
    _lint_ok = []
    _lint_miss = []
    for _bin, _exts_l, _inst in _LINTERS_DOC:
        if _which(_bin):
            _lint_ok.append(_bin)
        else:
            _lint_miss.append((_bin, _exts_l, _inst))
    if _lint_ok:
        ok("Linters", f"Instalados: {', '.join(_lint_ok)}")
    for _bin, _exts_l, _inst in _lint_miss:
        warn("Linters", f"{_bin} no encontrado  [dim]{_exts_l}  →  {_inst}[/dim]")

    # ── 4b. efm-langserver — backends (lsp_after_write para xml/md/rst/…) ─────
    # Estos linters se usan como backends de efm-langserver para los tipos de fichero
    # que NO tienen servidor LSP dedicado (.xml, .md, .spec, .rst, .tex, .dockerfile, .tf).
    # NO duplican lint_after_write: solo actúan vía LSP cuando se escribe uno de esos ficheros.
    _EFM_BACKENDS_DOC = [
        # (binary,          extensiones LSP,         install hint)
        ("efm-langserver",  "LSP general",            "apt install efm-langserver"),
        ("xmllint",         ".xml .xsl .xslt .svg",   "apt install libxml2-utils"),
        ("markdownlint",    ".md .markdown",           "npm i -g markdownlint-cli"),
        ("rpmlint",         ".spec",                   "apt install rpmlint"),
        ("rstcheck",        ".rst",                    "pip install rstcheck"),
        ("chktex",          ".tex .latex",             "apt install chktex"),
        ("hadolint",        ".dockerfile",             "apt install hadolint"),
        ("tflint",          ".tf .tfvars",             "ver tflint.io"),
        ("gitlint",         "git commits",             "apt install gitlint"),
    ]
    _efm_ok = []
    _efm_miss = []
    for _bin, _exts_l, _inst in _EFM_BACKENDS_DOC:
        if _which(_bin):
            _efm_ok.append(_bin)
        else:
            _efm_miss.append((_bin, _exts_l, _inst))
    if _efm_ok:
        ok("efm-langserver", f"Backends instalados: {', '.join(_efm_ok)}")
    for _bin, _exts_l, _inst in _efm_miss:
        warn("efm-langserver", f"{_bin} no encontrado  [dim]{_exts_l}  →  {_inst}[/dim]")

    # ── 5. Formatters — autoformat_after_write ───────────────────────────────
    _FMTS = [
        ("black",        ".py",               "pip install black"),
        ("isort",        ".py imports",       "pip install isort"),
        ("prettier",     ".js .ts .css .html","npm i -g prettier"),
        ("gofmt",        ".go",               "apt install golang"),
        ("rustfmt",      ".rs",               "rustup component add rustfmt"),
        ("clang-format", ".c .cpp .h",        "apt install clang-format"),
        ("ktlint",       ".kt",               "https://github.com/pinterest/ktlint"),
        ("rubocop",      ".rb",               "gem install rubocop"),
        ("sqlfluff",     ".sql",              "pip install sqlfluff"),
    ]
    _fmt_ok   = [b for b, _, _ in _FMTS if _which(b)]
    _fmt_miss = [(b, e, i) for b, e, i in _FMTS if not _which(b)]
    if _fmt_ok:
        ok("Formatters", f"Instalados: {', '.join(_fmt_ok)}")
    for _bin, _exts_l, _inst in _fmt_miss:
        warn("Formatters", f"{_bin} no encontrado  [dim]{_exts_l}  →  {_inst}[/dim]")

    # ── 6. Hooks — builtins activos y sus dependencias ───────────────────────
    _ALL_BUILTINS = {
        "diff_after_write":           ("diff visual tras write/edit",                None),
        "ctags_after_write":          ("reindexea símbolos ctags",                   "ctags"),
        "lint_after_write":           ("linting automático tras write/edit",         None),
        "quick_syntax_after_write":   ("sintaxis .py instantánea (ast.parse)",       None),
        "lsp_after_write":            ("diagnósticos LSP tras escribir",             None),
        "autoformat_after_write":     ("formatea código automáticamente",            None),
        "backup_before_write":        ("copia .bak antes de modificar",              None),
        "check_secrets":              ("bloquea si detecta tokens/keys",             None),
        "log_tool_calls":             ("registra tool calls en .jsonl",              None),
        "verify_after_edit":          ("re-lee sección tras edit_file",              None),
        "todo_scan_after_write":      ("muestra TODOs/FIXMEs encontrados",           None),
        "test_after_write":           ("ejecuta pytest del fichero modificado",      None),
        "size_check_after_write":     ("avisa si fichero >300 líneas / 15 KB",       None),
        "test_suite_delta":           ("delta de regresiones pre/post escritura",    None),
        "interface_change_detector":  ("detecta cambios de firma AST en .py",       None),
        "config_syntax_after_write":  ("valida .json/.toml/.ini tras escritura",     None),
        "git_push_guard":             ("advierte en push a ramas protegidas",        None),
        "security_audit_log":         ("audit log de tools Security MCP",            None),
    }
    if config.hooks_enabled:
        _active_hooks = set(config.hooks_builtins)
        for _hname, (_hdesc, _hdep) in _ALL_BUILTINS.items():
            if _hname in _active_hooks:
                if _hdep and not _which(_hdep):
                    warn("Hooks", f"{_hname}  [dim]activo pero {_hdep} no instalado[/dim]")
                else:
                    ok("Hooks", f"{_hname}  [dim]{_hdesc}[/dim]")
            else:
                warn("Hooks", f"{_hname}  [dim]inactivo  →  /hooks builtin {_hname}[/dim]")
    else:
        warn("Hooks", "Sistema de hooks desactivado  [dim](hooks.enabled=false)[/dim]")

    # ── 7. RAG — búsqueda semántica del workspace ─────────────────────────────
    _rag = getattr(agent_loop, "_workspace_rag", None)
    if config.rag_enabled:
        if _rag is not None:
            _n_files = _rag.indexed_files
            _n_chunks = _rag.index_size
            if _n_files > 0:
                ok("RAG", f"{_n_files} ficheros · {_n_chunks} fragmentos indexados")
            else:
                warn("RAG", "Habilitado pero workspace aún no indexado")
            ok("RAG", f"topK={config.rag_top_k}  threshold={config.rag_similarity_threshold:.2f}")
        else:
            warn("RAG", "RAG habilitado pero no inicializado")
        # Embeddings para RAG
        _embed = getattr(agent_loop, "_embed_client", None)
        if _embed and _embed.is_available():
            ok("RAG", f"Embeddings disponibles  [dim]({config.embed_model})[/dim]")
        else:
            fail("RAG", f"Embeddings no disponibles — instala {config.embed_model} en Ollama")
    else:
        warn("RAG", "Desactivado  [dim](rag.enabled=false en oocode.json)[/dim]")

    # ── 8. Memoria persistente ────────────────────────────────────────────────
    _mem = agent_loop.memory
    _mem_dir  = _mem._dir
    _mem_mds  = list(_mem_dir.glob("*.md")) if _mem_dir.exists() else []
    _mem_mds  = [p for p in _mem_mds if p.name != "MEMORY.md"]
    _mem_embs = list(_mem_dir.glob("*.emb.json")) if _mem_dir.exists() else []
    _n_mems   = len(_mem_mds)
    _n_embs   = len(_mem_embs)
    if _n_mems > 0:
        _emb_ratio = f"{_n_embs}/{_n_mems} con embedding"
        ok("Memoria", f"{_n_mems} memorias · {_emb_ratio}  [dim]({_mem_dir})[/dim]")
    else:
        warn("Memoria", f"Sin memorias guardadas  [dim]({_mem_dir})[/dim]")
    if _mem._embed and _mem._embed.is_available():
        ok("Memoria", f"Búsqueda semántica disponible  [dim](threshold {_mem._threshold:.2f})[/dim]")
    else:
        warn("Memoria", "Embeddings no disponibles — /mem search no funcionará")
    _mem_embed_on = getattr(config, "memory_embed_enabled", True)
    if _mem_embed_on:
        ok("Memoria", "memory_embed_enabled  [dim]activo — los recuerdos se indexan por vectores[/dim]")
    else:
        warn("Memoria", "memory_embed_enabled  [dim]desactivado — sin indexación vectorial de memorias[/dim]  "
                        "[dim](embeddings.memoryEmbedEnabled en oocode.json)[/dim]")

    # ── 9. SearXNG ────────────────────────────────────────────────────────────
    if config.searxng_url:
        try:
            _r = requests.get(
                f"{config.searxng_url.rstrip('/')}/search",
                params={"q": "test", "format": "json"},
                timeout=5,
                headers={"Accept": "application/json"},
            )
            _r.raise_for_status()
            _mode = "activo (reemplaza web_search)" if config.searxng_enabled else "disponible (searxng_search)"
            ok("SearXNG", f"Conectado en {config.searxng_url}  —  {_mode}")
        except Exception as _e:
            fail("SearXNG", f"Error conectando con {config.searxng_url}: {_e}")
    else:
        warn("SearXNG", "No configurado  [dim](searxng.url en oocode.json)[/dim]")

    # ── 10. Config y ficheros ─────────────────────────────────────────────────
    from config import CONFIG_FILE
    if CONFIG_FILE.exists():
        ok("Config", f"oocode.json  [dim]{CONFIG_FILE}[/dim]")
    else:
        fail("Config", f"oocode.json no encontrado: {CONFIG_FILE}")

    _ws_path = Path(config.workspace).expanduser()
    if _ws_path.exists():
        ok("Config", f"Workspace  [dim]{_ws_path}[/dim]")
    else:
        warn("Config", f"Workspace no existe: {_ws_path}")

    if config.project_dir:
        _pd = Path(config.project_dir)
        ok("Config", f"Proyecto  [dim]{_pd}[/dim]  "
                     + ("[green]OOCODE.md[/green]" if (_pd / "OOCODE.md").exists() else "[dim]sin OOCODE.md[/dim]"))

    _oocode_warn = config.oocode_md_warning()
    if _oocode_warn:
        warn("Config", _oocode_warn)

    if log.is_enabled():
        ok("Config", f"Log activo  [dim]{log.log_file_path()}[/dim]")
    else:
        warn("Config", "Logging desactivado  [dim](logging.enabled=false)[/dim]")

    if config.chatlog_enabled:
        _cl_path = getattr(agent_loop.chatlog, "_path", "~/.oocode/logs/chat.log")
        ok("Config", f"Chatlog activo  [dim]{_cl_path}[/dim]")
    else:
        warn("Config", "Chatlog desactivado  [dim](chatlog.enabled=false en oocode.json)[/dim]")

    # ── 11. Plugins ───────────────────────────────────────────────────────────
    if agent_loop.plugins is not None:
        _pm = agent_loop.plugins
        _loaded_p = _pm._loaded
        if _loaded_p:
            for _pname, _pmod in _loaded_p.items():
                _pver   = getattr(_pmod, "VERSION", "?")
                _ptools = getattr(_pmod, "TOOLS", [])
                ok("Plugins", f"[cyan]{_pname}[/cyan] v{_pver}  [dim]{len(_ptools)} tools propias[/dim]")
        else:
            _penabled = sorted(_pm._enabled)
            if _penabled:
                warn("Plugins", f"Habilitados pero no cargados: {', '.join(_penabled)}")
            else:
                warn("Plugins", "Ningún plugin activo  [dim](/plugins enable <nombre>)[/dim]")
    else:
        warn("Plugins", "PluginManager no inicializado")

    # ── 12. Skills ────────────────────────────────────────────────────────────
    if agent_loop.skills is not None:
        _sm = agent_loop.skills
        _senabled = sorted(_sm._enabled)
        if _senabled:
            ok("Skills", f"Activos: {', '.join(_senabled)}")
        else:
            warn("Skills", "Ningún skill activo  [dim](/skills enable <nombre>)[/dim]")
    else:
        warn("Skills", "SkillManager no inicializado")

    # ── 13. Herramientas del sistema ──────────────────────────────────────────
    _enabled_plugins = set(agent_loop.plugins._enabled) if agent_loop.plugins else set()

    if "clipboard" in _enabled_plugins:
        if _env_os.environ.get("WAYLAND_DISPLAY"):
            if _which("wl-copy"):
                ok("Plugins-Tools", "wl-copy  [dim]portapapeles Wayland[/dim]")
            else:
                fail("Plugins-Tools", "wl-copy no encontrado  [dim]apt install wl-clipboard[/dim]")
        else:
            _clip = "xclip" if _which("xclip") else ("xsel" if _which("xsel") else None)
            if _clip:
                ok("Plugins-Tools", f"{_clip}  [dim]portapapeles X11[/dim]")
            else:
                fail("Plugins-Tools", "xclip/xsel no encontrado  [dim]apt install xclip[/dim]")

    if "test_runner" in _enabled_plugins:
        _runners = [b for b in ("pytest", "jest", "go", "cargo") if _which(b)]
        if _runners:
            ok("Plugins-Tools", f"test runners: {', '.join(_runners)}")
        else:
            warn("Plugins-Tools", "Sin test runners  [dim]instala pytest, jest, go o cargo[/dim]")

    if "vault" in _enabled_plugins:
        _vault_file = Path.home() / ".oocode" / "vault.enc"
        try:
            import cryptography  # noqa: F401
            _crypto_ok = True
        except ImportError:
            _crypto_ok = False
        if not _crypto_ok:
            fail("Plugins-Tools", "cryptography no instalado  [dim]pip install cryptography[/dim]")
        elif _vault_file.exists():
            _vperms = oct(_vault_file.stat().st_mode)[-3:]
            ok("Plugins-Tools", f"vault.enc  [dim]permisos {_vperms}[/dim]")
        else:
            warn("Plugins-Tools", f"Vault no creado  [dim]/vault init[/dim]")

    _TOOL_CMDS = [
        # (cmd,          descripción,                        opcional)
        ("git",          "git_status/diff/commit/…",         False),
        ("docker",       "docker_ps/logs/exec/…",            True),
        ("rg",           "grep_code — ripgrep",              True),
        ("strace",       "strace_run",                       True),
        ("gdb",          "gdb_run",                          True),
        ("valgrind",     "valgrind_run",                     True),
        ("make",         "make_run",                         False),
        ("cmake",        "make_run CMake",                   True),
        ("patch",        "patch_apply",                      False),
        ("tar",          "archive_extract/create",           False),
        ("unzip",        "archive_extract ZIP",              False),
        ("zip",          "archive_create ZIP",               True),
        ("cloc",         "count_lines",                      True),
        ("tokei",        "count_lines alternativa",          True),
        ("node",         "npm_tool / run_script JS",         True),
        ("npm",          "npm_tool",                         True),
        ("python3",      "python_exec / pdb_run",            False),
        ("pip",          "pip_tool",                         False),
        ("ctags",        "build_symbol_index",               True),
        ("jq",           "json_format",                      True),
        ("nc",           "port_check",                       True),
        ("curl",         "http_get",                         True),
    ]
    for _cmd, _desc, _opt in _TOOL_CMDS:
        _p = _which(_cmd)
        if _p:
            ok("Tools", f"{_cmd}  [dim]{_desc}[/dim]")
        elif _opt:
            warn("Tools", f"{_cmd} no encontrado  [dim]{_desc}[/dim]")
        else:
            fail("Tools", f"{_cmd} no encontrado  [dim]{_desc}[/dim]")

    # ── 14. Paquetes Python ───────────────────────────────────────────────────
    _OPTIONAL_PY_PKGS = [
        ("tree_sitter",           "tree_sitter plugin — extracción AST"),
        ("tree_sitter_c",         "tree_sitter plugin — soporte C"),
        ("tree_sitter_cpp",       "tree_sitter plugin — soporte C++"),
        ("chromadb",              "embeddings_search plugin"),
        ("sentence_transformers", "embeddings locales"),
        ("ruff",                  "linter Python"),
    ]
    for _pkg in _REQUIRED_PACKAGES:
        try:
            _ver = importlib.metadata.version(_pkg)
            ok("Python", f"{_pkg} {_ver}")
        except importlib.metadata.PackageNotFoundError:
            fail("Python", f"{_pkg} no instalado  [dim]pip install {_pkg}[/dim]")
    for _pkg, _desc in _OPTIONAL_PY_PKGS:
        try:
            _ver = importlib.metadata.version(_pkg)
            ok("Python (opcional)", f"{_pkg} {_ver}")
        except importlib.metadata.PackageNotFoundError:
            warn("Python (opcional)", f"{_pkg} no instalado  [dim]{_desc}[/dim]")

    # ── 15. Servidores MCP bundled — dependencias opcionales ─────────────────
    _any_extra_mcp = any([
        getattr(config, "mcp_iot_assistant_enabled", False),
        getattr(config, "mcp_security_assistant_enabled", False),
        getattr(config, "mcp_word_assistant_enabled", False),
        getattr(config, "mcp_excel_assistant_enabled", False),
        getattr(config, "mcp_pptx_assistant_enabled", False),
    ])
    if _any_extra_mcp:
        # (display_name, [metadata_names_to_try], import_fallback, description)
        _IOT_PY_PKGS = [
            ("kasa",     ["kasa"],           "kasa",           "IoT MCP — TAPO luces/enchufes TP-Link  (sudo apt install python3-kasa)"),
            ("blinkpy",  ["blinkpy"],        "blinkpy",        "IoT MCP — cámaras Blink/Amazon Ring   (sudo apt install python3-blinkpy)"),
            ("aiohttp",  ["aiohttp"],        "aiohttp",        "IoT MCP — HTTP async (requerido por blinkpy)"),
            ("tinytuya", ["tinytuya"],       "tinytuya",       "IoT MCP — dispositivos Tuya/Smart Life  (pip install tinytuya)"),
            ("paho",     ["paho-mqtt"],      "paho.mqtt",      "IoT MCP — broker MQTT  (sudo apt install python3-paho-mqtt)"),
        ]
        _HO_PY_PKGS = [
            ("openpyxl",   ["openpyxl"],            "openpyxl",   "Home Office MCP — hojas de cálculo Excel   pip install openpyxl"),
            ("docx",       ["python-docx"],          "docx",       "Home Office MCP — documentos .docx         pip install python-docx"),
            ("pptx",       ["python-pptx"],          "pptx",       "Home Office MCP — presentaciones .pptx     pip install python-pptx"),
            ("matplotlib", ["matplotlib"],           "matplotlib", "Home Office MCP — gráficas dinámicas       pip install matplotlib"),
            ("markdown",   ["Markdown", "markdown"], "markdown",   "Home Office MCP — Markdown→HTML             pip install markdown"),
        ]

        def _pkg_ok(names: list, import_path: str) -> tuple[bool, str]:
            for n in names:
                try:
                    ver = importlib.metadata.version(n)
                    return True, ver
                except importlib.metadata.PackageNotFoundError:
                    pass
            try:
                importlib.import_module(import_path.split(".")[0])
                return True, "apt"
            except ImportError:
                return False, ""
        _SEC_CLI = [
            ("nmap",       "Security MCP — escaneo de puertos",      "apt install nmap"),
            ("nikto",      "Security MCP — análisis web",            "apt install nikto  ||  git clone https://github.com/sullo/nikto"),
            ("gobuster",   "Security MCP — fuerza bruta dirs",       "apt install gobuster"),
            ("hashcat",    "Security MCP — cracking de hashes",      "apt install hashcat"),
            ("whois",      "Security MCP — info de dominio",         "apt install whois"),
            ("dig",        "Security MCP — consultas DNS",           "apt install dnsutils"),
            ("openssl",    "Security MCP — certificados y crypto",   "apt install openssl"),
            ("trufflehog", "Security MCP — secrets en git",          "pip install trufflehog"),
            ("gitleaks",   "Security MCP — secrets en código",       "https://github.com/gitleaks/gitleaks"),
            ("steghide",   "Security MCP — esteganografía",          "apt install steghide"),
            ("xxd",        "Security MCP — hex dump",                "apt install xxd"),
        ]
        _IOT_CLI = [
            ("avahi-browse", "IoT MCP — descubrimiento mDNS",        "apt install avahi-utils"),
        ]
        _HO_CLI = [
            ("pandoc",    "Home Office MCP — conversión de documentos", "apt install pandoc"),
            ("tesseract", "Home Office MCP — OCR imagen→texto",         "apt install tesseract-ocr"),
            ("pdftotext", "Home Office MCP — texto desde PDF",          "apt install poppler-utils"),
        ]

        if getattr(config, "mcp_iot_assistant_enabled", False):
            for _pkg, _meta, _imp, _desc in _IOT_PY_PKGS:
                _found, _ver = _pkg_ok(_meta, _imp)
                if _found:
                    ok("IoT MCP Python", f"{_pkg} {_ver}")
                else:
                    warn("IoT MCP Python", f"{_pkg} no instalado  [dim]{_desc}[/dim]")
            for _cmd, _desc, _inst in _IOT_CLI:
                if _which(_cmd):
                    ok("IoT MCP Tools", f"{_cmd}  [dim]{_desc}[/dim]")
                else:
                    warn("IoT MCP Tools", f"{_cmd} no encontrado  [dim]{_desc}  →  {_inst}[/dim]")

        if getattr(config, "mcp_security_assistant_enabled", False):
            for _cmd, _desc, _inst in _SEC_CLI:
                if _which(_cmd):
                    ok("Security MCP Tools", f"{_cmd}  [dim]{_desc}[/dim]")
                else:
                    warn("Security MCP Tools", f"{_cmd} no encontrado  [dim]{_desc}  →  {_inst}[/dim]")

        if any(getattr(config, f"mcp_{_s}_assistant_enabled", False) for _s in ("word", "excel", "pptx")):
            for _pkg, _meta, _imp, _desc in _HO_PY_PKGS:
                _found, _ver = _pkg_ok(_meta, _imp)
                if _found:
                    ok("Office MCP Python", f"{_pkg} {_ver}")
                else:
                    warn("Office MCP Python", f"{_pkg} no instalado  [dim]{_desc}[/dim]")
            for _cmd, _desc, _inst in _HO_CLI:
                if _which(_cmd):
                    ok("Office MCP Tools", f"{_cmd}  [dim]{_desc}[/dim]")
                else:
                    warn("Office MCP Tools", f"{_cmd} no encontrado  [dim]{_desc}  →  {_inst}[/dim]")

    # ── 16. WebUI ────────────────────────────────────────────────────────────────
    if getattr(config, "webui_enabled", False):
        ok("WebUI", f"Activo en http://{config.webui_host}:{config.webui_port}")
    else:
        warn("WebUI", "Desactivado  [dim](/webserver start)[/dim]")

    # ── 17. Sesiones ──────────────────────────────────────────────────────────
    try:
        from agent.session import SESSIONS_ROOT as _SR
        if _SR.exists():
            _adirs = [d for d in _SR.iterdir() if d.is_dir()]
            _tsess = sum(len(list(d.glob("*.jsonl"))) for d in _adirs)
            ok("Sesiones", f"Directorio OK  [dim]{_SR}[/dim]  ({_tsess} sesiones en {len(_adirs)} agente(s))")
        else:
            warn("Sesiones", f"Directorio no existe  [dim]{_SR}[/dim]  (se creará al iniciar)")
    except Exception as _se:
        warn("Sesiones", f"No se pudo verificar: {_se}")

    # ── 18. Visión / portapapeles ─────────────────────────────────────────────
    _clip_ok = False
    for _vc, _vd, _vi in [
        ("xclip",    "portapapeles X11 — Ctrl+P en TUI",    "apt install xclip"),
        ("xsel",     "portapapeles X11 alternativo",         "apt install xsel"),
        ("wl-paste", "portapapeles Wayland — Ctrl+P en TUI", "apt install wl-clipboard"),
    ]:
        if _which(_vc):
            ok("Vision / Portapapeles", f"{_vc}  [dim]{_vd}[/dim]")
            _clip_ok = True
    if not _clip_ok:
        warn("Vision / Portapapeles",
             "Sin herramienta de portapapeles  [dim]apt install xclip  (X11) o apt install wl-clipboard  (Wayland)[/dim]")
    try:
        _pil = importlib.metadata.version("Pillow")
        ok("Vision / Portapapeles", f"Pillow {_pil}  [dim]procesamiento de imágenes[/dim]")
    except importlib.metadata.PackageNotFoundError:
        warn("Vision / Portapapeles",
             "Pillow no instalado (opcional)  [dim]pip install Pillow[/dim]")

    # ── Renderizado ───────────────────────────────────────────────────────────
    _ICONS = {"ok": "[green]✓[/green]", "warn": "[yellow]⚠[/yellow]", "fail": "[red]✗[/red]"}
    _current_sec = ""
    for _sec, _status, _msg in checks:
        if _sec != _current_sec:
            console.print(f"  [bold dim]{_sec}[/bold dim]")
            _current_sec = _sec
        console.print(f"    {_ICONS[_status]}  {_msg}")

    n_ok   = sum(1 for _, s, _ in checks if s == "ok")
    n_warn = sum(1 for _, s, _ in checks if s == "warn")
    n_fail = sum(1 for _, s, _ in checks if s == "fail")
    console.print()
    console.print(
        f"  [dim]Resultado:[/dim]  "
        f"[green]{n_ok} OK[/green]  "
        f"[yellow]{n_warn} avisos[/yellow]  "
        f"[red]{n_fail} errores[/red]"
    )
    console.print()


# ── /config panel ─────────────────────────────────────────────────────────────

def _fetch_models_list(config) -> list[dict]:
    """Obtiene modelos del servidor Ollama. Devuelve lista de dicts.

    Solo el backend Ollama expone un listado de modelos; openai/anthropic no, así
    que se devuelve [] (el llamador permite introducir el nombre de modelo a mano).
    """
    if getattr(config, "api_type", "ollama") != "ollama":
        return []
    try:
        from api.ollama import list_ollama_models
        return list_ollama_models(config.ollama_host)
    except Exception as e:
        console.print(f"  [red]✗[/red]  No se puede conectar con Ollama: {e}")
        return []


def _fetch_model_info(config, model_name: str) -> dict:
    """Obtiene info de un modelo concreto vía la capa única api.ollama."""
    from api.ollama import model_info
    try:
        return model_info(config.ollama_host, model_name)
    except Exception as e:
        console.print(f"  [dim]No se pudo obtener info del modelo: {e}[/dim]")
        return {"params": {}, "details": {}, "modelinfo": {}}


def _cmd_config_panel(args: str, config, rt: RuntimeSettings) -> None:
    if not args or args == "show":
        print_config_full(config)
        print_runtime(rt)
        return

    if args != "edit":
        console.print("  [yellow]Uso:[/yellow]  /config  |  /config edit")
        return

    console.print()
    console.print("  [bold cyan]Editor de configuración[/bold cyan]  [dim](Enter = mantener valor actual)[/dim]")
    console.print()

    def _ask(label: str, current) -> str:
        return _tui_ask(label, default=str(current)).strip()

    def _ask_int(label: str, current: int) -> int:
        val = _ask(label, current)
        try:
            return int(val)
        except ValueError:
            return current

    def _ask_float(label: str, current: float) -> float:
        val = _ask(label, current)
        try:
            return float(val)
        except ValueError:
            return current

    # ── Modelo del agente ──────────────────────────────────────────────────────
    console.print("  [bold dim]── Modelo ──[/bold dim]")
    console.print(f"  Modelo actual: [bold cyan]{config.model or '(sin seleccionar)'}[/bold cyan]")

    models = _fetch_models_list(config)
    if models:
        # Tabla compacta con índice
        from rich.table import Table
        from rich import box as rbox
        t = Table(box=rbox.SIMPLE, show_header=True, padding=(0, 1))
        t.add_column("#",        style="dim cyan",  width=4,  justify="right")
        t.add_column("Nombre",   style="white",     width=40)
        t.add_column("Familia",  style="dim",       width=14)
        t.add_column("Tamaño",   style="dim",       width=9,  justify="right")
        t.add_column("Quant.",   style="dim")
        for i, m in enumerate(models, 1):
            det     = m.get("details", {}) or {}
            family  = det.get("family", "")
            quant   = det.get("quantization_level", "") or det.get("quantization", "")
            size_gb = m.get("size", 0) / 1e9
            marker  = "[bold cyan]▶[/bold cyan] " if m["name"] == config.model else "  "
            t.add_row(str(i), f"{marker}{m['name']}", family, f"{size_gb:.1f} GB", quant)
        console.print(t)

        raw_choice = _tui_ask(
            "Selecciona modelo (número, nombre o Enter para mantener)", default=""
        ).strip()
        if raw_choice:
            if raw_choice.isdigit():
                idx = int(raw_choice) - 1
                if 0 <= idx < len(models):
                    raw_choice = models[idx]["name"]
                else:
                    console.print("  [yellow]Número fuera de rango. Se mantiene el modelo actual.[/yellow]")
                    raw_choice = ""
            if raw_choice:
                config.model = raw_choice
                console.print(f"  [green]✓[/green]  Modelo → [bold cyan]{config.model}[/bold cyan]")

                # Mostrar info básica + auto-detectar y guardar config por modelo
                minfo    = _fetch_model_info(config, config.model)
                details  = minfo.get("details", {})
                if details:
                    family       = details.get("family", "")
                    quant        = details.get("quantization_level", "") or details.get("quantization", "")
                    params_count = details.get("parameter_size", "")
                    console.print(
                        f"  [dim]Familia:[/dim] {family}  "
                        f"[dim]Parámetros:[/dim] {params_count}  "
                        f"[dim]Quantización:[/dim] {quant}"
                    )
                _auto_detect_model_config(config, config.model)

    else:
        # Sin conexión — solo permite teclear nombre
        raw_choice = _tui_ask(
            "Nombre del modelo (Enter para mantener actual)", default=config.model or ""
        ).strip()
        if raw_choice and raw_choice != config.model:
            config.model = raw_choice
            console.print(f"  [green]✓[/green]  Modelo → [bold cyan]{config.model}[/bold cyan]")

    # ── Defaults globales de modelos (models.repeatPenalty / seed) ────────────
    # Aplican a todos los modelos si no tienen repeat_penalty/seed en params.
    console.print()
    console.print(
        "  [bold dim]── Defaults globales de modelos[/bold dim]  "
        "[dim](aplican si el modelo no los define | Enter = mantener | «-» = quitar)[/dim]"
    )

    def _ask_opt(label: str, current_val, cast_fn):
        """Pide valor opcional. Devuelve None si se escribe '-', cast_fn(val) si hay valor, o current_val."""
        default_str = str(current_val) if current_val is not None else "(default)"
        val = _tui_ask(label, default=default_str).strip()
        if val == "-" or val == "(default)":
            return None
        if val == default_str and current_val is None:
            return None
        try:
            return cast_fn(val)
        except (ValueError, TypeError):
            return current_val

    config.model_repeat_penalty = _ask_opt("repeat_penalty (1.0=sin penalización)", config.model_repeat_penalty, float)
    config.model_seed           = _ask_opt("seed           (-1=aleatorio)", config.model_seed, int)

    console.print("  [bold dim]── Parámetros por modelo ──[/bold dim]")
    if config.active_model_config:
        m_cfg    = config.active_model_config
        m_params = m_cfg.get("params", {})
        hist_t   = config.effective_max_context_tokens
        console.print(
            f"  [dim]Modelo:[/dim] [cyan]{config.model}[/cyan]  "
            f"[dim]historial efectivo: [white]{hist_t:,}[/white] tokens[/dim]"
        )
        new_ctx  = _ask_int("  contextWindow (num_ctx Ollama)", m_cfg.get("contextWindow", 8192))
        new_out  = _ask_int("  maxTokens     (salida máxima)", m_cfg.get("maxTokens", 2048))
        new_temp = _ask_opt("  temperature   (0.0–2.0)", m_params.get("temperature"), float)
        new_topp = _ask_opt("  top_p         (0.0–1.0)", m_params.get("top_p"), float)
        new_topk = _ask_opt("  top_k         (entero ≥1)", m_params.get("top_k"), int)
        new_pred = _ask_opt("  num_predict   (-1=∞)", m_params.get("num_predict"), int)
        new_pen  = _ask_opt("  repeat_penalty (1.0=sin penalización)", m_params.get("repeat_penalty"), float)
        new_seed = _ask_opt("  seed          (-1=aleatorio)", m_params.get("seed"), int)
        extra: dict = {}
        for k, v in [
            ("temperature",    new_temp),
            ("top_p",          new_topp),
            ("top_k",          new_topk),
            ("num_predict",    new_pred),
            ("repeat_penalty", new_pen),
            ("seed",           new_seed),
        ]:
            if v is not None:
                extra[k] = v
        new_timeout = _ask_int(
            "  timeoutSeconds (timeout del modelo, 0=sin timeout)",
            config.model_configs.get(config.model, {}).get("timeoutSeconds", config.fallback_timeout),
        )
        config.set_model_config(config.model, new_ctx, new_out, extra_params=extra)
        config.model_configs[config.model]["timeoutSeconds"] = new_timeout
    else:
        console.print(f"  [dim](Sin config per-modelo — usa /model {config.model or '<nombre>'} para detectar)[/dim]")

    console.print("  [bold dim]── Contexto y compactación ──[/bold dim]")
    config.compact_min_keep       = _ask_int("minKeep (mensajes mínimos)", config.compact_min_keep)
    config.compact_threshold      = _ask_float("compactThreshold (0.0–1.0)", config.compact_threshold)
    config.max_summary_chars      = _ask_int("maxSummaryChars", config.max_summary_chars)
    config.max_tool_result_tokens = _ask_int("maxToolResultTokens", config.max_tool_result_tokens)
    config.auto_continue_max      = _ask_int("autoContinueMax (0=desactivado; 12+ para tareas largas)", config.auto_continue_max)

    console.print()
    console.print("  [bold dim]── Embeddings ──[/bold dim]")
    config.embed_model                = _ask("modelo de embeddings", config.embed_model)
    config.embed_max_input_chars      = _ask_int("maxInputChars (chars máximos de texto a embedar, 8000 recomendado)", config.embed_max_input_chars)
    config.embed_similarity_threshold = _ask_float("similarityThreshold (0.0–1.0)", config.embed_similarity_threshold)
    config.embed_top_k                = _ask_int("topK", config.embed_top_k)
    config.embed_snippet_chars        = _ask_int("snippetChars", config.embed_snippet_chars)
    _mee = _ask("memoryEmbedEnabled — indexar memorias por vectores (true/false)",
                "true" if getattr(config, "memory_embed_enabled", True) else "false")
    config.memory_embed_enabled       = _mee.lower() in ("true", "s", "si", "sí", "yes", "1")

    console.print()
    console.print("  [bold dim]── Herramientas ──[/bold dim]")
    config.read_file_lines_default    = _ask_int("readFileLinesDefault", config.read_file_lines_default)
    config.read_file_lines_warn_large = _ask_int("readFileLinesWarnLarge", config.read_file_lines_warn_large)
    config.web_fetch_max_chars        = _ask_int("webFetchMaxChars", config.web_fetch_max_chars)
    config.bash_max_output_chars      = _ask_int("bashMaxOutputChars", config.bash_max_output_chars)

    console.print()
    console.print("  [bold dim]── Workspace ──[/bold dim]")
    config.ws_max_memory_lines = _ask_int("maxMemoryLines", config.ws_max_memory_lines)
    config.ws_max_daily_chars  = _ask_int("maxDailyChars", config.ws_max_daily_chars)

    console.print()
    console.print("  [bold dim]── SearXNG ──[/bold dim]")
    config.searxng_url         = _ask("URL de la instancia SearXNG (vacío = desactivado)", config.searxng_url)
    _en = _ask("reemplazar web_search con SearXNG (true/false)", "true" if config.searxng_enabled else "false")
    config.searxng_enabled     = _en.lower() in ("true", "s", "si", "sí", "yes", "1")
    config.searxng_max_results = _ask_int("maxResults", config.searxng_max_results)
    config.searxng_categories  = _ask("categories (general, news, science, it, images...)", config.searxng_categories)
    config.searxng_language    = _ask("language (auto, es, en, fr...)", config.searxng_language)
    config.searxng_safe_search = _ask_int("safeSearch (0=off, 1=moderate, 2=strict)", config.searxng_safe_search)
    config.searxng_timeout     = _ask_int("timeout (segundos)", config.searxng_timeout)

    console.print()
    console.print("  [bold dim]── Logging ──[/bold dim]")
    _log_en = _ask("activado (true/false)", "true" if config.log_enabled else "false")
    config.log_enabled   = _log_en.lower() in ("true", "s", "si", "sí", "yes", "1")
    config.log_level     = _tui_ask(
        "nivel", choices=["debug", "info", "warn", "error"], default=config.log_level
    )
    config.log_file      = _ask("fichero (vacío = ~/.oocode/logs/oocode.log)", config.log_file)
    config.log_max_size  = _ask_int("maxSizeMb", config.log_max_size)
    config.log_max_files = _ask_int("maxFiles (ficheros rotados)", config.log_max_files)

    console.print()
    console.print("  [bold dim]── Fallback (modelo de reserva por timeout) ──[/bold dim]")
    _fb_en = _ask("enabled (true/false)", "true" if config.fallback_enabled else "false")
    config.fallback_enabled = _fb_en.lower() in ("true", "s", "si", "sí", "yes", "1")
    _prev_fb_model          = config.fallback_model
    config.fallback_model   = _ask("modelo fallback  (p.ej. phi3:mini, vacío = desactivado)", config.fallback_model)
    config.fallback_timeout = _ask_int("timeoutSeconds   (segundos sin tokens)", config.fallback_timeout)
    # Auto-detectar config del modelo fallback si cambió o no tiene entrada aún
    if config.fallback_model and (
        config.fallback_model != _prev_fb_model
        or config.fallback_model not in config.model_configs
    ):
        console.print(
            f"  [dim]↳ detectando config de fallback [cyan]{config.fallback_model}[/cyan]…[/dim]"
        )
        _auto_detect_model_config(config, config.fallback_model)

    console.print()
    console.print("  [bold dim]── Permisos de herramientas ──[/bold dim]")
    console.print("  [dim](auto = siempre, ask = preguntar, deny = bloquear)[/dim]")
    for tool in sorted(config.permissions):
        current = config.permissions[tool]
        val = _tui_ask(f"  {tool}", choices=["auto", "ask", "deny"], default=current)
        config.permissions[tool] = val

    # ── Opciones de plugins ────────────────────────────────────────────────────
    plugin_opts = getattr(config, "plugin_options", {})
    if plugin_opts:
        console.print()
        console.print("  [bold dim]── Opciones de plugins ──[/bold dim]")
        for plugin_name, opts in sorted(plugin_opts.items()):
            console.print(f"  [dim]{plugin_name}:[/dim]")
            for key, val in sorted(opts.items()):
                if isinstance(val, bool):
                    raw = _tui_ask(f"    {key} (true/false)", default="true" if val else "false")
                    plugin_opts[plugin_name][key] = raw.lower() in ("true", "s", "si", "sí", "yes", "1")
                elif isinstance(val, int):
                    plugin_opts[plugin_name][key] = _ask_int(f"    {key}", val)
                else:
                    plugin_opts[plugin_name][key] = _ask(f"    {key}", val)
        config.plugin_options = plugin_opts

    # ── RAG ───────────────────────────────────────────────────────────────────
    console.print()
    console.print("  [bold dim]── RAG automático (workspace auto-inject) ──[/bold dim]")
    _rag_en = _ask("enabled (true/false)", "true" if config.rag_enabled else "false")
    config.rag_enabled = _rag_en.lower() in ("true", "s", "si", "sí", "yes", "1")
    config.rag_top_k = _ask_int("topK (fragmentos por turno)", config.rag_top_k)
    config.rag_similarity_threshold = _ask_float(
        "similarityThreshold (0.0–1.0, min relevancia)", config.rag_similarity_threshold
    )
    config.rag_max_snippet_chars = _ask_int(
        "maxSnippetChars (chars totales inyectados)", config.rag_max_snippet_chars
    )
    config.rag_index_interval = _ask_float(
        "indexInterval (segundos entre re-indexaciones)", config.rag_index_interval
    )
    console.print("  [dim]Boost para queries largas/complejas (mensaje ≥complexMinChars o multi-fichero):[/dim]")
    config.rag_top_k_complex = _ask_int(
        "topKComplex (top_k boost para queries complejas)", config.rag_top_k_complex
    )
    config.rag_threshold_complex = _ask_float(
        "thresholdComplex (threshold boost, más permisivo)", config.rag_threshold_complex
    )
    config.rag_complex_min_chars = _ask_int(
        "complexMinChars (longitud mínima del mensaje para boost)", config.rag_complex_min_chars
    )

    # ── MCP ───────────────────────────────────────────────────────────────────
    console.print()
    console.print("  [bold dim]── MCP (Model Context Protocol) ──[/bold dim]")
    config.mcp_request_timeout = _ask_float(
        "requestTimeout (segundos por llamada MCP)", config.mcp_request_timeout
    )
    _oa_en = _ask(
        "oocodeAssistant.enabled — servidor MCP bundled principal (true/false)",
        "true" if config.mcp_oocode_assistant_enabled else "false",
    )
    config.mcp_oocode_assistant_enabled = _oa_en.lower() in ("true", "s", "si", "sí", "yes", "1")
    _sa_en = _ask(
        "systemAssistant.enabled — servidor MCP bundled sistema (true/false)",
        "true" if config.mcp_system_assistant_enabled else "false",
    )
    config.mcp_system_assistant_enabled = _sa_en.lower() in ("true", "s", "si", "sí", "yes", "1")
    _word_en = _ask(
        "wordAssistant.enabled — servidor MCP documentos Word/PDF + núcleo O365 (true/false)",
        "true" if getattr(config, "mcp_word_assistant_enabled", False) else "false",
    )
    config.mcp_word_assistant_enabled = _word_en.lower() in ("true", "s", "si", "sí", "yes", "1")
    _excel_en = _ask(
        "excelAssistant.enabled — servidor MCP hojas de cálculo .xlsx/CSV (true/false)",
        "true" if getattr(config, "mcp_excel_assistant_enabled", False) else "false",
    )
    config.mcp_excel_assistant_enabled = _excel_en.lower() in ("true", "s", "si", "sí", "yes", "1")
    _pptx_en = _ask(
        "pptxAssistant.enabled — servidor MCP presentaciones .pptx (true/false)",
        "true" if getattr(config, "mcp_pptx_assistant_enabled", False) else "false",
    )
    config.mcp_pptx_assistant_enabled = _pptx_en.lower() in ("true", "s", "si", "sí", "yes", "1")
    _mail_en = _ask(
        "mailAssistant.enabled — servidor MCP email/calendario/notas/contactos (true/false)",
        "true" if getattr(config, "mcp_mail_assistant_enabled", False) else "false",
    )
    config.mcp_mail_assistant_enabled = _mail_en.lower() in ("true", "s", "si", "sí", "yes", "1")
    _cmdb_en = _ask(
        "cmdbAssistant.enabled — servidor MCP inventario IT/CMDB (true/false)",
        "true" if getattr(config, "mcp_cmdb_assistant_enabled", False) else "false",
    )
    config.mcp_cmdb_assistant_enabled = _cmdb_en.lower() in ("true", "s", "si", "sí", "yes", "1")
    _sec_en = _ask(
        "securityAssistant.enabled — servidor MCP seguridad/recon/CTF (true/false)",
        "true" if getattr(config, "mcp_security_assistant_enabled", False) else "false",
    )
    config.mcp_security_assistant_enabled = _sec_en.lower() in ("true", "s", "si", "sí", "yes", "1")
    _iot_en = _ask(
        "iotAssistant.enabled — servidor MCP IoT TAPO/Blink/Alexa/HA/MQTT (true/false)",
        "true" if getattr(config, "mcp_iot_assistant_enabled", False) else "false",
    )
    config.mcp_iot_assistant_enabled = _iot_en.lower() in ("true", "s", "si", "sí", "yes", "1")
    if config.mcp_servers:
        srv_summary = "  ".join(
            f"[cyan]{s.get('name', '?')}[/cyan]" for s in config.mcp_servers
        )
        console.print(
            f"  [dim]Servidores externos ({len(config.mcp_servers)}):[/dim] {srv_summary}  "
            "[dim](editar mcp.servers en oocode.json)[/dim]"
        )
    else:
        console.print("  [dim]Sin servidores MCP externos (mcp.servers en oocode.json).[/dim]")

    # ── Hooks ─────────────────────────────────────────────────────────────────
    console.print()
    console.print("  [bold dim]── Hooks PreToolUse/PostToolUse ──[/bold dim]")
    _h_en = _ask("enabled (true/false)", "true" if config.hooks_enabled else "false")
    config.hooks_enabled = _h_en.lower() in ("true", "s", "si", "sí", "yes", "1")
    try:
        from tools.hooks import HookManager as _HM
        _available_builtins = ", ".join(_HM.available_builtins())
    except Exception:
        _available_builtins = "lint_after_write, autoformat_after_write, backup_before_write, check_secrets, log_tool_calls"
    _cur_builtins = ", ".join(config.hooks_builtins) or "(ninguno)"
    console.print(f"  [dim]Disponibles: {_available_builtins}[/dim]")
    _b_raw = _ask(
        f"builtins activos (separados por coma, vacío=ninguno)", _cur_builtins
    )
    config.hooks_builtins = (
        [b.strip() for b in _b_raw.split(",") if b.strip()]
        if _b_raw and _b_raw != "(ninguno)" else []
    )

    # ── Snapshots ─────────────────────────────────────────────────────────────
    console.print()
    console.print("  [bold dim]── Snapshots de sesión ──[/bold dim]")
    _sn_en = _ask("enabled (true/false)", "true" if config.snapshots_enabled else "false")
    config.snapshots_enabled = _sn_en.lower() in ("true", "s", "si", "sí", "yes", "1")
    config.snapshots_max = _ask_int(
        "maxSnapshots (máximo a conservar por agente)", config.snapshots_max
    )
    _sc_en = _ask(
        "saveOnCompact (guardar también al compactar) (true/false)",
        "true" if config.snapshots_save_on_compact else "false"
    )
    config.snapshots_save_on_compact = _sc_en.lower() in ("true", "s", "si", "sí", "yes", "1")

    # ── LSP (pluginOptions.lsp) ───────────────────────────────────────────────
    console.print()
    lsp_enabled = "lsp" in config.plugins_enabled
    lsp_marker  = "[green]activo[/green]" if lsp_enabled else "[dim]inactivo — /plugins enable lsp[/dim]"
    console.print(f"  [bold dim]── LSP (Language Server Protocol)[/bold dim]  {lsp_marker}")
    lsp_opts = config.plugin_options.get("lsp", {})
    lsp_to = _ask_float("requestTimeout (s)", float(lsp_opts.get("requestTimeout", 10)))
    # Sanear antes de usar: autoStart debe ser lista, serverCmds debe ser dict
    _lsp_as_val = lsp_opts.get("autoStart", [])
    if not isinstance(_lsp_as_val, list):
        _lsp_as_val = []
    _lsp_as_val = [s for s in _lsp_as_val if isinstance(s, str)]
    _lsp_srv = lsp_opts.get("serverCmds", {})
    if not isinstance(_lsp_srv, dict):
        _lsp_srv = {}
    lsp_as_raw = _ask(
        "autoStart (extensiones separadas por coma, p.ej. .py,.ts)",
        ", ".join(_lsp_as_val)
    )
    lsp_as = [e.strip() for e in lsp_as_raw.split(",") if e.strip()]
    config.plugin_options["lsp"] = {
        **lsp_opts,
        "requestTimeout": lsp_to,
        "serverCmds":     _lsp_srv,
        "autoStart":      lsp_as,
    }

    # ── Herramientas — code_search ─────────────────────────────────────────────
    console.print()
    console.print("  [bold dim]── code_search ──[/bold dim]")
    config.code_search_max_results   = _ask_int(
        "codeSearchMaxResults (resultados máx.)", config.code_search_max_results
    )
    config.code_search_context_lines = _ask_int(
        "codeSearchContextLines (líneas contexto)", config.code_search_context_lines
    )
    config.code_search_max_filesize  = _ask(
        "codeSearchMaxFilesize (tamaño máx. rg, ej. 500K)", config.code_search_max_filesize
    )

    # ── Caché de herramientas ──────────────────────────────────────────────────
    console.print()
    console.print("  [bold dim]── Caché de herramientas ──[/bold dim]")
    _tc_en = _ask("toolCacheEnabled (true/false)", "true" if config.tool_cache_enabled else "false")
    config.tool_cache_enabled  = _tc_en.lower() in ("true", "s", "si", "sí", "yes", "1")
    config.tool_cache_max_size = _ask_int("toolCacheMaxSize (entradas máx)", config.tool_cache_max_size)

    # ── Visión (imágenes) ──────────────────────────────────────────────────────
    console.print()
    console.print("  [bold dim]── Visión (imágenes) ──[/bold dim]")
    _vis_en = _ask("visionEnabled (true/false)", "true" if config.vision_enabled else "false")
    config.vision_enabled        = _vis_en.lower() in ("true", "s", "si", "sí", "yes", "1")
    _vis_si = _ask("visionShowIndicator (true/false)", "true" if config.vision_show_indicator else "false")
    config.vision_show_indicator = _vis_si.lower() in ("true", "s", "si", "sí", "yes", "1")

    console.print()
    save = _tui_ask("¿Guardar cambios?", choices=["s", "n"], default="s")
    if save == "s":
        config.save()
        console.print("  [green]✓[/green]  Configuración guardada en oocode.json.")
        # Aplicar parámetros RAG en caliente sobre la instancia activa
        al = _agent_loop_ref
        if al is not None:
            rag = getattr(al, "_workspace_rag", None)
            if rag is not None:
                rag.update_config(
                    top_k=config.rag_top_k,
                    similarity_threshold=config.rag_similarity_threshold,
                    max_snippet_chars=config.rag_max_snippet_chars,
                    index_interval=config.rag_index_interval,
                )
            # Actualizar context.max_tokens si cambió el modelo
            if config.effective_context_window:
                al.context.max_tokens = config.effective_max_context_tokens
            # Aplicar caché intra-turno en caliente
            if hasattr(al, "registry"):
                al.registry.cache_enabled  = config.tool_cache_enabled
                al.registry.cache_max_size = config.tool_cache_max_size
    else:
        console.print("  [dim]Cambios descartados.[/dim]")


# ── Sistema ───────────────────────────────────────────────────────────────────

def _cmd_init(args: str, config, agent_loop) -> None:
    import os, subprocess as _sp, collections as _col

    target_dir = Path(args).expanduser().resolve() if args else Path(os.getcwd())
    path = target_dir / "OOCODE.md"

    # ── Notificación antes de comenzar ────────────────────────────────────────
    console.print(
        f"  [bold cyan]⊡  Analizando directorio[/bold cyan]  [cyan]{target_dir}[/cyan]"
    )
    console.print("  [dim]Detectando lenguaje, estructura, comandos y estado del proyecto…[/dim]")

    # ── Escaneo del directorio ─────────────────────────────────────────────────
    try:
        top_entries = list(os.scandir(target_dir))
        top_files   = {e.name for e in top_entries}
    except OSError:
        top_files   = set()
        top_entries = []

    project_name = target_dir.name
    lang, build_cmd, test_cmd, run_cmd = "desconocido", "", "", ""
    extra_info: list[str] = []

    if "pyproject.toml" in top_files or "setup.py" in top_files or "requirements.txt" in top_files:
        lang      = "Python"
        run_cmd   = "python3 main.py"
        test_cmd  = "pytest"
        # Extraer dependencias del requirements.txt
        req = target_dir / "requirements.txt"
        if req.exists():
            try:
                deps = [ln.split("==")[0].split(">=")[0].strip()
                        for ln in req.read_text().splitlines()
                        if ln.strip() and not ln.startswith("#")][:10]
                if deps:
                    extra_info.append(f"Dependencias principales: {', '.join(deps)}")
            except Exception:
                pass
    if "package.json" in top_files:
        lang      = "Node.js / TypeScript"
        run_cmd   = "npm start"
        test_cmd  = "npm test"
        build_cmd = "npm run build"
        try:
            import json as _json
            pkg = _json.loads((target_dir / "package.json").read_text())
            desc = pkg.get("description", "")
            if desc:
                extra_info.append(f"Descripción package.json: {desc}")
        except Exception:
            pass
    if "Cargo.toml" in top_files:
        lang      = "Rust"
        build_cmd = "cargo build"
        test_cmd  = "cargo test"
        run_cmd   = "cargo run"
    if "go.mod" in top_files:
        lang      = "Go"
        build_cmd = "go build ./..."
        test_cmd  = "go test ./..."
        run_cmd   = "go run ."
    if "Makefile" in top_files:
        build_cmd = build_cmd or "make"
        test_cmd  = test_cmd  or "make test"
    if "docker-compose.yml" in top_files or "docker-compose.yaml" in top_files:
        run_cmd = run_cmd or "docker compose up -d"
        extra_info.append("Docker Compose disponible")
    if "CMakeLists.txt" in top_files or "configure.ac" in top_files:
        lang      = lang if lang != "desconocido" else "C/C++"
        build_cmd = build_cmd or "cmake -B build && cmake --build build"
        test_cmd  = test_cmd  or "ctest --test-dir build"

    # ── Conteo de ficheros por extensión ──────────────────────────────────────
    ext_count: _col.Counter = _col.Counter()
    try:
        for root, dirs, files in os.walk(target_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.')
                       and d not in ("node_modules", "__pycache__", ".git", "venv", ".venv",
                                     "dist", "build", "target", ".mypy_cache")]
            for f in files:
                ext = Path(f).suffix.lower()
                if ext:
                    ext_count[ext] += 1
            if root != str(target_dir) and root.count(os.sep) - str(target_dir).count(os.sep) >= 3:
                dirs.clear()  # no profundizar más de 3 niveles
    except Exception:
        pass

    top_exts = [f"{ext}({n})" for ext, n in ext_count.most_common(8) if n > 0]
    if top_exts:
        extra_info.append(f"Ficheros por tipo: {', '.join(top_exts)}")
    total_files = sum(ext_count.values())
    if total_files:
        extra_info.append(f"Total ficheros: {total_files}")

    # ── Leer README si existe ─────────────────────────────────────────────────
    readme_desc = ""
    for rname in ("README.md", "README.rst", "README.txt", "README"):
        readme_path = target_dir / rname
        if readme_path.exists():
            try:
                lines = readme_path.read_text(errors="replace").splitlines()
                # Tomar el primer párrafo no vacío tras el título
                in_content = False
                desc_lines: list[str] = []
                for line in lines[:40]:
                    if line.startswith("#"):
                        in_content = True
                        continue
                    if in_content and line.strip():
                        desc_lines.append(line.strip())
                    elif in_content and desc_lines:
                        break
                readme_desc = " ".join(desc_lines)[:300]
            except Exception:
                pass
            break

    # ── Git: últimos commits y rama actual ────────────────────────────────────
    git_info = ""
    git_status_summary = ""
    try:
        branch = _sp.check_output(
            ["git", "-C", str(target_dir), "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=_sp.DEVNULL, text=True,
        ).strip()
        log = _sp.check_output(
            ["git", "-C", str(target_dir), "log", "--oneline", "-6"],
            stderr=_sp.DEVNULL, text=True,
        ).strip()
        git_info = f"Rama: {branch}\nÚltimos commits:\n" + "\n".join(
            f"  {ln}" for ln in log.splitlines()
        )
        # Estado actual
        status = _sp.check_output(
            ["git", "-C", str(target_dir), "status", "--short"],
            stderr=_sp.DEVNULL, text=True,
        ).strip()
        if status:
            changed = len(status.splitlines())
            git_status_summary = f"{changed} fichero(s) modificados sin commit"
        else:
            git_status_summary = "árbol de trabajo limpio"
    except Exception:
        pass

    # ── Estructura de directorios (2 niveles) ─────────────────────────────────
    _skip_dirs = {"node_modules", "__pycache__", ".git", "venv", ".venv",
                  "dist", "build", "target", ".mypy_cache", ".pytest_cache"}
    try:
        struct_lines_list: list[str] = []
        for e in sorted(top_entries, key=lambda x: (not x.is_dir(), x.name)):
            if e.is_dir() and not e.name.startswith('.') and e.name not in _skip_dirs:
                struct_lines_list.append(f"{project_name}/{e.name}/")
                try:
                    sub = sorted(s.name for s in os.scandir(e.path)
                                 if not s.name.startswith('.') and s.name not in _skip_dirs)[:6]
                    for s in sub:
                        struct_lines_list.append(f"  {project_name}/{e.name}/{s}")
                except Exception:
                    pass
            elif not e.is_dir() and not e.name.startswith('.'):
                struct_lines_list.append(f"{project_name}/{e.name}")
        struct_lines = "\n".join(struct_lines_list[:30]) or f"{project_name}/"
    except OSError:
        struct_lines = f"{project_name}/"

    # ── Comandos ──────────────────────────────────────────────────────────────
    cmds_lines = []
    if build_cmd:
        cmds_lines.append(f"# Build\n{build_cmd}")
    if test_cmd:
        cmds_lines.append(f"# Tests\n{test_cmd}")
    if run_cmd:
        cmds_lines.append(f"# Ejecutar\n{run_cmd}")
    cmds_block = "\n\n".join(cmds_lines) if cmds_lines else "# Añade los comandos del proyecto aquí"

    # ── Construir sección extra ────────────────────────────────────────────────
    extra_block = ("\n".join(f"- {i}" for i in extra_info) + "\n") if extra_info else ""

    # ── Sección git ───────────────────────────────────────────────────────────
    git_block = ""
    if git_info:
        git_block = f"\n## Estado Git\n\n```\n{git_info}\nEstado: {git_status_summary}\n```\n"

    # ── Generar contenido ─────────────────────────────────────────────────────
    desc_section = readme_desc if readme_desc else "<!-- Describe brevemente el propósito y contexto del proyecto -->"

    content = f"""\
# {project_name}

## Descripción del proyecto
{desc_section}

## Lenguaje / Stack
{lang}
{extra_block}
## Arquitectura
```
{struct_lines}
```
<!-- Describe aquí los módulos o carpetas más importantes -->

## Ficheros clave
<!-- Ficheros/módulos principales y su funcionalidad, una línea por entrada:
     - ruta/fichero — qué hace y por qué importa
     Mantén esta lista concisa: solo lo esencial para entender el proyecto. -->

## Comandos

```bash
{cmds_block}
```
{git_block}
## Convenciones de código
<!-- Estilo, nomenclatura, linting, formateo -->

## Notas para el agente
<!-- Instrucciones específicas: qué hacer, qué evitar, contexto importante -->
- Usa `python3`, no `python`, para ejecutar scripts Python.
- Antes de editar un fichero léelo con read_file (offset + limit para ficheros grandes).
"""

    # ── Mostrar preview y pedir confirmación ──────────────────────────────────
    console.print()
    console.print("  [bold]Vista previa del OOCODE.md generado:[/bold]")
    console.print("  " + "─" * 58)
    for line in content.splitlines()[:30]:
        console.print(f"  [dim]{line}[/dim]" if line.startswith("#") else f"  {line}")
    if content.count("\n") > 30:
        console.print(f"  [dim]… ({content.count(chr(10)) - 30} líneas más)[/dim]")
    console.print("  " + "─" * 58)
    console.print()

    import sys as _sys
    try:
        _interactive = _sys.stdin.isatty()
    except Exception:
        _interactive = False
    if not _interactive:
        confirm = "n" if path.exists() else "s"
    elif path.exists():
        confirm = _tui_ask("OOCODE.md ya existe. ¿Sobreescribir con el análisis anterior?",
                           choices=["s", "n"], default="n")
    else:
        try:
            confirm = _tui_ask("¿Guardar este OOCODE.md?", choices=["s", "n"], default="s")
        except OSError:
            confirm = "s"
    if confirm != "s":
        console.print("  [dim]Cancelado — OOCODE.md no modificado.[/dim]")
        return

    path.write_text(content)
    console.print(f"  [green]✓[/green]  OOCODE.md guardado en [cyan]{path}[/cyan]")
    console.print(
        "  [dim]Revísalo y edítalo si es necesario: "
        f"el agente lo leerá en cada turno para orientarse en el proyecto.[/dim]"
    )
    console.print(
        "  [dim]Tip: añade contexto en 'Notas para el agente' y ajusta los comandos si no son correctos.[/dim]"
    )


def _cmd_review(agent_loop, config) -> None:
    agent_loop.run(
        f"Ejecuta `git diff HEAD` en '{config.workspace}' y haz una revisión detallada: "
        "bugs, problemas de seguridad, mejoras de calidad. Si no hay cambios, indícalo."
    )


def _cmd_webserver(args: str, config, agent_loop) -> None:
    """Levanta/detiene el WebUI daemon (host/puerto/log leídos de oocode.json vía config)."""
    import sys as _sys

    # Verificar que Flask está instalado
    try:
        import flask  # noqa: F401
    except ImportError:
        console.print(
            "  [yellow]⚠[/yellow]  Flask no instalado. Instala con: pip install flask\n"
            "  [dim]Uso: /webserver start — Levanta el WebUI[/dim]\n"
            "  [dim]Uso: /webserver stop  — Para el WebUI[/dim]\n"
            "  [dim]Uso: /webserver status — Estado actual[/dim]"
        )
        return

    # Leer configuración desde config (persistida en oocode.json)
    _host = getattr(config, "webui_host", "0.0.0.0")
    _port = int(getattr(config, "webui_port", 4000))
    _log_file_str = getattr(config, "webui_log_file", "")
    _log_max  = int(getattr(config, "webui_log_max_size", 5))
    _log_path = (
        Path(_log_file_str).expanduser()
        if _log_file_str
        else Path.home() / ".oocode" / "logs" / "webserver.log"
    )

    # webui_state.json — estado de RUNTIME (pid, started, uptime), no persiste en oocode.json
    # oocode.json["webui"]["enabled"] — configuración PERSISTENTE (arranca al iniciar)
    _state_file = Path.home() / ".oocode" / "webui_state.json"

    def _load_state() -> dict:
        if _state_file.exists():
            try:
                with open(_state_file) as _f:
                    return json.load(_f)
            except Exception:
                pass
        return {}

    def _save_state(s: dict) -> None:
        _state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(_state_file, "w") as _f:
            json.dump(s, _f, indent=2)

    def _save_webui_config(enabled: bool) -> None:
        """Persiste webui.enabled directamente en oocode.json."""
        _cfg_path = Path.home() / ".oocode" / "oocode.json"
        try:
            _data = json.loads(_cfg_path.read_text()) if _cfg_path.exists() else {}
            _data.setdefault("webui", {})["enabled"] = enabled
            _cfg_path.write_text(json.dumps(_data, indent=2, ensure_ascii=False))
        except Exception:
            pass
        try:
            object.__setattr__(config, "webui_enabled", enabled)
        except Exception:
            pass

    state = _load_state()

    if args in ("", "status"):
        if state.get("running"):
            elapsed = int(datetime.now().timestamp() - state.get("started_ts", datetime.now().timestamp()))
            console.print(
                f"  [green]✓[/green]  WebUI activo en http://{_host}:{_port}\n"
                f"  [dim]PID: [cyan]{state.get('pid', '?')}[/cyan] | "
                f"Uptime: [cyan]{elapsed}s[/cyan] | "
                f"Log: [cyan]{_log_path}[/cyan][/dim]\n"
                "  [dim]Uso: /webserver stop — Para el WebUI[/dim]"
            )
        else:
            console.print(
                f"  [yellow]⚠[/yellow]  WebUI no activo (config: {_host}:{_port})\n"
                "  [dim]Uso: /webserver start — Levanta el WebUI[/dim]"
            )
        return

    elif args == "start":
        if state.get("running"):
            console.print(
                f"  [yellow]⚠[/yellow]  WebUI ya activo en http://{_host}:{_port}\n"
                "  [dim]Usa /webserver restart para reiniciarlo[/dim]"
            )
            return

        console.print(f"  [dim]Iniciando WebUI daemon en {_host}:{_port}...[/dim]")

        _save_webui_config(True)   # persistir en oocode.json

        # Lanzar el servidor como proceso INDEPENDIENTE (daemon) que persiste
        # tras cerrar el TUI. start_new_session=True lo separa del proceso padre.
        import subprocess as _subprocess
        _server_mod = str(Path(__file__).parent.parent / "webui" / "server.py")
        _proc = _subprocess.Popen(
            [_sys.executable, _server_mod, _host, str(_port), str(_log_path), str(_log_max)],
            stdout=_subprocess.DEVNULL,
            stderr=_subprocess.DEVNULL,
            stdin=_subprocess.DEVNULL,
            start_new_session=True,
        )

        # Esperar brevemente a que el servidor escriba su estado
        import time as _time
        for _ in range(20):
            _time.sleep(0.15)
            if _state_file.exists():
                break

        console.print(
            f"  [green]✓[/green]  WebUI iniciado en http://{_host}:{_port}\n"
            f"  [dim]PID: [cyan]{_proc.pid}[/cyan] | "
            f"Log → [cyan]{_log_path}[/cyan] | Abre en tu navegador[/dim]\n"
            f"  [dim]El servidor persiste tras cerrar el TUI. "
            f"Para parar: [cyan]/webserver stop[/cyan] o "
            f"[cyan]oocode --webserver stop[/cyan][/dim]"
        )

    elif args == "stop":
        if state.get("running"):
            _pid = state.get("pid")
            if _pid:
                try:
                    os.kill(_pid, 0)   # comprobar si el proceso existe
                    os.kill(_pid, 15)  # SIGTERM
                    console.print(f"  [green]✓[/green]  WebUI detenido (PID {_pid} → SIGTERM)\n")
                except ProcessLookupError:
                    console.print("  [yellow]⚠[/yellow]  El proceso ya no existía\n")
                except PermissionError:
                    console.print(f"  [yellow]⚠[/yellow]  Sin permiso para señalizar PID {_pid}\n")
            _state_file.unlink(missing_ok=True)
            _save_webui_config(False)
        else:
            _state_file.unlink(missing_ok=True)
            console.print("  [yellow]⚠[/yellow]  WebUI no estaba activo\n")

    elif args == "restart":
        if _state_file.exists():
            _state_file.unlink(missing_ok=True)
        console.print("  [dim]Reiniciando WebUI...[/dim]")
        _cmd_webserver("start", config, agent_loop)

    else:
        console.print(
            f"  [yellow]⚠[/yellow]  Subcomando desconocido: '{args}'\n"
            "  [dim]Uso: /webserver [start|stop|restart|status][/dim]"
        )


def _cmd_keybindings(args: str, agent_loop) -> None:
    """Gestión de keybindings: list | set <acción> <key> | reset [acción]."""
    from agent.keybindings import KeybindingManager, DEFAULT_KB

    # Obtener el manager del REPL (asignado en run_repl)
    kb_manager: KeybindingManager | None = getattr(agent_loop, "_kb_manager", None)
    if kb_manager is None:
        kb_manager = KeybindingManager()

    parts = args.split(maxsplit=2)
    sub   = parts[0].lower() if parts else "list"

    if sub in ("", "list"):
        print_keybindings(kb_manager.effective())

    elif sub == "set":
        if len(parts) < 3:
            console.print("  [dim]Uso: /keybindings set <acción> <key>[/dim]")
            console.print(f"  [dim]Acciones disponibles: {', '.join(DEFAULT_KB.keys())}[/dim]")
            return
        action, new_key = parts[1], parts[2]
        if kb_manager.set(action, new_key):
            from ui.renderer import _fmt_key
            console.print(
                f"  [green]✓[/green]  [cyan]{action}[/cyan] → "
                f"[bold]{_fmt_key(new_key)}[/bold]  "
                f"[dim](reinicia para activar el nuevo binding)[/dim]"
            )
        else:
            console.print(
                f"  [red]✗[/red]  Acción desconocida: [bold]{action}[/bold]\n"
                f"  [dim]Acciones disponibles: {', '.join(DEFAULT_KB.keys())}[/dim]"
            )

    elif sub == "reset":
        if len(parts) >= 2:
            action = parts[1]
            kb_manager.reset(action)
            console.print(f"  [green]✓[/green]  [cyan]{action}[/cyan] restaurado al valor por defecto.")
        else:
            kb_manager.reset()
            console.print("  [green]✓[/green]  Todos los keybindings restaurados a valores por defecto.")

    else:
        console.print(
            f"  [red]✗[/red]  Subcomando desconocido: [bold]{sub}[/bold]\n"
            "  [dim]Uso: /keybindings  |  /keybindings set <acción> <key>  |  /keybindings reset [acción][/dim]"
        )


# ── Helpers internos ──────────────────────────────────────────────────────────

def _hint_mem_names(memory) -> None:
    """Muestra los nombres de memorias disponibles como sugerencia."""
    names = memory.list_all()
    if names:
        console.print(f"  [dim]Memorias disponibles: {', '.join(names[:8])}[/dim]")


def _remove_from_index(slug: str, memory) -> None:
    """Elimina una entrada del MEMORY.md."""
    if not memory._index.exists():
        return
    lines = [l for l in memory._index.read_text().splitlines() if f"]({slug})" not in l]
    memory._index.write_text("\n".join(lines))


def _cmd_hooks(args: str, agent_loop) -> None:
    """Lista o gestiona hooks PreToolUse/PostToolUse."""
    parts = args.strip().split(maxsplit=1)
    sub   = parts[0].lower() if parts else ""
    rest  = parts[1] if len(parts) > 1 else ""
    hooks = agent_loop.registry.hooks

    if sub == "clear":
        hooks.clear()
        console.print("  [green]✓[/green]  Todos los hooks eliminados.")
        return

    if sub == "builtin":
        from tools.hooks import HookManager as _HM
        available = _HM.available_builtins()
        name = rest.strip()
        if not name:
            console.print(f"  Built-ins disponibles: {', '.join(available)}")
            return
        if name not in available:
            console.print(f"  [red]✗[/red]  Built-in desconocido: {name}")
            return
        removed = hooks.unregister_builtin(name)
        if removed:
            console.print(f"  [yellow]⊖[/yellow]  Hook built-in '{name}' desactivado.")
            cfg = getattr(agent_loop, "config", None)
            if cfg is not None:
                cfg.hooks_builtins = [h for h in cfg.hooks_builtins if h != name]
                cfg.save()
        else:
            done = hooks.register_builtins([name])
            if done:
                console.print(f"  [green]✓[/green]  Hook built-in '{name}' activado.")
                cfg = getattr(agent_loop, "config", None)
                if cfg is not None and name not in cfg.hooks_builtins:
                    cfg.hooks_builtins = list(cfg.hooks_builtins) + [name]
                    cfg.save()
            else:
                console.print(f"  [dim]Hook '{name}' ya estaba activo.[/dim]")
        return

    # Lista hooks registrados
    console.print()
    from tools.hooks import HookManager as _HM
    all_builtins  = _HM.available_builtins()
    active_bnames = hooks.active_builtin_names()

    table = Table(title="Hooks activos", box=box.SIMPLE, show_header=True,
                  header_style="bold cyan")
    table.add_column("Tipo",      style="bold magenta", width=6)
    table.add_column("Patrón",   style="cyan", width=16)
    table.add_column("Función",  style="dim")
    table.add_column("Built-in", style="dim yellow", width=10)

    total = 0
    for tipo, pattern, fname, is_builtin in hooks.list_rows():
        table.add_row(tipo, pattern, fname, "✓" if is_builtin else "")
        total += 1

    if total > 0:
        console.print(table)
    else:
        console.print("  [dim]Sin hooks activos.[/dim]")

    # Built-ins disponibles con estado activo/inactivo
    btable = Table(title="Built-ins disponibles", box=box.SIMPLE, show_header=True,
                   header_style="bold cyan")
    btable.add_column("",       width=3)
    btable.add_column("Nombre", style="cyan")
    for name in all_builtins:
        icon = "[green]✓[/green]" if name in active_bnames else "[dim]◻[/dim]"
        btable.add_row(icon, name)
    console.print(btable)

    console.print(
        f"  {total} hook(s) activo(s)  ·  "
        "[dim]/hooks builtin <nombre> · /hooks clear[/dim]\n"
    )


# ── LSP ───────────────────────────────────────────────────────────────────────

def _cmd_lsp(args: str, agent_loop) -> None:
    """Muestra estado del pool LSP."""
    parts = args.strip().split(maxsplit=1)
    sub   = parts[0].lower() if parts else ""

    # Obtener plugin LSP (si está cargado)
    lsp_plugin = None
    if agent_loop.plugins:
        lsp_plugin = agent_loop.plugins._loaded.get("lsp")

    if lsp_plugin is None:
        console.print("  [yellow]⚠[/yellow]  Plugin LSP no activo.  [dim]/plugins enable lsp[/dim]")
        return

    get_status = getattr(lsp_plugin, "get_status", None)
    if get_status is None:
        console.print("  [yellow]⚠[/yellow]  Plugin LSP sin función get_status.")
        return

    status = get_status()
    pool   = getattr(lsp_plugin, "_pool", None)

    def _resolve_ext(arg: str) -> str:
        """Convierte 'pylsp', 'bash-language-server', 'py', '.py' → '.py' etc."""
        arg = arg.strip()
        if arg.startswith("."):
            return arg.lower()
        # Intentar como extensión directa
        ext_try = f".{arg.lower()}"
        if pool and ext_try in pool._cmds:
            return ext_try
        # Intentar como nombre de ejecutable
        if pool:
            for e, cmd in pool._cmds.items():
                if cmd[0] == arg:
                    return e
        return ext_try

    # ── Subcomandos de acción ─────────────────────────────────────────────────
    if sub in ("stop", "restart", "start") and parts[1:]:
        ext = _resolve_ext(parts[1])
        if not pool:
            console.print("  [yellow]⚠[/yellow]  Pool LSP no disponible.")
            return
        if sub == "stop":
            with pool._lock:
                client = pool._clients.pop(ext, None)
            if client:
                client.stop()
                console.print(f"  [green]✓[/green]  Servidor LSP '{ext}' parado.")
            else:
                console.print(f"  [dim]No hay servidor LSP activo para '{ext}'.[/dim]")
        elif sub == "restart":
            console.print(f"  [dim]Reiniciando LSP '{ext}'…[/dim]")
            ok = pool.restart(ext)
            if ok:
                console.print(f"  [green]✓[/green]  Servidor LSP '{ext}' reiniciado.")
            else:
                console.print(f"  [red]✗[/red]  No se pudo reiniciar '{ext}' "
                              "(¿servidor instalado?).")
        else:  # start
            console.print(f"  [dim]Arrancando LSP '{ext}'…[/dim]")
            client = pool.get(ext)
            if client:
                console.print(f"  [green]✓[/green]  Servidor LSP '{ext}' activo.")
            else:
                console.print(f"  [red]✗[/red]  No se pudo arrancar '{ext}' "
                              "(¿servidor instalado?).")
        return

    # ── /lsp enable / disable — gestiona autoStart en oocode.json ────────────
    if sub in ("enable", "disable") and parts[1:]:
        srv_name = parts[1].strip()
        config   = agent_loop.config
        lsp_opts = config.plugin_options.get("lsp", {})
        if not isinstance(lsp_opts, dict):
            lsp_opts = {}
        # Sanear datos corruptos: serverCmds debe ser dict, autoStart lista de strings
        if not isinstance(lsp_opts.get("serverCmds"), dict):
            lsp_opts["serverCmds"] = {}
        auto_start_raw = lsp_opts.get("autoStart", [])
        if not isinstance(auto_start_raw, list):
            auto_start_raw = []   # evita list("[]") → ["[", "]"]
        auto_start = [s for s in auto_start_raw if isinstance(s, str)]
        # Normalizar a extensión para guardarlo
        ext = _resolve_ext(srv_name)
        if sub == "enable":
            if ext not in auto_start:
                auto_start.append(ext)
            lsp_opts["autoStart"] = auto_start
            config.plugin_options["lsp"] = lsp_opts
            config.save()
            console.print(
                f"  [green]✓[/green]  '{ext}' añadido a autoStart LSP.\n"
                "  [dim]Se iniciará automáticamente al arrancar OOCode.[/dim]"
            )
            # Arrancar ahora si pool disponible
            if pool:
                client = pool.get(ext)
                if client:
                    console.print(f"  [green]✓[/green]  Servidor LSP '{ext}' arrancado.")
        else:  # disable
            auto_start = [e for e in auto_start if e != ext]
            lsp_opts["autoStart"] = auto_start
            config.plugin_options["lsp"] = lsp_opts
            config.save()
            console.print(f"  [green]✓[/green]  '{ext}' eliminado de autoStart LSP.")
        return

    console.print()
    # ── Clientes activos ──────────────────────────────────────────────────────
    clients = status.get("clients", [])
    if clients:
        t = Table(title="Clientes LSP activos", box=box.SIMPLE, header_style="bold cyan")
        t.add_column("Ext",      style="cyan", width=8)
        t.add_column("Servidor", style="dim")
        t.add_column("Estado",   width=8)
        t.add_column("Reqs",     width=6)
        t.add_column("Errores",  width=8)
        t.add_column("Ficheros", width=9)
        t.add_column("Idle",     width=8)
        for c in clients:
            estado  = "[green]●[/green]" if c.get("alive") else "[red]✗[/red]"
            reqs    = str(c.get("requests", 0))
            errors  = str(c.get("errors", 0)) if c.get("errors") else "[dim]0[/dim]"
            idle_s  = c.get("idle_s")
            idle    = f"{idle_s}s" if idle_s is not None else "[dim]—[/dim]"
            t.add_row(c.get("ext", "?"), c.get("cmd", "?"), estado,
                      reqs, errors, str(c.get("files", 0)), idle)
        console.print(t)
    else:
        console.print("  [dim]Sin clientes LSP activos.[/dim]")

    # ── Servidores disponibles ────────────────────────────────────────────────
    available = status.get("available", [])
    config    = agent_loop.config
    lsp_opts  = config.plugin_options.get("lsp", {}) if config else {}
    auto_start_cfg = set(lsp_opts.get("autoStart", []) if isinstance(lsp_opts, dict) else [])

    installed = [s for s in available if s.get("installed")]
    if installed:
        srv_parts = []
        for s in installed:
            exts_str = ", ".join(s["exts"])
            auto_mark = " [green]●[/green]" if any(e in auto_start_cfg for e in s["exts"]) else ""
            srv_parts.append(f"[cyan]{s['name']}[/cyan] ({exts_str}){auto_mark}")
        console.print(f"\n  [dim]Servidores instalados:[/dim]  " + "  ".join(srv_parts))
        console.print("  [dim]([green]●[/green] = autoStart habilitado)[/dim]")
    not_inst = [s for s in available if not s.get("installed")]
    if not_inst:
        console.print("  [dim]No instalados:[/dim]  " + "  ".join(s["name"] for s in not_inst))
    console.print(
        "\n  [dim]/lsp start <ext|nombre>  ·  /lsp stop …  ·  /lsp restart …"
        "\n  /lsp enable <nombre>  ·  /lsp disable <nombre>[/dim]\n"
    )


# ── /steer — actualizar contexto/tarea del agente principal ──────────────────

def _cmd_steer(args: str, agent_loop) -> None:
    """Inyecta una instrucción de actualización en el contexto del agente principal.

    Uso: /steer <nueva tarea o instrucción>

    Añade la instrucción como mensaje de sistema al historial, de forma que el
    agente la tome en cuenta en el próximo turno o al completar el actual.
    """
    instruction = args.strip()
    if not instruction:
        console.print("  [yellow]Uso:[/yellow]  /steer <nueva tarea o instrucción>")
        console.print("  [dim]Actualiza el contexto/tarea del agente principal en curso.[/dim]")
        return

    # Inyectar como mensaje de usuario con prefijo especial en el historial
    ctx = agent_loop.context
    ctx.add("user", f"[STEER] Actualiza tu tarea: {instruction}")

    # Actualizar el label del separador para reflejar la tarea activa
    agent_loop._sep_label = instruction

    console.print(
        f"  [green]✓[/green]  Steer inyectado al agente principal:\n"
        f"  [dim cyan]↳ {instruction}[/dim cyan]"
    )
    console.print(
        "  [dim]El agente procesará la instrucción en el próximo turno.[/dim]"
    )


# ── MCP ───────────────────────────────────────────────────────────────────────

def _cmd_mcp(args: str, agent_loop) -> None:
    """Gestión del pool MCP: estado, catálogo, instalación y configuración."""
    parts = args.strip().split(maxsplit=1)
    sub   = parts[0].lower() if parts else ""
    rest  = parts[1].strip() if len(parts) > 1 else ""

    pool = getattr(agent_loop, "_mcp_pool", None)

    # ── /mcp catalog [query] ──────────────────────────────────────────────────
    if sub == "catalog":
        _cmd_mcp_catalog(rest)
        return

    # ── /mcp check <id> ───────────────────────────────────────────────────────
    if sub == "check":
        _cmd_mcp_check(rest)
        return

    # ── /mcp install <id> [extra args...] ────────────────────────────────────
    if sub == "install":
        _cmd_mcp_install(rest, agent_loop, pool)
        return

    # ── /mcp add <name> <cmd...> ─────────────────────────────────────────────
    if sub == "add":
        _cmd_mcp_add(rest, agent_loop, pool)
        return

    # ── /mcp remove <name> ────────────────────────────────────────────────────
    if sub == "remove":
        _cmd_mcp_remove(rest, pool)
        return

    # ── /mcp enable/disable <name> ────────────────────────────────────────────
    if sub in ("enable", "disable"):
        _cmd_mcp_toggle(rest, sub == "enable", pool, agent_loop)
        return

    # ── /mcp reload <name> ────────────────────────────────────────────────────
    if sub == "reload" and rest:
        if pool is None:
            console.print("  [dim]Sin pool MCP activo.[/dim]")
            return
        client = pool.get_client(rest)
        if client is None:
            console.print(f"  [red]✗[/red]  Servidor MCP '{rest}' no encontrado.")
            return
        n = client.reload_tools()
        console.print(f"  [green]✓[/green]  {rest}: {n} tools recargadas.")
        return

    # ── /mcp restart <name> ───────────────────────────────────────────────────
    if sub == "restart" and rest:
        if pool is None:
            console.print("  [dim]Sin pool MCP activo.[/dim]")
            return
        client = pool.restart_server(rest)
        if client and client.is_alive:
            console.print(f"  [green]✓[/green]  Servidor MCP '{rest}' reiniciado "
                          f"({len(client.tools)} tools).")
        else:
            console.print(f"  [red]✗[/red]  No se pudo reiniciar '{rest}'.")
        return

    # ── /mcp → estado general ─────────────────────────────────────────────────
    cfg = getattr(agent_loop, "config", None)

    # Tabla completa de servidores bundled con su estado de config
    _BUNDLED_INFO: list[tuple[str, str, str]] = [
        # (server-name, config-attr, script-filename)
        ("oocode-assistant",       "mcp_oocode_assistant_enabled",        "oocode_assistant.py"),
        ("system-assistant",       "mcp_system_assistant_enabled",        "system_assistant.py"),
        ("devops-assistant",       "mcp_devops_assistant_enabled",        "devops_assistant.py"),
        ("database-assistant",     "mcp_database_assistant_enabled",      "database_assistant.py"),
        ("word-assistant",         "mcp_word_assistant_enabled",          "word_assistant.py"),
        ("excel-assistant",        "mcp_excel_assistant_enabled",         "excel_assistant.py"),
        ("pptx-assistant",         "mcp_pptx_assistant_enabled",          "pptx_assistant.py"),
        ("mail-assistant",         "mcp_mail_assistant_enabled",          "mail_assistant.py"),
        ("cmdb-assistant",         "mcp_cmdb_assistant_enabled",          "cmdb_assistant.py"),
        ("security-assistant",     "mcp_security_assistant_enabled",      "security_assistant.py"),
        ("iot-assistant",          "mcp_iot_assistant_enabled",           "iot_assistant.py"),
        ("http-client-assistant",  "mcp_http_client_assistant_enabled",   "http_client_assistant.py"),
    ]

    console.print()

    # ── Servidores bundled (activos + inactivos) ──────────────────────────────
    t = Table(title="Servidores MCP bundled", box=box.SIMPLE, header_style="bold cyan")
    t.add_column("Nombre",    style="cyan")
    t.add_column("Estado",    width=10)
    t.add_column("Activo",    width=8)
    t.add_column("Tools",     width=7)
    t.add_column("Resources", width=10)
    t.add_column("Prompts",   width=9)
    t.add_column("Error",     style="dim red", max_width=35)

    running_names = {s["name"] for s in (pool.status() if pool else [])}
    pool_by_name  = {s["name"]: s for s in (pool.status() if pool else [])}

    for srv_name, cfg_attr, _script in _BUNDLED_INFO:
        enabled = bool(getattr(cfg, cfg_attr, False)) if cfg else False
        if srv_name in running_names:
            s      = pool_by_name[srv_name]
            alive  = "[green]●[/green]" if s["alive"] else "[red]✗[/red]"
            tools  = str(s["tools"])
            res    = str(s.get("resources", 0)) if s.get("resources") else "[dim]0[/dim]"
            prmt   = str(s.get("prompts",   0)) if s.get("prompts")   else "[dim]0[/dim]"
            err    = s.get("error", "")
            act    = "[green]enabled[/green]"
        else:
            alive  = "[dim]○[/dim]"
            tools  = "[dim]—[/dim]"
            res    = "[dim]—[/dim]"
            prmt   = "[dim]—[/dim]"
            err    = ""
            act    = "[green]enabled[/green]" if enabled else "[dim]disabled[/dim]"
        t.add_row(srv_name, alive, act, tools, res, prmt, err)
    console.print(t)

    # ── Servidores externos (mcp.servers[]) ───────────────────────────────────
    if pool:
        external = [s for s in pool.status() if s["name"] not in {b[0] for b in _BUNDLED_INFO}]
        if external:
            t2 = Table(title="Servidores MCP externos", box=box.SIMPLE, header_style="bold cyan")
            t2.add_column("Nombre",    style="cyan")
            t2.add_column("Cmd",       style="dim", max_width=30)
            t2.add_column("Estado",    width=8)
            t2.add_column("Tools",     width=7)
            t2.add_column("Resources", width=10)
            t2.add_column("Prompts",   width=9)
            t2.add_column("Error",     style="dim red", max_width=35)
            for s in external:
                alive = "[green]●[/green]" if s["alive"] else "[red]✗[/red]"
                res   = str(s.get("resources", 0)) if s.get("resources") else "[dim]0[/dim]"
                prmt  = str(s.get("prompts",   0)) if s.get("prompts")   else "[dim]0[/dim]"
                t2.add_row(s["name"], s["cmd"], alive, str(s["tools"]),
                           res, prmt, s.get("error", ""))
            console.print(t2)

    n_tools = pool.tool_count if pool else 0
    n_srv   = pool.client_count if pool else 0
    console.print(
        f"\n  {n_srv} servidor(es) activos · {n_tools} tools  ·  "
        "[dim]/mcp enable|disable <nombre> · /mcp catalog · /mcp install <id>[/dim]\n"
    )


def _cmd_mcp_catalog(query: str) -> None:
    """Muestra el catálogo de servidores MCP disponibles."""
    from agent.mcp_manager import search_catalog, check_server_prerequisites
    servers = search_catalog(query)
    if not servers:
        console.print(f"  [dim]No hay resultados para '{query}'.[/dim]")
        return
    title = f"Catálogo MCP{' — ' + query if query else ''}"
    t = Table(title=title, box=box.SIMPLE, header_style="bold cyan")
    t.add_column("ID",          style="cyan",   width=14)
    t.add_column("Runtime",     style="yellow", width=8)
    t.add_column("Descripción", max_width=50)
    t.add_column("OK",          width=4)
    for srv in servers:
        missing = check_server_prerequisites(srv)
        ok = "[green]✓[/green]" if not missing else f"[red]✗ {', '.join(missing)}[/red]"
        t.add_row(srv.get("id", ""), srv.get("runtime", ""), srv.get("description", ""), ok)
    console.print()
    console.print(t)
    console.print(
        "  [dim]/mcp install <id> [args...]  ·  /mcp check <id>  para detalles[/dim]\n"
    )


def _cmd_mcp_check(id_or_name: str) -> None:
    """Muestra detalles y prerequisitos de un servidor del catálogo."""
    from agent.mcp_manager import find_in_catalog, check_server_prerequisites
    if not id_or_name:
        console.print("  [dim]Uso: /mcp check <id>  (ver /mcp catalog para IDs)[/dim]")
        return
    srv = find_in_catalog(id_or_name)
    if srv is None:
        console.print(f"  [red]✗[/red]  '{id_or_name}' no encontrado en el catálogo.  "
                      "[dim]/mcp catalog para listar[/dim]")
        return
    console.print()
    console.print(f"  [bold cyan]{srv.get('name', '')}[/bold cyan]  "
                  f"[dim]({srv.get('id', '')})[/dim]")
    console.print(f"  {srv.get('description', '')}")
    console.print(f"  [dim]Runtime:[/dim]  {srv.get('runtime', '')}")
    console.print(f"  [dim]Cmd base:[/dim] {' '.join(srv.get('cmd', []))}")
    if srv.get("example_args"):
        console.print(f"  [dim]Ejemplo:[/dim]  "
                      f"{' '.join(srv.get('cmd', []))} {' '.join(srv.get('example_args', []))}")
    if srv.get("install_hint"):
        console.print(f"  [dim]Instalar:[/dim] {srv['install_hint']}")
    if srv.get("note"):
        console.print(f"  [dim]Nota:[/dim]     {srv['note']}")
    missing = check_server_prerequisites(srv)
    if missing:
        console.print(f"  [red]✗ Prerequisito no encontrado:[/red] {', '.join(missing)}")
        console.print(f"  [dim]Instala con:[/dim] {srv.get('install_hint', 'ver documentación')}")
    else:
        console.print("  [green]✓[/green]  Prerequisitos OK")
    console.print()


def _cmd_mcp_install(rest: str, agent_loop, pool) -> None:
    """Añade un servidor del catálogo a oocode.json y lo arranca (hot-add)."""
    from agent.mcp_manager import (
        find_in_catalog, build_entry_from_catalog,
        add_server, check_server_prerequisites, hot_add_to_pool,
    )
    if not rest:
        console.print("  [dim]Uso: /mcp install <id> [args adicionales...][/dim]")
        console.print("  [dim]     /mcp catalog para ver IDs disponibles[/dim]")
        return

    tokens    = rest.split()
    id_or_name = tokens[0]
    extra_args = tokens[1:]

    srv = find_in_catalog(id_or_name)
    if srv is None:
        console.print(f"  [red]✗[/red]  '{id_or_name}' no encontrado en el catálogo.  "
                      "[dim]/mcp catalog para listar[/dim]")
        return

    # Verificar prerequisitos
    missing = check_server_prerequisites(srv)
    if missing:
        console.print(
            f"  [yellow]⚠[/yellow]  Prerequisito no encontrado: [bold]{', '.join(missing)}[/bold]"
        )
        if srv.get("install_hint"):
            console.print(f"  Instalar con: [cyan]{srv['install_hint']}[/cyan]")
        console.print("  [dim]Configura igualmente (arranque fallará si el runtime no está disponible)[/dim]")

    entry = build_entry_from_catalog(srv, extra_args)
    add_server(entry)
    console.print(
        f"  [green]✓[/green]  Servidor [cyan]{entry['name']}[/cyan] añadido a oocode.json"
    )
    console.print(f"  [dim]Cmd:[/dim] {' '.join(entry['cmd'])}")

    # Hot-add: arrancar en el pool activo sin reiniciar OOCode
    if pool is not None:
        registry = getattr(agent_loop, "registry", None)
        if registry is not None:
            console.print(f"  Arrancando [cyan]{entry['name']}[/cyan]…", end=" ")
            ok, msg = hot_add_to_pool(entry, pool, registry)
            if ok:
                console.print(f"[green]✓[/green]  {msg}")
            else:
                console.print(f"[red]✗[/red]  {msg}")
        else:
            console.print("  [dim]Reinicia OOCode para activar el servidor.[/dim]")
    else:
        console.print("  [dim]Reinicia OOCode para activar el servidor.[/dim]")


def _cmd_mcp_add(rest: str, agent_loop, pool) -> None:
    """Añade un servidor MCP personalizado (nombre + cmd libre)."""
    from agent.mcp_manager import add_server, hot_add_to_pool
    tokens = rest.split()
    if len(tokens) < 2:
        console.print("  [dim]Uso: /mcp add <nombre> <cmd> [args...][/dim]")
        console.print("  [dim]Ejemplo: /mcp add mi-fs npx -y @modelcontextprotocol/server-filesystem /home/user[/dim]")
        return

    name = tokens[0]
    cmd  = tokens[1:]
    entry = {"name": name, "cmd": cmd, "enabled": True}
    add_server(entry)
    console.print(
        f"  [green]✓[/green]  Servidor [cyan]{name}[/cyan] añadido a oocode.json"
    )
    console.print(f"  [dim]Cmd:[/dim] {' '.join(cmd)}")

    if pool is not None:
        registry = getattr(agent_loop, "registry", None)
        if registry is not None:
            console.print(f"  Arrancando [cyan]{name}[/cyan]…", end=" ")
            ok, msg = hot_add_to_pool(entry, pool, registry)
            if ok:
                console.print(f"[green]✓[/green]  {msg}")
            else:
                console.print(f"[red]✗[/red]  {msg}")
        else:
            console.print("  [dim]Reinicia OOCode para activar el servidor.[/dim]")
    else:
        console.print("  [dim]Reinicia OOCode para activar el servidor.[/dim]")


def _cmd_mcp_remove(name: str, pool) -> None:
    """Elimina un servidor de oocode.json y lo para si está activo."""
    from agent.mcp_manager import remove_server
    if not name:
        console.print("  [dim]Uso: /mcp remove <nombre>[/dim]")
        return
    removed = remove_server(name)
    if removed:
        console.print(f"  [green]✓[/green]  Servidor [cyan]{name}[/cyan] eliminado de oocode.json.")
        if pool is not None:
            client = pool.get_client(name)
            if client:
                try:
                    client.stop()
                except Exception:
                    pass
                console.print(f"  [dim]Servidor parado.[/dim]")
        console.print("  [dim]Reinicia OOCode para aplicar cambios.[/dim]")
    else:
        console.print(f"  [red]✗[/red]  Servidor '{name}' no encontrado en oocode.json.")


_BUNDLED_CONFIG_ATTR: dict[str, str] = {
    "oocode-assistant":      "mcp_oocode_assistant_enabled",
    "system-assistant":      "mcp_system_assistant_enabled",
    "devops-assistant":      "mcp_devops_assistant_enabled",
    "database-assistant":    "mcp_database_assistant_enabled",
    "word-assistant":        "mcp_word_assistant_enabled",
    "excel-assistant":       "mcp_excel_assistant_enabled",
    "pptx-assistant":        "mcp_pptx_assistant_enabled",
    "mail-assistant":        "mcp_mail_assistant_enabled",
    "cmdb-assistant":        "mcp_cmdb_assistant_enabled",
    "security-assistant":    "mcp_security_assistant_enabled",
    "iot-assistant":         "mcp_iot_assistant_enabled",
    "http-client-assistant": "mcp_http_client_assistant_enabled",
}


def _cmd_mcp_toggle(name: str, enable: bool, pool, agent_loop=None) -> None:
    """Activa o desactiva un servidor en oocode.json y en la config en memoria."""
    from agent.mcp_manager import set_server_enabled
    if not name:
        action = "enable" if enable else "disable"
        console.print(f"  [dim]Uso: /mcp {action} <nombre>[/dim]")
        return
    found = set_server_enabled(name, enable)
    if found:
        # Actualizar también el objeto OOConfig en memoria para servidores bundled
        attr = _BUNDLED_CONFIG_ATTR.get(name)
        if attr and agent_loop is not None:
            config = getattr(agent_loop, "config", None)
            if config is not None and hasattr(config, attr):
                setattr(config, attr, enable)
        state = "[green]activado[/green]" if enable else "[dim]desactivado[/dim]"
        console.print(f"  [green]✓[/green]  Servidor [cyan]{name}[/cyan] {state} en oocode.json.")
        console.print("  [dim]Reinicia OOCode para aplicar.[/dim]")
    else:
        console.print(f"  [red]✗[/red]  Servidor '{name}' no encontrado en oocode.json.")


# ── RAG ───────────────────────────────────────────────────────────────────────

def _cmd_rag(args: str, agent_loop, config) -> None:
    """Muestra estado del RAG workspace o fuerza re-indexación."""
    sub = args.strip().lower()
    rag = getattr(agent_loop, "_workspace_rag", None)

    if sub == "enable":
        config.rag_enabled = True
        config.save()
        if rag is None:
            embed_client = getattr(agent_loop, "_embed_client", None)
            if embed_client is not None and embed_client.is_available():
                try:
                    from agent.workspace_rag import WorkspaceRAG as _WorkspaceRAG
                    from pathlib import Path as _Path
                    _cfg_dir = _Path.home() / ".oocode"
                    rag = _WorkspaceRAG(
                        workspace=config.workspace,
                        embed_client=embed_client,
                        index_dir=_cfg_dir / "search_index",
                        top_k=config.rag_top_k,
                        similarity_threshold=config.rag_similarity_threshold,
                        max_snippet_chars=config.rag_max_snippet_chars,
                        index_interval=config.rag_index_interval,
                        max_file_chars=config.rag_max_file_chars,
                        chunk_chars=config.rag_chunk_chars,
                        chunk_overlap=config.rag_chunk_overlap,
                        max_files=config.rag_max_files,
                        min_slot_chars=config.rag_min_slot_chars,
                    )
                    agent_loop._workspace_rag = rag
                    rag.ensure_indexed()
                    console.print("  [green]✓[/green]  RAG activado — indexación iniciada en background.")
                except Exception as exc:
                    console.print("  [green]✓[/green]  RAG activado.")
                    console.print(f"  [yellow]⚠[/yellow]  No se pudo inicializar en caliente: {exc}")
            else:
                console.print("  [green]✓[/green]  RAG activado (se aplica en el próximo arranque).")
                console.print("  [dim]  (modelo de embeddings no disponible en este momento)[/dim]")
        else:
            console.print("  [green]✓[/green]  RAG ya estaba activo.")
        return

    if sub == "disable":
        config.rag_enabled = False
        config.save()
        if rag is not None:
            agent_loop._workspace_rag = None
        console.print("  [yellow]⊖[/yellow]  RAG desactivado.")
        return

    if sub == "reindex":
        if rag is None:
            console.print("  [yellow]⚠[/yellow]  RAG no activo.")
            return
        import threading as _threading
        import time as _time
        _RAG_REINDEX_POLL = 0.4   # segundos entre comprobaciones de progreso de re-indexación
        console.print("  [dim]Re-indexando workspace…[/dim]")
        _t = _threading.Thread(target=rag._do_index, args=(False,), daemon=True,
                               name="oocode-rag-reindex")
        _t.start()
        _last_files = -1
        while _t.is_alive():
            _files = getattr(rag, "_files_indexed", 0)
            if _files != _last_files:
                _last_files = _files
                if _files > 0:
                    console.print(f"  [dim]  … {_files} ficheros procesados[/dim]")
            _time.sleep(_RAG_REINDEX_POLL)
        console.print(
            f"  [green]✓[/green]  Re-indexación completa: "
            f"[cyan]{rag.index_size}[/cyan] fragmentos  ·  "
            f"{rag.indexed_files} ficheros."
        )
        return

    # Estado
    console.print()
    if not config.rag_enabled:
        console.print("  [dim]RAG: desactivado[/dim]  ([dim]/rag enable[/dim] para activar)")
        return

    if rag is None:
        console.print("  [yellow]⚠[/yellow]  RAG habilitado en config pero no inicializado.")
        console.print("  [dim](comprueba el modelo de embeddings con /doctor)[/dim]")
        return

    import time as _time
    last_idx = getattr(rag, "last_indexed", 0.0)
    idx_files = getattr(rag, "indexed_files", "?")
    if last_idx > 0:
        elapsed = _time.time() - last_idx
        if elapsed < 120:
            last_str = f"hace {elapsed:.0f}s"
        elif elapsed < 3600:
            last_str = f"hace {elapsed/60:.0f}m"
        else:
            last_str = f"hace {elapsed/3600:.1f}h"
    else:
        last_str = "nunca (indexando en background…)"

    last_hits      = getattr(rag, "last_hits", 0)
    last_available = getattr(rag, "last_available", 0)
    if last_hits > 0:
        if last_available > last_hits:
            hits_str = (f"[cyan]{last_hits}[/cyan]/[dim]{last_available}[/dim] recuperados "
                        f"[dim](topK limitó — {last_available - last_hits} descartados)[/dim]")
        else:
            hits_str = f"[cyan]{last_hits}[/cyan] recuperados el último turno"
    else:
        hits_str = "[dim]sin hits en el último turno[/dim]"

    console.print(
        f"\n  [bold cyan]RAG[/bold cyan]  workspace=[dim]{rag._workspace}[/dim]\n"
        f"  índice: [cyan]{rag.index_size}[/cyan] fragmentos  ·  "
        f"[dim]{idx_files} ficheros[/dim]\n"
        f"  última indexación: [dim]{last_str}[/dim]  ·  "
        f"intervalo={config.rag_index_interval}s\n"
        f"  topK=[cyan]{config.rag_top_k}[/cyan]  ·  "
        f"threshold={config.rag_similarity_threshold}  ·  "
        f"maxChars={config.rag_max_snippet_chars}\n"
        f"  último turno: {hits_str}\n"
        f"\n  [dim]/rag reindex · /rag disable · /rag config[/dim]\n"
    )


# ── Snapshots ─────────────────────────────────────────────────────────────────

def _cmd_snapshots(args: str, agent_loop) -> None:
    """Lista o muestra snapshots de sesión."""
    import json as _json
    from config import CONFIG_DIR

    parts = args.strip().split(maxsplit=1)
    sub   = parts[0].lower() if parts else ""
    rest  = parts[1].strip() if len(parts) > 1 else ""

    snap_dir = CONFIG_DIR / "snapshots" / agent_loop.config.agent_id

    if sub == "clear":
        if not snap_dir.exists():
            console.print("  [dim]Sin snapshots guardados.[/dim]")
            return
        snaps = list(snap_dir.glob("snapshot_*.json"))
        for f in snaps:
            try:
                f.unlink()
            except Exception:
                pass
        console.print(f"  [green]✓[/green]  {len(snaps)} snapshot(s) eliminado(s).")
        return

    if not snap_dir.exists():
        console.print("  [dim]Sin snapshots guardados.[/dim]")
        return

    snaps = sorted(snap_dir.glob("snapshot_*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not snaps:
        console.print("  [dim]Sin snapshots guardados.[/dim]")
        return

    if sub == "show":
        try:
            idx = int(rest) - 1 if rest else 0
            if idx < 0 or idx >= len(snaps):
                console.print(f"  [red]✗[/red]  Índice fuera de rango (1–{len(snaps)}).")
                return
            data = _json.loads(snaps[idx].read_text())
            console.print()
            console.print(f"  [bold cyan]Snapshot #{idx+1}[/bold cyan]  {data.get('timestamp', '')}")
            console.print(f"  session: [dim]{data.get('session_id', '?')}[/dim]")
            console.print(f"  modelo:  [dim]{data.get('model', '?')}[/dim]")
            console.print(f"  workspace: [dim]{data.get('workspace', '?')}[/dim]")
            tok = data.get("tokens_used", {})
            console.print(f"  tokens: in={tok.get('input', 0)}  out={tok.get('output', 0)}")
            ctx = data.get("context", {})
            console.print(f"  contexto: {ctx.get('messages', 0)} msgs  "
                          f"~{ctx.get('tokens_estimate', 0)} tok")
            if ctx.get("summary"):
                console.print(f"\n  [dim]Resumen:[/dim]\n  {ctx['summary']}")
            last = data.get("last_messages", [])
            if last:
                console.print(f"\n  [dim]Últimos {len(last)} mensajes:[/dim]")
                for m in last:
                    role = m.get("role", "?")
                    content = m.get("content", "")
                    console.print(f"  [{role}] {content}")
            console.print()
        except Exception as exc:
            console.print(f"  [red]✗[/red]  Error leyendo snapshot: {exc}")
        return

    # Lista
    console.print()
    t = Table(title=f"Snapshots — agente {agent_loop.config.agent_id}",
              box=box.SIMPLE, header_style="bold cyan")
    t.add_column("#",         width=4, style="dim")
    t.add_column("Timestamp", style="cyan", width=22)
    t.add_column("Sesión",    style="dim", width=12)
    t.add_column("Modelo",    style="dim", max_width=28)
    t.add_column("Msgs",      width=6)
    t.add_column("Tokens",    width=8)

    for i, snap_file in enumerate(snaps[:20], 1):
        try:
            data = _json.loads(snap_file.read_text())
            ctx  = data.get("context", {})
            tok  = data.get("tokens_used", {})
            t.add_row(
                str(i),
                data.get("timestamp", "?")[:19],
                data.get("session_id", "?")[:10] + "…",
                data.get("model", "?"),
                str(ctx.get("messages", 0)),
                f"{tok.get('input', 0) + tok.get('output', 0):,}",
            )
        except Exception:
            t.add_row(str(i), snap_file.name, "", "", "", "")

    console.print(t)
    console.print(
        f"\n  {len(snaps)} snapshot(s)  ·  máx={agent_loop.config.snapshots_max}  ·  "
        "[dim]/snapshots show <n> · /snapshots clear[/dim]\n"
    )


# ── /diff, /symbols, /lint ─────────────────────────────────────────────────────

def _cmd_diff(args: str) -> None:
    from rich.markup import escape as _resc
    from rich.text import Text
    try:
        from tools.diff_renderer import get_history, rerender_entry
    except ImportError:
        console.print("  [red]✗[/red]  tools.diff_renderer no disponible.")
        return

    history = get_history()
    if not history:
        console.print(Text("  Sin diffs en esta sesión.", style="dim"))
        return

    target = args.strip()
    if target:
        matches = [e for e in history if target in e["path"]]
        if not matches:
            console.print(Text(f"  Sin diffs para '{target}' en esta sesión.", style="yellow"))
            return
        for entry in reversed(matches):
            rerender_entry(entry)
    else:
        t = Text()
        t.append("  Diffs de esta sesión", style="bold")
        t.append(f"  ({len(history)} ediciones)\n", style="dim")
        console.print(t)
        for i, entry in enumerate(reversed(history), 1):
            row = Text()
            row.append(f"  {i:2d}.  ", style="dim")
            row.append(_resc(entry["path"]), style="cyan")
            row.append("  ", style="")
            row.append(f"+{entry.get('added', 0)}", style="green")
            row.append("  ", style="")
            row.append(f"─{entry.get('removed', 0)}", style="red")
            console.print(row)
        console.print(Text("\n  /diff <nombre-fichero> para ver un diff completo.", style="dim"))


def _cmd_symbols(args: str) -> None:
    try:
        from tools.ctags_index import build_symbol_index, find_symbol, list_symbols
    except ImportError:
        console.print("  [red]✗[/red]  tools.ctags_index no disponible.")
        return
    from pathlib import Path as _P
    a = args.strip()
    if a and _P(a).is_file():
        console.print(list_symbols(a))
    elif a:
        console.print(find_symbol(a))
    else:
        console.print(build_symbol_index())


def _cmd_lint(args: str, config) -> None:
    from pathlib import Path as _P
    from tools.hooks import _lint_file, _lint_project
    path = args.strip() or getattr(config, "workspace", "") or ""
    p    = _P(path) if path else _P.cwd()
    if p.is_file():
        out = _lint_file(str(p))
        console.print(out or "  [green]✓[/green]  Sin diagnósticos.")
    else:
        console.print(_lint_project(str(p)))


def run_webserver_standalone(cmd: str, config) -> bool:
    """Controla el WebUI daemon desde CLI (oocode --webserver start|stop|status|restart).

    Devuelve True si la operación tuvo éxito, False si hubo error.
    """
    import sys as _sys
    import os as _os
    import subprocess as _subprocess
    import time as _time
    from pathlib import Path as _P

    _state_file = _P.home() / ".oocode" / "webui_state.json"
    _host       = getattr(config, "webui_host", "0.0.0.0")
    _port       = int(getattr(config, "webui_port", 4000))
    _log_file   = getattr(config, "webui_log_file", "")
    _log_max    = int(getattr(config, "webui_log_max_size", 5))
    _log_path   = (
        _P(_log_file).expanduser()
        if _log_file
        else _P.home() / ".oocode" / "logs" / "webserver.log"
    )

    def _load_state() -> dict:
        if _state_file.exists():
            try:
                return json.loads(_state_file.read_text())
            except Exception:
                pass
        return {}

    def _save_config(enabled: bool) -> None:
        _cfg = _P.home() / ".oocode" / "oocode.json"
        try:
            _d = json.loads(_cfg.read_text()) if _cfg.exists() else {}
            _d.setdefault("webui", {})["enabled"] = enabled
            _cfg.write_text(json.dumps(_d, indent=2, ensure_ascii=False))
        except Exception:
            pass

    def _do_stop(state: dict) -> bool:
        _pid = state.get("pid")
        if _pid:
            try:
                _os.kill(_pid, 0)
                _os.kill(_pid, 15)  # SIGTERM
                console.print(f"  [green]✓[/green]  WebUI daemon detenido (PID {_pid})\n")
            except ProcessLookupError:
                console.print("  [yellow]⚠[/yellow]  El proceso ya no existía\n")
            except PermissionError:
                console.print(f"  [yellow]⚠[/yellow]  Sin permiso para señalizar PID {_pid}\n")
                return False
        _state_file.unlink(missing_ok=True)
        _save_config(False)
        return True

    def _do_start() -> bool:
        try:
            import flask  # noqa: F401
        except ImportError:
            console.print(
                "  [red]✗[/red]  Flask no instalado.\n"
                "  [dim]Instala con: pip install flask[/dim]"
            )
            return False
        _save_config(True)
        _server_mod = str(_P(__file__).parent.parent / "webui" / "server.py")
        _proc = _subprocess.Popen(
            [_sys.executable, _server_mod, _host, str(_port), str(_log_path), str(_log_max)],
            stdout=_subprocess.DEVNULL,
            stderr=_subprocess.DEVNULL,
            stdin=_subprocess.DEVNULL,
            start_new_session=True,
        )
        for _ in range(30):
            _time.sleep(0.2)
            if _state_file.exists():
                break
        state = _load_state()
        if state.get("running"):
            console.print(
                f"  [green]✓[/green]  WebUI daemon iniciado en http://{_host}:{_port}\n"
                f"  [dim]PID: [cyan]{state.get('pid', _proc.pid)}[/cyan] | "
                f"Log → [cyan]{_log_path}[/cyan][/dim]\n"
                f"  [dim]Para parar: [cyan]oocode --webserver stop[/cyan][/dim]"
            )
            return True
        console.print(
            f"  [yellow]⚠[/yellow]  El servidor tardó en arrancar. "
            f"Revisa el log: [cyan]{_log_path}[/cyan]\n"
        )
        return False

    state = _load_state()

    if cmd == "status":
        if state.get("running"):
            _pid = state.get("pid")
            _alive = False
            if _pid:
                try:
                    _os.kill(_pid, 0)
                    _alive = True
                except Exception:
                    pass
            _elapsed = int(_time.time() - state.get("started_ts", _time.time()))
            _status_icon = "[green]✓[/green]" if _alive else "[yellow]⚠[/yellow] (proceso ya no existe)"
            console.print(
                f"  {_status_icon}  WebUI en http://{state.get('host', _host)}:{state.get('port', _port)}\n"
                f"  [dim]PID: [cyan]{_pid}[/cyan] | Uptime: [cyan]{_elapsed}s[/cyan] | "
                f"Log: [cyan]{state.get('log', _log_path)}[/cyan][/dim]"
            )
        else:
            console.print(
                f"  [yellow]●[/yellow]  WebUI no activo (config: {_host}:{_port})\n"
                f"  [dim]Arranca con: [cyan]oocode --webserver start[/cyan][/dim]"
            )
        return True

    elif cmd == "start":
        if state.get("running"):
            _pid = state.get("pid")
            try:
                if _pid:
                    _os.kill(_pid, 0)
                console.print(
                    f"  [yellow]⚠[/yellow]  WebUI ya activo en http://{_host}:{_port} (PID {_pid})\n"
                    "  [dim]Usa [cyan]oocode --webserver restart[/cyan] para reiniciarlo[/dim]"
                )
                return True
            except (ProcessLookupError, TypeError):
                _state_file.unlink(missing_ok=True)
        console.print(f"  [dim]Iniciando WebUI daemon en {_host}:{_port}...[/dim]")
        return _do_start()

    elif cmd == "stop":
        if state.get("running"):
            return _do_stop(state)
        _state_file.unlink(missing_ok=True)
        console.print("  [yellow]⚠[/yellow]  WebUI no estaba activo\n")
        return True

    elif cmd == "restart":
        _WEBUI_RESTART_GRACE = 0.5   # segundos de gracia entre stop y start del daemon WebUI
        console.print(f"  [dim]Reiniciando WebUI en {_host}:{_port}...[/dim]")
        if state.get("running"):
            _do_stop(state)
            _time.sleep(_WEBUI_RESTART_GRACE)
        return _do_start()

    return True
