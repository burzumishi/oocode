"""Tests de tools git del MCP server (sin LLM, requiere git disponible)."""
import sys
import subprocess
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.oocode_assistant import (
    _tool_git_status,
    _tool_git_diff,
    _tool_git_log,
    _tool_git_branch,
)

pytestmark = pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="git no disponible",
)


@pytest.fixture
def git_repo(tmp_path):
    """Crea un repositorio git temporal con un commit inicial."""
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"],
                   capture_output=True, cwd=str(tmp_path))
    subprocess.run(["git", "config", "user.name", "Test"],
                   capture_output=True, cwd=str(tmp_path))
    (tmp_path / "README.md").write_text("# Test repo\n")
    subprocess.run(["git", "add", "."], capture_output=True, cwd=str(tmp_path))
    subprocess.run(["git", "commit", "-m", "initial"],
                   capture_output=True, cwd=str(tmp_path))
    return tmp_path


class TestGitStatus:
    def test_clean_repo(self, git_repo):
        result = _tool_git_status({"path": str(git_repo)})
        assert "nothing to commit" in result or "limpio" in result or "clean" in result.lower() or "working tree clean" in result

    def test_with_untracked(self, git_repo):
        (git_repo / "new_file.py").write_text("print('hello')\n")
        result = _tool_git_status({"path": str(git_repo)})
        assert "new_file.py" in result or "untracked" in result.lower() or "sin seguimiento" in result.lower()


class TestGitLog:
    def test_returns_commits(self, git_repo):
        result = _tool_git_log({"path": str(git_repo)})
        assert "initial" in result

    def test_with_limit(self, git_repo):
        result = _tool_git_log({"path": str(git_repo), "n": 1})
        assert isinstance(result, str)
        assert len(result) > 0


class TestGitBranch:
    def test_shows_branch(self, git_repo):
        result = _tool_git_branch({"path": str(git_repo)})
        assert "main" in result or "master" in result


class TestGitDiff:
    def test_no_changes(self, git_repo):
        result = _tool_git_diff({"path": str(git_repo)})
        # Empty diff on clean repo
        assert isinstance(result, str)

    def test_with_changes(self, git_repo):
        (git_repo / "README.md").write_text("# Modified\n")
        result = _tool_git_diff({"path": str(git_repo)})
        assert "README" in result or "Modified" in result or "@@" in result
