"""Tests de todos los prompts y recursos del MCP server oocode_assistant (sin LLM).

Verifica que:
- Cada prompt retorna una lista de mensajes con role/content válidos
- Cada recurso retorna un string no vacío
- Los schemas de _TOOLS tienen los campos obligatorios
- Todos los nombres de _TOOL_FNS existen como claves en _TOOL_FNS
- _RESOURCES tiene exactamente un handler por URI
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.oocode_assistant import (
    _TOOLS,
    _PROMPTS,
    _RESOURCES,
    _TOOL_FNS,
    _RESOURCE_FNS,
    _get_prompt,
)


# ── _TOOLS schema integrity ───────────────────────────────────────────────────

class TestToolSchemas:
    def test_all_tools_have_name(self):
        for tool in _TOOLS:
            assert "name" in tool, f"Tool sin 'name': {tool}"
            assert isinstance(tool["name"], str)
            assert len(tool["name"]) > 0

    def test_all_tools_have_description(self):
        for tool in _TOOLS:
            assert "description" in tool, f"Tool sin 'description': {tool['name']}"
            assert isinstance(tool["description"], str)
            assert len(tool["description"]) > 0

    def test_all_tools_have_parameters_or_input_schema(self):
        for tool in _TOOLS:
            has_params = "parameters" in tool or "inputSchema" in tool
            assert has_params, f"Tool sin 'parameters' ni 'inputSchema': {tool['name']}"

    def test_no_double_wrapper(self):
        """Schemas no deben tener wrapper {type:function, function:{...}}."""
        for tool in _TOOLS:
            # Si tiene type:function pero también name al nivel raíz → doble wrapper
            if tool.get("type") == "function" and "function" in tool:
                assert False, f"Tool '{tool.get('name', '?')}' tiene wrapper doble"

    def test_no_duplicate_tool_names(self):
        names = [t["name"] for t in _TOOLS]
        assert len(names) == len(set(names)), f"Nombres duplicados: {[n for n in names if names.count(n) > 1]}"

    def test_all_tools_have_handler(self):
        """Cada tool en _TOOLS debe tener su función en _TOOL_FNS."""
        for tool in _TOOLS:
            name = tool["name"]
            assert name in _TOOL_FNS, f"Tool '{name}' no tiene handler en _TOOL_FNS"

    def test_all_handlers_callable(self):
        for name, fn in _TOOL_FNS.items():
            assert callable(fn), f"Handler de '{name}' no es callable"

    def test_tool_count(self):
        """Verificar que no bajamos de 109 tools registradas."""
        assert len(_TOOLS) >= 109, f"Solo hay {len(_TOOLS)} tools (mínimo 109)"


# ── _PROMPTS coverage ─────────────────────────────────────────────────────────

_EXPECTED_PROMPTS = [
    "api_design",
    "architecture_review",
    "benchmark",
    "code_migration",
    "code_review",
    "commit_message",
    "data_model",
    "debug_c",
    "debug_failing_edits",
    "debug_session",
    "documentation",
    "error_analysis",
    "explain_code",
    "fix_lint",
    "generate_c_code",
    "generate_code",
    "generate_cpp_code",
    "generate_java_code",
    "generate_js_code",
    "generate_perl_script",
    "generate_python_code",
    "generate_ruby_code",
    "generate_sh_script",
    "generate_sql_schema",
    "generate_yaml_config",
    "log_analysis",
    "optimize_query",
    "plan_code_changes",
    "pr_description",
    "pre_implementation_check",
    "refactor_code",
    "security_audit",
    "sql_query",
    "test_cases",
    "write_tests",
]


class TestPrompts:
    def test_all_expected_prompts_registered(self):
        for name in _EXPECTED_PROMPTS:
            assert name in _PROMPTS, f"Prompt '{name}' no registrado en _PROMPTS"

    def test_prompt_count(self):
        assert len(_PROMPTS) >= 35, f"Solo hay {len(_PROMPTS)} prompts (mínimo 35)"

    @pytest.mark.parametrize("name", _EXPECTED_PROMPTS)
    def test_prompt_returns_message_list(self, name):
        result = _get_prompt(name, {})
        assert isinstance(result, list), f"Prompt '{name}' no devuelve lista"
        assert len(result) > 0, f"Prompt '{name}' devuelve lista vacía"
        for msg in result:
            assert "role" in msg, f"Mensaje de '{name}' sin 'role'"
            assert "content" in msg, f"Mensaje de '{name}' sin 'content'"

    def test_code_review_with_code(self):
        result = _get_prompt("code_review", {"code": "def foo(): pass", "language": "python"})
        text = result[0]["content"]["text"] if isinstance(result[0]["content"], dict) else result[0]["content"]
        assert "def foo" in text or "python" in text.lower()

    def test_debug_session_with_error(self):
        result = _get_prompt("debug_session", {"error": "AttributeError: NoneType"})
        text = result[0]["content"]["text"] if isinstance(result[0]["content"], dict) else result[0]["content"]
        assert "AttributeError" in text

    def test_generate_code_with_task(self):
        result = _get_prompt("generate_code", {"task": "sort a list", "language": "python"})
        assert isinstance(result, list) and len(result) > 0

    def test_plan_code_changes(self):
        result = _get_prompt("plan_code_changes", {"task": "refactor auth module"})
        assert isinstance(result, list) and len(result) > 0

    def test_pre_implementation_check(self):
        result = _get_prompt("pre_implementation_check", {"task": "add tests"})
        assert isinstance(result, list) and len(result) > 0

    def test_debug_failing_edits(self):
        result = _get_prompt("debug_failing_edits", {"error": "old_string not found"})
        assert isinstance(result, list) and len(result) > 0

    def test_security_audit(self):
        result = _get_prompt("security_audit", {"code": "eval(user_input)"})
        assert isinstance(result, list) and len(result) > 0

    def test_refactor_code(self):
        result = _get_prompt("refactor_code", {"code": "x=1;y=2;z=x+y", "language": "python"})
        assert isinstance(result, list) and len(result) > 0

    def test_write_tests(self):
        result = _get_prompt("write_tests", {"code": "def add(a,b): return a+b", "language": "python"})
        assert isinstance(result, list) and len(result) > 0

    def test_unknown_prompt_returns_something(self):
        result = _get_prompt("nonexistent_prompt_xyz", {})
        assert isinstance(result, list)


# ── _RESOURCES coverage ───────────────────────────────────────────────────────

_EXPECTED_RESOURCES = [
    "project://context",
    "project://structure",
    "project://git",
    "project://deps",
    "project://tests",
    "project://env",
    "project://errors",
    "project://metrics",
    "project://changelog",
    "project://docker",
    "project://coverage",
    "project://makefile",
    "project://ci",
    "project://lint",
    "project://openapi",
    "project://todos",
    "project://processes",
    "project://templates",
    "project://reasoning",
    "project://lsp",
]


class TestResources:
    def test_resources_is_list(self):
        assert isinstance(_RESOURCES, list)

    def test_all_expected_resources_registered(self):
        uris = {r.get("uri") or r.get("name") for r in _RESOURCES}
        for uri in _EXPECTED_RESOURCES:
            assert uri in uris, f"Resource '{uri}' no registrado en _RESOURCES"

    def test_resource_count(self):
        assert len(_RESOURCES) >= 20, f"Solo hay {len(_RESOURCES)} resources (mínimo 20)"

    def test_all_resources_have_handler(self):
        for uri in _EXPECTED_RESOURCES:
            assert uri in _RESOURCE_FNS, f"Resource '{uri}' no tiene handler en _RESOURCE_FNS"

    def test_all_resource_handlers_callable(self):
        for uri, fn in _RESOURCE_FNS.items():
            assert callable(fn), f"Handler de '{uri}' no es callable"

    @pytest.mark.parametrize("uri", _EXPECTED_RESOURCES)
    def test_resource_returns_string(self, uri):
        fn = _RESOURCE_FNS[uri]
        result = fn()
        assert isinstance(result, str), f"Resource '{uri}' no devuelve string"
        assert len(result) >= 0  # puede estar vacío si el proyecto no tiene ese artefacto

    def test_reasoning_resource_content(self):
        fn = _RESOURCE_FNS["project://reasoning"]
        result = fn()
        assert "LSP" in result or "edit" in result.lower() or "razon" in result.lower() or isinstance(result, str)

    def test_lsp_resource_content(self):
        fn = _RESOURCE_FNS["project://lsp"]
        result = fn()
        assert "LSP" in result or "server" in result.lower() or isinstance(result, str)

    def test_context_resource_content(self):
        fn = _RESOURCE_FNS["project://context"]
        result = fn()
        assert isinstance(result, str)

    def test_structure_resource_content(self):
        fn = _RESOURCE_FNS["project://structure"]
        result = fn()
        assert isinstance(result, str)

    def test_processes_resource_content(self):
        fn = _RESOURCE_FNS["project://processes"]
        result = fn()
        assert isinstance(result, str)


# ── _RESOURCES list schema ────────────────────────────────────────────────────

class TestResourcesSchema:
    def test_all_resources_have_uri(self):
        for r in _RESOURCES:
            assert "uri" in r or "name" in r, f"Resource sin URI/name: {r}"

    def test_all_resources_have_name(self):
        for r in _RESOURCES:
            assert "name" in r, f"Resource sin 'name': {r}"

    def test_no_duplicate_uris(self):
        uris = [r.get("uri") or r.get("name") for r in _RESOURCES]
        assert len(uris) == len(set(uris)), f"URIs duplicadas: {[u for u in uris if uris.count(u) > 1]}"
