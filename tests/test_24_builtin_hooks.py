"""Tests para los 4 hooks built-in principales:
  - _builtin_diff_after_write
  - _builtin_ctags_after_write
  - _builtin_lint_after_write
  - _builtin_lsp_after_write

Cubre: extracción de rutas (write_file/edit_file/edit_files y variantes MCP),
       skip en resultados de error, filtrado de extensiones y _is_write_tool.
"""
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock


# ── Helpers ───────────────────────────────────────────────────────────────────

OK   = "Fichero escrito: /tmp/f.py\n1,024 bytes, 32 líneas."
ERR  = "Error: fichero no encontrado"
FAIL = "Operación fallida: rollback aplicado"
ROLL = "rollback"

# Args para cada variante de herramienta
def _write_args(path="/tmp/f.py", use_file_path=False):
    """Native write_file usa 'path'; MCP write_file usa 'file_path'."""
    key = "file_path" if use_file_path else "path"
    return {key: path, "content": "print('hello')"}

def _edit_args(path="/tmp/f.py"):
    return {"path": path, "old_string": "a", "new_string": "b"}

def _edit_files_args(paths=("/tmp/f.py", "/tmp/g.py")):
    return {"edits": [{"path": p, "old_string": "a", "new_string": "b"} for p in paths]}


# ── _is_write_tool ────────────────────────────────────────────────────────────

class TestIsWriteTool(unittest.TestCase):
    def _fn(self, name):
        from tools.hooks import _is_write_tool
        return _is_write_tool(name)

    def test_write_file_native(self):
        self.assertTrue(self._fn("write_file"))

    def test_edit_file_native(self):
        self.assertTrue(self._fn("edit_file"))

    def test_edit_files_native(self):
        self.assertTrue(self._fn("edit_files"))

    def test_mcp_write_file(self):
        self.assertTrue(self._fn("mcp__oocode_assistant__write_file"))

    def test_mcp_edit_file(self):
        self.assertTrue(self._fn("mcp__oocode_assistant__edit_file"))

    def test_mcp_edit_files(self):
        self.assertTrue(self._fn("mcp__oocode_assistant__edit_files"))

    def test_read_file_excluded(self):
        self.assertFalse(self._fn("read_file"))

    def test_bash_excluded(self):
        self.assertFalse(self._fn("bash"))

    def test_run_tests_excluded(self):
        self.assertFalse(self._fn("run_tests"))

    def test_lint_file_excluded(self):
        self.assertFalse(self._fn("lint_file"))

    def test_mcp_read_file_excluded(self):
        # mcp_*_read_file does NOT end with _write_file / _edit_file / _edit_files
        self.assertFalse(self._fn("mcp__oocode_assistant__read_file"))


# ── _builtin_diff_after_write ─────────────────────────────────────────────────

class TestDiffAfterWrite(unittest.TestCase):
    def _hook(self, tool_name, args, result):
        from tools.hooks import _builtin_diff_after_write
        return _builtin_diff_after_write(tool_name, args, result)

    def test_skips_error_result_write_file(self):
        with patch("tools.diff_renderer.render_write_diff") as m:
            r = self._hook("write_file", _write_args(), ERR)
            m.assert_not_called()
            self.assertIsNone(r)

    def test_skips_error_result_edit_file(self):
        with patch("tools.diff_renderer.render_edit_diff") as m:
            r = self._hook("edit_file", _edit_args(), ERR)
            m.assert_not_called()
            self.assertIsNone(r)

    def test_skips_fallida_result(self):
        with patch("tools.diff_renderer.render_write_diff") as m:
            r = self._hook("write_file", _write_args(), FAIL)
            m.assert_not_called()
            self.assertIsNone(r)

    def test_skips_rollback_result(self):
        with patch("tools.diff_renderer.render_edit_diff") as m:
            r = self._hook("edit_file", _edit_args(), ROLL)
            m.assert_not_called()
            self.assertIsNone(r)

    def test_calls_render_write_diff_on_success(self):
        with patch("tools.diff_renderer.render_write_diff") as m:
            r = self._hook("write_file", _write_args(), OK)
            m.assert_called_once()
            self.assertIsNone(r)

    def test_calls_render_edit_diff_on_edit_file(self):
        with patch("tools.diff_renderer.render_edit_diff") as m:
            r = self._hook("edit_file", _edit_args(), OK)
            m.assert_called_once()
            self.assertIsNone(r)

    def test_calls_render_edit_diff_on_edit_files(self):
        with patch("tools.diff_renderer.render_edit_diff") as m:
            r = self._hook("edit_files", _edit_files_args(), OK)
            m.assert_called_once()
            self.assertIsNone(r)

    def test_calls_render_write_diff_on_mcp_write_file(self):
        with patch("tools.diff_renderer.render_write_diff") as m:
            r = self._hook("mcp__oocode_assistant__write_file",
                           _write_args(use_file_path=True), OK)
            m.assert_called_once()
            self.assertIsNone(r)

    def test_calls_render_edit_diff_on_mcp_edit_file(self):
        with patch("tools.diff_renderer.render_edit_diff") as m:
            r = self._hook("mcp__oocode_assistant__edit_file", _edit_args(), OK)
            m.assert_called_once()
            self.assertIsNone(r)

    def test_unrelated_tool_returns_none(self):
        with patch("tools.diff_renderer.render_write_diff") as m:
            r = self._hook("run_tests", {}, "3 passed")
            m.assert_not_called()
            self.assertIsNone(r)


# ── _builtin_ctags_after_write ────────────────────────────────────────────────

class TestCtagsAfterWrite(unittest.TestCase):
    def _hook(self, tool_name, args, result=OK):
        from tools.hooks import _builtin_ctags_after_write
        return _builtin_ctags_after_write(tool_name, args, result)

    def test_skips_non_write_tool(self):
        with patch("tools.ctags_index.build_index_for_file") as m:
            self._hook("read_file", {"path": "/tmp/f.py"})
            m.assert_not_called()

    def test_skips_error_result(self):
        with patch("tools.ctags_index.build_index_for_file") as m:
            self._hook("write_file", _write_args(), ERR)
            m.assert_not_called()

    def test_skips_fallida_result(self):
        with patch("tools.ctags_index.build_index_for_file") as m:
            self._hook("edit_file", _edit_args(), FAIL)
            m.assert_not_called()

    def test_write_file_native_path_key(self):
        """Native write_file usa 'path' como clave."""
        with patch("tools.ctags_index.build_index_for_file") as m:
            self._hook("write_file", {"path": "/tmp/f.py"})
            m.assert_called_once_with("/tmp/f.py")

    def test_write_file_mcp_file_path_key(self):
        """MCP write_file usa 'file_path' como clave."""
        with patch("tools.ctags_index.build_index_for_file") as m:
            self._hook("write_file", {"file_path": "/tmp/f.py"})
            m.assert_called_once_with("/tmp/f.py")

    def test_edit_file_native(self):
        with patch("tools.ctags_index.build_index_for_file") as m:
            self._hook("edit_file", {"path": "/tmp/f.py"})
            m.assert_called_once_with("/tmp/f.py")

    def test_mcp_write_file(self):
        with patch("tools.ctags_index.build_index_for_file") as m:
            self._hook("mcp__oocode_assistant__write_file", {"file_path": "/tmp/f.py"})
            m.assert_called_once_with("/tmp/f.py")

    def test_mcp_edit_file(self):
        with patch("tools.ctags_index.build_index_for_file") as m:
            self._hook("mcp__oocode_assistant__edit_file", {"path": "/tmp/f.py"})
            m.assert_called_once_with("/tmp/f.py")

    def test_edit_files_multi_path(self):
        """edit_files debe indexar TODOS los ficheros del batch."""
        with patch("tools.ctags_index.build_index_for_file") as m:
            args = {"edits": [{"path": "/tmp/a.py"}, {"path": "/tmp/b.py"}]}
            self._hook("edit_files", args)
            self.assertEqual(m.call_count, 2)
            paths_called = [c.args[0] for c in m.call_args_list]
            self.assertIn("/tmp/a.py", paths_called)
            self.assertIn("/tmp/b.py", paths_called)

    def test_edit_files_skips_delete_action(self):
        """edit_files con action=delete no debe indexar ese fichero."""
        with patch("tools.ctags_index.build_index_for_file") as m:
            args = {"edits": [
                {"path": "/tmp/a.py", "action": "delete"},
                {"path": "/tmp/b.py"},
            ]}
            self._hook("edit_files", args)
            self.assertEqual(m.call_count, 1)
            m.assert_called_once_with("/tmp/b.py")

    def test_no_path_returns_none(self):
        result = self._hook("write_file", {})
        self.assertIsNone(result)

    def test_always_returns_none(self):
        with patch("tools.ctags_index.build_index_for_file"):
            result = self._hook("write_file", {"path": "/tmp/f.py"})
            self.assertIsNone(result)

    def test_ctags_exception_swallowed(self):
        """Errores en ctags no deben propagarse."""
        with patch("tools.ctags_index.build_index_for_file",
                   side_effect=RuntimeError("ctags not found")):
            # No debe lanzar excepción
            self._hook("write_file", {"path": "/tmp/f.py"})


# ── _builtin_lint_after_write ─────────────────────────────────────────────────

class TestLintAfterWrite(unittest.TestCase):
    def _hook(self, tool_name, args, result=OK):
        from tools.hooks import _builtin_lint_after_write
        return _builtin_lint_after_write(tool_name, args, result)

    def test_skips_non_write_tool(self):
        with patch("tools.hooks._lint_file") as m:
            self._hook("read_file", {"path": "/tmp/f.py"})
            m.assert_not_called()

    def test_skips_error_result(self):
        with patch("tools.hooks._lint_file") as m:
            self._hook("write_file", _write_args(), ERR)
            m.assert_not_called()

    def test_skips_fallida_result(self):
        with patch("tools.hooks._lint_file") as m:
            self._hook("edit_file", _edit_args(), FAIL)
            m.assert_not_called()

    def test_write_file_native_path(self):
        """Native write_file usa 'path'."""
        with patch("tools.hooks._lint_file", return_value="") as m:
            self._hook("write_file", {"path": "/tmp/f.py"})
            m.assert_called_once_with("/tmp/f.py")

    def test_write_file_mcp_file_path(self):
        """MCP write_file usa 'file_path'."""
        with patch("tools.hooks._lint_file", return_value="") as m:
            self._hook("write_file", {"file_path": "/tmp/f.py"})
            m.assert_called_once_with("/tmp/f.py")

    def test_edit_file_native(self):
        with patch("tools.hooks._lint_file", return_value="") as m:
            self._hook("edit_file", {"path": "/tmp/f.py"})
            m.assert_called_once_with("/tmp/f.py")

    def test_mcp_write_file(self):
        with patch("tools.hooks._lint_file", return_value="") as m:
            self._hook("mcp__oocode_assistant__write_file", {"file_path": "/tmp/f.py"})
            m.assert_called_once_with("/tmp/f.py")

    def test_mcp_edit_file(self):
        with patch("tools.hooks._lint_file", return_value="") as m:
            self._hook("mcp__oocode_assistant__edit_file", {"path": "/tmp/f.py"})
            m.assert_called_once_with("/tmp/f.py")

    def test_edit_files_multi_path(self):
        """edit_files debe lintear TODOS los ficheros del batch."""
        with patch("tools.hooks._lint_file", return_value="") as m:
            args = {"edits": [{"path": "/tmp/a.py"}, {"path": "/tmp/b.py"}]}
            self._hook("edit_files", args)
            self.assertEqual(m.call_count, 2)

    def test_edit_files_skips_delete(self):
        with patch("tools.hooks._lint_file", return_value="") as m:
            args = {"edits": [
                {"path": "/tmp/a.py", "action": "delete"},
                {"path": "/tmp/b.py"},
            ]}
            self._hook("edit_files", args)
            self.assertEqual(m.call_count, 1)
            m.assert_called_once_with("/tmp/b.py")

    def test_no_path_returns_none(self):
        result = self._hook("write_file", {})
        self.assertIsNone(result)

    def test_no_lint_output_returns_none(self):
        with patch("tools.hooks._lint_file", return_value=""):
            result = self._hook("write_file", {"path": "/tmp/f.py"})
            self.assertIsNone(result)

    def test_lint_errors_appended_to_result(self):
        """Si hay errores de lint, se añaden al resultado para que el LLM los vea."""
        with patch("tools.hooks._lint_file", return_value="✗ error en línea 5"):
            with patch("ui.console.console"):
                result = self._hook("write_file", {"path": "/tmp/f.py"})
        self.assertIsNotNone(result)
        self.assertIn("[Lint]", result)
        self.assertIn("error en línea 5", result)

    def test_lint_ok_returns_none(self):
        """Si el lint pasa sin errores, no se añade nada al resultado."""
        with patch("tools.hooks._lint_file", return_value="✓ sin errores"):
            with patch("ui.console.console"):
                result = self._hook("write_file", {"path": "/tmp/f.py"})
        self.assertIsNone(result)


# ── _builtin_lsp_after_write ──────────────────────────────────────────────────

class TestLspAfterWrite(unittest.TestCase):
    def _hook(self, tool_name, args, result=OK):
        from tools.hooks import _builtin_lsp_after_write
        return _builtin_lsp_after_write(tool_name, args, result)

    def test_skips_non_write_tool(self):
        r = self._hook("read_file", {"path": "/tmp/f.py"})
        self.assertIsNone(r)

    def test_skips_error_result(self):
        r = self._hook("write_file", _write_args(), ERR)
        self.assertIsNone(r)

    def test_skips_fallida_result(self):
        r = self._hook("edit_file", _edit_args(), FAIL)
        self.assertIsNone(r)

    def test_skips_unknown_extension(self):
        """Extensiones no-LSP (.txt, .log) no deben activar diagnósticos."""
        r = self._hook("write_file", {"path": "/tmp/f.txt"})
        self.assertIsNone(r)

    def test_skips_no_extension(self):
        r = self._hook("write_file", {"path": "/tmp/noext"})
        self.assertIsNone(r)

    def test_skips_when_no_lsp_server(self):
        """Si no hay servidor LSP, no lanzar error."""
        with patch("plugins.lsp.lsp_diagnostics",
                   return_value="No hay servidor LSP activo para este fichero"):
            r = self._hook("write_file", {"path": "/tmp/f.py"})
            self.assertIsNone(r)

    def test_supported_extension_py(self):
        with patch("plugins.lsp.lsp_diagnostics", return_value="✓ Sin errores"):
            with patch("ui.console.console"):
                r = self._hook("write_file", {"path": "/tmp/f.py"})
                # ✓ → resultado positivo
                self.assertIsNotNone(r)
                self.assertIn("✓ Sin errores", r)

    def test_supported_extension_ts(self):
        with patch("plugins.lsp.lsp_diagnostics", return_value="✓ Sin errores"):
            with patch("ui.console.console"):
                r = self._hook("write_file", {"path": "/tmp/f.ts"})
                self.assertIsNotNone(r)

    def test_supported_extension_go(self):
        with patch("plugins.lsp.lsp_diagnostics", return_value="✓ ok"):
            with patch("ui.console.console"):
                r = self._hook("write_file", {"path": "/tmp/f.go"})
                self.assertIsNotNone(r)

    def test_write_file_native_path_key(self):
        """Native write_file usa 'path'."""
        with patch("plugins.lsp.lsp_diagnostics", return_value="") as m:
            self._hook("write_file", {"path": "/tmp/f.py"})
            m.assert_called_once_with("/tmp/f.py")

    def test_write_file_mcp_file_path_key(self):
        """MCP write_file usa 'file_path'."""
        with patch("plugins.lsp.lsp_diagnostics", return_value="") as m:
            self._hook("write_file", {"file_path": "/tmp/f.py"})
            m.assert_called_once_with("/tmp/f.py")

    def test_edit_file_native(self):
        with patch("plugins.lsp.lsp_diagnostics", return_value="") as m:
            self._hook("edit_file", {"path": "/tmp/f.py"})
            m.assert_called_once_with("/tmp/f.py")

    def test_mcp_write_file(self):
        with patch("plugins.lsp.lsp_diagnostics", return_value="") as m:
            self._hook("mcp__oocode_assistant__write_file", {"file_path": "/tmp/f.py"})
            m.assert_called_once_with("/tmp/f.py")

    def test_mcp_edit_file(self):
        with patch("plugins.lsp.lsp_diagnostics", return_value="") as m:
            self._hook("mcp__oocode_assistant__edit_file", {"path": "/tmp/f.py"})
            m.assert_called_once_with("/tmp/f.py")

    def test_edit_files_runs_lsp_on_all_files(self):
        """edit_files ejecuta LSP en todos los ficheros LSP-capaces del batch."""
        with patch("plugins.lsp.lsp_diagnostics", return_value="") as m:
            args = {"edits": [{"path": "/tmp/a.py"}, {"path": "/tmp/b.py"}]}
            self._hook("edit_files", args)
            self.assertEqual(m.call_count, 2)
            calls = [c.args[0] for c in m.call_args_list]
            self.assertIn("/tmp/a.py", calls)
            self.assertIn("/tmp/b.py", calls)

    def test_edit_files_capped_at_3(self):
        """edit_files no ejecuta LSP en más de 3 ficheros para evitar saturación."""
        paths = [f"/tmp/f{i}.py" for i in range(5)]
        with patch("plugins.lsp.lsp_diagnostics", return_value="") as m:
            args = {"edits": [{"path": p} for p in paths]}
            self._hook("edit_files", args)
            self.assertLessEqual(m.call_count, 3)

    def test_lsp_errors_appended_to_result(self):
        """Errores LSP se añaden al resultado para que el LLM los vea."""
        diag = "✗ ERROR: tipo incorrecto en línea 10"
        with patch("plugins.lsp.lsp_diagnostics", return_value=diag):
            with patch("ui.console.console"):
                r = self._hook("write_file", {"path": "/tmp/f.py"})
        self.assertIsNotNone(r)
        self.assertIn("[LSP]", r)
        self.assertIn("error", r.lower())

    def test_lsp_exception_swallowed(self):
        """Errores internos de LSP no se propagan."""
        with patch("plugins.lsp.lsp_diagnostics", side_effect=ImportError("no lsp")):
            r = self._hook("write_file", {"path": "/tmp/f.py"})
            self.assertIsNone(r)

    def test_no_path_returns_none(self):
        r = self._hook("write_file", {})
        self.assertIsNone(r)


# ── LSP extensions coverage ───────────────────────────────────────────────────

class TestLspDiagExts(unittest.TestCase):
    """Verifica que _LSP_DIAG_EXTS cubre las extensiones clave."""

    def _exts(self):
        from tools.hooks import _LSP_DIAG_EXTS
        return _LSP_DIAG_EXTS

    def test_python(self):
        self.assertIn(".py", self._exts())

    def test_c_cpp(self):
        for ext in (".c", ".h", ".cpp", ".hpp"):
            self.assertIn(ext, self._exts())

    def test_js_ts(self):
        for ext in (".js", ".ts", ".jsx", ".tsx"):
            self.assertIn(ext, self._exts())

    def test_go_rust_java(self):
        for ext in (".go", ".rs", ".java"):
            self.assertIn(ext, self._exts())

    def test_shell_yaml(self):
        for ext in (".sh", ".yaml", ".yml"):
            self.assertIn(ext, self._exts())

    def test_sql_ruby_perl(self):
        for ext in (".sql", ".rb", ".pl"):
            self.assertIn(ext, self._exts())

    def test_php(self):
        self.assertIn(".php", self._exts())

    def test_txt_not_in_exts(self):
        self.assertNotIn(".txt", self._exts())

    def test_log_not_in_exts(self):
        self.assertNotIn(".log", self._exts())


# ── _BUILTINS completeness ────────────────────────────────────────────────────

class TestBuiltinsRegistry(unittest.TestCase):
    """Verifica que _BUILTINS registra todos los hooks y con los tipos correctos."""

    def _b(self):
        from tools.hooks import _BUILTINS
        return _BUILTINS

    def test_all_expected_hooks_present(self):
        expected = {
            "diff_after_write", "lsp_after_write", "ctags_after_write",
            "lint_after_write", "quick_syntax_after_write",
            "autoformat_after_write", "backup_before_write",
            "check_secrets", "log_tool_calls",
        }
        self.assertTrue(expected.issubset(set(self._b().keys())))

    def test_post_hooks_are_post(self):
        post_hooks = {
            "diff_after_write", "lsp_after_write", "ctags_after_write",
            "lint_after_write", "quick_syntax_after_write",
            "autoformat_after_write", "log_tool_calls",
        }
        for name in post_hooks:
            kind, _, _ = self._b()[name]
            self.assertEqual(kind, "post", f"{name} debe ser 'post'")

    def test_pre_hooks_are_pre(self):
        # check_secrets is "pre"; backup_before_write is now "pre+post"
        kind, _, _ = self._b()["check_secrets"]
        self.assertEqual(kind, "pre", "check_secrets debe ser 'pre'")

    def test_backup_is_pre_post(self):
        kind, _, fn = self._b()["backup_before_write"]
        self.assertEqual(kind, "pre+post", "backup_before_write debe ser 'pre+post'")
        pre_fn, post_fn = fn
        self.assertTrue(callable(pre_fn))
        self.assertTrue(callable(post_fn))

    def test_all_hooks_have_callable_fn(self):
        for name, (hook_type, _, fn) in self._b().items():
            if hook_type == "pre+post":
                pre_fn, post_fn = fn
                self.assertTrue(callable(pre_fn), f"hook '{name}' pre_fn debe ser callable")
                self.assertTrue(callable(post_fn), f"hook '{name}' post_fn debe ser callable")
            else:
                self.assertTrue(callable(fn), f"hook '{name}' debe tener fn callable")

    def test_default_config_builtins_subset_of_builtins(self):
        """Todos los hooks en DEFAULT_CONFIG deben existir en _BUILTINS."""
        from config import DEFAULT_CONFIG
        from tools.hooks import _BUILTINS
        for h in DEFAULT_CONFIG["hooks"]["builtins"]:
            self.assertIn(h, _BUILTINS, f"'{h}' en DEFAULT_CONFIG no existe en _BUILTINS")


# ── HookManager integration ───────────────────────────────────────────────────

class TestHookManagerRegisterBuiltins(unittest.TestCase):
    """Verifica que HookManager puede registrar y ejecutar los builtin hooks."""

    def _mgr(self):
        from tools.hooks import HookManager
        return HookManager()

    def test_register_single_builtin(self):
        mgr = self._mgr()
        registered = mgr.register_builtins(["diff_after_write"])
        self.assertIn("diff_after_write", registered)

    def test_register_unknown_builtin_ignored(self):
        mgr = self._mgr()
        registered = mgr.register_builtins(["no_existe_hook"])
        self.assertNotIn("no_existe_hook", registered)

    def test_register_all_default_builtins(self):
        from config import DEFAULT_CONFIG
        mgr = self._mgr()
        registered = mgr.register_builtins(DEFAULT_CONFIG["hooks"]["builtins"])
        for h in DEFAULT_CONFIG["hooks"]["builtins"]:
            self.assertIn(h, registered)

    def test_run_post_calls_fn(self):
        """run_post ejecuta los hooks registrados."""
        mgr = self._mgr()
        called = []
        def _dummy(tool, args, result):
            called.append(tool)
            return None
        mgr.register_post("write_file", _dummy)
        mgr.run_post("write_file", {"path": "/f"}, "ok")
        self.assertEqual(called, ["write_file"])

    def test_run_pre_calls_fn(self):
        """run_pre ejecuta los hooks registrados."""
        mgr = self._mgr()
        called = []
        def _dummy(tool, args):
            called.append(tool)
            return args
        mgr.register_pre("write_file", _dummy)
        mgr.run_pre("write_file", {"path": "/f"})
        self.assertEqual(called, ["write_file"])

    def test_pre_hook_none_cancels(self):
        """Pre-hook que devuelve None cancela la ejecución (run_pre devuelve continuar=False)."""
        mgr = self._mgr()
        mgr.register_pre("*", lambda t, a: None)
        continuar, _args = mgr.run_pre("write_file", {"path": "/f"})
        self.assertFalse(continuar)  # False = cancelado

    def test_post_hook_modifies_result(self):
        """Post-hook que devuelve string modifica el resultado."""
        mgr = self._mgr()
        mgr.register_post("*", lambda t, a, r: r + " MODIFIED")
        result = mgr.run_post("write_file", {}, "OK")
        self.assertEqual(result, "OK MODIFIED")


# ── check_secrets: placeholder detection ─────────────────────────────────────

class TestCheckSecretsPlaceholders(unittest.TestCase):
    """check_secrets no debe bloquear valores de marcador/ejemplo."""

    def _hook(self, content: str):
        from tools.hooks import _builtin_check_secrets
        return _builtin_check_secrets("write_file", {"content": content, "path": "/tmp/f.yml"})

    # --- casos que DEBEN bloquearse ---
    def test_real_password_blocked(self):
        """Una password real de alta entropía sí debe bloquearse."""
        result = self._hook("password: xK9!mN2@pQrZ7vW3")
        self.assertIsNone(result)

    def test_aws_key_blocked(self):
        # AWS key: AKIA + exactamente 16 chars alfanum, sin palabras placeholder
        content = "aws_access_key_id = AKIAQWERTYUIOP123456"
        self.assertIsNone(self._hook(content))

    # --- casos que NO deben bloquearse ---
    def test_example_password_allowed(self):
        result = self._hook("password: example_password")
        self.assertIsNotNone(result)

    def test_your_password_allowed(self):
        result = self._hook("password: your_password_here")
        self.assertIsNotNone(result)

    def test_changeme_allowed(self):
        result = self._hook("password: changeme")
        self.assertIsNotNone(result)

    def test_placeholder_template_allowed(self):
        result = self._hook("password: ${DB_PASSWORD}")
        self.assertIsNotNone(result)

    def test_mustache_template_allowed(self):
        result = self._hook("password: {{DB_PASSWORD}}")
        self.assertIsNotNone(result)

    def test_angle_bracket_allowed(self):
        result = self._hook("password: <your-password>")
        self.assertIsNotNone(result)

    def test_docker_compose_example_allowed(self):
        content = (
            "version: '3'\nservices:\n  db:\n    environment:\n"
            "      POSTGRES_PASSWORD: example_password\n"
            "      MYSQL_ROOT_PASSWORD: changeme\n"
        )
        result = self._hook(content)
        self.assertIsNotNone(result)

    def test_generic_secret_example_allowed(self):
        result = self._hook("secret: your_secret_key_here")
        self.assertIsNotNone(result)

    def test_api_key_placeholder_allowed(self):
        result = self._hook("api_key: your_api_key_here")
        self.assertIsNotNone(result)

    def test_xxx_placeholder_allowed(self):
        result = self._hook("password: xxxxxxxx")
        self.assertIsNotNone(result)

    def test_empty_content_allowed(self):
        result = self._hook("")
        self.assertIsNotNone(result)

    def test_no_credentials_allowed(self):
        result = self._hook("name: my_service\nport: 8080\ndebug: true")
        self.assertIsNotNone(result)


# ── _precheck_tool_call: OOCODE.md writes allowed ─────────────────────────────

class TestPrecheckOOCODEMdAllowed(unittest.TestCase):
    """El agente puede escribir/editar OOCODE.md (ya no está bloqueado)."""

    def _loop(self):
        from agent.loop import AgentLoop
        loop = AgentLoop.__new__(AgentLoop)
        loop._turn_written_scripts = set()
        loop._turn_read_paths = set()
        return loop

    def test_write_oocode_md_allowed(self):
        loop = self._loop()
        result = loop._precheck_tool_call(
            "write_file", {"path": "/home/user/project/OOCODE.md", "content": "# Project"}
        )
        self.assertIsNone(result, "write_file a OOCODE.md debe estar permitido")

    def test_edit_oocode_md_allowed(self):
        loop = self._loop()
        result = loop._precheck_tool_call(
            "edit_file", {"path": "/home/user/project/OOCODE.md",
                          "old_string": "old", "new_string": "new"}
        )
        self.assertIsNone(result, "edit_file a OOCODE.md debe estar permitido")

    def test_mcp_write_oocode_md_allowed(self):
        loop = self._loop()
        result = loop._precheck_tool_call(
            "mcp_oocode_write_file",
            {"file_path": "/project/OOCODE.md", "content": "# Updated"}
        )
        self.assertIsNone(result, "mcp write a OOCODE.md debe estar permitido")


# ── _is_modify_tool ──────────────────────────────────────────────────────────

class TestIsModifyTool(unittest.TestCase):
    """_is_modify_tool() cubre write/edit/replace/patch incluyendo MCP."""
    def _fn(self, name):
        from tools.hooks import _is_modify_tool
        return _is_modify_tool(name)

    def test_write_file(self):
        self.assertTrue(self._fn("write_file"))

    def test_edit_file(self):
        self.assertTrue(self._fn("edit_file"))

    def test_edit_files(self):
        self.assertTrue(self._fn("edit_files"))

    def test_regex_replace(self):
        self.assertTrue(self._fn("regex_replace"))

    def test_smart_replace(self):
        self.assertTrue(self._fn("smart_replace"))

    def test_bulk_replace(self):
        self.assertTrue(self._fn("bulk_replace"))

    def test_patch_apply(self):
        self.assertTrue(self._fn("patch_apply"))

    def test_mcp_regex_replace(self):
        self.assertTrue(self._fn("mcp_oocode_assistant_regex_replace"))

    def test_mcp_bulk_replace(self):
        self.assertTrue(self._fn("mcp_oocode_assistant_bulk_replace"))

    def test_mcp_patch_apply(self):
        self.assertTrue(self._fn("mcp_oocode_assistant_patch_apply"))

    def test_read_file_excluded(self):
        self.assertFalse(self._fn("read_file"))

    def test_bash_excluded(self):
        self.assertFalse(self._fn("bash"))

    def test_run_tests_excluded(self):
        self.assertFalse(self._fn("run_tests"))


# ── Permisos subagente: _non_interactive ──────────────────────────────────────

class TestSubagentNonInteractive(unittest.TestCase):
    """Cuando _ask_fn=None y _non_interactive=True, los tools 'ask' se auto-aprueban."""

    def test_ask_tool_auto_approved_when_non_interactive(self):
        from tools.permissions import PermissionManager
        pm = PermissionManager({"bash": "ask"})
        pm._non_interactive = True
        result = pm.check("bash", "ejecutar bash")
        self.assertTrue(result)
        # Debe haberse añadido a session_auto para las próximas llamadas
        self.assertIn("bash", pm._session_auto)

    def test_ask_tool_prompts_when_interactive(self):
        from tools.permissions import PermissionManager
        pm = PermissionManager({"bash": "ask"})
        pm._non_interactive = False
        # Con ask_fn que siempre retorna "n"
        pm._ask_fn = lambda tool, desc: "n"
        result = pm.check("bash", "ejecutar bash")
        self.assertFalse(result)

    def test_deny_still_denied_when_non_interactive(self):
        from tools.permissions import PermissionManager
        pm = PermissionManager({"bash": "deny"})
        pm._non_interactive = True
        result = pm.check("bash", "ejecutar bash")
        self.assertFalse(result)

    def test_auto_tool_always_allowed(self):
        from tools.permissions import PermissionManager
        pm = PermissionManager({"read_file": "auto"})
        pm._non_interactive = True
        result = pm.check("read_file", "leer fichero")
        self.assertTrue(result)


# ── Permisos config: run_tests y test_file son auto ──────────────────────────

class TestDefaultPermissions(unittest.TestCase):
    """Verifica permisos por defecto actualizados."""

    def test_run_tests_is_auto(self):
        from config import DEFAULT_CONFIG
        self.assertEqual(DEFAULT_CONFIG["permissions"]["run_tests"], "auto")

    def test_test_file_is_auto(self):
        from config import DEFAULT_CONFIG
        self.assertEqual(DEFAULT_CONFIG["permissions"]["test_file"], "auto")

    def test_bash_is_ask(self):
        from config import DEFAULT_CONFIG
        self.assertEqual(DEFAULT_CONFIG["permissions"]["bash"], "ask")

    def test_write_file_is_ask(self):
        from config import DEFAULT_CONFIG
        self.assertEqual(DEFAULT_CONFIG["permissions"]["write_file"], "ask")


if __name__ == "__main__":
    unittest.main()
