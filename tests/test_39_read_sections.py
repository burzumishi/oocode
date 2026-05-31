"""Tests for read_sections tool."""
import textwrap
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from mcp_servers.oocode_assistant import (
    _tool_read_sections,
    _read_sections_python,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _py(tmp_path, content: str):
    p = tmp_path / "sample.py"
    p.write_text(textwrap.dedent(content))
    return p


# ---------------------------------------------------------------------------
# _read_sections_python — core extraction
# ---------------------------------------------------------------------------

class TestReadSectionsPython:
    def test_extracts_function(self, tmp_path):
        p = _py(tmp_path, '''\
            def greet():
                return "hello"

            def goodbye():
                return "bye"
        ''')
        out = _read_sections_python(str(p), p.read_text(), ["greet"])
        assert "def greet" in out
        assert "hello" in out
        assert "def goodbye" not in out

    def test_extracts_class(self, tmp_path):
        p = _py(tmp_path, '''\
            class Foo:
                pass

            class Bar:
                pass
        ''')
        out = _read_sections_python(str(p), p.read_text(), ["Foo"])
        assert "class Foo" in out
        assert "class Bar" not in out

    def test_extracts_method_qualified(self, tmp_path):
        p = _py(tmp_path, '''\
            class Agent:
                def run(self):
                    return 42

                def stop(self):
                    return 0
        ''')
        out = _read_sections_python(str(p), p.read_text(), ["Agent.run"])
        assert "def run" in out
        assert "return 42" in out
        assert "def stop" not in out

    def test_extracts_method_unqualified(self, tmp_path):
        p = _py(tmp_path, '''\
            class Agent:
                def run(self):
                    return 42
        ''')
        out = _read_sections_python(str(p), p.read_text(), ["run"])
        assert "def run" in out
        assert "return 42" in out

    def test_extracts_multiple_sections(self, tmp_path):
        p = _py(tmp_path, '''\
            def alpha():
                return 1

            def beta():
                return 2

            def gamma():
                return 3
        ''')
        out = _read_sections_python(str(p), p.read_text(), ["alpha", "gamma"])
        assert "def alpha" in out
        assert "def gamma" in out
        assert "def beta" not in out

    def test_missing_section_reported(self, tmp_path):
        p = _py(tmp_path, '''\
            def existing():
                pass
        ''')
        out = _read_sections_python(str(p), p.read_text(), ["nonexistent"])
        assert "nonexistent" in out
        assert "No encontrado" in out or "No se encontraron" in out

    def test_partial_found_partial_not_found(self, tmp_path):
        p = _py(tmp_path, '''\
            def found():
                return True
        ''')
        out = _read_sections_python(str(p), p.read_text(), ["found", "missing"])
        assert "def found" in out
        assert "missing" in out

    def test_includes_decorators(self, tmp_path):
        p = _py(tmp_path, '''\
            import functools

            @functools.lru_cache(maxsize=None)
            def cached():
                return 99
        ''')
        out = _read_sections_python(str(p), p.read_text(), ["cached"])
        assert "@functools.lru_cache" in out
        assert "def cached" in out

    def test_header_shows_line_range(self, tmp_path):
        p = _py(tmp_path, '''\
            def simple():
                pass
        ''')
        out = _read_sections_python(str(p), p.read_text(), ["simple"])
        assert "sample.py:" in out
        assert "–" in out  # range separator

    def test_async_function(self, tmp_path):
        p = _py(tmp_path, '''\
            async def fetch():
                return await something()
        ''')
        out = _read_sections_python(str(p), p.read_text(), ["fetch"])
        assert "async def fetch" in out

    def test_syntax_error_returns_error_msg(self, tmp_path):
        p = tmp_path / "bad.py"
        p.write_text("def broken(:\n    pass\n")
        out = _read_sections_python(str(p), p.read_text(), ["broken"])
        assert "SyntaxError" in out

    def test_nested_class_method(self, tmp_path):
        p = _py(tmp_path, '''\
            class Outer:
                class Inner:
                    def method(self):
                        return "inner"
        ''')
        out = _read_sections_python(str(p), p.read_text(), ["Inner.method"])
        assert "def method" in out
        assert "inner" in out


# ---------------------------------------------------------------------------
# _tool_read_sections dispatcher
# ---------------------------------------------------------------------------

class TestToolReadSections:
    def test_basic_python(self, tmp_path):
        p = _py(tmp_path, '''\
            def hello():
                return "world"
        ''')
        result = _tool_read_sections({"path": str(p), "sections": ["hello"]})
        assert "def hello" in result
        assert "world" in result

    def test_missing_path_error(self):
        result = _tool_read_sections({"sections": ["foo"]})
        assert "Error" in result
        assert "path" in result

    def test_missing_sections_error(self, tmp_path):
        p = _py(tmp_path, "def f(): pass\n")
        result = _tool_read_sections({"path": str(p)})
        assert "Error" in result
        assert "sections" in result

    def test_nonexistent_file(self, tmp_path):
        result = _tool_read_sections({"path": str(tmp_path / "ghost.py"), "sections": ["f"]})
        assert "Error" in result
        assert "no encontrado" in result.lower() or "Error" in result

    def test_directory_error(self, tmp_path):
        result = _tool_read_sections({"path": str(tmp_path), "sections": ["f"]})
        assert "directorio" in result or "Error" in result

    def test_sections_as_string_csv(self, tmp_path):
        p = _py(tmp_path, '''\
            def alpha():
                return 1

            def beta():
                return 2
        ''')
        result = _tool_read_sections({"path": str(p), "sections": "alpha,beta"})
        assert "def alpha" in result
        assert "def beta" in result

    def test_qualified_method(self, tmp_path):
        p = _py(tmp_path, '''\
            class Loop:
                def run(self):
                    return "running"
        ''')
        result = _tool_read_sections({"path": str(p), "sections": ["Loop.run"]})
        assert "running" in result

    def test_class_extraction(self, tmp_path):
        p = _py(tmp_path, '''\
            class Engine:
                def start(self):
                    pass
                def stop(self):
                    pass
        ''')
        result = _tool_read_sections({"path": str(p), "sections": ["Engine"]})
        assert "class Engine" in result
        assert "def start" in result
        assert "def stop" in result


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class TestReadSectionsSchema:
    def test_schema_exists(self):
        from mcp_servers.oocode_assistant import _TOOLS
        schema = next((t for t in _TOOLS if t["name"] == "read_sections"), None)
        assert schema is not None

    def test_schema_required_fields(self):
        from mcp_servers.oocode_assistant import _TOOLS
        schema = next(t for t in _TOOLS if t["name"] == "read_sections")
        required = schema["inputSchema"]["required"]
        assert "path" in required
        assert "sections" in required

    def test_schema_sections_is_array(self):
        from mcp_servers.oocode_assistant import _TOOLS
        schema = next(t for t in _TOOLS if t["name"] == "read_sections")
        props = schema["inputSchema"]["properties"]
        assert props["sections"]["type"] == "array"
        assert props["sections"]["items"]["type"] == "string"

    def test_native_wrapper_in_oocode_source(self):
        import inspect
        import oocode
        src = inspect.getsource(oocode)
        assert "read_sections" in src
        assert "_mcp_read_sections" in src

    def test_permission_in_default_config(self):
        from config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["permissions"].get("read_sections") == "auto"
