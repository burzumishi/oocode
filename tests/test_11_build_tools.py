"""Tests de tools de build: make_run, run_script, format_code."""
import sys
import subprocess
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.oocode_assistant import (
    _tool_make_run,
    _tool_run_script,
    _tool_format_code,
)

HAS_MAKE    = subprocess.run(["which", "make"],   capture_output=True).returncode == 0
HAS_BLACK   = subprocess.run(["which", "black"],  capture_output=True).returncode == 0
HAS_RUFF    = subprocess.run(["which", "ruff"],   capture_output=True).returncode == 0


class TestMakeRun:
    @pytest.mark.skipif(not HAS_MAKE, reason="make no disponible")
    def test_simple_makefile(self, tmp_path):
        (tmp_path / "Makefile").write_text("all:\n\techo BUILD_OK\n")
        result = _tool_make_run({
            "directory": str(tmp_path),
            "target":    "all",
        })
        assert "BUILD_OK" in result

    @pytest.mark.skipif(not HAS_MAKE, reason="make no disponible")
    def test_nonexistent_target(self, tmp_path):
        (tmp_path / "Makefile").write_text("all:\n\techo ok\n")
        result = _tool_make_run({
            "directory": str(tmp_path),
            "target":    "nonexistent_target_xyz",
        })
        assert "Error" in result or "No rule" in result or "error" in result.lower()


class TestRunScript:
    def test_python_script(self, tmp_path):
        script = tmp_path / "myscript.py"
        script.write_text("print('SCRIPT_OUTPUT')\n")
        # run_script uses "script" not "path"
        result = _tool_run_script({
            "script": str(script),
        })
        assert "SCRIPT_OUTPUT" in result

    def test_bash_script(self, tmp_path):
        script = tmp_path / "myscript.sh"
        script.write_text("#!/bin/bash\necho BASH_OUTPUT\n")
        script.chmod(0o755)
        result = _tool_run_script({
            "script": str(script),
        })
        assert "BASH_OUTPUT" in result

    def test_nonexistent_script(self, tmp_path):
        result = _tool_run_script({"script": str(tmp_path / "nonexistent.py")})
        assert "Error" in result or "no existe" in result


class TestFormatCode:
    @pytest.mark.skipif(not (HAS_BLACK or HAS_RUFF), reason="black/ruff no disponible")
    def test_formats_python(self, tmp_path):
        f = tmp_path / "unformatted.py"
        f.write_text("x=1\ny=2\nz = x+y\n")
        result = _tool_format_code({"path": str(f)})
        assert isinstance(result, str)

    def test_nonexistent_file(self):
        result = _tool_format_code({"path": "/nonexistent/file.py"})
        assert "Error" in result or "no existe" in result
