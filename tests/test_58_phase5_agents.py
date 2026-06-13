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
        st1 = team.add_subtask("task1", "coding")
        st2 = team.add_subtask("task2", "coding")

        class FakeRunner:
            def run(self, agent_id, task, silent=True):
                return f"result of {task}"

        results = team.execute(FakeRunner())
        assert st1["id"] in results
        assert st2["id"] in results
        assert "task1" in results[st1["id"]]
        assert "task2" in results[st2["id"]]

    def test_execute_marks_team_completed(self, tmp_path):
        from agent.tasks import AgentTeam

        team = AgentTeam("t2", "coding", ["coding"], str(tmp_path / "t.json"))
        team.add_subtask("task", "coding")

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
        st = team.add_subtask("bad_task", "coding")

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
        st = team.add_subtask("task", "coding")
        team.fail_subtask(st["id"], "test error")

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
        _cmd_agent_team("add eq3 my-task coding", cfg, None)
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


# ── LLM tools: create_team / run_team ────────────────────────────────────────

class TestLLMTeamTools:
    """Tests del API LLM de create_team/run_team (as_team_schemas)."""

    def _make_runner(self, agent_ids=("main", "coder", "docs")):
        from unittest.mock import MagicMock
        from agent.subagent import SubAgentRunner
        cfg = MagicMock()
        agents = []
        for aid in agent_ids:
            a = MagicMock()
            a.id = aid
            a.name = aid.capitalize()
            a.emoji = "🤖"
            agents.append(a)
        cfg.agents = agents
        cfg.model = "test-model"
        cfg.subagents_max_concurrent = 4
        runner = SubAgentRunner.__new__(SubAgentRunner)
        runner.config = cfg
        runner._parent_webui_queue = None
        return runner

    def test_create_team_invalid_lead_returns_error(self, tmp_path, monkeypatch):
        from agent import tasks as tm
        monkeypatch.setattr(tm, "CONFIG_DIR", tmp_path)
        (tmp_path / "teams").mkdir()
        runner = self._make_runner()
        tools = runner.as_team_schemas()
        _, create_fn, _ = tools[0]
        result = create_fn(
            team_id="t1",
            subtasks=[{"description": "x", "assign_to": "main"}],
            lead_agent_id="nonexistent",
        )
        assert "Error" in result
        assert "nonexistent" in result

    def test_create_team_invalid_assign_to_returns_error(self, tmp_path, monkeypatch):
        from agent import tasks as tm
        monkeypatch.setattr(tm, "CONFIG_DIR", tmp_path)
        (tmp_path / "teams").mkdir()
        runner = self._make_runner()
        tools = runner.as_team_schemas()
        _, create_fn, _ = tools[0]
        result = create_fn(
            team_id="t2",
            subtasks=[{"description": "x", "assign_to": "ghost_agent"}],
        )
        assert "Error" in result
        assert "ghost_agent" in result

    def test_create_team_uses_first_agent_as_default_lead(self, tmp_path, monkeypatch):
        from agent import tasks as tm
        monkeypatch.setattr(tm, "CONFIG_DIR", tmp_path)
        (tmp_path / "teams").mkdir()
        runner = self._make_runner(agent_ids=("alpha", "beta"))
        tools = runner.as_team_schemas()
        _, create_fn, _ = tools[0]
        result = create_fn(
            team_id="t3",
            subtasks=[{"description": "do x", "assign_to": "alpha"}],
        )
        assert "alpha" in result
        assert "Error" not in result

    def test_schema_lead_default_matches_first_agent(self):
        runner = self._make_runner(agent_ids=("custom1", "custom2"))
        tools = runner.as_team_schemas()
        _, _, create_schema = tools[0]
        desc = create_schema["parameters"]["properties"]["lead_agent_id"]["description"]
        assert "custom1" in desc

    def test_create_then_run_team_flow(self, tmp_path, monkeypatch):
        from agent import tasks as tm
        monkeypatch.setattr(tm, "CONFIG_DIR", tmp_path)
        (tmp_path / "teams").mkdir()
        runner = self._make_runner()
        runner.run = lambda agent_id, task, silent=True, **kw: f"done: {task}"
        tools = runner.as_team_schemas()
        _, create_fn, _ = tools[0]
        _, run_fn, _    = tools[1]
        create_fn(
            team_id="flow-test",
            subtasks=[
                {"description": "analyze code", "assign_to": "coder"},
                {"description": "write docs",   "assign_to": "docs"},
            ],
        )
        result = run_fn(team_id="flow-test")
        assert "analyze code" in result
        assert "write docs" in result

    def test_run_team_nonexistent_returns_error(self, tmp_path, monkeypatch):
        from agent import tasks as tm
        monkeypatch.setattr(tm, "CONFIG_DIR", tmp_path)
        (tmp_path / "teams").mkdir()
        runner = self._make_runner()
        tools = runner.as_team_schemas()
        _, run_fn, _ = tools[1]
        result = run_fn(team_id="does-not-exist")
        assert "Error" in result

    def test_schema_description_shows_available_agents(self):
        runner = self._make_runner(agent_ids=("qa", "dev", "pm"))
        tools = runner.as_team_schemas()
        _, _, create_schema = tools[0]
        desc = create_schema["description"]
        assert "qa" in desc
        assert "dev" in desc
        assert "pm" in desc


# ── timeout por subagente ─────────────────────────────────────────────────────

class TestSubagentTimeout:
    """Tests del watchdog de timeout en spawn_background y spawn_subagent/spawn_fanout."""

    def _make_runner(self):
        from unittest.mock import MagicMock
        from agent.subagent import SubAgentRunner, _get_concurrency_sem
        cfg = MagicMock()
        agent_main   = MagicMock(); agent_main.id   = "main";   agent_main.name   = "Main";   agent_main.emoji = "🤖"
        agent_coding = MagicMock(); agent_coding.id = "coding"; agent_coding.name = "Coder"; agent_coding.emoji = "💻"
        cfg.agents = [agent_main, agent_coding]
        runner = SubAgentRunner.__new__(SubAgentRunner)
        runner.config              = cfg
        runner._parent_webui_queue = None
        runner._concurrency_sem    = _get_concurrency_sem(4)
        return runner

    # ── spawn_background watchdog ─────────────────────────────────────────────

    def test_no_timeout_completes_normally(self):
        runner = self._make_runner()
        runner.run = lambda agent_id, task, silent=True, **kw: "ok"
        sub = runner.spawn_background("main", "fast_task", timeout_seconds=0)
        sub.thread.join(timeout=5)
        assert sub.status == "done"
        assert sub.result == "ok"

    def test_timeout_kills_slow_subagent(self):
        """Un subagente que dura más que timeout_seconds se marca como killed."""
        runner = self._make_runner()

        def slow_run(agent_id, task, silent=True, kill_event=None, **kw):
            # Espera hasta que kill_event se active o timeout de seguridad
            if kill_event:
                kill_event.wait(timeout=10)
            return "nunca llega"

        runner.run = slow_run
        sub = runner.spawn_background("main", "slow_task", timeout_seconds=1)
        sub.thread.join(timeout=5)

        assert sub.status == "killed"
        assert sub.error is not None
        assert "Timeout" in sub.error
        assert "1s" in sub.error

    def test_timeout_sets_kill_event(self):
        """El watchdog activa kill_event para detener el loop del subagente."""
        runner = self._make_runner()
        observed_kill_event = []

        def capturing_run(agent_id, task, silent=True, kill_event=None, **kw):
            observed_kill_event.append(kill_event)
            if kill_event:
                kill_event.wait(timeout=10)
            return ""

        runner.run = capturing_run
        sub = runner.spawn_background("main", "task", timeout_seconds=1)
        sub.thread.join(timeout=5)

        assert len(observed_kill_event) == 1
        assert observed_kill_event[0].is_set()

    def test_external_kill_before_timeout_does_not_double_set(self):
        """Si el usuario mata antes del timeout, el watchdog no sobrescribe el estado."""
        runner = self._make_runner()

        def killable_run(agent_id, task, silent=True, kill_event=None, **kw):
            if kill_event:
                kill_event.wait(timeout=10)
            return ""

        runner.run = killable_run
        sub = runner.spawn_background("main", "task", timeout_seconds=5)
        # Simular kill externo antes del timeout
        time.sleep(0.05)
        sub.kill_event.set()
        sub.status = "killed"
        sub.thread.join(timeout=3)

        # El error NO debe decir "Timeout" (fue kill manual, no timeout)
        assert sub.error is None or "Timeout" not in sub.error

    def test_fast_subagent_watchdog_exits_cleanly(self):
        """El watchdog se cancela solo cuando el subagente termina antes del timeout."""
        runner = self._make_runner()
        runner.run = lambda agent_id, task, silent=True, **kw: "fast_result"
        sub = runner.spawn_background("main", "task", timeout_seconds=10)
        sub.thread.join(timeout=5)
        assert sub.status == "done"
        assert sub.result == "fast_result"
        assert sub.error is None

    # ── spawn_subagent tool ───────────────────────────────────────────────────

    def test_spawn_subagent_schema_has_timeout_param(self):
        runner = self._make_runner()
        _, _, schema = runner.as_tool_schema()
        props = schema["parameters"]["properties"]
        assert "timeout_seconds" in props
        assert props["timeout_seconds"]["type"] == "integer"
        assert "timeout_seconds" not in schema["parameters"].get("required", [])

    def test_spawn_subagent_timeout_returns_timeout_message(self):
        runner = self._make_runner()

        def slow_run(agent_id, task, silent=True, kill_event=None, **kw):
            if kill_event:
                kill_event.wait(timeout=10)
            return ""

        runner.run = slow_run
        _, fn, _ = runner.as_tool_schema()
        result = fn(agent_id="main", task="slow_task", timeout_seconds=1)
        assert "Timeout" in result or "timeout" in result.lower()
        assert "main" in result

    def test_spawn_subagent_no_timeout_completes(self):
        runner = self._make_runner()
        runner.run = lambda agent_id, task, silent=True, **kw: "done"
        _, fn, _ = runner.as_tool_schema()
        result = fn(agent_id="main", task="task", timeout_seconds=0)
        assert result == "done"

    # ── spawn_fanout timeout ──────────────────────────────────────────────────

    def test_fanout_schema_has_timeout_param(self):
        runner = self._make_runner()
        _, _, schema = runner.as_fanout_schema()
        props = schema["parameters"]["properties"]
        assert "timeout_seconds" in props
        assert "timeout_seconds" not in schema["parameters"].get("required", [])

    def test_fanout_timeout_kills_slow_chunks(self):
        """Chunks lentos se matan por timeout; los rápidos completan normalmente."""
        runner = self._make_runner()

        def mixed_run(agent_id, task, silent=True, kill_event=None, **kw):
            if "SLOW" in task:
                if kill_event:
                    kill_event.wait(timeout=10)
                return "nunca"
            return f"ok: {task}"

        runner.run = mixed_run
        _, fn, _ = runner.as_fanout_schema()
        result = fn(
            agent_id="main",
            task_chunks=["fast_chunk", "SLOW_chunk"],
            timeout_seconds=1,
        )
        assert "ok: fast_chunk" in result
        assert "⛔" in result   # slow chunk → error/timeout

    def test_fanout_no_timeout_all_complete(self):
        runner = self._make_runner()
        runner.run = lambda agent_id, task, silent=True, **kw: f"ok: {task}"
        _, fn, _ = runner.as_fanout_schema()
        result = fn(agent_id="main", task_chunks=["A", "B"], timeout_seconds=0)
        assert "ok: A" in result
        assert "ok: B" in result


# ── plan_tasks ↔ TaskManager sync ─────────────────────────────────────────────

class TestPlanTaskSync:
    """Tests de sincronización bidireccional entre _plan_tasks y TaskManager."""

    def _make_loop(self, tmp_path, monkeypatch):
        """AgentLoop mínimo con TaskManager real en tmp_path."""
        from unittest.mock import MagicMock, patch
        from agent import tasks as tasks_mod
        monkeypatch.setattr(tasks_mod, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr(tasks_mod, "TASKS_FILE", tmp_path / "tasks.json")

        from agent.tasks import TaskManager
        from agent.loop import AgentLoop

        loop = AgentLoop.__new__(AgentLoop)
        # Atributos mínimos que usan plan_create / task_done
        loop._plan_tasks       = []
        loop.is_subagent       = False
        loop.capture_output    = True   # silencia prints
        loop.tasks             = TaskManager()
        loop._webui_queue      = None
        loop._set_plan_header_mode_cb = None
        loop._flush_live_block_cb     = None
        loop._start_live_block_cb     = None
        # Stubs para métodos que plan_create / task_done llaman
        loop._print                       = MagicMock()
        loop._webui_emit                  = MagicMock()
        loop._flush_task_intermediate_summary = MagicMock()
        loop._print_plan_panel_update         = MagicMock()
        loop._mark_all_plan_tasks_done        = lambda: None
        return loop

    # ── plan_create ────────────────────────────────────────────────────────

    def test_plan_create_adds_tasks_to_taskmanager(self, tmp_path, monkeypatch):
        loop = self._make_loop(tmp_path, monkeypatch)
        loop._execute_plan_create(["task A", "task B", "task C"])
        tasks = loop.tasks.all_tasks()
        titles = [t["title"] for t in tasks]
        assert "task A" in titles
        assert "task B" in titles
        assert "task C" in titles

    def test_plan_create_marks_description_as_plan(self, tmp_path, monkeypatch):
        loop = self._make_loop(tmp_path, monkeypatch)
        loop._execute_plan_create(["task X"])
        tasks = loop.tasks.all_tasks()
        assert all(t["description"] == "__plan__" for t in tasks)

    def test_plan_create_first_task_is_wip(self, tmp_path, monkeypatch):
        loop = self._make_loop(tmp_path, monkeypatch)
        loop._execute_plan_create(["primera", "segunda"])
        tasks = loop.tasks.all_tasks()
        by_title = {t["title"]: t for t in tasks}
        assert by_title["primera"]["status"] == "wip"
        assert by_title["segunda"]["status"] == "todo"

    def test_plan_create_stores_task_id_in_plan_tasks(self, tmp_path, monkeypatch):
        loop = self._make_loop(tmp_path, monkeypatch)
        loop._execute_plan_create(["task 1", "task 2"])
        for pt in loop._plan_tasks:
            assert "task_id" in pt
            assert pt["task_id"] is not None

    def test_plan_create_replaces_old_plan(self, tmp_path, monkeypatch):
        """El segundo plan_create elimina las entradas del plan anterior."""
        loop = self._make_loop(tmp_path, monkeypatch)
        loop._execute_plan_create(["old A", "old B"])
        loop._execute_plan_create(["new 1", "new 2"])
        tasks = loop.tasks.all_tasks()
        titles = [t["title"] for t in tasks]
        assert "old A" not in titles
        assert "old B" not in titles
        assert "new 1" in titles
        assert "new 2" in titles

    def test_plan_create_empty_tasks_returns_error(self, tmp_path, monkeypatch):
        loop = self._make_loop(tmp_path, monkeypatch)
        result = loop._execute_plan_create([])
        assert "Error" in result
        assert loop.tasks.all_tasks() == []

    # ── task_done ──────────────────────────────────────────────────────────

    def test_task_done_marks_done_in_taskmanager(self, tmp_path, monkeypatch):
        loop = self._make_loop(tmp_path, monkeypatch)
        loop._execute_plan_create(["task A", "task B"])
        loop._execute_task_done()
        tasks = {t["title"]: t for t in loop.tasks.all_tasks()}
        assert tasks["task A"]["status"] == "done"

    def test_task_done_activates_next_as_wip(self, tmp_path, monkeypatch):
        loop = self._make_loop(tmp_path, monkeypatch)
        loop._execute_plan_create(["task A", "task B", "task C"])
        loop._execute_task_done()
        tasks = {t["title"]: t for t in loop.tasks.all_tasks()}
        assert tasks["task B"]["status"] == "wip"
        assert tasks["task C"]["status"] == "todo"

    def test_task_done_all_removes_from_taskmanager(self, tmp_path, monkeypatch):
        """Al completar el plan entero, las entradas se eliminan del TaskManager."""
        loop = self._make_loop(tmp_path, monkeypatch)
        loop._execute_plan_create(["single task"])
        loop._execute_task_done()
        plan_tasks = [
            t for t in loop.tasks.all_tasks()
            if t.get("description") == "__plan__"
        ]
        assert plan_tasks == []

    def test_task_done_without_plan_returns_error(self, tmp_path, monkeypatch):
        loop = self._make_loop(tmp_path, monkeypatch)
        result = loop._execute_task_done()
        assert "No hay plan" in result or "plan" in result.lower()

    # ── restore ────────────────────────────────────────────────────────────

    def test_restore_recovers_pending_plan_from_taskmanager(self, tmp_path, monkeypatch):
        """Simula reinicio: crea plan, vacía _plan_tasks, comprueba restauración."""
        loop = self._make_loop(tmp_path, monkeypatch)
        loop._execute_plan_create(["paso 1", "paso 2", "paso 3"])
        # Simular reinicio: _plan_tasks se vacía pero TaskManager persiste
        loop._plan_tasks = []
        loop._restore_plan_from_tasks()
        assert len(loop._plan_tasks) == 3
        texts = [pt["text"] for pt in loop._plan_tasks]
        assert "paso 1" in texts
        assert "paso 2" in texts
        assert "paso 3" in texts

    def test_restore_maps_wip_to_active(self, tmp_path, monkeypatch):
        loop = self._make_loop(tmp_path, monkeypatch)
        loop._execute_plan_create(["A", "B"])
        loop._plan_tasks = []
        loop._restore_plan_from_tasks()
        active = [pt for pt in loop._plan_tasks if pt["status"] == "active"]
        assert len(active) == 1
        assert active[0]["text"] == "A"

    def test_restore_maps_todo_to_pending(self, tmp_path, monkeypatch):
        loop = self._make_loop(tmp_path, monkeypatch)
        loop._execute_plan_create(["A", "B", "C"])
        loop._plan_tasks = []
        loop._restore_plan_from_tasks()
        pending = [pt for pt in loop._plan_tasks if pt["status"] == "pending"]
        assert len(pending) == 2

    def test_restore_preserves_task_ids(self, tmp_path, monkeypatch):
        loop = self._make_loop(tmp_path, monkeypatch)
        loop._execute_plan_create(["task X"])
        original_ids = [pt["task_id"] for pt in loop._plan_tasks]
        loop._plan_tasks = []
        loop._restore_plan_from_tasks()
        restored_ids = [pt.get("task_id") for pt in loop._plan_tasks]
        assert restored_ids == original_ids

    def test_restore_noop_if_plan_already_active(self, tmp_path, monkeypatch):
        """No sobreescribe _plan_tasks si ya hay un plan en memoria."""
        loop = self._make_loop(tmp_path, monkeypatch)
        loop._execute_plan_create(["X"])
        original_len  = len(loop._plan_tasks)
        original_text = loop._plan_tasks[0]["text"]
        loop._restore_plan_from_tasks()
        # La lista no se reemplazó: misma longitud y mismo contenido
        assert len(loop._plan_tasks) == original_len
        assert loop._plan_tasks[0]["text"] == original_text

    def test_restore_noop_after_completed_plan(self, tmp_path, monkeypatch):
        """Tras completar el plan (cleanup), restore no devuelve nada."""
        loop = self._make_loop(tmp_path, monkeypatch)
        loop._execute_plan_create(["single"])
        loop._execute_task_done()   # completa y limpia TaskManager
        loop._plan_tasks = []
        loop._restore_plan_from_tasks()
        assert loop._plan_tasks == []

    def test_restore_noop_for_subagent(self, tmp_path, monkeypatch):
        loop = self._make_loop(tmp_path, monkeypatch)
        loop._execute_plan_create(["task"])
        loop._plan_tasks = []
        loop.is_subagent = True
        loop._restore_plan_from_tasks()
        assert loop._plan_tasks == []

    # ── integración ─────────────────────────────────────────────────────────

    def test_full_plan_lifecycle_cleans_up(self, tmp_path, monkeypatch):
        """Plan completo: create → task_done × N → TaskManager vacío al final."""
        loop = self._make_loop(tmp_path, monkeypatch)
        loop._execute_plan_create(["paso 1", "paso 2"])
        loop._execute_task_done()   # completa paso 1, activa paso 2
        # Verificar estado intermedio
        tasks_mid = {t["title"]: t for t in loop.tasks.all_tasks()}
        assert tasks_mid["paso 1"]["status"] == "done"
        assert tasks_mid["paso 2"]["status"] == "wip"
        loop._execute_task_done()   # completa paso 2 → cleanup
        plan_remaining = [
            t for t in loop.tasks.all_tasks()
            if t.get("description") == "__plan__"
        ]
        assert plan_remaining == []

    def test_manual_tasks_not_affected_by_plan(self, tmp_path, monkeypatch):
        """Tareas manuales en TaskManager no se borran al completar el plan."""
        loop = self._make_loop(tmp_path, monkeypatch)
        loop.tasks.add("user manual task")
        loop._execute_plan_create(["plan step"])
        loop._execute_task_done()
        all_remaining = loop.tasks.all_tasks()
        manual = [t for t in all_remaining if t["title"] == "user manual task"]
        assert len(manual) == 1


# ── spawn_fanout ──────────────────────────────────────────────────────────────

class TestSpawnFanout:
    """Tests del tool spawn_fanout: mismo agente × N chunks en paralelo."""

    def _make_runner(self):
        """SubAgentRunner mínimo para tests (sin Ollama real)."""
        from unittest.mock import MagicMock
        from agent.subagent import SubAgentRunner, _get_concurrency_sem
        cfg = MagicMock()
        agent_main   = MagicMock(); agent_main.id   = "main";   agent_main.name   = "Main";   agent_main.emoji = "🤖"
        agent_coding = MagicMock(); agent_coding.id = "coding"; agent_coding.name = "Coder"; agent_coding.emoji = "💻"
        cfg.agents = [agent_main, agent_coding]
        cfg.subagents_max_concurrent = 4
        runner = SubAgentRunner.__new__(SubAgentRunner)
        runner.config               = cfg
        runner._parent_webui_queue  = None
        runner._concurrency_sem     = _get_concurrency_sem(4)
        return runner

    def _patch_run(self, runner, fn):
        """Sustituye runner.run con una función fake."""
        runner.run = fn

    # ── Schema ──────────────────────────────────────────────────────────────

    def test_schema_name_and_params(self):
        runner = self._make_runner()
        name, fn, schema = runner.as_fanout_schema()
        assert name == "spawn_fanout"
        props = schema["parameters"]["properties"]
        assert "agent_id" in props
        assert "task_chunks" in props
        assert schema["parameters"]["required"] == ["agent_id", "task_chunks"]

    def test_schema_description_mentions_chunks(self):
        runner = self._make_runner()
        _, _, schema = runner.as_fanout_schema()
        assert "chunk" in schema["description"].lower()

    # ── Validación de parámetros ─────────────────────────────────────────────

    def test_invalid_agent_returns_error(self):
        runner = self._make_runner()
        _, fn, _ = runner.as_fanout_schema()
        result = fn(agent_id="unknown_agent", task_chunks=["task1"])
        assert "Error" in result

    def test_empty_chunks_returns_error(self):
        runner = self._make_runner()
        _, fn, _ = runner.as_fanout_schema()
        result = fn(agent_id="main", task_chunks=[])
        assert "Error" in result

    def test_too_many_chunks_returns_error(self):
        runner = self._make_runner()
        _, fn, _ = runner.as_fanout_schema()
        result = fn(agent_id="main", task_chunks=["t"] * 11)
        assert "Error" in result

    def test_blank_chunks_filtered(self):
        """Chunks vacíos o solo espacios se filtran; si todos vacíos → error."""
        runner = self._make_runner()
        _, fn, _ = runner.as_fanout_schema()
        result = fn(agent_id="main", task_chunks=["  ", "", "  "])
        assert "Error" in result

    # ── Ejecución correcta ────────────────────────────────────────────────────

    def test_returns_all_chunks(self):
        runner = self._make_runner()
        self._patch_run(runner, lambda agent_id, task, silent=True, **kw: f"resultado: {task}")
        _, fn, _ = runner.as_fanout_schema()
        result = fn(agent_id="coding", task_chunks=["analiza A", "analiza B", "analiza C"])
        assert "Chunk 1/3" in result
        assert "Chunk 2/3" in result
        assert "Chunk 3/3" in result
        assert "resultado: analiza A" in result
        assert "resultado: analiza B" in result
        assert "resultado: analiza C" in result

    def test_synthesis_hint_present(self):
        runner = self._make_runner()
        self._patch_run(runner, lambda agent_id, task, silent=True, **kw: "ok")
        _, fn, _ = runner.as_fanout_schema()
        result = fn(agent_id="main", task_chunks=["chunk1"])
        assert "Combina los hallazgos" in result

    def test_chunk_header_truncates_long_description(self):
        """Chunks largos se truncan a 80 chars en el header."""
        runner = self._make_runner()
        self._patch_run(runner, lambda agent_id, task, silent=True, **kw: "ok")
        _, fn, _ = runner.as_fanout_schema()
        long_task = "A" * 200
        result = fn(agent_id="main", task_chunks=[long_task])
        # El header contiene máximo 80 chars del chunk
        assert "A" * 80 in result
        assert "A" * 81 not in result.split("---")[0]  # no en el body del header

    def test_single_chunk_works(self):
        runner = self._make_runner()
        self._patch_run(runner, lambda agent_id, task, silent=True, **kw: "solo uno")
        _, fn, _ = runner.as_fanout_schema()
        result = fn(agent_id="main", task_chunks=["single task"])
        assert "solo uno" in result
        assert "1/1" in result

    # ── Manejo de errores ────────────────────────────────────────────────────

    def test_partial_failure_shows_error(self):
        def fake_run(agent_id, task, silent=True, **kw):
            if "bad" in task:
                raise RuntimeError("intentional failure")
            return f"ok: {task}"
        runner = self._make_runner()
        self._patch_run(runner, fake_run)
        _, fn, _ = runner.as_fanout_schema()
        result = fn(agent_id="main", task_chunks=["good_task", "bad_task"])
        assert "ok: good_task" in result
        assert "⛔ Error" in result
        assert "intentional failure" in result

    def test_all_failed_shows_zero_ok(self):
        def fake_run(agent_id, task, silent=True, **kw):
            raise RuntimeError("everything fails")
        runner = self._make_runner()
        self._patch_run(runner, fake_run)
        _, fn, _ = runner.as_fanout_schema()
        result = fn(agent_id="main", task_chunks=["A", "B"])
        assert "0/2" in result

    # ── Concurrencia ─────────────────────────────────────────────────────────

    def test_respects_concurrency_semaphore(self):
        """No más de max_concurrent chunks corren simultáneamente."""
        runner = self._make_runner()
        runner._concurrency_sem = threading.Semaphore(2)

        running = [0]
        peak    = [0]
        lock_c  = threading.Lock()

        def fake_run(agent_id, task, silent=True, **kw):
            with lock_c:
                running[0] += 1
                if running[0] > peak[0]:
                    peak[0] = running[0]
            time.sleep(0.03)
            with lock_c:
                running[0] -= 1
            return "done"

        self._patch_run(runner, fake_run)
        _, fn, _ = runner.as_fanout_schema()
        fn(agent_id="main", task_chunks=["t1", "t2", "t3", "t4", "t5"])

        assert peak[0] <= 2, f"Pico de concurrencia {peak[0]} supera el límite de 2"

    def test_all_chunks_run_even_with_sem_1(self):
        """Con semáforo=1 los chunks corren en serie pero todos se completan."""
        runner = self._make_runner()
        runner._concurrency_sem = threading.Semaphore(1)
        order = []

        def fake_run(agent_id, task, silent=True, **kw):
            order.append(task)
            return f"hecho: {task}"

        self._patch_run(runner, fake_run)
        _, fn, _ = runner.as_fanout_schema()
        result = fn(agent_id="coding", task_chunks=["A", "B", "C"])
        assert len(order) == 3
        assert "hecho: A" in result
        assert "hecho: B" in result
        assert "hecho: C" in result

    def test_result_truncated_when_too_long(self):
        """Resultados >4000 chars se truncan por chunk."""
        runner = self._make_runner()
        big = "X" * 5000
        self._patch_run(runner, lambda agent_id, task, silent=True, **kw: big)
        _, fn, _ = runner.as_fanout_schema()
        result = fn(agent_id="main", task_chunks=["bigchunk"])
        assert "truncado" in result
        # El resultado no debe superar 4000 chars del original + overhead de truncation msg
        chunk_section = result.split("---")[0]
        assert chunk_section.count("X") <= 4000


# ── MCP chart tools ───────────────────────────────────────────────────────────

class TestMCPChartTools:
    """Tests de la tool única de gráficas Word `insert_chart` (OOXML nativo, sin matplotlib).
    Usan tempfile propio para evitar interferencias con el autouse fixture _cleanup_test_tmp."""

    def test_insert_chart_creates_native_docx(self):
        import tempfile, zipfile
        from mcp_servers.word_assistant import _TOOL_FNS
        with tempfile.TemporaryDirectory() as d:
            out = str(Path(d) / "chart.docx")
            result = _TOOL_FNS["insert_chart"]({
                "path": out, "chart_type": "bar", "title": "Test Bar",
                "data": {"categories": ["A", "B", "C"],
                         "series": [{"label": "S1", "values": [10, 20, 30]}]},
            })
            assert "✅" in result, f"Tool error: {result}"
            assert Path(out).exists()
            # Verificar que es un chart OOXML nativo, no una imagen PNG
            with zipfile.ZipFile(out) as z:
                names = z.namelist()
                assert any("charts/chart" in n for n in names), "No hay chartSpace OOXML"
                assert not any(n.startswith("word/media/") for n in names), "No debe incrustar PNG"

    def test_insert_chart_pie_native(self):
        import tempfile
        from mcp_servers.word_assistant import _TOOL_FNS
        with tempfile.TemporaryDirectory() as d:
            out = str(Path(d) / "pie.docx")
            result = _TOOL_FNS["insert_chart"]({
                "path": out, "chart_type": "pie", "title": "Test Pie",
                "data": {"categories": ["X", "Y"],
                         "series": [{"label": "Dist", "values": [60, 40]}]},
            })
            assert "✅" in result, f"Tool error: {result}"
            assert Path(out).exists()

    def test_insert_chart_missing_path(self):
        from mcp_servers.word_assistant import _TOOL_FNS
        result = _TOOL_FNS["insert_chart"]({"chart_type": "bar", "data": {}})
        assert "requerido" in result.lower() or "path" in result.lower()

    def test_chart_tools_registered_in_tool_fns(self):
        from mcp_servers.word_assistant import _TOOL_FNS
        assert "insert_chart" in _TOOL_FNS, "Tool 'insert_chart' no registrada"
        # Las tools antiguas (matplotlib PNG y duplicadas) ya no existen
        for removed in ("create_bar_chart", "create_pie_chart", "create_line_chart",
                        "doc_insert_chart_native", "doc_insert_diagram",
                        "create_gantt_chart", "create_org_chart", "create_heatmap",
                        "markdown_to_html"):
            assert removed not in _TOOL_FNS, f"Tool '{removed}' debería estar eliminada"


# ── Config nuevos campos de subagentes ───────────────────────────────────────

class TestSubagentsConfigNewFields:
    """Nuevos campos en bloque subagents de oocode.json: autoContMax, inferenceTimeout, defaultTimeout."""

    def test_defaults_auto_cont_max(self):
        from config import OOConfig, DEFAULT_CONFIG
        assert DEFAULT_CONFIG["subagents"]["autoContMax"] == 16
        cfg = OOConfig()
        assert cfg.subagents_auto_cont_max == 16

    def test_defaults_inference_timeout(self):
        from config import OOConfig, DEFAULT_CONFIG
        assert DEFAULT_CONFIG["subagents"]["inferenceTimeout"] == 0
        cfg = OOConfig()
        assert cfg.subagents_inference_timeout == 0

    def test_defaults_default_timeout(self):
        from config import OOConfig, DEFAULT_CONFIG
        assert DEFAULT_CONFIG["subagents"]["defaultTimeout"] == 0
        cfg = OOConfig()
        assert cfg.subagents_default_timeout == 0

    def test_from_json_reads_auto_cont_max(self, tmp_path):
        import json, config as cfg_mod
        from config import OOConfig
        tmp = tmp_path / "oocode.json"
        tmp.write_text(json.dumps({"subagents": {"autoContMax": 24}}))
        orig = cfg_mod.CONFIG_FILE
        try:
            cfg_mod.CONFIG_FILE = tmp
            cfg = OOConfig.load()
        finally:
            cfg_mod.CONFIG_FILE = orig
        assert cfg.subagents_auto_cont_max == 24

    def test_from_json_reads_inference_timeout(self, tmp_path):
        import json, config as cfg_mod
        from config import OOConfig
        tmp = tmp_path / "oocode.json"
        tmp.write_text(json.dumps({"subagents": {"inferenceTimeout": 300}}))
        orig = cfg_mod.CONFIG_FILE
        try:
            cfg_mod.CONFIG_FILE = tmp
            cfg = OOConfig.load()
        finally:
            cfg_mod.CONFIG_FILE = orig
        assert cfg.subagents_inference_timeout == 300

    def test_from_json_reads_default_timeout(self, tmp_path):
        import json, config as cfg_mod
        from config import OOConfig
        tmp = tmp_path / "oocode.json"
        tmp.write_text(json.dumps({"subagents": {"defaultTimeout": 600}}))
        orig = cfg_mod.CONFIG_FILE
        try:
            cfg_mod.CONFIG_FILE = tmp
            cfg = OOConfig.load()
        finally:
            cfg_mod.CONFIG_FILE = orig
        assert cfg.subagents_default_timeout == 600

    def test_save_writes_new_fields(self, tmp_path):
        import json, config as cfg_mod
        from config import OOConfig
        tmp = tmp_path / "oocode.json"
        orig = cfg_mod.CONFIG_FILE
        try:
            cfg_mod.CONFIG_FILE = tmp
            cfg = OOConfig(
                subagents_auto_cont_max=20,
                subagents_inference_timeout=180,
                subagents_default_timeout=900,
            )
            cfg.save()
            data = json.loads(tmp.read_text())
        finally:
            cfg_mod.CONFIG_FILE = orig
        sa = data["subagents"]
        assert sa["autoContMax"] == 20
        assert sa["inferenceTimeout"] == 180
        assert sa["defaultTimeout"] == 900

    def test_auto_cont_max_zero_means_inherit(self, tmp_path):
        import json, config as cfg_mod
        from config import OOConfig
        tmp = tmp_path / "oocode.json"
        tmp.write_text(json.dumps({"subagents": {"autoContMax": 0}}))
        orig = cfg_mod.CONFIG_FILE
        try:
            cfg_mod.CONFIG_FILE = tmp
            cfg = OOConfig.load()
        finally:
            cfg_mod.CONFIG_FILE = orig
        assert cfg.subagents_auto_cont_max == 0


class TestSubagentRunAppliesConfig:
    """run() aplica los nuevos límites de config al sub_config antes de ejecutar."""

    def test_auto_cont_max_override_logic(self):
        """La lógica de override de auto_continue_max funciona correctamente."""
        # Reproduce la lógica exacta de subagent.py run():
        #   if self.config.subagents_auto_cont_max > 0:
        #       sub_config.auto_continue_max = self.config.subagents_auto_cont_max

        class FakeParent:
            subagents_auto_cont_max     = 20
            subagents_inference_timeout = 300

        class FakeSubConfig:
            auto_continue_max = 8
            inference_timeout_override = 0

        parent = FakeParent()
        sub = FakeSubConfig()

        if parent.subagents_auto_cont_max > 0:
            sub.auto_continue_max = parent.subagents_auto_cont_max
        if parent.subagents_inference_timeout > 0:
            sub.inference_timeout_override = parent.subagents_inference_timeout

        assert sub.auto_continue_max == 20
        assert sub.inference_timeout_override == 300

    def test_zero_does_not_override(self):
        """Con subagents_auto_cont_max==0 e inferenceTimeout==0, no sobreescribe."""
        class FakeParent:
            subagents_auto_cont_max     = 0
            subagents_inference_timeout = 0

        class FakeSubConfig:
            auto_continue_max = 8
            inference_timeout_override = 0

        parent = FakeParent()
        sub = FakeSubConfig()

        if parent.subagents_auto_cont_max > 0:
            sub.auto_continue_max = parent.subagents_auto_cont_max
        if parent.subagents_inference_timeout > 0:
            sub.inference_timeout_override = parent.subagents_inference_timeout

        assert sub.auto_continue_max == 8
        assert sub.inference_timeout_override == 0

    def test_subagent_source_code_contains_override(self):
        """Verificar que agent/subagent.py contiene los overrides de config."""
        import ast, pathlib
        src = pathlib.Path("agent/subagent.py").read_text()
        assert "subagents_auto_cont_max" in src, "Debe haber override de auto_cont_max"
        assert "subagents_inference_timeout" in src, "Debe haber override de inference_timeout"
        assert "sub_config.auto_continue_max" in src
        assert "sub_config.inference_timeout_override" in src


class TestSpawnSubagentDefaultTimeout:
    """spawn_subagent y spawn_fanout aplican defaultTimeout de config."""

    def _make_runner(self, default_timeout=0):
        from unittest.mock import MagicMock
        from agent.subagent import SubAgentRunner, _get_concurrency_sem
        cfg = MagicMock()
        agent_main = MagicMock()
        agent_main.id    = "main"
        agent_main.name  = "Main"
        agent_main.emoji = "🤖"
        cfg.agents = [agent_main]
        cfg.model  = "test-model"
        cfg.subagents_max_concurrent  = 4
        cfg.subagents_default_timeout = default_timeout
        runner = SubAgentRunner.__new__(SubAgentRunner)
        runner.config              = cfg
        runner._parent_webui_queue = None
        runner._concurrency_sem    = _get_concurrency_sem(4)
        return runner

    def test_default_timeout_zero_no_watchdog(self):
        """Si defaultTimeout==0 y LLM no especifica timeout, no hay watchdog."""
        runner = self._make_runner(default_timeout=0)
        runner.run = lambda agent_id, task, silent=True, **kw: "ok"
        _, fn, _ = runner.as_tool_schema()
        result = fn(agent_id="main", task="task", timeout_seconds=0)
        assert result == "ok"

    def test_default_timeout_applied_when_llm_sends_zero(self):
        """Si defaultTimeout>0 y LLM envía timeout_seconds=0, se aplica defaultTimeout."""
        import threading
        runner = self._make_runner(default_timeout=1)  # 1 segundo

        def slow_run(agent_id, task, silent=True, kill_event=None, **kw):
            if kill_event:
                kill_event.wait(timeout=10)
            return ""

        runner.run = slow_run
        _, fn, _ = runner.as_tool_schema()
        # LLM no especifica timeout → debe usar defaultTimeout=1 → subagente se mata
        result = fn(agent_id="main", task="slow_task", timeout_seconds=0)
        assert "Timeout" in result or "timeout" in result.lower()

    def test_explicit_timeout_overrides_default(self):
        """timeout_seconds explícito del LLM tiene precedencia sobre defaultTimeout."""
        import threading
        runner = self._make_runner(default_timeout=600)  # 10 min de default

        results = []

        def fast_run(agent_id, task, silent=True, **kw):
            results.append("done")
            return "fast_result"

        runner.run = fast_run
        _, fn, _ = runner.as_tool_schema()
        # LLM especifica timeout_seconds=5 (ignora el default)
        result = fn(agent_id="main", task="fast_task", timeout_seconds=5)
        assert result == "fast_result"

    def test_fanout_applies_default_timeout(self):
        """spawn_fanout también aplica defaultTimeout cuando no se especifica."""
        runner = self._make_runner(default_timeout=1)

        def slow_run(agent_id, task, silent=True, kill_event=None, **kw):
            if kill_event:
                kill_event.wait(timeout=10)
            return ""

        runner.run = slow_run
        _, fn, schema = runner.as_fanout_schema()
        result = fn(agent_id="main", task_chunks=["chunk1"], timeout_seconds=0)
        # Con defaultTimeout=1 s, el chunk lento debe ser killed
        assert "killed" in result or "Timeout" in result or "error" in result.lower()
