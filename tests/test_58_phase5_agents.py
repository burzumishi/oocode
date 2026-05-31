"""Tests Fase 5: AgentTeam.execute, /agent team TUI, WebUI /agents, tools MCP gráficas."""
import json
import threading
import time
import queue
from pathlib import Path
import tempfile
import pytest


# ── AgentTeam ─────────────────────────────────────────────────────────────────

class TestAgentTeam:
    def test_execute_returns_results(self, tmp_path):
        from agent.tasks import AgentTeam

        team = AgentTeam("t1", "coding", ["coding"], str(tmp_path / "t.json"))
        st1 = team.add_subtask("tarea1", "coding")
        st2 = team.add_subtask("tarea2", "coding")

        class FakeRunner:
            def run(self, agent_id, task, silent=True):
                return f"resultado de {task}"

        results = team.execute(FakeRunner())
        assert st1["id"] in results
        assert st2["id"] in results
        assert "tarea1" in results[st1["id"]]
        assert "tarea2" in results[st2["id"]]

    def test_execute_marks_team_completed(self, tmp_path):
        from agent.tasks import AgentTeam

        team = AgentTeam("t2", "coding", ["coding"], str(tmp_path / "t.json"))
        team.add_subtask("tarea", "coding")

        class FakeRunner:
            def run(self, agent_id, task, silent=True):
                return "ok"

        team.execute(FakeRunner())
        assert team.status == "completed"

    def test_execute_on_empty_returns_existing_results(self, tmp_path):
        from agent.tasks import AgentTeam

        team = AgentTeam("t3", "coding", ["coding"], str(tmp_path / "t.json"))
        # Sin subtasks → devuelve dict vacío
        class FakeRunner:
            def run(self, *a, **kw): return "x"

        result = team.execute(FakeRunner())
        assert result == {}

    def test_execute_handles_runner_exception(self, tmp_path):
        from agent.tasks import AgentTeam

        team = AgentTeam("t4", "coding", ["coding"], str(tmp_path / "t.json"))
        st = team.add_subtask("tarea_mala", "coding")

        class BrokenRunner:
            def run(self, agent_id, task, silent=True):
                raise RuntimeError("fallo del runner")

        results = team.execute(BrokenRunner())
        assert st["id"] in results
        assert "[error]" in results[st["id"]]

    def test_execute_persists_completed_subtasks(self, tmp_path):
        from agent.tasks import AgentTeam

        team_file = str(tmp_path / "team.json")
        team = AgentTeam("t5", "coding", ["coding"], team_file)
        st = team.add_subtask("persistir", "coding")

        class FakeRunner:
            def run(self, agent_id, task, silent=True):
                return "persistido"

        team.execute(FakeRunner())

        # Recargar desde disco
        data = json.loads(Path(team_file).read_text())
        assert data["subtasks"][0]["status"] == "completed"
        assert data["status"] == "completed"

    def test_fail_subtask(self, tmp_path):
        from agent.tasks import AgentTeam

        team = AgentTeam("t6", "coding", ["coding"], str(tmp_path / "t.json"))
        st = team.add_subtask("tarea", "coding")
        team.fail_subtask(st["id"], "error de prueba")

        data = json.loads((tmp_path / "t.json").read_text())
        assert data["subtasks"][0]["status"] == "failed"

    def test_list_teams_returns_created(self, tmp_path, monkeypatch):
        from agent import tasks as tasks_mod
        monkeypatch.setattr(tasks_mod, "CONFIG_DIR", tmp_path)
        (tmp_path / "teams").mkdir()

        team = tasks_mod.AgentTeam("equipo1", "coding", ["coding"],
                                    str(tmp_path / "teams" / "equipo1.json"))
        team._save()

        teams = tasks_mod.list_teams()
        assert any(t["team_id"] == "equipo1" for t in teams)

    def test_delete_team(self, tmp_path, monkeypatch):
        from agent import tasks as tasks_mod
        monkeypatch.setattr(tasks_mod, "CONFIG_DIR", tmp_path)
        (tmp_path / "teams").mkdir()

        tasks_mod.AgentTeam("del1", "main", ["main"],
                             str(tmp_path / "teams" / "del1.json"))._save()

        assert tasks_mod.delete_team("del1") is True
        assert not (tmp_path / "teams" / "del1.json").exists()
        assert tasks_mod.delete_team("del1") is False  # ya borrado


# ── /agent team TUI ───────────────────────────────────────────────────────────

class TestAgentTeamTUI:
    def _make_config(self):
        from unittest.mock import MagicMock
        cfg = MagicMock()
        agent_main    = MagicMock(); agent_main.id = "main";    agent_main.name = "Main";    agent_main.emoji = "🤖"; agent_main.model = None; agent_main.workspace = "/tmp"
        agent_coding  = MagicMock(); agent_coding.id = "coding"; agent_coding.name = "Coder"; agent_coding.emoji = "💻"; agent_coding.model = None; agent_coding.workspace = "/tmp"
        cfg.agents = [agent_main, agent_coding]
        cfg.agent_id = "main"
        return cfg

    def test_team_list_empty(self, tmp_path, monkeypatch, capsys):
        from agent import tasks as tm
        monkeypatch.setattr(tm, "CONFIG_DIR", tmp_path)
        (tmp_path / "teams").mkdir()

        from ui.commands import _cmd_agent_team
        _cmd_agent_team("list", self._make_config(), None)
        # No debería lanzar excepción

    def test_team_create(self, tmp_path, monkeypatch, capsys):
        from agent import tasks as tm
        monkeypatch.setattr(tm, "CONFIG_DIR", tmp_path)
        (tmp_path / "teams").mkdir()

        from ui.commands import _cmd_agent_team
        _cmd_agent_team("create equipo-test coding coding,main", self._make_config(), None)
        assert (tmp_path / "teams" / "equipo-test.json").exists()

    def test_team_create_invalid_agent(self, tmp_path, monkeypatch, capsys):
        from agent import tasks as tm
        monkeypatch.setattr(tm, "CONFIG_DIR", tmp_path)
        (tmp_path / "teams").mkdir()

        from ui.commands import _cmd_agent_team
        # "unknown" no está en config.agents
        _cmd_agent_team("create bad-team unknown coding", self._make_config(), None)
        assert not (tmp_path / "teams" / "bad-team.json").exists()

    def test_team_add_and_status(self, tmp_path, monkeypatch):
        from agent import tasks as tm
        monkeypatch.setattr(tm, "CONFIG_DIR", tmp_path)
        (tmp_path / "teams").mkdir()

        from ui.commands import _cmd_agent_team
        cfg = self._make_config()
        _cmd_agent_team("create eq2 coding coding", cfg, None)
        _cmd_agent_team("add eq2 analizar-codigo coding", cfg, None)

        data = json.loads((tmp_path / "teams" / "eq2.json").read_text())
        assert len(data["subtasks"]) == 1
        assert data["subtasks"][0]["description"] == "analizar-codigo"

    def test_team_done(self, tmp_path, monkeypatch):
        from agent import tasks as tm
        monkeypatch.setattr(tm, "CONFIG_DIR", tmp_path)
        (tmp_path / "teams").mkdir()

        from ui.commands import _cmd_agent_team
        cfg = self._make_config()
        _cmd_agent_team("create eq3 coding coding", cfg, None)
        _cmd_agent_team("add eq3 mi-tarea coding", cfg, None)
        data = json.loads((tmp_path / "teams" / "eq3.json").read_text())
        st_id = data["subtasks"][0]["id"]

        _cmd_agent_team(f"done eq3 {st_id} resultado-ok", cfg, None)
        data2 = json.loads((tmp_path / "teams" / "eq3.json").read_text())
        assert data2["subtasks"][0]["status"] == "completed"

    def test_team_delete(self, tmp_path, monkeypatch):
        from agent import tasks as tm
        monkeypatch.setattr(tm, "CONFIG_DIR", tmp_path)
        (tmp_path / "teams").mkdir()

        from ui.commands import _cmd_agent_team
        cfg = self._make_config()
        _cmd_agent_team("create eq4 coding coding", cfg, None)
        assert (tmp_path / "teams" / "eq4.json").exists()
        _cmd_agent_team("delete eq4", cfg, None)
        assert not (tmp_path / "teams" / "eq4.json").exists()

    def test_team_run_with_runner(self, tmp_path, monkeypatch):
        from agent import tasks as tm
        monkeypatch.setattr(tm, "CONFIG_DIR", tmp_path)
        (tmp_path / "teams").mkdir()

        from unittest.mock import MagicMock
        from ui.commands import _cmd_agent_team
        cfg = self._make_config()

        runner = MagicMock()
        runner.run.return_value = "trabajo completado"
        loop  = MagicMock()
        loop.subagent_runner = runner

        _cmd_agent_team("create eq5 coding coding", cfg, loop)
        _cmd_agent_team("add eq5 refactorizar-modulo coding", cfg, loop)
        _cmd_agent_team("run eq5", cfg, loop)

        runner.run.assert_called_once()


# ── WebUI /agents ─────────────────────────────────────────────────────────────

class TestWebUIAgents:
    @pytest.fixture
    def client(self):
        flask = pytest.importorskip("flask", reason="flask not installed")  # noqa: F841
        from webui.app import app
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    def test_agents_page_returns_200(self, client):
        resp = client.get('/agents')
        assert resp.status_code == 200

    def test_agents_page_has_polling_script(self, client):
        resp = client.get('/agents')
        assert b'fetchAgents' in resp.data
        assert b'POLL_INTERVAL' in resp.data

    def test_api_agents_returns_json(self, client):
        resp = client.get('/api/agents')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "running" in data
        assert "recent" in data
        assert "ts" in data

    def test_api_agents_kill_not_found(self, client):
        resp = client.post('/api/agents/kill/nope')
        assert resp.status_code == 404

    def test_api_agents_steer_missing_instruction(self, client):
        resp = client.post('/api/agents/steer/nope',
                           json={}, content_type='application/json')
        assert resp.status_code == 400

    def test_api_agents_steer_not_found(self, client):
        resp = client.post('/api/agents/steer/nope',
                           json={"instruction": "haz algo"},
                           content_type='application/json')
        assert resp.status_code == 404

    def test_api_agents_spawn_missing_params(self, client):
        resp = client.post('/api/agents/spawn',
                           json={}, content_type='application/json')
        assert resp.status_code == 400

    def test_api_agents_kill_running_agent(self, client):
        """Registra un subagente falso y verifica que kill lo detiene."""
        from agent.subagent import _registry, _registry_lock, ActiveSubAgent
        import uuid

        run_id = uuid.uuid4().hex
        sub = ActiveSubAgent(
            run_id=run_id, agent_id="coding", agent_name="Test", agent_emoji="💻",
            task="test task", thread=threading.Thread(target=lambda: None),
            kill_event=threading.Event(), steer_queue=queue.SimpleQueue(),
        )
        with _registry_lock:
            _registry[run_id] = sub

        try:
            resp = client.post(f'/api/agents/kill/{run_id[:6]}')
            data = json.loads(resp.data)
            assert resp.status_code == 200
            assert data["ok"] is True
            assert sub.status == "killed"
        finally:
            with _registry_lock:
                _registry.pop(run_id, None)

    def test_api_agents_steer_running_agent(self, client):
        """Registra un subagente falso y verifica que steer encola la instrucción."""
        from agent.subagent import _registry, _registry_lock, ActiveSubAgent
        import uuid

        run_id = uuid.uuid4().hex
        steer_q = queue.SimpleQueue()
        sub = ActiveSubAgent(
            run_id=run_id, agent_id="main", agent_name="Main", agent_emoji="🤖",
            task="test steer", thread=threading.Thread(target=lambda: None),
            kill_event=threading.Event(), steer_queue=steer_q,
        )
        with _registry_lock:
            _registry[run_id] = sub

        try:
            resp = client.post(f'/api/agents/steer/{run_id[:6]}',
                               json={"instruction": "nueva instrucción"},
                               content_type='application/json')
            data = json.loads(resp.data)
            assert resp.status_code == 200
            assert data["ok"] is True
            assert not steer_q.empty()
            assert steer_q.get() == "nueva instrucción"
            assert sub.steer_count == 1
        finally:
            with _registry_lock:
                _registry.pop(run_id, None)


# ── MCP chart tools ───────────────────────────────────────────────────────────

class TestMCPChartTools:
    """Tests de los tools de gráficas matplotlib. Usan tempfile propio para
    evitar interferencias con el autouse fixture _cleanup_test_tmp."""

    def test_create_bar_chart_creates_file(self):
        import tempfile
        from mcp_servers.home_office_assistant import _tool_create_bar_chart
        with tempfile.TemporaryDirectory() as d:
            out = str(Path(d) / "bar.png")
            result = _tool_create_bar_chart({
                "data": {"categories": ["A", "B", "C"], "values": [10, 20, 30]},
                "title": "Test Bar",
                "output": out,
            })
            assert "✅" in result, f"Tool error: {result}"
            assert Path(out).exists()

    def test_create_pie_chart_creates_file(self):
        import tempfile
        from mcp_servers.home_office_assistant import _tool_create_pie_chart
        with tempfile.TemporaryDirectory() as d:
            out = str(Path(d) / "pie.png")
            result = _tool_create_pie_chart({
                "data": {"labels": ["X", "Y"], "sizes": [60, 40]},
                "title": "Test Pie",
                "output": out,
            })
            assert "✅" in result, f"Tool error: {result}"
            assert Path(out).exists()

    def test_create_line_chart_creates_file(self):
        import tempfile
        from mcp_servers.home_office_assistant import _tool_create_line_chart
        with tempfile.TemporaryDirectory() as d:
            out = str(Path(d) / "line.png")
            result = _tool_create_line_chart({
                "data": {"x_labels": ["Ene", "Feb", "Mar"], "y_values": [5, 10, 8]},
                "output": out,
            })
            assert "✅" in result, f"Tool error: {result}"
            assert Path(out).exists()

    def test_insert_chart_unsupported_type(self, tmp_path):
        from mcp_servers.home_office_assistant import _tool_insert_chart
        result = _tool_insert_chart({
            "path": str(tmp_path / "noexiste.docx"),
            "chart_type": "waterfall",
            "data": {},
        })
        assert "no encontrado" in result or "no soportado" in result

    def test_chart_tools_registered_in_tool_fns(self):
        from mcp_servers.home_office_assistant import _TOOL_FNS
        for name in ("insert_chart", "create_bar_chart", "create_pie_chart", "create_line_chart"):
            assert name in _TOOL_FNS, f"Tool '{name}' no registrada en _TOOL_FNS"
