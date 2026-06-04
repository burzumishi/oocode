"""Tests para botón Kill, endpoint /api/chat/kill y multi-tarea en WebUI.

Sin Ollama ni proceso externo.
"""
import json
import queue
import threading
import time
import unittest
from unittest.mock import MagicMock, patch


# ── /api/chat/kill endpoint ───────────────────────────────────────────────────

class TestApiChatKill(unittest.TestCase):

    def _make_client(self):
        from webui.app import app as _app
        _app.config["TESTING"]    = True
        _app.config["SECRET_KEY"] = "test-secret"
        return _app.test_client()

    def _inject_session(self, sid, loop, q):
        # El endpoint mete el retorno de request_kill()/kill_all_extras() en jsonify,
        # así que los mocks deben devolver dicts reales (un MagicMock no es serializable).
        if isinstance(loop, MagicMock):
            loop.request_kill.return_value   = {"subagents": 0}
            loop.kill_all_extras.return_value = {"jobs": 0, "wip": 0}
        from webui.sessions import _WEBUI_SESSIONS
        _WEBUI_SESSIONS[sid] = {
            "loop":    loop,
            "queue":   q,
            "history": [],
            "lock":    threading.Lock(),
            "thread":  None,
        }

    def test_kill_no_session_returns_404(self):
        """Sin sesión registrada → 404."""
        with self._make_client() as c:
            with patch("webui.helpers._get_or_create_sid", return_value="no_session_xyz"), \
                 patch("webui.api_chat._get_or_create_sid", return_value="no_session_xyz"):
                resp = c.post("/api/chat/kill")
        self.assertEqual(resp.status_code, 404)

    def test_kill_delegates_to_request_kill(self):
        """El endpoint delega en loop.request_kill() (que marca _kill_requested,
        aborta el LLM en vuelo y mata subagentes vía kill_all)."""
        from webui.sessions import _WEBUI_SESSIONS
        sid  = "test_kill_sid_001"
        q    = queue.SimpleQueue()
        loop = MagicMock()
        self._inject_session(sid, loop, q)

        with self._make_client() as c:
            with patch("webui.api_chat._get_or_create_sid", return_value=sid):
                resp = c.post("/api/chat/kill")

        data = json.loads(resp.data)
        self.assertTrue(data.get("ok"), f"Expected ok, got: {data}")
        loop.request_kill.assert_called_once()
        _WEBUI_SESSIONS.pop(sid, None)

    def test_kill_emits_done_event(self):
        from webui.sessions import _WEBUI_SESSIONS
        sid  = "test_kill_sid_002"
        q    = queue.SimpleQueue()
        loop = MagicMock()
        loop._kill_requested = False
        self._inject_session(sid, loop, q)

        with self._make_client() as c:
            with patch("webui.api_chat._get_or_create_sid", return_value=sid), \
                 patch("agent.subagent.list_running", return_value=[]):
                c.post("/api/chat/kill")

        ev = q.get_nowait()
        self.assertEqual(ev.get("type"), "done")
        _WEBUI_SESSIONS.pop(sid, None)

    def test_kill_cancels_subagents_via_request_kill(self):
        """La cancelación de subagentes ahora la hace request_kill()→kill_all() (cubierto
        en test_80). Aquí basta verificar que el endpoint la invoca."""
        from webui.sessions import _WEBUI_SESSIONS
        sid  = "test_kill_sid_003"
        q    = queue.SimpleQueue()
        loop = MagicMock()
        self._inject_session(sid, loop, q)

        with self._make_client() as c:
            with patch("webui.api_chat._get_or_create_sid", return_value=sid):
                c.post("/api/chat/kill")

        loop.request_kill.assert_called_once()
        _WEBUI_SESSIONS.pop(sid, None)

    def test_kill_invokes_kill_all_extras(self):
        """Paridad con /kill all: el endpoint también deshabilita scheduler + wip vía
        loop.kill_all_extras()."""
        from webui.sessions import _WEBUI_SESSIONS
        sid  = "test_kill_sid_extras"
        q    = queue.SimpleQueue()
        loop = MagicMock()
        self._inject_session(sid, loop, q)

        with self._make_client() as c:
            with patch("webui.api_chat._get_or_create_sid", return_value=sid):
                c.post("/api/chat/kill")

        loop.request_kill.assert_called_once()
        loop.kill_all_extras.assert_called_once()
        _WEBUI_SESSIONS.pop(sid, None)

    def test_kill_returns_summary(self):
        """El JSON de respuesta reporta subagentes/jobs/wip matados (para el aviso UI)."""
        from webui.sessions import _WEBUI_SESSIONS
        sid  = "test_kill_sid_summary"
        q    = queue.SimpleQueue()
        loop = MagicMock()
        self._inject_session(sid, loop, q)
        loop.request_kill.return_value    = {"subagents": 3}
        loop.kill_all_extras.return_value = {"jobs": 2, "wip": 5}

        with self._make_client() as c:
            with patch("webui.api_chat._get_or_create_sid", return_value=sid):
                resp = c.post("/api/chat/kill")

        data = json.loads(resp.data)
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("subagents"), 3)
        self.assertEqual(data.get("jobs"), 2)
        self.assertEqual(data.get("wip"), 5)
        _WEBUI_SESSIONS.pop(sid, None)

    def test_kill_route_registered(self):
        from webui.app import app as _app
        rules = [r.rule for r in _app.url_map.iter_rules()]
        self.assertIn("/api/chat/kill", rules)


# ── page_chat: Kill button UI ─────────────────────────────────────────────────

class TestPageChatKillButton(unittest.TestCase):

    def _src(self):
        from webui.app import app as _app
        _app.config["TESTING"] = True
        _app.config["SECRET_KEY"] = "test-secret"
        with _app.test_client() as c:
            return c.get("/chat").data.decode("utf-8", errors="replace")

    def test_kill_button_present(self):
        self.assertIn("tui-kill", self._src())

    def test_kill_button_calls_endpoint(self):
        src = self._src()
        self.assertIn("/api/chat/kill", src)
        self.assertIn("killAgent", src)

    def test_kill_button_hidden_by_default(self):
        src = self._src()
        # El botón debe tener display:none por defecto
        self.assertIn("display:none", src)
        self.assertIn("tui-kill-btn", src)

    def test_set_busy_shows_kill_button(self):
        src = self._src()
        # setBusy debe gestionar la visibilidad del botón kill
        self.assertIn("tui-kill", src)
        # setBusy debe mostrar el botón cuando busy=true
        idx_kill = src.find("kill.style.display = busy")
        self.assertGreater(idx_kill, 0, "setBusy debe controlar kill.style.display")

    def test_kill_css_class_present(self):
        self.assertIn("tui-kill-btn", self._src())


# ── page_chat: subagente plan/tool events ─────────────────────────────────────

class TestPageChatSubagentMultitask(unittest.TestCase):

    def _src(self):
        from webui.app import app as _app
        _app.config["TESTING"] = True
        _app.config["SECRET_KEY"] = "test-secret"
        with _app.test_client() as c:
            return c.get("/chat").data.decode("utf-8", errors="replace")

    def test_subagent_plan_handler(self):
        src = self._src()
        self.assertIn("appendSubagentPlan", src)

    def test_subagent_tool_start_handler(self):
        src = self._src()
        self.assertIn("appendSubagentToolStart", src)

    def test_subagent_tool_done_handler(self):
        src = self._src()
        self.assertIn("appendSubagentToolDone", src)

    def test_plan_event_checks_subagent_flag(self):
        src = self._src()
        # El handler 'plan' debe ramificar por ev.subagent
        self.assertIn("ev.subagent", src)

    def test_tool_start_event_checks_subagent_flag(self):
        src = self._src()
        # El handler 'tool_start' también debe ramificar
        self.assertIn("appendSubagentToolStart", src)

    def test_subagent_plan_no_finish_tool_block(self):
        """Los planes de subagentes no deben llamar _finishToolBlock()."""
        src = self._src()
        # La función appendSubagentPlan no debe contener _finishToolBlock
        idx_fn  = src.find("function appendSubagentPlan")
        idx_end = src.find("\nfunction ", idx_fn + 1)
        fn_body = src[idx_fn:idx_end] if idx_end > idx_fn else src[idx_fn:idx_fn+500]
        self.assertNotIn("_finishToolBlock", fn_body)

    def test_subagent_plan_shows_tasks(self):
        """appendSubagentPlan muestra tasks numeradas."""
        src = self._src()
        idx = src.find("function appendSubagentPlan")
        self.assertGreater(idx, 0)
        body = src[idx:idx+400]
        self.assertIn("tasks", body)
        # Ahora usa markdown (md variable) en lugar de array lines
        self.assertIn("appendSubagentText", body)

    def test_plan_normal_still_calls_finish_tool_block(self):
        """Los planes del agente principal siguen llamando _finishToolBlock()."""
        src = self._src()
        # En el handler 'plan', la rama non-subagent llama _finishToolBlock
        plan_handler_idx = src.find("case 'plan':")
        self.assertGreater(plan_handler_idx, 0)
        plan_handler_end = src.find("break;", plan_handler_idx)
        plan_handler     = src[plan_handler_idx:plan_handler_end]
        self.assertIn("_finishToolBlock", plan_handler)


# ── Integración: source check en loop.py para plan events de subagentes ───────

class TestLoopPlanEmitSubagent(unittest.TestCase):

    def test_plan_emit_uses_webui_emit(self):
        """_execute_plan_create usa _webui_emit (hereda el marker subagent)."""
        import inspect
        import agent.loop as _lp
        src = inspect.getsource(_lp.AgentLoop._execute_plan_create)
        self.assertIn("_webui_emit", src)

    def test_tool_start_emit_uses_webui_emit(self):
        """El tool_start WebUI también usa _webui_emit."""
        import inspect
        import agent.loop as _lp
        src = inspect.getsource(_lp.AgentLoop._show_tool_running_header)
        self.assertIn("_webui_emit", src)


if __name__ == "__main__":
    unittest.main()
