"""Tests para la paridad de servidores MCP bundled entre TUI y WebUI.

Regresión: el WebUI (webui/sessions.py) solo arrancaba 5 de los 8 servidores MCP
bundled — faltaban devops/database/http-client. devops-assistant está activo por
defecto (66 tools git/docker/fs), así que el WebUI se quedaba sin esas tools mientras
el TUI sí las cargaba. Fix: helper único agent/services.bundled_mcp_servers usado por
ambos arranques.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from config import OOConfig
from agent.services import bundled_mcp_servers, _BUNDLED_MCP


# Los 8 servidores bundled documentados en CLAUDE.md
_EXPECTED_8 = {
    "oocode-assistant", "system-assistant", "devops-assistant", "database-assistant",
    "home-office-assistant", "security-assistant", "iot-assistant", "http-client-assistant",
}


class TestBundledMcpHelper:

    def test_all_eight_servers_registered(self):
        names = {name for _, name, _ in _BUNDLED_MCP}
        assert names == _EXPECTED_8

    def test_each_has_config_flag(self):
        c = OOConfig()
        for flag_attr, name, fname in _BUNDLED_MCP:
            assert hasattr(c, flag_attr), f"falta flag {flag_attr} para {name}"

    def test_each_server_file_exists(self):
        c = OOConfig()
        for flag_attr in (a for a, _, _ in _BUNDLED_MCP):
            setattr(c, flag_attr, True)
        got = bundled_mcp_servers(c)
        assert len(got) == 8, [s["name"] for s in got]

    def test_defaults_include_devops(self):
        """devops-assistant está activo por defecto y DEBE arrancar."""
        c = OOConfig()
        got = {s["name"] for s in bundled_mcp_servers(c)}
        assert "devops-assistant" in got
        assert {"oocode-assistant", "system-assistant", "devops-assistant"} <= got

    def test_disabled_servers_excluded(self):
        c = OOConfig()
        # database está desactivado por defecto
        got = {s["name"] for s in bundled_mcp_servers(c)}
        assert "database-assistant" not in got

    def test_dedup_against_existing(self):
        c = OOConfig()
        got = bundled_mcp_servers(c, {"devops-assistant"})
        names = [s["name"] for s in got]
        assert "devops-assistant" not in names  # ya listado por el usuario

    def test_cmd_shape(self):
        c = OOConfig()
        srv = bundled_mcp_servers(c)[0]
        assert srv["name"] and isinstance(srv["cmd"], list)
        assert srv["cmd"][0] == sys.executable
        assert srv["cmd"][1].endswith(".py")


class TestWebuiConfigCoverage:
    """El endpoint de config del WebUI expone y persiste los 8 flags MCP."""

    def test_get_config_exposes_all_flags(self):
        import webui.api_config as ac
        src = open(ac.__file__).read()
        for flag_attr, _, _ in _BUNDLED_MCP:
            assert f'"{flag_attr}"' in src, f"GET config no expone {flag_attr}"

    def test_set_config_persists_all_flags(self):
        import webui.api_config as ac
        src = open(ac.__file__).read()
        # _bool("<flag>", "<flag>") debe existir para cada servidor
        for flag_attr, _, _ in _BUNDLED_MCP:
            assert f'_bool("{flag_attr}"' in src, f"SET config no persiste {flag_attr}"

    def test_config_page_lists_all_flags(self):
        import webui.page_config as pc
        src = open(pc.__file__).read()
        for flag_attr, _, _ in _BUNDLED_MCP:
            assert flag_attr in src, f"page_config no lista {flag_attr}"


def test_tui_and_webui_use_same_helper():
    """Tanto oocode.py (TUI) como webui/sessions.py importan el helper compartido."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for fn in ("oocode.py", "webui/sessions.py"):
        src = open(os.path.join(root, fn)).read()
        assert "bundled_mcp_servers" in src, f"{fn} no usa el helper compartido"
