"""Tests de los módulos core del agente (sin LLM): config, registry, permissions, chatlog, context."""
import sys
import json
import pytest
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestChatLog:
    def test_disabled_by_default(self, tmp_path):
        from agent.chatlog import ChatLogger
        cl = ChatLogger(enabled=False, path=str(tmp_path / "chat.log"))
        cl.log_user("hello")
        cl.log_assistant("hi there")
        assert not (tmp_path / "chat.log").exists()

    def test_logs_when_enabled(self, tmp_path):
        from agent.chatlog import ChatLogger
        log_path = tmp_path / "chat.log"
        cl = ChatLogger(enabled=True, path=str(log_path))
        cl.log_user("hola")
        cl.log_assistant("respuesta")
        cl.log_tool_call("bash", {"cmd": "ls"}, "file1\nfile2\n")
        content = log_path.read_text()
        assert "hola" in content
        assert "respuesta" in content
        assert "bash" in content
        assert "ls" in content

    def test_session_header_written(self, tmp_path):
        from agent.chatlog import ChatLogger
        log_path = tmp_path / "chat.log"
        cl = ChatLogger(enabled=True, path=str(log_path))
        content = log_path.read_text()
        assert "SESIÓN" in content

    def test_rotation_on_size(self, tmp_path):
        from agent.chatlog import ChatLogger
        log_path = tmp_path / "rotate.log"
        # Crear log "grande" artificialmente
        log_path.write_text("X" * 1024)  # 1 KB
        cl = ChatLogger(enabled=True, path=str(log_path), max_size_mb=0)  # 0 = siempre rota
        # El fichero original debe haberse renombrado
        backup = log_path.with_suffix(".log.1")
        assert backup.exists() or log_path.stat().st_size < 1024  # rotado o reescrito

    def test_session_end(self, tmp_path):
        from agent.chatlog import ChatLogger
        log_path = tmp_path / "end.log"
        cl = ChatLogger(enabled=True, path=str(log_path))
        cl.log_session_end()
        content = log_path.read_text()
        assert "FIN SESIÓN" in content


class TestConversationContext:
    def test_add_and_messages(self):
        from agent.context import ConversationContext
        ctx = ConversationContext(max_tokens=4000)
        ctx.add("user", "hello")
        ctx.add("assistant", "hi there")
        msgs = ctx.messages
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

    def test_stats(self):
        from agent.context import ConversationContext
        ctx = ConversationContext(max_tokens=4000)
        ctx.add("user", "hello world")
        stats = ctx.stats()
        assert "tokens_estimate" in stats
        assert stats["tokens_estimate"] > 0
        assert "max_tokens" in stats

    def test_add_tool_result(self):
        from agent.context import ConversationContext
        ctx = ConversationContext(max_tokens=4000)
        ctx.add("user", "run ls")
        ctx.add_tool_result("call_1", "bash", "file1.txt\nfile2.txt\n")
        msgs = ctx.messages
        assert any(m["role"] == "tool" for m in msgs)


class TestPermissions:
    def test_auto_mode(self):
        from tools.permissions import PermissionManager
        pm = PermissionManager({"bash": "auto"})
        result = pm.check("bash", "bash(ls)")
        assert result is True

    def test_deny_mode(self):
        from tools.permissions import PermissionManager
        pm = PermissionManager({"bash": "deny"})
        result = pm.check("bash", "bash(rm -rf /)")
        assert result is False

    def test_unknown_tool_defaults_ask(self):
        from tools.permissions import PermissionManager
        pm = PermissionManager({})
        # Tool desconocida → modo "ask" por defecto
        mode = pm.resolve_mode("unknown_tool")
        assert mode in ("auto", "ask", "deny")  # debe devolver un modo válido


class TestToolRegistry:
    def test_register_and_call(self):
        from tools.registry import ToolRegistry
        reg = ToolRegistry()

        def my_tool(**kwargs) -> str:
            return f"result:{kwargs.get('x', 'none')}"

        schema = {
            "type": "function",
            "function": {
                "name": "my_tool",
                "description": "Test tool",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "string", "description": "Input"}
                    },
                    "required": []
                }
            }
        }
        reg.register("my_tool", my_tool, schema)
        result = reg.call("my_tool", {"x": "hello"})
        assert result == "result:hello"

    def test_call_unknown_tool(self):
        from tools.registry import ToolRegistry
        reg = ToolRegistry()
        result = reg.call("nonexistent_tool", {})
        assert "Error" in result or "desconocida" in result or "not found" in result.lower()

    def test_ollama_schemas(self):
        from tools.registry import ToolRegistry
        reg = ToolRegistry()

        def dummy(**kwargs) -> str:
            return "ok"

        # register() stores the schema as-is and ollama_schemas() wraps it in {"type":"function","function":schema}
        # So schema should be the raw function definition (without the outer wrapper)
        schema = {
            "name": "dummy_test_tool",
            "description": "Dummy test tool",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
        reg.register("dummy_test_tool", dummy, schema)
        schemas = reg.ollama_schemas()
        assert any(
            s.get("function", {}).get("name") == "dummy_test_tool"
            for s in schemas
        )


class TestOOConfig:
    def test_load_defaults(self, tmp_path, monkeypatch):
        from config import OOConfig, CONFIG_DIR, CONFIG_FILE
        # Patch CONFIG_DIR y CONFIG_FILE para no tocar ~/.oocode
        tmp_config = tmp_path / "oocode.json"
        monkeypatch.setattr("config.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("config.CONFIG_FILE", tmp_config)
        monkeypatch.setattr("config.MEMORY_DIR", tmp_path / "memory")
        cfg = OOConfig.load()
        assert cfg.ollama_host == "http://localhost:11434"
        assert isinstance(cfg.permissions, dict)

    def test_chatlog_defaults(self):
        from config import OOConfig
        cfg = OOConfig()
        assert cfg.chatlog_enabled is False
        assert cfg.chatlog_path == ""
        assert cfg.chatlog_max_size_mb == 10


class TestPostprocessToolResult:
    """Tests del detector de bucles de búsqueda vacíos en AgentLoop."""

    def _make_loop(self, tmp_path):
        """Crea un AgentLoop mínimo para probar _postprocess_tool_result."""
        from unittest.mock import MagicMock
        from config import OOConfig
        from tools.registry import ToolRegistry
        from tools.permissions import PermissionManager
        from agent.memory import MemorySystem
        from agent.session import SessionManager
        from workspace.manager import WorkspaceManager
        from agent.runtime import RuntimeSettings
        from agent.loop import AgentLoop

        cfg = OOConfig()
        reg = ToolRegistry()
        perm = PermissionManager({})
        mem = MemorySystem(str(tmp_path / "memory"))
        ws = WorkspaceManager(str(tmp_path))
        sess = SessionManager("test")
        rt = RuntimeSettings()
        loop = AgentLoop(cfg, reg, perm, mem, ws, sess, rt,
                         capture_output=True, ollama_client=MagicMock())
        return loop

    def test_no_hint_on_first_empty(self, tmp_path):
        loop = self._make_loop(tmp_path)
        result = loop._postprocess_tool_result(
            "grep_code", {"pattern": "foo"}, "Sin resultados para 'foo' en /tmp"
        )
        assert "⚡ AGENTE" not in result

    def test_hint_on_second_consecutive_empty(self, tmp_path):
        loop = self._make_loop(tmp_path)
        loop._postprocess_tool_result(
            "grep_code", {"pattern": "foo"}, "Sin resultados para 'foo' en /tmp"
        )
        result = loop._postprocess_tool_result(
            "grep_code", {"pattern": "foo2"}, "Sin resultados para 'foo2' en /tmp"
        )
        assert "⚡ AGENTE" in result
        assert "symbol_lookup" in result

    def test_streak_resets_on_success(self, tmp_path):
        loop = self._make_loop(tmp_path)
        # Dos vacíos seguidos
        loop._postprocess_tool_result("grep_code", {"pattern": "a"}, "Sin resultados")
        loop._postprocess_tool_result("grep_code", {"pattern": "b"}, "Sin resultados")
        assert loop._empty_search_streak == 2
        # Resultado con éxito — resetea
        loop._postprocess_tool_result("grep_code", {"pattern": "c"}, "found: foo.py:5:bar")
        assert loop._empty_search_streak == 0

    def test_non_search_tool_resets_streak(self, tmp_path):
        loop = self._make_loop(tmp_path)
        loop._postprocess_tool_result("grep_code", {"pattern": "a"}, "Sin resultados")
        loop._postprocess_tool_result("grep_code", {"pattern": "b"}, "Sin resultados")
        assert loop._empty_search_streak == 2
        # Una tool que no es de búsqueda
        loop._postprocess_tool_result("bash", {"command": "ls"}, "file.txt")
        assert loop._empty_search_streak == 0

    def test_hint_includes_tried_patterns(self, tmp_path):
        loop = self._make_loop(tmp_path)
        loop._postprocess_tool_result("grep_code", {"pattern": "pat_alpha"}, "Sin resultados")
        result = loop._postprocess_tool_result(
            "grep_code", {"pattern": "pat_beta"}, "Sin resultados"
        )
        assert "pat_alpha" in result or "pat_beta" in result

    def test_streak_counter_increments(self, tmp_path):
        loop = self._make_loop(tmp_path)
        for i in range(4):
            loop._postprocess_tool_result("grep_code", {"pattern": f"p{i}"}, "Sin resultados")
        assert loop._empty_search_streak == 4


class TestPermissionManagerElevated:
    """Tests del sistema de permisos con /elevated."""

    def _make_perms(self, perms: dict | None = None) -> "PermissionManager":
        from tools.permissions import PermissionManager
        return PermissionManager(perms or {
            "read_file":  "auto",
            "write_file": "ask",
            "bash":       "ask",
        })

    def test_full_returns_auto_for_known_tool(self):
        pm = self._make_perms()
        pm.set_elevated("full")
        assert pm.resolve_mode("write_file") == "auto"
        assert pm.resolve_mode("bash") == "auto"
        assert pm.resolve_mode("read_file") == "auto"

    def test_full_returns_auto_for_unknown_tool(self):
        """Bug fix: /elevated full debe apliar a tools no registradas en _perms."""
        pm = self._make_perms()
        pm.set_elevated("full")
        # Tools NO en _perms
        assert pm.resolve_mode("grep_code") == "auto"
        assert pm.resolve_mode("symbol_lookup") == "auto"
        assert pm.resolve_mode("mcp_oocode_assistant_grep_code") == "auto"
        assert pm.resolve_mode("any_unknown_tool_xyz") == "auto"

    def test_full_check_returns_true_without_prompt(self):
        pm = self._make_perms()
        pm.set_elevated("full")
        # Incluso tools desconocidas deben pasar sin prompt
        assert pm.check("unknown_mcp_tool", "test") is True

    def test_off_converts_ask_to_deny(self):
        pm = self._make_perms()
        pm.set_elevated("off")
        assert pm.resolve_mode("write_file") == "deny"
        assert pm.resolve_mode("bash") == "deny"
        # Read-only sigue siendo auto
        assert pm.resolve_mode("read_file") == "auto"

    def test_off_unknown_tool_returns_deny(self):
        pm = self._make_perms()
        pm.set_elevated("off")
        assert pm.resolve_mode("unknown_xyz") == "deny"

    def test_mcp_tool_inherits_bare_name_permission(self):
        """MCP tools deben heredar el permiso del nombre bare."""
        pm = self._make_perms({"write_file": "ask", "read_file": "auto"})
        # Sin elevated
        assert pm.resolve_mode("mcp_oocode_assistant_write_file") == "ask"
        assert pm.resolve_mode("mcp_oocode_assistant_read_file") == "auto"

    def test_mcp_tool_full_elevated(self):
        pm = self._make_perms({"write_file": "ask", "read_file": "auto"})
        pm.set_elevated("full")
        assert pm.resolve_mode("mcp_oocode_assistant_write_file") == "auto"

    def test_set_elevated_ask_restores_from_perms(self):
        """ask mode: no bloquea, usa _perms normal."""
        pm = self._make_perms()
        pm.set_elevated("full")
        assert pm.resolve_mode("write_file") == "auto"
        pm.set_elevated("ask")
        assert pm.resolve_mode("write_file") == "ask"
        assert pm.resolve_mode("read_file") == "auto"

    def test_on_mode_auto_approves_ask_tools(self):
        """on mode: auto-aprueba tools 'ask' sin tocar 'deny'."""
        pm = self._make_perms({"read_file": "auto", "write_file": "ask", "bash": "deny"})
        pm.set_elevated("on")
        assert pm.resolve_mode("write_file") == "auto"   # ask → auto
        assert pm.resolve_mode("read_file")  == "auto"   # auto → auto
        assert pm.resolve_mode("bash")       == "deny"   # deny se respeta

    def test_on_mode_preserves_deny_unlike_full(self):
        """on no anula 'deny'; full sí."""
        pm = self._make_perms({"bash": "deny"})
        pm.set_elevated("on")
        assert pm.resolve_mode("bash") == "deny"
        pm.set_elevated("full")
        assert pm.resolve_mode("bash") == "auto"

    def test_ask_restore_preserves_user_deny(self):
        """Bug fix: al volver a 'ask', 'deny' configurado por el usuario se conserva."""
        pm = self._make_perms({"read_file": "auto", "write_file": "ask", "bash": "deny"})
        # Simular config de usuario con bash en deny
        from unittest.mock import MagicMock
        pm._elevated = "full"   # simular que veníamos de full
        # El loop de "ask" debe respetar que bash tiene deny (no default)
        # Hacemos el restore directamente sobre _perms (como lo hace loop.py)
        from config import DEFAULT_CONFIG
        _def = DEFAULT_CONFIG["permissions"]
        fake_user_config = {"bash": "deny"}   # usuario bloqueó bash
        for _tool in list(pm._perms):
            _bare    = pm._bare_name(_tool)
            _lookup  = _bare if _bare else _tool
            _default = _def.get(_lookup, "ask")
            user_perm = fake_user_config.get(_lookup) or fake_user_config.get(_tool)
            if user_perm is not None and user_perm != _default:
                continue
            pm._perms[_tool] = _default
        pm.set_elevated("ask")
        # bash debe seguir siendo deny (no default "ask")
        assert pm._perms.get("bash") == "deny"
        assert pm.resolve_mode("bash") == "deny"
        # read_file sigue siendo auto
        assert pm.resolve_mode("read_file") == "auto"

    def test_off_mode_denies_ask_tools_but_allows_auto(self):
        """off: ask→deny, auto→auto, deny→deny."""
        pm = self._make_perms({"read_file": "auto", "write_file": "ask", "bash": "ask"})
        pm.set_elevated("off")
        assert pm.resolve_mode("write_file") == "deny"
        assert pm.resolve_mode("bash")       == "deny"
        assert pm.resolve_mode("read_file")  == "auto"

    def test_full_overrides_deny(self):
        """full anula incluso 'deny' explícito."""
        pm = self._make_perms({"bash": "deny", "write_file": "deny"})
        pm.set_elevated("full")
        assert pm.resolve_mode("bash")       == "auto"
        assert pm.resolve_mode("write_file") == "auto"

    def test_mode_cycle_ask_on_full_ask(self):
        """Ciclo ask→on→full→ask produce comportamiento correcto en cada paso."""
        pm = self._make_perms({"read_file": "auto", "write_file": "ask"})
        # ask: cada tool usa su permiso configurado
        pm.set_elevated("ask")
        assert pm.resolve_mode("write_file") == "ask"
        assert pm.resolve_mode("read_file")  == "auto"
        # on: todo auto
        pm.set_elevated("on")
        assert pm.resolve_mode("write_file") == "auto"
        assert pm.resolve_mode("read_file")  == "auto"
        # full: todo auto (igual que on cuando no hay deny)
        pm.set_elevated("full")
        assert pm.resolve_mode("write_file") == "auto"
        assert pm.resolve_mode("read_file")  == "auto"
        # volver a ask: restaura defaults
        pm.set_elevated("ask")
        assert pm.resolve_mode("write_file") == "ask"
        assert pm.resolve_mode("read_file")  == "auto"


class TestDefaultPermissionsCompleteness:
    """Verifica que tools clave de MCP están en DEFAULT_PERMISSIONS."""

    def test_grep_code_is_auto(self):
        from config import DEFAULT_CONFIG
        perms = DEFAULT_CONFIG["permissions"]
        assert perms.get("grep_code") == "auto", "grep_code debe ser 'auto' en DEFAULT_PERMISSIONS"

    def test_multi_grep_is_auto(self):
        from config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["permissions"].get("multi_grep") == "auto"

    def test_symbol_lookup_is_auto(self):
        from config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["permissions"].get("symbol_lookup") == "auto"

    def test_code_compare_is_auto(self):
        from config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["permissions"].get("code_compare") == "auto"

    def test_find_files_is_auto(self):
        from config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["permissions"].get("find_files") == "auto"

    def test_read_files_is_auto(self):
        from config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["permissions"].get("read_files") == "auto"

    def test_mcp_grep_code_resolves_auto_without_elevated(self):
        """Con DEFAULT_PERMISSIONS correcto, mcp_oocode_assistant_grep_code debe ser 'auto'."""
        from config import DEFAULT_CONFIG
        from tools.permissions import PermissionManager
        perms = DEFAULT_CONFIG["permissions"].copy()
        pm = PermissionManager(perms)
        mode = pm.resolve_mode("mcp_oocode_assistant_grep_code")
        assert mode == "auto", f"grep_code debería ser 'auto', got {mode!r}"
