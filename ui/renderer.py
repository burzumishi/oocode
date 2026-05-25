"""Renderer: todos los componentes visuales de OOCode al estilo Claude Code."""
import random
import time
from pathlib import Path
from typing import Any
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich import box
from config import APP_NAME, APP_SUBTITLE, VERSION
from ui.console import console

# Paleta de colores
C_BRAND   = "bold white"
C_DIM     = "dim"
C_CYAN    = "bold cyan"
C_GREEN   = "bold green"
C_YELLOW  = "yellow"
C_RED     = "bold red"
C_BLUE    = "blue"

# ── Logos ASCII ────────────────────────────────────────────────────────────────
#  Inspirados en 🤖 — las dos ◉ son los ojos / las O de OOCode
#  Bordes dobles, sonrisa ╰─╯, manos ◉, pies ■

LOGO_LARGE = [
    "         ╷         ",   # antena
    "  ╔══════╧══════╗  ",   # cabeza (borde doble)
    "  ║   ◉     ◉   ║  ",   # ojos
    "  ║    ╰───╯    ║  ",   # sonrisa
    "  ╠═════════════╣  ",   # separador cuerpo
    "  ║▓▓▓▓▓▓▓▓▓▓▓▓▓║  ",   # cuerpo
    "  ╚════╤═══╤════╝  ",   # base cuerpo
    "◉══════╢   ╟══════◉",   # brazos con manos (bolas ◉)
    "       │   │       ",   # piernas
    "       ■   ■       ",   # pies (cuadrados ■)
]

LOGO_MEDIUM = [
    "      ╷      ",          # antena
    " ╔════╧════╗ ",          # cabeza
    " ║  ◉   ◉  ║ ",          # ojos
    " ║   ╰─╯   ║ ",          # sonrisa
    " ╚═════════╝ ",          # base
]

LOGO_MINI = "╔◉═◉╗"

# Logo compacto 3 líneas — para el reset visual tras compactación de contexto
LOGO_COMPACT = [
    "╔◉═◉╗",   # ojos
    "║╰─╯║",   # sonrisa
    "╚═══╝",   # base
]

# ── Tips rotatorios ────────────────────────────────────────────────────────────

TIPS: list[str] = [
    "[bold cyan]/mem save nombre[/bold cyan]  recuerda algo importante entre sesiones",
    "[bold cyan]/branch save[/bold cyan]  guarda snapshot antes de cambios arriesgados",
    "[bold cyan]/think medium[/bold cyan]  activa razonamiento más profundo para tareas complejas",
    "[bold cyan]/compact[/bold cyan]  libera contexto cuando el modelo se vuelve lento",
    "[bold cyan]/ctx full[/bold cyan]  carga contexto completo del workspace (~800 tokens)",
    "[bold cyan]/elevated on[/bold cyan]  aprueba herramientas automáticamente en la sesión",
    "[bold cyan]/review[/bold cyan]  pide al agente que revise el git diff actual",
    "[bold cyan]/init[/bold cyan]  crea OOCODE.md con instrucciones para el proyecto",
    "[bold cyan]/plugins enable searxng[/bold cyan]  activa búsqueda web con tu instancia local",
    "[bold cyan]/doctor[/bold cyan]  diagnostica la conexión con Ollama y la configuración",
    "[bold cyan]/logs 50[/bold cyan]  muestra los últimos 50 eventos del log",
    "[bold cyan]/tasks add título[/bold cyan]  añade una tarea al gestor de tareas",
    "[bold cyan]/spawn coding tarea[/bold cyan]  delega en un subagente con workspace distinto",
    "[bold cyan]/color random[/bold cyan]  cambia el esquema de color aleatoriamente",
    "[bold cyan]/sessions[/bold cyan]  navega por el historial de sesiones anteriores",
    "[bold cyan]/verbose on[/bold cyan]  muestra los argumentos completos de cada herramienta",
    "[bold cyan]/usage[/bold cyan]  estadísticas de tokens de la sesión actual",
    "[bold cyan]/model[/bold cyan]  cambia el modelo sin reiniciar OOCode",
    "[bold cyan]Ctrl+R[/bold cyan]  busca en el historial de comandos anteriores",
    "El agente lee ficheros con [bold cyan]read_file[/bold cyan] — no necesitas copiar código manualmente",
    "Escribe [bold cyan]/mem search consulta[/bold cyan] para búsqueda semántica en tus memorias",
    "[bold cyan]/checkpoint[/bold cyan]  guarda el resumen actual en la memoria del workspace",
]


def _random_tip() -> str:
    return random.choice(TIPS)


def _print_logo_animated(lines: list[str], color: str = "cyan") -> None:
    """Muestra el logo línea a línea con efecto de aparición."""
    for line in lines:
        console.print(f"  [bold {color}]{line}[/bold {color}]")
        time.sleep(0.025)


def print_banner(config) -> None:
    from agent.runtime import COLOR_PRESETS
    accent = getattr(config, "accent_color", "cyan")
    rich_color = COLOR_PRESETS.get(accent, COLOR_PRESETS["cyan"])[1]

    project_name = Path(config.workspace).name

    console.print()

    # ── Logo MEDIUM + nombre en columnas ────────────────────────────────────
    logo_text = Text()
    for i, line in enumerate(LOGO_MEDIUM):
        if i == 2:    # ojos → accent vivo
            logo_text.append(f"  {line}\n", style=f"bold {rich_color}")
        elif i == 3:  # sonrisa → accent suave
            logo_text.append(f"  {line}\n", style=f"{rich_color}")
        elif i in (1, 4):  # bordes cabeza → blanco tenue
            logo_text.append(f"  {line}\n", style="dim white")
        else:         # antena (i=0) → accent tenue
            logo_text.append(f"  {line}\n", style=f"dim {rich_color}")

    name_text = Text()
    name_text.append("\n")
    name_text.append(f"  {APP_NAME}", style="bold white")
    name_text.append("  ", style="dim")
    name_text.append(f"v{VERSION}", style="dim")
    name_text.append("\n")
    name_text.append(f"  {APP_SUBTITLE}\n", style="dim")
    name_text.append("\n")
    name_text.append(f"  {config.agent_emoji} ", style="bold")
    name_text.append(f"{config.agent_name}", style=f"bold {rich_color}")
    name_text.append("  ·  ", style="dim")
    name_text.append(f"{config.agent_id}", style="dim")

    console.print(Columns([logo_text, name_text], padding=(0, 2)))

    # ── Info ────────────────────────────────────────────────────────────────
    console.print()

    def row(icon: str, label: str, value: str) -> None:
        console.print(
            f"  [dim]{icon}[/dim]  [dim]{label:<12}[/dim]{value}"
        )

    if config.model:
        row("◈", "Modelo", f"[bold {rich_color}]{config.model}[/bold {rich_color}]")

    # Proyecto: solo nombre si coincide con el final del path, si no muestra ambos
    ws_path = config.workspace
    ws_display = (
        f"[dim]{ws_path}[/dim]"
        if ws_path.endswith(f"/{project_name}") or ws_path == project_name
        else f"[bold white]{project_name}[/bold white]  [dim]{ws_path}[/dim]"
    )
    row("◈", "Proyecto", ws_display)
    row("◈", "Servidor", f"[dim]{config.ollama_host}[/dim]")

    # ── Tip del día ─────────────────────────────────────────────────────────
    console.print()
    console.print(f"  [dim]✦[/dim]  {_random_tip()}")

    # ── Hint ────────────────────────────────────────────────────────────────
    console.print()
    console.print(
        "  [dim cyan]/help[/dim cyan][dim] comandos[/dim]"
        "  [dim]·[/dim]  "
        "[dim]Ctrl+C interrumpir[/dim]"
        "  [dim]·[/dim]  "
        "[dim cyan]/exit[/dim cyan][dim] salir[/dim]"
    )
    console.print()


def print_compact_banner(config) -> None:
    """Banner compacto (3 líneas) para el reset visual tras compactación de contexto."""
    from agent.runtime import COLOR_PRESETS
    accent   = getattr(config, "accent_color", "cyan")
    rich_col = COLOR_PRESETS.get(accent, COLOR_PRESETS["cyan"])[1]
    ws_path  = str(config.workspace or "")
    proj     = f"~/{Path(ws_path).name}" if ws_path else "~"
    model_s  = (config.model or "—")[:34]

    logo_styles = [f"bold {rich_col}", f"{rich_col}", "white"]
    infos: list[tuple[str, str, str, str]] = [
        (f"  {APP_NAME} ", "bold white",         f"v{VERSION}", "dim"),
        (f"  {model_s}",   "dim",                " · Ollama",   "dim"),
        (f"  {proj}",      "dim",                "",            ""),
    ]

    console.print()
    for logo_line, logo_sty, (pre, pre_sty, suf, suf_sty) in zip(
        LOGO_COMPACT, logo_styles, infos
    ):
        t = Text()
        t.append(f" {logo_line}  ", style=logo_sty)
        t.append(pre, style=pre_sty)
        if suf:
            t.append(suf, style=suf_sty)
        console.print(t)
    console.print()


def print_splash(config) -> None:
    """Logo grande animado — se usa con /splash."""
    from agent.runtime import COLOR_PRESETS
    accent = getattr(config, "accent_color", "cyan")
    rich_color = COLOR_PRESETS.get(accent, COLOR_PRESETS["cyan"])[1]

    console.print()
    # Robot grande, línea a línea
    for i, line in enumerate(LOGO_LARGE):
        if i == 2:   # ojos → color accent vivo
            console.print(f"       [bold {rich_color}]{line}[/bold {rich_color}]")
        elif i == 3:  # sonrisa → accent suave
            console.print(f"       [{rich_color}]{line}[/{rich_color}]")
        elif i in (7, 9):  # brazos+manos / pies → accent
            console.print(f"       [bold {rich_color}]{line}[/bold {rich_color}]")
        elif i in (1, 4, 5, 6):  # bordes + cuerpo → blanco tenue
            console.print(f"       [dim white]{line}[/dim white]")
        else:          # antena, piernas
            console.print(f"       [dim]{line}[/dim]")
        time.sleep(0.04)

    console.print()
    # Nombre en grande con separadores
    console.print(f"       [bold white]{APP_NAME}[/bold white]"
                  f"  [dim]·[/dim]  "
                  f"[dim]{APP_SUBTITLE}[/dim]"
                  f"  [dim]v{VERSION}[/dim]")
    console.print()
    console.print(f"       [dim]{_random_tip()}[/dim]")
    console.print()


def print_model_selector(models: list[dict]) -> None:
    table = Table(
        title="Modelos disponibles en Ollama",
        box=box.ROUNDED,
        border_style="blue",
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("#", style=C_CYAN, width=4, justify="right")
    table.add_column("Nombre", style="white")
    table.add_column("Familia", style="dim")
    table.add_column("Tamaño", style="dim", justify="right")
    for i, m in enumerate(models, 1):
        size_gb = m.get("size", 0) / 1e9
        family = m.get("details", {}).get("family", "") if isinstance(m.get("details"), dict) else ""
        table.add_row(str(i), m["name"], family, f"{size_gb:.1f} GB")
    console.print(table)


def print_help(commands: dict[str, dict[str, str]]) -> None:
    console.print()
    console.rule("[bold cyan]Comandos OOCode[/bold cyan]", style="blue")
    console.print()

    table = Table(box=box.SIMPLE, padding=(0, 2), show_header=False)
    table.add_column("cmd", style=C_CYAN, no_wrap=True)
    table.add_column("desc", style="white")

    for group_title, items in commands.items():
        table.add_row(f"[dim]{group_title}[/dim]", "", style="dim")
        for cmd, desc in items.items():
            table.add_row(f"  {cmd}", desc)

    console.print(table)
    console.print()
    console.print("  [dim]Cualquier otro texto se envía al modelo como mensaje.[/dim]")
    console.print()


def print_config(config) -> None:
    console.print()
    console.rule("[bold cyan]Configuración[/bold cyan]", style="blue")
    console.print()

    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    t.add_column("key", style="dim", no_wrap=True)
    t.add_column("val", style="white")
    t.add_row("Agente",    f"{config.agent_emoji} {config.agent_name} ({config.agent_id})")
    t.add_row("Modelo",    f"[bold cyan]{config.model or '(sin seleccionar)'}[/bold cyan]")
    t.add_row("Servidor",  config.ollama_host)
    t.add_row("Workspace", config.workspace)
    t.add_row("Contexto",  f"{config.max_context_tokens} tokens máx.")
    console.print(t)

    console.print()
    p = Table(box=box.SIMPLE, show_header=True, padding=(0, 2))
    p.add_column("Herramienta", style="dim")
    p.add_column("Permiso", style="white")
    for tool, mode in config.permissions.items():
        color = {"auto": "green", "ask": "yellow", "deny": "red"}.get(mode, "white")
        p.add_row(tool, f"[{color}]{mode}[/{color}]")
    console.print(p)
    console.print()


def print_agents(agents: list, current_id: str) -> None:
    console.print()
    console.rule("[bold cyan]Agentes disponibles[/bold cyan]", style="blue")
    console.print()

    t = Table(box=box.SIMPLE, show_header=True, padding=(0, 2))
    t.add_column("ID", style=C_CYAN)
    t.add_column("Nombre", style="white")
    t.add_column("Modelo", style="dim")
    t.add_column("Workspace", style="dim")

    for a in agents:
        marker = " [bold green]◀ activo[/bold green]" if a.id == current_id else ""
        t.add_row(
            f"{a.emoji} {a.id}",
            f"{a.name}{marker}",
            a.model or "[dim](heredado)[/dim]",
            a.workspace,
        )
    console.print(t)
    console.print()


def print_spawn_header(agent_name: str, agent_emoji: str, task: str) -> None:
    console.print()
    console.rule(
        f"[bold cyan]↳ Subagente {agent_emoji} {agent_name}[/bold cyan]",
        style="cyan dim",
    )
    task_preview = task[:80] + "…" if len(task) > 80 else task
    console.print(f"  [dim]Tarea:[/dim] {task_preview}")
    console.print()


def print_spawn_footer(agent_name: str) -> None:
    console.rule(f"[dim]↲ fin subagente · {agent_name}[/dim]", style="cyan dim")
    console.print()


# ── Sesiones ───────────────────────────────────────────────────────────────────

def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def _progress_bar(used: int, total: int, width: int = 20) -> str:
    if total <= 0:
        return "─" * width
    pct = min(used / total, 1.0)
    filled = int(pct * width)
    bar = "█" * filled + "░" * (width - filled)
    color = "green" if pct < 0.6 else "yellow" if pct < 0.85 else "red"
    return f"[{color}]{bar}[/{color}]"


def print_context(context, config, session) -> None:
    """Muestra el estado actual del contexto y la sesión."""
    from agent.session import _ago
    stats = session.stats()
    msg_count = len(context.messages)
    # Estimación: 4 chars ≈ 1 token
    est_chars = sum(len(str(m.get("content", ""))) for m in context.messages)
    est_tokens = est_chars // 4
    max_tokens = config.max_context_tokens
    session_short = stats["session_id"][:8]

    console.print()
    console.rule("[bold cyan]Contexto[/bold cyan]", style="blue")
    console.print()

    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    t.add_column("key", style="dim", no_wrap=True)
    t.add_column("val", style="white")

    t.add_row("Sesión",   f"[dim]{session_short}…[/dim]  [dim]{_ago(stats['started_at'])}[/dim]")
    t.add_row("Modelo",   f"[bold cyan]{config.model or '—'}[/bold cyan]")
    t.add_row("Agente",   f"{config.agent_emoji} {config.agent_name} [dim]({config.agent_id})[/dim]")
    t.add_row("Mensajes", f"[white]{msg_count}[/white] [dim]en contexto[/dim]")
    t.add_row(
        "Tokens",
        f"[white]~{_fmt_tokens(est_tokens)}[/white] [dim]/ {_fmt_tokens(max_tokens)} máx. (estimado)[/dim]",
    )
    t.add_row(
        "Uso Ollama",
        f"[white]{_fmt_tokens(stats['input_tokens'])}[/white] [dim]entrada[/dim]  "
        f"[white]{_fmt_tokens(stats['output_tokens'])}[/white] [dim]salida[/dim]",
    )
    t.add_row(
        "Progreso",
        _progress_bar(est_tokens, max_tokens) + f"  [dim]{int(min(est_tokens/max_tokens,1)*100)}%[/dim]",
    )
    t.add_row("Compactaciones", str(stats["compactions"]) if stats["compactions"] else "[dim]ninguna[/dim]")
    console.print(t)
    console.print()


def print_usage(session) -> None:
    """Muestra estadísticas de uso de tokens de la sesión actual."""
    stats = session.stats()
    inp = stats["input_tokens"]
    out = stats["output_tokens"]
    total = inp + out

    console.print()
    console.rule("[bold cyan]Uso de tokens[/bold cyan]", style="blue")
    console.print()

    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    t.add_column("key", style="dim", no_wrap=True)
    t.add_column("val", style="white")

    t.add_row("Sesión",        f"[dim]{stats['session_id'][:8]}…[/dim]")
    t.add_row("Inicio",        f"[dim]{stats['started_at'][:16].replace('T',' ')}[/dim]")
    t.add_row("Modelo",        f"[bold cyan]{stats['model'] or '—'}[/bold cyan]")
    t.add_row("Mensajes",      str(stats["message_count"]))
    t.add_row("Tool calls",    str(stats["tool_calls"]))
    t.add_row("",              "")
    t.add_row("Tokens entrada", f"[white]{_fmt_tokens(inp)}[/white]")
    t.add_row("Tokens salida",  f"[white]{_fmt_tokens(out)}[/white]")
    t.add_row("Total tokens",   f"[bold white]{_fmt_tokens(total)}[/bold white]")
    t.add_row("",              "")
    t.add_row("Coste",         "[green]$0.00[/green]  [dim](modelo local, sin coste de API)[/dim]")

    console.print(t)
    console.print()


def print_sessions(sessions: list[dict], current_id: str) -> None:
    """Muestra la lista de sesiones pasadas."""
    from agent.session import _ago

    if not sessions:
        console.print("  [dim]No hay sesiones guardadas.[/dim]")
        return

    console.print()
    console.rule("[bold cyan]Sesiones[/bold cyan]", style="blue")
    console.print()

    t = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    t.add_column("#",        style="dim",       width=3,  justify="right")
    t.add_column("ID",       style="cyan",      width=10)
    t.add_column("Modelo",   style="white",     width=22)
    t.add_column("Msgs",     style="white",     width=5,  justify="right")
    t.add_column("Tokens",   style="white",     width=8,  justify="right")
    t.add_column("Calls",    style="dim",       width=6,  justify="right")
    t.add_column("Hace",     style="dim",       width=12)

    for i, s in enumerate(sessions, 1):
        sid = s["session_id"]
        is_current = sid == current_id
        marker = " [bold green]●[/bold green]" if is_current else ""
        tokens = s.get("input_tokens", 0) + s.get("output_tokens", 0)
        t.add_row(
            str(i),
            f"{sid[:8]}…{marker}",
            (s.get("model") or "—")[:22],
            str(s.get("message_count", 0)),
            _fmt_tokens(tokens) if tokens else "—",
            str(s.get("tool_calls", 0)),
            _ago(s.get("started_at", "")),
        )

    console.print(t)
    console.print(
        "  [dim]Usa[/dim] [cyan]/session <id>[/cyan] [dim]para restaurar una sesión.[/dim]"
    )
    console.print()


# ── Status / Gateway / Runtime ─────────────────────────────────────────────────

def print_status(config, session, runtime, context) -> None:
    """Vista general de estado del sistema al estilo /status de OpenClaw."""
    from agent.session import _ago

    console.print()
    console.rule("[bold cyan]Estado[/bold cyan]", style="blue")
    console.print()

    def row(label: str, value: str) -> None:
        console.print(f"  [dim]{label:<18}[/dim]{value}")

    stats = session.stats()

    # Agente
    row("Agente",    f"[bold cyan]{config.agent_emoji} {config.agent_name}[/bold cyan]  [dim]({config.agent_id})[/dim]")
    row("Modelo",    f"[bold cyan]{config.model or '—'}[/bold cyan]"
                     + (f"  [yellow]→ fast: {runtime.fast_model}[/yellow]" if runtime.fast_mode else ""))
    if config.fallback_active_config:
        row("Fallback",  f"[green]⚡ {config.fallback_model}[/green]  [dim](timeout: {config.fallback_timeout}s)[/dim]")
    elif config.fallback_model:
        row("Fallback",  f"[yellow]{config.fallback_model}[/yellow]  [dim](desactivado)[/dim]")
    row("Workspace", f"[dim]{config.workspace}[/dim]")
    row("Sesión",    f"[dim]{stats['session_id'][:8]}…[/dim]  {_ago(stats['started_at'])}")

    console.print()

    # Contexto
    msg_count = len(context.messages)
    est_tokens = sum(len(str(m.get("content", ""))) for m in context.messages) // 4
    row("Mensajes",  f"[white]{msg_count}[/white] [dim]en contexto[/dim]")
    row("Tokens est.", f"[white]~{_fmt_tokens(est_tokens)}[/white] / {_fmt_tokens(config.max_context_tokens)}")
    row("Ollama uso", f"{_fmt_tokens(stats['input_tokens'])}↑  {_fmt_tokens(stats['output_tokens'])}↓")

    console.print()

    # Runtime flags
    flags = [
        ("think",     runtime.think_level,   runtime.think_level != "off"),
        ("reasoning", "on" if runtime.reasoning else "off", runtime.reasoning),
        ("fast",      "on" if runtime.fast_mode else "off",  runtime.fast_mode),
        ("verbose",   "on" if runtime.verbose else "off",    runtime.verbose),
        ("trace",     "on" if runtime.trace else "off",      runtime.trace),
        ("elevated",  runtime.elevated,      runtime.elevated != "ask"),
        ("usage",     runtime.usage_display, runtime.usage_display != "tokens"),
        ("activation",runtime.activation,    runtime.activation != "always"),
    ]
    for name, val, active in flags:
        color = "bold cyan" if active else "dim"
        row(f"/{name}", f"[{color}]{val}[/{color}]")

    console.print()


def print_gateway_status(config) -> None:
    """Estado del servidor Ollama (equivalente a /gateway-status de OpenClaw)."""
    import ollama as _ollama

    console.print()
    console.rule("[bold cyan]Gateway / Ollama[/bold cyan]", style="blue")
    console.print()

    console.print(f"  [dim]Host:[/dim]  {config.ollama_host}")

    try:
        client = _ollama.Client(host=config.ollama_host)
        #try:
        data = client.list()
        #finally:
        #    return True
        #    client.close()
        models = data.get("models", []) if isinstance(data, dict) else list(data.models)
        console.print(f"  [green]●[/green]  Conectado  —  [white]{len(models)}[/white] [dim]modelos disponibles[/dim]")

        if models:
            console.print()
            t = Table(box=box.SIMPLE, show_header=True, padding=(0, 2))
            t.add_column("Modelo",  style="white")
            t.add_column("Familia", style="dim")
            t.add_column("Tamaño",  style="dim", justify="right")
            t.add_column("Activo",  style="bold green", width=7)
            for m in models:
                name   = m.model if hasattr(m, "model") else m.get("name", "—")
                _raw_size = m.size if hasattr(m, "size") else m.get("size", 0)
                size      = (_raw_size or 0) / 1e9
                det: Any  = m.details if hasattr(m, "details") else {}
                family = (det.family if hasattr(det, "family") else det.get("family", "—")) if det else "—"
                active = "◀" if name == config.model else ""
                t.add_row(name, str(family), f"{size:.1f} GB", active)
            console.print(t)
    except Exception as e:
        console.print(f"  [red]●[/red]  Sin conexión  —  {e}")

    console.print()


def print_commands(slash_help: dict) -> None:
    """Lista compacta de comandos sin descripciones largas."""
    console.print()
    console.rule("[bold cyan]Comandos disponibles[/bold cyan]", style="blue")
    console.print()
    for group, cmds in slash_help.items():
        console.print(f"  [dim]{group}[/dim]")
        names = "  ".join(f"[cyan]{c.split()[0]}[/cyan]" for c in cmds)
        console.print(f"    {names}")
        console.print()


def print_ctx_status(context, config, runtime) -> None:
    """Estado detallado del contexto: tokens, modo, resumen acumulado."""
    stats = context.stats()
    pct = int(stats["tokens_estimate"] / max(stats["max_tokens"], 1) * 100)
    bar = _progress_bar(stats["tokens_estimate"], stats["max_tokens"])

    console.print()
    console.rule("[bold cyan]Contexto[/bold cyan]", style="blue")
    console.print()

    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    t.add_column("key", style="dim", no_wrap=True)
    t.add_column("val", style="white")

    mode_color = "yellow" if runtime.ctx_mode == "full" else "green"
    t.add_row("Modo workspace",
              f"[{mode_color}]{runtime.ctx_mode}[/{mode_color}]  "
              f"[dim](mini ~150 tok | full ~800 tok)[/dim]")
    t.add_row("Mensajes en ctx", f"[white]{stats['messages']}[/white]")
    t.add_row("Tokens estimados",
              f"[white]~{_fmt_tokens(stats['tokens_estimate'])}[/white] "
              f"/ {_fmt_tokens(stats['max_tokens'])}  {bar}  [dim]{pct}%[/dim]")

    summary_status = (
        f"[cyan]{stats['summary_chars']} chars[/cyan]  [dim](inyectado en system prompt)[/dim]"
        if stats["has_summary"] else "[dim]ninguno[/dim]"
    )
    t.add_row("Resumen compact.", summary_status)
    t.add_row("Límite tokens",   f"[dim]{config.max_context_tokens}[/dim]")
    console.print(t)

    if stats["has_summary"]:
        console.print()
        console.print("  [dim cyan]Resumen acumulado:[/dim cyan]")
        preview = context.summary[:400].replace("\n", "\n  ")
        console.print(f"  [dim]{preview}[/dim]")
        if len(context.summary) > 400:
            console.print(f"  [dim]… ({len(context.summary) - 400} chars más)[/dim]")

    console.print()
    console.print(
        "  [dim]Comandos:[/dim]  "
        "[cyan]/ctx mini[/cyan] · [cyan]/ctx full[/cyan] · "
        "[cyan]/compact[/cyan] · [cyan]/compact fast[/cyan] · [cyan]/checkpoint[/cyan]"
    )
    console.print()


def print_mem_list(memories: list[dict], embed_available: bool) -> None:
    """Lista de memorias con metadatos."""
    console.print()
    console.rule("[bold cyan]Memoria persistente[/bold cyan]", style="blue")
    console.print()

    if not memories:
        console.print("  [dim]Sin memorias guardadas. Usa /mem save <nombre> o pide al agente que recuerde algo.[/dim]")
        console.print()
        return

    t = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    t.add_column("#",       style="dim",    width=3,  justify="right")
    t.add_column("Nombre",  style="cyan",   width=28)
    t.add_column("Tamaño",  style="dim",    width=8,  justify="right")
    t.add_column("Embed",   style="dim",    width=7)
    t.add_column("Desc",    style="white")

    for i, m in enumerate(memories, 1):
        has_emb = "[green]✓[/green]" if m.get("has_embedding") else "[dim]—[/dim]"
        size_str = f"{m['size']}B" if m['size'] < 1024 else f"{m['size']//1024}K"
        t.add_row(str(i), m["name"], size_str, has_emb, m.get("desc", ""))

    console.print(t)
    emb_status = (
        "[green]disponible[/green]" if embed_available
        else "[dim]no disponible[/dim]"
    )
    console.print(f"  [dim]Embeddings semánticos:[/dim] {emb_status}")
    console.print()
    console.print(
        "  [dim]Comandos:[/dim]  "
        "[cyan]/mem search <query>[/cyan] · "
        "[cyan]/mem show <nombre>[/cyan] · "
        "[cyan]/mem rm <nombre>[/cyan]"
    )
    console.print()


def print_mem_search(hits: list[tuple[float, str, str]], query: str) -> None:
    """Resultados de búsqueda semántica en memoria."""
    console.print()
    console.rule(
        f"[bold cyan]Búsqueda:[/bold cyan] [white]{query[:60]}[/white]",
        style="blue",
    )
    console.print()

    if not hits:
        console.print("  [dim]Sin resultados relevantes (umbral de similitud: 0.30).[/dim]")
        console.print()
        return

    for score, slug, snippet in hits:
        bar_w = int(score * 20)
        bar = "[cyan]" + "█" * bar_w + "[/cyan]" + "[dim]" + "░" * (20 - bar_w) + "[/dim]"
        console.print(f"  {bar}  [bold cyan]{slug}[/bold cyan]  [dim]{score:.3f}[/dim]")
        # Muestra primeras 3 líneas del snippet
        for line in snippet.splitlines()[:3]:
            if line.strip():
                console.print(f"    [dim]{line[:100]}[/dim]")
        console.print()


def print_runtime(runtime) -> None:
    """Muestra todos los flags de runtime actuales."""
    console.print()
    console.rule("[bold cyan]Configuración en tiempo de ejecución[/bold cyan]", style="blue")
    console.print()

    t = Table(box=box.SIMPLE, show_header=True, padding=(0, 2))
    t.add_column("Comando",   style="cyan", no_wrap=True)
    t.add_column("Valor",     style="white")
    t.add_column("Opciones",  style="dim")

    rows = [
        ("/think",      runtime.think_level,                   "off | minimal | low | medium | high"),
        ("/reasoning",  "on" if runtime.reasoning else "off",  "on | off"),
        ("/fast",       "on" if runtime.fast_mode else "off",   "on | off | status"),
        ("/verbose",    "on" if runtime.verbose else "off",    "on | off"),
        ("/trace",      "on" if runtime.trace else "off",      "on | off"),
        ("/elevated",   runtime.elevated,                      "off | on | ask | full"),
        ("/usage",      runtime.usage_display,                 "off | tokens | full"),
        ("/activation", runtime.activation,                    "always | mention"),
    ]
    for cmd, val, opts in rows:
        is_default = val in ("off", "ask", "tokens", "always", "off")
        style = "dim" if is_default else "bold cyan"
        t.add_row(cmd, f"[{style}]{val}[/{style}]", opts)

    console.print(t)
    console.print()


# ── Branches ──────────────────────────────────────────────────────────────────

def print_branches(branches: list[dict], current_msgs: int) -> None:
    console.print()
    console.rule("[bold cyan]Ramas de conversación[/bold cyan]", style="blue")
    console.print()
    if not branches:
        console.print("  [dim]Sin ramas guardadas. Usa /branch save <nombre>.[/dim]")
        console.print()
        return
    t = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    t.add_column("#",      style="dim",   width=3, justify="right")
    t.add_column("Nombre", style="cyan",  width=22)
    t.add_column("Msgs",   style="white", width=5, justify="right")
    t.add_column("Creada", style="dim")
    for i, b in enumerate(branches, 1):
        ts = b.get("created_at", "")[:16].replace("T", " ")
        t.add_row(str(i), b["name"], str(b.get("message_count", 0)), ts)
    console.print(t)
    console.print(f"  [dim]Contexto actual:[/dim] {current_msgs} mensajes")
    console.print(
        "  [dim]Comandos:[/dim]  "
        "[cyan]/branch load <nombre>[/cyan] · "
        "[cyan]/branch rm <nombre>[/cyan]"
    )
    console.print()


# ── Tasks ─────────────────────────────────────────────────────────────────────

_STATUS_ICON  = {"todo": "○", "wip": "◐", "done": "●"}
_STATUS_COLOR = {"todo": "white", "wip": "yellow", "done": "dim"}


def print_tasks(tasks: list[dict]) -> None:
    console.print()
    console.rule("[bold cyan]Tareas[/bold cyan]", style="blue")
    console.print()
    if not tasks:
        console.print("  [dim]Sin tareas. Usa /tasks add <título>.[/dim]")
        console.print()
        return
    t = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    t.add_column("ID",     style="dim",   width=9)
    t.add_column("Estado", style="white", width=8)
    t.add_column("Título", style="white")
    t.add_column("Fecha",  style="dim",   width=11)
    for task in tasks:
        st    = task["status"]
        icon  = _STATUS_ICON.get(st, "?")
        color = _STATUS_COLOR.get(st, "white")
        ts    = task.get("created_at", "")[:10]
        t.add_row(
            f"[dim]{task['id']}[/dim]",
            f"[{color}]{icon} {st}[/{color}]",
            task["title"],
            ts,
        )
    console.print(t)
    todo = sum(1 for tk in tasks if tk["status"] == "todo")
    wip  = sum(1 for tk in tasks if tk["status"] == "wip")
    done = sum(1 for tk in tasks if tk["status"] == "done")
    console.print(f"  [dim]○ todo: {todo}  ◐ wip: {wip}  ● done: {done}[/dim]")
    console.print(
        "  [dim]Comandos:[/dim]  "
        "[cyan]/tasks add <título>[/cyan] · "
        "[cyan]/tasks wip <id>[/cyan] · "
        "[cyan]/tasks done <id>[/cyan] · "
        "[cyan]/tasks rm <id>[/cyan]"
    )
    console.print()


# ── Schedule ──────────────────────────────────────────────────────────────────

def print_schedule(jobs: list[dict], scheduler) -> None:
    console.print()
    console.rule("[bold cyan]Tareas programadas[/bold cyan]", style="blue")
    console.print()
    if not jobs:
        console.print("  [dim]Sin jobs. Usa /schedule add <minutos> <comando>.[/dim]")
        console.print()
        return
    t = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    t.add_column("ID",      style="dim",   width=9)
    t.add_column("Activo",  style="white", width=7)
    t.add_column("Cada",    style="dim",   width=8)
    t.add_column("Próxima", style="white", width=10)
    t.add_column("Runs",    style="dim",   width=5, justify="right")
    t.add_column("Comando", style="white")
    for job in jobs:
        enabled  = "[green]✓[/green]" if job["enabled"] else "[dim]—[/dim]"
        mins     = job["interval_minutes"]
        interval = f"{mins}m" if mins < 60 else f"{mins // 60}h"
        next_r   = scheduler.next_run(job)
        runs     = str(job.get("run_count", 0))
        cmd_prev = job["command"][:40] + ("…" if len(job["command"]) > 40 else "")
        t.add_row(f"[dim]{job['id']}[/dim]", enabled, interval, next_r, runs, cmd_prev)
    console.print(t)
    console.print(
        "  [dim]Comandos:[/dim]  "
        "[cyan]/schedule add <min> <cmd>[/cyan] · "
        "[cyan]/schedule toggle <id>[/cyan] · "
        "[cyan]/schedule run[/cyan] · "
        "[cyan]/schedule rm <id>[/cyan]"
    )
    console.print()


# ── Skills / Plugins ──────────────────────────────────────────────────────────

def print_skills(skills: list[dict]) -> None:
    _print_extensions(skills, "Skills", "skill")


def print_plugins(plugins: list[dict]) -> None:
    _print_extensions(plugins, "Plugins", "plugin")


def _print_extensions(items: list[dict], title: str, kind: str) -> None:
    console.print()
    console.rule(f"[bold cyan]{title}[/bold cyan]", style="blue")
    console.print()
    if not items:
        console.print(f"  [dim]Sin {kind}s. Usa /{kind}s create <nombre>.[/dim]")
        console.print()
        return
    t = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    t.add_column("Nombre",      style="cyan",  width=22)
    t.add_column("Activo",      style="white", width=7)
    t.add_column("Tools/Hooks", style="dim",   width=12)
    t.add_column("Descripción", style="dim")
    for item in items:
        enabled = "[green]✓[/green]" if item["enabled"] else "[dim]—[/dim]"
        if kind == "skill":
            extra = f"{item.get('tool_count', 0)} tools"
        else:
            extra = "cargado" if item.get("loaded") else "—"
        t.add_row(item["name"], enabled, extra, (item.get("description") or "")[:60])
    console.print(t)
    console.print(
        f"  [dim]Comandos:[/dim]  "
        f"[cyan]/{kind}s create <nombre>[/cyan] · "
        f"[cyan]/{kind}s enable <nombre>[/cyan] · "
        f"[cyan]/{kind}s disable <nombre>[/cyan]"
    )
    console.print()


# ── Config panel interactivo ──────────────────────────────────────────────────

def print_config_full(config) -> None:
    console.print()
    console.rule("[bold cyan]Configuración completa[/bold cyan]", style="blue")
    console.print()

    sections = [
        ("Agente", [
            ("ID",          config.agent_id),
            ("Nombre",      f"{config.agent_emoji} {config.agent_name}"),
            ("Modelo",      config.model or "(sin seleccionar)"),
            ("Host",        config.ollama_host),
            ("Workspace",   config.workspace),
        ]),
        ("Contexto", [
            ("maxTokens",           str(config.max_context_tokens)),
            ("minKeep",             str(config.compact_min_keep)),
            ("compactThreshold",    str(config.compact_threshold)),
            ("maxSummaryChars",     str(config.max_summary_chars)),
            ("maxToolResultTokens", str(config.max_tool_result_tokens)),
            ("autoContinueMax",     str(config.auto_continue_max)),
        ]),
        ("Embeddings", [
            ("modelo",       config.embed_model),
            ("maxChars",     str(config.embed_max_input_chars)),
            ("threshold",    str(config.embed_similarity_threshold)),
            ("snippetChars", str(config.embed_snippet_chars)),
            ("topK",         str(config.embed_top_k)),
        ]),
        ("Herramientas", [
            ("readLines",          str(config.read_file_lines_default)),
            ("readLinesWarnLarge", str(config.read_file_lines_warn_large)),
            ("webFetchChars",      str(config.web_fetch_max_chars)),
            ("bashMaxOutputChars", str(config.bash_max_output_chars)),
        ]),
        ("Workspace", [
            ("maxMemoryLines", str(config.ws_max_memory_lines)),
            ("maxDailyChars",  str(config.ws_max_daily_chars)),
        ]),
        ("SearXNG", [
            ("URL",         config.searxng_url or "[dim](sin configurar)[/dim]"),
            ("Activado",    "[green]sí[/green]" if config.searxng_enabled else "[dim]no[/dim]"),
            ("maxResults",  str(config.searxng_max_results)),
            ("categories",  config.searxng_categories),
            ("language",    config.searxng_language),
            ("safeSearch",  str(config.searxng_safe_search)),
            ("timeout",     f"{config.searxng_timeout}s"),
        ]),
        ("Logging", [
            ("Activo",      "[green]sí[/green]" if config.log_enabled else "[dim]no[/dim]"),
            ("Nivel",       config.log_level),
            ("Fichero",     config.log_file or "[dim](~/.oocode/logs/oocode.log)[/dim]"),
            ("maxSizeMb",   str(config.log_max_size)),
            ("maxFiles",    str(config.log_max_files)),
        ]),
        ("Opciones del modelo", [
            (k, str(v)) for k, v in [
                ("temperature",    config.model_temperature),
                ("top_p",          config.model_top_p),
                ("top_k",          config.model_top_k),
                ("num_ctx",        config.model_num_ctx),
                ("num_predict",    config.model_num_predict),
                ("repeat_penalty", config.model_repeat_penalty),
                ("seed",           config.model_seed),
            ] if v is not None
        ] or [("—", "[dim](usando defaults del modelo)[/dim]")]),
        ("Permisos de herramientas", [
            (tool, f"[green]{mode}[/green]" if mode == "auto" else
                   f"[yellow]{mode}[/yellow]" if mode == "ask" else
                   f"[red]{mode}[/red]")
            for tool, mode in sorted(config.permissions.items())
        ] or [("—", "[dim](usando defaults)[/dim]")]),
        ("Plugins activos", [
            (str(i + 1), p) for i, p in enumerate(config.plugins_enabled)
        ] or [("—", "[dim](ninguno)[/dim]")]),
        ("Opciones de plugins", [
            (f"{plugin}.{key}", str(val))
            for plugin, opts in sorted(getattr(config, "plugin_options", {}).items())
            for key, val in sorted(opts.items())
        ] or [("—", "[dim](ninguno)[/dim]")]),
        ("Skills activos", [
            (str(i + 1), s) for i, s in enumerate(config.skills_enabled)
        ] or [("—", "[dim](ninguno)[/dim]")]),
        ("RAG automático", [
            ("Activado",          "[green]sí[/green]" if config.rag_enabled else "[dim]no[/dim]"),
            ("topK",              str(config.rag_top_k)),
            ("threshold",         str(config.rag_similarity_threshold)),
            ("maxSnippetChars",   str(config.rag_max_snippet_chars)),
            ("indexInterval",     f"{config.rag_index_interval}s"),
            ("topKComplex",       str(config.rag_top_k_complex)),
            ("thresholdComplex",  str(config.rag_threshold_complex)),
            ("complexMinChars",   str(config.rag_complex_min_chars)),
        ]),
        ("MCP", [
            ("oocodeAssistant", "[green]habilitado[/green]" if config.mcp_oocode_assistant_enabled else "[dim]deshabilitado[/dim]"),
            ("systemAssistant", "[green]habilitado[/green]" if config.mcp_system_assistant_enabled else "[dim]deshabilitado[/dim]"),
            ("requestTimeout",  f"{config.mcp_request_timeout}s"),
            ("servers",         str(len(config.mcp_servers)) + " externo(s)"),
        ]),
        ("Hooks", [
            ("Activo",   "[green]sí[/green]" if config.hooks_enabled else "[dim]no[/dim]"),
            ("builtins", ", ".join(config.hooks_builtins) or "[dim](ninguno)[/dim]"),
        ]),
        ("Fallback", [
            ("Activado",        "[green]sí[/green]" if config.fallback_enabled else "[dim]no[/dim]"),
            ("Modelo",          config.fallback_model or "[dim](sin configurar)[/dim]"),
            ("Timeout",         f"{config.fallback_timeout}s"),
            ("Estado efectivo", "[green]⚡ activo[/green]" if config.fallback_active_config else "[dim]desactivado[/dim]"),
        ]),
    ]

    for section_name, rows in sections:
        t = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        t.add_column("key", style="dim",   no_wrap=True, width=24)
        t.add_column("val", style="white")
        for k, v in rows:
            t.add_row(k, v)
        console.print(f"  [bold dim]{section_name}[/bold dim]")
        console.print(t)

    console.print("  [bold dim]Permisos[/bold dim]")
    p = Table(box=box.SIMPLE, show_header=True, padding=(0, 2))
    p.add_column("Herramienta", style="dim")
    p.add_column("Permiso",     style="white")
    for tool, mode in config.permissions.items():
        color = {"auto": "green", "ask": "yellow", "deny": "red"}.get(mode, "white")
        p.add_row(tool, f"[{color}]{mode}[/{color}]")
    console.print(p)
    console.print()


# ── Keybindings ───────────────────────────────────────────────────────────────

def _fmt_key(key: str) -> str:
    """Convierte notación prompt_toolkit a texto legible: c-o → Ctrl+O."""
    key = key.strip()
    parts = key.split()
    rendered = []
    for part in parts:
        if part.startswith("c-"):
            rendered.append(f"Ctrl+{part[2:].upper()}")
        elif part.startswith("s-"):
            rendered.append(f"Shift+{part[2:].upper()}")
        elif part == "escape":
            rendered.append("Esc")
        elif part == "enter":
            rendered.append("Enter")
        elif part.startswith("f") and part[1:].isdigit():
            rendered.append(part.upper())
        else:
            rendered.append(part)
    return " ".join(rendered)


def print_keybindings(kb_rows: list[dict]) -> None:
    console.print()
    console.rule("[bold cyan]Keybindings[/bold cyan]", style="blue")
    console.print()

    t = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    t.add_column("Tecla",    style="bold cyan", width=18, no_wrap=True)
    t.add_column("Acción",   style="white",     width=20)
    t.add_column("Descripción", style="dim")
    t.add_column("",         style="dim",       width=4)

    for row in kb_rows:
        key_str   = _fmt_key(row["key"])
        modified  = "[yellow]mod[/yellow]" if row["modified"] else ""
        t.add_row(key_str, row["action"], row["desc"], modified)

    console.print(t)
    console.print(
        "  [dim]Comandos:[/dim]  "
        "[cyan]/keybindings set <acción> <key>[/cyan]  ·  "
        "[cyan]/keybindings reset [acción][/cyan]"
    )
    console.print()


def print_expand_output(tool_calls: list[tuple], last_response: str, _console=None) -> None:
    """Expande la salida completa del último turno (Ctrl+O)."""
    import json as _json
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.markdown import Markdown

    c = _console or console

    if not tool_calls and not last_response:
        c.print("  [dim]No hay salida del turno anterior.[/dim]")
        return

    c.print()
    if tool_calls:
        c.rule(
            f"[bold cyan]Tool calls[/bold cyan]  [dim]({len(tool_calls)} herramienta{'s' if len(tool_calls)!=1 else ''})[/dim]",
            style="dim cyan",
        )
        for i, (name, args_str, result) in enumerate(tool_calls, 1):
            result_str = str(result)
            n_lines    = result_str.count("\n") + 1
            n_chars    = len(result_str)

            c.print(
                f"\n  [dim cyan]⚙[/dim cyan]  [{i}/{len(tool_calls)}]  "
                f"[bold]{name}[/bold]  "
                f"[dim]{args_str[:100]}{'…' if len(args_str) > 100 else ''}[/dim]  "
                f"[dim cyan]▸ {n_lines} líneas · {n_chars} chars[/dim cyan]"
            )

            try:
                parsed = _json.loads(result_str)
                body = Syntax(
                    _json.dumps(parsed, indent=2, ensure_ascii=False),
                    "json", theme="monokai", line_numbers=True, word_wrap=True,
                )
                c.print(Panel(body, border_style="dim cyan", padding=(0, 1)))
            except Exception:
                first_line = result_str.lstrip()[:80]
                if first_line.startswith(("#!", "def ", "class ", "import ", "#!/")):
                    lang = "python"
                elif first_line.startswith(("$ ", "# ", ">> ")):
                    lang = "bash"
                else:
                    lang = "text"
                body = Syntax(
                    result_str, lang, theme="monokai",
                    line_numbers=(n_lines > 10), word_wrap=True,
                )
                c.print(Panel(body, border_style="dim", padding=(0, 1)))

    if last_response:
        c.print()
        c.rule("[dim]Respuesta del asistente[/dim]", style="dim")
        c.print(Markdown(last_response))

    c.print()
    c.print("  [dim](Ctrl+O de nuevo para expandir · /copy para copiar la respuesta)[/dim]")
    c.print()
