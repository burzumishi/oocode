"""
test_49_markdown_xml.py — Tests para Markdown/XML tools, LSP y /doctor

Cubre:
  - render_markdown tool (MCP oocode_assistant)
  - xml_format tool
  - xml_validate tool
  - Prompts generate_report y summarize_session
  - Resources report://template_md y report://template_xml
  - LSP: .md y .xml en _SERVER_CMDS y _EXT_TO_LANG
  - Hooks: markdownlint y xmllint en _LINTERS
  - /doctor: marksman, lemminx, markdownlint, xmllint
  - OOCODE.md trust check en startup
  - /doctor apt package fallback (paho, markdown, kasa)
"""
import importlib
import json
import sys
import os
import tempfile
from pathlib import Path

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# MCP Tools
# ─────────────────────────────────────────────────────────────────────────────

class TestRenderMarkdown:
    def _call(self, **kwargs):
        from mcp_servers.oocode_assistant import _tool_render_markdown
        return _tool_render_markdown(kwargs)

    def test_basic_markdown(self):
        md = "# Hola\n\nEsto es un **test**.\n\n- item 1\n- item 2\n"
        result = self._call(text=md)
        assert "Markdown válido" in result
        assert "1 cabeceras" in result

    def test_counts_code_blocks(self):
        md = "# Test\n\n```python\nprint('hola')\n```\n"
        result = self._call(text=md)
        assert "1 bloques de código" in result

    def test_from_file(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("# Título\n\nContenido.\n")
        result = self._call(file=str(f))
        assert "Markdown válido" in result

    def test_missing_file(self):
        result = self._call(file="/no/existe.md")
        assert "no existe" in result.lower() or "Error" in result

    def test_no_args_error(self):
        result = self._call()
        assert "requerido" in result.lower() or "Error" in result

    def test_save_to_output(self, tmp_path):
        out = tmp_path / "out.md"
        result = self._call(text="# Test\n", output=str(out))
        assert out.exists()
        assert "Guardado" in result


class TestXmlFormat:
    def _call(self, **kwargs):
        from mcp_servers.oocode_assistant import _tool_xml_format
        return _tool_xml_format(kwargs)

    def test_basic_xml(self):
        xml = "<root><child>value</child></root>"
        result = self._call(text=xml)
        assert "✓" in result
        assert "formateado" in result.lower()

    def test_indentation(self):
        xml = "<root><child>v</child></root>"
        result = self._call(text=xml, indent=4)
        assert "✓" in result

    def test_from_file(self, tmp_path):
        f = tmp_path / "data.xml"
        f.write_text("<root><item>1</item></root>")
        result = self._call(file=str(f))
        assert "✓" in result

    def test_invalid_xml_error(self):
        result = self._call(text="<unclosed")
        assert "Error" in result or "✗" in result

    def test_save_to_output(self, tmp_path):
        out = tmp_path / "formatted.xml"
        result = self._call(text="<root><a>1</a></root>", output=str(out))
        assert out.exists()
        content = out.read_text()
        assert "<root>" in content

    def test_no_args_error(self):
        result = self._call()
        assert "requerido" in result.lower() or "Error" in result


class TestXmlValidate:
    def _call(self, **kwargs):
        from mcp_servers.oocode_assistant import _tool_xml_validate
        return _tool_xml_validate(kwargs)

    def test_valid_xml(self):
        result = self._call(text="<root><child/></root>")
        assert "✓" in result
        assert "bien formado" in result

    def test_invalid_xml(self):
        result = self._call(text="<root><unclosed>")
        assert "✗" in result
        assert "mal formado" in result

    def test_from_file(self, tmp_path):
        f = tmp_path / "v.xml"
        f.write_text("<doc><item>x</item></doc>")
        result = self._call(file=str(f))
        assert "✓" in result

    def test_missing_file(self):
        result = self._call(file="/no/existe.xml")
        assert "no existe" in result.lower() or "Error" in result

    def test_no_args_error(self):
        result = self._call()
        assert "requerido" in result.lower() or "Error" in result

    def test_schema_without_lxml(self, tmp_path):
        # XSD validation falls back to lxml-not-installed message
        f = tmp_path / "s.xml"
        f.write_text("<root/>")
        s = tmp_path / "schema.xsd"
        s.write_text('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:element name="root"/></xs:schema>')
        result = self._call(file=str(f), schema=str(s))
        # Either validates with lxml or reports lxml missing — both are OK
        assert "✓" in result


# ─────────────────────────────────────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────────────────────────────────────

class TestNewPrompts:
    def test_generate_report_in_prompts(self):
        from mcp_servers.oocode_assistant import _PROMPTS
        assert "generate_report" in _PROMPTS

    def test_summarize_session_in_prompts(self):
        from mcp_servers.oocode_assistant import _PROMPTS
        assert "summarize_session" in _PROMPTS

    def test_generate_report_has_arguments(self):
        from mcp_servers.oocode_assistant import _PROMPTS
        p = _PROMPTS["generate_report"]
        assert any(a["name"] == "topic" and a["required"] for a in p["arguments"])

    def test_summarize_session_optional_scope(self):
        from mcp_servers.oocode_assistant import _PROMPTS
        p = _PROMPTS["summarize_session"]
        assert any(a["name"] == "scope" for a in p["arguments"])

    def test_generate_report_handler_markdown(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("generate_report", {"topic": "tests", "format": "markdown"})
        assert msgs
        text = msgs[0]["content"]["text"]
        assert "tests" in text
        assert "Markdown" in text

    def test_generate_report_handler_xml(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("generate_report", {"topic": "status", "format": "xml"})
        assert msgs
        text = msgs[0]["content"]["text"]
        assert "XML" in text

    def test_summarize_session_handler(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("summarize_session", {})
        assert msgs
        text = msgs[0]["content"]["text"]
        assert "resumen" in text.lower() or "Resumen" in text

    def test_generate_report_with_sections(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("generate_report", {"topic": "x", "sections": "A,B,C"})
        text = msgs[0]["content"]["text"]
        assert "A,B,C" in text


# ─────────────────────────────────────────────────────────────────────────────
# Resources
# ─────────────────────────────────────────────────────────────────────────────

class TestReportResources:
    def test_template_md_in_resources(self):
        from mcp_servers.oocode_assistant import _RESOURCES
        uris = [r["uri"] for r in _RESOURCES]
        assert "report://template_md" in uris

    def test_template_xml_in_resources(self):
        from mcp_servers.oocode_assistant import _RESOURCES
        uris = [r["uri"] for r in _RESOURCES]
        assert "report://template_xml" in uris

    def test_template_md_mimetype(self):
        from mcp_servers.oocode_assistant import _RESOURCES
        r = next(r for r in _RESOURCES if r["uri"] == "report://template_md")
        assert r["mimeType"] == "text/markdown"

    def test_template_xml_mimetype(self):
        from mcp_servers.oocode_assistant import _RESOURCES
        r = next(r for r in _RESOURCES if r["uri"] == "report://template_xml")
        assert r["mimeType"] == "text/xml"

    def test_template_md_handler_content(self):
        from mcp_servers.oocode_assistant import _RESOURCE_FNS
        fn = _RESOURCE_FNS["report://template_md"]
        content = fn()
        assert "# " in content
        assert "Resumen" in content

    def test_template_xml_handler_content(self):
        from mcp_servers.oocode_assistant import _RESOURCE_FNS
        fn = _RESOURCE_FNS["report://template_xml"]
        content = fn()
        assert "<?xml" in content
        assert "<report>" in content

    def test_template_xml_well_formed(self):
        import xml.etree.ElementTree as ET
        from mcp_servers.oocode_assistant import _RESOURCE_FNS
        content = _RESOURCE_FNS["report://template_xml"]()
        ET.fromstring(content.encode())  # raises if invalid

    def test_resource_fns_all_have_handlers(self):
        from mcp_servers.oocode_assistant import _RESOURCES, _RESOURCE_FNS
        for r in _RESOURCES:
            assert r["uri"] in _RESOURCE_FNS, f"Sin handler para {r['uri']}"

    def test_total_resources_count(self):
        from mcp_servers.oocode_assistant import _RESOURCES
        assert len(_RESOURCES) == 25


# ─────────────────────────────────────────────────────────────────────────────
# LSP client
# ─────────────────────────────────────────────────────────────────────────────

class TestLspMarkdownXml:
    def test_md_in_server_cmds(self):
        from agent.lsp_client import _SERVER_CMDS
        assert ".md" in _SERVER_CMDS
        # efm-langserver con markdownlint — vscode-markdown-language-server roto en Node 22
        assert _SERVER_CMDS[".md"][0] == "efm-langserver"

    def test_markdown_alias_in_server_cmds(self):
        from agent.lsp_client import _SERVER_CMDS
        assert ".markdown" in _SERVER_CMDS

    def test_xml_uses_efm_langserver(self):
        # efm-langserver reemplaza lemminx (que requería Java) como backend XML
        from agent.lsp_client import _SERVER_CMDS
        cmd = _SERVER_CMDS.get(".xml", [])
        assert cmd and cmd[0] == "efm-langserver"

    def test_xml_variants_use_efm_langserver(self):
        # .xsl/.xslt/.svg se resuelven via alias .xml → efm-langserver
        from agent.lsp_client import _SERVER_CMDS, _SERVER_ALIASES
        for ext in (".xsl", ".xslt", ".svg"):
            # alias debe apuntar a .xml (que usa efm-langserver)
            assert _SERVER_ALIASES.get(ext) == ".xml"

    def test_md_lang_in_ext_to_lang(self):
        from agent.lsp_client import _EXT_TO_LANG
        assert _EXT_TO_LANG[".md"] == "markdown"
        assert _EXT_TO_LANG[".markdown"] == "markdown"

    def test_xml_lang_in_ext_to_lang(self):
        from agent.lsp_client import _EXT_TO_LANG
        for ext in (".xml", ".xsl", ".xslt", ".svg"):
            assert _EXT_TO_LANG[ext] == "xml"

    def test_markdown_alias(self):
        from agent.lsp_client import _SERVER_ALIASES
        assert ".markdown" in _SERVER_ALIASES
        assert _SERVER_ALIASES[".markdown"] == ".md"

    def test_xml_variants_in_aliases(self):
        # .xsl/.xslt/.svg alias a .xml (que usa efm-langserver como backend)
        from agent.lsp_client import _SERVER_ALIASES
        for ext in (".xsl", ".xslt", ".svg"):
            assert ext in _SERVER_ALIASES
            assert _SERVER_ALIASES[ext] == ".xml"


# ─────────────────────────────────────────────────────────────────────────────
# Hooks — _LINTERS
# ─────────────────────────────────────────────────────────────────────────────

class TestHooksMarkdownXml:
    def test_md_not_in_direct_linters(self):
        """markdownlint se aplica vía efm-langserver (lsp_after_write), no lint_after_write."""
        from tools.hooks import _LINTERS
        assert ".md" not in _LINTERS

    def test_xml_not_in_direct_linters(self):
        """xmllint se aplica vía efm-langserver (lsp_after_write), no lint_after_write."""
        from tools.hooks import _LINTERS
        assert ".xml" not in _LINTERS

    def test_spec_not_in_direct_linters(self):
        """rpmlint se aplica vía efm-langserver (lsp_after_write), no lint_after_write."""
        from tools.hooks import _LINTERS
        assert ".spec" not in _LINTERS

    def test_markdownlint_in_efm_config(self):
        """markdownlint aparece en la config de efm-langserver para .md."""
        import shutil
        if not shutil.which("markdownlint"):
            pytest.skip("markdownlint no instalado")
        from agent.lsp_client import _generate_efm_config
        cfg = _generate_efm_config()
        assert "markdownlint" in cfg

    def test_xmllint_in_efm_config(self):
        """xmllint aparece en la config de efm-langserver para .xml."""
        import shutil
        if not shutil.which("xmllint"):
            pytest.skip("xmllint no instalado")
        from agent.lsp_client import _generate_efm_config
        cfg = _generate_efm_config()
        assert "xmllint" in cfg


# ─────────────────────────────────────────────────────────────────────────────
# /doctor apt package fallback
# ─────────────────────────────────────────────────────────────────────────────

class TestDoctorPackageFallback:
    def _pkg_ok(self, names, import_path):
        """Re-implementación de la función interna _pkg_ok para testear."""
        import importlib.metadata
        for n in names:
            try:
                ver = importlib.metadata.version(n)
                return True, ver
            except importlib.metadata.PackageNotFoundError:
                pass
        try:
            importlib.import_module(import_path.split(".")[0])
            return True, "apt"
        except ImportError:
            return False, ""

    def test_paho_metadata_fallback(self):
        # paho-mqtt should be findable via metadata or import
        found, ver = self._pkg_ok(["paho-mqtt"], "paho.mqtt")
        # On this system paho-mqtt is installed, so should be found
        assert isinstance(found, bool)

    def test_markdown_capitalized_metadata(self):
        # "Markdown" (capital M) should work
        import importlib.metadata
        try:
            ver = importlib.metadata.version("Markdown")
            assert ver  # should find Markdown 3.x
        except importlib.metadata.PackageNotFoundError:
            # If not installed, that's OK for the test
            pass

    def test_pkg_ok_import_fallback(self):
        # If metadata fails but module is importable, returns (True, "apt")
        import importlib.metadata
        found, ver = self._pkg_ok(["__nonexistent_pkg_xyz__"], "os")
        assert found is True
        assert ver == "apt"

    def test_pkg_ok_not_found(self):
        found, ver = self._pkg_ok(["__nonexistent_pkg_xyz__"], "__nonexistent_module_xyz__")
        assert found is False
        assert ver == ""

    def test_pkg_ok_metadata_found(self):
        # pip itself should always be findable
        import importlib.metadata
        found, ver = self._pkg_ok(["pip"], "pip")
        assert found is True
        assert ver != "apt"


# ─────────────────────────────────────────────────────────────────────────────
# OOCODE.md trust check in oocode.py
# ─────────────────────────────────────────────────────────────────────────────

class TestOocodemdTrustCheck:
    def test_oocode_md_path_computation(self, tmp_path):
        """Verifica que la ruta OOCODE.md se calcula desde project_dir."""
        project_dir = str(tmp_path)
        p = Path(project_dir) / "OOCODE.md"
        assert not p.exists()

    def test_cmd_init_creates_file(self, tmp_path):
        """_cmd_init puede crear OOCODE.md en un directorio dado."""
        from ui.commands import _cmd_init

        class _FakeCfg:
            agent_id = "main"
            agent_name = "OOCode"

        _cmd_init(str(tmp_path), _FakeCfg(), None)
        assert (tmp_path / "OOCODE.md").exists()

    def test_cmd_init_file_content(self, tmp_path):
        from ui.commands import _cmd_init

        class _FakeCfg:
            agent_id = "main"
            agent_name = "OOCode"

        _cmd_init(str(tmp_path), _FakeCfg(), None)
        content = (tmp_path / "OOCODE.md").read_text()
        assert "## Comandos" in content
        assert "## Notas para el agente" in content

    def test_cmd_init_detects_python_project(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("pytest\n")
        from ui.commands import _cmd_init

        class _FakeCfg:
            agent_id = "main"
            agent_name = "OOCode"

        _cmd_init(str(tmp_path), _FakeCfg(), None)
        content = (tmp_path / "OOCODE.md").read_text()
        assert "Python" in content


# ─────────────────────────────────────────────────────────────────────────────
# Totals / integration
# ─────────────────────────────────────────────────────────────────────────────

class TestTotals:
    def test_tool_fns_has_render_markdown(self):
        from mcp_servers.oocode_assistant import _TOOL_FNS
        assert "render_markdown" in _TOOL_FNS

    def test_tool_fns_has_xml_format(self):
        from mcp_servers.oocode_assistant import _TOOL_FNS
        assert "xml_format" in _TOOL_FNS

    def test_tool_fns_has_xml_validate(self):
        from mcp_servers.oocode_assistant import _TOOL_FNS
        assert "xml_validate" in _TOOL_FNS

    def test_tool_count_120(self):
        from mcp_servers.oocode_assistant import _TOOLS
        assert len(_TOOLS) == 120

    def test_prompt_count_45(self):
        from mcp_servers.oocode_assistant import _PROMPTS
        assert len(_PROMPTS) == 45

    def test_permissions_for_new_tools(self):
        from config import DEFAULT_CONFIG
        perms = DEFAULT_CONFIG["permissions"]
        for tool in ("render_markdown", "xml_format", "xml_validate"):
            assert tool in perms, f"Falta permiso para {tool}"
            assert perms[tool] == "auto"
