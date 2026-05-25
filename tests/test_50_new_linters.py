"""
test_50_new_linters.py — Tests para nuevos linters apt y efm-langserver

Cubre:
  - efm-langserver: generación de config YAML
  - Nuevas entradas en _LINTERS (splint, B::Lint, jsonlint, rpmlint, ansible-lint)
  - LSP: .xml/.spec via efm-langserver en _SERVER_CMDS
  - MCP tools: gitlint_check, ansible_lint, efm_config_update
  - MCP prompt: ansible_review
  - /doctor: nuevos linters en _LINTERS_DOC, efm-langserver en _LSP_INSTALL
  - Permisos config.py para los nuevos tools
  - Contador total de tools/prompts/resources
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# efm-langserver config generation
# ─────────────────────────────────────────────────────────────────────────────

class TestEfmConfigGeneration:
    def test_generate_efm_config_returns_string(self):
        from agent.lsp_client import _generate_efm_config
        result = _generate_efm_config()
        assert isinstance(result, str)

    def test_generate_efm_config_has_version(self):
        from agent.lsp_client import _generate_efm_config
        cfg = _generate_efm_config()
        assert "version: 2" in cfg

    def test_generate_efm_config_has_root_markers(self):
        from agent.lsp_client import _generate_efm_config
        cfg = _generate_efm_config()
        assert "root-markers" in cfg

    def test_generate_efm_config_has_languages_section(self):
        from agent.lsp_client import _generate_efm_config
        cfg = _generate_efm_config()
        assert "languages:" in cfg

    def test_ensure_efm_config_creates_file(self, tmp_path):
        from agent import lsp_client
        orig_path = lsp_client._EFM_CONFIG_PATH
        try:
            lsp_client._EFM_CONFIG_PATH = tmp_path / "efm-langserver.yaml"
            lsp_client._ensure_efm_config(force=True)
            assert lsp_client._EFM_CONFIG_PATH.exists()
        finally:
            lsp_client._EFM_CONFIG_PATH = orig_path

    def test_ensure_efm_config_not_overwrite_when_content_matches(self, tmp_path):
        from agent import lsp_client
        orig_path = lsp_client._EFM_CONFIG_PATH
        try:
            cfg_path = tmp_path / "efm-langserver.yaml"
            # Write the exact content that _generate_efm_config() would produce
            generated = lsp_client._generate_efm_config()
            cfg_path.write_text(generated)
            mtime_before = cfg_path.stat().st_mtime_ns
            lsp_client._EFM_CONFIG_PATH = cfg_path
            lsp_client._ensure_efm_config(force=False)
            # Content matches → file should not be touched
            assert cfg_path.stat().st_mtime_ns == mtime_before
        finally:
            lsp_client._EFM_CONFIG_PATH = orig_path

    def test_ensure_efm_config_overwrites_stale_content(self, tmp_path):
        """Stale/custom content is replaced by the freshly-generated config."""
        from agent import lsp_client
        orig_path = lsp_client._EFM_CONFIG_PATH
        try:
            cfg_path = tmp_path / "efm-langserver.yaml"
            cfg_path.write_text("# stale custom config\n")
            lsp_client._EFM_CONFIG_PATH = cfg_path
            lsp_client._ensure_efm_config(force=False)
            # Content differs → regenerated
            assert cfg_path.read_text() == lsp_client._generate_efm_config()
        finally:
            lsp_client._EFM_CONFIG_PATH = orig_path

    def test_ensure_efm_config_force_overwrites(self, tmp_path):
        from agent import lsp_client
        orig_path = lsp_client._EFM_CONFIG_PATH
        try:
            cfg_path = tmp_path / "efm-langserver.yaml"
            cfg_path.write_text("# old config\n")
            lsp_client._EFM_CONFIG_PATH = cfg_path
            lsp_client._ensure_efm_config(force=True)
            content = cfg_path.read_text()
            assert "version: 2" in content
        finally:
            lsp_client._EFM_CONFIG_PATH = orig_path

    def test_xmllint_section_when_installed(self):
        """xmllint es casi seguro que está instalado en el sistema."""
        if not shutil.which("xmllint"):
            pytest.skip("xmllint no instalado")
        from agent.lsp_client import _generate_efm_config
        cfg = _generate_efm_config()
        assert "xmllint" in cfg

    def test_rpmlint_section_when_installed(self):
        if not shutil.which("rpmlint"):
            pytest.skip("rpmlint no instalado")
        from agent.lsp_client import _generate_efm_config
        cfg = _generate_efm_config()
        assert "rpmlint" in cfg

    def test_markdownlint_section_when_installed(self):
        if not shutil.which("markdownlint"):
            pytest.skip("markdownlint no instalado")
        from agent.lsp_client import _generate_efm_config
        cfg = _generate_efm_config()
        assert "markdownlint" in cfg

    def test_gitlint_section_when_installed(self):
        if not shutil.which("gitlint"):
            pytest.skip("gitlint no instalado")
        from agent.lsp_client import _generate_efm_config
        cfg = _generate_efm_config()
        assert "gitlint" in cfg

    def test_ansible_lint_not_in_efm(self):
        """ansible-lint ya está en _LINTERS para lint_after_write; no se duplica en efm."""
        from agent.lsp_client import _generate_efm_config
        cfg = _generate_efm_config()
        assert "ansible-lint" not in cfg

    def test_jsonlint_not_in_efm(self):
        """jsonlint ya está en _LINTERS para .json (vscode-json-language-server como LSP)."""
        from agent.lsp_client import _generate_efm_config
        cfg = _generate_efm_config()
        assert "jsonlint" not in cfg


# ─────────────────────────────────────────────────────────────────────────────
# _LINTERS entries (hooks.py)
# ─────────────────────────────────────────────────────────────────────────────

class TestLintersEntries:
    def _get_linters(self):
        from tools.hooks import _LINTERS
        return _LINTERS

    def test_splint_in_c_linters(self):
        linters = self._get_linters()
        c_cmds = [" ".join(cmd) for cmd in linters.get(".c", [])]
        assert any("splint" in cmd for cmd in c_cmds)

    def test_splint_in_h_linters(self):
        linters = self._get_linters()
        h_cmds = [" ".join(cmd) for cmd in linters.get(".h", [])]
        assert any("splint" in cmd for cmd in h_cmds)

    def test_blint_perl_in_pl_linters(self):
        linters = self._get_linters()
        pl_cmds = [" ".join(cmd) for cmd in linters.get(".pl", [])]
        assert any("B::Lint" in cmd or "-MO=Lint" in cmd for cmd in pl_cmds)

    def test_blint_perl_in_pm_linters(self):
        linters = self._get_linters()
        pm_cmds = [" ".join(cmd) for cmd in linters.get(".pm", [])]
        assert any("B::Lint" in cmd or "-MO=Lint" in cmd for cmd in pm_cmds)

    def test_jsonlint_in_json_linters(self):
        linters = self._get_linters()
        json_cmds = [" ".join(cmd) for cmd in linters.get(".json", [])]
        assert any("jsonlint" in cmd for cmd in json_cmds)

    def test_spec_not_in_direct_linters(self):
        """rpmlint se invoca vía efm-langserver para .spec, no vía lint_after_write directo."""
        linters = self._get_linters()
        assert ".spec" not in linters

    def test_ansible_lint_in_yaml_linters(self):
        linters = self._get_linters()
        yaml_cmds = [" ".join(cmd) for cmd in linters.get(".yaml", [])]
        assert any("ansible-lint" in cmd for cmd in yaml_cmds)

    def test_ansible_lint_in_yml_linters(self):
        linters = self._get_linters()
        yml_cmds = [" ".join(cmd) for cmd in linters.get(".yml", [])]
        assert any("ansible-lint" in cmd for cmd in yml_cmds)

    def test_yamllint_still_in_yaml_linters(self):
        linters = self._get_linters()
        yaml_cmds = [" ".join(cmd) for cmd in linters.get(".yaml", [])]
        assert any("yamllint" in cmd for cmd in yaml_cmds)

    def test_linter_commands_have_file_placeholder(self):
        """Casi todos los comandos deben tener {file}; .rs usa cargo (proyecto entero)."""
        from tools.hooks import _LINTERS
        # .rs usa 'cargo check' que opera en el proyecto, no en un fichero individual
        skip_exts = {".rs"}
        for ext, cmds in _LINTERS.items():
            if ext in skip_exts:
                continue
            for cmd in cmds:
                joined = " ".join(cmd)
                assert "{file}" in joined, f"Falta {{file}} en linter {ext}: {cmd}"


# ─────────────────────────────────────────────────────────────────────────────
# LSP server entries (.xml / .spec via efm-langserver)
# ─────────────────────────────────────────────────────────────────────────────

class TestLspEfmEntries:
    def test_xml_uses_efm_langserver(self):
        from agent.lsp_client import _SERVER_CMDS
        cmd = _SERVER_CMDS.get(".xml", [])
        assert cmd and cmd[0] == "efm-langserver"

    def test_xsl_alias_to_xml(self):
        from agent.lsp_client import _SERVER_ALIASES
        assert _SERVER_ALIASES.get(".xsl") == ".xml"

    def test_xslt_alias_to_xml(self):
        from agent.lsp_client import _SERVER_ALIASES
        assert _SERVER_ALIASES.get(".xslt") == ".xml"

    def test_svg_alias_to_xml(self):
        from agent.lsp_client import _SERVER_ALIASES
        assert _SERVER_ALIASES.get(".svg") == ".xml"

    def test_spec_uses_efm_langserver(self):
        from agent.lsp_client import _SERVER_CMDS
        cmd = _SERVER_CMDS.get(".spec", [])
        assert cmd and cmd[0] == "efm-langserver"

    def test_spec_in_ext_to_lang(self):
        from agent.lsp_client import _EXT_TO_LANG
        assert ".spec" in _EXT_TO_LANG

    def test_xml_in_ext_to_lang(self):
        from agent.lsp_client import _EXT_TO_LANG
        assert ".xml" in _EXT_TO_LANG

    def test_efm_config_path_in_xml_cmd(self):
        from agent.lsp_client import _SERVER_CMDS, _EFM_CONFIG_PATH
        cmd = _SERVER_CMDS.get(".xml", [])
        assert any(str(_EFM_CONFIG_PATH) in c for c in cmd)

    def test_alias_targets_exist_in_server_cmds(self):
        """Todos los alias deben apuntar a extensiones que existen en _SERVER_CMDS."""
        from agent.lsp_client import _SERVER_CMDS, _SERVER_ALIASES
        for alias, target in _SERVER_ALIASES.items():
            assert target in _SERVER_CMDS, f"Alias {alias}→{target} apunta a target inexistente"


# ─────────────────────────────────────────────────────────────────────────────
# MCP tools: gitlint_check, ansible_lint, efm_config_update
# ─────────────────────────────────────────────────────────────────────────────

class TestGitlintCheckTool:
    def _call(self, **kwargs):
        from mcp_servers.oocode_assistant import _tool_gitlint_check
        return _tool_gitlint_check(kwargs)

    def test_no_gitlint_error(self):
        with patch("shutil.which", return_value=None):
            result = self._call()
        assert "gitlint" in result.lower()
        assert "instalado" in result.lower() or "install" in result.lower()

    def test_not_git_repo(self, tmp_path):
        if not shutil.which("gitlint"):
            pytest.skip("gitlint no instalado")
        result = self._call(directory=str(tmp_path))
        assert "Error" in result or "no es un repo" in result

    def test_default_count_is_1(self):
        from mcp_servers.oocode_assistant import _tool_gitlint_check
        import inspect
        # Verifica que el parámetro count tenga default 1
        src = inspect.getsource(_tool_gitlint_check)
        assert 'get("count", 1)' in src

    def test_in_tools_list(self):
        from mcp_servers.oocode_assistant import _TOOLS
        names = [t["name"] for t in _TOOLS]
        assert "gitlint_check" in names

    def test_in_tool_fns(self):
        from mcp_servers.oocode_assistant import _TOOL_FNS
        assert "gitlint_check" in _TOOL_FNS

    def test_schema_has_count_property(self):
        from mcp_servers.oocode_assistant import _TOOLS
        tool = next(t for t in _TOOLS if t["name"] == "gitlint_check")
        props = tool["inputSchema"]["properties"]
        assert "count" in props

    def test_schema_has_directory_property(self):
        from mcp_servers.oocode_assistant import _TOOLS
        tool = next(t for t in _TOOLS if t["name"] == "gitlint_check")
        props = tool["inputSchema"]["properties"]
        assert "directory" in props


class TestAnsibleLintTool:
    def _call(self, **kwargs):
        from mcp_servers.oocode_assistant import _tool_ansible_lint
        return _tool_ansible_lint(kwargs)

    def test_no_ansible_lint_error(self):
        with patch("shutil.which", return_value=None):
            result = self._call(path=".")
        assert "ansible-lint" in result.lower()

    def test_nonexistent_path_error(self, tmp_path):
        if not shutil.which("ansible-lint"):
            pytest.skip("ansible-lint no instalado")
        result = self._call(path=str(tmp_path / "nonexistent.yml"))
        assert "Error" in result or "no existe" in result

    def test_in_tools_list(self):
        from mcp_servers.oocode_assistant import _TOOLS
        names = [t["name"] for t in _TOOLS]
        assert "ansible_lint" in names

    def test_in_tool_fns(self):
        from mcp_servers.oocode_assistant import _TOOL_FNS
        assert "ansible_lint" in _TOOL_FNS

    def test_schema_has_path_property(self):
        from mcp_servers.oocode_assistant import _TOOLS
        tool = next(t for t in _TOOLS if t["name"] == "ansible_lint")
        props = tool["inputSchema"]["properties"]
        assert "path" in props

    def test_schema_has_profile_property(self):
        from mcp_servers.oocode_assistant import _TOOLS
        tool = next(t for t in _TOOLS if t["name"] == "ansible_lint")
        props = tool["inputSchema"]["properties"]
        assert "profile" in props

    def test_schema_has_tags_property(self):
        from mcp_servers.oocode_assistant import _TOOLS
        tool = next(t for t in _TOOLS if t["name"] == "ansible_lint")
        props = tool["inputSchema"]["properties"]
        assert "tags" in props

    def test_valid_playbook(self, tmp_path):
        if not shutil.which("ansible-lint"):
            pytest.skip("ansible-lint no instalado")
        playbook = tmp_path / "site.yml"
        playbook.write_text("---\n- hosts: localhost\n  tasks: []\n")
        result = self._call(path=str(playbook), profile="min")
        assert isinstance(result, str) and len(result) > 0


class TestEfmConfigUpdateTool:
    def _call(self, **kwargs):
        from mcp_servers.oocode_assistant import _tool_efm_config_update
        return _tool_efm_config_update(kwargs)

    def test_in_tools_list(self):
        from mcp_servers.oocode_assistant import _TOOLS
        names = [t["name"] for t in _TOOLS]
        assert "efm_config_update" in names

    def test_in_tool_fns(self):
        from mcp_servers.oocode_assistant import _TOOL_FNS
        assert "efm_config_update" in _TOOL_FNS

    def test_returns_string(self, tmp_path):
        from agent import lsp_client
        orig_path = lsp_client._EFM_CONFIG_PATH
        try:
            lsp_client._EFM_CONFIG_PATH = tmp_path / "efm-langserver.yaml"
            result = self._call()
            assert isinstance(result, str)
        finally:
            lsp_client._EFM_CONFIG_PATH = orig_path

    def test_result_mentions_efm(self, tmp_path):
        from agent import lsp_client
        orig_path = lsp_client._EFM_CONFIG_PATH
        try:
            lsp_client._EFM_CONFIG_PATH = tmp_path / "efm-langserver.yaml"
            result = self._call()
            assert "efm-langserver" in result.lower() or "efm" in result.lower()
        finally:
            lsp_client._EFM_CONFIG_PATH = orig_path

    def test_creates_config_file(self, tmp_path):
        from agent import lsp_client
        orig_path = lsp_client._EFM_CONFIG_PATH
        try:
            cfg_path = tmp_path / "efm-langserver.yaml"
            lsp_client._EFM_CONFIG_PATH = cfg_path
            self._call()
            assert cfg_path.exists()
        finally:
            lsp_client._EFM_CONFIG_PATH = orig_path

    def test_config_contains_yaml(self, tmp_path):
        from agent import lsp_client
        orig_path = lsp_client._EFM_CONFIG_PATH
        try:
            lsp_client._EFM_CONFIG_PATH = tmp_path / "efm-langserver.yaml"
            result = self._call()
            assert "```yaml" in result or "version: 2" in result
        finally:
            lsp_client._EFM_CONFIG_PATH = orig_path


# ─────────────────────────────────────────────────────────────────────────────
# MCP prompt: ansible_review
# ─────────────────────────────────────────────────────────────────────────────

class TestAnsibleReviewPrompt:
    def test_in_prompts_dict(self):
        from mcp_servers.oocode_assistant import _PROMPTS
        assert "ansible_review" in _PROMPTS

    def test_has_description(self):
        from mcp_servers.oocode_assistant import _PROMPTS
        assert _PROMPTS["ansible_review"]["description"]

    def test_has_path_argument(self):
        from mcp_servers.oocode_assistant import _PROMPTS
        args = _PROMPTS["ansible_review"]["arguments"]
        names = [a["name"] for a in args]
        assert "path" in names

    def test_has_profile_argument(self):
        from mcp_servers.oocode_assistant import _PROMPTS
        args = _PROMPTS["ansible_review"]["arguments"]
        names = [a["name"] for a in args]
        assert "profile" in names

    def test_get_prompt_returns_messages(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("ansible_review", {"path": "site.yml", "profile": "moderate"})
        assert isinstance(msgs, list) and len(msgs) > 0

    def test_get_prompt_mentions_ansible_lint(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("ansible_review", {"path": "playbook.yml"})
        text = msgs[0]["content"]["text"]
        assert "ansible_lint" in text

    def test_get_prompt_uses_provided_path(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("ansible_review", {"path": "/tmp/myplay.yml"})
        text = msgs[0]["content"]["text"]
        assert "/tmp/myplay.yml" in text

    def test_get_prompt_uses_provided_profile(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("ansible_review", {"path": ".", "profile": "safety"})
        text = msgs[0]["content"]["text"]
        assert "safety" in text


# ─────────────────────────────────────────────────────────────────────────────
# /doctor linter entries
# ─────────────────────────────────────────────────────────────────────────────

class TestDoctorLinterEntries:
    def _get_linters_doc(self):
        """Extract _LINTERS_DOC from _cmd_doctor source without running it."""
        import ast
        import inspect
        from ui.commands import _cmd_doctor
        src = inspect.getsource(_cmd_doctor)
        # Parse the source for _LINTERS_DOC list literal
        # We look for the list of tuples starting with _LINTERS_DOC
        lines = src.splitlines()
        start = next(i for i, l in enumerate(lines) if "_LINTERS_DOC" in l and "=" in l)
        end = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == "]")
        block = "\n".join(lines[start:end + 1])
        block = block.replace("_LINTERS_DOC = [", "[")
        # Strip trailing comma issues
        result = []
        for line in lines[start + 1:end]:
            line = line.strip()
            if line.startswith("(") and line.endswith("),"):
                parts = line[1:-2].split(",")
                if len(parts) >= 3:
                    result.append(tuple(p.strip().strip('"').strip("'") for p in parts))
        return result

    def test_splint_in_linters_doc(self):
        from ui.commands import _cmd_doctor
        import inspect
        src = inspect.getsource(_cmd_doctor)
        assert "splint" in src

    def test_rpmlint_in_linters_doc(self):
        from ui.commands import _cmd_doctor
        import inspect
        src = inspect.getsource(_cmd_doctor)
        assert "rpmlint" in src

    def test_jsonlint_in_linters_doc(self):
        from ui.commands import _cmd_doctor
        import inspect
        src = inspect.getsource(_cmd_doctor)
        assert "jsonlint" in src

    def test_ansible_lint_in_linters_doc(self):
        from ui.commands import _cmd_doctor
        import inspect
        src = inspect.getsource(_cmd_doctor)
        assert "ansible-lint" in src

    def test_gitlint_in_linters_doc(self):
        from ui.commands import _cmd_doctor
        import inspect
        src = inspect.getsource(_cmd_doctor)
        assert "gitlint" in src

    def test_efm_langserver_in_linters_doc(self):
        from ui.commands import _cmd_doctor
        import inspect
        src = inspect.getsource(_cmd_doctor)
        assert "efm-langserver" in src

    def test_efm_langserver_in_lsp_install(self):
        from ui.commands import _cmd_doctor
        import inspect
        src = inspect.getsource(_cmd_doctor)
        assert "efm-langserver" in src
        assert "apt install efm-langserver" in src


# ─────────────────────────────────────────────────────────────────────────────
# Permissions
# ─────────────────────────────────────────────────────────────────────────────

class TestPermissions:
    def test_gitlint_check_has_permission(self):
        from config import DEFAULT_CONFIG
        assert "gitlint_check" in DEFAULT_CONFIG["permissions"]

    def test_ansible_lint_has_permission(self):
        from config import DEFAULT_CONFIG
        assert "ansible_lint" in DEFAULT_CONFIG["permissions"]

    def test_efm_config_update_has_permission(self):
        from config import DEFAULT_CONFIG
        assert "efm_config_update" in DEFAULT_CONFIG["permissions"]

    def test_gitlint_permission_is_auto(self):
        from config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["permissions"]["gitlint_check"] == "auto"

    def test_ansible_lint_permission_is_auto(self):
        from config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["permissions"]["ansible_lint"] == "auto"

    def test_efm_config_update_permission_is_auto(self):
        from config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["permissions"]["efm_config_update"] == "auto"

    def test_all_mcp_tools_have_permission(self):
        from mcp_servers.oocode_assistant import _TOOLS
        from config import DEFAULT_CONFIG
        perms = DEFAULT_CONFIG["permissions"]
        missing = [t["name"] for t in _TOOLS if t["name"] not in perms]
        assert missing == [], f"Tools sin permiso: {missing}"


# ─────────────────────────────────────────────────────────────────────────────
# Tool / Prompt / Resource counts
# ─────────────────────────────────────────────────────────────────────────────

class TestCounts:
    def test_total_tools_count(self):
        from mcp_servers.oocode_assistant import _TOOLS
        assert len(_TOOLS) == 120, f"Se esperaban 120 tools, hay {len(_TOOLS)}"

    def test_total_prompts_count(self):
        from mcp_servers.oocode_assistant import _PROMPTS
        assert len(_PROMPTS) == 45, f"Se esperaban 45 prompts, hay {len(_PROMPTS)}"

    def test_total_resources_count(self):
        from mcp_servers.oocode_assistant import _RESOURCES
        assert len(_RESOURCES) == 25, f"Se esperaban 25 resources, hay {len(_RESOURCES)}"
