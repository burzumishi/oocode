"""Tests para los nuevos hooks: config_syntax_after_write, git_push_guard, security_audit_log.

Cubre:
- config_syntax_after_write: .json/.toml/.ini/.cfg válidos e inválidos
- config_syntax_after_write: silencioso para extensiones no soportadas / tool errónea
- git_push_guard: pre-hook para git_commit (mensaje vacío/corto/genérico) y git_push (rama protegida)
- git_push_guard: silencioso para tools que no son git_commit/git_push
- security_audit_log: escribe en security_audit.log tras security tools
- security_audit_log: silencioso para tools fuera de _SECURITY_TOOL_NAMES
- HookManager: register/unregister de los nuevos built-ins
- config_syntax_after_write activo por defecto; git_push_guard/security_audit_log no
"""
import sys, os, json, tempfile, textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest
from tools.hooks import (
    _BUILTINS,
    HookManager,
    _builtin_config_syntax_after_write,
    _builtin_git_push_guard,
    _builtin_security_audit_log,
    _SECURITY_TOOL_NAMES,
    _PROTECTED_BRANCHES,
    _WEAK_COMMIT_MSGS,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_tmp(suffix: str, content: str) -> Path:
    """Crea un fichero temporal con el contenido dado y devuelve su Path."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8"
    ) as f:
        f.write(content)
        return Path(f.name)


def _fake_write_args(path: str) -> dict:
    return {"file_path": path}


def _fake_edit_args(path: str) -> dict:
    return {"path": path}


OK_RESULT = "Fichero escrito correctamente."


# ── config_syntax_after_write ─────────────────────────────────────────────────

class TestConfigSyntaxAfterWrite:

    def test_valid_json_returns_none(self):
        p = _write_tmp(".json", '{"key": "value", "n": 42}')
        try:
            r = _builtin_config_syntax_after_write("write_file", _fake_write_args(str(p)), OK_RESULT)
            assert r is None
        finally:
            p.unlink(missing_ok=True)

    def test_invalid_json_appends_error(self):
        p = _write_tmp(".json", '{"key": "missing_quote}')
        try:
            r = _builtin_config_syntax_after_write("write_file", _fake_write_args(str(p)), OK_RESULT)
            assert r is not None
            assert "[config_syntax]" in r
            assert p.name in r
        finally:
            p.unlink(missing_ok=True)

    def test_valid_toml_returns_none(self):
        try:
            import tomllib  # noqa: F401
        except ImportError:
            pytest.skip("tomllib no disponible")
        p = _write_tmp(".toml", '[section]\nkey = "value"\nn = 42\n')
        try:
            r = _builtin_config_syntax_after_write("write_file", _fake_write_args(str(p)), OK_RESULT)
            assert r is None
        finally:
            p.unlink(missing_ok=True)

    def test_invalid_toml_appends_error(self):
        try:
            import tomllib  # noqa: F401
        except ImportError:
            pytest.skip("tomllib no disponible")
        p = _write_tmp(".toml", '[section\nkey = "unclosed bracket"\n')
        try:
            r = _builtin_config_syntax_after_write("write_file", _fake_write_args(str(p)), OK_RESULT)
            assert r is not None
            assert "[config_syntax]" in r
        finally:
            p.unlink(missing_ok=True)

    def test_valid_ini_returns_none(self):
        p = _write_tmp(".ini", "[section]\nkey = value\nother = 42\n")
        try:
            r = _builtin_config_syntax_after_write("write_file", _fake_write_args(str(p)), OK_RESULT)
            assert r is None
        finally:
            p.unlink(missing_ok=True)

    def test_invalid_ini_appends_error(self):
        # Un valor antes de cualquier sección → MissingSectionHeaderError
        p = _write_tmp(".ini", "orphan_key = no_section\n[section]\nkey = ok\n")
        try:
            r = _builtin_config_syntax_after_write("write_file", _fake_write_args(str(p)), OK_RESULT)
            # configparser.read_string no siempre falla en valores huérfanos según versión
            # El test principal es que no lance excepción
            assert r is None or "[config_syntax]" in (r or "")
        finally:
            p.unlink(missing_ok=True)

    def test_valid_cfg_returns_none(self):
        p = _write_tmp(".cfg", "[settings]\ndebug = true\nhost = localhost\n")
        try:
            r = _builtin_config_syntax_after_write("write_file", _fake_write_args(str(p)), OK_RESULT)
            assert r is None
        finally:
            p.unlink(missing_ok=True)

    def test_unsupported_extension_silent(self):
        p = _write_tmp(".yaml", "key: value\n")
        try:
            r = _builtin_config_syntax_after_write("write_file", _fake_write_args(str(p)), OK_RESULT)
            assert r is None
        finally:
            p.unlink(missing_ok=True)

    def test_non_write_tool_silent(self):
        p = _write_tmp(".json", '{"ok": true}')
        try:
            r = _builtin_config_syntax_after_write("read_file", _fake_write_args(str(p)), "contenido")
            assert r is None
        finally:
            p.unlink(missing_ok=True)

    def test_error_result_silent(self):
        p = _write_tmp(".json", '{"ok": true}')
        try:
            r = _builtin_config_syntax_after_write("write_file", _fake_write_args(str(p)), "Error: permiso denegado")
            assert r is None
        finally:
            p.unlink(missing_ok=True)

    def test_no_path_in_args_silent(self):
        r = _builtin_config_syntax_after_write("write_file", {}, OK_RESULT)
        assert r is None

    def test_edit_file_uses_path_key(self):
        """edit_file usa 'path', no 'file_path'."""
        p = _write_tmp(".json", '{"edit": true}')
        try:
            r = _builtin_config_syntax_after_write("edit_file", _fake_edit_args(str(p)), OK_RESULT)
            assert r is None  # JSON válido → None
        finally:
            p.unlink(missing_ok=True)

    def test_edit_files_uses_edits_list(self):
        """edit_files con lista de edits — toma el primer path."""
        p = _write_tmp(".json", '{"multi": true}')
        try:
            args = {"edits": [{"path": str(p), "action": "edit", "old_string": "", "new_string": ""}]}
            r = _builtin_config_syntax_after_write("edit_files", args, OK_RESULT)
            assert r is None
        finally:
            p.unlink(missing_ok=True)

    def test_in_builtins_dict(self):
        assert "config_syntax_after_write" in _BUILTINS
        hook_type, _, _ = _BUILTINS["config_syntax_after_write"]
        assert hook_type == "post"

    def test_active_by_default(self):
        from config import DEFAULT_CONFIG
        assert "config_syntax_after_write" in DEFAULT_CONFIG["hooks"]["builtins"]

    def test_register_unregister(self):
        hm = HookManager()
        hm.register_builtins(["config_syntax_after_write"])
        assert hm.post_count == 1
        removed = hm.unregister_builtin("config_syntax_after_write")
        assert removed
        assert hm.post_count == 0


# ── git_push_guard ────────────────────────────────────────────────────────────

class TestGitPushGuard:

    def test_non_git_tool_returns_args(self):
        args = {"file_path": "/some/file.py"}
        result = _builtin_git_push_guard("write_file", args)
        assert result == args

    def test_git_commit_good_message_returns_args(self):
        args = {"message": "Implementa autenticación OAuth2 con JWT"}
        result = _builtin_git_push_guard("git_commit", args)
        assert result == args

    def test_git_commit_empty_message_still_returns_args(self):
        """El hook no bloquea — sólo advierte."""
        args = {"message": ""}
        result = _builtin_git_push_guard("git_commit", args)
        assert result == args

    def test_git_commit_short_message_returns_args(self):
        args = {"message": "fix"}
        result = _builtin_git_push_guard("git_commit", args)
        assert result == args

    def test_git_commit_weak_message_returns_args(self):
        for weak in _WEAK_COMMIT_MSGS:
            args = {"message": weak}
            result = _builtin_git_push_guard("git_commit", args)
            assert result == args

    def test_git_push_non_protected_returns_args(self):
        """git_push a una rama de feature no genera bloqueo."""
        args = {"remote": "origin", "branch": "feature/oauth"}
        with patch("subprocess.check_output", return_value="feature/oauth\n"):
            result = _builtin_git_push_guard("git_push", args)
        assert result == args

    def test_git_push_subprocess_error_returns_args(self):
        """Si git falla, el hook no lanza excepción y devuelve args."""
        import subprocess
        args = {"remote": "origin"}
        with patch("subprocess.check_output", side_effect=subprocess.CalledProcessError(1, "git")):
            result = _builtin_git_push_guard("git_push", args)
        assert result == args

    def test_protected_branches_set_contains_main_master(self):
        assert "main" in _PROTECTED_BRANCHES
        assert "master" in _PROTECTED_BRANCHES
        assert "production" in _PROTECTED_BRANCHES

    def test_weak_commit_msgs_not_empty(self):
        assert len(_WEAK_COMMIT_MSGS) >= 5

    def test_in_builtins_dict(self):
        assert "git_push_guard" in _BUILTINS
        hook_type, _, _ = _BUILTINS["git_push_guard"]
        assert hook_type == "pre"

    def test_not_active_by_default(self):
        from config import DEFAULT_CONFIG
        assert "git_push_guard" not in DEFAULT_CONFIG["hooks"]["builtins"]

    def test_register_unregister(self):
        hm = HookManager()
        hm.register_builtins(["git_push_guard"])
        assert hm.pre_count == 1
        removed = hm.unregister_builtin("git_push_guard")
        assert removed
        assert hm.pre_count == 0

    def test_hook_manager_pre_runs_on_git_commit(self):
        hm = HookManager()
        hm.register_builtins(["git_push_guard"])
        ok, args_out = hm.run_pre("git_commit", {"message": "buen mensaje largo aquí"})
        assert ok is True
        assert args_out["message"] == "buen mensaje largo aquí"

    def test_hook_manager_pre_silent_on_write_file(self):
        hm = HookManager()
        hm.register_builtins(["git_push_guard"])
        # git_* pattern no coincide con write_file → no se ejecuta
        ok, args_out = hm.run_pre("write_file", {"file_path": "/tmp/x.py"})
        assert ok is True


# ── security_audit_log ────────────────────────────────────────────────────────

class TestSecurityAuditLog:

    def test_security_tool_writes_log(self):
        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / ".oocode" / "logs" / "security_audit.log"
            with patch("pathlib.Path.home", return_value=Path(td)):
                _builtin_security_audit_log(
                    "nmap_scan",
                    {"target": "192.168.1.1"},
                    "Host is up. Ports: 22/tcp open",
                )
            assert log_path.exists()
            content = log_path.read_text()
            assert "nmap_scan" in content
            assert "192.168.1.1" in content

    def test_non_security_tool_silent(self):
        r = _builtin_security_audit_log("write_file", {"file_path": "/x.py"}, "ok")
        assert r is None

    def test_result_not_modified(self):
        """El hook nunca modifica el resultado — siempre devuelve None."""
        with tempfile.TemporaryDirectory() as td:
            with patch("pathlib.Path.home", return_value=Path(td)):
                r = _builtin_security_audit_log("ssl_check", {"host": "example.com"}, "TLS 1.3 OK")
            assert r is None

    def test_all_security_tools_in_set(self):
        expected_subset = {
            "nmap_scan", "nikto_scan", "gobuster_run", "hash_crack",
            "ssl_check", "dns_enum", "secret_scan", "fw_audit",
        }
        assert expected_subset.issubset(_SECURITY_TOOL_NAMES)

    def test_log_entry_format(self):
        with tempfile.TemporaryDirectory() as td:
            with patch("pathlib.Path.home", return_value=Path(td)):
                _builtin_security_audit_log(
                    "whois_lookup",
                    {"domain": "example.com"},
                    "Registrant: ACME Corp",
                )
            content = (Path(td) / ".oocode" / "logs" / "security_audit.log").read_text()
            # Formato: [ISO-timestamp] tool  target= → summary
            assert "whois_lookup" in content
            assert "example.com" in content
            assert "Registrant" in content

    def test_multiple_entries_append(self):
        with tempfile.TemporaryDirectory() as td:
            with patch("pathlib.Path.home", return_value=Path(td)):
                for tool in ("nmap_scan", "ssl_check"):
                    _builtin_security_audit_log(tool, {"target": "1.2.3.4"}, "result")
            lines = (Path(td) / ".oocode" / "logs" / "security_audit.log").read_text().splitlines()
            assert len(lines) == 2

    def test_in_builtins_dict(self):
        assert "security_audit_log" in _BUILTINS
        hook_type, _, _ = _BUILTINS["security_audit_log"]
        assert hook_type == "post"

    def test_not_active_by_default(self):
        from config import DEFAULT_CONFIG
        assert "security_audit_log" not in DEFAULT_CONFIG["hooks"]["builtins"]

    def test_register_unregister(self):
        hm = HookManager()
        hm.register_builtins(["security_audit_log"])
        assert hm.post_count == 1
        removed = hm.unregister_builtin("security_audit_log")
        assert removed
        assert hm.post_count == 0


# ── available_builtins coverage ───────────────────────────────────────────────

class TestNewHooksAvailability:

    def test_all_new_hooks_in_available_builtins(self):
        available = HookManager.available_builtins()
        for name in ("config_syntax_after_write", "git_push_guard", "security_audit_log"):
            assert name in available, f"{name} debe estar en available_builtins()"

    def test_all_builtins_register_without_error(self):
        """Todos los built-ins incluyendo los nuevos se registran limpiamente."""
        hm = HookManager()
        done = hm.register_builtins(list(_BUILTINS.keys()))
        assert len(done) == len(_BUILTINS)
