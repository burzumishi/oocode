"""Tests de tools de filesystem del MCP server oocode_assistant (sin LLM).

Nota: _safe_path() solo acepta rutas dentro de home o cwd.
Las fixtures usan ~/.oocode/_test_tmp/ para evitar el bloqueo.
"""
import sys
import pytest
import stat
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.oocode_assistant import (
    _tool_ls_file,
    _tool_ls_dir,
    _tool_find_file,
    _tool_find_dir,
    _tool_grep_file,
    _tool_mkdir_dir,
    _tool_touch_file,
    _tool_mv_file,
    _tool_cp_file,
    _tool_rm_file,
    _tool_rm_dir,
    _tool_file_stat,
    _tool_tree,
    _tool_readlink,
    _tool_symlink_create,
    _tool_chmod_file,
)


class TestLsFile:
    def test_existing_file(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("print('hello')\n")
        result = _tool_ls_file({"path": str(f)})
        assert "test.py" in result

    def test_nonexistent(self, tmp_path):
        result = _tool_ls_file({"path": str(tmp_path / "nonexistent.py")})
        assert "Error" in result or "no existe" in result


class TestLsDir:
    def test_existing_dir(self, tmp_path):
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.txt").write_text("")
        result = _tool_ls_dir({"path": str(tmp_path)})
        assert "a.py" in result or "b.txt" in result

    def test_empty_dir(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        result = _tool_ls_dir({"path": str(empty)})
        assert isinstance(result, str)  # no error fatal


class TestFindFile:
    def test_find_by_pattern(self, tmp_path):
        (tmp_path / "hello.py").write_text("")
        (tmp_path / "bar.txt").write_text("")
        # _tool_find_file usa "path" y "pattern"
        result = _tool_find_file({"path": str(tmp_path), "pattern": "*.py"})
        assert "hello.py" in result
        assert "bar.txt" not in result

    def test_no_match(self, tmp_path):
        (tmp_path / "keep_dir").mkdir()  # Ensure dir exists and is non-empty
        result = _tool_find_file({"path": str(tmp_path), "pattern": "*.xyz_nonexistent_q7q7q7"})
        # Either returns 0 results message, empty, or shows "0 encontrados"
        assert isinstance(result, str)
        assert "hello.py" not in result  # nothing leaked in


class TestFindDir:
    def test_find_subdir(self, tmp_path):
        sub = tmp_path / "mysubdir"
        sub.mkdir()
        result = _tool_find_dir({"path": str(tmp_path), "pattern": "mysubdir"})
        assert "mysubdir" in result


class TestGrepFile:
    def test_finds_pattern(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("def foo():\n    return 42\ndef bar():\n    return 0\n")
        result = _tool_grep_file({"path": str(f), "pattern": "def foo"})
        assert "def foo" in result

    def test_no_match(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("hello world\n")
        result = _tool_grep_file({"path": str(f), "pattern": "nonexistent_xyz_q7q7q7"})
        # Returns a message like "Sin coincidencias para '...' en code.py" or "0 found"
        assert isinstance(result, str)
        assert "hello world" not in result  # the content line shouldn't appear


class TestMkdirDir:
    def test_creates_directory(self, tmp_path):
        new_dir = tmp_path / "new_subdir"
        result = _tool_mkdir_dir({"path": str(new_dir)})
        assert new_dir.exists()
        assert new_dir.is_dir()

    def test_creates_nested(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        result = _tool_mkdir_dir({"path": str(nested)})
        assert nested.exists()  # mkdir_dir hace parents=True por defecto


class TestTouchFile:
    def test_creates_file(self, tmp_path):
        f = tmp_path / "newfile.txt"
        result = _tool_touch_file({"path": str(f)})
        assert f.exists()

    def test_updates_existing(self, tmp_path):
        f = tmp_path / "existing.txt"
        f.write_text("content")
        import time
        time.sleep(0.01)
        result = _tool_touch_file({"path": str(f)})
        assert f.exists()
        assert "content" in f.read_text()


class TestMvFile:
    def test_renames_file(self, tmp_path):
        src = tmp_path / "old.txt"
        dst = tmp_path / "new.txt"
        src.write_text("content")
        result = _tool_mv_file({"src": str(src), "dst": str(dst)})
        assert not src.exists()
        assert dst.exists()
        assert dst.read_text() == "content"


class TestCpFile:
    def test_copies_file(self, tmp_path):
        src = tmp_path / "orig.txt"
        dst = tmp_path / "copy.txt"
        src.write_text("hello")
        result = _tool_cp_file({"src": str(src), "dst": str(dst)})
        assert src.exists()
        assert dst.exists()
        assert dst.read_text() == "hello"


class TestRmFile:
    def test_removes_file(self, tmp_path):
        f = tmp_path / "todelete.txt"
        f.write_text("bye")
        result = _tool_rm_file({"path": str(f)})
        assert not f.exists()

    def test_nonexistent(self, tmp_path):
        result = _tool_rm_file({"path": str(tmp_path / "nonexistent.txt")})
        assert "Error" in result or "no existe" in result


class TestRmDir:
    def test_removes_empty_dir(self, tmp_path):
        d = tmp_path / "empty_dir"
        d.mkdir()
        result = _tool_rm_dir({"path": str(d)})
        assert not d.exists()

    def test_removes_dir_recursive(self, tmp_path):
        d = tmp_path / "full_dir"
        d.mkdir()
        (d / "file.txt").write_text("content")
        result = _tool_rm_dir({"path": str(d), "recursive": True})
        assert not d.exists()


class TestFileStat:
    def test_returns_info(self, tmp_path):
        f = tmp_path / "stat_test.py"
        f.write_text("line1\nline2\nline3\n")
        result = _tool_file_stat({"path": str(f)})
        assert "stat_test.py" in result or "3" in result

    def test_includes_line_count(self, tmp_path):
        f = tmp_path / "lines.py"
        f.write_text("\n".join(f"line{i}" for i in range(10)) + "\n")
        result = _tool_file_stat({"path": str(f)})
        assert "10" in result  # 10 líneas

    def test_nonexistent(self, tmp_path):
        result = _tool_file_stat({"path": str(tmp_path / "nonexistent.xyz")})
        assert "Error" in result or "no existe" in result


class TestTree:
    def test_returns_tree(self, tmp_path):
        (tmp_path / "a.py").write_text("")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.py").write_text("")
        result = _tool_tree({"path": str(tmp_path)})
        assert "a.py" in result or "sub" in result


class TestSymlink:
    def test_create_and_readlink(self, tmp_path):
        target = tmp_path / "target.txt"
        target.write_text("hello")
        link = tmp_path / "link.txt"
        # _tool_symlink_create uses "target" and "link_path"
        result = _tool_symlink_create({"target": str(target), "link_path": str(link)})
        assert link.is_symlink()
        rl = _tool_readlink({"path": str(link)})
        assert "target.txt" in rl or str(target) in rl


class TestChmodFile:
    def test_chmod(self, tmp_path):
        f = tmp_path / "script.sh"
        f.write_text("#!/bin/bash\necho hello\n")
        result = _tool_chmod_file({"path": str(f), "mode": "755"})
        fstat = f.stat()
        assert fstat.st_mode & stat.S_IXUSR  # executable por owner
