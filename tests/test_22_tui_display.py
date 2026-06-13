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
        assert "Searched for 1 pattern" in s
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


class TestModifyClosesVisualUnit:
    """Una edición completada con éxito CIERRA su unidad visual (estilo Claude Code):
    exploración + razonamiento + edición + diff pasan al buffer estático al momento;
    la siguiente write tool reabre su propio bloque. Sin esto, N ediciones del MISMO
    fichero se apilaban en un live block ("Used 16 tools") y los diffs se soltaban
    todos de golpe al final."""

    def _loop(self):
        loop = _make_loop()
        loop._status_cb = lambda x: None
        loop._webui_queue = None
        loop._print = lambda *a, **k: None
        loop._render_tool_diff_print = lambda *a, **k: None
        return loop

    def test_modify_success_flushes_block(self):
        """edit_file OK (pre_shown) → _flush_turn_block tras renderizar el diff."""
        loop = self._loop()
        flushed = []
        loop._flush_turn_block = lambda: flushed.append(True)
        loop._show_tool_block("edit_file", {"path": "/p/a.c"},
                              "✓ aplicado", allowed=True, pre_shown=True)
        assert flushed == [True]

    def test_modify_failure_keeps_block_open(self):
        """Edición FALLIDA → NO cierra (el reintento se queda en el mismo bloque)."""
        loop = self._loop()
        flushed = []
        loop._flush_turn_block = lambda: flushed.append(True)
        loop._show_tool_block("edit_file", {"path": "/p/a.c"},
                              "⛔ PRE-EDIT FALLIDO", allowed=True, pre_shown=True)
        assert flushed == []

    def test_read_tool_does_not_flush(self):
        """Las tools de lectura se bufferizan y NO cierran la unidad."""
        loop = self._loop()
        flushed = []
        loop._flush_turn_block = lambda: flushed.append(True)
        loop._show_tool_block("read_file", {"path": "/p/a.c"},
                              "contenido", allowed=True, pre_shown=True)
        assert flushed == []

    def test_next_modify_reopens_block(self):
        """Tras el cierre post-diff (sin bloque abierto), la siguiente write tool
        reabre su propia unidad ● vía _start_live_block_cb."""
        loop = self._loop()
        loop._current_write_target = ""   # reset por el flush post-diff
        loop._bullet_block_open = False
        started = []
        loop._start_live_block_cb = lambda b: started.append(b)
        loop._show_tool_running_header("edit_file", {"path": "/p/b.c"})
        assert len(started) == 1
        assert "b.c" in started[0]
        assert loop._bullet_block_open is True
        assert loop._current_write_target.endswith("b.c")

    def test_open_block_does_not_reopen(self):
        """Con bloque abierto (1ª edición tras explorar el fichero) NO se reabre
        ni se cierra nada — la exploración y la edición siguen juntas."""
        loop = self._loop()
        loop._current_write_target = ""
        loop._bullet_block_open = True    # el ● del texto del modelo sigue abierto
        started, flushed = [], []
        loop._start_live_block_cb = lambda b: started.append(b)
        loop._flush_turn_block = lambda: flushed.append(True)
        loop._show_tool_running_header("edit_file", {"path": "/p/c.c"})
        assert started == [] and flushed == []


class TestConcernChangeSplitsBlock:
    """Frontera de bloque por CAMBIO DE ASUNTO (concern) en iteraciones tool-only:
    un intento de compilación (bash/make) y la edición de un fichero son unidades
    visuales distintas. Sin esto, 'autogen + make + razonar errores + editar
    house.h' acababan TODOS bajo un mismo "Used N tools" con los 💭 enterrados.
    Las tandas de solo lectura son NEUTRALES y nunca rompen el bloque (la regla
    canónica 'razonar a solas nunca cierra' sigue intacta — deciden las TOOLS)."""

    def _loop(self):
        loop = _make_loop()
        loop._status_cb = lambda x: None
        loop._webui_queue = None
        loop._print = lambda *a, **k: None
        return loop

    @staticmethod
    def _tc(name, args):
        from types import SimpleNamespace
        return SimpleNamespace(function=SimpleNamespace(name=name, arguments=args))

    # ── _tools_concern ───────────────────────────────────────────────────────
    def test_concern_write_tool(self):
        loop = self._loop()
        tcs = [self._tc("read_file", {"path": "/p/h.c"}),
               self._tc("edit_file", {"path": "/p/h.c", "old_string": "a", "new_string": "b"})]
        assert loop._tools_concern(tcs) == "file:/p/h.c"

    def test_concern_smart_replace_file_param(self):
        loop = self._loop()
        tcs = [self._tc("smart_replace", {"file": "/p/n.h", "pattern": "x", "replacement": "y"})]
        assert loop._tools_concern(tcs) == "file:/p/n.h"

    def test_concern_cmd_tools(self):
        loop = self._loop()
        for name in ("bash", "python_exec", "make_run", "run_script"):
            assert loop._tools_concern([self._tc(name, {"command": "make"})]) == "cmd"

    def test_concern_reads_are_neutral(self):
        loop = self._loop()
        tcs = [self._tc("read_file", {"path": "/p/a.c"}),
               self._tc("grep_code", {"pattern": "foo"})]
        assert loop._tools_concern(tcs) == ""

    def test_concern_write_without_path_is_neutral(self):
        """Write tool sin ruta extraíble → '' (sin concern fiable, no romper)."""
        loop = self._loop()
        assert loop._tools_concern([self._tc("edit_file", {"old_string": "a"})]) == ""

    # ── tracking del concern del bloque ──────────────────────────────────────
    def test_cmd_tool_marks_block(self):
        loop = self._loop()
        loop._block_has_cmd = False
        loop._show_tool_running_header("bash", {"command": "make"})
        assert loop._block_has_cmd is True

    def test_flush_resets_concern(self):
        loop = self._loop()
        loop._flush_live_block_cb = lambda s: None
        loop._block_has_cmd = True
        loop._current_write_target = "/p/a.c"
        loop._flush_turn_block()
        assert loop._block_has_cmd is False
        assert loop._current_write_target == ""

    # ── decisión en run(): cmd → file rompe; lecturas no ─────────────────────
    def test_run_source_overrides_dup_on_concern_change(self):
        """run() degrada _is_dup_bullet a False cuando el concern de la tanda
        entrante difiere del concern establecido del bloque abierto. La decisión
        la toman las tools (_tools_concern), NUNCA el razonamiento a solas."""
        import inspect
        from agent.loop import AgentLoop
        src = inspect.getsource(AgentLoop.run)
        i_dup  = src.index("_is_dup_bullet = self._is_duplicate_bullet")
        i_ovr  = src.index("_next_concern = self._tools_concern(tool_calls)")
        i_step = src.index("_text_step = bool(")
        assert i_dup < i_ovr < i_step
        seg = src[i_dup:i_step]
        assert "if _is_dup_bullet:" in seg          # solo iteraciones de continuación
        assert "_blk_concern" in seg
        assert "_is_dup_bullet = False" in seg

    def test_cmd_block_then_edit_splits(self):
        """Simulación: bloque abierto con comandos (make) + tanda entrante con
        edit_file → la decisión de run() marca la tanda como unidad nueva."""
        loop = self._loop()
        loop._bullet_block_open = True
        loop._block_has_cmd = True
        loop._current_write_target = ""
        tcs = [self._tc("edit_file", {"path": "/p/house.h", "old_string": "a", "new_string": "b"})]
        assert loop._is_duplicate_bullet("", tcs) is True       # tool-only continuación…
        blk = "cmd"
        nxt = loop._tools_concern(tcs)
        assert nxt == "file:/p/house.h" and nxt != blk          # …pero el asunto cambia

    def test_cmd_block_then_reads_does_not_split(self):
        """Lecturas tras comandos (diagnóstico del error de make) NO rompen."""
        loop = self._loop()
        loop._bullet_block_open = True
        loop._block_has_cmd = True
        tcs = [self._tc("read_file", {"path": "/p/house.c"})]
        assert loop._tools_concern(tcs) == ""                   # neutral → continuación

    def test_same_file_block_does_not_split(self):
        """Más ediciones del MISMO fichero → mismo concern → mismo bloque."""
        loop = self._loop()
        loop._bullet_block_open = True
        loop._current_write_target = "/p/house.h"
        tcs = [self._tc("edit_file", {"path": "/p/house.h", "old_string": "x", "new_string": "y"})]
        assert loop._tools_concern(tcs) == "file:/p/house.h"    # == concern del bloque


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

    def test_mem_tool_flushes_block_and_skips_live_feed(self):
        """mem_save/workspace_remember NO se encierran en el bloque de tools: cierran
        el live block (su ◐ ⬡ sale estático, fuera) y no alimentan el live feed."""
        loop = _make_loop()
        loop._status_cb = lambda x: None
        loop._webui_queue = None
        flushed, live_updates = [], []
        loop._flush_live_block_cb = lambda s="": None
        loop._flush_turn_block = lambda: flushed.append(True)
        loop._update_live_tool_start_cb = lambda label, prev: live_updates.append(label)
        loop._print = lambda *a, **k: None
        loop._show_tool_running_header("mem_save", {"name": "x"})
        assert flushed == [True]
        assert live_updates == []

    def test_mem_tool_result_does_not_count_in_next_block(self):
        """El resultado de una mem tool (pre_shown) no incrementa el contador del
        bloque siguiente (saldría 'Used N+1 tools' en un bloque al que no pertenece)."""
        loop = _make_loop()
        loop._status_cb = lambda x: None
        loop._webui_queue = None
        loop._print = lambda *a, **k: None
        loop._show_inline_compact_result = lambda *a, **k: None
        counts = []
        loop._update_live_tools_cb = lambda n: counts.append(n)
        loop._show_tool_block("mem_save", {"name": "x"}, "✓ guardado",
                              allowed=True, pre_shown=True)
        assert counts == []

    def test_task_done_flushes_block_and_skips_live_feed(self):
        """task_done marca el fin de una tarea del plan: cierra la unidad visual de
        la tarea ANTES de ejecutarse (su narración ● sale estática entre bloques,
        no enterrada en _live_block_body) y no alimenta el live feed."""
        loop = _make_loop()
        loop._status_cb = lambda x: None
        loop._webui_queue = None
        flushed, live_updates = [], []
        loop._flush_live_block_cb = lambda s="": None
        loop._flush_turn_block = lambda: flushed.append(True)
        loop._update_live_tool_start_cb = lambda label, prev: live_updates.append(label)
        loop._print = lambda *a, **k: None
        loop._show_tool_running_header("task_done", {"message": "Tarea 3 hecha"})
        assert flushed == [True]
        assert live_updates == []

    def test_task_done_result_does_not_count_in_next_block(self):
        """El resultado de task_done ('✔ Tarea N/M…') es guía para el modelo, no
        display: no se bufferiza ni incrementa el contador del bloque siguiente."""
        loop = _make_loop()
        loop._status_cb = lambda x: None
        loop._webui_queue = None
        loop._print = lambda *a, **k: None
        counts = []
        loop._update_live_tools_cb = lambda n: counts.append(n)
        loop._turn_block = []
        loop._show_tool_block("task_done", {"message": "x"}, "✔ Tarea 1/3 completada",
                              allowed=True, pre_shown=True)
        assert counts == []
        assert loop._turn_block == []

    def test_first_edit_same_file_does_not_flush(self):
        """Read+edit del MISMO fichero (1ª edición tras explorarlo) NO rompe el bloque:
        la exploración y la edición del fichero quedan juntas en un bloque."""
        loop = _make_loop()
        loop._status_cb = lambda x: None
        loop._current_write_target = ""           # aún no se editó nada
        loop._live_tool_count = 3                  # ya hubo exploración del fichero
        flushed = []
        loop._flush_turn_block = lambda: flushed.append(True)
        loop._print = lambda *a, **k: None
        loop._show_tool_running_header("edit_file", {"path": "/p/foo.c"})
        assert not flushed, "la 1ª edición no debe romper el bloque (mismo fichero)"
        assert loop._current_write_target.endswith("foo.c")

    def test_switch_file_flushes_block(self):
        """Editar un fichero DISTINTO al que veníamos editando SÍ abre un bloque nuevo."""
        loop = _make_loop()
        loop._status_cb = lambda x: None
        loop._current_write_target = "/p/foo.c"   # veníamos editando foo.c
        loop._live_tool_count = 1
        flushed = []
        loop._flush_turn_block = lambda: flushed.append(True)
        loop._print = lambda *a, **k: None
        loop._show_tool_running_header("edit_file", {"path": "/p/bar.c"})
        assert flushed, "cambiar de fichero debe cerrar el bloque anterior"
        assert loop._current_write_target.endswith("bar.c")

    def test_extract_write_target_covers_file_param(self):
        """smart_replace/regex_replace usan el parámetro `file` (no `path`): si
        _extract_write_target no lo cubre, el auto-split por fichero NUNCA dispara
        para ellas y las ediciones de varios ficheros se acumulan en un solo bloque
        ("Used 13 tools" con 3 Replace de 3 ficheros — bug real 2026-06-11)."""
        loop = _make_loop()
        assert loop._extract_write_target(
            "smart_replace", {"file": "/p/a.c", "pattern": "x", "replacement": "y"}
        ) == "/p/a.c"
        assert loop._extract_write_target(
            "regex_replace", {"file": "/p/b.c", "pattern": "x", "replacement": "y"}
        ) == "/p/b.c"
        assert loop._extract_write_target("edit_file", {"path": "/p/c.c"}) == "/p/c.c"
        assert loop._extract_write_target("write_file", {"file_path": "/p/d.c"}) == "/p/d.c"

    def test_switch_file_flushes_block_smart_replace(self):
        """El auto-split también dispara entre smart_replace de ficheros distintos."""
        loop = _make_loop()
        loop._status_cb = lambda x: None
        loop._current_write_target = "/p/act_move.c"
        loop._live_tool_count = 1
        flushed = []
        loop._flush_turn_block = lambda: flushed.append(True)
        loop._print = lambda *a, **k: None
        loop._show_tool_running_header(
            "smart_replace", {"file": "/p/parser.c", "pattern": "x", "replacement": "y"})
        assert flushed, "smart_replace sobre OTRO fichero debe cerrar el bloque"
        assert loop._current_write_target.endswith("parser.c")

    def test_repl_mode_no_status_cb(self):
        """En modo REPL (sin _status_cb), el header se muestra igual."""
        loop = _make_loop()
        loop._status_cb = None
        lines = self._run_header(loop, "grep_code", {})
        assert any("◐" in l for l in lines)

    def test_spawn_subagent_flushes_live_block_first(self):
        """spawn_subagent en TUI cierra el live block del mensaje anterior antes de
        imprimir su header → el subagente es un mensaje NUEVO, no queda enterrado en
        el bloque de tools previo (no se ve hasta el flush)."""
        loop = _make_loop()
        loop._status_cb = lambda x: None
        loop._webui_queue = None
        loop._sub_lines_shown = 5
        flushed = []
        loop._flush_live_block_cb = lambda s="": None
        loop._flush_turn_block = lambda: flushed.append(True)
        agent_id = "coding"  # _tgt=None → fallback emoji/name (sin agentes en cfg default)
        lines = self._run_header(loop, "spawn_subagent",
                                 {"agent_id": agent_id, "task": "haz X"})
        # Se cerró el live block del mensaje anterior ANTES de imprimir el header
        assert flushed == [True]
        # El header ● del subagente se imprimió en la conversación (mensaje nuevo)
        assert any("●" in l and "spawn_subagent" in l for l in lines)
        # Reseteó el buffer de líneas del subagente
        assert loop._sub_lines_shown == 0

    def test_spawn_subagent_does_not_feed_previous_live_block(self):
        """El update del live block (que enterraría el header en _live_block_body del ●
        anterior) NO se invoca para spawn_subagent en TUI."""
        loop = _make_loop()
        loop._status_cb = lambda x: None
        loop._webui_queue = None
        loop._sub_lines_shown = 0
        loop._flush_live_block_cb = lambda s="": None
        loop._flush_turn_block = lambda: None
        live_updates = []
        loop._update_live_tool_start_cb = lambda label, prev: live_updates.append(label)
        agent_id = "coding"  # _tgt=None → fallback emoji/name (sin agentes en cfg default)
        self._run_header(loop, "spawn_subagent",
                         {"agent_id": agent_id, "task": "haz X"})
        # spawn_subagent NO alimenta el live block del mensaje anterior
        assert live_updates == []

    @pytest.mark.parametrize("tool", ["explore", "create_team", "run_team", "spawn_fanout"])
    def test_orchestration_tools_flush_live_block(self, tool):
        """Todas las tools de orquestación cierran el live block del mensaje anterior
        antes de ejecutar → su streaming │ no queda enterrado en el ● previo."""
        loop = _make_loop()
        loop._status_cb = lambda x: None
        loop._webui_queue = None
        flushed = []
        loop._flush_live_block_cb = lambda s="": None
        loop._flush_turn_block = lambda: flushed.append(True)
        live_updates = []
        loop._update_live_tool_start_cb = lambda label, prev: live_updates.append(label)
        self._run_header(loop, tool, {"task": "x", "team_id": "t", "agent_id": "a",
                                      "task_chunks": ["a"], "subtasks": []})
        assert flushed == [True]
        # NO alimentan el live block del mensaje anterior
        assert live_updates == []


class TestSubagentLinePrintCap:
    """El streaming │ del subagente tiene un cap _MAX_SUB_LINES *por turno*.

    Regresión: el cap se reseteaba solo una vez por run() completo, así que un
    subagente multi-turno congelaba tras 12 líneas y ocultaba toda la actividad
    posterior. El bucle de turnos (run()) ahora resetea _sub_lines_shown por turno
    para que las líneas nuevas sigan apareciendo (las antiguas hacen scroll arriba).
    """

    def _sub_loop(self, monkeypatch, max_lines=3):
        from unittest.mock import MagicMock
        import agent.loop as _loop_mod
        loop = _make_loop()
        loop.is_subagent = True
        loop.capture_output = False
        loop._webui_queue = None
        loop._subagent_color_idx = 0
        loop._sub_lines_shown = 0
        loop._MAX_SUB_LINES = max_lines
        printed = []
        fake_console = MagicMock()
        fake_console.print = lambda *a, **k: printed.append(a[0] if a else "")
        monkeypatch.setattr(_loop_mod, "console", fake_console)
        return loop, printed

    def test_subagent_suppresses_after_cap(self, monkeypatch):
        loop, printed = self._sub_loop(monkeypatch, max_lines=3)
        for i in range(6):
            loop._print(f"line {i}")
        # 3 líneas reales + 1 aviso "buffer lleno"; el resto se suprime
        real = [p for p in printed if "buffer lleno" not in str(p)]
        assert len(real) == 3
        assert any("buffer lleno" in str(p) for p in printed)

    def test_per_turn_reset_resumes_streaming(self, monkeypatch):
        loop, printed = self._sub_loop(monkeypatch, max_lines=3)
        for i in range(5):
            loop._print(f"t1 {i}")
        n_after_turn1 = len([p for p in printed if "buffer lleno" not in str(p)])
        # El reset por turno (lo que hace el bucle de run() en cada iteración)
        loop._sub_lines_shown = 0
        loop._print("t2 nueva linea")
        n_after_turn2 = len([p for p in printed if "buffer lleno" not in str(p)])
        # Tras el reset vuelven a imprimirse líneas nuevas (no quedó congelado)
        assert n_after_turn2 == n_after_turn1 + 1

    def test_reset_only_for_subagent_in_loop(self):
        """El reset por turno solo aplica a subagentes (el agente principal no usa cap)."""
        import inspect
        from agent.loop import AgentLoop
        src = inspect.getsource(AgentLoop.run)
        assert "if self.is_subagent:" in src
        assert "self._sub_lines_shown = 0" in src


class TestSubagentBulletAlignment:
    """El ● de texto de un subagente pasa por _print (prefijo │ alineado), no por
    console.print directo en columna 0 (desalineado respecto a sus líneas de tool)."""

    def _sub_loop(self, monkeypatch):
        from unittest.mock import MagicMock
        import agent.loop as _loop_mod
        loop = _make_loop()
        loop.is_subagent = True
        loop.capture_output = False
        loop._webui_queue = None
        loop._subagent_color_idx = 0
        loop._sub_lines_shown = 0
        loop._MAX_SUB_LINES = 20
        loop._start_live_block_cb = None
        calls = []
        fake = MagicMock()
        fake.print = lambda *a, **k: calls.append(a)
        monkeypatch.setattr(_loop_mod, "console", fake)
        return loop, calls

    def test_subagent_bullet_uses_pipe_prefix(self, monkeypatch):
        loop, calls = self._sub_loop(monkeypatch)
        loop._turn_display_bullet(
            "Tarea 6 activa: Documentar.\nVoy a crear la doc.", [])
        assert calls, "no se imprimió nada"
        # Todas las líneas llevan el prefijo │ como primer arg de console.print
        assert all("│" in str(c[0]) for c in calls if c)
        first = " ".join(str(x) for x in calls[0])
        assert "●" in first and "Tarea 6 activa" in first

    def test_subagent_bullet_continuation_indented(self, monkeypatch):
        loop, calls = self._sub_loop(monkeypatch)
        loop._turn_display_bullet("Cabecera.\nContinuación.", [])
        # 2 líneas: ● cabecera + continuación; ambas con │
        assert len(calls) == 2
        assert "●" in " ".join(str(x) for x in calls[0])
        assert "Continuación" in " ".join(str(x) for x in calls[1])

    def test_main_agent_bullet_not_pipe_wrapped(self, monkeypatch):
        loop, calls = self._sub_loop(monkeypatch)
        loop.is_subagent = False  # agente principal → rama else, columna propia
        loop._turn_display_bullet("Mensaje principal.", [])
        joined = " ".join(str(x) for c in calls for x in c)
        assert "│" not in joined
        assert "●" in joined and "Mensaje principal" in joined


class TestToolOnlyTurnStartsLiveBlock:
    """qwen3.5 (y otros modelos) emiten tool_calls SIN texto. El live block debe
    arrancar igual para que las salidas de read/bash/grep sean visibles en vivo.

    Regresión: antes el render del turno se gateaba con `if text:`, así que las
    iteraciones sin texto no arrancaban el live block ni flusheaban _turn_block →
    las tools quedaban bufferizadas e invisibles (y el siguiente flush las
    descartaba con el live block inactivo). Sólo se veía cambiar "Pensando".
    """

    def _tc(self, name, args):
        fn = MagicMock()
        fn.name = name
        fn.arguments = args
        tc = MagicMock()
        tc.function = fn
        return tc

    def test_empty_text_with_tools_starts_live_block(self, monkeypatch):
        import agent.loop as _loop_mod
        loop = _make_loop()
        loop.is_subagent = False
        loop.capture_output = False
        loop._webui_queue = None
        loop._WRITE_TOOLS = set()
        loop._live_tool_count = 0
        started = []
        loop._start_live_block_cb = lambda bullet: started.append(bullet)
        monkeypatch.setattr(_loop_mod, "console", MagicMock())
        # Respuesta tool-only: texto vacío + un read_file
        loop._turn_display_bullet("", [self._tc("read_file", {"path": "x.py"})])
        assert started, "el live block no arrancó con texto vacío + tool_calls"

    def test_empty_text_no_tools_does_not_start_live_block(self, monkeypatch):
        import agent.loop as _loop_mod
        loop = _make_loop()
        loop.is_subagent = False
        loop.capture_output = False
        loop._webui_queue = None
        loop._WRITE_TOOLS = set()
        loop._live_tool_count = 0
        started = []
        loop._start_live_block_cb = lambda bullet: started.append(bullet)
        monkeypatch.setattr(_loop_mod, "console", MagicMock())
        # Sin tools y sin texto: no debe arrancar el live block
        loop._turn_display_bullet("", [])
        assert not started

    def test_empty_text_bullet_labels_first_tool_not_ellipsis(self, monkeypatch):
        """Tool-only turn: el bullet inicial del live block debe etiquetar la primera
        tool ('Reading x.py'), NO el placeholder '…' (que era lo que el flush estático
        mostraba como header permanente del turno)."""
        import agent.loop as _loop_mod
        loop = _make_loop()
        loop.is_subagent = False
        loop.capture_output = False
        loop._webui_queue = None
        loop._WRITE_TOOLS = set()
        loop._live_tool_count = 0
        started = []
        loop._start_live_block_cb = lambda bullet: started.append(bullet)
        monkeypatch.setattr(_loop_mod, "console", MagicMock())
        loop._turn_display_bullet("", [self._tc("read_file", {"path": "x.py"})])
        assert started
        assert started[0] != "…"
        assert "Reading" in started[0] and "x.py" in started[0]

    def test_empty_text_bullet_shows_bash_command(self, monkeypatch):
        """Para bash, el bullet muestra el verbo 'Running' + el comando."""
        import agent.loop as _loop_mod
        loop = _make_loop()
        loop.is_subagent = False
        loop.capture_output = False
        loop._webui_queue = None
        loop._WRITE_TOOLS = set()
        loop._live_tool_count = 0
        started = []
        loop._start_live_block_cb = lambda bullet: started.append(bullet)
        monkeypatch.setattr(_loop_mod, "console", MagicMock())
        loop._turn_display_bullet("", [self._tc("bash", {"command": "make"})])
        assert started and started[0] != "…"
        assert "Running" in started[0]

    def test_separator_only_text_labels_first_tool(self, monkeypatch):
        """Regresión: el LLM emite '---' (regla horizontal markdown) como separador
        tras un plan. No debe renderizarse como '● ---'; el bullet del live block
        debe etiquetar la primera tool (p. ej. 'Running make…')."""
        import agent.loop as _loop_mod
        loop = _make_loop()
        loop.is_subagent = False
        loop.capture_output = False
        loop._webui_queue = None
        loop._WRITE_TOOLS = set()
        loop._live_tool_count = 0
        started = []
        loop._start_live_block_cb = lambda bullet: started.append(bullet)
        monkeypatch.setattr(_loop_mod, "console", MagicMock())
        loop._turn_display_bullet("---", [self._tc("bash", {"command": "make clean"})])
        assert started, "el live block no arrancó"
        assert started[0] != "---" and "---" not in started[0]
        assert "Running" in started[0]

    def test_separator_then_text_keeps_real_text(self, monkeypatch):
        """'---\\n\\nTexto real' → el separador inicial se descarta y el bullet usa
        el texto informativo, no '---'."""
        import agent.loop as _loop_mod
        loop = _make_loop()
        loop.is_subagent = False
        loop.capture_output = False
        loop._webui_queue = None
        loop._WRITE_TOOLS = set()
        loop._live_tool_count = 0
        started = []
        loop._start_live_block_cb = lambda bullet: started.append(bullet)
        _console = MagicMock()
        monkeypatch.setattr(_loop_mod, "console", _console)
        loop._turn_display_bullet("---\n\nCompilando el proyecto.",
                                  [self._tc("bash", {"command": "make"})])
        assert started
        # El bullet (live o estático) no debe ser el separador
        _printed = " ".join(str(c) for c in _console.print.call_args_list)
        assert "Compilando" in _printed or "Compilando" in (started[0] if started else "")
        assert started[0] != "---"

    def test_bullet_from_first_tool_empty_when_no_tools(self):
        loop = _make_loop()
        assert loop._bullet_from_first_tool([]) == ""

    def test_bullet_from_first_tool_multi_suffix(self):
        """Con varias tools, añade '(+N)' para indicar que hay más."""
        loop = _make_loop()
        lbl = loop._bullet_from_first_tool(
            [self._tc("read_file", {"path": "a.py"}), self._tc("bash", {"command": "ls"})])
        assert "(+1)" in lbl

    def test_edit_bullet_shows_file_not_tool_name(self):
        """'Editing Update' (sin sentido) → 'Editing (db.c)': muestra el fichero."""
        loop = _make_loop()
        lbl = loop._bullet_from_first_tool([self._tc("edit_file", {"path": "/x/src/db.c"})])
        assert lbl == "Editing (db.c)"
        assert "Update" not in lbl

    def test_edit_bullet_resolves_path_alias(self):
        """El modelo llama edit_file(file=…); el ● debe resolver el alias de ruta."""
        loop = _make_loop()
        lbl = loop._bullet_from_first_tool([self._tc("edit_file", {"file": "/x/src/db.c"})])
        assert lbl == "Editing (db.c)"

    def test_read_variants_bullet_show_file(self):
        """read_sections/read_files/ls_dir/code_outline… deben mostrar el fichero en el
        ● (antes el bullet caía a solo 'Reading' aunque el ⎿ sí mostraba el fichero)."""
        loop = _make_loop()
        assert loop._bullet_from_first_tool(
            [self._tc("read_sections", {"path": "/x/src/omedit.c", "sections": ["f"]})]
        ) == "Reading (omedit.c)"
        assert loop._bullet_from_first_tool(
            [self._tc("read_files", {"paths": ["/x/src/omedit.c", "/x/src/db.c"]})]
        ) == "Reading (omedit.c +1)"
        assert loop._bullet_from_first_tool(
            [self._tc("ls_dir", {"path": "/x/src"})]
        ) == "Listing (src)"
        # alias de ruta también en read_sections
        assert loop._bullet_from_first_tool(
            [self._tc("read_sections", {"file": "/x/src/omedit.c", "sections": ["f"]})]
        ) == "Reading (omedit.c)"

    def test_live_verb_label_no_ctx_drops_tool_name(self):
        """Sin contexto, un verbo propio NO cuelga el display ('Editing', no 'Editing Update')."""
        loop = _make_loop()
        assert loop._live_verb_label("edit_file", "", "Update") == "Editing"
        # Tool sin verbo propio: el display sí es la mejor pista.
        assert loop._live_verb_label("docker_inspect", "", "DockerInspect") == "Using DockerInspect"


class TestDuplicateBulletDedup:
    """qwen3.5 reemite el MISMO preámbulo cada iteración del auto-continue ejecutando
    tools distintas. _is_duplicate_bullet detecta el ● duplicado para que las tools se
    acumulen bajo un solo bloque (⎿ Ran N commands) en vez de un ● por turno."""

    def _tc(self):
        fn = MagicMock()
        fn.name = "bash"
        fn.arguments = {"command": "ls"}
        tc = MagicMock()
        tc.function = fn
        return tc

    def test_identical_text_with_open_block_is_duplicate(self):
        loop = _make_loop()
        loop.is_subagent = False
        loop.capture_output = False
        loop._bullet_block_open = True
        loop._last_displayed_bullet = "Continuaré con la modernización."
        assert loop._is_duplicate_bullet(
            "Continuaré  con   la modernización.", [self._tc()]) is True

    def test_different_text_is_not_duplicate(self):
        loop = _make_loop()
        loop.is_subagent = False
        loop.capture_output = False
        loop._bullet_block_open = True
        loop._last_displayed_bullet = "Paso A."
        assert loop._is_duplicate_bullet("Paso B.", [self._tc()]) is False

    def test_no_open_block_is_not_duplicate(self):
        loop = _make_loop()
        loop.is_subagent = False
        loop.capture_output = False
        loop._bullet_block_open = False          # sin bloque vivo → no se puede acumular
        loop._last_displayed_bullet = "Mismo texto."
        assert loop._is_duplicate_bullet("Mismo texto.", [self._tc()]) is False

    def test_no_tools_is_not_duplicate(self):
        loop = _make_loop()
        loop.is_subagent = False
        loop.capture_output = False
        loop._bullet_block_open = True
        loop._last_displayed_bullet = "Mismo texto."
        assert loop._is_duplicate_bullet("Mismo texto.", []) is False

    def test_subagent_never_duplicates(self):
        loop = _make_loop()
        loop.is_subagent = True
        loop.capture_output = True
        loop._bullet_block_open = True
        loop._last_displayed_bullet = "Mismo texto."
        assert loop._is_duplicate_bullet("Mismo texto.", [self._tc()]) is False

    def test_flush_turn_block_closes_open_flag(self):
        loop = _make_loop()
        loop.capture_output = False
        loop._status_cb = None
        loop._flush_live_block_cb = None
        loop._bullet_block_open = True
        loop._turn_block = []
        loop._flush_turn_block()
        assert loop._bullet_block_open is False


class TestOrchestrationToolFooter:
    """El footer ⎿ de explore/team/fanout se imprime ESTÁTICO (no se bufferiza en el
    live block ya cerrado, donde se perdería)."""

    def test_explore_prints_static_footer(self):
        loop = _make_loop()
        loop._status_cb = lambda x: None
        loop._webui_queue = None
        loop._live_tool_count = 0
        loop._update_live_tools_cb = lambda n: (_ for _ in ()).throw(
            AssertionError("no debe tocar el contador del live block"))
        loop._update_live_current_tool_cb = None
        lines = []
        loop._print = lambda msg, *a, **k: lines.append(msg)
        loop._show_tool_block("explore", {"task": "mapear x"},
                              "Hallazgos de la exploración\nlínea 2",
                              allowed=True, pre_shown=True)
        # Footer ⎿ impreso directamente (no enterrado en _turn_block)
        assert any("⎿" in l for l in lines)
        # No se bufferizó en _turn_block (que ya no tiene live block)
        assert loop._turn_block == []


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
        """Un flush con N tools emite exactamente 1 línea de resumen compacto."""
        loop = self._loop_with_status()
        loop._turn_block = [
            ("read_file", {"path": "a.py"}, "ok", True),
            ("grep_code", {"pattern": "foo"}, "ok", True),
            ("bash", {}, "ok", True),
        ]
        loop._flush_turn_block()
        assert loop._print.call_count == 1
        printed = loop._print.call_args[0][0]
        assert "ctrl+o to expand" in printed

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


# ─────────────────────────────────────────────────────────────────────────────
# OSC 8 hyperlinks: Rich (force_terminal=True) los emite en enlaces de markdown,
# pero el ANSI() de prompt_toolkit no los entiende y muestra el contenido crudo
# ("8;id=…;https://…URL  texto  8;;"). _flatten_osc8 los reescribe a "texto (url)".
# ─────────────────────────────────────────────────────────────────────────────

class TestFlattenOsc8:
    def _fn(self):
        from ui.app import _flatten_osc8
        return _flatten_osc8

    def test_real_reported_case(self):
        """El caso exacto reportado: enlace con id= y ST = ESC backslash."""
        flat = self._fn()
        s = ('\x1b]8;id=788935;https://en.cppreference.com/w/c/standard'
             '\x1b\\C17 Standard\x1b]8;;\x1b\\')
        assert flat(s) == 'C17 Standard (https://en.cppreference.com/w/c/standard)'
        # No queda ningún resto de la secuencia OSC 8 cruda
        assert '\x1b]8' not in flat(s)
        assert '8;id=' not in flat(s)

    def test_bel_terminator(self):
        """Soporta ST = BEL (\\x07) además de ESC backslash."""
        flat = self._fn()
        s = '\x1b]8;;https://example.com\x07texto\x1b]8;;\x07'
        assert flat(s) == 'texto (https://example.com)'

    def test_autolink_no_duplicate_url(self):
        """Si el texto visible ES la url, no se duplica."""
        flat = self._fn()
        s = '\x1b]8;;https://example.com\x07https://example.com\x1b]8;;\x07'
        assert flat(s) == 'https://example.com'

    def test_preserves_surrounding_sgr_color(self):
        """Los códigos de color SGR alrededor del enlace se conservan intactos."""
        flat = self._fn()
        s = '\x1b[32m\x1b]8;;https://a.com\x1b\\A\x1b]8;;\x1b\\\x1b[0m'
        assert flat(s) == '\x1b[32mA (https://a.com)\x1b[0m'

    def test_multiple_links_one_line(self):
        flat = self._fn()
        s = ('\x1b]8;;https://a.com\x1b\\A\x1b]8;;\x1b\\ y '
             '\x1b]8;;https://b.com\x1b\\B\x1b]8;;\x1b\\')
        assert flat(s) == 'A (https://a.com) y B (https://b.com)'

    def test_orphan_opener_stripped(self):
        """Un introductor sin cierre se elimina (no deja basura cruda)."""
        flat = self._fn()
        s = '\x1b]8;;https://a.com\x1b\\texto sin cierre'
        assert flat(s) == 'texto sin cierre'

    def test_plain_text_untouched_fastpath(self):
        """Texto sin OSC 8 pasa sin cambios (fast-path)."""
        flat = self._fn()
        s = 'línea normal \x1b[1msin enlaces\x1b[0m'
        assert flat(s) is s  # mismo objeto: salida temprana sin regex
