"""Tests para los subcomandos /mcp en ui/commands.py.

No requiere Ollama, npx ni proceso externo.
Mock completo de console y filesystem.
"""
import json
import inspect
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mocked_console():
    """Parchea ui.commands.console y devuelve el mock."""
    return patch("ui.commands.console")


def _catalog_entry(id_="filesystem", runtime="npx"):
    return {
        "id": id_, "name": f"MCP {id_.title()}",
        "description": f"Servidor {id_}", "package": f"@mcp/{id_}",
        "runtime": runtime,
        "cmd": ["npx", "-y", f"@mcp/{id_}"],
        "example_args": ["/tmp"],
        "note": "Test note",
        "install_hint": f"npm install -g @mcp/{id_}",
        "tags": [id_],
    }


# ── _cmd_mcp_catalog ──────────────────────────────────────────────────────────

class TestCmdMcpCatalog(unittest.TestCase):

    def _call(self, query=""):
        from ui.commands import _cmd_mcp_catalog
        with _mocked_console():
            _cmd_mcp_catalog(query)

    def test_catalog_no_query_runs(self):
        self._call("")  # debe terminar sin excepción

    def test_catalog_query_runs(self):
        self._call("git")

    def test_catalog_unknown_query_prints_no_results(self):
        from ui.commands import _cmd_mcp_catalog
        with _mocked_console() as mc:
            _cmd_mcp_catalog("xyznonexistent999")
        # console.print se llamó con mensaje de "no hay resultados"
        printed = " ".join(str(a) for a, _ in mc.print.call_args_list)
        self.assertIn("No hay resultados", printed)

    def test_catalog_shows_id_column(self):
        """La tabla incluye el ID del servidor (verificado a través de search_catalog)."""
        from agent.mcp_manager import search_catalog
        results = search_catalog("filesystem")
        self.assertTrue(any(s["id"] == "filesystem" for s in results))

    def test_catalog_full_list_non_empty(self):
        from agent.mcp_manager import load_catalog
        self.assertGreater(len(load_catalog()), 0)


# ── _cmd_mcp_check ────────────────────────────────────────────────────────────

class TestCmdMcpCheck(unittest.TestCase):

    def _call(self, id_or_name=""):
        from ui.commands import _cmd_mcp_check
        with _mocked_console():
            _cmd_mcp_check(id_or_name)

    def test_check_empty_shows_usage(self):
        from ui.commands import _cmd_mcp_check
        with _mocked_console() as mc:
            _cmd_mcp_check("")
        printed = " ".join(str(a) for a, _ in mc.print.call_args_list)
        self.assertIn("Uso", printed)

    def test_check_known_id_runs(self):
        self._call("filesystem")  # sin excepción

    def test_check_unknown_id_prints_error(self):
        from ui.commands import _cmd_mcp_check
        with _mocked_console() as mc:
            _cmd_mcp_check("nonexistent-xyz-abc")
        printed = " ".join(str(a) for a, _ in mc.print.call_args_list)
        self.assertIn("no encontrado", printed)

    def test_check_git_shows_name(self):
        from ui.commands import _cmd_mcp_check
        with _mocked_console() as mc:
            _cmd_mcp_check("git")
        printed = " ".join(str(a) for a, _ in mc.print.call_args_list)
        self.assertIn("git", printed.lower())

    def test_check_shows_install_hint_on_missing_runtime(self):
        """Si el runtime no está disponible, debe mostrar el install_hint."""
        fake_catalog = [_catalog_entry("fake-srv", runtime="__fake_rt__")]
        with patch("agent.mcp_manager._CATALOG_PATH") as mp:
            mp.exists.return_value = True
            mp.read_text.return_value = json.dumps(fake_catalog)
            from ui.commands import _cmd_mcp_check
            with _mocked_console() as mc:
                _cmd_mcp_check("fake-srv")
        printed = " ".join(str(a) for a, _ in mc.print.call_args_list)
        # debe mencionar que falta el prerequisito
        self.assertTrue(
            "npm install" in printed or "__fake_rt__" in printed or "Prerequisito" in printed
        )


# ── _cmd_mcp_install ──────────────────────────────────────────────────────────

class TestCmdMcpInstall(unittest.TestCase):

    def _call(self, rest, agent_loop=None, pool=None, config_file=None):
        from ui.commands import _cmd_mcp_install
        loop = agent_loop or MagicMock()
        with _mocked_console(), \
             patch("agent.mcp_manager._CONFIG_FILE",
                   config_file or Path("/tmp/oocode_test_install.json")):
            _cmd_mcp_install(rest, loop, pool)

    def test_install_empty_shows_usage(self):
        from ui.commands import _cmd_mcp_install
        with _mocked_console() as mc:
            _cmd_mcp_install("", MagicMock(), None)
        printed = " ".join(str(a) for a, _ in mc.print.call_args_list)
        self.assertIn("Uso", printed)

    def test_install_unknown_id_shows_error(self):
        from ui.commands import _cmd_mcp_install
        with _mocked_console() as mc:
            _cmd_mcp_install("nonexistent-xyz-abc", MagicMock(), None)
        printed = " ".join(str(a) for a, _ in mc.print.call_args_list)
        self.assertIn("no encontrado", printed)

    def test_install_known_id_without_pool_writes_config(self, tmp_path=None):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg_file = Path(td) / "oocode.json"
            from ui.commands import _cmd_mcp_install
            with _mocked_console(), \
                 patch("agent.mcp_manager._CONFIG_FILE", cfg_file):
                _cmd_mcp_install("memory", MagicMock(), None)
            assert cfg_file.exists(), "oocode.json should be created"
            data = json.loads(cfg_file.read_text())
            servers = data.get("mcp", {}).get("servers", [])
            assert any(s["name"] == "memory" for s in servers), \
                "memory server should be in config"

    def test_install_with_extra_args_passes_through(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg_file = Path(td) / "oocode.json"
            from ui.commands import _cmd_mcp_install
            with _mocked_console(), \
                 patch("agent.mcp_manager._CONFIG_FILE", cfg_file):
                _cmd_mcp_install("filesystem /home/user", MagicMock(), None)
            data = json.loads(cfg_file.read_text())
            servers = data.get("mcp", {}).get("servers", [])
            fs = next((s for s in servers if s["name"] == "filesystem"), None)
            self.assertIsNotNone(fs)
            self.assertIn("/home/user", fs["cmd"])

    def test_install_with_live_pool_calls_hot_add(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg_file = Path(td) / "oocode.json"
            from tools.registry import ToolRegistry
            registry = ToolRegistry()
            loop = MagicMock()
            loop.registry = registry

            mock_pool = MagicMock()
            mock_client = MagicMock()
            mock_client.is_alive = True
            mock_client.tools = []
            mock_client.error = ""
            mock_client._timeout = 15.0
            mock_client.list_resources.return_value = []
            mock_client.list_prompts.return_value = []
            mock_pool.start_server.return_value = mock_client

            from ui.commands import _cmd_mcp_install
            with _mocked_console(), \
                 patch("agent.mcp_manager._CONFIG_FILE", cfg_file):
                _cmd_mcp_install("memory", loop, mock_pool)

            mock_pool.start_server.assert_called_once()

    def test_install_warns_on_missing_runtime(self):
        import tempfile
        fake_catalog = [_catalog_entry("badrt", runtime="__fake_rt__")]
        with tempfile.TemporaryDirectory() as td:
            cfg_file = Path(td) / "oocode.json"
            with patch("agent.mcp_manager._CATALOG_PATH") as mp, \
                 _mocked_console() as mc, \
                 patch("agent.mcp_manager._CONFIG_FILE", cfg_file):
                mp.exists.return_value = True
                mp.read_text.return_value = json.dumps(fake_catalog)
                from ui.commands import _cmd_mcp_install
                _cmd_mcp_install("badrt", MagicMock(), None)
            printed = " ".join(str(a) for a, _ in mc.print.call_args_list)
            self.assertIn("__fake_rt__", printed)


# ── _cmd_mcp_add ──────────────────────────────────────────────────────────────

class TestCmdMcpAdd(unittest.TestCase):

    def test_add_empty_shows_usage(self):
        from ui.commands import _cmd_mcp_add
        with _mocked_console() as mc:
            _cmd_mcp_add("", MagicMock(), None)
        printed = " ".join(str(a) for a, _ in mc.print.call_args_list)
        self.assertIn("Uso", printed)

    def test_add_only_name_shows_usage(self):
        from ui.commands import _cmd_mcp_add
        with _mocked_console() as mc:
            _cmd_mcp_add("onlyname", MagicMock(), None)
        printed = " ".join(str(a) for a, _ in mc.print.call_args_list)
        self.assertIn("Uso", printed)

    def test_add_name_and_cmd_writes_config(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg_file = Path(td) / "oocode.json"
            from ui.commands import _cmd_mcp_add
            with _mocked_console(), \
                 patch("agent.mcp_manager._CONFIG_FILE", cfg_file):
                _cmd_mcp_add("my-srv npx -y @mypackage/server", MagicMock(), None)
            data = json.loads(cfg_file.read_text())
            servers = data.get("mcp", {}).get("servers", [])
            srv = next((s for s in servers if s["name"] == "my-srv"), None)
            self.assertIsNotNone(srv)
            self.assertEqual(srv["cmd"], ["npx", "-y", "@mypackage/server"])

    def test_add_with_pool_calls_hot_add(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg_file = Path(td) / "oocode.json"
            from tools.registry import ToolRegistry
            registry = ToolRegistry()
            loop = MagicMock()
            loop.registry = registry

            mock_client = MagicMock()
            mock_client.is_alive = True
            mock_client.tools = []
            mock_client.error = ""
            mock_client._timeout = 15.0
            mock_client.list_resources.return_value = []
            mock_client.list_prompts.return_value = []
            mock_pool = MagicMock()
            mock_pool.start_server.return_value = mock_client

            from ui.commands import _cmd_mcp_add
            with _mocked_console(), \
                 patch("agent.mcp_manager._CONFIG_FILE", cfg_file):
                _cmd_mcp_add("custom-srv echo hello", loop, mock_pool)

            mock_pool.start_server.assert_called_once()

    def test_add_without_pool_no_crash(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg_file = Path(td) / "oocode.json"
            from ui.commands import _cmd_mcp_add
            with _mocked_console(), \
                 patch("agent.mcp_manager._CONFIG_FILE", cfg_file):
                _cmd_mcp_add("x echo hello", MagicMock(), None)


# ── _cmd_mcp_remove ───────────────────────────────────────────────────────────

class TestCmdMcpRemove(unittest.TestCase):

    def test_remove_empty_shows_usage(self):
        from ui.commands import _cmd_mcp_remove
        with _mocked_console() as mc:
            _cmd_mcp_remove("", None)
        printed = " ".join(str(a) for a, _ in mc.print.call_args_list)
        self.assertIn("Uso", printed)

    def test_remove_existing_server(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg_file = Path(td) / "oocode.json"
            cfg_file.write_text(json.dumps(
                {"mcp": {"servers": [{"name": "my-srv", "cmd": ["x"]}]}}
            ))
            from ui.commands import _cmd_mcp_remove
            with _mocked_console() as mc, \
                 patch("agent.mcp_manager._CONFIG_FILE", cfg_file):
                _cmd_mcp_remove("my-srv", None)
            printed = " ".join(str(a) for a, _ in mc.print.call_args_list)
            self.assertIn("my-srv", printed)
            # verificar que se borró del fichero
            data = json.loads(cfg_file.read_text())
            servers = data.get("mcp", {}).get("servers", [])
            self.assertFalse(any(s["name"] == "my-srv" for s in servers))

    def test_remove_nonexistent_shows_error(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg_file = Path(td) / "oocode.json"
            cfg_file.write_text(json.dumps({"mcp": {"servers": []}}))
            from ui.commands import _cmd_mcp_remove
            with _mocked_console() as mc, \
                 patch("agent.mcp_manager._CONFIG_FILE", cfg_file):
                _cmd_mcp_remove("nope", None)
            printed = " ".join(str(a) for a, _ in mc.print.call_args_list)
            self.assertIn("nope", printed)

    def test_remove_stops_pool_client(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg_file = Path(td) / "oocode.json"
            cfg_file.write_text(json.dumps(
                {"mcp": {"servers": [{"name": "live-srv", "cmd": ["x"]}]}}
            ))
            mock_client = MagicMock()
            mock_pool = MagicMock()
            mock_pool.get_client.return_value = mock_client

            from ui.commands import _cmd_mcp_remove
            with _mocked_console(), \
                 patch("agent.mcp_manager._CONFIG_FILE", cfg_file):
                _cmd_mcp_remove("live-srv", mock_pool)
            mock_client.stop.assert_called_once()


# ── _cmd_mcp_toggle ───────────────────────────────────────────────────────────

class TestCmdMcpToggle(unittest.TestCase):

    def test_enable_empty_shows_usage(self):
        from ui.commands import _cmd_mcp_toggle
        with _mocked_console() as mc:
            _cmd_mcp_toggle("", True, None)
        printed = " ".join(str(a) for a, _ in mc.print.call_args_list)
        self.assertIn("Uso", printed)

    def test_disable_empty_shows_usage(self):
        from ui.commands import _cmd_mcp_toggle
        with _mocked_console() as mc:
            _cmd_mcp_toggle("", False, None)
        printed = " ".join(str(a) for a, _ in mc.print.call_args_list)
        self.assertIn("Uso", printed)

    def test_enable_existing_server(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg_file = Path(td) / "oocode.json"
            cfg_file.write_text(json.dumps(
                {"mcp": {"servers": [{"name": "s", "cmd": ["x"], "enabled": False}]}}
            ))
            from ui.commands import _cmd_mcp_toggle
            with _mocked_console() as mc, \
                 patch("agent.mcp_manager._CONFIG_FILE", cfg_file):
                _cmd_mcp_toggle("s", True, None)
            data = json.loads(cfg_file.read_text())
            srv = data["mcp"]["servers"][0]
            self.assertTrue(srv["enabled"])

    def test_disable_existing_server(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg_file = Path(td) / "oocode.json"
            cfg_file.write_text(json.dumps(
                {"mcp": {"servers": [{"name": "s", "cmd": ["x"], "enabled": True}]}}
            ))
            from ui.commands import _cmd_mcp_toggle
            with _mocked_console(), \
                 patch("agent.mcp_manager._CONFIG_FILE", cfg_file):
                _cmd_mcp_toggle("s", False, None)
            data = json.loads(cfg_file.read_text())
            self.assertFalse(data["mcp"]["servers"][0]["enabled"])

    def test_toggle_nonexistent_shows_error(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg_file = Path(td) / "oocode.json"
            cfg_file.write_text(json.dumps({"mcp": {"servers": []}}))
            from ui.commands import _cmd_mcp_toggle
            with _mocked_console() as mc, \
                 patch("agent.mcp_manager._CONFIG_FILE", cfg_file):
                _cmd_mcp_toggle("nope", True, None)
            printed = " ".join(str(a) for a, _ in mc.print.call_args_list)
            self.assertIn("nope", printed)


# ── _cmd_mcp (dispatch principal) ────────────────────────────────────────────

class TestCmdMcpDispatch(unittest.TestCase):

    def _make_loop(self):
        loop = MagicMock()
        loop._mcp_pool = None
        return loop

    def _call(self, args):
        from ui.commands import _cmd_mcp
        with _mocked_console():
            _cmd_mcp(args, self._make_loop())

    def test_dispatch_catalog(self):
        with patch("ui.commands._cmd_mcp_catalog") as m:
            from ui.commands import _cmd_mcp
            with _mocked_console():
                _cmd_mcp("catalog", self._make_loop())
            m.assert_called_once_with("")

    def test_dispatch_catalog_with_query(self):
        with patch("ui.commands._cmd_mcp_catalog") as m:
            from ui.commands import _cmd_mcp
            with _mocked_console():
                _cmd_mcp("catalog git", self._make_loop())
            m.assert_called_once_with("git")

    def test_dispatch_check(self):
        with patch("ui.commands._cmd_mcp_check") as m:
            from ui.commands import _cmd_mcp
            with _mocked_console():
                _cmd_mcp("check filesystem", self._make_loop())
            m.assert_called_once_with("filesystem")

    def test_dispatch_install(self):
        with patch("ui.commands._cmd_mcp_install") as m:
            from ui.commands import _cmd_mcp
            loop = self._make_loop()
            with _mocked_console():
                _cmd_mcp("install memory", loop)
            m.assert_called_once_with("memory", loop, None)

    def test_dispatch_add(self):
        with patch("ui.commands._cmd_mcp_add") as m:
            from ui.commands import _cmd_mcp
            loop = self._make_loop()
            with _mocked_console():
                _cmd_mcp("add my-srv echo", loop)
            m.assert_called_once_with("my-srv echo", loop, None)

    def test_dispatch_remove(self):
        with patch("ui.commands._cmd_mcp_remove") as m:
            from ui.commands import _cmd_mcp
            loop = self._make_loop()
            with _mocked_console():
                _cmd_mcp("remove my-srv", loop)
            m.assert_called_once_with("my-srv", None)

    def test_dispatch_enable(self):
        with patch("ui.commands._cmd_mcp_toggle") as m:
            from ui.commands import _cmd_mcp
            loop = self._make_loop()
            with _mocked_console():
                _cmd_mcp("enable my-srv", loop)
            m.assert_called_once_with("my-srv", True, None)

    def test_dispatch_disable(self):
        with patch("ui.commands._cmd_mcp_toggle") as m:
            from ui.commands import _cmd_mcp
            loop = self._make_loop()
            with _mocked_console():
                _cmd_mcp("disable my-srv", loop)
            m.assert_called_once_with("my-srv", False, None)

    def test_no_args_no_pool_shows_hint(self):
        from ui.commands import _cmd_mcp
        loop = self._make_loop()
        with _mocked_console() as mc:
            _cmd_mcp("", loop)
        printed = " ".join(str(a) for a, _ in mc.print.call_args_list)
        self.assertIn("catalog", printed.lower())

    def test_reload_with_pool(self):
        from ui.commands import _cmd_mcp
        loop = self._make_loop()
        mock_client = MagicMock()
        mock_client.reload_tools.return_value = 5
        mock_pool = MagicMock()
        mock_pool.get_client.return_value = mock_client
        loop._mcp_pool = mock_pool
        with _mocked_console():
            _cmd_mcp("reload my-srv", loop)
        mock_client.reload_tools.assert_called_once()

    def test_reload_unknown_server(self):
        from ui.commands import _cmd_mcp
        loop = self._make_loop()
        mock_pool = MagicMock()
        mock_pool.get_client.return_value = None
        loop._mcp_pool = mock_pool
        with _mocked_console() as mc:
            _cmd_mcp("reload unknown", loop)
        printed = " ".join(str(a) for a, _ in mc.print.call_args_list)
        self.assertIn("unknown", printed)

    def test_restart_with_pool_alive(self):
        from ui.commands import _cmd_mcp
        loop = self._make_loop()
        mock_client = MagicMock()
        mock_client.is_alive = True
        mock_client.tools = [1, 2]
        mock_pool = MagicMock()
        mock_pool.restart_server.return_value = mock_client
        loop._mcp_pool = mock_pool
        with _mocked_console() as mc:
            _cmd_mcp("restart my-srv", loop)
        printed = " ".join(str(a) for a, _ in mc.print.call_args_list)
        self.assertIn("my-srv", printed)

    def test_status_table_with_alive_pool(self):
        from ui.commands import _cmd_mcp
        loop = self._make_loop()
        mock_pool = MagicMock()
        mock_pool.status.return_value = [
            {"name": "test-srv", "cmd": "echo", "alive": True,
             "tools": 3, "resources": 0, "prompts": 0, "error": ""},
        ]
        mock_pool.client_count = 1
        mock_pool.tool_count   = 3
        loop._mcp_pool = mock_pool
        with _mocked_console():
            _cmd_mcp("", loop)  # no crash


# ── Integración con handle_slash ──────────────────────────────────────────────

class TestMcpHandleSlashIntegration(unittest.TestCase):

    def test_mcp_subcommands_in_slash_help(self):
        from ui.commands import SLASH_HELP
        all_keys = " ".join(k for cmds in SLASH_HELP.values() for k in cmds.keys())
        self.assertIn("/mcp", all_keys)
        self.assertIn("catalog", all_keys)
        self.assertIn("install", all_keys)

    def test_mcp_catalog_command_listed(self):
        from ui.commands import SLASH_HELP
        all_text = " ".join(
            f"{k} {v}" for cmds in SLASH_HELP.values() for k, v in cmds.items()
        )
        self.assertIn("catalog", all_text.lower())

    def test_handle_slash_mcp_no_crash(self):
        from ui.commands import handle_slash
        loop = MagicMock()
        loop._mcp_pool = None
        cfg  = MagicMock()
        with patch("ui.commands.console"), \
             patch("ui.commands._cmd_mcp") as m:
            handle_slash("/mcp", loop, cfg)
        m.assert_called_once()

    def test_handle_slash_mcp_catalog_no_crash(self):
        from ui.commands import handle_slash
        loop = MagicMock()
        loop._mcp_pool = None
        cfg  = MagicMock()
        with patch("ui.commands.console"), \
             patch("ui.commands._cmd_mcp") as m:
            handle_slash("/mcp catalog", loop, cfg)
        m.assert_called_once()


if __name__ == "__main__":
    unittest.main()
