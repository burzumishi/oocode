"""Tests for code_outline with_docstrings parameter."""
import textwrap
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from mcp_servers.oocode_assistant import (
    _tool_code_outline,
    _outline_python,
    _docstring_first_line,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_py(tmp_path, content: str):
    p = tmp_path / "sample.py"
    p.write_text(textwrap.dedent(content))
    return p


# ---------------------------------------------------------------------------
# _docstring_first_line
# ---------------------------------------------------------------------------

class TestDocstringFirstLine:
    def test_simple_string(self):
        import ast
        src = '"""Hace algo útil."""\ndef f(): pass'
        tree = ast.parse(src)
        # create a FunctionDef with a docstring for test
        func_src = 'def f():\n    """Primera línea.\n\n    Más detalles.\n    """\n    pass'
        node = ast.parse(func_src).body[0]
        result = _docstring_first_line(node)
        assert result == "Primera línea."

    def test_multiline_returns_first_nonempty(self):
        import ast
        src = 'def f():\n    """\n    Esto es la primera.\n    Y segunda.\n    """\n    pass'
        node = ast.parse(src).body[0]
        result = _docstring_first_line(node)
        assert result == "Esto es la primera."

    def test_no_docstring_returns_empty(self):
        import ast
        src = "def f():\n    pass"
        node = ast.parse(src).body[0]
        result = _docstring_first_line(node)
        assert result == ""

    def test_truncates_at_90_chars(self):
        import ast
        long_doc = "X" * 200
        src = f'def f():\n    """{long_doc}"""\n    pass'
        node = ast.parse(src).body[0]
        result = _docstring_first_line(node)
        assert len(result) == 90

    def test_class_docstring(self):
        import ast
        src = 'class Foo:\n    """Clase para cosas."""\n    pass'
        node = ast.parse(src).body[0]
        result = _docstring_first_line(node)
        assert result == "Clase para cosas."


# ---------------------------------------------------------------------------
# _outline_python with_docstrings=True
# ---------------------------------------------------------------------------

class TestOutlinePythonWithDocstrings:
    def test_function_docstring_shown(self, tmp_path):
        p = _write_py(tmp_path, '''\
            def greet():
                """Saluda al usuario."""
                pass
        ''')
        text = p.read_text()
        out = _outline_python(str(p), text, len(text.splitlines()), with_docstrings=True)
        assert "Saluda al usuario." in out

    def test_function_no_docstring_no_suffix(self, tmp_path):
        p = _write_py(tmp_path, '''\
            def greet():
                pass
        ''')
        text = p.read_text()
        out = _outline_python(str(p), text, len(text.splitlines()), with_docstrings=True)
        assert "greet" in out
        assert " — " not in out

    def test_class_docstring_shown(self, tmp_path):
        p = _write_py(tmp_path, '''\
            class Agent:
                """Motor principal del agente."""
                def run(self):
                    """Ejecuta el loop principal."""
                    pass
        ''')
        text = p.read_text()
        out = _outline_python(str(p), text, len(text.splitlines()), with_docstrings=True)
        assert "Motor principal del agente." in out
        assert "Ejecuta el loop principal." in out

    def test_without_docstrings_no_suffix(self, tmp_path):
        p = _write_py(tmp_path, '''\
            def greet():
                """Saluda al usuario."""
                pass
        ''')
        text = p.read_text()
        out = _outline_python(str(p), text, len(text.splitlines()), with_docstrings=False)
        assert "Saluda al usuario." not in out
        assert " — " not in out

    def test_multiline_docstring_only_first_line(self, tmp_path):
        p = _write_py(tmp_path, '''\
            def process():
                """Primera línea del doc.

                Esta segunda línea no debe aparecer.
                """
                pass
        ''')
        text = p.read_text()
        out = _outline_python(str(p), text, len(text.splitlines()), with_docstrings=True)
        assert "Primera línea del doc." in out
        assert "segunda línea no debe aparecer" not in out

    def test_dash_separator_format(self, tmp_path):
        p = _write_py(tmp_path, '''\
            def compute():
                """Calcula el resultado."""
                pass
        ''')
        text = p.read_text()
        out = _outline_python(str(p), text, len(text.splitlines()), with_docstrings=True)
        assert "  — Calcula el resultado." in out

    def test_method_docstring_shown(self, tmp_path):
        p = _write_py(tmp_path, '''\
            class Foo:
                def bar(self):
                    """Método bar hace cosas."""
                    pass
        ''')
        text = p.read_text()
        out = _outline_python(str(p), text, len(text.splitlines()), with_docstrings=True)
        assert "Método bar hace cosas." in out

    def test_static_method_docstring(self, tmp_path):
        p = _write_py(tmp_path, '''\
            class Foo:
                @staticmethod
                def helper():
                    """Función de ayuda estática."""
                    pass
        ''')
        text = p.read_text()
        out = _outline_python(str(p), text, len(text.splitlines()), with_docstrings=True)
        assert "Función de ayuda estática." in out


# ---------------------------------------------------------------------------
# _tool_code_outline wires with_docstrings
# ---------------------------------------------------------------------------

class TestToolCodeOutlineWithDocstrings:
    def test_with_docstrings_false_default(self, tmp_path):
        p = _write_py(tmp_path, '''\
            def greet():
                """Saluda."""
                pass
        ''')
        result = _tool_code_outline({"path": str(p)})
        assert "Saluda." not in result

    def test_with_docstrings_true(self, tmp_path):
        p = _write_py(tmp_path, '''\
            def greet():
                """Saluda."""
                pass
        ''')
        result = _tool_code_outline({"path": str(p), "with_docstrings": True})
        assert "Saluda." in result

    def test_with_docstrings_false_explicit(self, tmp_path):
        p = _write_py(tmp_path, '''\
            def greet():
                """Saluda."""
                pass
        ''')
        result = _tool_code_outline({"path": str(p), "with_docstrings": False})
        assert "Saluda." not in result

    def test_with_docstrings_nonpy_ignored(self, tmp_path):
        p = tmp_path / "sample.js"
        p.write_text("function greet() { /** @doc */ }")
        result = _tool_code_outline({"path": str(p), "with_docstrings": True})
        # Should not error — ctags path, just check no crash
        assert isinstance(result, str)

    def test_with_docstrings_class_and_method(self, tmp_path):
        p = _write_py(tmp_path, '''\
            class Router:
                """Enruta peticiones HTTP."""
                def dispatch(self):
                    """Despacha la petición al handler."""
                    pass
        ''')
        result = _tool_code_outline({"path": str(p), "with_docstrings": True})
        assert "Enruta peticiones HTTP." in result
        assert "Despacha la petición al handler." in result

    def test_with_docstrings_min_lines_respected(self, tmp_path):
        p = _write_py(tmp_path, '''\
            def f():
                """Pequeño."""
                pass
        ''')
        result = _tool_code_outline({"path": str(p), "with_docstrings": True, "min_lines": 9999})
        assert "Pequeño." not in result
        assert "read_file" in result


# ---------------------------------------------------------------------------
# Schema includes with_docstrings
# ---------------------------------------------------------------------------

class TestCodeOutlineSchema:
    def test_schema_has_with_docstrings_property(self):
        from mcp_servers.oocode_assistant import _TOOLS
        schema = next(t for t in _TOOLS if t["name"] == "code_outline")
        props = schema["inputSchema"]["properties"]
        assert "with_docstrings" in props

    def test_schema_with_docstrings_is_boolean(self):
        from mcp_servers.oocode_assistant import _TOOLS
        schema = next(t for t in _TOOLS if t["name"] == "code_outline")
        wd = schema["inputSchema"]["properties"]["with_docstrings"]
        assert wd["type"] == "boolean"

    def test_native_wrapper_accepts_with_docstrings(self, tmp_path):
        """The native oocode.py code_outline wrapper passes with_docstrings."""
        import inspect
        import oocode as _oo
        # We check that code_outline() accepts with_docstrings by calling it directly
        # The wrapper is defined inside build_registry; but we can verify via the source
        src = inspect.getsource(_oo)
        # Verify the wrapper definition includes with_docstrings
        assert "with_docstrings: bool = False" in src or 'with_docstrings=False' in src
        # Verify the schema also lists with_docstrings
        assert '"with_docstrings"' in src
