"""Tests for interface_change_detector hook."""
import textwrap
import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tools.hooks import (
    _BUILTINS,
    _icd_extract_sigs,
    _icd_extract_docs,
    _icd_sig_str,
    _icd_snapshots,
    _icd_get_path,
    _builtin_icd_pre,
    _builtin_icd_post,
    reset_icd_snapshots,
    HookManager,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _py(tmp_path, name: str, content: str):
    p = tmp_path / name
    p.write_text(textwrap.dedent(content))
    return p


# ---------------------------------------------------------------------------
# _icd_sig_str — signature string builder
# ---------------------------------------------------------------------------

class TestIcdSigStr:
    def _parse_args(self, src: str):
        import ast
        fn = ast.parse(src).body[0]
        return fn.args

    def test_no_args(self):
        a = self._parse_args("def f(): pass")
        assert _icd_sig_str(a) == "()"

    def test_positional_args(self):
        a = self._parse_args("def f(a, b): pass")
        assert _icd_sig_str(a) == "(a, b)"

    def test_default_value(self):
        a = self._parse_args("def f(a, b=1): pass")
        assert _icd_sig_str(a) == "(a, b=1)"

    def test_annotation(self):
        a = self._parse_args("def f(a: int, b: str): pass")
        assert "int" in _icd_sig_str(a)
        assert "str" in _icd_sig_str(a)

    def test_star_args(self):
        a = self._parse_args("def f(*args): pass")
        assert "*args" in _icd_sig_str(a)

    def test_kwargs(self):
        a = self._parse_args("def f(**kwargs): pass")
        assert "**kwargs" in _icd_sig_str(a)

    def test_kwonly(self):
        a = self._parse_args("def f(*, key=True): pass")
        sig = _icd_sig_str(a)
        assert "key=True" in sig

    def test_full_signature(self):
        a = self._parse_args("def f(a, b=2, *args, key=True, **kw): pass")
        sig = _icd_sig_str(a)
        assert "a" in sig
        assert "b=2" in sig
        assert "*args" in sig
        assert "key=True" in sig
        assert "**kw" in sig


# ---------------------------------------------------------------------------
# _icd_extract_sigs — AST signature extraction
# ---------------------------------------------------------------------------

class TestIcdExtractSigs:
    def test_top_level_function(self):
        code = "def greet(name): pass"
        sigs = _icd_extract_sigs(code)
        assert "greet" in sigs
        assert "name" in sigs["greet"]

    def test_class_method(self):
        code = "class Foo:\n    def bar(self, x): pass"
        sigs = _icd_extract_sigs(code)
        assert "Foo.bar" in sigs
        assert "x" in sigs["Foo.bar"]

    def test_no_top_level_for_nested(self):
        # Nested function inside another function — NOT indexed (not an interface)
        code = "def outer():\n    def inner(): pass"
        sigs = _icd_extract_sigs(code)
        assert "outer" in sigs
        assert "inner" not in sigs

    def test_syntax_error_returns_empty(self):
        sigs = _icd_extract_sigs("def broken(:")
        assert sigs == {}

    def test_async_function(self):
        code = "async def fetch(url: str) -> None: pass"
        sigs = _icd_extract_sigs(code)
        assert "fetch" in sigs
        assert "url" in sigs["fetch"]

    def test_multiple_classes(self):
        code = "class A:\n    def m(self): pass\nclass B:\n    def n(self, x): pass"
        sigs = _icd_extract_sigs(code)
        assert "A.m" in sigs
        assert "B.n" in sigs

    def test_unchanged_sig_same_text(self):
        code = "def f(a, b): pass"
        assert _icd_extract_sigs(code) == _icd_extract_sigs(code)


# ---------------------------------------------------------------------------
# _icd_get_path
# ---------------------------------------------------------------------------

class TestIcdGetPath:
    def test_path_key(self, tmp_path):
        p = tmp_path / "foo.py"
        p.write_text("")
        result = _icd_get_path("edit_file", {"path": str(p)})
        assert len(result) == 1

    def test_file_path_key(self, tmp_path):
        p = tmp_path / "foo.py"
        p.write_text("")
        result = _icd_get_path("write_file", {"file_path": str(p)})
        assert len(result) == 1

    def test_empty_returns_empty(self):
        assert _icd_get_path("edit_file", {}) == []


# ---------------------------------------------------------------------------
# Pre-hook: captures snapshot
# ---------------------------------------------------------------------------

class TestIcdPre:
    def setup_method(self):
        reset_icd_snapshots()

    def test_captures_py_file(self, tmp_path):
        p = _py(tmp_path, "sample.py", "def f(a): pass\n")
        returned = _builtin_icd_pre("edit_file", {"path": str(p)})
        assert returned == {"path": str(p)}  # always returns args
        assert str(p.resolve()) in _icd_snapshots

    def test_captures_content(self, tmp_path):
        p = _py(tmp_path, "sample.py", "def f(a, b): pass\n")
        _builtin_icd_pre("write_file", {"path": str(p)})
        key = str(p.resolve())
        assert "def f" in _icd_snapshots[key]

    def test_ignores_non_py(self, tmp_path):
        p = tmp_path / "script.sh"
        p.write_text("echo hello")
        _builtin_icd_pre("write_file", {"path": str(p)})
        assert str(p.resolve()) not in _icd_snapshots

    def test_non_write_tool_skips(self, tmp_path):
        p = _py(tmp_path, "sample.py", "def f(): pass\n")
        _builtin_icd_pre("read_file", {"path": str(p)})
        assert str(p.resolve()) not in _icd_snapshots

    def test_does_not_overwrite_existing_snapshot(self, tmp_path):
        p = _py(tmp_path, "sample.py", "def f(a): pass\n")
        key = str(p.resolve())
        _icd_snapshots[key] = "ORIGINAL CONTENT"
        _builtin_icd_pre("edit_file", {"path": str(p)})
        assert _icd_snapshots[key] == "ORIGINAL CONTENT"

    def test_always_returns_args(self, tmp_path):
        """Pre-hook MUST return args (not None) or the tool gets blocked."""
        p = _py(tmp_path, "sample.py", "def f(): pass\n")
        result = _builtin_icd_pre("edit_file", {"path": str(p), "extra": "x"})
        assert result is not None
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Post-hook: detects signature changes
# ---------------------------------------------------------------------------

class TestIcdPost:
    def setup_method(self):
        reset_icd_snapshots()

    def test_detects_added_parameter(self, tmp_path):
        p = _py(tmp_path, "sample.py", "def greet(name): pass\n")
        key = str(p.resolve())
        _icd_snapshots[key] = "def greet(name): pass\n"
        # Now "after" has a new param
        p.write_text("def greet(name, loud=False): pass\n")
        result = _builtin_icd_post("edit_file", {"path": str(p)}, "ok")
        assert result is not None
        assert "greet" in result
        assert "loud" in result

    def test_detects_removed_parameter(self, tmp_path):
        p = _py(tmp_path, "sample.py", "def f(a, b): pass\n")
        key = str(p.resolve())
        _icd_snapshots[key] = "def f(a, b): pass\n"
        p.write_text("def f(a): pass\n")
        result = _builtin_icd_post("edit_file", {"path": str(p)}, "ok")
        assert result is not None
        assert "f" in result

    def test_no_change_returns_none(self, tmp_path):
        p = _py(tmp_path, "sample.py", "def f(a): pass\n")
        key = str(p.resolve())
        _icd_snapshots[key] = "def f(a): pass\n"
        p.write_text("def f(a): pass\n")  # same
        result = _builtin_icd_post("edit_file", {"path": str(p)}, "ok")
        assert result is None

    def test_body_change_no_sig_change_returns_none(self, tmp_path):
        p = _py(tmp_path, "sample.py", "def f(a):\n    return a\n")
        key = str(p.resolve())
        _icd_snapshots[key] = "def f(a):\n    return a\n"
        p.write_text("def f(a):\n    return a * 2\n")
        result = _builtin_icd_post("edit_file", {"path": str(p)}, "ok")
        assert result is None

    def test_error_result_skipped(self, tmp_path):
        p = _py(tmp_path, "sample.py", "def f(a): pass\n")
        key = str(p.resolve())
        _icd_snapshots[key] = "def f(a): pass\n"
        p.write_text("def f(a, b): pass\n")
        result = _builtin_icd_post("edit_file", {"path": str(p)}, "Error: something failed")
        assert result is None

    def test_no_snapshot_returns_none(self, tmp_path):
        p = _py(tmp_path, "sample.py", "def f(a, b): pass\n")
        result = _builtin_icd_post("edit_file", {"path": str(p)}, "ok")
        assert result is None

    def test_non_write_tool_returns_none(self, tmp_path):
        p = _py(tmp_path, "sample.py", "def f(): pass\n")
        key = str(p.resolve())
        _icd_snapshots[key] = "def f(a): pass\n"
        result = _builtin_icd_post("read_file", {"path": str(p)}, "ok")
        assert result is None

    def test_class_method_sig_change(self, tmp_path):
        p = _py(tmp_path, "sample.py",
                "class Agent:\n    def run(self, msg):\n        pass\n")
        key = str(p.resolve())
        _icd_snapshots[key] = "class Agent:\n    def run(self, msg):\n        pass\n"
        p.write_text("class Agent:\n    def run(self, msg, stream=False):\n        pass\n")
        result = _builtin_icd_post("edit_file", {"path": str(p)}, "ok")
        assert result is not None
        assert "Agent.run" in result
        assert "stream" in result

    def test_shows_before_and_after(self, tmp_path):
        p = _py(tmp_path, "sample.py", "def f(a): pass\n")
        key = str(p.resolve())
        _icd_snapshots[key] = "def f(a): pass\n"
        p.write_text("def f(a, b): pass\n")
        result = _builtin_icd_post("edit_file", {"path": str(p)}, "ok")
        assert "Antes:" in result
        assert "Ahora:" in result

    def test_multiple_functions_changed(self, tmp_path):
        before = "def alpha(x): pass\ndef beta(y): pass\n"
        after  = "def alpha(x, z): pass\ndef beta(y, w): pass\n"
        p = _py(tmp_path, "sample.py", before)
        p.write_text(after)
        key = str(p.resolve())
        _icd_snapshots[key] = before
        result = _builtin_icd_post("edit_file", {"path": str(p)}, "ok")
        assert result is not None
        assert "alpha" in result
        assert "beta" in result


# ---------------------------------------------------------------------------
# Registration in _BUILTINS
# ---------------------------------------------------------------------------

class TestIcdRegistration:
    def test_in_builtins(self):
        assert "interface_change_detector" in _BUILTINS

    def test_is_pre_post_pair(self):
        hook_type, _, _ = _BUILTINS["interface_change_detector"]
        assert hook_type == "pre+post"

    def test_tuple_of_callables(self):
        _, _, fns = _BUILTINS["interface_change_detector"]
        assert isinstance(fns, tuple) and len(fns) == 2
        pre_fn, post_fn = fns
        assert callable(pre_fn) and callable(post_fn)

    def test_total_builtins_now_15(self):
        assert len(_BUILTINS) == 19

    def test_not_active_by_default(self):
        from config import DEFAULT_CONFIG
        active = DEFAULT_CONFIG.get("hooks", {}).get("builtins", [])
        assert "interface_change_detector" not in active

    def test_register_activates_both(self):
        hm = HookManager()
        hm.register_builtins(["interface_change_detector"])
        pre_names  = {fn.__name__ for _, fn in hm._pre}
        post_names = {fn.__name__ for _, fn in hm._post}
        assert "_builtin_icd_pre"  in pre_names
        assert "_builtin_icd_post" in post_names

    def test_unregister_removes_both(self):
        hm = HookManager()
        hm.register_builtins(["interface_change_detector"])
        hm.unregister_builtin("interface_change_detector")
        pre_names  = {fn.__name__ for _, fn in hm._pre}
        post_names = {fn.__name__ for _, fn in hm._post}
        assert "_builtin_icd_pre"  not in pre_names
        assert "_builtin_icd_post" not in post_names


# ---------------------------------------------------------------------------
# _icd_extract_docs
# ---------------------------------------------------------------------------

class TestIcdExtractDocs:
    def test_function_docstring(self):
        code = 'def greet(name):\n    """Saluda al usuario."""\n    pass'
        docs = _icd_extract_docs(code)
        assert docs.get("greet") == "Saluda al usuario."

    def test_no_docstring_empty_string(self):
        code = "def greet(): pass"
        docs = _icd_extract_docs(code)
        assert docs.get("greet") == ""

    def test_class_docstring(self):
        code = 'class Agent:\n    """Motor del agente."""\n    pass'
        docs = _icd_extract_docs(code)
        assert docs.get("Agent") == "Motor del agente."

    def test_method_docstring(self):
        code = 'class A:\n    def run(self):\n        """Ejecuta el loop."""\n        pass'
        docs = _icd_extract_docs(code)
        assert docs.get("A.run") == "Ejecuta el loop."

    def test_multiline_returns_first_nonempty(self):
        code = 'def f():\n    """\n    Primera línea.\n    Segunda.\n    """\n    pass'
        docs = _icd_extract_docs(code)
        assert docs.get("f") == "Primera línea."

    def test_truncates_at_120(self):
        long = "X" * 200
        code = f'def f():\n    """{long}"""\n    pass'
        docs = _icd_extract_docs(code)
        assert len(docs.get("f", "")) == 120

    def test_syntax_error_returns_empty(self):
        docs = _icd_extract_docs("def broken(:")
        assert docs == {}


# ---------------------------------------------------------------------------
# Docstring monitor in post-hook
# ---------------------------------------------------------------------------

class TestDocstringMonitor:
    def setup_method(self):
        reset_icd_snapshots()

    def test_stale_docstring_warning_when_sig_changed(self, tmp_path):
        before = 'def process(data):\n    """Procesa los datos."""\n    pass\n'
        after  = 'def process(data, strict=False):\n    """Procesa los datos."""\n    pass\n'
        p = _py(tmp_path, "core.py", before)
        p.write_text(after)
        key = str(p.resolve())
        _icd_snapshots[key] = before
        result = _builtin_icd_post("edit_file", {"path": str(p)}, "ok")
        assert result is not None
        assert "Docstring posiblemente desactualizado" in result
        assert "Procesa los datos." in result

    def test_no_stale_warning_when_doc_also_updated(self, tmp_path):
        before = 'def process(data):\n    """Procesa los datos."""\n    pass\n'
        after  = 'def process(data, strict=False):\n    """Procesa los datos con modo strict."""\n    pass\n'
        p = _py(tmp_path, "core.py", before)
        p.write_text(after)
        key = str(p.resolve())
        _icd_snapshots[key] = before
        result = _builtin_icd_post("edit_file", {"path": str(p)}, "ok")
        assert result is not None
        assert "Docstring posiblemente desactualizado" not in result
        assert "Docstring actualizado" in result

    def test_no_stale_warning_when_no_docstring(self, tmp_path):
        before = "def process(data):\n    pass\n"
        after  = "def process(data, strict=False):\n    pass\n"
        p = _py(tmp_path, "core.py", before)
        p.write_text(after)
        key = str(p.resolve())
        _icd_snapshots[key] = before
        result = _builtin_icd_post("edit_file", {"path": str(p)}, "ok")
        # Sig change still reported, but no docstring warning
        assert result is not None
        assert "Docstring" not in result

    def test_doc_only_change_reported(self, tmp_path):
        before = 'def f(a):\n    """Versión antigua."""\n    return a\n'
        after  = 'def f(a):\n    """Versión mejorada con más detalles."""\n    return a\n'
        p = _py(tmp_path, "core.py", before)
        p.write_text(after)
        key = str(p.resolve())
        _icd_snapshots[key] = before
        result = _builtin_icd_post("edit_file", {"path": str(p)}, "ok")
        assert result is not None
        assert "Docstring modificado" in result
        assert "Versión antigua." in result

    def test_doc_only_change_no_false_sig_warning(self, tmp_path):
        before = 'def f(a):\n    """Old doc."""\n    return a\n'
        after  = 'def f(a):\n    """New doc."""\n    return a\n'
        p = _py(tmp_path, "core.py", before)
        p.write_text(after)
        key = str(p.resolve())
        _icd_snapshots[key] = before
        result = _builtin_icd_post("edit_file", {"path": str(p)}, "ok")
        # Should NOT report a signature change
        assert result is not None
        assert "Cambio de interfaz" not in result

    def test_doc_deleted_reported(self, tmp_path):
        before = 'def f(a):\n    """Esta función era importante."""\n    pass\n'
        after  = 'def f(a):\n    pass\n'
        p = _py(tmp_path, "core.py", before)
        p.write_text(after)
        key = str(p.resolve())
        _icd_snapshots[key] = before
        result = _builtin_icd_post("edit_file", {"path": str(p)}, "ok")
        assert result is not None
        assert "Docstring" in result

    def test_no_report_when_nothing_changed(self, tmp_path):
        code = 'def f(a):\n    """Sin cambios."""\n    return a\n'
        p = _py(tmp_path, "core.py", code)
        p.write_text(code)
        key = str(p.resolve())
        _icd_snapshots[key] = code
        result = _builtin_icd_post("edit_file", {"path": str(p)}, "ok")
        assert result is None


# ---------------------------------------------------------------------------
# Deleted symbol detection
# ---------------------------------------------------------------------------

class TestDeletedSymbols:
    def setup_method(self):
        reset_icd_snapshots()

    def test_deleted_function_reported(self, tmp_path):
        before = "def process(data): pass\ndef helper(): pass\n"
        after  = "def helper(): pass\n"
        p = _py(tmp_path, "core.py", before)
        p.write_text(after)
        key = str(p.resolve())
        _icd_snapshots[key] = before
        result = _builtin_icd_post("edit_file", {"path": str(p)}, "ok")
        assert result is not None
        assert "Símbolo eliminado" in result
        assert "process" in result

    def test_deleted_method_reported(self, tmp_path):
        before = "class Engine:\n    def run(self): pass\n    def stop(self): pass\n"
        after  = "class Engine:\n    def run(self): pass\n"
        p = _py(tmp_path, "engine.py", before)
        p.write_text(after)
        key = str(p.resolve())
        _icd_snapshots[key] = before
        result = _builtin_icd_post("edit_file", {"path": str(p)}, "ok")
        assert result is not None
        assert "Símbolo eliminado" in result
        assert "Engine.stop" in result

    def test_private_deletion_ignored(self, tmp_path):
        before = "def _internal(): pass\ndef public(): pass\n"
        after  = "def public(): pass\n"
        p = _py(tmp_path, "mod.py", before)
        p.write_text(after)
        key = str(p.resolve())
        _icd_snapshots[key] = before
        result = _builtin_icd_post("edit_file", {"path": str(p)}, "ok")
        # _internal is private — must not be reported
        assert result is None or "Símbolo eliminado" not in result

    def test_deleted_shows_era_signature(self, tmp_path):
        before = "def fetch(url: str, timeout: int = 10): pass\n"
        after  = "# función eliminada\n"
        p = _py(tmp_path, "api.py", before)
        p.write_text(after)
        key = str(p.resolve())
        _icd_snapshots[key] = before
        result = _builtin_icd_post("edit_file", {"path": str(p)}, "ok")
        assert result is not None
        assert "Era:" in result
        assert "fetch" in result

    def test_all_functions_deleted_all_reported(self, tmp_path):
        before = "def alpha(): pass\ndef beta(): pass\n"
        after  = ""
        p = _py(tmp_path, "mod.py", before)
        p.write_text(after)
        key = str(p.resolve())
        _icd_snapshots[key] = before
        result = _builtin_icd_post("edit_file", {"path": str(p)}, "ok")
        assert result is not None
        assert "alpha" in result
        assert "beta" in result

    def test_no_deletion_no_report(self, tmp_path):
        code = "def process(data): pass\n"
        p = _py(tmp_path, "core.py", code)
        p.write_text(code)
        key = str(p.resolve())
        _icd_snapshots[key] = code
        result = _builtin_icd_post("edit_file", {"path": str(p)}, "ok")
        assert result is None


# ---------------------------------------------------------------------------
# active_builtin_names
# ---------------------------------------------------------------------------

class TestActiveBuiltinNames:
    def test_empty_manager_returns_empty_set(self):
        hm = HookManager()
        assert hm.active_builtin_names() == set()

    def test_registered_builtin_appears(self):
        hm = HookManager()
        hm.register_builtins(["interface_change_detector"])
        assert "interface_change_detector" in hm.active_builtin_names()

    def test_unregistered_builtin_disappears(self):
        hm = HookManager()
        hm.register_builtins(["interface_change_detector"])
        hm.unregister_builtin("interface_change_detector")
        assert "interface_change_detector" not in hm.active_builtin_names()

    def test_default_builtins_active(self):
        from config import DEFAULT_CONFIG
        hm = HookManager()
        hm.register_builtins(DEFAULT_CONFIG.get("hooks", {}).get("builtins", []))
        active = hm.active_builtin_names()
        for name in DEFAULT_CONFIG.get("hooks", {}).get("builtins", []):
            assert name in active


# ---------------------------------------------------------------------------
# reset_icd_snapshots
# ---------------------------------------------------------------------------

class TestResetIcdSnapshots:
    def test_clears_snapshots(self, tmp_path):
        p = _py(tmp_path, "f.py", "def f(): pass\n")
        _icd_snapshots[str(p.resolve())] = "content"
        reset_icd_snapshots()
        assert len(_icd_snapshots) == 0
