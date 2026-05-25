"""Tests para las mejoras TUI de la sesión 2026-05-19.

Cubre:
- _flush_turn_block resetea _turn_block (sin acumulación entre batches)
- _make_compact_summary muestra nombre de fichero en edición única
- _make_compact_summary cuenta líneas +/- para ediciones
- _make_compact_summary normaliza nombres de MCP tools (mcp_*_edit_file → edit_file)
- render_edit_diff maneja arg "file_path" además de "path"
- _precheck_tool_call bloquea python_exec con escrituras múltiples de fuentes
- _show_tool_block en TUI mode muestra header para write tools
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# _make_compact_summary
# ─────────────────────────────────────────────────────────────────────────────

from agent.loop import _make_compact_summary


def _block(name, args=None, result="ok", allowed=True):
    return (name, args or {}, result, allowed)


class TestMakeCompactSummary:

    def test_single_read(self):
        blocks = [_block("read_file", {"path": "foo.py"})]
        s = _make_compact_summary(blocks)
        assert "Read 1 file" in s
        assert "(ctrl+o to expand)" in s

    def test_multiple_reads(self):
        blocks = [_block("read_file"), _block("read_file"), _block("read_file")]
        s = _make_compact_summary(blocks)
        assert "Read 3 files" in s

    def test_single_edit_shows_filename(self):
        blocks = [_block("edit_file", {"path": "agent/loop.py", "old_string": "foo", "new_string": "bar"})]
        s = _make_compact_summary(blocks)
        # Debe mostrar el nombre del fichero, no "1 file"
        assert "Updated loop.py" in s

    def test_single_edit_counts_lines(self):
        old = "line1\nline2\nline3"
        new = "line1\nNEW_LINE\nNEW_LINE2\nline3"
        blocks = [_block("edit_file", {"path": "test.py", "old_string": old, "new_string": new})]
        s = _make_compact_summary(blocks)
        # +2 líneas añadidas, -1 eliminada
        assert "+2 -1" in s

    def test_multiple_edits_shows_count(self):
        blocks = [
            _block("edit_file", {"path": "a.py", "old_string": "x", "new_string": "y"}),
            _block("edit_file", {"path": "b.py", "old_string": "a", "new_string": "b"}),
        ]
        s = _make_compact_summary(blocks)
        assert "Updated 2 files" in s

    def test_write_verb_updated(self):
        # edit_file ahora usa "Updated" en lugar de "Edited"
        blocks = [_block("edit_file", {"path": "x.py"})]
        s = _make_compact_summary(blocks)
        assert "Updated" in s

    def test_bash_counted(self):
        blocks = [_block("bash"), _block("bash")]
        s = _make_compact_summary(blocks)
        assert "Ran 2 commands" in s

    def test_denied_counted(self):
        blocks = [_block("bash", allowed=False)]
        s = _make_compact_summary(blocks)
        assert "Denied" in s

    def test_mixed_batch(self):
        blocks = [
            _block("read_file", {"path": "a.py"}),
            _block("grep_code"),
            _block("edit_file", {"path": "b.py", "old_string": "x", "new_string": "y"}),
            _block("bash"),
        ]
        s = _make_compact_summary(blocks)
        assert "Read 1 file" in s
        assert "Searched 1 pattern" in s
        assert "Updated b.py" in s
        assert "Ran 1 command" in s

    def test_mcp_edit_normalized(self):
        # MCP tools con nombre mcp_oocode_assistant_edit_file
        blocks = [_block("mcp_oocode_assistant_edit_file", {"path": "x.py"})]
        s = _make_compact_summary(blocks)
        # Debe reconocer como edit y usar "Updated"
        assert "Updated" in s

    def test_mcp_regex_replace_normalized(self):
        blocks = [_block("mcp_oocode_assistant_regex_replace")]
        s = _make_compact_summary(blocks)
        assert "Replaced" in s

    def test_empty_blocks(self):
        s = _make_compact_summary([])
        assert "(ctrl+o to expand)" in s

    def test_write_file_verb(self):
        blocks = [_block("write_file", {"path": "out.py"})]
        s = _make_compact_summary(blocks)
        assert "Wrote 1 file" in s

    def test_patch_apply_verb(self):
        blocks = [_block("patch_apply")]
        s = _make_compact_summary(blocks)
        assert "Applied 1 patch" in s

    def test_no_ctrl_o_if_empty(self):
        s = _make_compact_summary([])
        # Devuelve el expand hint aunque no haya nada
        assert "(ctrl+o to expand)" in s


# ─────────────────────────────────────────────────────────────────────────────
# render_edit_diff — manejo de file_path vs path
# ─────────────────────────────────────────────────────────────────────────────

from tools.diff_renderer import render_edit_diff
import io, contextlib


class TestRenderEditDiff:

    def test_handles_path_arg(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("def foo():\n    return 1\n")
        args = {"path": str(f), "old_string": "return 1", "new_string": "return 2"}
        # No debe lanzar excepción
        render_edit_diff(args, "ok")

    def test_handles_file_path_arg(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x = 1\n")
        args = {"file_path": str(f), "old_string": "x = 1", "new_string": "x = 2"}
        # No debe lanzar excepción (file_path en lugar de path)
        render_edit_diff(args, "ok")

    def test_skips_on_error_result(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x = 1\n")
        args = {"path": str(f), "old_string": "x", "new_string": "y"}
        # Con "Error" en el resultado, no hace nada
        render_edit_diff(args, "Error: cadena no encontrada")

    def test_skips_if_no_path(self):
        args = {"old_string": "a", "new_string": "b"}
        render_edit_diff(args, "ok")  # no debe lanzar

    def test_skips_if_old_eq_new(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x = 1\n")
        args = {"path": str(f), "old_string": "x", "new_string": "x"}
        render_edit_diff(args, "ok")  # no debe lanzar


# ─────────────────────────────────────────────────────────────────────────────
# _precheck_tool_call — python_exec con escrituras múltiples
# ─────────────────────────────────────────────────────────────────────────────

from unittest.mock import MagicMock, patch
import importlib


def _make_loop():
    """Crea un AgentLoop minimal para probar _precheck_tool_call."""
    from agent.loop import AgentLoop
    from tools.registry import ToolRegistry
    from tools.permissions import PermissionManager
    from agent.memory import MemorySystem
    from config import OOConfig

    cfg = OOConfig()
    reg = ToolRegistry()
    perm = PermissionManager(cfg.permissions)
    mem = MagicMock()
    ws = MagicMock()
    session = MagicMock()
    loop = AgentLoop.__new__(AgentLoop)
    loop.config = cfg
    loop.registry = reg
    loop.permissions = perm
    loop.memory = mem
    loop.workspace_manager = ws
    loop.session = session
    loop.rt = MagicMock()
    loop.rt.verbose = False
    loop.is_subagent = False
    loop.capture_output = False
    loop._status_cb = None
    loop._turn_written_scripts = set()
    loop._bash_block_counts = {}
    loop._kill_requested = False
    loop._turn_read_cache = {}
    loop._turn_write_seen = {}
    loop._turn_block_has_header = False
    loop._turn_block = []
    loop._tool_current_file = ""
    loop._flush_live_block_cb = None
    loop._start_live_block_cb = None
    loop._update_live_tools_cb = None
    loop._live_tool_count = 0
    return loop


class TestPrecheckPythonExec:

    def test_allows_single_file_write(self):
        loop = _make_loop()
        code = "with open('/tmp/out.py', 'w') as f:\n    f.write('x')\n"
        result = loop._precheck_tool_call("python_exec", {"code": code})
        assert result is None  # un solo fichero → permitido

    def test_blocks_two_source_writes(self):
        loop = _make_loop()
        code = (
            "open('src/a.py', 'w').write('x')\n"
            "open('src/b.py', 'w').write('y')\n"
        )
        result = loop._precheck_tool_call("python_exec", {"code": code})
        assert result is not None
        assert "⛔" in result
        assert "edit_file" in result
        assert "bulk_replace" in result

    def test_blocks_c_source_writes(self):
        loop = _make_loop()
        code = (
            "open('src/a.c', 'w').write(content)\n"
            "open('src/b.h', 'w').write(content)\n"
        )
        result = loop._precheck_tool_call("python_exec", {"code": code})
        assert result is not None
        assert "⛔" in result

    def test_allows_non_source_writes(self):
        loop = _make_loop()
        # JSON y TXT no son fuentes → permitido
        code = (
            "open('data.json', 'w').write(j)\n"
            "open('out.txt', 'w').write(t)\n"
        )
        result = loop._precheck_tool_call("python_exec", {"code": code})
        assert result is None

    def test_allows_empty_code(self):
        loop = _make_loop()
        result = loop._precheck_tool_call("python_exec", {"code": ""})
        assert result is None

    def test_bash_not_affected(self):
        loop = _make_loop()
        # bash no pasa por el bloque python_exec (make -j4 no es bloqueado)
        result = loop._precheck_tool_call("bash", {"command": "make -j4"})
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# _flush_turn_block — reset tras flush
# ─────────────────────────────────────────────────────────────────────────────

class TestFlushTurnBlockReset:

    def test_resets_after_flush(self):
        """_flush_turn_block debe vaciar _turn_block tras imprimir el resumen."""
        loop = _make_loop()
        loop._status_cb = lambda x: None  # simula TUI mode
        loop._turn_block = [
            ("read_file", {}, "ok", True),
            ("bash", {}, "ok", True),
        ]
        # Parchar _print para no imprimir nada real
        loop._print = lambda *a, **k: None
        loop._flush_turn_block()
        assert loop._turn_block == []

    def test_resets_when_empty(self):
        loop = _make_loop()
        loop._status_cb = lambda x: None
        loop._turn_block = []
        loop._print = lambda *a, **k: None
        loop._flush_turn_block()
        assert loop._turn_block == []

    def test_resets_when_no_status_cb(self):
        loop = _make_loop()
        loop._status_cb = None
        loop._turn_block = [("bash", {}, "ok", True)]
        loop._print = lambda *a, **k: None
        loop._flush_turn_block()
        # Sin status_cb → también resetea (return temprano)
        assert loop._turn_block == []

    def test_second_flush_shows_new_tools_only(self):
        """Dos flushes consecutivos: cada uno muestra solo las tools del batch actual."""
        summaries = []
        loop = _make_loop()
        loop._status_cb = lambda x: None
        loop._print = lambda msg, *a, **k: summaries.append(msg)

        # Batch 1: solo read
        loop._turn_block = [("read_file", {"path": "a.py"}, "ok", True)]
        loop._flush_turn_block()
        assert loop._turn_block == []

        # Batch 2: solo bash (no debe incluir el read del batch 1)
        loop._turn_block = [("bash", {}, "ok", True)]
        loop._flush_turn_block()
        assert loop._turn_block == []

        # Primera línea: solo "Read 1 file"
        # Segunda línea: solo "Ran 1 command" (NO "Read 1 file, Ran 1 command")
        assert len(summaries) == 2
        assert "Read" in summaries[0]
        assert "Ran" in summaries[1]
        assert "Read" not in summaries[1]  # el clave: el batch 2 no incluye el batch 1


class TestFlushTurnBlockHeader:
    """Tests para la supresión de ⎿ Wrote cuando ya se mostró ● header."""

    def test_write_only_batch_suppressed(self):
        """Batch con solo write tools y _turn_block_has_header=True → sin ⎿."""
        summaries = []
        loop = _make_loop()
        loop._status_cb = lambda x: None
        loop._print = lambda msg, *a, **k: summaries.append(msg)
        loop._turn_block_has_header = True
        loop._turn_block = [("edit_file", {"path": "x.py"}, "ok", True)]
        loop._flush_turn_block()
        # No debe imprimir resumen (write ya tiene ●)
        assert summaries == []
        assert loop._turn_block == []
        assert loop._turn_block_has_header is False

    def test_write_and_bash_shows_bash_only(self):
        """Batch write+bash con header → solo ⎿ para bash, write suprimido."""
        summaries = []
        loop = _make_loop()
        loop._status_cb = lambda x: None
        loop._print = lambda msg, *a, **k: summaries.append(msg)
        loop._turn_block_has_header = True
        loop._turn_block = [
            ("edit_file", {"path": "x.py"}, "ok", True),
            ("bash", {}, "ok", True),
        ]
        loop._flush_turn_block()
        assert len(summaries) == 1
        assert "Ran" in summaries[0]
        assert "Updated" not in summaries[0]  # edit_file filtrado

    def test_no_header_shows_all(self):
        """Sin header previo → ⎿ muestra todos los tools normalmente."""
        summaries = []
        loop = _make_loop()
        loop._status_cb = lambda x: None
        loop._print = lambda msg, *a, **k: summaries.append(msg)
        loop._turn_block_has_header = False
        loop._turn_block = [
            ("edit_file", {"path": "x.py"}, "ok", True),
            ("bash", {}, "ok", True),
        ]
        loop._flush_turn_block()
        assert len(summaries) == 1
        assert "Updated" in summaries[0]
        assert "Ran" in summaries[0]

    def test_header_flag_reset_after_flush(self):
        """_turn_block_has_header se resetea a False tras flush."""
        loop = _make_loop()
        loop._status_cb = lambda x: None
        loop._print = lambda *a, **k: None
        loop._turn_block_has_header = True
        loop._turn_block = [("edit_file", {}, "ok", True)]
        loop._flush_turn_block()
        assert loop._turn_block_has_header is False


# ─────────────────────────────────────────────────────────────────────────────
# tools.progress — mecanismo de callback de progreso
# ─────────────────────────────────────────────────────────────────────────────

import threading

class TestProgressCallback:

    def test_set_and_report(self):
        """set_progress_callback + report_progress llama el callback."""
        from tools.progress import set_progress_callback, report_progress
        received = []
        set_progress_callback(lambda f: received.append(f))
        report_progress("src/foo.py")
        report_progress("src/bar.py")
        set_progress_callback(None)
        assert received == ["src/foo.py", "src/bar.py"]

    def test_none_callback_no_error(self):
        """report_progress sin callback no lanza excepción."""
        from tools.progress import set_progress_callback, report_progress
        set_progress_callback(None)
        report_progress("any/file.py")  # no debe lanzar

    def test_exception_in_callback_swallowed(self):
        """Excepción en el callback no propaga."""
        from tools.progress import set_progress_callback, report_progress
        def bad_cb(f): raise RuntimeError("boom")
        set_progress_callback(bad_cb)
        report_progress("x.py")  # no debe lanzar
        set_progress_callback(None)

    def test_thread_local_isolation(self):
        """Callbacks son thread-local — no se mezclan entre hilos."""
        from tools.progress import set_progress_callback, report_progress
        results_a: list[str] = []
        results_b: list[str] = []

        def thread_a():
            set_progress_callback(lambda f: results_a.append(f))
            import time; time.sleep(0.05)
            report_progress("file_a.py")
            set_progress_callback(None)

        def thread_b():
            set_progress_callback(lambda f: results_b.append(f))
            report_progress("file_b.py")
            set_progress_callback(None)

        t_a = threading.Thread(target=thread_a)
        t_b = threading.Thread(target=thread_b)
        t_a.start(); t_b.start()
        t_a.join(); t_b.join()

        assert "file_a.py" in results_a
        assert "file_b.py" in results_b
        assert "file_a.py" not in results_b
        assert "file_b.py" not in results_a


# ─────────────────────────────────────────────────────────────────────────────
# AgentLoop._tool_current_file — campo inicializado
# ─────────────────────────────────────────────────────────────────────────────

class TestToolCurrentFile:

    def test_field_exists_and_default(self):
        loop = _make_loop()
        assert hasattr(loop, "_tool_current_file")
        assert loop._tool_current_file == ""

    def test_can_be_set(self):
        loop = _make_loop()
        loop._tool_current_file = "src/main.py"
        assert loop._tool_current_file == "src/main.py"


# ─────────────────────────────────────────────────────────────────────────────
# _show_inline_compact_result — resultado compacto inline
# ─────────────────────────────────────────────────────────────────────────────

class TestShowInlineCompactResult:

    def _collect(self, loop, name, args, result, allowed=True):
        lines = []
        loop._print = lambda msg, *a, **k: lines.append(msg)
        loop._show_inline_compact_result(name, args, result, allowed)
        return lines

    def test_denied(self):
        loop = _make_loop()
        lines = self._collect(loop, "grep_code", {}, "ok", allowed=False)
        assert any("Denegado" in l for l in lines)

    def test_no_results(self):
        loop = _make_loop()
        lines = self._collect(loop, "grep_code", {}, "Sin resultados.")
        assert any("Sin resultados" in l for l in lines)

    def test_error_result(self):
        loop = _make_loop()
        lines = self._collect(loop, "bash", {}, "Error: not found")
        assert any("not found" in l for l in lines)

    def test_search_result_shows_match_count(self):
        loop = _make_loop()
        fake_result = (
            "src/main.py:10:1\n"
            "  ▶    10│ def foo():\n"
            "src/util.py:5:3\n"
            "  ▶     5│ x = foo()\n"
        )
        lines = self._collect(loop, "grep_code", {"pattern": "foo"}, fake_result)
        out = " ".join(lines)
        assert "resultado" in out or "match" in out.lower() or "2" in out

    def test_read_tool_shows_filename(self):
        loop = _make_loop()
        lines = self._collect(
            loop, "read_file",
            {"path": "/home/user/project/src/main.py"},
            "line1\nline2\nline3\n",
        )
        out = " ".join(lines)
        assert "main.py" in out

    def test_generic_tool_shows_first_line(self):
        loop = _make_loop()
        lines = self._collect(loop, "bash", {}, "hello world\nmore stuff\n")
        out = " ".join(lines)
        assert "hello world" in out

    def test_generic_multiline_shows_count(self):
        loop = _make_loop()
        content = "\n".join(f"line {i}" for i in range(10))
        lines = self._collect(loop, "python_exec", {}, content)
        out = " ".join(lines)
        # Debe mostrar +N líneas
        assert "+" in out or "9" in out


# ─────────────────────────────────────────────────────────────────────────────
# _show_tool_running_header — TUI mode muestra ◐ para TODAS las tools
# ─────────────────────────────────────────────────────────────────────────────

class TestShowToolRunningHeaderTUI:

    def _run_header(self, loop, name, args=None):
        lines = []
        loop._print = lambda msg, *a, **k: lines.append(msg)
        loop._show_tool_running_header(name, args or {})
        return lines

    def test_write_shows_green_circle(self):
        loop = _make_loop()
        loop._status_cb = lambda x: None
        lines = self._run_header(loop, "edit_file", {"path": "foo.py"})
        assert any("◐" in l for l in lines)

    def test_search_no_circle_in_tui_mode(self):
        """En TUI mode, grep_code/bash no muestran ◐ en conversación (van a _turn_block)."""
        loop = _make_loop()
        loop._status_cb = lambda x: None
        lines = self._run_header(loop, "grep_code", {"pattern": "foo"})
        # En TUI mode las tools de búsqueda NO imprimen ◐ en la conversación
        assert not any("◐" in l for l in lines)

    def test_bash_no_circle_in_tui_mode(self):
        """En TUI mode, bash no muestra ◐ en conversación (va a _turn_block)."""
        loop = _make_loop()
        loop._status_cb = lambda x: None
        lines = self._run_header(loop, "bash", {"command": "ls"})
        assert not any("◐" in l for l in lines)

    def test_mem_tool_shows_cyan_circle(self):
        loop = _make_loop()
        loop._status_cb = lambda x: None
        lines = self._run_header(loop, "mem_save", {"name": "test"})
        out = " ".join(lines)
        assert "◐" in out

    def test_repl_mode_no_status_cb(self):
        """En modo REPL (sin _status_cb), el header se muestra igual."""
        loop = _make_loop()
        loop._status_cb = None
        lines = self._run_header(loop, "grep_code", {})
        assert any("◐" in l for l in lines)


# ─────────────────────────────────────────────────────────────────────────────
# LSP plugin — nuevas tools registradas
# ─────────────────────────────────────────────────────────────────────────────

class TestLspNewTools:

    def test_tools_list_includes_new_tools(self):
        """Las nuevas tools LSP están registradas en TOOLS."""
        from plugins.lsp import TOOLS
        names = {t[0] for t in TOOLS}
        assert "lsp_workspace_symbols" in names
        assert "lsp_call_hierarchy" in names
        assert "lsp_restart" in names

    def test_diagnostics_schema_has_wait(self):
        """lsp_diagnostics tiene parámetro wait en el schema."""
        from plugins.lsp import TOOLS
        diag_schema = next((t[2] for t in TOOLS if t[0] == "lsp_diagnostics"), None)
        assert diag_schema is not None
        props = diag_schema["parameters"]["properties"]
        assert "wait" in props

    def test_lsp_restart_no_server_msg(self):
        """lsp_restart devuelve mensaje si pool no inicializado."""
        from plugins import lsp as lsp_mod
        original_pool = lsp_mod._pool
        lsp_mod._pool = None
        try:
            result = lsp_mod.lsp_restart("foo.py")
            assert "no inicializado" in result or "LSP pool" in result
        finally:
            lsp_mod._pool = original_pool

    def test_lsp_call_hierarchy_no_client(self):
        """lsp_call_hierarchy devuelve mensaje si no hay cliente."""
        from plugins import lsp as lsp_mod
        original_pool = lsp_mod._pool
        lsp_mod._pool = None
        try:
            result = lsp_mod.lsp_call_hierarchy("foo.py", 1)
            assert "no encontrado" in result.lower() or "lsp" in result.lower()
        finally:
            lsp_mod._pool = original_pool

    def test_lsp_workspace_symbols_no_client(self):
        """lsp_workspace_symbols devuelve mensaje si no hay cliente."""
        from plugins import lsp as lsp_mod
        original_pool = lsp_mod._pool
        lsp_mod._pool = None
        try:
            result = lsp_mod.lsp_workspace_symbols("foo.py", "test")
            assert isinstance(result, str)
        finally:
            lsp_mod._pool = original_pool


# ─────────────────────────────────────────────────────────────────────────────
# TestTurnBlockAccumulation — varios batches se acumulan; flush produce 1 ⎿
# ─────────────────────────────────────────────────────────────────────────────

from unittest.mock import MagicMock


class TestTurnBlockAccumulation:
    """Verifica que _turn_block acumula tools de múltiples batches sin flush
    automático, y que _flush_turn_block produce una sola línea ⎿ con todo."""

    def _loop_with_status(self):
        """Loop en TUI mode (status_cb activo)."""
        loop = _make_loop()
        loop._status_cb = lambda x: None
        loop._print = MagicMock()
        return loop

    # ── Acumulación sin flush ──────────────────────────────────────────────

    def test_turn_block_starts_empty(self):
        loop = _make_loop()
        assert loop._turn_block == []

    def test_append_adds_to_turn_block(self):
        loop = self._loop_with_status()
        loop._turn_block.append(("read_file", {"path": "a.py"}, "ok", True))
        loop._turn_block.append(("bash", {}, "out", True))
        assert len(loop._turn_block) == 2

    def test_no_auto_flush_after_append(self):
        """Añadir a _turn_block manualmente no hace flush."""
        loop = self._loop_with_status()
        loop._turn_block.append(("read_file", {}, "ok", True))
        loop._turn_block.append(("grep_code", {}, "ok", True))
        # Sin llamar _flush_turn_block, el bloque sigue lleno
        assert len(loop._turn_block) == 2
        loop._print.assert_not_called()

    # ── Flush produce una sola ⎿ ───────────────────────────────────────────

    def test_flush_produces_single_line(self):
        """Un flush con N tools emite exactamente 1 línea ⎿."""
        loop = self._loop_with_status()
        loop._turn_block = [
            ("read_file", {"path": "a.py"}, "ok", True),
            ("grep_code", {"pattern": "foo"}, "ok", True),
            ("bash", {}, "ok", True),
        ]
        loop._flush_turn_block()
        assert loop._print.call_count == 1
        printed = loop._print.call_args[0][0]
        assert "⎿" in printed

    def test_flush_merges_reads_and_searches(self):
        """Flush combina lecturas y búsquedas en un solo resumen."""
        loop = self._loop_with_status()
        loop._turn_block = [
            ("read_file", {}, "ok", True),
            ("read_file", {}, "ok", True),
            ("grep_code", {"pattern": "bar"}, "ok", True),
        ]
        loop._flush_turn_block()
        line = loop._print.call_args[0][0]
        assert "Read 2 files" in line
        assert "Searched" in line

    def test_flush_two_batches_merged(self):
        """Simula dos batches acumulados → un solo ⎿ con todo sumado."""
        loop = self._loop_with_status()
        # batch 1
        loop._turn_block.append(("read_file", {"path": "a.py"}, "ok", True))
        loop._turn_block.append(("read_file", {"path": "b.py"}, "ok", True))
        # batch 2 (sin flush intermedio)
        loop._turn_block.append(("bash", {}, "done", True))
        loop._turn_block.append(("grep_code", {}, "ok", True))

        loop._flush_turn_block()

        assert loop._print.call_count == 1
        line = loop._print.call_args[0][0]
        assert "Read 2 files" in line
        assert "Ran 1 command" in line
        assert "Searched" in line

    # ── Flush limpia el buffer ─────────────────────────────────────────────

    def test_flush_clears_turn_block(self):
        loop = self._loop_with_status()
        loop._turn_block = [("bash", {}, "ok", True)]
        loop._flush_turn_block()
        assert loop._turn_block == []

    def test_flush_resets_header_flag(self):
        loop = self._loop_with_status()
        loop._turn_block = [("edit_file", {"path": "x.py"}, "ok", True)]
        loop._turn_block_has_header = True
        loop._flush_turn_block()
        assert loop._turn_block_has_header is False

    def test_double_flush_no_double_print(self):
        """Llamar flush dos veces solo imprime en el primero."""
        loop = self._loop_with_status()
        loop._turn_block = [("bash", {}, "ok", True)]
        loop._flush_turn_block()
        loop._flush_turn_block()  # segunda vez: _turn_block ya vacío
        assert loop._print.call_count == 1

    def test_flush_empty_block_no_print(self):
        """Flush con _turn_block vacío no imprime nada."""
        loop = self._loop_with_status()
        loop._turn_block = []
        loop._flush_turn_block()
        loop._print.assert_not_called()

    # ── capture_output mode ────────────────────────────────────────────────

    def test_flush_capture_mode_clears_silently(self):
        """En capture_output=True el flush limpia sin imprimir."""
        loop = _make_loop()
        loop.capture_output = True
        loop._status_cb = lambda x: None
        loop._print = MagicMock()
        loop._turn_block = [("bash", {}, "ok", True), ("read_file", {}, "ok", True)]
        loop._flush_turn_block()
        loop._print.assert_not_called()
        assert loop._turn_block == []

    def test_flush_no_status_cb_clears_silently(self):
        """Sin _status_cb (modo REPL) el flush limpia sin imprimir ⎿."""
        loop = _make_loop()
        loop._status_cb = None
        loop._print = MagicMock()
        loop._turn_block = [("bash", {}, "ok", True)]
        loop._flush_turn_block()
        loop._print.assert_not_called()
        assert loop._turn_block == []

    # ── write tools con header previo ──────────────────────────────────────

    def test_flush_excludes_write_when_header_shown(self):
        """Si ya se mostró un ● header para write, el flush filtra esas tools."""
        loop = self._loop_with_status()
        loop._turn_block_has_header = True
        loop._turn_block = [
            ("edit_file", {"path": "x.py"}, "ok", True),  # filtrada
            ("bash", {}, "ok", True),                       # incluida
        ]
        loop._flush_turn_block()
        line = loop._print.call_args[0][0]
        # bash debe estar pero edit_file no (ya mostrado en header)
        assert "Ran 1 command" in line
        assert "Updated" not in line

    def test_flush_only_writes_no_print_when_header_shown(self):
        """Si solo hay write tools y hay header, el flush no imprime ⎿."""
        loop = self._loop_with_status()
        loop._turn_block_has_header = True
        loop._turn_block = [
            ("edit_file", {"path": "x.py"}, "ok", True),
            ("write_file", {"path": "y.py"}, "ok", True),
        ]
        loop._flush_turn_block()
        loop._print.assert_not_called()
