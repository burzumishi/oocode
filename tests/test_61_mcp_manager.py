"""Tests para agent/mcp_manager.py — catálogo, config y hot-add.

No requiere Ollama, npx, uvx ni ningún proceso externo.
"""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ── Catálogo ──────────────────────────────────────────────────────────────────

class TestCatalogLoad:
    def test_load_catalog_returns_list(self):
        from agent.mcp_manager import load_catalog
        cat = load_catalog()
        assert isinstance(cat, list)

    def test_catalog_not_empty(self):
        from agent.mcp_manager import load_catalog
        assert len(load_catalog()) >= 5

    def test_catalog_entries_have_id(self):
        from agent.mcp_manager import load_catalog
        for srv in load_catalog():
            assert "id" in srv, f"entrada sin 'id': {srv}"

    def test_catalog_entries_have_cmd(self):
        from agent.mcp_manager import load_catalog
        for srv in load_catalog():
            assert "cmd" in srv and isinstance(srv["cmd"], list), f"cmd inválido: {srv}"

    def test_catalog_entries_have_runtime(self):
        from agent.mcp_manager import load_catalog
        valid_runtimes = {"npx", "uvx", "python", "python3", "node", "custom", ""}
        for srv in load_catalog():
            assert srv.get("runtime", "") in valid_runtimes, \
                f"runtime desconocido: {srv.get('runtime')}"

    def test_catalog_known_ids_present(self):
        from agent.mcp_manager import load_catalog
        ids = {s["id"] for s in load_catalog()}
        for expected in ("filesystem", "git", "memory", "postgres", "sqlite"):
            assert expected in ids, f"ID '{expected}' no encontrado en catálogo"

    def test_catalog_filesystem_cmd_starts_npx(self):
        from agent.mcp_manager import find_in_catalog
        srv = find_in_catalog("filesystem")
        assert srv is not None
        assert srv["cmd"][0] == "npx"

    def test_catalog_git_runtime_uvx(self):
        from agent.mcp_manager import find_in_catalog
        srv = find_in_catalog("git")
        assert srv is not None
        assert srv["runtime"] == "uvx"

    def test_catalog_memory_cmd_contains_package(self):
        from agent.mcp_manager import find_in_catalog
        srv = find_in_catalog("memory")
        assert srv is not None
        assert "@modelcontextprotocol/server-memory" in " ".join(srv["cmd"])


class TestFindInCatalog:
    def test_find_by_id_exact(self):
        from agent.mcp_manager import find_in_catalog
        assert find_in_catalog("filesystem") is not None

    def test_find_by_id_case_insensitive(self):
        from agent.mcp_manager import find_in_catalog
        assert find_in_catalog("FILESYSTEM") is not None

    def test_find_missing_returns_none(self):
        from agent.mcp_manager import find_in_catalog
        assert find_in_catalog("nonexistent-xyz-123") is None

    def test_find_returns_dict(self):
        from agent.mcp_manager import find_in_catalog
        srv = find_in_catalog("git")
        assert isinstance(srv, dict)
        assert srv["id"] == "git"


class TestSearchCatalog:
    def test_empty_query_returns_all(self):
        from agent.mcp_manager import search_catalog, load_catalog
        assert len(search_catalog("")) == len(load_catalog())

    def test_search_by_tag(self):
        from agent.mcp_manager import search_catalog
        results = search_catalog("sql")
        ids = {s["id"] for s in results}
        # postgres and sqlite have "sql" in tags or description
        assert ids & {"postgres", "sqlite"}, "esperaba postgres o sqlite en resultados sql"

    def test_search_by_description(self):
        from agent.mcp_manager import search_catalog
        results = search_catalog("git")
        assert any(s["id"] == "git" for s in results)

    def test_search_no_results(self):
        from agent.mcp_manager import search_catalog
        results = search_catalog("xyznonexistentterm999")
        assert results == []


# ── Prerequisitos ─────────────────────────────────────────────────────────────

class TestPrerequisites:
    def test_check_runtime_python3_found(self):
        from agent.mcp_manager import check_runtime
        # python3 está siempre disponible en el entorno de tests
        assert check_runtime("python3") is True

    def test_check_runtime_fake_missing(self):
        from agent.mcp_manager import check_runtime
        assert check_runtime("__totally_fake_runtime_xyz__") is False

    def test_check_server_prerequisites_python(self):
        from agent.mcp_manager import check_server_prerequisites
        srv = {"runtime": "python"}
        # python3 disponible → sin missing
        missing = check_server_prerequisites(srv)
        assert isinstance(missing, list)

    def test_check_server_prerequisites_custom_no_check(self):
        from agent.mcp_manager import check_server_prerequisites
        srv = {"runtime": "custom"}
        assert check_server_prerequisites(srv) == []

    def test_check_server_prerequisites_empty_runtime(self):
        from agent.mcp_manager import check_server_prerequisites
        srv = {"runtime": ""}
        assert check_server_prerequisites(srv) == []

    def test_check_prerequisites_missing_runtime(self):
        from agent.mcp_manager import check_server_prerequisites
        srv = {"runtime": "__fake_runtime_xyz__"}
        missing = check_server_prerequisites(srv)
        assert "__fake_runtime_xyz__" in missing


# ── Config (oocode.json) ──────────────────────────────────────────────────────

class TestAddServer:
    def test_add_creates_mcp_servers_key(self, tmp_path):
        from agent.mcp_manager import add_server
        f = tmp_path / "oocode.json"
        entry = {"name": "test-srv", "cmd": ["echo", "hello"], "enabled": True}
        add_server(entry, config_file=f)
        servers = json.loads(f.read_text()).get("mcp", {}).get("servers", [])
        assert any(s["name"] == "test-srv" for s in servers)

    def test_add_preserves_existing_entries(self, tmp_path):
        from agent.mcp_manager import add_server
        f = tmp_path / "oocode.json"
        add_server({"name": "srv-a", "cmd": ["a"]}, config_file=f)
        add_server({"name": "srv-b", "cmd": ["b"]}, config_file=f)
        servers = json.loads(f.read_text()).get("mcp", {}).get("servers", [])
        names = {s["name"] for s in servers}
        assert "srv-a" in names and "srv-b" in names

    def test_add_replaces_existing_same_name(self, tmp_path):
        from agent.mcp_manager import add_server
        f = tmp_path / "oocode.json"
        add_server({"name": "srv", "cmd": ["old"]}, config_file=f)
        add_server({"name": "srv", "cmd": ["new"]}, config_file=f)
        servers = json.loads(f.read_text()).get("mcp", {}).get("servers", [])
        assert len([s for s in servers if s["name"] == "srv"]) == 1
        assert next(s for s in servers if s["name"] == "srv")["cmd"] == ["new"]

    def test_add_creates_parent_dir(self, tmp_path):
        from agent.mcp_manager import add_server
        f = tmp_path / "nested" / "oocode.json"
        add_server({"name": "x", "cmd": ["x"]}, config_file=f)
        assert f.exists()

    def test_add_preserves_other_config_sections(self, tmp_path):
        from agent.mcp_manager import add_server
        f = tmp_path / "oocode.json"
        f.write_text(json.dumps({"api": {"host": "http://localhost:11434"}}))
        add_server({"name": "x", "cmd": ["x"]}, config_file=f)
        cfg = json.loads(f.read_text())
        assert cfg["api"]["host"] == "http://localhost:11434"


class TestRemoveServer:
    def test_remove_existing(self, tmp_path):
        from agent.mcp_manager import add_server, remove_server
        f = tmp_path / "oocode.json"
        add_server({"name": "del-me", "cmd": ["x"]}, config_file=f)
        result = remove_server("del-me", config_file=f)
        assert result is True
        servers = json.loads(f.read_text()).get("mcp", {}).get("servers", [])
        assert not any(s["name"] == "del-me" for s in servers)

    def test_remove_nonexistent_returns_false(self, tmp_path):
        from agent.mcp_manager import remove_server
        f = tmp_path / "oocode.json"
        f.write_text(json.dumps({"mcp": {"servers": []}}))
        assert remove_server("nope", config_file=f) is False

    def test_remove_missing_config_returns_false(self, tmp_path):
        from agent.mcp_manager import remove_server
        f = tmp_path / "nosuchfile.json"
        assert remove_server("x", config_file=f) is False

    def test_remove_keeps_other_servers(self, tmp_path):
        from agent.mcp_manager import add_server, remove_server
        f = tmp_path / "oocode.json"
        add_server({"name": "keep", "cmd": ["k"]}, config_file=f)
        add_server({"name": "gone", "cmd": ["g"]}, config_file=f)
        remove_server("gone", config_file=f)
        servers = json.loads(f.read_text()).get("mcp", {}).get("servers", [])
        assert any(s["name"] == "keep" for s in servers)


class TestSetServerEnabled:
    def test_enable_existing(self, tmp_path):
        from agent.mcp_manager import add_server, set_server_enabled
        f = tmp_path / "oocode.json"
        add_server({"name": "s", "cmd": ["x"], "enabled": False}, config_file=f)
        result = set_server_enabled("s", True, config_file=f)
        assert result is True
        servers = json.loads(f.read_text()).get("mcp", {}).get("servers", [])
        assert next(s for s in servers if s["name"] == "s")["enabled"] is True

    def test_disable_existing(self, tmp_path):
        from agent.mcp_manager import add_server, set_server_enabled
        f = tmp_path / "oocode.json"
        add_server({"name": "s", "cmd": ["x"], "enabled": True}, config_file=f)
        set_server_enabled("s", False, config_file=f)
        servers = json.loads(f.read_text()).get("mcp", {}).get("servers", [])
        assert next(s for s in servers if s["name"] == "s")["enabled"] is False

    def test_toggle_nonexistent_returns_false(self, tmp_path):
        from agent.mcp_manager import set_server_enabled
        f = tmp_path / "oocode.json"
        f.write_text(json.dumps({"mcp": {"servers": []}}))
        assert set_server_enabled("nope", True, config_file=f) is False

    def test_toggle_missing_config_returns_false(self, tmp_path):
        from agent.mcp_manager import set_server_enabled
        assert set_server_enabled("x", True, config_file=tmp_path / "nope.json") is False

    def test_enable_bundled_devops(self, tmp_path):
        from agent.mcp_manager import set_server_enabled
        f = tmp_path / "oocode.json"
        f.write_text(json.dumps({"mcp": {"servers": [], "devopsAssistant": {"enabled": False}}}))
        result = set_server_enabled("devops-assistant", True, config_file=f)
        assert result is True
        data = json.loads(f.read_text())
        assert data["mcp"]["devopsAssistant"]["enabled"] is True

    def test_disable_bundled_database(self, tmp_path):
        from agent.mcp_manager import set_server_enabled
        f = tmp_path / "oocode.json"
        f.write_text(json.dumps({"mcp": {"servers": [], "databaseAssistant": {"enabled": True}}}))
        set_server_enabled("database-assistant", False, config_file=f)
        data = json.loads(f.read_text())
        assert data["mcp"]["databaseAssistant"]["enabled"] is False

    def test_enable_bundled_creates_key_if_missing(self, tmp_path):
        from agent.mcp_manager import set_server_enabled
        f = tmp_path / "oocode.json"
        f.write_text(json.dumps({"mcp": {"servers": []}}))
        result = set_server_enabled("home-office-assistant", True, config_file=f)
        assert result is True
        data = json.loads(f.read_text())
        assert data["mcp"]["homeOfficeAssistant"]["enabled"] is True

    def test_bundled_server_map_coverage(self):
        from agent.mcp_manager import _BUNDLED_SERVER_MAP
        expected = {
            "oocode-assistant", "system-assistant", "devops-assistant",
            "database-assistant", "home-office-assistant",
            "security-assistant", "iot-assistant", "http-client-assistant",
        }
        assert expected == set(_BUNDLED_SERVER_MAP.keys())


# ── Construcción de cmd ───────────────────────────────────────────────────────

class TestBuildCmd:
    def test_build_cmd_appends_extra_args(self):
        from agent.mcp_manager import build_cmd_from_catalog
        srv = {"cmd": ["npx", "-y", "@mcp/server-fs"]}
        cmd = build_cmd_from_catalog(srv, ["/home/user"])
        assert cmd == ["npx", "-y", "@mcp/server-fs", "/home/user"]

    def test_build_cmd_no_extra(self):
        from agent.mcp_manager import build_cmd_from_catalog
        srv = {"cmd": ["npx", "-y", "@mcp/server-memory"]}
        cmd = build_cmd_from_catalog(srv, [])
        assert cmd == ["npx", "-y", "@mcp/server-memory"]

    def test_build_entry_from_catalog_uses_id_as_name(self):
        from agent.mcp_manager import find_in_catalog, build_entry_from_catalog
        srv = find_in_catalog("filesystem")
        entry = build_entry_from_catalog(srv, ["/tmp"])
        assert entry["name"] == "filesystem"
        assert "/tmp" in entry["cmd"]
        assert entry["enabled"] is True

    def test_build_entry_from_catalog_custom_name(self):
        from agent.mcp_manager import find_in_catalog, build_entry_from_catalog
        srv = find_in_catalog("memory")
        entry = build_entry_from_catalog(srv, [], custom_name="my-memory")
        assert entry["name"] == "my-memory"

    def test_build_entry_has_description(self):
        from agent.mcp_manager import find_in_catalog, build_entry_from_catalog
        srv = find_in_catalog("git")
        entry = build_entry_from_catalog(srv, [])
        assert entry.get("description", "") != ""


# ── Hot-add ───────────────────────────────────────────────────────────────────

class TestHotAdd:
    def _make_pool_and_registry(self, tool_count: int = 2):
        """Crea mocks de pool y registry para hot-add."""
        from tools.registry import ToolRegistry
        registry = ToolRegistry()

        tools = [
            {"name": f"tool_{i}", "description": f"Tool {i}",
             "inputSchema": {"type": "object", "properties": {}}}
            for i in range(tool_count)
        ]
        mock_client = MagicMock()
        mock_client.is_alive = True
        mock_client.tools = tools
        mock_client.error = ""
        mock_client._timeout = 15.0
        mock_client.list_resources.return_value = []
        mock_client.list_prompts.return_value = []
        mock_client._capabilities = {}

        mock_pool = MagicMock()
        mock_pool.start_server.return_value = mock_client

        return mock_pool, registry, mock_client

    def test_hot_add_ok_returns_true(self):
        from agent.mcp_manager import hot_add_to_pool
        pool, registry, client = self._make_pool_and_registry(3)
        entry = {"name": "test", "cmd": ["echo"], "enabled": True}

        with patch("agent.mcp_client.mcp_tool_to_oocode",
                   side_effect=lambda c, t, **_: (
                       t["name"], lambda **kw: "ok",
                       {"name": t["name"], "description": "", "parameters": {}}
                   )):
            ok, msg = hot_add_to_pool(entry, pool, registry)

        assert ok is True
        assert "tools" in msg

    def test_hot_add_empty_cmd_returns_false(self):
        from agent.mcp_manager import hot_add_to_pool
        pool, registry, _ = self._make_pool_and_registry()
        entry = {"name": "bad", "cmd": [], "enabled": True}
        ok, msg = hot_add_to_pool(entry, pool, registry)
        assert ok is False
        assert "cmd" in msg.lower() or "vacío" in msg.lower()

    def test_hot_add_dead_client_returns_false(self):
        from agent.mcp_manager import hot_add_to_pool
        from tools.registry import ToolRegistry
        registry = ToolRegistry()

        mock_client = MagicMock()
        mock_client.is_alive = False
        mock_client.error = "proceso no arrancó"
        mock_pool = MagicMock()
        mock_pool.start_server.return_value = mock_client

        entry = {"name": "dead", "cmd": ["fake"], "enabled": True}
        ok, msg = hot_add_to_pool(entry, mock_pool, registry)
        assert ok is False

    def test_hot_add_pool_start_exception_returns_false(self):
        from agent.mcp_manager import hot_add_to_pool
        from tools.registry import ToolRegistry
        registry = ToolRegistry()

        mock_pool = MagicMock()
        mock_pool.start_server.side_effect = RuntimeError("boom")

        entry = {"name": "err", "cmd": ["x"], "enabled": True}
        ok, msg = hot_add_to_pool(entry, mock_pool, registry)
        assert ok is False
        assert "boom" in msg


# ── Integración catálogo + config ─────────────────────────────────────────────

class TestCatalogIntegration:
    def test_install_from_catalog_filesystem(self, tmp_path):
        """Simula /mcp install filesystem /home/user."""
        from agent.mcp_manager import (
            find_in_catalog, build_entry_from_catalog,
            add_server,
        )
        f = tmp_path / "oocode.json"
        srv = find_in_catalog("filesystem")
        entry = build_entry_from_catalog(srv, ["/home/user"])
        add_server(entry, config_file=f)

        servers = json.loads(f.read_text()).get("mcp", {}).get("servers", [])
        fs = next((s for s in servers if s["name"] == "filesystem"), None)
        assert fs is not None
        assert "/home/user" in fs["cmd"]
        assert fs["enabled"] is True

    def test_install_postgres_with_uri(self, tmp_path):
        from agent.mcp_manager import (
            find_in_catalog, build_entry_from_catalog,
            add_server,
        )
        f = tmp_path / "oocode.json"
        srv = find_in_catalog("postgres")
        entry = build_entry_from_catalog(srv, ["postgresql://localhost/testdb"])
        add_server(entry, config_file=f)

        servers = json.loads(f.read_text()).get("mcp", {}).get("servers", [])
        pg = next((s for s in servers if s["name"] == "postgres"), None)
        assert pg is not None
        assert "postgresql://localhost/testdb" in pg["cmd"]

    def test_install_memory_no_args(self, tmp_path):
        from agent.mcp_manager import (
            find_in_catalog, build_entry_from_catalog,
            add_server,
        )
        f = tmp_path / "oocode.json"
        srv = find_in_catalog("memory")
        entry = build_entry_from_catalog(srv, [])
        add_server(entry, config_file=f)

        servers = json.loads(f.read_text()).get("mcp", {}).get("servers", [])
        mem = next((s for s in servers if s["name"] == "memory"), None)
        assert mem is not None
        # cmd should be exactly the catalog cmd (no extra args)
        assert mem["cmd"] == srv["cmd"]

    def test_round_trip_add_remove(self, tmp_path):
        from agent.mcp_manager import add_server, remove_server
        f = tmp_path / "oocode.json"
        add_server({"name": "temp", "cmd": ["x"]}, config_file=f)
        assert any(s["name"] == "temp" for s in json.loads(f.read_text()).get("mcp", {}).get("servers", []))
        remove_server("temp", config_file=f)
        assert not any(s["name"] == "temp" for s in json.loads(f.read_text()).get("mcp", {}).get("servers", []))
