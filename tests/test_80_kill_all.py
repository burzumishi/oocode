"""Tests para /kill y /kill all: matar turno + subagentes + equipos al momento.

Cubre:
- AgentLoop.request_kill(): marca _kill_requested, aborta el LLM en vuelo
  (_close_stream_connection → kill_stream) y mata subagentes (kill_all).
- Team.execute(): registra cada miembro de equipo con kill_event para que kill_all
  pueda matarlo (antes los miembros de equipo eran inmatables).
- kill_all() alcanza a un miembro de equipo registrado y lo desbloquea.
"""
import os
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── AgentLoop.request_kill ─────────────────────────────────────────────────────

class TestRequestKill:
    def _make_loop(self, runner=None):
        from agent.loop import AgentLoop
        loop = AgentLoop.__new__(AgentLoop)
        loop._kill_requested = False
        loop._client_needs_rebuild = False
        loop.client = MagicMock()
        loop.subagent_runner = runner
        return loop

    def test_sets_flag_and_aborts_llm(self):
        loop = self._make_loop(runner=None)
        summary = loop.request_kill()
        assert loop._kill_requested is True
        # _close_stream_connection → kill_stream() (cierre forzado del socket del LLM)
        loop.client.kill_stream.assert_called_once()
        assert loop._client_needs_rebuild is True
        assert summary["subagents"] == 0

    def test_kills_subagents_via_runner(self):
        runner = MagicMock()
        runner.kill_all.return_value = 4
        loop = self._make_loop(runner=runner)
        summary = loop.request_kill()
        runner.kill_all.assert_called_once()
        assert summary["subagents"] == 4

    def test_tolerant_to_runner_error(self):
        runner = MagicMock()
        runner.kill_all.side_effect = RuntimeError("boom")
        loop = self._make_loop(runner=runner)
        summary = loop.request_kill()   # no debe propagar
        assert loop._kill_requested is True
        assert summary["subagents"] == 0


# ── AgentLoop.kill_all_extras — parte extra de /kill all ───────────────────────

class TestKillAllExtras:
    def _make_loop(self, scheduler=None, tasks=None):
        from agent.loop import AgentLoop
        loop = AgentLoop.__new__(AgentLoop)
        loop.scheduler = scheduler
        loop.tasks = tasks
        return loop

    def test_disables_enabled_jobs_and_resets_wip(self):
        sched = MagicMock()
        sched.all_jobs.return_value = [
            {"id": "j1", "enabled": True},
            {"id": "j2", "enabled": False},   # ya deshabilitado → no se toca
            {"id": "j3", "enabled": True},
        ]
        tasks = MagicMock()
        tasks.all_tasks.return_value = [{"id": "t1"}, {"id": "t2"}]
        loop = self._make_loop(scheduler=sched, tasks=tasks)

        out = loop.kill_all_extras()

        assert out == {"jobs": 2, "wip": 2}
        assert sched.toggle.call_count == 2
        sched.toggle.assert_any_call("j1")
        sched.toggle.assert_any_call("j3")
        tasks.all_tasks.assert_called_once_with(status="wip")
        assert tasks.update.call_count == 2
        tasks.update.assert_any_call("t1", status="todo")

    def test_no_scheduler_no_tasks(self):
        loop = self._make_loop(scheduler=None, tasks=None)
        assert loop.kill_all_extras() == {"jobs": 0, "wip": 0}

    def test_tolerant_to_errors(self):
        sched = MagicMock()
        sched.all_jobs.side_effect = RuntimeError("boom")
        tasks = MagicMock()
        tasks.all_tasks.side_effect = RuntimeError("boom")
        loop = self._make_loop(scheduler=sched, tasks=tasks)
        assert loop.kill_all_extras() == {"jobs": 0, "wip": 0}


# ── Team.execute — miembros de equipo killables ────────────────────────────────

class TestTeamMembersKillable:
    def _clear_registry(self):
        from agent import subagent as sa
        with sa._registry_lock:
            sa._registry.clear()

    def test_member_registered_with_kill_event(self, tmp_path):
        """Durante la ejecución, el miembro está en _registry y su run() recibe la
        kill_event + sub_ref correctos."""
        from agent.tasks import AgentTeam
        from agent import subagent as sa
        self._clear_registry()
        captured = {}

        class R:
            config = SimpleNamespace(
                agents=[SimpleNamespace(id="coding", name="Coder", emoji="💻")]
            )
            def run(self, agent_id, task, silent=True, kill_event=None, sub_ref=None):
                captured["in_registry"] = (
                    sub_ref is not None
                    and sa.get_by_prefix(sub_ref.run_id[:6]) is not None
                )
                captured["kill_event_wired"] = (
                    kill_event is not None and sub_ref.kill_event is kill_event
                )
                captured["emoji"] = sub_ref.agent_emoji if sub_ref else None
                return "ok"

        team = AgentTeam("tk1", "coding", ["coding"], str(tmp_path / "t.json"))
        team.add_subtask("hazlo", "coding")
        team.execute(R())

        assert captured.get("in_registry") is True
        assert captured.get("kill_event_wired") is True
        assert captured.get("emoji") == "💻"
        self._clear_registry()

    def test_kill_all_unblocks_team_member(self, tmp_path):
        """kill_all() pone la kill_event del miembro → su run() (que la espera) sale."""
        from agent.tasks import AgentTeam
        from agent.subagent import SubAgentRunner
        from agent import subagent as sa
        self._clear_registry()
        observed = {}

        class R:
            config = SimpleNamespace(
                agents=[SimpleNamespace(id="coding", name="Coder", emoji="💻")]
            )
            def run(self, agent_id, task, silent=True, kill_event=None, sub_ref=None):
                # Simula trabajo bloqueante hasta que lo maten.
                fired = kill_event.wait(timeout=3.0)
                observed["fired"] = fired
                if fired:
                    sub_ref.status = "killed"
                return "partial"

        team = AgentTeam("tk2", "coding", ["coding"], str(tmp_path / "t.json"))
        team.add_subtask("bucle", "coding")

        t = threading.Thread(target=team.execute, args=(R(),), daemon=True)
        t.start()

        # Esperar a que el miembro aparezca en el registro
        deadline = time.time() + 2.0
        while time.time() < deadline and not sa.list_running():
            time.sleep(0.02)
        assert sa.list_running(), "el miembro de equipo no se registró"

        # kill_all() solo usa el _registry global (ignora self)
        n = SubAgentRunner.kill_all(None)
        assert n >= 1

        t.join(timeout=3.0)
        assert not t.is_alive(), "execute() no terminó tras kill_all"
        assert observed.get("fired") is True
        self._clear_registry()
