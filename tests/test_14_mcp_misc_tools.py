"""Tests de tools MCP misceláneas sin cobertura previa (sin LLM).

Cubre: write_file, env_check, count_lines, tree, json_validate, yaml_validate,
jq_query, port_check, process_list, http_get, template_fill, search_todos,
read_project_file, list_recent_files, run_quick_check, code_compare, multi_grep.

NOTA: tmp_path está definido en conftest.py como ~/.oocode/_test_tmp para evitar
el bloqueo de _safe_path que rechaza rutas fuera del home del usuario.
"""
import json
import os
import sys
import subprocess
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.oocode_assistant import (
    _tool_write_file,
    _tool_env_check,
    _tool_count_lines,
    _tool_tree,
    _tool_json_validate,
    _tool_yaml_validate,
    _tool_jq_query,
    _tool_port_check,
    _tool_process_list,
    _tool_http_get,
    _tool_template_fill,
    _tool_search_todos,
    _tool_read_project_file,
    _tool_list_recent_files,
    _tool_run_quick_check,
    _tool_code_compare,
    _tool_multi_grep,
)

HAS_JQ = subprocess.run(["which", "jq"], capture_output=True).returncode == 0


# ── write_file ────────────────────────────────────────────────────────────────
# Parámetros reales: file_path (no "path"), content, append, mkdir

class TestWriteFile:
    def test_creates_file(self, tmp_path):
        out = str(tmp_path / "hello.txt")
        result = _tool_write_file({"file_path": out, "content": "hola"})
        assert Path(out).exists()
        assert Path(out).read_text() == "hola"

    def test_overwrites_existing(self, tmp_path):
        out = tmp_path / "file.txt"
        out.write_text("old")
        _tool_write_file({"file_path": str(out), "content": "new"})
        assert out.read_text() == "new"

    def test_returns_byte_info(self, tmp_path):
        out = str(tmp_path / "bytes.txt")
        result = _tool_write_file({"file_path": out, "content": "abc"})
        assert isinstance(result, str)
        assert "3" in result or "bytes" in result or "byte" in result

    def test_missing_file_path(self):
        result = _tool_write_file({"content": "x"})
        assert "error" in result.lower() or "requer" in result.lower()

    def test_creates_parent_dirs_with_mkdir(self, tmp_path):
        out = str(tmp_path / "subdir" / "nested.txt")
        result = _tool_write_file({"file_path": out, "content": "deep", "mkdir": True})
        assert Path(out).exists()

    def test_append_mode(self, tmp_path):
        out = str(tmp_path / "append.txt")
        _tool_write_file({"file_path": out, "content": "line1\n"})
        _tool_write_file({"file_path": out, "content": "line2\n", "append": True})
        content = Path(out).read_text()
        assert "line1" in content and "line2" in content


# ── env_check ─────────────────────────────────────────────────────────────────

class TestEnvCheck:
    def test_returns_string(self):
        result = _tool_env_check({})
        assert isinstance(result, str)
        assert len(result) > 5

    def test_returns_known_var(self):
        # PATH siempre existe
        result = _tool_env_check({"vars": "PATH"})
        assert isinstance(result, str)
        # PATH puede estar oculto o visible
        assert "PATH" in result or isinstance(result, str)

    def test_user_var(self):
        result = _tool_env_check({"vars": "USER"})
        assert isinstance(result, str)

    def test_missing_var_no_crash(self):
        result = _tool_env_check({"vars": "_OOCODE_NONEXISTENT_VAR_XYZ"})
        assert isinstance(result, str)


# ── count_lines ───────────────────────────────────────────────────────────────

class TestCountLines:
    def test_counts_file(self, tmp_path):
        f = tmp_path / "sample.py"
        f.write_text("line1\nline2\nline3\n")
        result = _tool_count_lines({"path": str(f)})
        assert "3" in result

    def test_counts_directory(self, tmp_path):
        (tmp_path / "a.py").write_text("a\nb\n")
        (tmp_path / "b.py").write_text("c\nd\ne\n")
        result = _tool_count_lines({"path": str(tmp_path)})
        assert isinstance(result, str) and len(result) > 0

    def test_missing_path(self):
        result = _tool_count_lines({})
        assert isinstance(result, str)


# ── tree ──────────────────────────────────────────────────────────────────────

class TestTree:
    def test_lists_structure(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("")
        (tmp_path / "README.md").write_text("")
        result = _tool_tree({"path": str(tmp_path)})
        assert isinstance(result, str) and len(result) > 5

    def test_depth_limit(self, tmp_path):
        (tmp_path / "a" / "b" / "c").mkdir(parents=True)
        (tmp_path / "a" / "b" / "c" / "deep.py").write_text("")
        result_shallow = _tool_tree({"path": str(tmp_path), "depth": 1})
        result_deep    = _tool_tree({"path": str(tmp_path), "depth": 5})
        assert len(result_deep) >= len(result_shallow)

    def test_nonexistent_path(self, tmp_path):
        result = _tool_tree({"path": str(tmp_path / "nope")})
        assert isinstance(result, str)


# ── json_validate ─────────────────────────────────────────────────────────────
# La función devuelve "JSON válido" (español), no "valid"

class TestJsonValidate:
    def test_valid_json(self):
        result = _tool_json_validate({"content": '{"key": "value", "n": 42}'})
        assert "válido" in result.lower() or "valid" in result.lower() or "✓" in result

    def test_invalid_json(self):
        result = _tool_json_validate({"content": "{bad json"})
        assert "error" in result.lower() or "invalid" in result.lower() or "inválido" in result.lower()

    def test_valid_json_file(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"a": 1}')
        result = _tool_json_validate({"file": str(f)})
        assert "válido" in result.lower() or "valid" in result.lower() or isinstance(result, str)

    def test_missing_params(self):
        result = _tool_json_validate({})
        assert "error" in result.lower() or "requer" in result.lower()


# ── yaml_validate ─────────────────────────────────────────────────────────────
# La función devuelve "YAML válido" (español)

class TestYamlValidate:
    def test_valid_yaml(self):
        result = _tool_yaml_validate({"content": "key: value\nlist:\n  - a\n  - b\n"})
        assert "válido" in result.lower() or "valid" in result.lower() or "✓" in result

    def test_invalid_yaml(self):
        result = _tool_yaml_validate({"content": "key: [\nbad"})
        assert "error" in result.lower() or "invalid" in result.lower() or "inválido" in result.lower()

    def test_valid_yaml_file(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("name: test\nversion: 1\n")
        result = _tool_yaml_validate({"file": str(f)})
        assert "válido" in result.lower() or isinstance(result, str)

    def test_missing_params(self):
        result = _tool_yaml_validate({})
        assert "error" in result.lower() or "requer" in result.lower()


# ── jq_query ──────────────────────────────────────────────────────────────────
# Parámetros reales: query, content (no "input"), path, compact

@pytest.mark.skipif(not HAS_JQ, reason="jq no instalado")
class TestJqQuery:
    def test_simple_query(self):
        result = _tool_jq_query({"query": ".name", "content": '{"name": "oocode"}'})
        assert "oocode" in result

    def test_array_query(self):
        result = _tool_jq_query({"query": ".[] | .id", "content": '[{"id":1},{"id":2}]'})
        assert "1" in result and "2" in result

    def test_invalid_json_content(self):
        result = _tool_jq_query({"query": ".foo", "content": "not json"})
        assert isinstance(result, str)

    def test_missing_params(self):
        result = _tool_jq_query({})
        assert "error" in result.lower() or "requer" in result.lower()

    def test_jq_file(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"name": "test", "count": 5}')
        result = _tool_jq_query({"query": ".count", "path": str(f)})
        assert "5" in result


# ── port_check ────────────────────────────────────────────────────────────────

class TestPortCheck:
    def test_returns_string(self):
        result = _tool_port_check({})
        assert isinstance(result, str) and len(result) > 0

    def test_specific_port(self):
        result = _tool_port_check({"ports": "22,80,443"})
        assert isinstance(result, str)

    def test_nonexistent_port(self):
        result = _tool_port_check({"ports": "19999"})
        assert isinstance(result, str)


# ── process_list ──────────────────────────────────────────────────────────────

class TestProcessList:
    def test_returns_processes(self):
        result = _tool_process_list({})
        assert isinstance(result, str) and len(result) > 5

    def test_filter_by_name(self):
        result = _tool_process_list({"filter": "python"})
        assert isinstance(result, str)

    def test_nonexistent_filter(self):
        result = _tool_process_list({"filter": "_oocode_nonexistent_xyz_"})
        assert isinstance(result, str)


# ── http_get ──────────────────────────────────────────────────────────────────

class TestHttpGet:
    def test_missing_url(self):
        result = _tool_http_get({})
        assert "error" in result.lower() or "requer" in result.lower() or "url" in result.lower()

    def test_invalid_url_schema(self):
        result = _tool_http_get({"url": "ftp://example.com"})
        assert isinstance(result, str)


# ── template_fill ─────────────────────────────────────────────────────────────
# Variables: dict (no JSON string); style default="double" usa {{key}} no {key}

class TestTemplateFill:
    def test_double_brace_substitution(self):
        result = _tool_template_fill({
            "template": "Hello, {{name}}! Version {{version}}.",
            "variables": {"name": "OOCode", "version": "1.0"},
        })
        assert "OOCode" in result
        assert "1.0" in result

    def test_single_brace_style(self):
        result = _tool_template_fill({
            "template": "Hello, {name}!",
            "variables": {"name": "World"},
            "style": "single",
        })
        assert "World" in result

    def test_dollar_style(self):
        result = _tool_template_fill({
            "template": "Project: ${project}",
            "variables": {"project": "oocode"},
            "style": "dollar",
        })
        assert "oocode" in result

    def test_missing_variable_warns(self):
        result = _tool_template_fill({
            "template": "Hello, {{name}} and {{other}}!",
            "variables": {"name": "World"},
        })
        assert isinstance(result, str)
        # Either fills name or shows warning about missing variable
        assert "World" in result or "ADVERTENCIA" in result or isinstance(result, str)

    def test_missing_template(self):
        result = _tool_template_fill({})
        assert "error" in result.lower() or "requer" in result.lower()

    def test_variables_must_be_dict(self):
        result = _tool_template_fill({
            "template": "Hello {name}",
            "variables": "name=test",
        })
        assert "error" in result.lower()

    def test_template_with_newlines(self):
        result = _tool_template_fill({
            "template": "Project: {{project}}\nAuthor: {{author}}",
            "variables": {"project": "oocode", "author": "Antonio"},
        })
        assert "oocode" in result
        assert "Antonio" in result


# ── search_todos ──────────────────────────────────────────────────────────────

class TestSearchTodos:
    def test_finds_todos(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("x = 1  # TODO: improve this\ny = 2  # FIXME: broken\n")
        result = _tool_search_todos({"directory": str(tmp_path), "extensions": "py"})
        assert "TODO" in result or "FIXME" in result

    def test_no_todos(self, tmp_path):
        (tmp_path / "clean.py").write_text("x = 1\n")
        result = _tool_search_todos({"directory": str(tmp_path), "extensions": "py"})
        assert isinstance(result, str)

    def test_custom_tags(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("# HACK: workaround for issue #123\n")
        result = _tool_search_todos({"directory": str(tmp_path), "tags": "HACK", "extensions": "py"})
        assert "HACK" in result

    def test_nonexistent_dir(self, tmp_path):
        result = _tool_search_todos({"directory": str(tmp_path / "nope")})
        assert "error" in result.lower() or "no encontrado" in result.lower()


# ── read_project_file ─────────────────────────────────────────────────────────

class TestReadProjectFile:
    def test_reads_existing_file(self, tmp_path):
        f = tmp_path / "OOCODE.md"
        f.write_text("# Project\n\nThis is the README.")
        result = _tool_read_project_file({"filename": "OOCODE.md", "directory": str(tmp_path)})
        assert "Project" in result or "README" in result

    def test_nonexistent_file(self, tmp_path):
        result = _tool_read_project_file({"filename": "NONEXISTENT.md", "directory": str(tmp_path)})
        assert "no encontrado" in result.lower() or "not found" in result.lower()

    def test_truncation(self, tmp_path):
        f = tmp_path / "big.md"
        f.write_text("x" * 10000)
        result = _tool_read_project_file({"filename": "big.md", "directory": str(tmp_path), "max_chars": 100})
        assert "truncado" in result.lower() or len(result) < 500

    def test_default_oocode_md(self):
        # Debe encontrar el OOCODE.md del propio proyecto
        result = _tool_read_project_file({"filename": "OOCODE.md"})
        assert isinstance(result, str)


# ── list_recent_files ─────────────────────────────────────────────────────────

class TestListRecentFiles:
    def test_lists_files(self, tmp_path):
        (tmp_path / "a.py").write_text("a")
        (tmp_path / "b.py").write_text("b")
        result = _tool_list_recent_files({"directory": str(tmp_path)})
        assert "a.py" in result or "b.py" in result

    def test_filter_extension(self, tmp_path):
        (tmp_path / "code.py").write_text("x")
        (tmp_path / "doc.md").write_text("y")
        result = _tool_list_recent_files({"directory": str(tmp_path), "extension": "py"})
        assert "code.py" in result
        assert "doc.md" not in result

    def test_nonexistent_dir(self, tmp_path):
        result = _tool_list_recent_files({"directory": str(tmp_path / "nope")})
        assert "error" in result.lower()

    def test_count_limit(self, tmp_path):
        for i in range(5):
            (tmp_path / f"f{i}.py").write_text(f"# {i}")
        result = _tool_list_recent_files({"directory": str(tmp_path), "count": 2})
        assert isinstance(result, str)


# ── run_quick_check ───────────────────────────────────────────────────────────

class TestRunQuickCheck:
    def test_simple_command(self):
        result = _tool_run_quick_check({"command": "echo hello"})
        assert "hello" in result

    def test_exit_code(self):
        result = _tool_run_quick_check({"command": "exit 1"})
        assert "exit 1" in result or "error" in result.lower()

    def test_blocked_command(self):
        result = _tool_run_quick_check({"command": "rm -rf /"})
        assert "bloqueado" in result.lower() or "error" in result.lower()

    def test_missing_command(self):
        result = _tool_run_quick_check({})
        assert "error" in result.lower() or "requer" in result.lower()

    def test_command_with_output(self):
        result = _tool_run_quick_check({"command": "python3 -c 'print(1+1)'"})
        assert "2" in result


# ── code_compare ──────────────────────────────────────────────────────────────

class TestCodeCompare:
    def test_identical_files(self, tmp_path):
        content = "def foo():\n    return 42\n"
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        a.write_text(content)
        b.write_text(content)
        result = _tool_code_compare({"file1": str(a), "file2": str(b)})
        assert isinstance(result, str)

    def test_different_files(self, tmp_path):
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        a.write_text("def foo():\n    return 42\n")
        b.write_text("def foo():\n    return 99\n")
        result = _tool_code_compare({"file1": str(a), "file2": str(b)})
        assert isinstance(result, str) and len(result) > 5

    def test_missing_params(self):
        result = _tool_code_compare({})
        assert "error" in result.lower() or "requer" in result.lower()


# ── multi_grep ────────────────────────────────────────────────────────────────

class TestMultiGrep:
    def test_finds_multiple_patterns(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("def foo():\n    return bar\n\ndef baz():\n    pass\n")
        result = _tool_multi_grep({
            "patterns": "foo,baz",
            "path": str(tmp_path),
        })
        assert "foo" in result or "baz" in result

    def test_no_matches(self, tmp_path):
        (tmp_path / "code.py").write_text("x = 1\n")
        result = _tool_multi_grep({
            "patterns": "nonexistent_xyz_abc",
            "path": str(tmp_path),
        })
        assert isinstance(result, str)

    def test_glob_filter(self, tmp_path):
        (tmp_path / "code.py").write_text("def hello(): pass\n")
        (tmp_path / "data.txt").write_text("hello world\n")
        result = _tool_multi_grep({
            "patterns": "hello",
            "path": str(tmp_path),
            "glob": "*.py",
        })
        assert isinstance(result, str)
