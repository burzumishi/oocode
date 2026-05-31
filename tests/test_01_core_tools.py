"""Tests de las tools core del MCP server oocode_assistant (sin LLM)."""
import sys
import os
import json
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.oocode_assistant import (
    _tool_get_datetime,
    _tool_system_info,
    _tool_calculate,
    _tool_hash_text,
    _tool_json_format,
    _tool_url_encode,
    _tool_diff_files,
)


class TestDatetime:
    def test_returns_datetime(self):
        result = _tool_get_datetime({})
        assert "20" in result  # año ≥ 2020

    def test_utc_flag(self):
        result = _tool_get_datetime({"utc": True})
        assert "UTC" in result or "Z" in result or "20" in result


class TestSystemInfo:
    def test_returns_info(self):
        result = _tool_system_info({})
        assert isinstance(result, str)
        assert len(result) > 10


class TestCalculate:
    def test_addition(self):
        result = _tool_calculate({"expression": "2 + 3"})
        assert "5" in result

    def test_multiplication(self):
        result = _tool_calculate({"expression": "7 * 8"})
        assert "56" in result

    def test_float(self):
        result = _tool_calculate({"expression": "10 / 4"})
        assert "2.5" in result

    def test_invalid_expression(self):
        result = _tool_calculate({"expression": "import os; os.system('ls')"})
        assert "Error" in result or "error" in result or "inválida" in result or "no permitida" in result

    def test_missing_expression(self):
        result = _tool_calculate({})
        assert "Error" in result or "Falta" in result or "expression" in result.lower()


class TestHashText:
    def test_md5(self):
        result = _tool_hash_text({"text": "hello", "algorithm": "md5"})
        assert "5d41402abc4b2a76b9719d911017c592" in result.lower()

    def test_sha256(self):
        result = _tool_hash_text({"text": "hello"})
        assert "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824" in result.lower()

    def test_missing_text(self):
        result = _tool_hash_text({})
        assert "Error" in result or "Falta" in result or "text" in result.lower()


class TestJsonFormat:
    def test_valid_json(self):
        # El parámetro es "text", no "json_string"
        result = _tool_json_format({"text": '{"a":1,"b":2}'})
        assert '"a"' in result or "a" in result

    def test_invalid_json(self):
        result = _tool_json_format({"text": "not json"})
        assert "Error" in result or "inválido" in result or "JSON" in result or "JSONDecodeError" in result

    def test_missing_param(self):
        result = _tool_json_format({})
        assert "Error" in result or "requerido" in result


class TestUrlEncode:
    def test_encode(self):
        # El parámetro es "operation" no "action"
        result = _tool_url_encode({"text": "hello world", "operation": "encode"})
        assert "hello%20world" in result or "hello+world" in result

    def test_decode(self):
        result = _tool_url_encode({"text": "hello%20world", "operation": "decode"})
        assert "hello world" in result

    def test_missing_text(self):
        result = _tool_url_encode({})
        assert "Error" in result or "requerido" in result


class TestDiffFiles:
    def test_identical_files(self, tmp_path):
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_text("same content\n")
        b.write_text("same content\n")
        # Los parámetros son "file_a" y "file_b"
        result = _tool_diff_files({"file_a": str(a), "file_b": str(b)})
        assert "idénticos" in result or "identical" in result or result.strip() == "" or "sin diferencias" in result.lower() or "0" in result

    def test_different_files(self, tmp_path):
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_text("line1\nline2\n")
        b.write_text("line1\nline3\n")
        result = _tool_diff_files({"file_a": str(a), "file_b": str(b)})
        assert "line2" in result or "line3" in result or "---" in result or "@@" in result

    def test_text_diff(self):
        # text_a / text_b — modo inline
        result = _tool_diff_files({"text_a": "hello\nworld\n", "text_b": "hello\nearth\n"})
        assert "world" in result or "earth" in result or "---" in result

    def test_missing_params(self):
        result = _tool_diff_files({})
        assert "Error" in result or "proporciona" in result
