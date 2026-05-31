"""Tests de soporte PHP: LSP, linters, formateador y prompt php_workflow.

Cubre:
- .php en _LSP_DIAG_EXTS y _AUTOFORMAT_EXTS (hooks.py)
- .php en _LINTERS (hooks.py y mcp_server)
- format_code auto-detect para .php → php-cs-fixer
- Prompt php_workflow registrado y con contenido correcto
- Guía LSP contiene sección PHP
- lint_file responde a .php (llama php -l / phpcs / phpstan)

No requiere LLM ni conexión de red.
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── hooks.py — extensiones PHP ────────────────────────────────────────────────

class TestHooksPhpExtensions:
    def test_php_in_lsp_diag_exts(self):
        from tools.hooks import _LSP_DIAG_EXTS
        assert ".php" in _LSP_DIAG_EXTS

    def test_php_in_autoformat_exts(self):
        from tools.hooks import _AUTOFORMAT_EXTS
        assert ".php" in _AUTOFORMAT_EXTS

    def test_php_in_linters(self):
        from tools.hooks import _LINTERS
        assert ".php" in _LINTERS

    def test_php_linter_uses_php_minus_l(self):
        from tools.hooks import _LINTERS
        cmds = _LINTERS[".php"]
        assert any(cmd[0] == "php" and "-l" in cmd for cmd in cmds)

    def test_php_linter_uses_phpcs(self):
        from tools.hooks import _LINTERS
        cmds = _LINTERS[".php"]
        assert any(cmd[0] == "phpcs" for cmd in cmds)

    def test_php_linter_phpcs_standard_psr12(self):
        from tools.hooks import _LINTERS
        cmds = _LINTERS[".php"]
        phpcs_cmd = next(c for c in cmds if c[0] == "phpcs")
        assert any("PSR12" in arg for arg in phpcs_cmd)

    def test_lsp_after_write_triggers_for_php(self):
        """Verifica que el hook lsp_after_write pasa el filtro de extensión para .php."""
        from tools.hooks import _LSP_DIAG_EXTS
        assert ".php" in _LSP_DIAG_EXTS

    def test_autoformat_after_write_triggers_for_php(self):
        from tools.hooks import _AUTOFORMAT_EXTS
        assert ".php" in _AUTOFORMAT_EXTS


# ── MCP _LINTERS — PHP ────────────────────────────────────────────────────────

class TestMcpPhpLinters:
    def test_php_in_mcp_linters(self):
        from mcp_servers.oocode_assistant import _LINTERS
        assert ".php" in _LINTERS

    def test_mcp_php_linter_php_minus_l(self):
        from mcp_servers.oocode_assistant import _LINTERS
        cmds = _LINTERS[".php"]
        assert any(c[0] == "php" and "-l" in c for c in cmds)

    def test_mcp_php_linter_phpcs(self):
        from mcp_servers.oocode_assistant import _LINTERS
        cmds = _LINTERS[".php"]
        assert any(c[0] == "phpcs" for c in cmds)

    def test_mcp_php_linter_phpstan(self):
        from mcp_servers.oocode_assistant import _LINTERS
        cmds = _LINTERS[".php"]
        assert any(c[0] == "phpstan" for c in cmds)

    def test_mcp_php_phpstan_level(self):
        from mcp_servers.oocode_assistant import _LINTERS
        cmds = _LINTERS[".php"]
        phpstan_cmd = next(c for c in cmds if c[0] == "phpstan")
        assert "--level=5" in phpstan_cmd

    def test_lint_file_recognizes_php(self):
        from mcp_servers.oocode_assistant import _LINTERS
        assert _LINTERS.get(".php") is not None
        assert len(_LINTERS[".php"]) >= 2


# ── MCP lint_file con .php ────────────────────────────────────────────────────

class TestMcpLintFilePhp:
    @pytest.fixture
    def php_file(self, tmp_path_factory):
        d = tmp_path_factory.mktemp("php")
        f = d / "test.php"
        f.write_text("<?php\necho 'hello';\n")
        return f

    def test_lint_file_php_no_crash_without_linters(self, php_file):
        from mcp_servers.oocode_assistant import _tool_lint_file
        with patch("shutil.which", return_value=None):
            result = _tool_lint_file({"path": str(php_file)})
        assert "php" in result.lower() or "linter" in result.lower() or "Ningún" in result

    def test_lint_file_php_calls_php_minus_l(self, php_file):
        from mcp_servers.oocode_assistant import _tool_lint_file
        calls = []
        original_run = __import__("subprocess").Popen

        def fake_popen(cmd, **kwargs):
            calls.append(cmd)
            m = MagicMock()
            m.communicate.return_value = ("No syntax errors detected", None)
            m.returncode = 0
            return m

        with patch("shutil.which", return_value="/usr/bin/php"), \
             patch("subprocess.Popen", side_effect=fake_popen):
            _tool_lint_file({"path": str(php_file)})

        assert any(c[0] == "php" for c in calls)

    def test_lint_file_php_syntax_error_detected(self, tmp_path_factory):
        d = tmp_path_factory.mktemp("php_err")
        f = d / "bad.php"
        f.write_text("<?php\nfunction broken( {}\n")
        from mcp_servers.oocode_assistant import _tool_lint_file
        # php -l real si está disponible
        import shutil
        if not shutil.which("php"):
            pytest.skip("php no instalado")
        result = _tool_lint_file({"path": str(f)})
        assert "php" in result.lower()


# ── format_code auto-detect PHP ───────────────────────────────────────────────

class TestFormatCodePhp:
    @pytest.fixture
    def php_file(self, tmp_path_factory):
        d = tmp_path_factory.mktemp("fmt_php")
        f = d / "app.php"
        f.write_text("<?php\n  echo 'hello' ;\n")
        return f

    def test_format_code_auto_detects_php_cs_fixer(self, php_file):
        from mcp_servers.oocode_assistant import _tool_format_code
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = _tool_format_code({"path": str(php_file), "tool": "auto"})
        # Debe haber llamado con php-cs-fixer
        assert mock_run.called
        cmd = mock_run.call_args[0][0]
        assert "php-cs-fixer" in cmd

    def test_format_code_php_check_mode(self, php_file):
        from mcp_servers.oocode_assistant import _tool_format_code
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            _tool_format_code({"path": str(php_file), "tool": "php-cs-fixer", "check": True})
        cmd = mock_run.call_args[0][0]
        assert "--dry-run" in cmd

    def test_format_code_php_not_installed(self, php_file):
        from mcp_servers.oocode_assistant import _tool_format_code
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = _tool_format_code({"path": str(php_file), "tool": "php-cs-fixer"})
        assert "no está instalado" in result or "Error" in result

    def test_format_code_php_uses_psr12(self, php_file):
        from mcp_servers.oocode_assistant import _tool_format_code
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            _tool_format_code({"path": str(php_file), "tool": "php-cs-fixer"})
        cmd = mock_run.call_args[0][0]
        assert any("PSR12" in arg for arg in cmd)


# ── Prompt php_workflow ───────────────────────────────────────────────────────

class TestPhpWorkflowPrompt:
    def test_php_workflow_registered(self):
        from mcp_servers.oocode_assistant import _PROMPTS
        assert "php_workflow" in _PROMPTS

    def test_php_workflow_has_description(self):
        from mcp_servers.oocode_assistant import _PROMPTS
        desc = _PROMPTS["php_workflow"]["description"]
        assert "PHP" in desc
        assert "intelephense" in desc

    def test_php_workflow_has_required_task_arg(self):
        from mcp_servers.oocode_assistant import _PROMPTS
        args = _PROMPTS["php_workflow"]["arguments"]
        task_arg = next((a for a in args if a["name"] == "task"), None)
        assert task_arg is not None
        assert task_arg.get("required") is True

    def test_php_workflow_has_file_arg(self):
        from mcp_servers.oocode_assistant import _PROMPTS
        args = _PROMPTS["php_workflow"]["arguments"]
        assert any(a["name"] == "file" for a in args)

    def test_php_workflow_has_class_arg(self):
        from mcp_servers.oocode_assistant import _PROMPTS
        args = _PROMPTS["php_workflow"]["arguments"]
        assert any(a["name"] == "class" for a in args)

    def test_php_workflow_get_prompt_returns_messages(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("php_workflow", {"task": "Añadir método a la clase User"})
        assert msgs
        assert msgs[0]["role"] == "user"

    def test_php_workflow_prompt_contains_lsp_tools(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("php_workflow", {"task": "refactorizar"})
        text = msgs[0]["content"]["text"]
        assert "lsp_symbols" in text
        assert "lsp_diagnostics" in text
        assert "lsp_references" in text

    def test_php_workflow_prompt_mentions_lint_file(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("php_workflow", {"task": "arreglar bug"})
        text = msgs[0]["content"]["text"]
        assert "lint_file" in text

    def test_php_workflow_prompt_forbids_grep_bash(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("php_workflow", {"task": "buscar uso"})
        text = msgs[0]["content"]["text"]
        assert "grep -rn" in text or "NUNCA" in text

    def test_php_workflow_prompt_with_file_hint(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("php_workflow", {
            "task": "añadir validación",
            "file": "/var/www/src/User.php",
        })
        text = msgs[0]["content"]["text"]
        assert "User.php" in text

    def test_php_workflow_prompt_mentions_psr_or_phpdoc(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("php_workflow", {"task": "documentar"})
        text = msgs[0]["content"]["text"]
        assert "PHPDoc" in text or "PSR" in text or "namespace" in text

    def test_php_workflow_mentions_phpcs_and_phpstan(self):
        from mcp_servers.oocode_assistant import _get_prompt
        msgs = _get_prompt("php_workflow", {"task": "lint"})
        text = msgs[0]["content"]["text"]
        assert "phpcs" in text or "phpstan" in text


# ── Guía LSP contiene PHP ─────────────────────────────────────────────────────

class TestLspGuidePhp:
    def test_lsp_guide_contains_php_section(self):
        from mcp_servers.oocode_assistant import _resource_lsp_guide
        guide = _resource_lsp_guide()
        assert "PHP" in guide or "php" in guide

    def test_lsp_guide_mentions_intelephense(self):
        from mcp_servers.oocode_assistant import _resource_lsp_guide
        guide = _resource_lsp_guide()
        assert "intelephense" in guide

    def test_lsp_guide_php_mentions_lsp_symbols(self):
        from mcp_servers.oocode_assistant import _resource_lsp_guide
        guide = _resource_lsp_guide()
        # La sección PHP debe mencionar lsp_symbols
        php_idx = guide.lower().find("### php")
        assert php_idx != -1, "No se encontró la sección ### PHP en la guía"
        php_section = guide[php_idx:php_idx + 600]
        assert "lsp_symbols" in php_section

    def test_lsp_guide_php_mentions_lsp_diagnostics(self):
        from mcp_servers.oocode_assistant import _resource_lsp_guide
        guide = _resource_lsp_guide()
        php_idx = guide.lower().find("### php")
        php_section = guide[php_idx:php_idx + 600]
        assert "lsp_diagnostics" in php_section

    def test_lsp_guide_php_mentions_lsp_hover(self):
        from mcp_servers.oocode_assistant import _resource_lsp_guide
        guide = _resource_lsp_guide()
        php_idx = guide.lower().find("### php")
        php_section = guide[php_idx:php_idx + 600]
        assert "lsp_hover" in php_section


# ── lsp_client.py ya tenía PHP — verificar consistencia ──────────────────────

class TestLspClientPhp:
    def test_php_in_server_cmds(self):
        from agent.lsp_client import _SERVER_CMDS
        assert ".php" in _SERVER_CMDS

    def test_php_server_is_intelephense(self):
        from agent.lsp_client import _SERVER_CMDS
        cmd = _SERVER_CMDS[".php"]
        assert cmd[0] == "intelephense"

    def test_php_in_ext_to_lang(self):
        from agent.lsp_client import _EXT_TO_LANG
        assert ".php" in _EXT_TO_LANG
        assert _EXT_TO_LANG[".php"] == "php"
