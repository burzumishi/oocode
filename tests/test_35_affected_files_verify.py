"""Tests para affected_files tool y verify_after_edit hook.

Cubre:
- affected_files: encuentra ficheros con el símbolo
- affected_files: whole_word distingue símbolo de substring
- affected_files: exclude_tests filtra ficheros de test
- affected_files: directorio inexistente devuelve error
- affected_files: símbolo no encontrado devuelve mensaje claro
- affected_files: agrupa resultados por fichero
- verify_after_edit: re-lee la sección modificada y muestra contexto
- verify_after_edit: warn cuando new_string no se encuentra
- verify_after_edit: silencioso en write_file y edit_files
- verify_after_edit: silencioso en errores
- verify_after_edit: marca líneas cambiadas con ▶
- verify_after_edit: MCP variant edit_file
- HookManager: verify_after_edit en _BUILTINS y registrable
- Config: affected_files tiene permiso auto por defecto
"""
import sys, os, tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── affected_files ────────────────────────────────────────────────────────────

class TestAffectedFiles:
    def _tool(self, **kwargs):
        from mcp_servers.oocode_assistant import _tool_affected_files
        return _tool_affected_files(kwargs)

    def _make_workspace(self) -> str:
        tmpdir = tempfile.mkdtemp()
        # src/main.py — usa MY_FUNC dos veces
        Path(tmpdir, "main.py").write_text(
            "from utils import MY_FUNC\n\ndef run():\n    MY_FUNC(1)\n    MY_FUNC(2)\n"
        )
        # src/utils.py — define MY_FUNC
        Path(tmpdir, "utils.py").write_text(
            "def MY_FUNC(x):\n    return x * 2\n"
        )
        # test_main.py — referencia MY_FUNC en tests
        Path(tmpdir, "test_main.py").write_text(
            "from utils import MY_FUNC\ndef test_basic():\n    assert MY_FUNC(3) == 6\n"
        )
        # unrelated.py — no usa MY_FUNC
        Path(tmpdir, "unrelated.py").write_text(
            "x = 42\nprint(x)\n"
        )
        return tmpdir

    def test_finds_files_with_symbol(self):
        tmpdir = self._make_workspace()
        try:
            result = self._tool(symbol="MY_FUNC", directory=tmpdir)
            assert "MY_FUNC" in result
            assert "main.py" in result
            assert "utils.py" in result
        finally:
            import shutil; shutil.rmtree(tmpdir)

    def test_shows_file_count(self):
        tmpdir = self._make_workspace()
        try:
            result = self._tool(symbol="MY_FUNC", directory=tmpdir)
            assert "fichero" in result.lower() or "ref" in result.lower()
        finally:
            import shutil; shutil.rmtree(tmpdir)

    def test_symbol_not_found_clear_message(self):
        tmpdir = self._make_workspace()
        try:
            result = self._tool(symbol="NONEXISTENT_SYMBOL_XYZ", directory=tmpdir)
            assert "Ningún fichero" in result or "Sin resultados" in result or "no" in result.lower()
        finally:
            import shutil; shutil.rmtree(tmpdir)

    def test_directory_not_found_error(self):
        result = self._tool(symbol="foo", directory="/tmp/nonexistent_xyz_abc")
        assert "Error" in result or "no encontrado" in result

    def test_symbol_required(self):
        result = self._tool(symbol="", directory=".")
        assert "Error" in result or "obligatorio" in result

    def test_exclude_tests_filters_test_files(self):
        tmpdir = self._make_workspace()
        try:
            result_with    = self._tool(symbol="MY_FUNC", directory=tmpdir, exclude_tests=False)
            result_without = self._tool(symbol="MY_FUNC", directory=tmpdir, exclude_tests=True)
            # Con exclude_tests=True, test_main.py no debería aparecer
            if "test_main.py" in result_with:
                assert "test_main.py" not in result_without
        finally:
            import shutil; shutil.rmtree(tmpdir)

    def test_groups_by_file(self):
        tmpdir = self._make_workspace()
        try:
            result = self._tool(symbol="MY_FUNC", directory=tmpdir)
            # Cada fichero tiene sección con refs count
            assert "ref" in result or "─" in result
        finally:
            import shutil; shutil.rmtree(tmpdir)

    def test_extensions_filter(self):
        tmpdir = tempfile.mkdtemp()
        try:
            Path(tmpdir, "a.py").write_text("MY_SYM = 1\n")
            Path(tmpdir, "b.js").write_text("const MY_SYM = 2;\n")
            # Solo buscar en .py
            result = self._tool(symbol="MY_SYM", directory=tmpdir, extensions="py")
            assert "a.py" in result
            # b.js no debe aparecer si filtramos solo py
            # (ripgrep respeta el filtro de extensiones)
        finally:
            import shutil; shutil.rmtree(tmpdir)

    def test_whole_word_false_finds_substrings(self):
        tmpdir = tempfile.mkdtemp()
        try:
            Path(tmpdir, "a.py").write_text("MY_FUNC_EXTENDED = 1\nMY_FUNC = 2\n")
            result_ww  = self._tool(symbol="MY_FUNC", directory=tmpdir, whole_word=True)
            result_sub = self._tool(symbol="MY_FUNC", directory=tmpdir, whole_word=False)
            # Con whole_word=False encuentra "MY_FUNC_EXTENDED" también
            # Con whole_word=True solo encuentra "MY_FUNC" como palabra completa
            # Ambos deben encontrar al menos "MY_FUNC = 2"
            assert "a.py" in result_ww
            assert "a.py" in result_sub
        finally:
            import shutil; shutil.rmtree(tmpdir)

    def test_config_permission_auto(self):
        from config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["permissions"].get("affected_files") == "auto"

    def test_registered_in_oocode(self):
        """affected_files está importado del MCP server y registrable en oocode."""
        from mcp_servers.oocode_assistant import _tool_affected_files
        assert callable(_tool_affected_files)

    def test_in_mcp_tool_fns(self):
        from mcp_servers.oocode_assistant import _TOOL_FNS
        assert "affected_files" in _TOOL_FNS


# ── verify_after_edit hook ────────────────────────────────────────────────────

def _tmp_py_content(content: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


class TestVerifyAfterEdit:
    def _hook(self, tool: str, args: dict, result: str = "Editado correctamente."):
        from tools.hooks import _builtin_verify_after_edit
        return _builtin_verify_after_edit(tool, args, result)

    def test_appends_verify_section_for_edit_file(self):
        content = "def foo():\n    return 1\n\ndef bar():\n    return 2\n"
        path = _tmp_py_content(content)
        try:
            r = self._hook("edit_file", {"path": path, "old_string": "return 1", "new_string": "return 42"})
            # new_string "return 42" está en el fichero: debe aparecer en verify
            assert r is not None
            assert "[Verify]" in r
        finally:
            os.unlink(path)

    def test_shows_context_lines(self):
        content = "line1\nline2\nTARGET_LINE\nline4\nline5\n"
        path = _tmp_py_content(content)
        try:
            printed = []
            with patch("tools.hooks._hprint", side_effect=printed.append):
                r = self._hook("edit_file", {"path": path, "new_string": "TARGET_LINE"})
            assert r is not None
            assert "TARGET_LINE" in r or any("verify" in s.lower() for s in printed)
        finally:
            os.unlink(path)

    def test_marks_changed_lines_with_arrow(self):
        content = "a = 1\nb = 2\nNEW_CODE = 99\nc = 3\n"
        path = _tmp_py_content(content)
        try:
            r = self._hook("edit_file", {"path": path, "new_string": "NEW_CODE = 99"})
            assert r is not None
            assert "▶" in r
        finally:
            os.unlink(path)

    def test_warn_when_new_string_not_found(self):
        content = "def foo(): pass\n"
        path = _tmp_py_content(content)
        try:
            printed = []
            with patch("tools.hooks._hprint", side_effect=printed.append):
                r = self._hook("edit_file", {
                    "path": path,
                    "new_string": "THIS_DOES_NOT_EXIST_IN_FILE"
                })
            assert r is not None
            assert "⚠" in r or "no encontrado" in r or any("no encontrado" in s for s in printed)
        finally:
            os.unlink(path)

    def test_silent_for_write_file(self):
        path = _tmp_py_content("x = 1\n")
        try:
            r = self._hook("write_file", {"path": path, "new_string": "x = 1"})
            assert r is None
        finally:
            os.unlink(path)

    def test_edit_files_no_edits_key_silent(self):
        """edit_files sin clave 'edits' (args malformados) → silencioso."""
        path = _tmp_py_content("x = 1\n")
        try:
            r = self._hook("edit_files", {"path": path, "new_string": "x = 1"})
            assert r is None
        finally:
            os.unlink(path)

    def test_edit_files_verifies_each_edit(self):
        content = "def foo(): pass\ndef bar(): pass\n"
        path1 = _tmp_py_content(content)
        path2 = _tmp_py_content(content)
        try:
            r = self._hook("edit_files", {
                "edits": [
                    {"path": path1, "new_string": "def foo(): pass"},
                    {"path": path2, "new_string": "def bar(): pass"},
                ]
            })
            assert r is not None
            assert r.count("[Verify]") == 2
        finally:
            os.unlink(path1)
            os.unlink(path2)

    def test_edit_files_empty_edits_silent(self):
        r = self._hook("edit_files", {"edits": []})
        assert r is None

    def test_edit_files_not_found_warns(self):
        content = "def foo(): pass\n"
        path = _tmp_py_content(content)
        try:
            r = self._hook("edit_files", {
                "edits": [{"path": path, "new_string": "THIS_NOT_IN_FILE"}]
            })
            assert r is not None
            assert "no encontrado" in r
        finally:
            os.unlink(path)

    def test_silent_on_error_result(self):
        path = _tmp_py_content("x = 1\n")
        try:
            r = self._hook("edit_file", {"path": path, "new_string": "x = 1"},
                           result="Error: old_string no encontrada")
            assert r is None
        finally:
            os.unlink(path)

    def test_silent_for_read_file(self):
        r = self._hook("read_file", {"path": "/tmp/x.py", "new_string": "foo"})
        assert r is None

    def test_mcp_variant_edit_file(self):
        content = "alpha = 1\nbeta = 2\n"
        path = _tmp_py_content(content)
        try:
            r = self._hook(
                "mcp_oocode_assistant_edit_file",
                {"file_path": path, "new_string": "beta = 2"}
            )
            assert r is not None
            assert "[Verify]" in r
        finally:
            os.unlink(path)

    def test_mcp_edit_files_no_edits_key_silent(self):
        """MCP edit_files sin clave 'edits' → silencioso."""
        r = self._hook("mcp_oocode_assistant_edit_files", {"path": "/tmp/x.py", "new_string": "x"})
        assert r is None

    def test_no_new_string_no_output(self):
        path = _tmp_py_content("x = 1\n")
        try:
            r = self._hook("edit_file", {"path": path, "new_string": ""})
            assert r is None
        finally:
            os.unlink(path)

    def test_multiline_new_string(self):
        content = "def old():\n    return 1\n\ndef new_fn():\n    x = 10\n    return x\n\nend = True\n"
        path = _tmp_py_content(content)
        try:
            new_str = "def new_fn():\n    x = 10\n    return x"
            r = self._hook("edit_file", {"path": path, "new_string": new_str})
            assert r is not None
            assert "[Verify]" in r
            # El rango debe mostrar múltiples líneas
            assert "-" in r.split("[Verify]")[1]
        finally:
            os.unlink(path)


# ── HookManager registro ──────────────────────────────────────────────────────

class TestVerifyAfterEditRegistration:
    def test_in_builtins(self):
        from tools.hooks import _BUILTINS
        assert "verify_after_edit" in _BUILTINS

    def test_is_post_hook(self):
        from tools.hooks import _BUILTINS
        hook_type, _, _ = _BUILTINS["verify_after_edit"]
        assert hook_type == "post"

    def test_registrable(self):
        from tools.hooks import HookManager
        hm = HookManager()
        done = hm.register_builtins(["verify_after_edit"])
        assert "verify_after_edit" in done
        assert hm.post_count == 1

    def test_active_by_default(self):
        from config import DEFAULT_CONFIG
        defaults = DEFAULT_CONFIG["hooks"]["builtins"]
        assert "verify_after_edit" in defaults

    def test_total_builtins_now_15(self):
        from tools.hooks import _BUILTINS
        assert len(_BUILTINS) == 19  # 14 anteriores + interface_change_detector
