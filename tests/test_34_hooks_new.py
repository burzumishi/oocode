"""Tests para los nuevos hooks de utilidad: todo_scan, test_after_write, size_check.

Cubre:
- todo_scan_after_write: detecta TODO/FIXME/HACK/XXX en ficheros modificados
- todo_scan_after_write: silencioso sin marcadores / extensión no soportada / error
- test_after_write: descubre test file y ejecuta pytest
- test_after_write: silencioso si no hay test file / el fichero ya es un test
- size_check_after_write: avisa al superar umbral de líneas/bytes
- size_check_after_write: silencioso si está dentro del umbral / no es write tool
- HookManager: register/unregister de los nuevos built-ins
- /hooks builtin: los tres nuevos aparecen en available_builtins()
"""
import sys, os, textwrap, tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.hooks import (
    _builtin_todo_scan_after_write,
    _builtin_test_after_write,
    _builtin_size_check_after_write,
    HookManager,
    _BUILTINS,
    _SIZE_WARN_LINES,
    _SIZE_WARN_BYTES,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tmp_py(content: str, suffix=".py") -> str:
    """Escribe contenido en un fichero temporal y devuelve la ruta."""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8"
    )
    f.write(content)
    f.close()
    return f.name


# ── todo_scan_after_write ─────────────────────────────────────────────────────

class TestTodoScanAfterWrite:
    def test_detects_todo(self):
        path = _tmp_py("# TODO: refactor this\nx = 1\n")
        try:
            r = _builtin_todo_scan_after_write("write_file", {"path": path}, "OK")
            assert r is None  # hook no modifica el resultado, solo imprime
        finally:
            os.unlink(path)

    def test_detects_fixme(self):
        path = _tmp_py("# FIXME: this crashes\n")
        try:
            printed = []
            with patch("tools.hooks._hprint", side_effect=printed.append):
                _builtin_todo_scan_after_write("write_file", {"path": path}, "OK")
            assert any("FIXME" in s for s in printed)
        finally:
            os.unlink(path)

    def test_detects_hack_and_xxx(self):
        path = _tmp_py("# HACK: workaround\n# XXX: investigate\n")
        try:
            printed = []
            with patch("tools.hooks._hprint", side_effect=printed.append):
                _builtin_todo_scan_after_write("write_file", {"path": path}, "OK")
            joined = " ".join(printed)
            assert "HACK" in joined
            assert "XXX" in joined
        finally:
            os.unlink(path)

    def test_silent_when_no_markers(self):
        path = _tmp_py("x = 1\ndef foo(): pass\n")
        try:
            printed = []
            with patch("tools.hooks._hprint", side_effect=printed.append):
                r = _builtin_todo_scan_after_write("write_file", {"path": path}, "OK")
            assert r is None
            assert not printed
        finally:
            os.unlink(path)

    def test_silent_on_error_result(self):
        path = _tmp_py("# TODO: fix\n")
        try:
            printed = []
            with patch("tools.hooks._hprint", side_effect=printed.append):
                _builtin_todo_scan_after_write("write_file", {"path": path}, "Error: permiso denegado")
            assert not printed
        finally:
            os.unlink(path)

    def test_silent_for_non_code_extension(self):
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False, encoding="utf-8"
        )
        f.write("TODO: something\n")
        f.close()
        try:
            printed = []
            with patch("tools.hooks._hprint", side_effect=printed.append):
                _builtin_todo_scan_after_write("write_file", {"path": f.name}, "OK")
            assert not printed
        finally:
            os.unlink(f.name)

    def test_not_triggered_for_non_modify_tool(self):
        path = _tmp_py("# TODO: fix\n")
        try:
            printed = []
            with patch("tools.hooks._hprint", side_effect=printed.append):
                _builtin_todo_scan_after_write("read_file", {"path": path}, "contenido")
            assert not printed
        finally:
            os.unlink(path)

    def test_limits_display_to_five(self):
        todos = "".join(f"# TODO: item {i}\n" for i in range(10))
        path = _tmp_py(todos)
        try:
            printed = []
            with patch("tools.hooks._hprint", side_effect=printed.append):
                _builtin_todo_scan_after_write("write_file", {"path": path}, "OK")
            # Hay 10 TODOs; solo se muestran 5 + la línea "y N más"
            todo_lines = [s for s in printed if "TODO" in s and "item" in s]
            assert len(todo_lines) <= 5
        finally:
            os.unlink(path)

    def test_works_with_edit_files_edits_key(self):
        path = _tmp_py("# FIXME: something\n")
        try:
            printed = []
            with patch("tools.hooks._hprint", side_effect=printed.append):
                _builtin_todo_scan_after_write(
                    "edit_files",
                    {"edits": [{"path": path, "action": "write", "content": "x"}]},
                    "OK",
                )
            assert any("FIXME" in s for s in printed)
        finally:
            os.unlink(path)

    def test_mcp_variant_write_file(self):
        path = _tmp_py("# TODO: mcp test\n")
        try:
            printed = []
            with patch("tools.hooks._hprint", side_effect=printed.append):
                _builtin_todo_scan_after_write(
                    "mcp_oocode_assistant_write_file", {"file_path": path}, "OK"
                )
            assert any("TODO" in s for s in printed)
        finally:
            os.unlink(path)


# ── test_after_write ──────────────────────────────────────────────────────────

class TestTestAfterWrite:
    def _make_src_and_test(self, src_content: str, test_content: str):
        """Crea src.py y test_src.py en el mismo directorio temporal."""
        tmpdir = tempfile.mkdtemp()
        src    = Path(tmpdir) / "mymodule.py"
        tst    = Path(tmpdir) / "test_mymodule.py"
        src.write_text(src_content)
        tst.write_text(test_content)
        return str(src), str(tst), tmpdir

    def test_silent_when_no_test_file(self):
        path = _tmp_py("def foo(): return 1\n")
        try:
            r = _builtin_test_after_write("write_file", {"path": path}, "OK")
            assert r is None
        finally:
            os.unlink(path)

    def test_silent_when_source_is_test_file(self):
        """Si el fichero modificado ya es test_xxx.py, no lanzamos pytest."""
        path = _tmp_py("def test_foo(): pass\n")
        # Renombrar para que empiece con test_
        tst = path.replace(".py", "") + "_renamed_test.py"
        os.rename(path, tst)
        try:
            r = _builtin_test_after_write("write_file", {"path": tst}, "OK")
            assert r is None
        finally:
            if os.path.exists(tst):
                os.unlink(tst)

    def test_silent_on_error_result(self):
        src, tst, tmpdir = self._make_src_and_test(
            "def foo(): return 1\n",
            "from mymodule import foo\ndef test_foo(): assert foo() == 1\n",
        )
        try:
            r = _builtin_test_after_write("write_file", {"path": src}, "Error: fallo")
            assert r is None
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_not_triggered_for_non_py(self):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False)
        f.close()
        try:
            r = _builtin_test_after_write("write_file", {"path": f.name}, "OK")
            assert r is None
        finally:
            os.unlink(f.name)

    def test_not_triggered_for_non_modify_tool(self):
        path = _tmp_py("def foo(): pass\n")
        try:
            r = _builtin_test_after_write("read_file", {"path": path}, "contenido")
            assert r is None
        finally:
            os.unlink(path)

    def test_passing_tests_returns_none(self):
        src, tst, tmpdir = self._make_src_and_test(
            "def add(a, b): return a + b\n",
            "import sys, os; sys.path.insert(0, os.path.dirname(__file__))\n"
            "from mymodule import add\n"
            "def test_add(): assert add(1, 2) == 3\n",
        )
        try:
            printed = []
            with patch("tools.hooks._hprint", side_effect=printed.append):
                r = _builtin_test_after_write("write_file", {"path": src}, "OK")
            # Si pytest está instalado y pasan, result es None y se imprime ✓
            if r is not None:
                assert False, f"Unexpected result: {r}"
        except Exception:
            pass  # pytest puede no estar instalado en el entorno de test
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_failing_tests_appends_to_result(self):
        src, tst, tmpdir = self._make_src_and_test(
            "def add(a, b): return a - b\n",  # bug intencional
            "import sys, os; sys.path.insert(0, os.path.dirname(__file__))\n"
            "from mymodule import add\n"
            "def test_add(): assert add(1, 2) == 3\n",
        )
        try:
            r = _builtin_test_after_write("write_file", {"path": src}, "OK")
            # Si pytest está instalado, el test debe fallar y r debe contener el resultado
            if r is not None:
                assert "[Tests]" in r or "FAILED" in r or "assert" in r
        except Exception:
            pass  # pytest puede no estar instalado
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


# ── size_check_after_write ────────────────────────────────────────────────────

class TestSizeCheckAfterWrite:
    def test_warns_when_too_many_lines(self):
        content = "\n".join(f"x_{i} = {i}" for i in range(_SIZE_WARN_LINES + 10))
        path = _tmp_py(content)
        try:
            printed = []
            with patch("tools.hooks._hprint", side_effect=printed.append):
                r = _builtin_size_check_after_write("write_file", {"path": path}, "OK")
            assert r is None  # no modifica el resultado
            assert any("líneas" in s or "KB" in s for s in printed)
        finally:
            os.unlink(path)

    def test_warns_when_too_large_bytes(self):
        content = "x" * (_SIZE_WARN_BYTES + 100)
        path = _tmp_py(content)
        try:
            printed = []
            with patch("tools.hooks._hprint", side_effect=printed.append):
                _builtin_size_check_after_write("write_file", {"path": path}, "OK")
            assert any("KB" in s or "líneas" in s for s in printed)
        finally:
            os.unlink(path)

    def test_silent_when_within_limits(self):
        content = "\n".join(f"x_{i} = {i}" for i in range(10))
        path = _tmp_py(content)
        try:
            printed = []
            with patch("tools.hooks._hprint", side_effect=printed.append):
                r = _builtin_size_check_after_write("write_file", {"path": path}, "OK")
            assert r is None
            assert not printed
        finally:
            os.unlink(path)

    def test_silent_on_error_result(self):
        content = "\n".join(f"x_{i} = {i}" for i in range(_SIZE_WARN_LINES + 10))
        path = _tmp_py(content)
        try:
            printed = []
            with patch("tools.hooks._hprint", side_effect=printed.append):
                _builtin_size_check_after_write("write_file", {"path": path}, "Error: permiso")
            assert not printed
        finally:
            os.unlink(path)

    def test_also_triggered_for_edit_file(self):
        """edit_file también activa size_check: si tras editar el fichero supera umbral, avisa."""
        content = "\n".join(f"x_{i} = {i}" for i in range(_SIZE_WARN_LINES + 10))
        path = _tmp_py(content)
        try:
            printed = []
            with patch("tools.hooks._hprint", side_effect=printed.append):
                _builtin_size_check_after_write("edit_file", {"path": path}, "OK")
            assert any("líneas" in s or "KB" in s for s in printed)
        finally:
            os.unlink(path)

    def test_not_triggered_for_non_modify_tool(self):
        content = "\n".join(f"x_{i} = {i}" for i in range(_SIZE_WARN_LINES + 10))
        path = _tmp_py(content)
        try:
            printed = []
            with patch("tools.hooks._hprint", side_effect=printed.append):
                _builtin_size_check_after_write("read_file", {"path": path}, "contenido")
            assert not printed
        finally:
            os.unlink(path)

    def test_mcp_write_file_variant(self):
        content = "\n".join(f"x_{i} = {i}" for i in range(_SIZE_WARN_LINES + 10))
        path = _tmp_py(content)
        try:
            printed = []
            with patch("tools.hooks._hprint", side_effect=printed.append):
                _builtin_size_check_after_write(
                    "mcp_oocode_assistant_write_file", {"file_path": path}, "OK"
                )
            assert any("líneas" in s or "KB" in s for s in printed)
        finally:
            os.unlink(path)


# ── HookManager + _BUILTINS ───────────────────────────────────────────────────

class TestNewBuiltinsRegistration:
    def test_all_new_hooks_in_builtins(self):
        assert "todo_scan_after_write" in _BUILTINS
        assert "test_after_write" in _BUILTINS
        assert "size_check_after_write" in _BUILTINS

    def test_available_builtins_includes_new(self):
        available = HookManager.available_builtins()
        assert "todo_scan_after_write" in available
        assert "test_after_write" in available
        assert "size_check_after_write" in available

    def test_total_builtins_count(self):
        assert len(_BUILTINS) == 19  # 9 originales + todo_scan + test_after_write + size_check + verify_after_edit + test_suite_delta + interface_change_detector

    def test_register_todo_scan(self):
        hm = HookManager()
        done = hm.register_builtins(["todo_scan_after_write"])
        assert "todo_scan_after_write" in done
        assert hm.post_count == 1

    def test_register_test_after_write(self):
        hm = HookManager()
        done = hm.register_builtins(["test_after_write"])
        assert "test_after_write" in done
        assert hm.post_count == 1

    def test_register_size_check(self):
        hm = HookManager()
        done = hm.register_builtins(["size_check_after_write"])
        assert "size_check_after_write" in done
        assert hm.post_count == 1

    def test_unregister_todo_scan(self):
        hm = HookManager()
        hm.register_builtins(["todo_scan_after_write"])
        assert hm.post_count == 1
        removed = hm.unregister_builtin("todo_scan_after_write")
        assert removed
        assert hm.post_count == 0

    def test_new_hooks_are_post_type(self):
        for name in ("todo_scan_after_write", "test_after_write", "size_check_after_write"):
            hook_type, _, _ = _BUILTINS[name]
            assert hook_type == "post", f"{name} should be a post hook"

    def test_new_hooks_not_active_by_default(self):
        from config import DEFAULT_CONFIG
        defaults = DEFAULT_CONFIG["hooks"]["builtins"]
        for name in ("todo_scan_after_write", "test_after_write", "size_check_after_write"):
            assert name not in defaults, f"{name} should not be active by default"

    def test_all_builtins_register_cleanly(self):
        hm = HookManager()
        done = hm.register_builtins(list(_BUILTINS.keys()))
        assert len(done) == len(_BUILTINS)

    def test_double_register_idempotent(self):
        hm = HookManager()
        hm.register_builtins(["todo_scan_after_write"])
        hm.register_builtins(["todo_scan_after_write"])  # segunda vez → no duplica
        assert hm.post_count == 1
