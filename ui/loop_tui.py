"""TUI display mixin para AgentLoop: todo el rendering Rich/terminal.

Extraído de agent/loop.py para mantener la separación TUI/WebUI.
Importado por AgentLoop como primer mixin base:
    class AgentLoop(TUIDisplayMixin, WebUIMixin): ...
"""
import sys
import os
import time
import threading
from typing import Any, Callable, Optional

from agent.loop_helpers import (
    _HEADER_ANIM_CODES, _ANSI_BOLD, _ANSI_RESET,
    _SPINNER_FRAMES, _TASK_ICON_COLORS, _TOOL_LIVE_VERBS,
    _make_compact_summary, _ctx_bar, _fmt_tokens, _pbar_thin_ratio,
    _sfmt, _COMPACT_LOCK,
    _ANIM_JOIN_TIMEOUT, _COMPACT_SPINNER_POLL,
    _COMPACT_TEXT, _COMPACT_NEAR_TEXT,
)
import tools.progress as _tool_progress
from tools.hooks import _is_modify_tool


class TUIDisplayMixin:
    """Métodos de presentación TUI (Rich / ANSI / status_cb / live_block).

    Todos los atributos que usan (capture_output, is_subagent, _status_cb,
    _turn_block, _plan_tasks, context, session, config, rt, …) los define
    AgentLoop.__init__; este mixin los accede vía self.
    """

    # ── Contrato con AgentLoop (annotations-only, sin valor → mypy los verifica,
    # cero coste en runtime; un rename en AgentLoop.__init__ sin actualizar aquí
    # produce error de mypy, no AttributeError en producción) ─────────────────
    # -- attrs de __init__ con prefijo _
    _status_cb:             Optional[Callable]
    _clear_output_cb:       Optional[Callable]
    _flush_live_block_cb:   Optional[Callable]
    _update_live_tools_cb:  Optional[Callable]
    _turn_block:            list[tuple[str, dict, str, bool]]
    _turn_block_has_header: bool
    _live_tool_count:       int
    _pending_usage_line:    str
    _compacting_ctx:        bool
    _compact_running:       threading.Event
    _plan_tasks:            list[dict]
    _session_reads:         list[tuple[str, object, bool]]
    _session_mems:          list[str]
    _tool_current_file:     str
    _last_elapsed:          float
    # -- attrs públicos de __init__
    capture_output:         bool
    is_subagent:            bool
    config:                 Any
    context:                Any
    rt:                     Any
    session:                Any

    def _show_inline_compact_result(self, name: str, args: dict,
                                    result: str, allowed: bool) -> None:
        """Muestra resultado compacto inline (una línea ⎿ ) para tools no-write en TUI mode."""
        from rich.markup import escape as _esc

        if not allowed:
            self._print("  [dim red]⎿ Denegado[/dim red]")
            return

        r = result.strip() if result else ""
        if not r or r in ("Sin resultados.", "No results."):
            self._print("  [dim]⎿ Sin resultados[/dim]")
            return
        if r.startswith("⛔ AGENTE BLOQUEÓ"):
            first = r.splitlines()[0]
            self._print(f"  [bold yellow]⎿ {_esc(first)}[/bold yellow]")
            return
        if r.startswith("Error:") or r.startswith("Error ") or r.startswith("Timeout:"):
            self._print(f"  [dim red]⎿ {_esc(r.splitlines()[0])}[/dim red]")
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
                expand = " (ctrl+o)" if n_lines > 5 else ""
                self._print(
                    f"  [dim]⎿ {n_matches} resultado{'s' if n_matches != 1 else ''}"
                    f"  en {n_files} fichero{'s' if n_files != 1 else ''}{expand}[/dim]"
                )
            else:
                preview = lines[0]
                if n_lines > 2:
                    self._print(f"  [dim]⎿ {_esc(preview)}  +{n_lines-1}[/dim]")
                else:
                    self._print(f"  [dim]⎿ {_esc(preview)}[/dim]")
        elif name in self._READ_DISPLAY_TOOLS:
            # Fichero leído: "⎿ nombre  [N líneas]"
            fname = (args.get("path") or args.get("file_path") or
                     args.get("directory") or "")
            fname_short = fname.rsplit("/", 1)[-1] if fname else ""
            if fname_short:
                self._print(f"  [dim]⎿ {_esc(fname_short)}  [{n_lines} líneas][/dim]")
            else:
                preview = lines[0]
                self._print(f"  [dim]⎿ {_esc(preview)}[/dim]")
        else:
            # Caso general: primera línea + count
            preview = lines[0]
            if n_lines > 2:
                self._print(
                    f"  [dim]⎿ {_esc(preview)}  "
                    f"[dim cyan]+{n_lines-1}[/dim cyan][/dim]"
                )
            else:
                self._print(f"  [dim]⎿ {_esc(preview)}[/dim]")

    def _render_tool_diff_print(self, name: str, args: dict, result: str) -> None:
        """Renderiza diff de write/edit/replace via self._print (TUI-safe)."""
        if not result or "Error" in result or "fallida" in result or "rollback" in result:
            return
        try:
            import tools.diff_renderer as _dr
            _dr.set_dprint_fn(self._print)
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

    def _flush_task_intermediate_summary(self) -> None:
        """Emite ⎿ compacto de tools acumuladas entre task_done() calls.

        Llamado desde _execute_task_done() para emitir el resumen de tools de la
        tarea actual ANTES de cerrar el live block y mostrar ◈ Plan [N/M].
        El texto va al cuerpo del live block activo (o al buffer estático si no hay
        live block), de modo que el usuario ve siempre qué tools corrieron por tarea.
        Resetea _turn_block, _live_tool_count y sincroniza _update_live_tools_cb para
        que _flush_live_block_cb("") no añada un "Used N tools" fantasma.
        """
        if self.capture_output or self._status_cb is None:
            self._turn_block = []
            self._turn_block_has_header = False
            self._live_tool_count = 0
            if getattr(self, "_update_live_tools_cb", None):
                self._update_live_tools_cb(0)
            return
        block = self._turn_block
        if getattr(self, "_turn_block_has_header", False):
            block = [t for t in block if not _is_modify_tool(t[0])]
        if block:
            summary = _make_compact_summary(block)
            if summary and not getattr(self, "_webui_queue", None):
                self._print(f"  [dim]⎿ {summary}[/dim]")
        # Resetear buffers y sincronizar el contador de app.py
        # para que el _flush_live_block_cb("") no emita "Used N tools" fantasma.
        self._turn_block = []
        self._turn_block_has_header = False
        self._live_tool_count = 0
        if getattr(self, "_update_live_tools_cb", None):
            self._update_live_tools_cb(0)

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
                _sf    = ("  ⎿ " + _cf.rsplit("/", 1)[-1]) if _cf else ""
                line   = f"  {col}{bold}◐{reset} {bold}{display}{reset}{ctx_plain}{_sf}"
                pad    = max(0, _width - len(line))
                sys.stdout.write(f"\r{line}{' ' * pad}")
                sys.stdout.flush()
                fi += 1

        _anim_t = threading.Thread(
            target=_anim_thread, daemon=True, name=f"oocode-hdr-{name[:8]}"
        )
        _anim_t.start()

        try:
            result = self._execute_tool(name, args)
        finally:
            # Garantizado incluso si _execute_tool lanza: detiene el hilo y limpia
            # el terminal antes de que la excepción se propague hacia arriba.
            _done_ev.set()
            _anim_t.join(timeout=_ANIM_JOIN_TIMEOUT)
            if _is_prog_repl:
                _tool_progress.set_progress_callback(None)
            self._tool_current_file = ""
            sys.stdout.write(f"\r{' ' * _width}\r")
            sys.stdout.flush()

        if is_mem_tool:
            self._print(f"  [bold white]◐[/bold white] [white]{_esc(display)}[/white][dim]{ctx}[/dim]")
        else:
            self._print(f"  [white]◐[/white] [bold white]{_esc(display)}[/bold white][dim]{ctx}[/dim]")

        return result

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
            compact_hint = f"  [bold yellow]{_COMPACT_TEXT}[/bold yellow]"
        elif ctx_pct >= thresh_pct - 10:
            compact_hint = f"  [bold #ff7700]{_COMPACT_NEAR_TEXT}[/bold #ff7700]"
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
            "  [bold]✻[/bold] "
            "[dim]Conversación compactada[/dim]"
            "  [dim](ctrl+o para ver historial)[/dim]"
        )
        if has_summary:
            _con.print("  [dim]↻ resumen LLM preservado en contexto[/dim]")

        # ── Paso 4: referencias de ficheros y memorias ────────────────────────
        ws = str(self.config.workspace or "")

        all_compact_lines: list[str] = []

        if self._session_reads:
            seen: dict[str, tuple] = {}
            for item in self._session_reads:
                # Guard contra entradas corruptas (e.g. string en vez de tuple)
                if not (isinstance(item, (tuple, list)) and len(item) == 3):
                    continue
                path, n_lines, is_edit = item
                if not path or len(str(path)) < 2:
                    continue
                # Dividir paths separadas por coma (cuando read_files recibe string)
                for single_path in str(path).split(","):
                    single_path = single_path.strip()
                    if single_path:
                        seen[single_path] = (n_lines, is_edit)

            for path, (n_lines, is_edit) in list(seen.items())[-15:]:
                rel = path[len(ws):].lstrip("/") if (ws and path.startswith(ws)) else path
                if is_edit:
                    all_compact_lines.append(f"Updated {rel}")
                elif n_lines is not None:
                    all_compact_lines.append(f"Read file {rel} ({n_lines} líneas)")
                else:
                    all_compact_lines.append(f"Referenced file {rel}")

        if self._session_mems:
            seen_mems = list(dict.fromkeys(self._session_mems))  # deduplica preservando orden
            for mname in seen_mems[-5:]:
                all_compact_lines.append(f"Memory saved: {mname}")

        for _i, _line in enumerate(all_compact_lines):
            _sym = "⎿" if _i == len(all_compact_lines) - 1 else "│"
            _con.print(f"  [dim]{_sym} {_line}[/dim]")

        if self._session_reads or self._session_mems:
            _con.print()

        self._session_reads = []
        self._session_mems  = []

        # Plan: no reprint tras compactación — el spinner multitarea ya indica la tarea activa

    def _do_compact_locked(self, with_summary: bool = True) -> int:
        """Lógica de compactación — siempre ejecutada bajo _COMPACT_LOCK."""
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
                        while not _done_ev.wait(timeout=_COMPACT_SPINNER_POLL):
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
        from ui.console import console as _con

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
            console=_con,
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

    def _print_plan_panel_update(self, compact: bool = False) -> None:
        """Imprime el estado actual del plan al terminal (actualización dinámica).

        Se llama tras task_done() y tras compactación para que el scroll buffer
        refleje el progreso real. Solo activo en modo TUI (no capture_output).
        compact=True → omite tareas done > 1 atrás (para compactación).
        """
        if self.capture_output or not self._plan_tasks:
            return
        from rich.markup import escape as _mesc
        from ui.console import console as _con

        total    = len(self._plan_tasks)
        done_n   = sum(1 for t in self._plan_tasks if t["status"] == "done")
        pending_n = sum(1 for t in self._plan_tasks if t["status"] == "pending")
        active_idx = next(
            (i for i, t in enumerate(self._plan_tasks) if t["status"] == "active"), -1
        )
        _ic = _TASK_ICON_COLORS[int(time.time()) % len(_TASK_ICON_COLORS)]

        if compact:
            # Tras compactación: header completo + todas las tareas (máx 12)
            _con.print(
                f"\n  [{_ic}]◈[/{_ic}]  [bold]Plan de ejecución[/bold]  "
                f"[dim]({done_n}/{total} completadas)[/dim]"
            )
            MAX_SHOW = 12
        else:
            # Tras task_done(): header con progreso + ventana deslizante
            _con.print(
                f"\n  [{_ic}]◈[/{_ic}]  [bold]Plan de ejecución  "
                f"[{done_n + (1 if active_idx >= 0 else 0)}/{total}][/bold]  "
                f"[dim]· {done_n} completadas · {pending_n} pendientes[/dim]"
            )
            MAX_SHOW = 7

        # Ventana deslizante centrada en la tarea activa
        if active_idx >= 0:
            win_start = max(0, active_idx - 1)
        else:
            win_start = max(0, done_n - 1)
        win_end = min(total, win_start + MAX_SHOW)
        if win_end - win_start < MAX_SHOW:
            win_start = max(0, win_end - MAX_SHOW)

        if win_start > 0:
            _con.print(f"  [dim]    … {win_start} completadas anteriores[/dim]")

        for i in range(win_start, win_end):
            t = self._plan_tasks[i]
            status = t["status"]
            _task_text = t["text"]
            if status == "active":
                _con.print(f"  [bold cyan]  {i + 1}. {_mesc(_task_text)}[/bold cyan]")
            else:
                _con.print(f"  [dim]  {i + 1}. {_mesc(_task_text)}[/dim]")

        remaining = total - win_end
        if remaining > 0:
            _con.print(f"  [dim]    … +{remaining} pendientes[/dim]")

