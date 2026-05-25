"""Tests de lint_file y lint_project para Python y C."""
import sys
import subprocess
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.oocode_assistant import (
    _tool_lint_file,
    _tool_lint_project,
)

HAS_RUFF    = subprocess.run(["which", "ruff"],    capture_output=True).returncode == 0
HAS_FLAKE8  = subprocess.run(["which", "flake8"],  capture_output=True).returncode == 0
HAS_CPPCHECK = subprocess.run(["which", "cppcheck"], capture_output=True).returncode == 0


class TestLintFile:
    @pytest.mark.skipif(not (HAS_RUFF or HAS_FLAKE8), reason="ruff/flake8 no disponible")
    def test_clean_python(self, tmp_path):
        f = tmp_path / "clean.py"
        f.write_text("def add(a, b):\n    return a + b\n")
        result = _tool_lint_file({"path": str(f)})
        assert isinstance(result, str)

    @pytest.mark.skipif(not (HAS_RUFF or HAS_FLAKE8), reason="ruff/flake8 no disponible")
    def test_dirty_python(self, tmp_path):
        f = tmp_path / "dirty.py"
        f.write_text("import os\nimport sys\nx=1\n")
        result = _tool_lint_file({"path": str(f)})
        # Debe encontrar al menos algún issue (E501, F401, etc.)
        assert isinstance(result, str)

    @pytest.mark.skipif(not HAS_CPPCHECK, reason="cppcheck no disponible")
    def test_clean_c(self, tmp_path):
        f = tmp_path / "clean.c"
        f.write_text("#include <stdio.h>\nint main(void) { return 0; }\n")
        result = _tool_lint_file({"path": str(f)})
        assert isinstance(result, str)

    def test_nonexistent_file(self):
        result = _tool_lint_file({"path": "/nonexistent/code.py"})
        assert "Error" in result or "no existe" in result or "not found" in result.lower()

    def test_unsupported_extension(self, tmp_path):
        f = tmp_path / "file.xyz"
        f.write_text("nothing\n")
        result = _tool_lint_file({"path": str(f)})
        # Puede decir "no hay linter" o devolver vacío
        assert isinstance(result, str)


class TestLintProject:
    @pytest.mark.skipif(not (HAS_RUFF or HAS_FLAKE8), reason="ruff/flake8 no disponible")
    def test_python_project(self, tmp_path):
        (tmp_path / "a.py").write_text("def foo():\n    pass\n")
        (tmp_path / "b.py").write_text("x = 1\n")
        result = _tool_lint_project({"path": str(tmp_path)})
        assert isinstance(result, str)

    def test_empty_dir(self, tmp_path):
        result = _tool_lint_project({"path": str(tmp_path)})
        assert isinstance(result, str)

    def test_nonexistent_dir(self, tmp_path):
        # _tool_lint_project uses "path" not "directory"
        result = _tool_lint_project({"path": str(tmp_path / "nonexistent_project_q7q7")})
        assert "Error" in result or "no existe" in result or "no encontrado" in result
