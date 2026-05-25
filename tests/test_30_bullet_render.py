"""Tests para el renderizado del ● (bullet) con texto del modelo.

Reproducibugs el problema reportado: textos cuya primera línea supera 300 chars
se mostraban como '●  …' con el texto en la línea siguiente en lugar de inline.

Cubre:
- Texto corto: primer línea inline con ●
- Texto largo (>300 chars primer línea): también inline, no "…"
- Texto markdown (#/`/-/*): no inline → ● solo + Markdown debajo
- Texto vacío o solo \n: no falla
- TUI path (start_live_block_cb): _bullet_text = first text, no "…"
- TUI path texto >200 chars: header truncado a 200 + "…" pero body completo
- REPL path: siempre inline si no es markdown
- _plain_first False solo cuando empieza con markdown o está vacío
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock, patch, call


def _make_loop():
    from agent.loop import AgentLoop
    from tools.registry import ToolRegistry
    from tools.permissions import PermissionManager
    from config import OOConfig
    cfg = OOConfig()
    loop = AgentLoop.__new__(AgentLoop)
    loop.config = cfg
    loop.registry = ToolRegistry()
    loop.permissions = PermissionManager(cfg.permissions)
    loop.memory = MagicMock()
    loop.workspace_manager = MagicMock()
    loop.session = MagicMock()
    loop.rt = MagicMock()
    loop.rt.verbose = False
    loop.rt.accent_color = "cyan"
    loop.is_subagent = False
    loop.capture_output = False
    loop._status_cb = None
    loop._auto_continue_count = 0
    loop._plan_tasks = []
    loop._turn_written_scripts = set()
    loop._turn_read_cache = {}
    loop._turn_write_seen = {}
    loop._turn_block_has_header = False
    loop._turn_block = []
    loop._tool_current_file = ""
    loop._bash_block_counts = {}
    loop._kill_requested = False
    loop._pending_tasks = []
    loop._last_tool_calls = []
    loop._start_live_block_cb = None
    loop._flush_live_block_cb = None
    loop._live_tool_count = 0
    return loop


def _simulate_text_render(loop, text: str, has_tool_calls: bool = False) -> dict:
    """
    Simula el bloque de renderizado de texto del modelo en run() (líneas 3736-3768).
    Retorna un dict con lo que se pasó a cada función de display.
    """
    from rich.markup import escape as _mesc
    from rich.padding import Padding
    from rich.markdown import Markdown
    from agent.runtime import COLOR_PRESETS

    _ac = COLOR_PRESETS.get(loop.rt.accent_color, COLOR_PRESETS["cyan"])[1]
    text_clean = text.lstrip()   # igual que en loop.py: strip ALL leading whitespace
    lines   = text_clean.split('\n', 1)
    first   = lines[0].rstrip()
    rest    = lines[1] if len(lines) > 1 else ""
    _MD = ('#', '`', '-', '*', '+', '|', '>', '!')
    _plain_first = bool(first and not first.lstrip().startswith(_MD))

    printed_lines = []
    live_block_header = None
    live_block_body_parts = []

    fake_console_print = lambda *args, **kw: printed_lines.append(args[0] if args else "")

    if loop._start_live_block_cb and has_tool_calls:
        if _plain_first:
            _hdr = first if len(first) <= 200 else first[:197] + "…"
            _bullet_text = _mesc(_hdr)
            _body_extra = first[197:] if len(first) > 200 else ""
        else:
            _bullet_text = "…"
            _body_extra = ""
        live_block_header = _bullet_text
        _body = (_body_extra + "\n" + rest).lstrip('\n') if _body_extra else rest
        if _plain_first and _body.strip():
            live_block_body_parts.append(_body.lstrip('\n'))
        elif not _plain_first:
            live_block_body_parts.append(text_clean)
    else:
        if _plain_first:
            printed_lines.append(f"  ●  {_mesc(first)}")
            if rest.strip():
                live_block_body_parts.append(rest.lstrip('\n'))
        else:
            printed_lines.append(f"  ●")
            live_block_body_parts.append(text_clean)

    return {
        "plain_first": _plain_first,
        "first": first,
        "rest": rest,
        "live_block_header": live_block_header,
        "live_block_body": live_block_body_parts,
        "printed_lines": printed_lines,
    }


# ── _plain_first lógica ───────────────────────────────────────────────────────

class TestPlainFirstLogic:
    def test_short_plain_text_is_plain(self):
        loop = _make_loop()
        r = _simulate_text_render(loop, "Texto corto de respuesta.")
        assert r["plain_first"] is True

    def test_long_plain_text_is_still_plain(self):
        """El límite de 300 chars fue eliminado — texto largo sigue siendo plain_first."""
        loop = _make_loop()
        long_text = "Los errores de utils.py y helpers.py están corregidos. Ahora quedan errores en main.py: 1) variable MAX_ITEMS no definida, 2) funciones parse_args() y validate_input() no definidas, 3) módulos json_parser, str_utils, file_reader no declarados. Necesito revisar config.py para ver qué incluye y corregir main.py."
        assert len(long_text) > 300
        r = _simulate_text_render(loop, long_text)
        assert r["plain_first"] is True

    def test_text_exactly_300_chars_is_plain(self):
        loop = _make_loop()
        text = "A" * 300
        r = _simulate_text_render(loop, text)
        assert r["plain_first"] is True

    def test_text_500_chars_is_plain(self):
        loop = _make_loop()
        text = "X" * 500
        r = _simulate_text_render(loop, text)
        assert r["plain_first"] is True

    def test_markdown_header_is_not_plain(self):
        loop = _make_loop()
        r = _simulate_text_render(loop, "# Encabezado markdown")
        assert r["plain_first"] is False

    def test_backtick_start_is_not_plain(self):
        loop = _make_loop()
        r = _simulate_text_render(loop, "```python\ncode\n```")
        assert r["plain_first"] is False

    def test_bullet_list_is_not_plain(self):
        loop = _make_loop()
        r = _simulate_text_render(loop, "- Item 1\n- Item 2")
        assert r["plain_first"] is False

    def test_asterisk_start_is_not_plain(self):
        loop = _make_loop()
        r = _simulate_text_render(loop, "**Bold text**")
        assert r["plain_first"] is False

    def test_empty_text_is_not_plain(self):
        loop = _make_loop()
        r = _simulate_text_render(loop, "")
        assert r["plain_first"] is False

    def test_only_newlines_is_not_plain(self):
        loop = _make_loop()
        r = _simulate_text_render(loop, "\n\n\n")
        assert r["plain_first"] is False

    def test_leading_newline_stripped(self):
        """Newlines iniciales se eliminan antes de evaluar _plain_first."""
        loop = _make_loop()
        r = _simulate_text_render(loop, "\n\nTexto sin markdown")
        assert r["plain_first"] is True
        assert r["first"] == "Texto sin markdown"

    def test_space_then_newline_is_not_empty(self):
        """Bug fix: ' \\nPlan: ...' producía _plain_first=False porque first era ''.
        Con text.lstrip() el espacio inicial también se elimina."""
        loop = _make_loop()
        r = _simulate_text_render(loop, " \nPlan: Implementar la solución propuesta")
        assert r["plain_first"] is True
        assert r["first"] == "Plan: Implementar la solución propuesta"

    def test_tab_then_newline_stripped(self):
        """Tab + newline antes del texto real: text.lstrip() los elimina."""
        loop = _make_loop()
        r = _simulate_text_render(loop, "\t\nIniciando análisis del código")
        assert r["plain_first"] is True
        assert r["first"] == "Iniciando análisis del código"

    def test_spaces_only_first_line_stripped_to_next(self):
        """Primera línea con solo espacios → text.lstrip() avanza al primer contenido."""
        loop = _make_loop()
        r = _simulate_text_render(loop, "   \nVoy a corregir el bug")
        assert r["plain_first"] is True
        assert r["first"] == "Voy a corregir el bug"


# ── REPL path (sin _start_live_block_cb) ─────────────────────────────────────

class TestReplBulletRender:
    def test_short_text_inline_with_bullet(self):
        loop = _make_loop()
        r = _simulate_text_render(loop, "Respuesta corta.")
        assert any("Respuesta corta." in line for line in r["printed_lines"])
        assert not any(line == "  ●" for line in r["printed_lines"])

    def test_long_text_inline_not_ellipsis(self):
        """El texto largo debe aparecer inline con ●, no "●" solo con ellipsis."""
        loop = _make_loop()
        long_text = "Los errores de utils.py y helpers.py están corregidos. Ahora quedan errores en main.py: 1) variable MAX_ITEMS no definida, 2) funciones parse_args() y validate_input() no definidas, 3) módulos json_parser, str_utils, file_reader no declarados. Necesito revisar config.py para ver qué incluye y corregir main.py."
        r = _simulate_text_render(loop, long_text)
        # Debe aparecer inline (no como "  ●" solo)
        assert not any(line.strip() == "●" for line in r["printed_lines"])
        assert any(long_text[:50] in line for line in r["printed_lines"])

    def test_markdown_text_bullet_alone(self):
        loop = _make_loop()
        r = _simulate_text_render(loop, "# Título\n\nContenido")
        assert any(line.strip() == "●" for line in r["printed_lines"])

    def test_multiline_first_in_bullet_rest_in_body(self):
        loop = _make_loop()
        r = _simulate_text_render(loop, "Primera línea.\n\nSegunda línea.")
        assert any("Primera línea." in line for line in r["printed_lines"])
        assert r["rest"].strip() == "Segunda línea."


# ── TUI path (con _start_live_block_cb y tool_calls) ─────────────────────────

class TestTuiBulletRender:
    def _make_tui_loop(self):
        loop = _make_loop()
        loop._start_live_block_cb = MagicMock()
        return loop

    def test_short_text_goes_to_live_header_not_ellipsis(self):
        loop = self._make_tui_loop()
        r = _simulate_text_render(loop, "Texto corto", has_tool_calls=True)
        assert r["live_block_header"] == "Texto corto"
        assert r["live_block_header"] != "…"

    def test_long_text_not_ellipsis_in_header(self):
        """Texto >300 chars ya no produce '…' en el live block header."""
        loop = self._make_tui_loop()
        long_text = "Los errores de utils.py y helpers.py están corregidos. Ahora quedan errores en main.py: 1) variable MAX_ITEMS no definida, 2) funciones parse_args() y validate_input() no definidas, 3) módulos json_parser, str_utils, file_reader no declarados. Necesito revisar config.py para ver qué incluye y corregir main.py."
        r = _simulate_text_render(loop, long_text, has_tool_calls=True)
        assert r["live_block_header"] != "…"
        assert r["live_block_header"] is not None

    def test_header_truncated_at_200_for_very_long_text(self):
        """Textos >200 chars: header muestra primeros 197 + '…' para evitar overflow."""
        loop = self._make_tui_loop()
        very_long = "X" * 250
        r = _simulate_text_render(loop, very_long, has_tool_calls=True)
        assert r["live_block_header"].endswith("…")
        # header no debe exceder 200 chars visibles (197 + "…")
        import re
        clean = re.sub(r'\[.*?\]', '', r["live_block_header"])  # strip Rich markup
        assert len(clean) <= 200

    def test_header_not_truncated_when_200_or_less(self):
        """Textos ≤200 chars: header muestra texto completo sin truncar."""
        loop = self._make_tui_loop()
        text_200 = "A" * 200
        r = _simulate_text_render(loop, text_200, has_tool_calls=True)
        assert not r["live_block_header"].endswith("…")

    def test_text_truncated_beyond_200_goes_to_body(self):
        """La parte >200 chars del primer párrafo va al cuerpo del live block."""
        loop = self._make_tui_loop()
        very_long = "A" * 197 + "EXTRA_CONTENT_HERE"
        r = _simulate_text_render(loop, very_long, has_tool_calls=True)
        assert r["live_block_header"].endswith("…")
        # La parte extra debe estar en el body
        assert any("EXTRA_CONTENT_HERE" in part for part in r["live_block_body"])

    def test_markdown_text_still_shows_ellipsis_in_header(self):
        """Texto markdown en primer párrafo → header sigue siendo '…'."""
        loop = self._make_tui_loop()
        r = _simulate_text_render(loop, "# Título\n\nContenido", has_tool_calls=True)
        assert r["live_block_header"] == "…"

    def test_multiline_rest_goes_to_body(self):
        """El texto tras la primera línea va al cuerpo del live block."""
        loop = self._make_tui_loop()
        text = "Primera línea breve.\n\nResto del mensaje más largo."
        r = _simulate_text_render(loop, text, has_tool_calls=True)
        assert r["live_block_header"] == "Primera línea breve."
        assert any("Resto del mensaje" in part for part in r["live_block_body"])

    def test_no_tool_calls_uses_repl_path(self):
        """Sin tool_calls, incluso con _start_live_block_cb usa el path de REPL."""
        loop = self._make_tui_loop()
        r = _simulate_text_render(loop, "Texto sin tools", has_tool_calls=False)
        assert r["live_block_header"] is None  # no fue al live block
        assert any("Texto sin tools" in line for line in r["printed_lines"])


# ── Regresión: el caso exacto del bug reportado ───────────────────────────────

class TestBulletRegressionCases:
    def test_exact_bug_text_not_ellipsis(self):
        """
        Reproduce el bug original: el texto de 316 chars producía '●  …'.
        Ahora debe mostrarse inline con el ●.
        """
        bug_text = (
            "Los errores de utils.py y helpers.py están corregidos. "
            "Ahora quedan errores en main.py: "
            "1) variable MAX_ITEMS no definida, "
            "2) funciones parse_args() y validate_input() no definidas, "
            "3) módulos json_parser, str_utils, file_reader no declarados. "
            "Necesito revisar config.py para ver qué incluye y corregir main.py."
        )
        assert len(bug_text) > 300

        # REPL path
        loop_repl = _make_loop()
        r_repl = _simulate_text_render(loop_repl, bug_text)
        assert r_repl["plain_first"] is True
        # El texto debe estar inline con ●, no abajo
        assert any(bug_text[:40] in line for line in r_repl["printed_lines"]), (
            f"El texto no aparece inline con ●. printed_lines={r_repl['printed_lines']}"
        )

        # TUI path
        loop_tui = _make_loop()
        loop_tui._start_live_block_cb = MagicMock()
        r_tui = _simulate_text_render(loop_tui, bug_text, has_tool_calls=True)
        assert r_tui["live_block_header"] != "…", (
            "El live block header muestra '…' en lugar del texto del modelo"
        )
        assert r_tui["live_block_header"] is not None

    def test_text_316_chars_plain_first_true(self):
        """Exactamente el tamaño del texto del bug: 316 chars."""
        text = "A" * 316
        loop = _make_loop()
        r = _simulate_text_render(loop, text)
        assert r["plain_first"] is True

    def test_text_299_chars_still_plain(self):
        """299 chars (justo por debajo del límite antiguo) sigue siendo plain."""
        text = "B" * 299
        loop = _make_loop()
        r = _simulate_text_render(loop, text)
        assert r["plain_first"] is True
