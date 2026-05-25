"""
test_51_integration_review.py — Tests de integración: hooks, subagentes, nuevos prompts/recursos

Cubre:
  - load_oocode_md_hooks en tools/hooks.py (función pública)
  - Herencia de hooks en subagentes (config.hooks_builtins heredado del padre)
  - Nuevos prompts: explore_codebase, troubleshoot_error, write_commit_message
  - Nuevos resources: project://hooks, project://active_tools
  - Consistencia _TOOLS/_TOOL_FNS y _RESOURCES/_RESOURCE_FNS
  - Conteo total actualizado (120 tools, 45 prompts, 25 resources)
  - Todos los prompts tienen handler en _get_prompt()
"""
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# load_oocode_md_hooks (ahora en tools/hooks.py)
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadOocodeMdHooks:
    def _make_config(self, md_text: str):
        cfg = MagicMock()
        cfg.load_oocode_md = MagicMock(return_value=md_text)
        return cfg

    def test_function_exists_in_hooks(self):
        from tools.hooks import load_oocode_md_hooks
        assert callable(load_oocode_md_hooks)

    def test_returns_int(self):
        from tools.hooks import load_oocode_md_hooks, HookManager
        hm  = HookManager()
        cfg = self._make_config("")
        result = load_oocode_md_hooks(hm, cfg)
        assert isinstance(result, int)

    def test_empty_md_returns_zero(self):
        from tools.hooks import load_oocode_md_hooks, HookManager
        hm  = HookManager()
        cfg = self._make_config("")
        assert load_oocode_md_hooks(hm, cfg) == 0

    def test_no_hooks_section_returns_zero(self):
        from tools.hooks import load_oocode_md_hooks, HookManager
        hm  = HookManager()
        cfg = self._make_config("# My project\n## Setup\nsome text\n")
        assert load_oocode_md_hooks(hm, cfg) == 0

    def test_registers_post_hook(self):
        from tools.hooks import load_oocode_md_hooks, HookManager
        hm  = HookManager()
        cfg = self._make_config("## Hooks\npost write_file: echo {path}\n")
        count = load_oocode_md_hooks(hm, cfg)
        assert count == 1
        assert len(hm._post) == 1

    def test_registers_pre_hook(self):
        from tools.hooks import load_oocode_md_hooks, HookManager
        hm  = HookManager()
        cfg = self._make_config("## Hooks\npre bash: echo before\n")
        count = load_oocode_md_hooks(hm, cfg)
        assert count == 1
        assert len(hm._pre) == 1

    def test_registers_multiple_hooks(self):
        from tools.hooks import load_oocode_md_hooks, HookManager
        hm  = HookManager()
        md  = "## Hooks\npost write_file: ruff check {path}\npre bash: echo test\n"
        cfg = self._make_config(md)
        count = load_oocode_md_hooks(hm, cfg)
        assert count == 2

    def test_hook_fn_name_contains_pattern(self):
        from tools.hooks import load_oocode_md_hooks, HookManager
        hm  = HookManager()
        cfg = self._make_config("## Hooks\npost edit_file: mypy {path}\n")
        load_oocode_md_hooks(hm, cfg)
        fn_name = hm._post[0][1].__name__
        assert "edit_file" in fn_name

    def test_config_without_load_method_returns_zero(self):
        from tools.hooks import load_oocode_md_hooks, HookManager
        hm  = HookManager()
        cfg = object()  # no tiene load_oocode_md
        result = load_oocode_md_hooks(hm, cfg)
        assert result == 0

    def test_oocode_py_wrapper_delegates(self):
        """El wrapper en oocode.py debe llamar a la función de tools.hooks."""
        import importlib
        import tools.hooks as hooks_mod
        original = hooks_mod.load_oocode_md_hooks
        called = []
        def fake(hm, cfg):
            called.append(True)
            return 0
        hooks_mod.load_oocode_md_hooks = fake
        try:
            import oocode
            hm  = MagicMock()
            cfg = MagicMock()
            cfg.load_oocode_md = MagicMock(return_value="")
            oocode._load_oocode_md_hooks(hm, cfg)
            assert called, "_load_oocode_md_hooks en oocode.py no llamó a tools.hooks"
        finally:
            hooks_mod.load_oocode_md_hooks = original


# ─────────────────────────────────────────────────────────────────────────────
# Herencia de hooks en subagentes
# ─────────────────────────────────────────────────────────────────────────────

class TestSubagentHookInheritance:
    def test_subagent_py_imports_hooks(self):
        """subagent.py debe importar desde tools.hooks para register_builtins."""
        import inspect
        import agent.subagent as sub_mod
        src = inspect.getsource(sub_mod)
        assert "hooks_builtins" in src, "subagent.py debe heredar hooks_builtins"
        assert "register_builtins" in src, "subagent.py debe llamar register_builtins"

    def test_subagent_inherits_hooks_enabled(self):
        import inspect
        import agent.subagent as sub_mod
        src = inspect.getsource(sub_mod)
        assert "hooks_enabled" in src

    def test_subagent_loads_oocode_md_hooks(self):
        import inspect
        import agent.subagent as sub_mod
        src = inspect.getsource(sub_mod)
        assert "load_oocode_md_hooks" in src or "lmh" in src

    def test_hooks_inherited_before_mcp_registration(self):
        """Hooks deben registrarse antes de las tools MCP (orden correcto)."""
        import inspect
        import agent.subagent as sub_mod
        src = inspect.getsource(sub_mod.SubAgentRunner.run)
        # El bloque de hooks debe aparecer antes del bloque MCP
        hooks_pos = src.find("register_builtins")
        mcp_pos   = src.find("parent_mcp")
        assert hooks_pos != -1 and mcp_pos != -1
        assert hooks_pos < mcp_pos, "register_builtins debe aparecer antes de parent_mcp"

    def test_subagent_inherits_specific_builtins(self):
        """Cuando el padre tiene hooks_builtins, el subagente los hereda."""
        from tools.registry import ToolRegistry
        from tools.hooks import HookManager

        # Simular padre con test_suite_delta activo
        parent_config      = MagicMock()
        parent_config.hooks_enabled  = True
        parent_config.hooks_builtins = ["diff_after_write", "test_suite_delta"]

        # registry limpio (como sale de build_registry_fn)
        registry = ToolRegistry()
        assert len(registry.hooks._pre) + len(registry.hooks._post) == 0

        # Aplicar la misma lógica que subagent.py
        sub_config = MagicMock()
        sub_config.hooks_enabled  = parent_config.hooks_enabled
        sub_config.hooks_builtins = list(parent_config.hooks_builtins)
        if sub_config.hooks_enabled and sub_config.hooks_builtins:
            registry.hooks.register_builtins(sub_config.hooks_builtins)

        active = registry.hooks.active_builtin_names()
        assert "diff_after_write" in active
        assert "test_suite_delta" in active

    def test_subagent_with_no_hooks_inherits_empty(self):
        """Padre con hooks_builtins=[] → subagente sin hooks registrados."""
        from tools.registry import ToolRegistry

        parent_config              = MagicMock()
        parent_config.hooks_enabled  = True
        parent_config.hooks_builtins = []

        registry   = ToolRegistry()
        sub_config = MagicMock()
        sub_config.hooks_enabled  = parent_config.hooks_enabled
        sub_config.hooks_builtins = list(parent_config.hooks_builtins)
        if sub_config.hooks_enabled and sub_config.hooks_builtins:
            registry.hooks.register_builtins(sub_config.hooks_builtins)

        active = registry.hooks.active_builtin_names()
        assert len(active) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Nuevos prompts MCP
# ─────────────────────────────────────────────────────────────────────────────

class TestExploreCodebasePrompt:
    def test_in_prompts_dict(self):
        from mcp_servers.oocode_assistant import _PROMPTS
        assert "explore_codebase" in _PROMPTS

    def test_has_focus_argument(self):
        from mcp_servers.oocode_assistant import _PROMPTS
        args = [a["name"] for a in _PROMPTS["explore_codebase"]["arguments"]]
        assert "focus" in args

    def test_has_depth_argument(self):
        from mcp_servers.oocode_assistant import _PROMPTS
        args = [a["name"] for a in _PROMPTS["explore_codebase"]["arguments"]]
        assert "depth" in args

    def test_handler_returns_messages(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("explore_codebase", {})
        assert isinstance(msgs, list) and len(msgs) > 0

    def test_handler_uses_focus(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("explore_codebase", {"focus": "tests"})
        text = msgs[0]["content"]["text"]
        assert "tests" in text.lower()

    def test_handler_mentions_analyze_codebase(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("explore_codebase", {})
        text = msgs[0]["content"]["text"]
        assert "analyze_codebase" in text or "code_outline" in text

    def test_handler_deep_depth(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("explore_codebase", {"depth": "deep"})
        text = msgs[0]["content"]["text"]
        assert "deep" in text.lower() or "completo" in text.lower()


class TestTroubleshootErrorPrompt:
    def test_in_prompts_dict(self):
        from mcp_servers.oocode_assistant import _PROMPTS
        assert "troubleshoot_error" in _PROMPTS

    def test_error_argument_required(self):
        from mcp_servers.oocode_assistant import _PROMPTS
        args = _PROMPTS["troubleshoot_error"]["arguments"]
        error_arg = next((a for a in args if a["name"] == "error"), None)
        assert error_arg is not None
        assert error_arg.get("required") is True

    def test_handler_includes_error_text(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("troubleshoot_error", {"error": "AttributeError: NoneType"})
        text = msgs[0]["content"]["text"]
        assert "AttributeError: NoneType" in text

    def test_handler_mentions_grep_code(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("troubleshoot_error", {"error": "some error"})
        text = msgs[0]["content"]["text"]
        assert "grep_code" in text

    def test_handler_mentions_run_tests(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("troubleshoot_error", {"error": "test failed"})
        text = msgs[0]["content"]["text"]
        assert "run_tests" in text

    def test_handler_includes_context_when_given(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("troubleshoot_error", {"error": "err", "context": "agent/loop.py"})
        text = msgs[0]["content"]["text"]
        assert "agent/loop.py" in text


class TestWriteCommitMessagePrompt:
    def test_in_prompts_dict(self):
        from mcp_servers.oocode_assistant import _PROMPTS
        assert "write_commit_message" in _PROMPTS

    def test_has_style_argument(self):
        from mcp_servers.oocode_assistant import _PROMPTS
        args = [a["name"] for a in _PROMPTS["write_commit_message"]["arguments"]]
        assert "style" in args

    def test_has_lang_argument(self):
        from mcp_servers.oocode_assistant import _PROMPTS
        args = [a["name"] for a in _PROMPTS["write_commit_message"]["arguments"]]
        assert "lang" in args

    def test_handler_returns_messages(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("write_commit_message", {})
        assert isinstance(msgs, list) and len(msgs) > 0

    def test_handler_conventional_style(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("write_commit_message", {"style": "conventional"})
        text = msgs[0]["content"]["text"]
        assert "feat" in text or "Conventional" in text

    def test_handler_mentions_git_diff(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("write_commit_message", {})
        text = msgs[0]["content"]["text"]
        assert "git_diff" in text

    def test_handler_spanish_lang(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("write_commit_message", {"lang": "es"})
        text = msgs[0]["content"]["text"]
        assert "español" in text.lower() or "es" in text.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Nuevos recursos MCP
# ─────────────────────────────────────────────────────────────────────────────

class TestProjectHooksResource:
    def test_in_resources_list(self):
        from mcp_servers.oocode_assistant import _RESOURCES
        uris = [r["uri"] for r in _RESOURCES]
        assert "project://hooks" in uris

    def test_in_resource_fns(self):
        from mcp_servers.oocode_assistant import _RESOURCE_FNS
        assert "project://hooks" in _RESOURCE_FNS

    def test_returns_string(self):
        from mcp_servers.oocode_assistant import _resource_active_hooks
        result = _resource_active_hooks()
        assert isinstance(result, str) and len(result) > 0

    def test_contains_hook_names(self):
        from mcp_servers.oocode_assistant import _resource_active_hooks
        result = _resource_active_hooks()
        assert "diff_after_write" in result

    def test_contains_toggle_instructions(self):
        from mcp_servers.oocode_assistant import _resource_active_hooks
        result = _resource_active_hooks()
        assert "/hooks builtin" in result

    def test_shows_active_section(self):
        from mcp_servers.oocode_assistant import _resource_active_hooks
        result = _resource_active_hooks()
        assert "Activos" in result or "activos" in result

    def test_shows_available_section(self):
        from mcp_servers.oocode_assistant import _resource_active_hooks
        result = _resource_active_hooks()
        assert "Disponibles" in result or "disponibles" in result


class TestProjectActiveToolsResource:
    def test_in_resources_list(self):
        from mcp_servers.oocode_assistant import _RESOURCES
        uris = [r["uri"] for r in _RESOURCES]
        assert "project://active_tools" in uris

    def test_in_resource_fns(self):
        from mcp_servers.oocode_assistant import _RESOURCE_FNS
        assert "project://active_tools" in _RESOURCE_FNS

    def test_returns_string(self):
        from mcp_servers.oocode_assistant import _resource_active_tools
        result = _resource_active_tools()
        assert isinstance(result, str) and len(result) > 0

    def test_contains_git_tools(self):
        from mcp_servers.oocode_assistant import _resource_active_tools
        result = _resource_active_tools()
        assert "git_status" in result and "git_commit" in result

    def test_contains_categories(self):
        from mcp_servers.oocode_assistant import _resource_active_tools
        result = _resource_active_tools()
        assert "Git" in result
        assert "Docker" in result or "Compose" in result

    def test_contains_edit_tools(self):
        from mcp_servers.oocode_assistant import _resource_active_tools
        result = _resource_active_tools()
        assert "edit_file" in result or "write_file" in result

    def test_mentions_prompts(self):
        from mcp_servers.oocode_assistant import _resource_active_tools
        result = _resource_active_tools()
        assert "Prompts" in result or "prompts" in result


# ─────────────────────────────────────────────────────────────────────────────
# Consistencia global
# ─────────────────────────────────────────────────────────────────────────────

class TestConsistency:
    def test_all_tools_have_fn(self):
        from mcp_servers.oocode_assistant import _TOOLS, _TOOL_FNS
        missing = [t["name"] for t in _TOOLS if t["name"] not in _TOOL_FNS]
        assert missing == [], f"Tools sin fn: {missing}"

    def test_all_resources_have_fn(self):
        from mcp_servers.oocode_assistant import _RESOURCES, _RESOURCE_FNS
        missing = [r["uri"] for r in _RESOURCES if r["uri"] not in _RESOURCE_FNS]
        assert missing == [], f"Resources sin fn: {missing}"

    def test_all_prompts_have_handler(self):
        from mcp_servers.oocode_assistant import _PROMPTS, _get_prompt
        no_handler = []
        for name in _PROMPTS:
            msgs = _get_prompt(name, {})
            if not isinstance(msgs, list) or len(msgs) == 0:
                no_handler.append(name)
        assert no_handler == [], f"Prompts sin handler: {no_handler}"

    def test_tool_count(self):
        from mcp_servers.oocode_assistant import _TOOLS
        assert len(_TOOLS) == 120, f"Se esperaban 120 tools, hay {len(_TOOLS)}"

    def test_prompt_count(self):
        from mcp_servers.oocode_assistant import _PROMPTS
        assert len(_PROMPTS) == 45, f"Se esperaban 45 prompts, hay {len(_PROMPTS)}"

    def test_resource_count(self):
        from mcp_servers.oocode_assistant import _RESOURCES
        assert len(_RESOURCES) == 25, f"Se esperaban 25 resources, hay {len(_RESOURCES)}"

    def test_all_mcp_tools_have_permission(self):
        from mcp_servers.oocode_assistant import _TOOLS
        from config import DEFAULT_CONFIG
        perms   = DEFAULT_CONFIG["permissions"]
        missing = [t["name"] for t in _TOOLS if t["name"] not in perms]
        assert missing == [], f"Tools sin permiso: {missing}"

    def test_builtins_all_registered_in_default_config(self):
        """Todos los hooks en DEFAULT_CONFIG['hooks']['builtins'] existen en _BUILTINS."""
        from tools.hooks import _BUILTINS
        from config import DEFAULT_CONFIG
        enabled = DEFAULT_CONFIG["hooks"]["builtins"]
        missing = [h for h in enabled if h not in _BUILTINS]
        assert missing == [], f"Hooks en config pero no en _BUILTINS: {missing}"

    def test_all_builtins_accessible_for_toggle(self):
        """Todos los hooks de _BUILTINS aparecen en HookManager.available_builtins()."""
        from tools.hooks import HookManager, _BUILTINS
        available = set(HookManager.available_builtins())
        missing   = [h for h in _BUILTINS if h not in available]
        assert missing == [], f"Hooks en _BUILTINS pero no en available_builtins: {missing}"

    def test_load_oocode_md_hooks_exported(self):
        """load_oocode_md_hooks debe ser importable desde tools.hooks."""
        from tools.hooks import load_oocode_md_hooks
        assert callable(load_oocode_md_hooks)

    def test_explore_codebase_handler_no_exception_on_empty_args(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("explore_codebase", {})
        assert msgs  # no lanza excepción

    def test_troubleshoot_error_handler_no_exception_on_empty_args(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("troubleshoot_error", {})
        assert msgs  # no lanza excepción

    def test_write_commit_message_handler_no_exception_on_empty_args(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("write_commit_message", {})
        assert msgs  # no lanza excepción
