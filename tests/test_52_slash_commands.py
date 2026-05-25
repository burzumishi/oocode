"""Tests for /slash commands: SLASH_HELP completeness and handle_slash dispatch."""
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


class TestSlashHelpCompleteness(unittest.TestCase):
    """Verify SLASH_HELP structure and contents."""

    def _sh(self):
        from ui.commands import SLASH_HELP
        return SLASH_HELP

    def test_slash_help_is_dict_of_dicts(self):
        sh = self._sh()
        self.assertIsInstance(sh, dict)
        for cat, cmds in sh.items():
            self.assertIsInstance(cat, str, f"category key must be str: {cat!r}")
            self.assertIsInstance(cmds, dict, f"category value must be dict: {cat!r}")

    def test_slash_help_has_required_categories(self):
        sh = self._sh()
        required = {
            "Sesión y contexto", "Tareas y planificación", "Memoria",
            "Extensiones", "Modos de respuesta", "Permisos y activación",
            "Agentes y modelos", "Hooks", "Herramientas de código",
            "Integraciones", "Sistema",
        }
        missing = required - set(sh.keys())
        self.assertFalse(missing, f"Missing categories: {missing}")

    def test_slash_help_entries_are_strings(self):
        for cat, cmds in self._sh().items():
            for k, v in cmds.items():
                self.assertIsInstance(k, str, f"key must be str in {cat}")
                self.assertIsInstance(v, str, f"value must be str in {cat}")

    def test_slash_help_core_commands_present(self):
        """Spot-check that core commands appear somewhere in SLASH_HELP."""
        all_keys = " ".join(
            k for cmds in self._sh().values() for k in cmds.keys()
        )
        for cmd in ["/new", "/compact", "/mem", "/think", "/elevated",
                    "/model", "/hooks", "/lsp", "/mcp", "/rag", "/doctor",
                    "/config", "/help", "/exit"]:
            self.assertIn(cmd, all_keys, f"{cmd} not found in SLASH_HELP")

    def test_slash_help_no_empty_descriptions(self):
        for cat, cmds in self._sh().items():
            for k, v in cmds.items():
                self.assertTrue(v.strip(), f"Empty description for {k!r} in {cat!r}")


class TestHandleSlashDispatch(unittest.TestCase):
    """Verify handle_slash() routes all documented commands without crashing."""

    def _make_loop(self):
        """Build a minimal AgentLoop mock."""
        loop = MagicMock()
        loop.rt = MagicMock()
        loop.rt.elevated = "ask"
        loop.rt.think_level = "off"
        loop.rt.reasoning = False
        loop.rt.verbose = False
        loop.rt.trace = False
        loop.context = MagicMock()
        loop.context.stats.return_value = {
            "messages": 0, "tokens_estimate": 0, "max_tokens": 8000,
            "summary_chars": 0, "has_summary": False,
        }
        loop.session = MagicMock()
        loop.memory = MagicMock()
        loop.memory._dir = MagicMock()
        loop.memory._dir.glob.return_value = []
        loop.memory.has_memories.return_value = False
        loop.memory.list_all.return_value = []
        loop.plugins = None
        loop._plan_tasks = []
        loop.config = MagicMock()
        loop.config.model = "test-model"
        return loop

    def _make_config(self):
        cfg = MagicMock()
        cfg.model = "test-model"
        return cfg

    def _call(self, cmd, args=""):
        from ui.commands import handle_slash
        full = f"{cmd} {args}".strip()
        loop = self._make_loop()
        cfg = self._make_config()
        with patch("ui.commands.console"), \
             patch("ui.commands.print_help"), \
             patch("ui.commands.print_commands"), \
             patch("ui.commands.print_status"), \
             patch("ui.commands.print_ctx_status"), \
             patch("ui.commands.print_config"), \
             patch("ui.commands.print_runtime"), \
             patch("ui.commands.print_splash"), \
             patch("ui.commands.print_gateway_status"):
            result = handle_slash(full, loop, cfg)
        return result

    def test_exit_returns_false(self):
        for cmd in ("/exit", "/quit", "/q"):
            with self.subTest(cmd=cmd):
                self.assertFalse(self._call(cmd))

    def test_most_commands_return_true(self):
        commands = [
            "/new", "/reset", "/context", "/compact", "/compact fast",
            "/resume", "/checkpoint", "/clear", "/abort",
            "/tasks", "/kill", "/mem", "/mem list",
            "/think off", "/think medium",
            "/verbose on", "/verbose off",
            "/trace on", "/trace off",
            "/elevated ask", "/elevated on", "/elevated off", "/elevated full",
            "/elev ask",
            "/activation always",
            "/commands",
            "/splash", "/tip",
            "/help", "/?",
        ]
        for cmd in commands:
            with self.subTest(cmd=cmd):
                result = self._call(cmd)
                self.assertTrue(result, f"{cmd!r} should return True")

    def test_unknown_command_returns_true(self):
        result = self._call("/nonexistent_command_xyz")
        self.assertTrue(result)

    def test_all_slash_help_keys_have_dispatch(self):
        """Check that handle_slash() source mentions each primary command."""
        import inspect
        from ui.commands import handle_slash
        source = inspect.getsource(handle_slash)
        # Extract primary command tokens from SLASH_HELP keys
        from ui.commands import SLASH_HELP
        missing = []
        for cmds in SLASH_HELP.values():
            for key in cmds.keys():
                # Get first token (may be "/cmd1  /cmd2" — check first one)
                primary = key.strip().split()[0]
                if not primary.startswith("/"):
                    continue
                # Remove trailing punctuation used in display
                primary = primary.rstrip(".,;:")
                # Skip aliases that share dispatch branches and truly compound ones
                if primary in ("/elev", "/memory", "/adddir", "/?",
                               "/gwstatus", "/settings", "/spawn"):
                    continue
                if primary not in source:
                    missing.append(primary)
        self.assertFalse(missing, f"Commands not found in handle_slash source: {missing}")


class TestHelpOutput(unittest.TestCase):
    """Test print_help and print_commands don't crash."""

    def test_print_help_runs(self):
        from ui.commands import print_help, SLASH_HELP
        import io
        from unittest.mock import patch
        with patch("ui.commands.console") as mc:
            print_help(SLASH_HELP)
        # Just checking it doesn't raise

    def test_print_commands_runs(self):
        from ui.commands import print_commands, SLASH_HELP
        with patch("ui.commands.console"):
            print_commands(SLASH_HELP)


class TestHooksCommand(unittest.TestCase):
    """Verify /hooks command works."""

    def test_hooks_dispatch_exists(self):
        import inspect
        from ui.commands import handle_slash
        src = inspect.getsource(handle_slash)
        self.assertIn('"/hooks"', src)

    def test_hooks_builtin_list_available(self):
        from tools.hooks import HookManager
        hm = HookManager()
        names = hm.available_builtins()
        self.assertIn("diff_after_write", names)
        self.assertIn("lint_after_write", names)
        self.assertIn("backup_before_write", names)
        self.assertIn("test_suite_delta", names)

    def test_backup_before_write_is_pre_post(self):
        from tools.hooks import _BUILTINS
        kind, _, fn = _BUILTINS["backup_before_write"]
        self.assertEqual(kind, "pre+post")
        pre_fn, post_fn = fn
        self.assertTrue(callable(pre_fn))
        self.assertTrue(callable(post_fn))


class TestConfigCommand(unittest.TestCase):
    """Verify /config dispatch exists."""

    def test_config_in_handle_slash(self):
        import inspect
        from ui.commands import handle_slash
        src = inspect.getsource(handle_slash)
        self.assertIn('"/config"', src)

    def test_doctor_in_handle_slash(self):
        import inspect
        from ui.commands import handle_slash
        src = inspect.getsource(handle_slash)
        self.assertIn('"/doctor"', src)

    def test_lsp_in_handle_slash(self):
        import inspect
        from ui.commands import handle_slash
        src = inspect.getsource(handle_slash)
        self.assertIn('"/lsp"', src)

    def test_mcp_in_handle_slash(self):
        import inspect
        from ui.commands import handle_slash
        src = inspect.getsource(handle_slash)
        self.assertIn('"/mcp"', src)

    def test_rag_in_handle_slash(self):
        import inspect
        from ui.commands import handle_slash
        src = inspect.getsource(handle_slash)
        self.assertIn('"/rag"', src)


if __name__ == "__main__":
    unittest.main()
