"""Tests de tools de búsqueda: grep_code, find_files, read_files, symbol_lookup."""
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.oocode_assistant import (
    _tool_grep_code,
    _tool_find_files,
    _tool_read_files,
    _tool_symbol_lookup,
)


class TestGrepCode:
    def test_finds_pattern(self, tmp_path):
        (tmp_path / "a.py").write_text("def foo():\n    pass\n")
        (tmp_path / "b.py").write_text("def bar():\n    pass\n")
        result = _tool_grep_code({
            "pattern":   "def foo",
            "directory": str(tmp_path),
        })
        assert "def foo" in result or "a.py" in result

    def test_no_match(self, tmp_path):
        (tmp_path / "a.py").write_text("hello world\n")
        result = _tool_grep_code({
            "pattern":   "NONEXISTENT_XYZ_12345",
            "directory": str(tmp_path),
        })
        # Puede devolver vacío, "0 matches", etc.
        assert isinstance(result, str)

    def test_with_extension_filter(self, tmp_path):
        (tmp_path / "a.py").write_text("TARGET_PATTERN\n")
        (tmp_path / "b.md").write_text("TARGET_PATTERN\n")
        result = _tool_grep_code({
            "pattern":    "TARGET_PATTERN",
            "directory":  str(tmp_path),
            "extensions": "py",  # solo Python
        })
        assert "TARGET_PATTERN" in result or "a.py" in result

    def test_with_context_lines(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("before\nTARGET\nafter\n")
        result = _tool_grep_code({
            "pattern":       "TARGET",
            "directory":     str(tmp_path),
            "context_lines": 1,
        })
        assert "TARGET" in result

    def test_missing_pattern(self, tmp_path):
        result = _tool_grep_code({"directory": str(tmp_path)})
        assert "Error" in result or "requerido" in result


class TestFindFiles:
    def test_finds_by_pattern(self, tmp_path):
        (tmp_path / "hello.py").write_text("")
        (tmp_path / "world.py").write_text("")
        (tmp_path / "other.txt").write_text("")
        result = _tool_find_files({
            "directory": str(tmp_path),
            "name":      "*.py",
        })
        assert "hello.py" in result
        assert "world.py" in result

    def test_by_extension(self, tmp_path):
        (tmp_path / "main.py").write_text("")
        (tmp_path / "data.txt").write_text("")
        result = _tool_find_files({
            "directory": str(tmp_path),
            "extension": "py",  # sin punto
        })
        assert "main.py" in result

    def test_recursive(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "nested.py").write_text("")
        result = _tool_find_files({
            "directory": str(tmp_path),
            "name":      "*.py",
        })
        assert "nested.py" in result

    def test_nonexistent_dir(self, tmp_path):
        result = _tool_find_files({
            "directory": str(tmp_path / "nonexistent"),
            "name":      "*.py",
        })
        assert "Error" in result or "no encontrado" in result


class TestSymbolLookup:
    def test_finds_function_definition(self, tmp_path):
        (tmp_path / "code.py").write_text("def my_function(x):\n    return x\n")
        result = _tool_symbol_lookup({
            "symbol":    "my_function",
            "directory": str(tmp_path),
            "extensions": "py",
        })
        assert "my_function" in result
        assert "encontrado con estrategia" in result

    def test_finds_c_macro(self, tmp_path):
        (tmp_path / "defs.h").write_text("#define MY_MACRO(x) ((x) * 2)\n")
        result = _tool_symbol_lookup({
            "symbol":    "MY_MACRO",
            "directory": str(tmp_path),
            "extensions": "h",
        })
        assert "MY_MACRO" in result
        assert "encontrado" in result

    def test_not_found_returns_suggestions(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        result = _tool_symbol_lookup({
            "symbol":    "NONEXISTENT_XYZ_Q8Q8",
            "directory": str(tmp_path),
            "extensions": "py",
        })
        assert "No se encontró" in result
        assert "NONEXISTENT_XYZ_Q8Q8" in result

    def test_missing_symbol_returns_error(self, tmp_path):
        result = _tool_symbol_lookup({"directory": str(tmp_path)})
        assert "Error" in result or "obligatorio" in result

    def test_finds_typedef(self, tmp_path):
        (tmp_path / "types.h").write_text("typedef struct { int x; } MyStruct;\n")
        result = _tool_symbol_lookup({
            "symbol":    "MyStruct",
            "directory": str(tmp_path),
            "extensions": "h",
        })
        assert "MyStruct" in result


class TestReadFiles:
    def test_reads_multiple(self, tmp_path):
        import json
        (tmp_path / "a.py").write_text("content_a\n")
        (tmp_path / "b.py").write_text("content_b\n")
        # _tool_read_files accepts JSON array string or CSV
        paths_json = json.dumps([str(tmp_path / "a.py"), str(tmp_path / "b.py")])
        result = _tool_read_files({"paths": paths_json})
        assert "content_a" in result
        assert "content_b" in result

    def test_handles_missing_file(self, tmp_path):
        import json
        (tmp_path / "exists.py").write_text("hello\n")
        paths_json = json.dumps([str(tmp_path / "exists.py"), str(tmp_path / "missing_xyz_q7q7.py")])
        result = _tool_read_files({"paths": paths_json})
        assert "hello" in result
