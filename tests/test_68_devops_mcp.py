"""Tests del servidor MCP devops_assistant (sin LLM, sin servidor externo).

Cubre: git, docker (mocked), filesystem mutations, build/debug, archive,
prompts, recursos y consistencia de _TOOLS/_TOOL_FNS.
"""
import json
import os
import stat
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.devops_assistant import (
    _TOOL_FNS,
    _TOOLS,
    _PROMPTS,
    _RESOURCES,
    _RESOURCE_FNS,
    _prompt_get,
    _tool_archive_create,
    _tool_archive_extract,
    _tool_archive_list,
    _tool_chmod_file,
    _tool_chown_file,
    _tool_cp_file,
    _tool_git_branch,
    _tool_git_diff,
    _tool_git_log,
    _tool_git_status,
    _tool_make_run,
    _tool_mkdir_dir,
    _tool_mv_file,
    _tool_python_exec,
    _tool_readlink,
    _tool_rm_dir,
    _tool_rm_file,
    _tool_run_script,
    _tool_symlink_create,
    _tool_touch_file,
)

HAS_GIT  = subprocess.run(["git", "--version"], capture_output=True).returncode == 0
HAS_MAKE = subprocess.run(["which", "make"],    capture_output=True).returncode == 0


# ── Fixtures ──────────────────────────────────────────────────────────────────

_TEST_TMP = Path.home() / ".oocode" / "_test_tmp_devops"


@pytest.fixture(autouse=True)
def _cleanup():
    _TEST_TMP.mkdir(parents=True, exist_ok=True)
    yield
    import shutil
    shutil.rmtree(_TEST_TMP, ignore_errors=True)


@pytest.fixture
def tmp_path():
    _TEST_TMP.mkdir(parents=True, exist_ok=True)
    return _TEST_TMP


@pytest.fixture
def git_repo(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"],  capture_output=True, cwd=str(tmp_path))
    subprocess.run(["git", "config", "user.name",  "Test"],     capture_output=True, cwd=str(tmp_path))
    (tmp_path / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "."],          capture_output=True, cwd=str(tmp_path))
    subprocess.run(["git", "commit", "-m", "init"], capture_output=True, cwd=str(tmp_path))
    return tmp_path


# ── Consistencia de schemas ────────────────────────────────────────────────────

class TestStructure:
    def test_tools_count_at_least_60(self):
        assert len(_TOOLS) >= 60, f"Solo hay {len(_TOOLS)} tools (mínimo 60)"

    def test_tool_fns_matches_tools(self):
        names = {t["name"] for t in _TOOLS}
        keys  = set(_TOOL_FNS.keys())
        assert names == keys, f"Mismatch — falta en _TOOL_FNS: {names-keys}, extra: {keys-names}"

    def test_every_tool_has_name_and_description(self):
        for t in _TOOLS:
            assert "name" in t and t["name"], f"Tool sin nombre: {t}"
            assert "description" in t and t["description"], f"Tool sin descripción: {t['name']}"

    def test_every_tool_has_input_schema(self):
        for t in _TOOLS:
            assert "inputSchema" in t, f"Tool sin inputSchema: {t['name']}"
            schema = t["inputSchema"]
            assert schema.get("type") == "object", f"{t['name']}: inputSchema.type != 'object'"

    def test_all_handlers_callable(self):
        for name, fn in _TOOL_FNS.items():
            assert callable(fn), f"Handler de '{name}' no es callable"

    def test_git_tools_present(self):
        names = {t["name"] for t in _TOOLS}
        for n in ("git_status", "git_log", "git_commit", "git_push", "git_pull", "git_branch"):
            assert n in names, f"Falta {n} en _TOOLS"

    def test_docker_tools_present(self):
        names = {t["name"] for t in _TOOLS}
        for n in ("docker_ps", "docker_logs", "docker_exec", "compose_up", "compose_down"):
            assert n in names, f"Falta {n} en _TOOLS"

    def test_build_tools_present(self):
        names = {t["name"] for t in _TOOLS}
        for n in ("make_run", "run_script", "python_exec", "pip_tool", "npm_tool"):
            assert n in names, f"Falta {n} en _TOOLS"

    def test_archive_tools_present(self):
        names = {t["name"] for t in _TOOLS}
        for n in ("archive_create", "archive_list", "archive_extract"):
            assert n in names, f"Falta {n} en _TOOLS"

    def test_fs_mutation_tools_present(self):
        names = {t["name"] for t in _TOOLS}
        for n in ("chmod_file", "chown_file", "mv_file", "cp_file", "rm_file", "mkdir_dir", "touch_file"):
            assert n in names, f"Falta {n} en _TOOLS"


# ── Git tools ─────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not HAS_GIT, reason="git no disponible")
class TestGitTools:
    def test_git_status_clean_repo(self, git_repo):
        result = _tool_git_status({"path": str(git_repo)})
        assert isinstance(result, str) and len(result) > 0

    def test_git_status_dirty_repo(self, git_repo):
        (git_repo / "new_file.py").write_text("x = 1\n")
        result = _tool_git_status({"path": str(git_repo)})
        assert "new_file.py" in result or "untracked" in result.lower() or "?" in result

    def test_git_log_returns_commits(self, git_repo):
        result = _tool_git_log({"path": str(git_repo), "n": 5})
        assert "init" in result.lower() or "commit" in result.lower()

    def test_git_branch_shows_branch(self, git_repo):
        result = _tool_git_branch({"path": str(git_repo)})
        assert isinstance(result, str) and len(result) > 0

    def test_git_diff_no_changes(self, git_repo):
        result = _tool_git_diff({"path": str(git_repo)})
        assert isinstance(result, str)


# ── Filesystem mutations ───────────────────────────────────────────────────────

class TestFilesystemMutations:
    def test_mkdir_creates_directory(self, tmp_path):
        new_dir = tmp_path / "subdir" / "nested"
        result = _tool_mkdir_dir({"path": str(new_dir), "parents": True})
        assert new_dir.exists() and new_dir.is_dir()

    def test_touch_creates_file(self, tmp_path):
        f = tmp_path / "touched.txt"
        result = _tool_touch_file({"path": str(f)})
        assert f.exists()

    def test_cp_copies_file(self, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("hello")
        dst = tmp_path / "dst.txt"
        _tool_cp_file({"source": str(src), "destination": str(dst)})
        assert dst.exists() and dst.read_text() == "hello"

    def test_mv_moves_file(self, tmp_path):
        src = tmp_path / "move_src.txt"
        src.write_text("content")
        dst = tmp_path / "move_dst.txt"
        _tool_mv_file({"source": str(src), "destination": str(dst)})
        assert dst.exists() and not src.exists()

    def test_rm_removes_file(self, tmp_path):
        f = tmp_path / "to_delete.txt"
        f.write_text("bye")
        _tool_rm_file({"path": str(f)})
        assert not f.exists()

    def test_rm_dir_removes_directory(self, tmp_path):
        d = tmp_path / "to_delete_dir"
        d.mkdir()
        (d / "file.txt").write_text("x")
        _tool_rm_dir({"path": str(d), "recursive": True})
        assert not d.exists()

    def test_chmod_changes_permissions(self, tmp_path):
        f = tmp_path / "perms.sh"
        f.write_text("#!/bin/bash\necho hi\n")
        result = _tool_chmod_file({"path": str(f), "mode": "755"})
        assert isinstance(result, str)
        s = oct(os.stat(str(f)).st_mode)
        assert s.endswith("755")

    def test_symlink_create_and_readlink(self, tmp_path):
        target = tmp_path / "target.txt"
        target.write_text("target content")
        link = tmp_path / "mylink"
        _tool_symlink_create({"target": str(target), "link_path": str(link)})
        assert link.is_symlink()
        result = _tool_readlink({"path": str(link)})
        assert str(target) in result


# ── Archive tools ──────────────────────────────────────────────────────────────

class TestArchiveTools:
    def test_create_tar_gz(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("hello")
        (src / "b.txt").write_text("world")
        archive = tmp_path / "out.tar.gz"
        result = _tool_archive_create({
            "archive": str(archive),
            "sources": str(src),
            "format": "tar.gz",
        })
        assert archive.exists()

    def test_list_tar_gz(self, tmp_path):
        src = tmp_path / "listme"
        src.mkdir()
        (src / "file.txt").write_text("data")
        archive = tmp_path / "list.tar.gz"
        _tool_archive_create({"archive": str(archive), "sources": str(src), "format": "tar.gz"})
        result = _tool_archive_list({"archive": str(archive)})
        assert "file.txt" in result

    def test_extract_tar_gz(self, tmp_path):
        src = tmp_path / "extract_src"
        src.mkdir()
        (src / "ex.txt").write_text("extracted content")
        archive = tmp_path / "extract.tar.gz"
        with tarfile.open(str(archive), "w:gz") as tar:
            tar.add(str(src / "ex.txt"), arcname="ex.txt")
        out_dir = tmp_path / "extracted"
        out_dir.mkdir()
        result = _tool_archive_extract({"archive": str(archive), "destination": str(out_dir)})
        assert (out_dir / "ex.txt").exists()

    def test_create_zip(self, tmp_path):
        src = tmp_path / "zipsrc"
        src.mkdir()
        (src / "z.txt").write_text("zip content")
        archive = tmp_path / "out.zip"
        result = _tool_archive_create({
            "archive": str(archive),
            "sources": str(src),
            "format": "zip",
        })
        assert archive.exists()


# ── Build/Run tools ────────────────────────────────────────────────────────────

class TestBuildTools:
    @pytest.mark.skipif(not HAS_MAKE, reason="make no disponible")
    def test_make_run_simple_target(self, tmp_path):
        (tmp_path / "Makefile").write_text("all:\n\techo BUILD_OK\n")
        result = _tool_make_run({"directory": str(tmp_path), "target": "all"})
        assert "BUILD_OK" in result

    def test_run_script_bash(self, tmp_path):
        script = tmp_path / "test.sh"
        script.write_text("#!/bin/bash\necho SCRIPT_DONE\n")
        result = _tool_run_script({"script": str(script), "interpreter": "bash"})
        assert "SCRIPT_DONE" in result

    def test_python_exec_simple(self):
        result = _tool_python_exec({"code": "print('hello devops')"})
        assert "hello devops" in result

    def test_python_exec_arithmetic(self):
        result = _tool_python_exec({"code": "print(6 * 7)"})
        assert "42" in result

    def test_python_exec_syntax_error(self):
        result = _tool_python_exec({"code": "def broken(:"})
        assert "Error" in result or "SyntaxError" in result or "error" in result.lower()


# ── Docker tools (mocked subprocess) ──────────────────────────────────────────

class TestDockerToolsMocked:
    def test_docker_ps_calls_docker(self):
        from mcp_servers.devops_assistant import _tool_docker_ps
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("CONTAINER ID   IMAGE\nabc123   nginx\n", "")
        mock_proc.returncode = 0
        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
            result = _tool_docker_ps({})
        assert mock_popen.called
        cmd = mock_popen.call_args[0][0]
        assert "docker" in cmd

    def test_compose_up_calls_docker_compose(self, tmp_path):
        from mcp_servers.devops_assistant import _tool_compose_up
        # Create a fake docker-compose.yml so _require_compose succeeds
        (tmp_path / "docker-compose.yml").write_text("version: '3'\nservices:\n  web:\n    image: nginx\n")
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("Servicios levantados.\n", "")
        mock_proc.returncode = 0
        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
            result = _tool_compose_up({"path": str(tmp_path), "detach": True})
        assert mock_popen.called
        cmd = mock_popen.call_args[0][0]
        assert "docker" in cmd or "compose" in " ".join(cmd)


# ── Prompts ────────────────────────────────────────────────────────────────────

class TestDevopsPrompts:
    def test_prompts_dict_exists(self):
        assert isinstance(_PROMPTS, dict) and len(_PROMPTS) >= 3

    def test_all_prompts_have_description(self):
        for name, defn in _PROMPTS.items():
            assert "description" in defn, f"Prompt '{name}' sin description"
            assert defn["description"], f"Prompt '{name}' description vacío"

    def test_all_prompts_have_arguments(self):
        for name, defn in _PROMPTS.items():
            assert "arguments" in defn, f"Prompt '{name}' sin arguments"
            assert isinstance(defn["arguments"], list)

    def test_expected_prompts_present(self):
        for name in ("docker_compose_setup", "git_workflow", "ci_pipeline"):
            assert name in _PROMPTS, f"Prompt '{name}' no encontrado"

    def test_docker_compose_setup_returns_messages(self):
        result = _prompt_get("docker_compose_setup", {"stack": "FastAPI + PostgreSQL + Redis"})
        assert isinstance(result, list) and len(result) > 0
        msg = result[0]
        assert msg.get("role") == "user"
        assert "docker-compose" in msg["content"]["text"].lower() or "compose" in msg["content"]["text"].lower()

    def test_git_workflow_returns_messages(self):
        result = _prompt_get("git_workflow", {"team_size": "small", "project": "API REST Python"})
        assert isinstance(result, list) and len(result) > 0
        assert result[0]["role"] == "user"
        text = result[0]["content"]["text"]
        assert "git" in text.lower() or "branch" in text.lower() or "flujo" in text.lower()

    def test_ci_pipeline_returns_messages(self):
        result = _prompt_get("ci_pipeline", {"project": "Python Django app", "platform": "github_actions"})
        assert isinstance(result, list) and len(result) > 0
        assert result[0]["role"] == "user"
        text = result[0]["content"]["text"]
        assert "pipeline" in text.lower() or "ci" in text.lower() or "github" in text.lower()

    def test_unknown_prompt_returns_fallback(self):
        result = _prompt_get("nonexistent_xyz", {})
        assert isinstance(result, list) and len(result) > 0

    def test_prompt_get_all_known(self):
        for name in _PROMPTS:
            result = _prompt_get(name, {})
            assert isinstance(result, list) and len(result) > 0, f"_prompt_get('{name}') devolvió vacío"


# ── Recursos ───────────────────────────────────────────────────────────────────

_EXPECTED_DEVOPS_RESOURCES = [
    "project://git",
    "project://docker",
    "project://makefile",
    "project://ci",
]


class TestDevopsResources:
    def test_resources_list_exists(self):
        assert isinstance(_RESOURCES, list) and len(_RESOURCES) == 4

    def test_all_expected_resources_registered(self):
        uris = {r["uri"] for r in _RESOURCES}
        for uri in _EXPECTED_DEVOPS_RESOURCES:
            assert uri in uris, f"Resource '{uri}' no en _RESOURCES"

    def test_all_resources_have_uri_name_description(self):
        for r in _RESOURCES:
            assert "uri" in r and r["uri"]
            assert "name" in r and r["name"]
            assert "description" in r and r["description"]

    def test_resource_fns_match_resources(self):
        uris = {r["uri"] for r in _RESOURCES}
        assert uris == set(_RESOURCE_FNS.keys()), \
            f"Mismatch: resources={uris}, fns={set(_RESOURCE_FNS.keys())}"

    def test_all_resource_handlers_callable(self):
        for uri, fn in _RESOURCE_FNS.items():
            assert callable(fn), f"Handler de '{uri}' no es callable"

    @pytest.mark.parametrize("uri", _EXPECTED_DEVOPS_RESOURCES)
    def test_resource_returns_string(self, uri):
        fn = _RESOURCE_FNS[uri]
        result = fn()
        assert isinstance(result, str), f"Resource '{uri}' no devuelve string"

    def test_git_resource_content(self):
        result = _RESOURCE_FNS["project://git"]()
        assert isinstance(result, str)

    def test_docker_resource_content(self):
        result = _RESOURCE_FNS["project://docker"]()
        assert isinstance(result, str)

    def test_makefile_resource_no_exception(self):
        result = _RESOURCE_FNS["project://makefile"]()
        assert isinstance(result, str)

    def test_ci_resource_no_exception(self):
        result = _RESOURCE_FNS["project://ci"]()
        assert isinstance(result, str)


# ── Configuración ──────────────────────────────────────────────────────────────

class TestDevopsConfig:
    def test_devops_in_default_config(self):
        from config import DEFAULT_CONFIG
        assert "devopsAssistant" in DEFAULT_CONFIG["mcp"]
        assert DEFAULT_CONFIG["mcp"]["devopsAssistant"]["enabled"] is True

    def test_database_in_default_config(self):
        from config import DEFAULT_CONFIG
        assert "databaseAssistant" in DEFAULT_CONFIG["mcp"]
        assert DEFAULT_CONFIG["mcp"]["databaseAssistant"]["enabled"] is False

    def test_ooconfig_devops_field(self):
        from config import OOConfig
        cfg = OOConfig()
        assert hasattr(cfg, "mcp_devops_assistant_enabled")
        assert cfg.mcp_devops_assistant_enabled is True

    def test_ooconfig_database_field(self):
        from config import OOConfig
        cfg = OOConfig()
        assert hasattr(cfg, "mcp_database_assistant_enabled")
        assert cfg.mcp_database_assistant_enabled is False

    def test_config_save_includes_devops(self, tmp_path):
        import json
        from unittest.mock import patch
        from config import OOConfig
        cfg_file = tmp_path / "oocode.json"
        cfg = OOConfig()
        cfg.mcp_devops_assistant_enabled = False
        with patch("config.CONFIG_FILE", cfg_file):
            cfg.save()
        data = json.loads(cfg_file.read_text())
        assert data["mcp"]["devopsAssistant"]["enabled"] is False

    def test_config_save_includes_database(self, tmp_path):
        import json
        from unittest.mock import patch
        from config import OOConfig
        cfg_file = tmp_path / "oocode.json"
        cfg = OOConfig()
        cfg.mcp_database_assistant_enabled = True
        with patch("config.CONFIG_FILE", cfg_file):
            cfg.save()
        data = json.loads(cfg_file.read_text())
        assert data["mcp"]["databaseAssistant"]["enabled"] is True

    def test_config_load_devops_false(self, tmp_path):
        import json
        from unittest.mock import patch
        from config import OOConfig
        cfg_file = tmp_path / "oocode.json"
        cfg_file.write_text(json.dumps({"mcp": {"devopsAssistant": {"enabled": False}}}))
        with patch("config.CONFIG_FILE", cfg_file):
            cfg = OOConfig.load()
        assert cfg.mcp_devops_assistant_enabled is False

    def test_config_load_database_true(self, tmp_path):
        import json
        from unittest.mock import patch
        from config import OOConfig
        cfg_file = tmp_path / "oocode.json"
        cfg_file.write_text(json.dumps({"mcp": {"databaseAssistant": {"enabled": True}}}))
        with patch("config.CONFIG_FILE", cfg_file):
            cfg = OOConfig.load()
        assert cfg.mcp_database_assistant_enabled is True
