"""Tests para el hook test_suite_delta (pre+post).

Cubre:
- registro en _BUILTINS como "pre+post"
- register_builtins añade pre Y post a HookManager
- unregister_builtin elimina ambos
- pre_count y post_count reflejan el par
- no activo por defecto
- _run_suite_capture parsea PASSED/FAILED/ERROR correctamente
- pre-hook captura baseline en primera escritura
- pre-hook silencioso si ya hay baseline
- pre-hook silencioso para herramienta no write
- post-hook reporta regresiones (antes PASSED, ahora FAILED)
- post-hook reporta fixes (antes FAILED, ahora PASSED)
- post-hook reporta tests nuevos que fallan
- post-hook silencioso cuando no hay delta
- post-hook silencioso sin baseline
- post-hook silencioso en resultado de error
- post-hook silencioso para herramienta no write
- list_rows incluye fns del par como builtin
- reset_suite_snapshot limpia el estado
- _find_suite_workdir sube hasta el marcador de proyecto
"""
import sys, os, tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── helpers ───────────────────────────────────────────────────────────────────

def _reset():
    """Limpia el estado global entre tests."""
    import tools.hooks as _h
    _h._suite_snapshot = None
    _h._suite_workdir = ""


# ── registro y estructura ─────────────────────────────────────────────────────

class TestTestSuiteDeltaRegistration:
    def test_in_builtins(self):
        from tools.hooks import _BUILTINS
        assert "test_suite_delta" in _BUILTINS

    def test_is_pre_post_type(self):
        from tools.hooks import _BUILTINS
        hook_type, _, _ = _BUILTINS["test_suite_delta"]
        assert hook_type == "pre+post"

    def test_fn_is_tuple_of_callables(self):
        from tools.hooks import _BUILTINS
        _, _, fn = _BUILTINS["test_suite_delta"]
        assert isinstance(fn, tuple) and len(fn) == 2
        pre_fn, post_fn = fn
        assert callable(pre_fn) and callable(post_fn)

    def test_register_builtins_adds_pre_and_post(self):
        from tools.hooks import HookManager
        hm = HookManager()
        done = hm.register_builtins(["test_suite_delta"])
        assert "test_suite_delta" in done
        assert hm.pre_count == 1
        assert hm.post_count == 1

    def test_unregister_builtin_removes_both(self):
        from tools.hooks import HookManager
        hm = HookManager()
        hm.register_builtins(["test_suite_delta"])
        removed = hm.unregister_builtin("test_suite_delta")
        assert removed is True
        assert hm.pre_count == 0
        assert hm.post_count == 0

    def test_active_by_default(self):
        from config import DEFAULT_CONFIG
        defaults = DEFAULT_CONFIG["hooks"]["builtins"]
        assert "test_suite_delta" in defaults

    def test_list_rows_marks_fns_as_builtin(self):
        from tools.hooks import HookManager
        hm = HookManager()
        hm.register_builtins(["test_suite_delta"])
        rows = hm.list_rows()
        assert any(r[3] for r in rows), "al menos una fn debe estar marcada como builtin"
        builtin_rows = [r for r in rows if r[3]]
        fn_names = [r[2] for r in builtin_rows]
        assert any("delta" in n for n in fn_names)

    def test_total_builtins_count(self):
        from tools.hooks import _BUILTINS
        assert len(_BUILTINS) == 19

    def test_double_register_is_idempotent(self):
        from tools.hooks import HookManager
        hm = HookManager()
        hm.register_builtins(["test_suite_delta"])
        hm.register_builtins(["test_suite_delta"])  # segunda vez
        assert hm.pre_count == 1
        assert hm.post_count == 1


# ── _run_suite_capture ────────────────────────────────────────────────────────

class TestRunSuiteCapture:
    def _mock_popen(self, output: str, returncode: int = 0):
        mock = MagicMock()
        mock.communicate.return_value = (output, None)
        mock.returncode = returncode
        mock.pid = 1234
        return mock

    def test_parses_passed_lines(self):
        from tools.hooks import _run_suite_capture
        output = (
            "tests/test_foo.py::TestFoo::test_bar PASSED\n"
            "tests/test_foo.py::TestFoo::test_baz PASSED\n"
        )
        with patch("subprocess.Popen", return_value=self._mock_popen(output)):
            result = _run_suite_capture("/tmp")
        assert result is not None
        assert "tests/test_foo.py::TestFoo::test_bar" in result
        assert result["tests/test_foo.py::TestFoo::test_bar"] == "PASSED"

    def test_parses_failed_lines(self):
        from tools.hooks import _run_suite_capture
        output = (
            "tests/test_foo.py::TestFoo::test_ok PASSED\n"
            "tests/test_foo.py::TestFoo::test_bad FAILED\n"
        )
        with patch("subprocess.Popen", return_value=self._mock_popen(output, returncode=1)):
            result = _run_suite_capture("/tmp")
        assert result is not None
        assert result["tests/test_foo.py::TestFoo::test_bad"] == "FAILED"
        assert result["tests/test_foo.py::TestFoo::test_ok"] == "PASSED"

    def test_parses_error_lines(self):
        from tools.hooks import _run_suite_capture
        output = "tests/test_foo.py::TestFoo::test_err ERROR\n"
        with patch("subprocess.Popen", return_value=self._mock_popen(output, 1)):
            result = _run_suite_capture("/tmp")
        assert result is not None
        assert result.get("tests/test_foo.py::TestFoo::test_err") == "ERROR"

    def test_returns_none_on_empty_output(self):
        from tools.hooks import _run_suite_capture
        with patch("subprocess.Popen", return_value=self._mock_popen("")):
            result = _run_suite_capture("/tmp")
        assert result is None

    def test_returns_none_on_file_not_found(self):
        from tools.hooks import _run_suite_capture
        with patch("subprocess.Popen", side_effect=FileNotFoundError):
            result = _run_suite_capture("/tmp")
        assert result is None

    def test_ignores_lines_without_double_colon(self):
        from tools.hooks import _run_suite_capture
        output = (
            "not a test id PASSED\n"
            "tests/test_foo.py::TestFoo::test_ok PASSED\n"
        )
        with patch("subprocess.Popen", return_value=self._mock_popen(output)):
            result = _run_suite_capture("/tmp")
        assert result is not None
        assert "not a test id" not in result


# ── pre-hook ──────────────────────────────────────────────────────────────────

class TestTestSuiteDeltaPre:
    def _pre(self, tool: str, args: dict):
        from tools.hooks import _builtin_test_suite_delta_pre
        return _builtin_test_suite_delta_pre(tool, args)

    def _fake_capture(self):
        return {
            "tests/test_foo.py::TestFoo::test_a": "PASSED",
            "tests/test_foo.py::TestFoo::test_b": "PASSED",
        }

    def setup_method(self):
        _reset()

    def test_captures_baseline_on_first_write(self):
        import tools.hooks as _h
        assert _h._suite_snapshot is None
        with patch("tools.hooks._run_suite_capture", return_value=self._fake_capture()), \
             patch("tools.hooks._find_suite_workdir", return_value="/project"), \
             patch("tools.hooks._hprint"):
            result = self._pre("write_file", {"path": "/project/main.py"})
        assert result == {"path": "/project/main.py"}  # args pass-through
        assert _h._suite_snapshot is not None
        assert _h._suite_workdir == "/project"

    def test_silent_if_baseline_already_set(self):
        import tools.hooks as _h
        _h._suite_snapshot = {"tests/t.py::T::t": "PASSED"}
        _h._suite_workdir = "/project"
        called = []
        with patch("tools.hooks._run_suite_capture", side_effect=lambda w: called.append(w)):
            self._pre("edit_file", {"path": "/project/main.py"})
        assert called == []  # no second capture

    def test_silent_for_non_write_tool(self):
        import tools.hooks as _h
        called = []
        with patch("tools.hooks._run_suite_capture", side_effect=lambda w: called.append(w)):
            self._pre("read_file", {"path": "/project/main.py"})
        assert called == []
        assert _h._suite_snapshot is None

    def test_returns_args_unchanged(self):
        args = {"path": "/project/main.py", "content": "x = 1"}
        with patch("tools.hooks._run_suite_capture", return_value=None), \
             patch("tools.hooks._find_suite_workdir", return_value="/project"):
            result = self._pre("write_file", args)
        assert result == args

    def test_handles_missing_path_gracefully(self):
        result = self._pre("write_file", {})
        assert result == {}  # silencioso, no crash


# ── post-hook ─────────────────────────────────────────────────────────────────

class TestTestSuiteDeltaPost:
    def _post(self, tool: str, args: dict, result: str = "ok"):
        from tools.hooks import _builtin_test_suite_delta_post
        return _builtin_test_suite_delta_post(tool, args, result)

    def setup_method(self):
        _reset()

    def _set_baseline(self, snapshot: dict):
        import tools.hooks as _h
        _h._suite_snapshot = snapshot
        _h._suite_workdir = "/project"

    def test_reports_regressions(self):
        self._set_baseline({
            "tests/t.py::T::test_ok": "PASSED",
            "tests/t.py::T::test_stable": "PASSED",
        })
        current = {
            "tests/t.py::T::test_ok": "FAILED",   # regresión
            "tests/t.py::T::test_stable": "PASSED",
        }
        with patch("tools.hooks._run_suite_capture", return_value=current), \
             patch("tools.hooks._hprint"):
            r = self._post("edit_file", {"path": "/project/main.py"})
        assert r is not None
        assert "regresión" in r
        assert "tests/t.py::T::test_ok" in r

    def test_reports_fixes(self):
        self._set_baseline({
            "tests/t.py::T::test_broken": "FAILED",
        })
        current = {
            "tests/t.py::T::test_broken": "PASSED",
        }
        with patch("tools.hooks._run_suite_capture", return_value=current), \
             patch("tools.hooks._hprint"):
            r = self._post("edit_file", {"path": "/project/main.py"})
        assert r is not None
        assert "fix" in r.lower()
        assert "tests/t.py::T::test_broken" in r

    def test_reports_new_failing_tests(self):
        self._set_baseline({
            "tests/t.py::T::test_old": "PASSED",
        })
        current = {
            "tests/t.py::T::test_old": "PASSED",
            "tests/t.py::T::test_new": "FAILED",
        }
        with patch("tools.hooks._run_suite_capture", return_value=current), \
             patch("tools.hooks._hprint"):
            r = self._post("edit_file", {"path": "/project/main.py"})
        assert r is not None
        assert "nuevo" in r.lower() or "test_new" in r

    def test_silent_when_no_delta(self):
        snapshot = {
            "tests/t.py::T::test_a": "PASSED",
            "tests/t.py::T::test_b": "PASSED",
        }
        self._set_baseline(snapshot)
        with patch("tools.hooks._run_suite_capture", return_value=dict(snapshot)), \
             patch("tools.hooks._hprint"):
            r = self._post("edit_file", {"path": "/project/main.py"})
        assert r is None

    def test_silent_without_baseline(self):
        r = self._post("edit_file", {"path": "/project/main.py"})
        assert r is None

    def test_silent_on_error_result(self):
        self._set_baseline({"tests/t.py::T::test_a": "PASSED"})
        r = self._post("edit_file", {"path": "/project/main.py"},
                       result="Error: old_string no encontrada")
        assert r is None

    def test_silent_for_non_write_tool(self):
        self._set_baseline({"tests/t.py::T::test_a": "PASSED"})
        r = self._post("read_file", {"path": "/project/main.py"})
        assert r is None

    def test_silent_when_capture_returns_none(self):
        self._set_baseline({"tests/t.py::T::test_a": "PASSED"})
        with patch("tools.hooks._run_suite_capture", return_value=None):
            r = self._post("edit_file", {"path": "/project/main.py"})
        assert r is None

    def test_appends_to_existing_result(self):
        self._set_baseline({"tests/t.py::T::test_ok": "PASSED"})
        current = {"tests/t.py::T::test_ok": "FAILED"}
        with patch("tools.hooks._run_suite_capture", return_value=current), \
             patch("tools.hooks._hprint"):
            r = self._post("edit_file", {"path": "/project/main.py"}, result="Editado.")
        assert r is not None
        assert r.startswith("Editado.")
        assert "test_suite_delta" in r

    def test_truncates_long_regression_list(self):
        baseline = {f"tests/t.py::T::test_{i}": "PASSED" for i in range(20)}
        self._set_baseline(baseline)
        current = {f"tests/t.py::T::test_{i}": "FAILED" for i in range(20)}
        with patch("tools.hooks._run_suite_capture", return_value=current), \
             patch("tools.hooks._hprint"):
            r = self._post("edit_file", {"path": "/project/main.py"})
        assert r is not None
        assert "más" in r  # indicador de truncado


# ── reset ──────────────────────────────────────────────────────────────────────

class TestResetSuiteSnapshot:
    def test_reset_clears_snapshot(self):
        import tools.hooks as _h
        _h._suite_snapshot = {"tests/t.py::T::test_a": "PASSED"}
        _h._suite_workdir = "/project"
        from tools.hooks import reset_suite_snapshot
        reset_suite_snapshot()
        assert _h._suite_snapshot is None
        assert _h._suite_workdir == ""


# ── _find_suite_workdir ────────────────────────────────────────────────────────

class TestFindSuiteWorkdir:
    def test_finds_pyproject_toml(self):
        from tools.hooks import _find_suite_workdir
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "pyproject.toml").write_text("[tool.pytest]\n")
            src = Path(tmp, "src", "main.py")
            src.parent.mkdir()
            src.write_text("x = 1\n")
            result = _find_suite_workdir(str(src))
            assert result == tmp

    def test_finds_pytest_ini(self):
        from tools.hooks import _find_suite_workdir
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "pytest.ini").write_text("[pytest]\n")
            subdir = Path(tmp, "a", "b")
            subdir.mkdir(parents=True)
            f = subdir / "x.py"
            f.write_text("pass\n")
            result = _find_suite_workdir(str(f))
            assert result == tmp

    def test_falls_back_to_parent(self):
        from tools.hooks import _find_suite_workdir
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp, "main.py")
            f.write_text("x = 1\n")
            result = _find_suite_workdir(str(f))
            assert result == tmp
