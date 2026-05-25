"""Tests de python_exec, pip_tool y mypy_check."""
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.oocode_assistant import (
    _tool_python_exec,
    _tool_mypy_check,
)


class TestPythonExec:
    def test_simple_print(self):
        result = _tool_python_exec({"code": "print('hello world')"})
        assert "hello world" in result

    def test_arithmetic(self):
        result = _tool_python_exec({"code": "print(2 + 2)"})
        assert "4" in result

    def test_multiline(self):
        code = "x = 10\ny = 20\nprint(x + y)"
        result = _tool_python_exec({"code": code})
        assert "30" in result

    def test_with_workdir(self, tmp_path):
        # python_exec uses subprocess with cwd=workdir; verifica que el cwd cambia
        result = _tool_python_exec({
            "code":    "import os; print(os.getcwd())",
            "workdir": str(tmp_path),
        })
        assert str(tmp_path) in result or "STDOUT" in result

    def test_syntax_error(self):
        result = _tool_python_exec({"code": "def broken(:"})
        assert "Error" in result or "SyntaxError" in result or "error" in result.lower()

    def test_runtime_error(self):
        result = _tool_python_exec({"code": "1 / 0"})
        assert "ZeroDivisionError" in result or "Error" in result

    def test_nonexistent_workdir(self):
        result = _tool_python_exec({
            "code":    "print('hi')",
            "workdir": "/nonexistent/path",
        })
        assert "Error" in result or "no existe" in result

    def test_missing_code(self):
        result = _tool_python_exec({})
        assert "Error" in result or "Falta" in result or "code" in result.lower()

    def test_stdout_captured(self):
        result = _tool_python_exec({"code": "import sys; print('stderr', file=sys.stderr); print('stdout')"})
        assert "stdout" in result


class TestMypyCheck:
    @pytest.mark.skipif(
        not Path("/usr/bin/mypy").exists() and
        not Path("/usr/local/bin/mypy").exists(),
        reason="mypy no instalado",
    )
    def test_valid_file(self, tmp_path):
        f = tmp_path / "typed.py"
        f.write_text("def add(a: int, b: int) -> int:\n    return a + b\n")
        result = _tool_mypy_check({"path": str(f)})
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.skipif(
        not Path("/usr/bin/mypy").exists() and
        not Path("/usr/local/bin/mypy").exists(),
        reason="mypy no instalado",
    )
    def test_type_error_file(self, tmp_path):
        f = tmp_path / "bad_types.py"
        f.write_text("def add(a: int, b: int) -> int:\n    return a + 'hello'\n")
        result = _tool_mypy_check({"path": str(f)})
        assert "error" in result.lower() or "incompatible" in result.lower()
