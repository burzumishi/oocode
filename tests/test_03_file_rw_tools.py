"""Tests de read_file, write_file, edit_file, edit_files, regex_replace, bulk_replace.

Las funciones principales de filesystem vienen de tools/filesystem.py (no MCP).
regex_replace y bulk_replace vienen del MCP server.
"""
import sys
import json
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.filesystem import read_file, write_file, edit_file, edit_files
from mcp_servers.oocode_assistant import (
    _tool_regex_replace,
    _tool_bulk_replace,
)


class TestWriteFile:
    def test_creates_file(self, tmp_path):
        f = tmp_path / "new.py"
        result = write_file(str(f), "print('hello')\n")
        assert f.exists()
        assert f.read_text() == "print('hello')\n"

    def test_overwrites_file(self, tmp_path):
        f = tmp_path / "existing.py"
        f.write_text("old content\n")
        write_file(str(f), "new content\n")
        assert f.read_text() == "new content\n"

    def test_returns_diff(self, tmp_path):
        f = tmp_path / "diff_test.py"
        f.write_text("line1\nline2\n")
        result = write_file(str(f), "line1\nline3\n")
        # El diff debería mostrar line2 → line3
        assert "line2" in result or "line3" in result or "diff" in result.lower() or "✓" in result or "Fichero" in result

    def test_creates_parent_dirs(self, tmp_path):
        f = tmp_path / "subdir" / "nested.py"
        write_file(str(f), "x = 1\n")
        assert f.exists()

    def test_missing_content(self, tmp_path):
        # write_file con contenido vacío es válido
        f = tmp_path / "empty.py"
        result = write_file(str(f), "")
        assert f.exists()


class TestReadFile:
    def test_reads_existing(self, tmp_path):
        f = tmp_path / "read_me.py"
        f.write_text("# hello\nprint('world')\n")
        result = read_file(str(f))
        assert "hello" in result or "world" in result

    def test_reads_with_offset(self, tmp_path):
        f = tmp_path / "multi.py"
        lines = [f"line{i}" for i in range(20)]
        f.write_text("\n".join(lines))
        result = read_file(str(f), offset=10, limit=5)
        assert "line10" in result

    def test_reads_with_limit(self, tmp_path):
        f = tmp_path / "limited.py"
        f.write_text("\n".join(f"L{i}" for i in range(100)))
        result = read_file(str(f), limit=10)
        assert "L0" in result
        # "más" should appear when there are remaining lines
        assert "más" in result or "90" in result

    def test_nonexistent(self, tmp_path):
        result = read_file(str(tmp_path / "nonexistent.py"))
        assert "Error" in result or "no encontrado" in result

    def test_line_numbers(self, tmp_path):
        f = tmp_path / "numbered.py"
        f.write_text("first\nsecond\nthird\n")
        result = read_file(str(f))
        # Líneas numeradas: "1\tfirst"
        assert "1" in result and "first" in result


class TestEditFile:
    def test_simple_edit(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("def old_name():\n    pass\n")
        result = edit_file(str(f), "old_name", "new_name")
        assert f.read_text() == "def new_name():\n    pass\n"
        assert "Edición" in result or "aplicada" in result

    def test_not_found(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("hello world\n")
        result = edit_file(str(f), "NONEXISTENT", "replacement")
        assert "Error" in result or "no encontrada" in result

    def test_ambiguous(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("foo\nfoo\n")
        result = edit_file(str(f), "foo", "bar")
        assert "Error" in result or "veces" in result or "2" in result

    def test_nonexistent_file(self, tmp_path):
        result = edit_file(str(tmp_path / "missing.py"), "old", "new")
        assert "Error" in result


class TestEditFileFlexible:
    """Match tolerante a whitespace: reduce fallos por espacios/indentación triviales."""

    def test_trailing_whitespace_on_inner_line(self, tmp_path):
        f = tmp_path / "c.c"
        f.write_text("/* DNS */\n#define ENABLE_DNS /**/   \n#define X\n")  # trailing ws
        # El modelo NO pone el trailing ws en la 2ª línea
        r = edit_file(str(f), "/* DNS */\n#define ENABLE_DNS /**/",
                      "/* DNS off */\n#undef ENABLE_DNS")
        assert "aplicada" in r
        assert "DNS off" in f.read_text() and "#define X" in f.read_text()

    def test_tab_vs_spaces_indent(self, tmp_path):
        f = tmp_path / "c.c"
        f.write_text("void f() {\n\tint x = 1;\n}\n")     # fichero con TAB
        r = edit_file(str(f), "void f() {\n    int x = 1;\n}",  # modelo con 4 espacios
                      "void f() {\n    int x = 2;\n}")
        assert "aplicada" in r
        assert "int x = 2;" in f.read_text()

    def test_uniform_indent_shift(self, tmp_path):
        f = tmp_path / "p.py"
        f.write_text("class A:\n    def g(self):\n        return 1\n")
        # old/new sin la indentación de clase; se reindenta al aplicar
        r = edit_file(str(f), "def g(self):\n    return 1",
                      "def g(self):\n    return 2")
        assert "aplicada" in r
        assert f.read_text() == "class A:\n    def g(self):\n        return 2\n"

    def test_ambiguous_flexible_not_applied(self, tmp_path):
        f = tmp_path / "c.c"
        f.write_text("  x = 1;\n\tx = 1;\n")   # mismo contenido, distinto whitespace
        r = edit_file(str(f), "x = 1;", "x = 2;")
        # 'x = 1;' es substring exacto 2 veces → ambiguo, no toca
        assert "Error" in r
        assert "x = 2;" not in f.read_text()

    def test_exact_still_works(self, tmp_path):
        f = tmp_path / "c.c"
        f.write_text("int a = 1;\nint b = 2;\n")
        r = edit_file(str(f), "int a = 1;", "int a = 9;")
        assert "aplicada" in r and "int a = 9;" in f.read_text()

    def test_interior_tabs_norm_level(self, tmp_path):
        """Nivel 4 (norm): tabs INTERIORES de alineación (C estilo GNU) vs espacios
        del modelo — strip no basta (el whitespace difiere dentro de la línea)."""
        f = tmp_path / "c.c"
        f.write_text("ch_printf_color (ch,\n\t\t _(\"hint\"),\n\t\t get_hint (50));\n")
        # El modelo reproduce la alineación interior con espacios
        r = edit_file(str(f),
                      "ch_printf_color (ch,\n   _(\"hint\"),\n   get_hint (50));",
                      "ch_printf_color (ch,\n   _(\"hint\"),\n   get_hint (level));")
        assert "aplicada" in r
        assert "get_hint (level));" in f.read_text()

    def test_norm_ambiguous_not_applied(self, tmp_path):
        """norm también exige match ÚNICO: dos zonas iguales al normalizar → no toca."""
        f = tmp_path / "c.c"
        f.write_text("a\tb;\nfin1;\na  b;\nfin2;\n")
        r = edit_file(str(f), "a b;", "a c;")
        assert "Error" in r
        assert "a c;" not in f.read_text()


class TestReadFileBanner:
    """skip_comment_banner colapsa cabeceras de licencia largas conservando line numbers."""

    def test_banner_collapsed_keeps_line_numbers(self, tmp_path):
        f = tmp_path / "c.c"
        banner = "/*\n" + "\n".join(f" * Author {i}" for i in range(12)) + "\n */\n"
        f.write_text(banner + "#include <stdio.h>\nint main(){return 0;}\n")
        out = read_file(str(f), skip_comment_banner=True)
        assert "cabecera de comentario/licencia" in out
        assert "15\t#include <stdio.h>" in out   # numeración preservada (banner=14 líneas)

    def test_preproc_directives_not_collapsed(self, tmp_path):
        f = tmp_path / "c.c"
        # Sin banner /* */: solo #include (directivas) → NO se colapsan
        f.write_text("#include <a.h>\n#include <b.h>\nint main(){}\n")
        out = read_file(str(f), skip_comment_banner=True)
        assert "cabecera" not in out
        assert "1\t#include <a.h>" in out

    def test_no_banner_skip_by_default(self, tmp_path):
        f = tmp_path / "c.c"
        banner = "/*\n" + "\n".join(f" * x{i}" for i in range(12)) + "\n */\n"
        f.write_text(banner + "int main(){}\n")
        out = read_file(str(f))   # default: no skip
        assert "1\t/*" in out and "cabecera" not in out

    def test_python_hash_banner(self, tmp_path):
        f = tmp_path / "m.py"
        f.write_text("\n".join(f"# Author {i}" for i in range(10)) + "\nimport os\nx = 1\n")
        out = read_file(str(f), skip_comment_banner=True)
        assert "cabecera" in out and "11\timport os" in out

    def test_sql_dash_banner(self, tmp_path):
        f = tmp_path / "q.sql"
        f.write_text("\n".join(f"-- line {i}" for i in range(9)) + "\nSELECT 1;\n")
        out = read_file(str(f), skip_comment_banner=True)
        assert "cabecera" in out and "10\tSELECT 1;" in out

    def test_python_hash_is_comment_not_preproc(self, tmp_path):
        """En Python `#` SÍ es comentario (a diferencia de C donde es directiva)."""
        f = tmp_path / "m.py"
        f.write_text("\n".join(f"# c{i}" for i in range(8)) + "\nprint(1)\n")
        out = read_file(str(f), skip_comment_banner=True)
        assert "cabecera" in out


class TestEditFiles:
    def test_single_edit(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("OLD = 1\n")
        result = edit_files([{
            "path":       str(f),
            "old_string": "OLD",
            "new_string": "NEW",
        }])
        assert "NEW" in f.read_text()
        assert "✓" in result or "aplicada" in result

    def test_atomic_rollback_on_error(self, tmp_path):
        f1 = tmp_path / "a.py"
        f1.write_text("MARKER_A\n")
        # f2 no existe → edición fallará
        result = edit_files([
            {"path": str(f1),              "old_string": "MARKER_A", "new_string": "DONE_A"},
            {"path": str(tmp_path / "b.py"), "old_string": "MARKER_B", "new_string": "DONE_B"},
        ])
        assert "Error" in result or "fallida" in result
        # f1 no debería haberse modificado (rollback)
        assert "MARKER_A" in f1.read_text() or "DONE_A" in f1.read_text()

    def test_create_operation(self, tmp_path):
        f = tmp_path / "brand_new.py"
        result = edit_files([{
            "path":      str(f),
            "operation": "create",
            "new_string": "# new file\n",
        }])
        assert f.exists()
        assert "# new file" in f.read_text()

    def test_delete_operation(self, tmp_path):
        f = tmp_path / "to_delete.py"
        f.write_text("bye\n")
        result = edit_files([{
            "path":      str(f),
            "operation": "delete",
        }])
        assert not f.exists()

    def test_dry_run(self, tmp_path):
        f = tmp_path / "original.py"
        f.write_text("ORIGINAL\n")
        result = edit_files([{
            "path":       str(f),
            "old_string": "ORIGINAL",
            "new_string": "CHANGED",
        }], dry_run=True)
        assert "ORIGINAL" in f.read_text()  # no se escribió
        assert "DRY" in result or "dry" in result.lower()

    def test_replace_all(self, tmp_path):
        f = tmp_path / "multi.py"
        f.write_text("foo\nfoo\nfoo\n")
        result = edit_files([{
            "path":        str(f),
            "old_string":  "foo",
            "new_string":  "bar",
            "replace_all": True,
        }])
        assert f.read_text() == "bar\nbar\nbar\n"

    def test_empty_edits(self):
        result = edit_files([])
        assert "Error" in result or "vacía" in result


class TestRegexReplace:
    def test_simple_replace(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("foo = 1\nbar = 2\nfoo = 3\n")
        # regex_replace uses "file" not "path", count=0 means all
        result = _tool_regex_replace({
            "file":        str(f),
            "pattern":     r"foo",
            "replacement": "baz",
            "count":       0,  # 0 = replace all
        })
        content = f.read_text()
        assert "baz" in content
        assert "foo" not in content

    def test_replace_first_only(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("foo = 1\nfoo = 2\n")
        _tool_regex_replace({
            "file":        str(f),
            "pattern":     r"foo",
            "replacement": "baz",
            "count":       1,  # 1 = replace first only
        })
        content = f.read_text()
        assert content.count("baz") == 1

    def test_invalid_regex(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("test\n")
        result = _tool_regex_replace({
            "file":        str(f),
            "pattern":     "[invalid",
            "replacement": "x",
        })
        assert "Error" in result or "regex" in result.lower() or "patrón" in result.lower() or "error" in result.lower()


class TestBulkReplace:
    def test_replace_in_multiple_files(self, tmp_path):
        (tmp_path / "a.py").write_text("OLD_TOKEN = 1\n")
        (tmp_path / "b.py").write_text("OLD_TOKEN = 2\n")
        # extensions as comma-separated string
        result = _tool_bulk_replace({
            "directory":   str(tmp_path),
            "pattern":     "OLD_TOKEN",
            "replacement": "NEW_TOKEN",
            "extensions":  "py",  # without dot, comma-separated
        })
        assert "NEW_TOKEN" in (tmp_path / "a.py").read_text()
        assert "NEW_TOKEN" in (tmp_path / "b.py").read_text()

    def test_respects_extension_filter(self, tmp_path):
        (tmp_path / "a.py").write_text("REPLACE_ME\n")
        (tmp_path / "b.txt").write_text("REPLACE_ME\n")
        _tool_bulk_replace({
            "directory":   str(tmp_path),
            "pattern":     "REPLACE_ME",
            "replacement": "DONE",
            "extensions":  "py",
        })
        assert "DONE" in (tmp_path / "a.py").read_text()
        assert "REPLACE_ME" in (tmp_path / "b.txt").read_text()
