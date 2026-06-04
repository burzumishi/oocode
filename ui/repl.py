"""REPL de OOCode — delega en OOCodeApp (full-screen TUI).

Este módulo también exporta las funciones de estilo/prompt/toolbar que
OOCodeApp reutiliza para mantener consistencia visual.
"""
import html
import time
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML

from agent.runtime import COLOR_PRESETS
from agent.loop_helpers import _ctx_bar, _fmt_elapsed, _COMPACT_TEXT, _COMPACT_NEAR_TEXT

# TTL cache para el conteo de memorias — evita glob en disco en cada render (7/s)
_mem_cache: dict = {"count": 0, "has": False, "ts": -999.0}


def _refresh_mem_cache(mem_sys) -> tuple[bool, int]:
    now = time.monotonic()
    if now - _mem_cache["ts"] < 30.0:
        return _mem_cache["has"], _mem_cache["count"]
    has   = mem_sys.has_memories()
    count = len(mem_sys.list_all()) if has else 0
    _mem_cache.update({"count": count, "has": has, "ts": now})
    return has, count

# Modos de permisos que cicla Shift+Tab
_PERM_CYCLE  = ["ask", "on", "full"]
_PERM_ICONS  = {"off": "○", "ask": "◎", "on": "◉", "full": "●"}
_PERM_LABELS = {"off": "solo lectura", "ask": "normal", "on": "elevado", "full": "sin restricciones"}

# ── Iconos de indicadores (todos los pares deben ser del mismo ancho de pantalla) ──

# Subagentes: 4 frames de emoji wide (2 columnas cada uno)
_SUBAGENT_FRAMES = ["🤖", "🦾", "🧠", "💻"]

# RAG indexando (cargando): ↻ activo / ◉ completo  — 1 col cada uno
_RAG_IDX_ICONS = ["↻", "◉"]

# RAG activo (hits en memoria semántica): ✦ / ◈  — 1 col cada uno
_RAG_ICONS = ["✦", "◈"]

# Memoria (mems guardadas): ⬢ / ⬡  — 1 col cada uno
_MEM_ICONS = ["⬢", "⬡"]

# MCP (servers conectados): ◉ / ◎  — 1 col cada uno
_MCP_ICONS = ["◉", "◎"]

# LSP (servidores activos): ⌨ / ✐  — 1 col cada uno
_LSP_ICONS = ["⌨", "✐"]

# Paletas de parpadeo para el tiempo total del agente (alterna cada segundo)
_BLINK_STYLES = [
    ("bg:#2a0e00 #ff7722 bold", "elapsed-a"),   # naranja
    ("bg:#1e0030 #ee44ff bold", "elapsed-b"),   # magenta
]


def _build_style(accent: str) -> Style:
    accent_hex = COLOR_PRESETS.get(accent, COLOR_PRESETS["cyan"])[0]
    return Style.from_dict({
        # ── Elementos del prompt / conversación ────────────────────────────
        "brand":   "#4499ff bold",          # nombre del agente
        "agent":   f"{accent_hex} bold",    # icono/nombre acento
        "sep":       "#2288cc bold",          # separadores ───── (azul vivo)
        "sep-label": f"{accent_hex} bold",  # [ oocode ❯ ... ] — usa color acento
        "project":   "#4499ff",             # ruta de proyecto (azul brillante)
        "arrow":   "#00ff88 bold",          # ❯  cursor de entrada
        "spinner": "#00e5ff bold italic",   # línea de estado activo (cyan neón)
        "dim":     "#8899bb",               # hints, tips, texto secundario (más claro)
        # ── Barra inferior ─────────────────────────────────────────────────
        "bottom-toolbar":      "bg:#06060f #334466",
        "bottom-toolbar.text": "bg:#06060f #446688",
        "bottom-toolbar.key":  "bg:#06060f #00aaff bold",
        # ── Bloques coloreados de la toolbar ───────────────────────────────
        "think-active":  "bg:#18004a #cc44ff bold",   # think  — violeta neón
        "ask-mode":      "bg:#003040 #00e5ff bold",   # ◎ask   — cyan neón
        "ctx-ok":        "bg:#001a08 #00ff88 bold",   # ctx    — verde neón
        "ctx-warn":      "bg:#1a1000 #ffdd00 bold",   # ctx    — amarillo neón (warning)
        "ctx-near-hint": "bg:#1a0800 #ff7700 bold",   # ctx    — naranja (↻ cerca compactación)
        "ctx-crit":      "bg:#1a0000 #ff3355 bold",   # ctx    — rojo neón
        "model-label":   "bg:#00101e #22bbff bold",   # modelo — azul brillante
        "elapsed-a":     "bg:#1a0700 #ff6600 bold",   # parpadeo — naranja neón
        "elapsed-b":     "bg:#180020 #ff00cc bold",   # parpadeo — rosa neón
        "rag-active":    "bg:#001a08 #00ff88 bold",   # rag      — verde neón
        "rag-indexing":  "bg:#1a1400 #ffdd00 bold",   # rag idx  — ámbar neón
        "vision-active": "bg:#001020 #44aaff bold",   # vision   — azul claro
        "mcp-active":    "bg:#0a001a #bb66ff bold",   # mcp      — violeta claro
        "lsp-active":    "bg:#001a12 #00ddaa bold",   # lsp      — verde menta
        "agent-main":    "bg:#001020 #4488ff bold",   # agente   — azul real (siempre visible)
        # ── Subagent panel (sin bg: hereda el fondo del status bar) ──────────────
        "sub-header":   "#00e5ff bold",      # ⏵⏵ cabecera — cyan bold
        "sub-main":     "#00e5ff bold",      # ● agente principal
        "sub-running":  "#00e5ff bold",      # ◯ subagente activo
        "sub-done":     "#00cc66",           # ◯ subagente terminado
        "sub-dim":      "#8899bb",           # hints, elapsed, hints
        "sub-name":     "#bb66ff bold",      # emoji + id del subagente
        "sub-chat":     "#00e5ff bold",      # 💬 parpadeante (comunicación sub↔principal)
        # ── Task progress panel ────────────────────────────────────────────────
        "task-done":     "#00cc66",                     # ✔ verde brillante
        "task-active":   "#00e5ff bold",                # ◼ cyan brillante
        # ── Status window — spinner thinking ──────────────────────────────────
        "status-word":      "#00e5ff bold",             # Cavilando… — cyan neón
        "status-phrase":    "#ffcc00 bold italic",      # sinaptizando más… — ámbar vivo
        "time-dim":         "#667799",                  # (22s · ) — gris azulado normal
        # ── Status window — barra de contexto coloreada ───────────────────────
        "status-bar-ok":    "#00cc66 bold",             # ▰▰▰ verde (ctx < 60%)
        "status-bar-warn":  "#ffdd00 bold",             # ▰▰▰ amarillo (60–umbral-10%)
        "status-bar-near":  "#ff8800 bold",             # ▰▰▰ naranja (cerca compactación)
        "status-bar-crit":  "#ff3333 bold",             # ▰▰▰ rojo (sobre umbral)
        "status-hint-near": "#ff7700 bold",             # ↻ cerca compactación — naranja
        "status-hint-crit": "#ff3355 bold",             # ↻ compactando — rojo neón
        # ── Status window — compactación en curso ────────────────────────────
        "compact-arrow":    "#ffbb00 bold",             # ↻  — ámbar brillante
        "compact-title":    "#ffffff bold",             # Compactando — blanco bold
        "compact-dim":      "#8899bb",                  # detalles de msgs/tok
        "compact-bar":      "#ff9900 bold",             # ▰▰▰ barra progreso compactación
        "compact-pct":      "#ffcc44 bold",             # 81% porcentaje compactación
        "compact-phrase":   "#00e5ff bold",             # resumiendo N msgs… — cyan
    })



def _build_toolbar(agent_loop) -> HTML:
    """Barra de estado inferior (3 líneas).

    Línea 1 — indicadores: agente, permisos, think, mem, rag, vision, mcp, ctx, modelo, tiempo
    Línea 2 — LSP: servidores de lenguaje activos (o '— lsp' si ninguno)
    Línea 3 — keybindings rápidos (F1-F4, ^O, ^Y, ^L, ^T, ^P si visión activa)

    Separador reducido: ' · ' (1 espacio a cada lado) en vez de '  ·  ' (2 espacios).
    Cada línea comienza con '· ' (bullet pegado al borde) y termina con ' ·'.
    """
    rt        = agent_loop.rt
    perm_icon = _PERM_ICONS.get(rt.elevated, "◎")
    ctx_stats = agent_loop.context.stats()
    ctx_tok   = ctx_stats["tokens_estimate"]
    max_tok   = ctx_stats["max_tokens"]
    ctx_pct   = int(ctx_tok / max(max_tok, 1) * 100)
    thresh    = int(agent_loop.context.compact_threshold * 100)

    ctx_bar   = _ctx_bar(ctx_tok, max_tok, 10, plain=True)

    if ctx_pct >= thresh:
        ctx_color    = "ctx-crit"
        compact_hint = f" {_COMPACT_TEXT}"
        hint_style   = ctx_color       # hint en rojo junto con la barra
    elif ctx_pct >= thresh - 10:
        ctx_color    = "ctx-warn"
        compact_hint = f" {_COMPACT_NEAR_TEXT}"
        hint_style   = "ctx-near-hint" # naranja separado de la barra amarilla
    else:
        ctx_color    = "ctx-ok"
        compact_hint = ""
        hint_style   = ""

    # Modelo: hasta 18 chars (más que antes) para aprovechar el espacio ganado con
    # el separador reducido. Incluye proveedor/familia: batiai/qwen3.5-9b → visible.
    model_short  = (agent_loop.config.model or "—").split(":")[0][:18]
    _tick        = int(time.time())
    blink_on     = _tick % 2 == 0
    _blink_phase = _tick % 4   # 4 fases para animaciones ricas

    # ── Bloque think/reasoning ──────────────────────────────────────────────
    think_parts = []
    if rt.think_level != "off":
        think_parts.append(rt.think_level[:3])
    if rt.reasoning:
        think_parts.append("+r")
    think_block = (
        f' · <think-active>think:{html.escape(".".join(think_parts))}</think-active>'
        if think_parts else ""
    )

    # ── Bloque RAG ─────────────────────────────────────────────────────────
    rag        = getattr(agent_loop, "_workspace_rag", None)
    rag_block  = ""
    if getattr(agent_loop.config, "rag_enabled", False) and rag is not None:
        if getattr(rag, "_indexing", False):
            files_done = getattr(rag, "_files_indexed", 0)
            rag_icon   = _RAG_IDX_ICONS[_blink_phase % len(_RAG_IDX_ICONS)]
            rag_block  = f' · <rag-indexing>{rag_icon} rag:idx({files_done})</rag-indexing>'
        else:
            n_files   = rag.indexed_files
            n_chunks  = getattr(rag, "index_size", 0)
            last_hits = getattr(rag, "last_hits", 0)
            rag_icon  = _RAG_ICONS[_blink_phase % len(_RAG_ICONS)]
            if last_hits > 0:
                rag_block = f' · <rag-active>{rag_icon} rag:{n_files}f·{last_hits}↑</rag-active>'
            else:
                rag_block = f' · <rag-active>{rag_icon} rag:{n_files}f/{n_chunks}c</rag-active>'

    # ── Bloque vision (Ctrl+P para adjuntar imagen) ─────────────────────────
    vision_block = ""
    if (getattr(agent_loop.config, "vision_show_indicator", True)
            and getattr(agent_loop, "_model_supports_images", lambda: False)()):
        pending_imgs = len(getattr(agent_loop, "_pending_images", []))
        if pending_imgs > 0:
            # Muestra el conteo de imágenes pendientes de forma destacada
            vision_block = f' · <vision-active>🖼 ×{pending_imgs} adjunta(s)</vision-active>'
        else:
            vision_block = ' · <vision-active>🖼 vision</vision-active>'

    # ── Bloque mem ─────────────────────────────────────────────────────────
    mem_block = ""
    mem_sys   = getattr(agent_loop, "memory", None)
    if mem_sys is not None:
        _has_mem, n_mem = _refresh_mem_cache(mem_sys)
        if _has_mem:
            mem_icon  = _MEM_ICONS[_blink_phase % len(_MEM_ICONS)]
            mem_block = f' · <rag-active>{mem_icon} mem:{n_mem}</rag-active>'

    # ── Bloque MCP — ancho fijo siempre (evita desplazamiento al conectar) ──
    mcp_block = ""
    mcp_pool  = getattr(agent_loop, "_mcp_pool", None)
    if mcp_pool is not None:
        n_mcp = mcp_pool.client_count
        if n_mcp > 0:
            mcp_icon  = _MCP_ICONS[_blink_phase % len(_MCP_ICONS)]
            mcp_block = f' · <mcp-active>{mcp_icon} mcp:{n_mcp}</mcp-active>'
        else:
            mcp_block = ' · <text>○ mcp</text>'

    # ── Bloque LSP — calculado aquí, usado solo en línea 2 ────────────────
    # _lsp_mod es el módulo real cargado por PluginManager (evita _pool=None en
    # el módulo importado directamente).
    lsp_line2 = ""   # contenido de línea 2 (servidores activos o placeholder)
    _lsp_mod  = getattr(agent_loop, "_lsp_mod", None)
    lsp_pool  = getattr(_lsp_mod, "_pool", None) if _lsp_mod is not None else None
    if lsp_pool is not None:
        active_exts = lsp_pool.active_extensions
        if active_exts:
            lsp_icon  = _LSP_ICONS[_blink_phase % len(_LSP_ICONS)]
            names     = " ".join(e.lstrip(".") for e in active_exts)
            lsp_line2 = f'· <lsp-active> {lsp_icon} {html.escape(names)} </lsp-active>'
    # Placeholder cuando LSP está cargado pero sin servidores activos aún
    if not lsp_line2 and lsp_pool is not None:
        lsp_line2 = '· <text> lsp — </text>'

    # ── Bloque agente (siempre visible) + subagentes activos si los hay ─────
    task_start  = getattr(agent_loop, "_task_start_time", None)  # leer antes del icono

    # Nombre del agente: hasta 14 chars en la toolbar (el panel de subagentes
    # usa el nombre completo)
    _agent_name = html.escape((getattr(agent_loop.config, "agent_name", None) or "main")[:14])
    try:
        from agent.subagent import list_running as _list_running
        _n_sub = len(_list_running())
    except Exception:
        _n_sub = 0

    # Animación solo cuando el agente está activo; estático en reposo
    _is_active = (task_start is not None) or (_n_sub > 0)
    _bot_icon  = (_SUBAGENT_FRAMES[_blink_phase % len(_SUBAGENT_FRAMES)]
                  if _is_active else _SUBAGENT_FRAMES[0])   # 🤖 estático en reposo

    # Primer bloque: comienza con '· ' (sin espacio inicial — ocupa todo el borde)
    if _n_sub > 0:
        # Con subagentes: icono animado + badge de count; el panel de subagentes
        # muestra la lista completa sobre la toolbar. El 💬 parpadea con blink_on
        # ("  " = 2 celdas en la fase apagada → mismo ancho que el emoji, sin saltos).
        _chat = "\U0001f4ac" if blink_on else "  "
        agent_block = (
            f'· <mcp-active>{_bot_icon} {_agent_name} {_chat} sub:{_n_sub}</mcp-active>'
        )
    else:
        agent_block = f'· <agent-main>{_bot_icon} {_agent_name}</agent-main>'

    # ── Bloque tiempo de tarea (parpadeo vivo / congelado / vacío) ──────────
    task_elapsed = getattr(agent_loop, "_task_elapsed", 0.0)

    if task_start is not None:
        elapsed_str   = _fmt_elapsed(time.time() - task_start)
        blink_cls     = "elapsed-a" if blink_on else "elapsed-b"
        elapsed_block = f' · <{blink_cls}>{html.escape(elapsed_str)}</{blink_cls}>'
    elif task_elapsed > 0:
        elapsed_block = f' · <elapsed-a>{html.escape(_fmt_elapsed(task_elapsed))}</elapsed-a>'
    else:
        elapsed_block = ""

    # ══════════════════════════════════════════════════════════════════════════
    # LÍNEA 1: indicadores principales
    #   · 🤖 main · ◎ ask · think · ⬡ mem · ◈ rag · 🖼 vision · ◉ mcp · ctx · modelo · tiempo ·
    # ══════════════════════════════════════════════════════════════════════════
    line1 = (
        agent_block                  # primer bloque: '· <estilo>...</estilo>'
        + f' · <ask-mode>{html.escape(perm_icon)} {html.escape(rt.elevated)}</ask-mode>'
        + think_block                # '' o ' · <think-active>...'
        + mem_block                  # '' o ' · <rag-active>mem:N...'
        + rag_block                  # '' o ' · <rag-active/rag-indexing>...'
        + vision_block               # '' o ' · <vision-active>🖼...'
        + mcp_block                  # '' o ' · <mcp-active>mcp:N...'
        # LSP ya NO va aquí — está en línea 2
        + f' · <{ctx_color}>ctx: {html.escape(ctx_bar)} {ctx_pct}%</{ctx_color}>'
        + (f'<{hint_style}>{html.escape(compact_hint)}</{hint_style}>'
           if compact_hint and hint_style != ctx_color
           else (html.escape(compact_hint) if compact_hint else ""))
        + f' · <model-label>{html.escape(model_short)}</model-label>'
        + elapsed_block              # '' o ' · <elapsed-a/b>Ns...'
        + ' ·'
    )

    # ══════════════════════════════════════════════════════════════════════════
    # LÍNEA 2: LSP — servidores activos o placeholder
    #   · ✐ py js ts go c cpp sh json yaml ... ·
    # ══════════════════════════════════════════════════════════════════════════
    if lsp_line2:
        line2 = lsp_line2 + ' ·'
    else:
        # Sin LSP configurado — línea vacía con indicador mínimo
        line2 = '· <text> — </text> ·'

    # ══════════════════════════════════════════════════════════════════════════
    # LÍNEA 3: keybindings
    #   · F1 keys · F2 status · F3 compact · ^O expand · ^Y copy · ^L clear · ^T tip ·
    # ══════════════════════════════════════════════════════════════════════════
    _img_hint = (
        ' · <key>^P</key><text> img</text>'
        if getattr(agent_loop, "_model_supports_images", lambda: False)() else ""
    )
    line3 = (
        '· <key>F1</key><text> keys</text>'
        ' · <key>F2</key><text> status</text>'
        ' · <key>F3</key><text> compact</text>'
        ' · <key>F4</key><text> ctx</text>'
        ' · <key>^O</key><text> expand</text>'
        ' · <key>^Y</key><text> copy</text>'
        ' · <key>^L</key><text> clear</text>'
        ' · <key>^T</key><text> tip</text>'
        + _img_hint
        + ' ·'
    )

    return HTML(line1 + '\n' + line2 + '\n' + line3)


def run_repl(agent_loop, config) -> None:
    """Arranca la TUI full-screen de OOCode."""
    from ui.app import OOCodeApp
    OOCodeApp(agent_loop, config).run()
