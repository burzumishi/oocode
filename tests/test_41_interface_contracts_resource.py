"""Tests for interface_contracts MCP resource and /new snapshot reset."""
import textwrap
import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ---------------------------------------------------------------------------
# Resource registration
# ---------------------------------------------------------------------------

class TestInterfaceContractsResourceRegistration:
    def test_resource_in_resources_list(self):
        from mcp_servers.oocode_assistant import _RESOURCES
        uris = [r["uri"] for r in _RESOURCES]
        assert "project://interface_contracts" in uris

    def test_resource_fn_registered(self):
        from mcp_servers.oocode_assistant import _RESOURCE_FNS
        assert "project://interface_contracts" in _RESOURCE_FNS

    def test_resource_mime_type(self):
        from mcp_servers.oocode_assistant import _RESOURCES
        r = next(r for r in _RESOURCES if r["uri"] == "project://interface_contracts")
        assert r["mimeType"] == "text/plain"

    def test_resource_has_description(self):
        from mcp_servers.oocode_assistant import _RESOURCES
        r = next(r for r in _RESOURCES if r["uri"] == "project://interface_contracts")
        assert len(r["description"]) > 20

    def test_total_resources_25(self):
        from mcp_servers.oocode_assistant import _RESOURCES
        assert len(_RESOURCES) == 25

    def test_resource_fns_match_resources(self):
        from mcp_servers.oocode_assistant import _RESOURCES, _RESOURCE_FNS
        for r in _RESOURCES:
            assert r["uri"] in _RESOURCE_FNS, f"Missing handler for {r['uri']}"


# ---------------------------------------------------------------------------
# _resource_interface_contracts — functional tests
# ---------------------------------------------------------------------------

class TestInterfaceContractsContent:
    def test_returns_string(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from mcp_servers.oocode_assistant import _resource_interface_contracts
        result = _resource_interface_contracts()
        assert isinstance(result, str)

    def test_empty_dir_returns_no_symbols_msg(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from mcp_servers.oocode_assistant import _resource_interface_contracts
        result = _resource_interface_contracts()
        assert "Sin símbolos públicos" in result or "Sin interfaces" in result

    def test_finds_public_functions(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # Create multiple .py files that all reference 'process'
        for i in range(4):
            f = tmp_path / f"module_{i}.py"
            f.write_text(f"from core import process\nprocess()\n")
        core = tmp_path / "core.py"
        core.write_text("def process(data=None):\n    pass\n")
        from mcp_servers.oocode_assistant import _resource_interface_contracts
        result = _resource_interface_contracts()
        assert "process" in result

    def test_excludes_private_symbols(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        for i in range(4):
            f = tmp_path / f"module_{i}.py"
            f.write_text("from core import _private\n_private()\n")
        core = tmp_path / "core.py"
        core.write_text("def _private(): pass\n")
        from mcp_servers.oocode_assistant import _resource_interface_contracts
        result = _resource_interface_contracts()
        # _private should not appear as a stable interface
        assert "_private" not in result or "Sin interfaces" in result

    def test_header_contains_directory(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        core = tmp_path / "core.py"
        core.write_text("def run(): pass\n")
        from mcp_servers.oocode_assistant import _resource_interface_contracts
        result = _resource_interface_contracts()
        # The header always appears even when empty
        assert str(tmp_path) in result or "Sin" in result

    def test_class_included(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        core = tmp_path / "engine.py"
        core.write_text("class Engine:\n    def run(self): pass\n")
        for i in range(4):
            f = tmp_path / f"user_{i}.py"
            f.write_text("from engine import Engine\nEngine()\n")
        from mcp_servers.oocode_assistant import _resource_interface_contracts
        result = _resource_interface_contracts()
        assert "Engine" in result

    def test_shows_file_count(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        core = tmp_path / "api.py"
        core.write_text("def fetch(url): pass\n")
        for i in range(5):
            f = tmp_path / f"client_{i}.py"
            f.write_text("from api import fetch\nfetch('x')\n")
        from mcp_servers.oocode_assistant import _resource_interface_contracts
        result = _resource_interface_contracts()
        assert "ficheros" in result


# ---------------------------------------------------------------------------
# /new resets icd_snapshots and suite_snapshot
# ---------------------------------------------------------------------------

class TestNewResetsSnapshots:
    def test_new_calls_reset_icd_snapshots(self):
        from tools.hooks import _icd_snapshots, reset_icd_snapshots
        _icd_snapshots["fake_path"] = "fake_content"
        assert len(_icd_snapshots) > 0

        from ui.commands import _cmd_new
        mock_loop = MagicMock()
        mock_loop.session.session_id = "abcdef1234567890"
        mock_loop.new_session.return_value = None
        with patch("ui.commands.console"):
            _cmd_new(mock_loop)

        assert len(_icd_snapshots) == 0

    def test_new_calls_reset_suite_snapshot(self):
        import tools.hooks as _hmod
        _hmod._suite_snapshot = {"fake_test::test_x": "PASSED"}
        assert _hmod._suite_snapshot is not None

        from ui.commands import _cmd_new
        mock_loop = MagicMock()
        mock_loop.session.session_id = "abcdef1234567890"
        mock_loop.new_session.return_value = None
        with patch("ui.commands.console"):
            _cmd_new(mock_loop)

        assert _hmod._suite_snapshot is None
