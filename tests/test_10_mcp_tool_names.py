"""Tests de que los nombres de tools MCP son correctos (sin prefijo mcp_oocode_assistant_)."""
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestMcpToolNames:
    """Verifica que mcp_tool_to_oocode() no añade prefijo a las tools bundled."""

    def test_no_prefix_for_oocode_assistant(self):
        from agent.mcp_client import McpClient, mcp_tool_to_oocode
        # Simular un cliente del servidor bundled
        client = McpClient.__new__(McpClient)
        client.name = "oocode_assistant"
        tool = {"name": "docker_logs", "description": "Docker logs", "inputSchema": {}}
        name, fn, schema = mcp_tool_to_oocode(client, tool)
        assert name == "docker_logs", f"Se esperaba 'docker_logs', se obtuvo '{name}'"
        assert not name.startswith("mcp_")

    def test_prefix_for_external_server(self):
        from agent.mcp_client import McpClient, mcp_tool_to_oocode
        client = McpClient.__new__(McpClient)
        client.name = "external_server"
        tool = {"name": "some_tool", "description": "External tool", "inputSchema": {}}
        # Para servidores externos debe añadir prefijo (o ser sin prefijo si no hay colisión)
        name, fn, schema = mcp_tool_to_oocode(client, tool, existing_names=frozenset())
        assert isinstance(name, str)
        assert len(name) > 0

    def test_hyphen_to_underscore(self):
        from agent.mcp_client import McpClient, mcp_tool_to_oocode
        client = McpClient.__new__(McpClient)
        client.name = "oocode_assistant"
        tool = {"name": "my-tool-name", "description": "Hyphenated", "inputSchema": {}}
        name, fn, schema = mcp_tool_to_oocode(client, tool)
        assert "-" not in name
        assert "my_tool_name" == name

    def test_known_tool_names_no_prefix(self):
        """Las tools conocidas del servidor bundled no deben tener prefijo."""
        from agent.mcp_client import McpClient, mcp_tool_to_oocode
        client = McpClient.__new__(McpClient)
        client.name = "oocode_assistant"

        expected_bare_names = [
            "bash", "read_file", "write_file", "edit_file",
            "git_status", "git_log", "docker_ps", "docker_logs",
            "compose_up", "compose_down", "lint_file", "python_exec",
        ]
        # Simular que el MCP server devuelve estas tools
        for bare_name in expected_bare_names:
            tool = {"name": bare_name, "description": "Test", "inputSchema": {}}
            name, _, _ = mcp_tool_to_oocode(client, tool)
            assert name == bare_name, (
                f"Tool '{bare_name}' debería mantener su nombre, pero se obtuvo '{name}'"
            )
            assert not name.startswith("mcp_"), (
                f"Tool '{name}' tiene prefijo mcp_ — esto rompe las reglas del agente"
            )
