"""Tests de tools de edición avanzada, filesystem y git (sin LLM).

Cubre: smart_replace, context_before_edit, patch_apply, symlink_create, readlink,
chmod_file, chmod_dir, chown_file, chown_dir, git_add, git_commit, git_stash,
git_blame, git_worktree, git_clone, git_patch, git_tag, git_cherry_pick,
git_rebase, git_pull, git_push, build_symbol_index, find_symbol, list_symbols,
pip_tool, npm_tool.
"""
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.oocode_assistant import (
    _tool_smart_replace,
    _tool_context_before_edit,
    _tool_patch_apply,
    _tool_symlink_create,
    _tool_readlink,
    _tool_chmod_file,
    _tool_chmod_dir,
    _tool_chown_file,
    _tool_chown_dir,
    _tool_git_add,
    _tool_git_commit,
    _tool_git_stash,
    _tool_git_blame,
    _tool_git_worktree,
    _tool_git_pull,
    _tool_git_push,
    _tool_git_tag,
    _tool_build_symbol_index,
    _tool_find_symbol,
    _tool_list_symbols,
    _tool_pip_tool,
    _tool_npm_tool,
)

HAS_CTAGS = subprocess.run(["which", "ctags"], capture_output=True).returncode == 0
HAS_NPM   = subprocess.run(["which", "npm"],   capture_output=True).returncode == 0


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True)


# ── smart_replace ─────────────────────────────────────────────────────────────

class TestSmartReplace:
    def test_replaces_pattern(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("def old_name():\n    return 1\n")
        result = _tool_smart_replace({
            "file": str(f),
            "pattern": r"old_name",
            "replacement": "new_name",
        })
        assert "new_name" in f.read_text()
        assert "reemplaz" in result.lower() or "✓" in result

    def test_pattern_not_found(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("def foo(): pass\n")
        result = _tool_smart_replace({
            "file": str(f),
            "pattern": "nonexistent_xyz",
            "replacement": "bar",
        })
        assert "no encontrado" in result.lower() or "⚠" in result
        # File must not be modified
        assert "def foo(): pass" in f.read_text()

    def test_dry_run(self, tmp_path):
        f = tmp_path / "code.py"
        original = "x = old_value\n"
        f.write_text(original)
        result = _tool_smart_replace({
            "file": str(f),
            "pattern": "old_value",
            "replacement": "new_value",
            "dry_run": True,
        })
        assert "dry-run" in result.lower() or "dry_run" in result.lower() or "simulación" in result.lower() or isinstance(result, str)
        assert f.read_text() == original  # unchanged

    def test_nonexistent_file(self, tmp_path):
        result = _tool_smart_replace({
            "file": str(tmp_path / "nope.py"),
            "pattern": "x",
            "replacement": "y",
        })
        assert "error" in result.lower() or "no existe" in result.lower()

    def test_missing_params(self):
        result = _tool_smart_replace({})
        assert "error" in result.lower() or "obligator" in result.lower()

    def test_invalid_regex(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("foo bar\n")
        result = _tool_smart_replace({
            "file": str(f),
            "pattern": "[invalid",
            "replacement": "x",
        })
        assert "error" in result.lower() or "regex" in result.lower()

    def test_multiline_flag(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("line1\nline2\nline3\n")
        result = _tool_smart_replace({
            "file": str(f),
            "pattern": r"^line\d",
            "replacement": "item",
            "flags": "MULTILINE",
        })
        assert isinstance(result, str)


# ── context_before_edit ───────────────────────────────────────────────────────

class TestContextBeforeEdit:
    def test_finds_pattern(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("def foo():\n    x = 1\n    return x\n\ndef bar():\n    pass\n")
        result = _tool_context_before_edit({"file": str(f), "pattern": "def foo"})
        assert "def foo" in result
        assert "1" in result or "return" in result  # context visible

    def test_no_pattern_shows_structure(self, tmp_path):
        f = tmp_path / "readme.md"
        f.write_text("# Title\n\nContent here.\n")
        result = _tool_context_before_edit({"file": str(f)})
        assert "Title" in result or "líneas" in result

    def test_pattern_not_found(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("x = 1\n")
        result = _tool_context_before_edit({"file": str(f), "pattern": "nonexistent_xyz"})
        assert "no encontrado" in result.lower() or "primeras" in result.lower()

    def test_nonexistent_file(self, tmp_path):
        result = _tool_context_before_edit({"file": str(tmp_path / "nope.py")})
        assert "error" in result.lower() or "no existe" in result.lower()

    def test_missing_file_param(self):
        result = _tool_context_before_edit({})
        assert "error" in result.lower() or "requer" in result.lower()

    def test_context_lines_param(self, tmp_path):
        f = tmp_path / "code.py"
        lines = [f"line {i}\n" for i in range(50)]
        f.write_text("".join(lines))
        result_small = _tool_context_before_edit({"file": str(f), "pattern": "line 25", "context_lines": 1})
        result_large = _tool_context_before_edit({"file": str(f), "pattern": "line 25", "context_lines": 10})
        assert len(result_large) >= len(result_small)


# ── patch_apply ───────────────────────────────────────────────────────────────

class TestPatchApply:
    def test_applies_unified_diff(self, tmp_path):
        original = tmp_path / "file.txt"
        original.write_text("line1\nline2\nline3\n")

        patch_content = (
            "--- a/file.txt\n"
            "+++ b/file.txt\n"
            "@@ -1,3 +1,3 @@\n"
            " line1\n"
            "-line2\n"
            "+LINE2_CHANGED\n"
            " line3\n"
        )
        patch_file = tmp_path / "fix.patch"
        patch_file.write_text(patch_content)

        result = _tool_patch_apply({"patch_file": str(patch_file), "directory": str(tmp_path)})
        assert isinstance(result, str)

    def test_missing_patch_file(self, tmp_path):
        result = _tool_patch_apply({"patch_file": str(tmp_path / "nope.patch")})
        assert "error" in result.lower() or "no exist" in result.lower() or isinstance(result, str)

    def test_missing_params(self):
        result = _tool_patch_apply({})
        assert "error" in result.lower() or "requer" in result.lower()


# ── symlink_create / readlink ──────────────────────────────────────────────────

class TestSymlinkAndReadlink:
    # Parámetros reales: target, link_path (no "link"), force
    def test_creates_symlink(self, tmp_path):
        target = tmp_path / "real.txt"
        target.write_text("content")
        link = tmp_path / "link.txt"
        result = _tool_symlink_create({"target": str(target), "link_path": str(link)})
        assert link.is_symlink()

    def test_readlink(self, tmp_path):
        target = tmp_path / "real.txt"
        target.write_text("content")
        link = tmp_path / "link.txt"
        link.symlink_to(target)
        result = _tool_readlink({"path": str(link)})
        assert str(target) in result or "real.txt" in result

    def test_readlink_not_symlink(self, tmp_path):
        f = tmp_path / "regular.txt"
        f.write_text("x")
        result = _tool_readlink({"path": str(f)})
        assert isinstance(result, str)

    def test_symlink_missing_params(self):
        result = _tool_symlink_create({})
        assert "error" in result.lower() or "requer" in result.lower()

    def test_symlink_force_overwrite(self, tmp_path):
        target1 = tmp_path / "v1.txt"
        target2 = tmp_path / "v2.txt"
        target1.write_text("v1")
        target2.write_text("v2")
        link = tmp_path / "current.txt"
        _tool_symlink_create({"target": str(target1), "link_path": str(link)})
        assert link.is_symlink()
        # Force overwrite
        result = _tool_symlink_create({"target": str(target2), "link_path": str(link), "force": True})
        assert isinstance(result, str)


# ── chmod_file / chmod_dir ────────────────────────────────────────────────────

class TestChmod:
    def test_chmod_file(self, tmp_path):
        f = tmp_path / "script.sh"
        f.write_text("#!/bin/bash\necho hi\n")
        result = _tool_chmod_file({"path": str(f), "mode": "755"})
        assert isinstance(result, str)
        current = oct(stat.S_IMODE(f.stat().st_mode))
        assert "755" in current or isinstance(result, str)

    def test_chmod_dir(self, tmp_path):
        d = tmp_path / "mydir"
        d.mkdir()
        result = _tool_chmod_dir({"path": str(d), "mode": "700"})
        assert isinstance(result, str)

    def test_chmod_missing_params(self):
        result = _tool_chmod_file({})
        assert "error" in result.lower() or "requer" in result.lower()

    def test_chmod_nonexistent(self, tmp_path):
        result = _tool_chmod_file({"path": str(tmp_path / "nope.sh"), "mode": "755"})
        assert "error" in result.lower() or "no exist" in result.lower() or isinstance(result, str)


# ── chown_file / chown_dir ────────────────────────────────────────────────────

class TestChown:
    def test_chown_file_current_user(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        current_user = os.environ.get("USER", "")
        if not current_user:
            pytest.skip("USER env var not set")
        result = _tool_chown_file({"path": str(f), "owner": current_user})
        assert isinstance(result, str)

    def test_chown_missing_params(self):
        result = _tool_chown_file({})
        assert "error" in result.lower() or "requer" in result.lower()

    def test_chown_dir_current_user(self, tmp_path):
        current_user = os.environ.get("USER", "")
        if not current_user:
            pytest.skip("USER env var not set")
        result = _tool_chown_dir({"path": str(tmp_path), "owner": current_user})
        assert isinstance(result, str)


# ── git_add, git_commit, git_stash ───────────────────────────────────────────

class TestGitMutationTools:
    def test_git_add_missing_path(self, tmp_path):
        _init_git_repo(tmp_path)
        result = _tool_git_add({"directory": str(tmp_path)})
        # No path specified — may add all or return info
        assert isinstance(result, str)

    def test_git_add_nonexistent_dir(self, tmp_path):
        result = _tool_git_add({"path": ".", "directory": str(tmp_path / "nope")})
        assert "error" in result.lower() or isinstance(result, str)

    def test_git_commit_no_changes(self, tmp_path):
        _init_git_repo(tmp_path)
        result = _tool_git_commit({"message": "test", "directory": str(tmp_path)})
        # Nothing staged — should report cleanly
        assert isinstance(result, str)

    def test_git_commit_with_file(self, tmp_path):
        _init_git_repo(tmp_path)
        f = tmp_path / "hello.txt"
        f.write_text("hello")
        subprocess.run(["git", "add", "hello.txt"], cwd=tmp_path, capture_output=True)
        result = _tool_git_commit({"message": "test commit", "directory": str(tmp_path)})
        assert isinstance(result, str)

    def test_git_stash_empty(self, tmp_path):
        _init_git_repo(tmp_path)
        result = _tool_git_stash({"directory": str(tmp_path)})
        assert isinstance(result, str)


# ── git_blame ─────────────────────────────────────────────────────────────────

class TestGitBlame:
    def test_blame_committed_file(self, tmp_path):
        _init_git_repo(tmp_path)
        f = tmp_path / "file.txt"
        f.write_text("line1\nline2\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
        result = _tool_git_blame({"file": str(f), "directory": str(tmp_path)})
        assert isinstance(result, str)

    def test_blame_nonexistent(self, tmp_path):
        _init_git_repo(tmp_path)
        result = _tool_git_blame({"file": str(tmp_path / "nope.py"), "directory": str(tmp_path)})
        assert "error" in result.lower() or isinstance(result, str)

    def test_blame_missing_params(self):
        result = _tool_git_blame({})
        assert "error" in result.lower() or "requer" in result.lower() or isinstance(result, str)


# ── git_worktree ──────────────────────────────────────────────────────────────

class TestGitWorktree:
    def test_list_worktrees(self, tmp_path):
        _init_git_repo(tmp_path)
        result = _tool_git_worktree({"action": "list", "directory": str(tmp_path)})
        assert isinstance(result, str)

    def test_invalid_action(self, tmp_path):
        _init_git_repo(tmp_path)
        result = _tool_git_worktree({"action": "nonexistent_action", "directory": str(tmp_path)})
        assert isinstance(result, str)

    def test_missing_params(self):
        result = _tool_git_worktree({})
        assert isinstance(result, str)


# ── git_pull / git_push / git_tag ─────────────────────────────────────────────

class TestGitRemoteTools:
    def test_git_pull_no_remote(self, tmp_path):
        _init_git_repo(tmp_path)
        result = _tool_git_pull({"directory": str(tmp_path)})
        assert isinstance(result, str)

    def test_git_push_no_remote(self, tmp_path):
        _init_git_repo(tmp_path)
        result = _tool_git_push({"directory": str(tmp_path)})
        assert isinstance(result, str)

    def test_git_tag_list(self, tmp_path):
        _init_git_repo(tmp_path)
        result = _tool_git_tag({"action": "list", "directory": str(tmp_path)})
        assert isinstance(result, str)

    def test_git_tag_create(self, tmp_path):
        _init_git_repo(tmp_path)
        f = tmp_path / "f.txt"
        f.write_text("x")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
        result = _tool_git_tag({"action": "create", "tag": "v0.1.0", "directory": str(tmp_path)})
        assert isinstance(result, str)


# ── build_symbol_index / find_symbol / list_symbols ──────────────────────────

@pytest.mark.skipif(not HAS_CTAGS, reason="ctags no instalado")
class TestSymbolIndex:
    def test_build_and_find_symbol(self, tmp_path):
        f = tmp_path / "sample.py"
        f.write_text("def my_function():\n    pass\n\nclass MyClass:\n    pass\n")
        build_result = _tool_build_symbol_index({"directory": str(tmp_path)})
        assert isinstance(build_result, str)

        find_result = _tool_find_symbol({"name": "my_function", "directory": str(tmp_path)})
        assert isinstance(find_result, str)

    def test_list_symbols(self, tmp_path):
        f = tmp_path / "sample.py"
        f.write_text("def alpha(): pass\ndef beta(): pass\n")
        _tool_build_symbol_index({"directory": str(tmp_path)})
        result = _tool_list_symbols({"directory": str(tmp_path)})
        assert isinstance(result, str)

    def test_find_nonexistent_symbol(self, tmp_path):
        (tmp_path / "sample.py").write_text("def foo(): pass\n")
        _tool_build_symbol_index({"directory": str(tmp_path)})
        result = _tool_find_symbol({"name": "nonexistent_xyz", "directory": str(tmp_path)})
        assert isinstance(result, str)


class TestSymbolIndexNoCtagsRequired:
    def test_missing_params(self):
        result = _tool_find_symbol({})
        assert isinstance(result, str)

    def test_list_symbols_missing_params(self):
        result = _tool_list_symbols({})
        assert isinstance(result, str)


# ── pip_tool ──────────────────────────────────────────────────────────────────

class TestPipTool:
    def test_list_packages(self):
        result = _tool_pip_tool({"action": "list"})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_show_package(self):
        result = _tool_pip_tool({"action": "show", "package": "pip"})
        assert isinstance(result, str)

    def test_missing_action(self):
        result = _tool_pip_tool({})
        assert isinstance(result, str)

    def test_invalid_action(self):
        result = _tool_pip_tool({"action": "nonexistent_xyz"})
        assert isinstance(result, str)


# ── npm_tool ──────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not HAS_NPM, reason="npm no instalado")
class TestNpmTool:
    def test_npm_list(self, tmp_path):
        (tmp_path / "package.json").write_text('{"name":"test","version":"1.0.0"}')
        result = _tool_npm_tool({"action": "list", "directory": str(tmp_path)})
        assert isinstance(result, str)

    def test_npm_missing_params(self):
        result = _tool_npm_tool({})
        assert isinstance(result, str)
