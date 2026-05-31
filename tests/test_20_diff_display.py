"""Tests de visualización de diffs para todas las herramientas de edición de ficheros.

Cubre:
- render_replace_diff  → regex_replace / smart_replace
- render_patch_diff    → patch_apply
- render_bulk_diff     → bulk_replace
- _render_patch_sections (interno)
- _builtin_diff_after_write: despacho a los nuevos renderers
- _tool_bulk_replace: incluye bloques ###FILE: en el resultado

No requiere LLM ni conexión de red.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Helpers ───────────────────────────────────────────────────────────────────

SIMPLE_UNIFIED_DIFF = """\
--- a/foo.py
+++ b/foo.py
@@ -1,3 +1,3 @@
 line1
-old line
+new line
 line3
"""

MULTI_FILE_PATCH = """\
--- a/alpha.c
+++ b/alpha.c
@@ -1,2 +1,2 @@
-int x = 0;
+int x = 1;

--- a/beta.h
+++ b/beta.h
@@ -1,2 +1,2 @@
-#define V 0
+#define V 1

"""

BULK_RESULT_WITH_DIFFS = (
    "bulk_replace [aplicado]  4 reemplazos en 2 fichero(s):\n"
    "  ✓  src/main.c  (2 reemplazos)\n"
    "###FILE:/proj/src/main.c\n"
    "```diff\n"
    "--- a/main.c\n"
    "+++ b/main.c\n"
    "@@ -1,3 +1,3 @@\n"
    " line1\n"
    "-old\n"
    "+new\n"
    " line3\n"
    "```\n"
    "  ✓  src/utils.c  (2 reemplazos)\n"
    "###FILE:/proj/src/utils.c\n"
    "```diff\n"
    "--- a/utils.c\n"
    "+++ b/utils.c\n"
    "@@ -5,3 +5,3 @@\n"
    " ctx\n"
    "-bad\n"
    "+good\n"
    " ctx\n"
    "```\n"
)


# ── render_replace_diff ───────────────────────────────────────────────────────

class TestRenderReplaceDiff:
    def _call(self, args, result):
        from tools.diff_renderer import render_replace_diff
        with patch("tools.diff_renderer._render_diff_from_unified") as m:
            render_replace_diff(args, result)
            return m

    def test_renders_diff_for_ok_result(self):
        args = {"file": "/tmp/foo.py"}
        result = f"OK — 3 reemplazos en 'foo.py'\n\n{SIMPLE_UNIFIED_DIFF}"
        m = self._call(args, result)
        m.assert_called_once()
        path_arg, diff_arg = m.call_args[0]
        assert path_arg == "/tmp/foo.py"
        assert "---" in diff_arg

    def test_renders_diff_for_smart_replace_ok(self):
        args = {"file": "/tmp/bar.c"}
        result = f"✓ smart_replace: 2 reemplazos aplicados en 'bar.c'.\n\n{SIMPLE_UNIFIED_DIFF}"
        m = self._call(args, result)
        m.assert_called_once()

    def test_renders_diff_for_dryrun(self):
        args = {"file": "/tmp/foo.py"}
        result = f"[dry-run] 2 reemplazos en 'foo.py':\n\n{SIMPLE_UNIFIED_DIFF}"
        m = self._call(args, result)
        m.assert_called_once()

    def test_no_render_on_error(self):
        args = {"file": "/tmp/foo.py"}
        result = "Error: 'foo.py' no existe."
        m = self._call(args, result)
        m.assert_not_called()

    def test_no_render_on_no_match(self):
        args = {"file": "/tmp/foo.py"}
        result = "No se encontraron coincidencias de 'xyz' en 'foo.py'."
        m = self._call(args, result)
        m.assert_not_called()

    def test_no_render_without_file_arg(self):
        args = {}
        result = f"OK — 1 reemplazos en 'foo.py'\n\n{SIMPLE_UNIFIED_DIFF}"
        m = self._call(args, result)
        m.assert_not_called()

    def test_no_render_if_no_blank_line(self):
        args = {"file": "/tmp/foo.py"}
        result = "OK — 1 reemplazos en 'foo.py' sin diff"
        m = self._call(args, result)
        m.assert_not_called()

    def test_no_render_if_diff_text_empty(self):
        args = {"file": "/tmp/foo.py"}
        result = "OK — 1 reemplazos en 'foo.py'\n\n"
        m = self._call(args, result)
        m.assert_not_called()

    def test_no_render_if_second_part_not_diff(self):
        args = {"file": "/tmp/foo.py"}
        result = "OK — 1 reemplazos en 'foo.py'\n\nSome other text that is not a diff."
        m = self._call(args, result)
        m.assert_not_called()

    def test_passes_correct_path(self):
        args = {"file": "/home/user/src/main.c"}
        result = f"OK — 1 reemplazos en 'main.c'\n\n{SIMPLE_UNIFIED_DIFF}"
        m = self._call(args, result)
        m.assert_called_once()
        assert m.call_args[0][0] == "/home/user/src/main.c"

    def test_diff_text_stripped(self):
        args = {"file": "/tmp/foo.py"}
        result = f"OK — 1 reemplazos en 'foo.py'\n\n\n\n{SIMPLE_UNIFIED_DIFF}\n\n"
        m = self._call(args, result)
        m.assert_called_once()

    def test_no_render_on_NO_encontrado(self):
        args = {"file": "/tmp/foo.py"}
        result = "⚠ smart_replace: patrón 'xyz' NO encontrado en 'foo.py' (100 líneas)."
        m = self._call(args, result)
        m.assert_not_called()


# ── _render_patch_sections ────────────────────────────────────────────────────

class TestRenderPatchSections:
    def _call(self, patch_text):
        from tools.diff_renderer import _render_patch_sections
        with patch("tools.diff_renderer._render_diff_from_unified") as m:
            _render_patch_sections(patch_text)
            return m

    def test_single_file_patch(self):
        m = self._call(SIMPLE_UNIFIED_DIFF)
        m.assert_called_once()
        path_arg, _ = m.call_args[0]
        assert path_arg == "foo.py"

    def test_multi_file_patch_calls_twice(self):
        m = self._call(MULTI_FILE_PATCH)
        assert m.call_count == 2
        paths = [c[0][0] for c in m.call_args_list]
        assert "alpha.c" in paths
        assert "beta.h" in paths

    def test_strips_b_prefix(self):
        patch_with_b = "--- a/src/main.c\n+++ b/src/main.c\n@@ -1 +1 @@\n-x\n+y\n"
        m = self._call(patch_with_b)
        m.assert_called_once()
        assert m.call_args[0][0] == "src/main.c"

    def test_skips_dev_null(self):
        patch_text = "--- /dev/null\n+++ b/new_file.py\n@@ -0,0 +1 @@\n+new\n"
        m = self._call(patch_text)
        # /dev/null no debe renderizarse como path fuente
        # pero +++ b/new_file.py sí
        # En nuestra impl, tomamos el path del +++
        # /dev/null no está en ---; si path viene del +++ y no es /dev/null, renderiza
        # Comportamiento: si el +++ no es /dev/null, renderiza
        # Aquí +++ es b/new_file.py → path = new_file.py → se renderiza
        m.assert_called_once()
        assert m.call_args[0][0] == "new_file.py"

    def test_skips_empty_sections(self):
        m = self._call("")
        m.assert_not_called()

    def test_skips_section_without_triple_minus(self):
        m = self._call("some random text\nno patch header\n")
        m.assert_not_called()


# ── render_patch_diff ─────────────────────────────────────────────────────────

class TestRenderPatchDiff:
    def _call(self, args, result):
        from tools.diff_renderer import render_patch_diff
        with patch("tools.diff_renderer._render_patch_sections") as m:
            render_patch_diff(args, result)
            return m

    def test_renders_patch_from_args(self):
        args = {"patch": SIMPLE_UNIFIED_DIFF}
        result = "patch [aplicado]  OK\n\npatching file foo.py"
        m = self._call(args, result)
        m.assert_called_once_with(SIMPLE_UNIFIED_DIFF)

    def test_no_render_on_fallo(self):
        args = {"patch": SIMPLE_UNIFIED_DIFF}
        result = "patch [aplicado]  FALLO (exit 1)\n\nhunk FAILED"
        m = self._call(args, result)
        m.assert_not_called()

    def test_no_render_on_error(self):
        args = {"patch": SIMPLE_UNIFIED_DIFF}
        result = "Error: directorio 'xyz' no existe."
        m = self._call(args, result)
        m.assert_not_called()

    def test_no_render_without_patch(self):
        args = {}
        result = "patch [aplicado]  OK\n\npatching file foo.py"
        m = self._call(args, result)
        m.assert_not_called()

    def test_renders_patch_from_file(self, tmp_path):
        patch_file = tmp_path / "fix.patch"
        patch_file.write_text(SIMPLE_UNIFIED_DIFF)
        args = {"patch_file": str(patch_file)}
        result = "patch [aplicado]  OK\n\npatching file foo.py"
        m = self._call(args, result)
        m.assert_called_once()

    def test_patch_file_not_found_no_crash(self):
        args = {"patch_file": "/nonexistent/path.patch"}
        result = "patch [aplicado]  OK"
        m = self._call(args, result)
        m.assert_not_called()

    def test_multi_file_patch(self):
        args = {"patch": MULTI_FILE_PATCH}
        result = "patch [aplicado]  OK\n\npatching alpha.c\npatching beta.h"
        m = self._call(args, result)
        m.assert_called_once_with(MULTI_FILE_PATCH)


@pytest.fixture
def tmp_path(tmp_path_factory):
    return tmp_path_factory.mktemp("patch_diff")


# ── render_bulk_diff ──────────────────────────────────────────────────────────

class TestRenderBulkDiff:
    def _call(self, args, result):
        from tools.diff_renderer import render_bulk_diff
        with patch("tools.diff_renderer._render_diff_from_unified") as m:
            render_bulk_diff(args, result)
            return m

    def test_renders_two_file_diffs(self):
        m = self._call({"directory": "/proj"}, BULK_RESULT_WITH_DIFFS)
        assert m.call_count == 2
        paths = [c[0][0] for c in m.call_args_list]
        assert "/proj/src/main.c" in paths
        assert "/proj/src/utils.c" in paths

    def test_no_render_without_markers(self):
        result = "bulk_replace [aplicado]  5 reemplazos en 1 fichero(s):\n  ✓  main.c  (5 reemplazos)"
        m = self._call({}, result)
        m.assert_not_called()

    def test_no_render_for_empty_diff_blocks(self):
        result = "bulk_replace [aplicado]:\n  ✓  x.c  (1)\n###FILE:/x.c\n```diff\n```\n"
        m = self._call({}, result)
        m.assert_not_called()

    def test_extracts_correct_diff_text(self):
        result = (
            "bulk_replace [aplicado]:\n"
            "  ✓  file.py  (1)\n"
            "###FILE:/path/file.py\n"
            "```diff\n"
            "--- a/file.py\n"
            "+++ b/file.py\n"
            "@@ -1 +1 @@\n"
            "-x\n"
            "+y\n"
            "```\n"
        )
        m = self._call({}, result)
        m.assert_called_once()
        _, diff_arg = m.call_args[0]
        assert "+y" in diff_arg
        assert "-x" in diff_arg

    def test_single_file_marker(self):
        result = (
            "###FILE:/tmp/single.py\n"
            "```diff\n"
            "--- a/single.py\n"
            "+++ b/single.py\n"
            "@@ -1 +1 @@\n"
            "-a\n"
            "+b\n"
            "```\n"
        )
        m = self._call({}, result)
        m.assert_called_once()
        assert m.call_args[0][0] == "/tmp/single.py"


# ── _builtin_diff_after_write dispatch ───────────────────────────────────────

class TestDiffHookDispatch:
    """Verifica que _builtin_diff_after_write despache a los renderers correctos."""

    def _run_hook(self, tool_name, args, result):
        from tools.hooks import _builtin_diff_after_write
        return _builtin_diff_after_write(tool_name, args, result)

    def test_edit_file_calls_render_edit_diff(self):
        with patch("tools.diff_renderer.render_edit_diff") as m:
            self._run_hook("edit_file", {"path": "/f.py", "old_string": "a", "new_string": "b"}, "OK")
            m.assert_called_once()

    def test_write_file_calls_render_write_diff(self):
        with patch("tools.diff_renderer.render_write_diff") as m:
            self._run_hook("write_file", {"file_path": "/f.py", "content": "x"}, "OK")
            m.assert_called_once()

    def test_regex_replace_calls_render_replace_diff(self):
        with patch("tools.diff_renderer.render_replace_diff") as m:
            args = {"file": "/f.py"}
            result = f"OK — 1 reemplazos en 'f.py'\n\n{SIMPLE_UNIFIED_DIFF}"
            self._run_hook("regex_replace", args, result)
            m.assert_called_once()

    def test_smart_replace_calls_render_replace_diff(self):
        with patch("tools.diff_renderer.render_replace_diff") as m:
            args = {"file": "/f.py"}
            result = f"✓ smart_replace: 1 reemplazos aplicados en 'f.py'.\n\n{SIMPLE_UNIFIED_DIFF}"
            self._run_hook("smart_replace", args, result)
            m.assert_called_once()

    def test_mcp_regex_replace_calls_render_replace_diff(self):
        with patch("tools.diff_renderer.render_replace_diff") as m:
            args = {"file": "/f.py"}
            result = f"OK — 1 reemplazos en 'f.py'\n\n{SIMPLE_UNIFIED_DIFF}"
            self._run_hook("mcp__oocode_assistant__regex_replace", args, result)
            m.assert_called_once()

    def test_mcp_smart_replace_calls_render_replace_diff(self):
        with patch("tools.diff_renderer.render_replace_diff") as m:
            args = {"file": "/f.py"}
            result = f"✓ smart_replace: 1 reemplazos en 'f.py'.\n\n{SIMPLE_UNIFIED_DIFF}"
            self._run_hook("mcp__oocode_assistant__smart_replace", args, result)
            m.assert_called_once()

    def test_bulk_replace_calls_render_bulk_diff(self):
        with patch("tools.diff_renderer.render_bulk_diff") as m:
            self._run_hook("bulk_replace", {}, BULK_RESULT_WITH_DIFFS)
            m.assert_called_once()

    def test_mcp_bulk_replace_calls_render_bulk_diff(self):
        with patch("tools.diff_renderer.render_bulk_diff") as m:
            self._run_hook("mcp__oocode_assistant__bulk_replace", {}, BULK_RESULT_WITH_DIFFS)
            m.assert_called_once()

    def test_patch_apply_calls_render_patch_diff(self):
        with patch("tools.diff_renderer.render_patch_diff") as m:
            args = {"patch": SIMPLE_UNIFIED_DIFF}
            self._run_hook("patch_apply", args, "patch [aplicado]  OK")
            m.assert_called_once()

    def test_mcp_patch_apply_calls_render_patch_diff(self):
        with patch("tools.diff_renderer.render_patch_diff") as m:
            args = {"patch": SIMPLE_UNIFIED_DIFF}
            self._run_hook("mcp__oocode_assistant__patch_apply", args, "patch [aplicado]  OK")
            m.assert_called_once()

    def test_unrelated_tool_returns_none(self):
        result = self._run_hook("run_tests", {}, "3 tests passed")
        assert result is None

    def test_hook_returns_none_for_all_dispatch_branches(self):
        with patch("tools.diff_renderer.render_replace_diff"):
            r = self._run_hook("regex_replace", {"file": "/f.py"}, "OK\n\n---")
            assert r is None

    def test_edit_files_multi_calls_render_edit_diff(self):
        with patch("tools.diff_renderer.render_edit_diff") as m:
            args = {"edits": [{"path": "/f.py", "old_string": "a", "new_string": "b"}]}
            self._run_hook("edit_files", args, "OK")
            m.assert_called_once()


# ── bulk_replace incluye bloques ###FILE: ─────────────────────────────────────

class TestBulkReplaceIncludesDiffBlocks:
    @pytest.fixture
    def proj_dir(self, tmp_path_factory):
        d = tmp_path_factory.mktemp("bulk")
        (d / "a.py").write_text("foo = 1\nfoo = 2\n")
        (d / "b.py").write_text("foo = 3\n")
        (d / "c.py").write_text("bar = 0\n")  # sin coincidencias
        return d

    def test_includes_file_marker_in_result(self, proj_dir):
        from mcp_servers.oocode_assistant import _tool_bulk_replace
        result = _tool_bulk_replace({
            "directory": str(proj_dir),
            "pattern": "foo",
            "replacement": "baz",
            "glob": "*.py",
        })
        assert "###FILE:" in result
        assert "```diff" in result

    def test_diff_block_contains_unified_diff_markers(self, proj_dir):
        from mcp_servers.oocode_assistant import _tool_bulk_replace
        result = _tool_bulk_replace({
            "directory": str(proj_dir),
            "pattern": "foo",
            "replacement": "baz",
            "glob": "*.py",
        })
        assert "---" in result
        assert "+++" in result
        assert "-foo" in result
        assert "+baz" in result

    def test_dry_run_has_no_file_markers(self, proj_dir):
        from mcp_servers.oocode_assistant import _tool_bulk_replace
        result = _tool_bulk_replace({
            "directory": str(proj_dir),
            "pattern": "foo",
            "replacement": "baz",
            "glob": "*.py",
            "dry_run": True,
        })
        assert "###FILE:" not in result

    def test_no_match_has_no_markers(self, proj_dir):
        from mcp_servers.oocode_assistant import _tool_bulk_replace
        result = _tool_bulk_replace({
            "directory": str(proj_dir),
            "pattern": "ZZZNOMATCH",
            "replacement": "x",
            "glob": "*.py",
        })
        assert "###FILE:" not in result

    def test_file_without_match_not_in_result(self, proj_dir):
        from mcp_servers.oocode_assistant import _tool_bulk_replace
        result = _tool_bulk_replace({
            "directory": str(proj_dir),
            "pattern": "foo",
            "replacement": "baz",
            "glob": "*.py",
        })
        # c.py no tiene 'foo', no debe aparecer en markers
        markers = [line for line in result.splitlines() if line.startswith("###FILE:")]
        for m in markers:
            assert "c.py" not in m

    def test_diff_block_limit_at_five_files(self, tmp_path_factory):
        from mcp_servers.oocode_assistant import _tool_bulk_replace
        d = tmp_path_factory.mktemp("bulk6")
        for i in range(7):
            (d / f"f{i}.py").write_text(f"x = {i}\n")
        result = _tool_bulk_replace({
            "directory": str(d),
            "pattern": "x",
            "replacement": "y",
            "glob": "*.py",
        })
        marker_count = result.count("###FILE:")
        assert marker_count <= 5

    def test_files_modified_correctly(self, proj_dir):
        from mcp_servers.oocode_assistant import _tool_bulk_replace
        _tool_bulk_replace({
            "directory": str(proj_dir),
            "pattern": "foo",
            "replacement": "baz",
            "glob": "*.py",
        })
        assert (proj_dir / "a.py").read_text() == "baz = 1\nbaz = 2\n"
        assert (proj_dir / "b.py").read_text() == "baz = 3\n"
        assert (proj_dir / "c.py").read_text() == "bar = 0\n"


# ── Integración: render_replace_diff con result real de regex_replace ─────────

class TestRenderReplaceDiffIntegration:
    @pytest.fixture
    def test_file(self, tmp_path_factory):
        d = tmp_path_factory.mktemp("rrd")
        f = d / "sample.py"
        f.write_text("x = old_value\ny = other\n")
        return f

    def test_full_regex_replace_then_render(self, test_file):
        from mcp_servers.oocode_assistant import _tool_regex_replace
        from tools.diff_renderer import render_replace_diff
        result = _tool_regex_replace({
            "file": str(test_file),
            "pattern": "old_value",
            "replacement": "new_value",
        })
        assert "OK" in result
        assert "###" not in result  # regex_replace no usa markers
        # render_replace_diff no debe lanzar excepción
        with patch("tools.diff_renderer._render_diff_from_unified") as m:
            render_replace_diff({"file": str(test_file)}, result)
            m.assert_called_once()

    def test_full_smart_replace_then_render(self, test_file):
        from mcp_servers.oocode_assistant import _tool_smart_replace
        from tools.diff_renderer import render_replace_diff
        # Restaurar contenido
        test_file.write_text("x = old_value\ny = other\n")
        result = _tool_smart_replace({
            "file": str(test_file),
            "pattern": "old_value",
            "replacement": "new_value",
        })
        assert "smart_replace" in result
        with patch("tools.diff_renderer._render_diff_from_unified") as m:
            render_replace_diff({"file": str(test_file)}, result)
            m.assert_called_once()


# ── _REPLACE_TOOL_NAMES / _REPLACE_TOOL_SUFFIXES definidos en hooks ───────────

class TestHooksConstants:
    def test_replace_tool_names_exists(self):
        from tools.hooks import _REPLACE_TOOL_NAMES
        assert "regex_replace" in _REPLACE_TOOL_NAMES
        assert "smart_replace" in _REPLACE_TOOL_NAMES

    def test_replace_tool_suffixes_exists(self):
        from tools.hooks import _REPLACE_TOOL_SUFFIXES
        assert "_regex_replace" in _REPLACE_TOOL_SUFFIXES
        assert "_smart_replace" in _REPLACE_TOOL_SUFFIXES

    def test_builtin_dict_still_contains_diff_hook(self):
        from tools.hooks import _BUILTINS
        assert "diff_after_write" in _BUILTINS

    def test_diff_hook_is_post(self):
        from tools.hooks import _BUILTINS
        hook_type, pattern, fn = _BUILTINS["diff_after_write"]
        assert hook_type == "post"

    def test_diff_hook_pattern_is_star(self):
        from tools.hooks import _BUILTINS
        _, pattern, _ = _BUILTINS["diff_after_write"]
        assert pattern == "*"
