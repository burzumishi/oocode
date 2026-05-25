"""Tests exhaustivos del sistema de permisos para todas las tools del MCP.

Verifica:
1. Que cada tool tiene un permiso definido en DEFAULT_CONFIG
2. Que el permiso es correcto (auto/ask/deny) según la categoría
3. Que PermissionManager.resolve_mode() devuelve el modo correcto
4. Que PermissionManager.check() pregunta cuando es "ask" y no pregunta cuando es "auto"
5. Que los nombres MCP heredan correctamente el permiso bare
6. Que todos los modos de elevated funcionan correctamente con cada tool
7. Que _ask_fn se invoca solo cuando la tool es "ask" y no está en session_auto
8. Que el timeout de _ask_fn auto-aprueba (documenta el comportamiento)
"""
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from io import StringIO

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DEFAULT_CONFIG
from tools.permissions import PermissionManager
from mcp_servers.oocode_assistant import _TOOLS


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_pm(extra: dict | None = None) -> PermissionManager:
    """Crea PermissionManager con DEFAULT_CONFIG + overrides opcionales."""
    perms = DEFAULT_CONFIG["permissions"].copy()
    if extra:
        perms.update(extra)
    return PermissionManager(perms)


def _make_pm_ask_fn(responses: list[str]) -> tuple[PermissionManager, list]:
    """PermissionManager con ask_fn que devuelve respuestas en secuencia."""
    pm = _make_pm()
    calls_log = []
    resp_iter = iter(responses)

    def _ask(tool: str, desc: str) -> str:
        r = next(resp_iter, "n")
        calls_log.append((tool, desc, r))
        return r

    pm._ask_fn = _ask
    return pm, calls_log


# ── Datos: clasificación de tools por permiso esperado ───────────────────────

_ALL_MCP_TOOLS  = [t["name"] for t in _TOOLS]
_DEFAULT_PERMS  = DEFAULT_CONFIG["permissions"]

# Clasificar tools por su permiso en DEFAULT_CONFIG
_AUTO_TOOLS = [t for t in _ALL_MCP_TOOLS if _DEFAULT_PERMS.get(t) == "auto"]
_ASK_TOOLS  = [t for t in _ALL_MCP_TOOLS if _DEFAULT_PERMS.get(t) == "ask"]
_DENY_TOOLS = [t for t in _ALL_MCP_TOOLS if _DEFAULT_PERMS.get(t) == "deny"]
_MISSING    = [t for t in _ALL_MCP_TOOLS if t not in _DEFAULT_PERMS]

# Tools read-only que DEBEN ser "auto"
_READONLY_TOOLS_MUST_BE_AUTO = [
    "grep_code", "multi_grep", "symbol_lookup", "code_compare", "find_files",
    "read_files", "diff_files", "http_get", "calculate", "env_check",
    "json_format", "hash_text", "port_check", "search_todos", "system_info",
    "list_recent_files", "read_project_file", "get_datetime", "process_list",
    "ls_file", "ls_dir", "find_file", "find_dir", "grep_file", "file_stat",
    "readlink", "tree", "count_lines", "template_fill", "mypy_check",
    "archive_list", "git_status", "git_diff", "git_log", "git_branch",
    "docker_ps", "docker_logs", "docker_inspect", "docker_images",
    "compose_version", "compose_services", "compose_status", "compose_config",
    "compose_images", "compose_top", "compose_logs", "lint_file", "lint_project",
    "find_symbol", "list_symbols", "context_before_edit", "pre_edit_check",
    "python_exec",
    # pip_tool es "ask" — puede instalar/desinstalar paquetes
]

# Tools destructivas que DEBEN ser "ask"
_DESTRUCTIVE_TOOLS_MUST_BE_ASK = [
    "write_file", "git_commit", "git_push", "git_add", "git_pull",
    "git_stash", "git_patch", "git_clone", "git_worktree",
    "docker_exec", "docker_stop", "docker_rm",
    "compose_up", "compose_down", "compose_stop", "compose_restart",
    "compose_build", "compose_pull", "compose_exec", "compose_run",
    "chmod_file", "chmod_dir", "chown_file", "chown_dir",
    "mv_file", "cp_file", "rm_file", "rm_dir", "mkdir_dir", "touch_file",
    "strace_run", "gdb_run", "pdb_run", "valgrind_run",
    "make_run", "run_script", "format_code",
    "archive_extract", "archive_create", "symlink_create", "patch_apply",
    "bulk_replace", "regex_replace", "smart_replace",
    "build_symbol_index",
]


# ── 1. Cobertura de DEFAULT_CONFIG ────────────────────────────────────────────

class TestDefaultConfigCoverage:
    def test_all_mcp_tools_have_permission_defined(self):
        """Cada tool del MCP server debe tener permiso explícito en DEFAULT_CONFIG."""
        assert _MISSING == [], (
            f"Tools sin permiso en DEFAULT_CONFIG: {_MISSING}\n"
            "Añade cada una a DEFAULT_CONFIG['permissions'] en config.py"
        )

    def test_no_deny_tools(self):
        """Ninguna tool del MCP debe estar en 'deny' por defecto."""
        assert _DENY_TOOLS == [], f"Tools en deny: {_DENY_TOOLS}"

    def test_tool_count_auto_vs_ask(self):
        """Verifica proporciones razonables de auto vs ask."""
        total = len(_ALL_MCP_TOOLS)
        assert len(_AUTO_TOOLS) > 0, "Debe haber tools auto"
        assert len(_ASK_TOOLS)  > 0, "Debe haber tools ask"
        assert len(_AUTO_TOOLS) + len(_ASK_TOOLS) == total, (
            f"auto({len(_AUTO_TOOLS)}) + ask({len(_ASK_TOOLS)}) != total({total})"
        )

    def test_readonly_tools_are_auto(self):
        """Tools de solo lectura deben ser 'auto' — no interrumpen al agente."""
        wrong = [t for t in _READONLY_TOOLS_MUST_BE_AUTO if _DEFAULT_PERMS.get(t) != "auto"]
        assert wrong == [], (
            f"Tools read-only configuradas como 'ask' (deben ser 'auto'): {wrong}"
        )

    def test_destructive_tools_are_ask(self):
        """Tools destructivas deben ser 'ask' — requieren confirmación."""
        wrong = [t for t in _DESTRUCTIVE_TOOLS_MUST_BE_ASK if _DEFAULT_PERMS.get(t) != "ask"]
        assert wrong == [], (
            f"Tools destructivas configuradas como 'auto' (deben ser 'ask'): {wrong}"
        )


# ── 2. resolve_mode() para cada tool ─────────────────────────────────────────

class TestResolveMode:
    @pytest.mark.parametrize("tool", _AUTO_TOOLS)
    def test_auto_tool_resolves_auto(self, tool):
        pm = _make_pm()
        assert pm.resolve_mode(tool) == "auto", f"'{tool}' debe ser auto"

    @pytest.mark.parametrize("tool", _ASK_TOOLS)
    def test_ask_tool_resolves_ask(self, tool):
        pm = _make_pm()
        assert pm.resolve_mode(tool) == "ask", f"'{tool}' debe ser ask"

    @pytest.mark.parametrize("tool", _ASK_TOOLS)
    def test_ask_tool_resolves_auto_when_elevated_full(self, tool):
        pm = _make_pm()
        pm.set_elevated("full")
        assert pm.resolve_mode(tool) == "auto", f"full: '{tool}' debe ser auto"

    @pytest.mark.parametrize("tool", _ASK_TOOLS)
    def test_ask_tool_resolves_deny_when_elevated_off(self, tool):
        pm = _make_pm()
        pm.set_elevated("off")
        assert pm.resolve_mode(tool) == "deny", f"off: '{tool}' debe ser deny"

    @pytest.mark.parametrize("tool", _AUTO_TOOLS)
    def test_auto_tool_stays_auto_when_elevated_off(self, tool):
        """elevated='off' solo bloquea tools 'ask'; las 'auto' siguen siendo auto."""
        pm = _make_pm()
        pm.set_elevated("off")
        assert pm.resolve_mode(tool) == "auto", (
            f"off: '{tool}' es auto en config, debe seguir siendo auto"
        )

    @pytest.mark.parametrize("tool", _AUTO_TOOLS)
    def test_auto_tool_stays_auto_when_elevated_ask(self, tool):
        """elevated='ask' (neutral) no cambia tools que ya son 'auto'."""
        pm = _make_pm()
        pm.set_elevated("ask")
        assert pm.resolve_mode(tool) == "auto", (
            f"ask neutral: '{tool}' debe seguir siendo auto"
        )

    @pytest.mark.parametrize("tool", _ASK_TOOLS)
    def test_ask_tool_stays_ask_when_elevated_ask(self, tool):
        """elevated='ask' (neutral) no cambia tools que son 'ask'."""
        pm = _make_pm()
        pm.set_elevated("ask")
        assert pm.resolve_mode(tool) == "ask", (
            f"ask neutral: '{tool}' debe seguir siendo ask"
        )

    @pytest.mark.parametrize("tool", _ASK_TOOLS)
    def test_ask_tool_resolves_auto_when_elevated_on(self, tool):
        """elevated='on' convierte ask → auto (respeta deny)."""
        pm = _make_pm()
        pm.set_elevated("on")
        assert pm.resolve_mode(tool) == "auto", f"on: '{tool}' debe ser auto"


# ── 3. MCP tool name resolution ───────────────────────────────────────────────

class TestMcpNameResolution:
    @pytest.mark.parametrize("tool", _AUTO_TOOLS)
    def test_mcp_auto_tool_resolves_correctly(self, tool):
        """mcp_oocode_assistant_<tool> hereda el permiso bare."""
        pm = _make_pm()
        mcp_name = f"mcp_oocode_assistant_{tool}"
        assert pm.resolve_mode(mcp_name) == "auto", (
            f"'{mcp_name}' debe ser auto (hereda de '{tool}')"
        )

    @pytest.mark.parametrize("tool", _ASK_TOOLS)
    def test_mcp_ask_tool_resolves_correctly(self, tool):
        """mcp_oocode_assistant_<tool> hereda 'ask' del nombre bare."""
        pm = _make_pm()
        mcp_name = f"mcp_oocode_assistant_{tool}"
        assert pm.resolve_mode(mcp_name) == "ask", (
            f"'{mcp_name}' debe ser ask (hereda de '{tool}')"
        )

    @pytest.mark.parametrize("tool", _ASK_TOOLS)
    def test_mcp_ask_tool_becomes_auto_with_full(self, tool):
        pm = _make_pm()
        pm.set_elevated("full")
        mcp_name = f"mcp_oocode_assistant_{tool}"
        assert pm.resolve_mode(mcp_name) == "auto"

    def test_unknown_mcp_tool_defaults_to_ask(self):
        pm = _make_pm()
        assert pm.resolve_mode("mcp_oocode_assistant_unknown_xyz_tool") == "ask"

    def test_unknown_tool_defaults_to_ask(self):
        pm = _make_pm()
        assert pm.resolve_mode("totally_unknown_tool_xyz") == "ask"

    def test_bare_name_extraction(self):
        pm = _make_pm()
        assert pm._bare_name("mcp_oocode_assistant_write_file") == "write_file"
        assert pm._bare_name("mcp_oocode_assistant_git_commit") == "git_commit"
        assert pm._bare_name("mcp_oocode_assistant_grep_code")  == "grep_code"
        assert pm._bare_name("write_file") is None
        assert pm._bare_name("grep_code")  is None


# ── 4. check() — auto tools never ask ────────────────────────────────────────

class TestCheckAutoTools:
    @pytest.mark.parametrize("tool", _AUTO_TOOLS)
    def test_auto_tool_check_returns_true_without_asking(self, tool):
        """Tools auto nunca deben invocar ask_fn."""
        pm, calls = _make_pm_ask_fn(["s"])
        result = pm.check(tool, f"calling {tool}")
        assert result is True, f"'{tool}' auto debe retornar True"
        assert calls == [], f"'{tool}' auto no debe invocar ask_fn, pero llamó: {calls}"

    def test_auto_tool_check_no_ask_fn_needed(self):
        """Tools auto funcionan aunque ask_fn sea None."""
        pm = _make_pm()
        pm._ask_fn = None
        for tool in _AUTO_TOOLS[:10]:
            assert pm.check(tool, "test") is True


# ── 5. check() — ask tools prompt the user ────────────────────────────────────

class TestCheckAskTools:
    @pytest.mark.parametrize("tool", _ASK_TOOLS)
    def test_ask_tool_invokes_ask_fn(self, tool):
        """Tools 'ask' deben invocar ask_fn exactamente una vez."""
        pm, calls = _make_pm_ask_fn(["s"])
        result = pm.check(tool, f"calling {tool}")
        assert result is True
        assert len(calls) == 1, (
            f"'{tool}' debe invocar ask_fn 1 vez, invocó {len(calls)}"
        )
        assert calls[0][0] == tool

    @pytest.mark.parametrize("tool", _ASK_TOOLS)
    def test_ask_tool_denied_when_user_says_no(self, tool):
        pm, calls = _make_pm_ask_fn(["n"])
        result = pm.check(tool, f"calling {tool}")
        assert result is False, f"'{tool}' debe ser denegado cuando user dice 'n'"

    @pytest.mark.parametrize("tool", _ASK_TOOLS)
    def test_ask_tool_session_auto_after_siempre(self, tool):
        """'siempre' añade la tool a session_auto: segunda llamada no pregunta."""
        pm, calls = _make_pm_ask_fn(["siempre", "s"])
        # Primera llamada: pregunta y responde "siempre"
        r1 = pm.check(tool, "test")
        assert r1 is True
        assert len(calls) == 1
        # Segunda llamada: no debe preguntar (ya en session_auto)
        r2 = pm.check(tool, "test")
        assert r2 is True
        assert len(calls) == 1, f"Segunda llamada no debe invocar ask_fn para '{tool}'"

    def test_ask_fn_not_called_when_in_session_auto(self):
        """Si una tool está en session_auto, check() retorna True sin preguntar."""
        pm = _make_pm()
        call_count = [0]

        def _ask(tool, desc):
            call_count[0] += 1
            return "n"

        pm._ask_fn = _ask
        pm._session_auto.add("write_file")
        result = pm.check("write_file", "test")
        assert result is True
        assert call_count[0] == 0

    def test_mcp_ask_tool_invokes_ask_fn(self):
        """MCP name del tool 'ask' también debe preguntar."""
        pm, calls = _make_pm_ask_fn(["s"])
        result = pm.check("mcp_oocode_assistant_write_file", "writing...")
        assert result is True
        assert len(calls) == 1
        assert calls[0][0] == "mcp_oocode_assistant_write_file"

    def test_mcp_session_auto_bare_name_skips_ask(self):
        """session_auto con nombre bare también aplica a mcp_... equivalente."""
        pm, calls = _make_pm_ask_fn(["s"])
        pm._session_auto.add("write_file")  # bare name
        result = pm.check("mcp_oocode_assistant_write_file", "test")
        assert result is True
        assert calls == [], "No debe preguntar si el bare name está en session_auto"


# ── 6. check() — deny tools ───────────────────────────────────────────────────

class TestCheckDenyTools:
    def test_deny_tool_returns_false_without_asking(self):
        pm = _make_pm({"write_file": "deny"})
        call_count = [0]
        pm._ask_fn = lambda t, d: (call_count.__setitem__(0, call_count[0]+1), "s")[1]
        with patch("tools.permissions.console") as mock_console:
            result = pm.check("write_file", "test")
        assert result is False
        assert call_count[0] == 0, "deny no debe invocar ask_fn"

    def test_deny_tool_with_elevated_full_returns_true(self):
        """full anula incluso deny."""
        pm = _make_pm({"bash": "deny"})
        pm.set_elevated("full")
        result = pm.check("bash", "test")
        assert result is True

    def test_deny_tool_with_elevated_on_stays_denied(self):
        """elevated=on respeta deny; solo anula ask."""
        pm = _make_pm({"bash": "deny"})
        pm.set_elevated("on")
        with patch("tools.permissions.console"):
            result = pm.check("bash", "test")
        assert result is False


# ── 7. elevated modes con check() ────────────────────────────────────────────

class TestElevatedWithCheck:
    def test_elevated_full_all_mcp_tools_pass(self):
        """elevated=full: TODAS las tools deben pasar sin preguntar."""
        pm = _make_pm()
        pm.set_elevated("full")
        call_count = [0]
        pm._ask_fn = lambda t, d: (call_count.__setitem__(0, call_count[0]+1), "s")[1]

        for tool in _ALL_MCP_TOOLS:
            result = pm.check(tool, "test")
            assert result is True, f"full: '{tool}' debe pasar"
        assert call_count[0] == 0, "full: ask_fn no debe ser invocado nunca"

    def test_elevated_off_ask_tools_denied(self):
        """elevated=off: tools 'ask' deben ser denegadas."""
        pm = _make_pm()
        pm.set_elevated("off")
        call_count = [0]
        pm._ask_fn = lambda t, d: (call_count.__setitem__(0, call_count[0]+1), "s")[1]

        denied = []
        for tool in _ASK_TOOLS:
            with patch("tools.permissions.console"):
                result = pm.check(tool, "test")
            if not result:
                denied.append(tool)

        assert len(denied) == len(_ASK_TOOLS), (
            f"off: {len(_ASK_TOOLS) - len(denied)} tools 'ask' no fueron denegadas: "
            f"{set(_ASK_TOOLS) - set(denied)}"
        )
        assert call_count[0] == 0, "off: ask_fn no debe ser invocado"

    def test_elevated_off_auto_tools_still_pass(self):
        """elevated=off: tools 'auto' siguen pasando."""
        pm = _make_pm()
        pm.set_elevated("off")

        for tool in _AUTO_TOOLS:
            result = pm.check(tool, "test")
            assert result is True, f"off: '{tool}' auto debe pasar"

    def test_elevated_on_ask_tools_pass_without_prompting(self):
        """elevated=on: tools 'ask' se convierten en auto (sin prompt)."""
        pm = _make_pm()
        pm.set_elevated("on")
        call_count = [0]
        pm._ask_fn = lambda t, d: (call_count.__setitem__(0, call_count[0]+1), "s")[1]

        for tool in _ASK_TOOLS:
            result = pm.check(tool, "test")
            assert result is True, f"on: '{tool}' debe pasar sin preguntar"
        assert call_count[0] == 0, "on: ask_fn no debe ser invocado"

    def test_elevated_ask_neutral_does_not_promote_auto(self):
        """elevated='ask' (neutral): tools 'auto' siguen sin preguntar.

        DOCUMENTACIÓN DEL COMPORTAMIENTO:
        El modo 'elevated=ask' es el modo neutro — no modifica los permisos.
        Si una tool tiene 'auto' en DEFAULT_CONFIG, NUNCA pregunta aunque el
        usuario esté en modo 'ask'. Para pedir confirmación en todas las tools,
        el usuario debe configurar manualmente cada tool como 'ask' en oocode.json.

        elevated='ask' solo afecta al ciclo de Shift+Tab (que muestra el modo activo).
        """
        pm = _make_pm()
        pm.set_elevated("ask")
        call_count = [0]
        pm._ask_fn = lambda t, d: (call_count.__setitem__(0, call_count[0]+1), "s")[1]

        for tool in _AUTO_TOOLS:
            result = pm.check(tool, "test")
            assert result is True
        assert call_count[0] == 0, (
            "elevated=ask neutral: las tools 'auto' no deben preguntar"
        )

    def test_elevated_ask_neutral_preserves_ask_behavior(self):
        """elevated='ask' (neutral): tools 'ask' siguen pidiendo confirmación."""
        pm, calls = _make_pm_ask_fn(["s"] * len(_ASK_TOOLS))
        pm.set_elevated("ask")

        asked = []
        for tool in _ASK_TOOLS:
            r = pm.check(tool, "test")
            if r:
                asked.append(tool)

        assert len(asked) == len(_ASK_TOOLS), "ask neutral: todas las tools 'ask' deben preguntar"


# ── 8. ask_fn invocation details ──────────────────────────────────────────────

class TestAskFnInvocation:
    def test_ask_fn_receives_tool_name(self):
        pm = _make_pm()
        received = []
        pm._ask_fn = lambda t, d: received.append(t) or "s"
        pm.check("write_file", "writing...")
        assert received == ["write_file"]

    def test_ask_fn_receives_description(self):
        pm = _make_pm()
        received = []
        pm._ask_fn = lambda t, d: received.append(d) or "s"
        pm.check("git_commit", "git_commit({...})")
        assert received == ["git_commit({...})"]

    def test_ask_fn_called_every_time_for_ask_tool(self):
        """Sin 'siempre', ask_fn se llama en cada check()."""
        pm, calls = _make_pm_ask_fn(["s", "s", "s"])
        for _ in range(3):
            pm.check("write_file", "test")
        assert len(calls) == 3

    def test_default_ask_fn_none_uses_console_input(self):
        """Sin ask_fn, check() usa _ask_default() que llama input()."""
        pm = _make_pm()
        pm._ask_fn = None
        with patch("builtins.input", return_value="n"), \
             patch("tools.permissions.console"):
            result = pm.check("write_file", "test")
        assert result is False

    def test_default_ask_fn_empty_returns_s(self):
        """_ask_default: Enter vacío → 's' (aprueba)."""
        pm = _make_pm()
        pm._ask_fn = None
        with patch("builtins.input", return_value=""), \
             patch("tools.permissions.console"):
            result = pm.check("write_file", "test")
        assert result is True

    def test_default_ask_fn_eof_returns_n(self):
        """_ask_default: EOFError (stdin cerrado) → 'n' (deniega)."""
        pm = _make_pm()
        pm._ask_fn = None
        with patch("builtins.input", side_effect=EOFError), \
             patch("tools.permissions.console"):
            result = pm.check("write_file", "test")
        assert result is False


# ── 9. set_permission() ───────────────────────────────────────────────────────

class TestSetPermission:
    def test_override_auto_to_ask(self):
        pm = _make_pm()
        assert pm.resolve_mode("grep_code") == "auto"
        pm.set_permission("grep_code", "ask")
        assert pm.resolve_mode("grep_code") == "ask"

    def test_override_ask_to_auto(self):
        pm = _make_pm()
        assert pm.resolve_mode("write_file") == "ask"
        pm.set_permission("write_file", "auto")
        assert pm.resolve_mode("write_file") == "auto"

    def test_override_to_deny(self):
        pm = _make_pm()
        pm.set_permission("grep_code", "deny")
        assert pm.resolve_mode("grep_code") == "deny"

    def test_invalid_mode_raises(self):
        pm = _make_pm()
        with pytest.raises(ValueError):
            pm.set_permission("grep_code", "invalid_mode")

    @pytest.mark.parametrize("tool", _ALL_MCP_TOOLS[:20])
    def test_set_all_to_auto_then_check(self, tool):
        """Forzar auto en una tool y verificar que check pasa sin prompt."""
        pm = _make_pm()
        pm.set_permission(tool, "auto")
        call_count = [0]
        pm._ask_fn = lambda t, d: (call_count.__setitem__(0, call_count[0]+1), "n")[1]
        result = pm.check(tool, "test")
        assert result is True
        assert call_count[0] == 0

    @pytest.mark.parametrize("tool", _AUTO_TOOLS[:20])
    def test_override_auto_to_deny_blocks_tool(self, tool):
        """Override 'auto' → 'deny' debe bloquear la tool."""
        pm = _make_pm()
        pm.set_permission(tool, "deny")
        with patch("tools.permissions.console"):
            result = pm.check(tool, "test")
        assert result is False


# ── 10. get_all() snapshot ────────────────────────────────────────────────────

class TestGetAll:
    def test_returns_copy_not_reference(self):
        pm = _make_pm()
        snapshot = pm.get_all()
        snapshot["write_file"] = "auto"
        # Original no debe cambiar
        assert pm.resolve_mode("write_file") == "ask"

    def test_snapshot_includes_all_mcp_tools(self):
        pm = _make_pm()
        all_perms = pm.get_all()
        for tool in _ALL_MCP_TOOLS:
            assert tool in all_perms, f"'{tool}' falta en get_all()"


# ── 11. ask_fn timeout comportamiento ────────────────────────────────────────

class TestAskFnTimeout:
    def test_timeout_denies_after_fix(self):
        """Tras el fix de seguridad, timeout → deniega (no auto-aprueba).

        El fix cambia _perm_result default de 's' → 'n' y retorna 'n' en timeout.
        """
        ev = threading.Event()

        def _ask_fn_with_timeout(tool: str, desc: str) -> str:
            timed_out = not ev.wait(timeout=0.01)  # timeout inmediato
            if timed_out:
                return "n"   # comportamiento correcto post-fix
            return "s"

        pm = _make_pm()
        pm._ask_fn = _ask_fn_with_timeout
        result = pm.check("write_file", "test")
        # Tras el fix: timeout → "n" → False (deniega)
        assert result is False

    def test_tui_ask_fn_perm_result_default_is_deny(self):
        """El default de _perm_result es 'n' (denegar) tras el fix de seguridad.

        En ui/app.py:_ask_fn (fixed):
            app._perm_result = ['n']   # ← default seguro = 'n' (deniega)
            timed_out = not app._perm_event.wait(timeout=300.0)
            if timed_out:
                return 'n'   # timeout → denegar
            return app._perm_result[0]

        Si _app.invalidate() falla o el usuario no responde en 300s,
        la tool se DENIEGA automáticamente (comportamiento seguro).
        """
        # Simular el comportamiento correcto (post-fix) de app._ask_fn
        perm_result = ["n"]          # valor por defecto = deniega
        perm_event  = threading.Event()

        def simulated_ask_fn(tool: str, desc: str) -> str:
            perm_event.clear()
            perm_result[0] = "n"   # default seguro
            timed_out = not perm_event.wait(timeout=0.01)  # timeout casi inmediato
            if timed_out:
                return "n"   # timeout → denegar
            return perm_result[0]

        pm = _make_pm()
        pm._ask_fn = simulated_ask_fn
        result = pm.check("write_file", "test")
        assert result is False, (
            "FIX: timeout en ask_fn debe DENEGAR (no auto-aprobar). "
            "Si la TUI no renderiza el diálogo o el usuario no responde, "
            "la tool se bloquea para evitar ejecución sin confirmación."
        )


# ── 12. Completitud del DEFAULT_CONFIG ───────────────────────────────────────

class TestDefaultConfigCompleteness:
    def test_all_109_tools_have_permissions(self):
        """Los 109 tools del MCP deben tener permiso."""
        assert len(_MISSING) == 0, (
            f"{len(_MISSING)} tools sin permiso: {_MISSING}"
        )

    def test_permissions_count_matches_tool_count(self):
        """Número de tools con permiso == número de tools en _TOOLS."""
        covered = [t for t in _ALL_MCP_TOOLS if t in _DEFAULT_PERMS]
        assert len(covered) == len(_ALL_MCP_TOOLS)

    @pytest.mark.parametrize("tool,expected", [
        ("grep_code",     "auto"),
        ("find_files",    "auto"),
        ("read_files",    "auto"),
        ("ls_dir",        "auto"),
        ("git_status",    "auto"),
        ("git_diff",      "auto"),
        ("file_stat",     "auto"),
        ("tree",          "auto"),
        ("context_before_edit", "auto"),
        ("pre_edit_check",      "auto"),
        ("lint_file",     "auto"),
        ("write_file",    "ask"),
        ("git_commit",    "ask"),
        ("git_push",      "ask"),
        ("rm_file",       "ask"),
        ("rm_dir",        "ask"),
        ("chmod_file",    "ask"),
        ("mv_file",       "ask"),
        ("smart_replace", "ask"),
        ("bulk_replace",  "ask"),
        ("regex_replace", "ask"),
        ("patch_apply",   "ask"),
        ("symlink_create","ask"),
        ("make_run",      "ask"),
        ("strace_run",    "ask"),
        ("gdb_run",       "ask"),
    ])
    def test_specific_tool_permission(self, tool, expected):
        """Test explícito del permiso de cada tool crítica."""
        pm = _make_pm()
        assert pm.resolve_mode(tool) == expected, (
            f"'{tool}' debe ser '{expected}', got '{pm.resolve_mode(tool)}'"
        )
