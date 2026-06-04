"""Tests para las mejoras de subagentes en WebUI.

Cubre:
- _webui_emit propaga marker subagent=True en AgentLoop.is_subagent
- stream_chunk pasa por _webui_emit (hereda marker)
- SubAgentRunner._parent_webui_queue propagado al loop del subagente
- /api/agents/<run_id>/output endpoint retorna resultado completo
- page_agents contiene las funciones showResult / showTask / closeModal
- page_chat contiene appendSubagentText y .tui-subagent-block CSS
- retry XML malformado (non-EOF)
"""
import json
import queue
import threading
import time
import unittest
from unittest.mock import MagicMock, patch


# ── _webui_emit: marker subagente ─────────────────────────────────────────────

class TestWebuiEmitSubagentMarker(unittest.TestCase):

    def _make_loop(self, is_subagent=False, agent_name="TestAgent",
                   agent_emoji="🤖") -> "AgentLoop":
        from agent.loop import AgentLoop
        cfg = MagicMock()
        cfg.agent_name  = agent_name
        cfg.agent_emoji = agent_emoji
        loop = AgentLoop.__new__(AgentLoop)
        loop.is_subagent  = is_subagent
        loop.config       = cfg
        loop._webui_queue = queue.SimpleQueue()
        return loop

    def test_non_subagent_no_marker(self):
        loop = self._make_loop(is_subagent=False)
        loop._webui_emit({"type": "text", "text": "hello"})
        ev = loop._webui_queue.get_nowait()
        self.assertNotIn("subagent", ev)

    def test_subagent_adds_marker(self):
        loop = self._make_loop(is_subagent=True, agent_name="Coding", agent_emoji="💻")
        loop._webui_emit({"type": "text", "text": "hello"})
        ev = loop._webui_queue.get_nowait()
        self.assertTrue(ev.get("subagent"))
        self.assertEqual(ev.get("subagent_name"),  "Coding")
        self.assertEqual(ev.get("subagent_emoji"), "💻")

    def test_subagent_does_not_mutate_original(self):
        loop = self._make_loop(is_subagent=True)
        original = {"type": "text", "text": "x"}
        loop._webui_emit(original)
        # original dict unchanged
        self.assertNotIn("subagent", original)

    def test_no_queue_is_noop(self):
        loop = self._make_loop(is_subagent=True)
        loop._webui_queue = None
        loop._webui_emit({"type": "text", "text": "x"})  # should not raise

    def test_subagent_marker_on_tool_start(self):
        loop = self._make_loop(is_subagent=True, agent_name="Security", agent_emoji="🔒")
        loop._webui_emit({"type": "tool_start", "tool": "bash"})
        ev = loop._webui_queue.get_nowait()
        self.assertTrue(ev.get("subagent"))
        self.assertEqual(ev.get("subagent_name"), "Security")

    def test_subagent_marker_on_stream_chunk(self):
        loop = self._make_loop(is_subagent=True, agent_name="Home", agent_emoji="🏠")
        loop._webui_emit({"type": "stream_chunk", "text": "tok"})
        ev = loop._webui_queue.get_nowait()
        self.assertTrue(ev.get("subagent"))
        self.assertEqual(ev.get("subagent_emoji"), "🏠")


# ── SubAgentRunner: propagación de _parent_webui_queue ────────────────────────

class TestSubAgentRunnerWebUiQueue(unittest.TestCase):

    def test_default_none(self):
        from agent.subagent import SubAgentRunner
        runner = SubAgentRunner(
            config=MagicMock(), permissions=MagicMock(),
            build_registry_fn=MagicMock(),
        )
        self.assertIsNone(runner._parent_webui_queue)

    def test_set_propagated_flag(self):
        from agent.subagent import SubAgentRunner
        runner = SubAgentRunner(
            config=MagicMock(), permissions=MagicMock(),
            build_registry_fn=MagicMock(),
        )
        q = queue.SimpleQueue()
        runner._parent_webui_queue = q
        self.assertIs(runner._parent_webui_queue, q)


# ── sessions.py: inyección al SubAgentRunner ──────────────────────────────────

class TestSessionsWebUiQueueInjection(unittest.TestCase):

    def test_sessions_injects_queue(self):
        import inspect
        import webui.sessions as _s
        src = inspect.getsource(_s)
        self.assertIn("_parent_webui_queue", src)
        self.assertIn("subagent_runner._parent_webui_queue", src)


# ── /api/agents/<run_id>/output ───────────────────────────────────────────────

class TestApiAgentOutput(unittest.TestCase):

    def _make_client(self):
        from webui.app import app as _app
        _app.config["TESTING"]    = True
        _app.config["SECRET_KEY"] = "test-secret"
        return _app.test_client()

    def test_output_endpoint_not_found(self):
        with self._make_client() as c:
            with patch("agent.subagent.get_by_prefix", return_value=None), \
                 patch("agent.subagent._registry", {}):
                resp = c.get("/api/agents/abc123/output")
        self.assertEqual(resp.status_code, 404)
        data = json.loads(resp.data)
        self.assertIn("error", data)

    def test_output_endpoint_found(self):
        from agent.subagent import ActiveSubAgent
        sub = ActiveSubAgent(
            run_id      = "abc123xyz",
            agent_id    = "coding",
            agent_name  = "Coding",
            agent_emoji = "💻",
            task        = "Analizar código",
            thread      = MagicMock(),
            kill_event  = threading.Event(),
            steer_queue = queue.SimpleQueue(),
            status      = "done",
            result      = "Resultado completo del análisis" * 30,
            finished_at = time.time(),
        )
        with self._make_client() as c:
            with patch("agent.subagent.get_by_prefix", return_value=sub):
                resp = c.get("/api/agents/abc123/output")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn("result", data)
        self.assertEqual(data["result"], sub.result)
        self.assertFalse(data.get("result_truncated", False))
        self.assertEqual(data["task"], "Analizar código")

    def test_result_preview_truncated_in_list(self):
        from webui.api_agents import _sub_to_dict
        from agent.subagent import ActiveSubAgent
        sub = ActiveSubAgent(
            run_id      = "xyzabc",
            agent_id    = "coding",
            agent_name  = "Coding",
            agent_emoji = "💻",
            task        = "Tarea larga",
            thread      = MagicMock(),
            kill_event  = threading.Event(),
            steer_queue = queue.SimpleQueue(),
            status      = "done",
            result      = "x" * 2000,
            finished_at = time.time(),
        )
        d = _sub_to_dict(sub, full=False)
        self.assertTrue(d["result_truncated"])
        self.assertLessEqual(len(d["result_preview"]), 600)

    def test_full_result_not_truncated(self):
        from webui.api_agents import _sub_to_dict
        from agent.subagent import ActiveSubAgent
        sub = ActiveSubAgent(
            run_id      = "xyzabc",
            agent_id    = "coding",
            agent_name  = "Coding",
            agent_emoji = "💻",
            task        = "Tarea",
            thread      = MagicMock(),
            kill_event  = threading.Event(),
            steer_queue = queue.SimpleQueue(),
            status      = "done",
            result      = "y" * 2000,
            finished_at = time.time(),
        )
        d = _sub_to_dict(sub, full=True)
        self.assertFalse(d.get("result_truncated", False))
        self.assertEqual(len(d["result_preview"]), 2000)


# ── page_agents: funciones JS ─────────────────────────────────────────────────

class TestPageAgentsJS(unittest.TestCase):

    def _src(self):
        from webui.app import app as _app
        _app.config["TESTING"] = True
        _app.config["SECRET_KEY"] = "test-secret"
        with _app.test_client() as c:
            return c.get("/agents").data.decode("utf-8", errors="replace")

    def test_showresult_function_present(self):
        self.assertIn("showResult", self._src())

    def test_showtask_function_present(self):
        self.assertIn("showTask", self._src())

    def test_closemodal_function_present(self):
        self.assertIn("closeModal", self._src())

    def test_modal_div_present(self):
        src = self._src()
        self.assertIn("agent-modal", src)

    def test_output_api_called(self):
        src = self._src()
        self.assertIn("/api/agents/", src)
        self.assertIn("/output", src)

    def test_task_column_present(self):
        self.assertIn("Tarea", self._src())


# ── page_chat: subagent CSS y funciones JS ────────────────────────────────────

class TestPageChatSubagentUI(unittest.TestCase):

    def _src(self):
        from webui.app import app as _app
        _app.config["TESTING"] = True
        _app.config["SECRET_KEY"] = "test-secret"
        with _app.test_client() as c:
            return c.get("/chat").data.decode("utf-8", errors="replace")

    def test_subagent_block_css(self):
        self.assertIn("tui-subagent-block", self._src())

    def test_append_subagent_text_function(self):
        self.assertIn("appendSubagentText", self._src())

    def test_append_subagent_chunk_function(self):
        self.assertIn("appendSubagentChunk", self._src())

    def test_sub_bufs_variable(self):
        self.assertIn("_subBufs", self._src())

    def test_subagent_event_handled(self):
        src = self._src()
        self.assertIn("ev.subagent", src)

    def test_subagent_header_style(self):
        self.assertIn("tui-subagent-hdr", self._src())


# ── retry XML malformado (non-EOF) ────────────────────────────────────────────

class TestXmlMalformedRetry(unittest.TestCase):

    def test_xml_malformed_retry_in_source(self):
        import inspect
        import agent.loop as _lp
        src = inspect.getsource(_lp)
        self.assertIn("xml_malformed_retry", src)
        self.assertIn("_is_eof_truncation", src)

    def test_xml_malformed_retry_branch(self):
        import inspect
        import agent.loop as _lp
        src = inspect.getsource(_lp)
        # Debe haber un retry separado para non-EOF XML errors
        self.assertIn("xml_malformed_retry_failed", src)

    def test_xml_non_eof_triggers_retry(self):
        """Verifica que _stream_response tiene la rama de retry para XML no-EOF."""
        import inspect
        import agent.loop as _lp
        src = inspect.getsource(_lp.AgentLoop._stream_response)
        # El retry específico para non-EOF debe estar presente
        self.assertIn("xml_malformed_retry", src)
        self.assertIn("not _is_eof_truncation", src)
        # Debe hacer una segunda llamada al backend (chat_sync o resp2/_r2)
        self.assertTrue("_r2" in src or "chat_sync" in src)

    def test_xml_retry_logs_warning(self):
        """La rama de retry logea xml_malformed_retry."""
        import inspect
        import agent.loop as _lp
        src = inspect.getsource(_lp.AgentLoop._stream_response)
        self.assertIn("xml_malformed_retry_failed", src)

    def test_xml_non_eof_branch_before_eof_branch(self):
        """El retry non-EOF debe aparecer antes que el fallback de texto parcial."""
        import inspect
        import agent.loop as _lp
        src = inspect.getsource(_lp.AgentLoop._stream_response)
        idx_retry = src.find("xml_malformed_retry")
        idx_fallback = src.find("xml_tool_call_recovered")
        self.assertGreater(idx_fallback, idx_retry,
                           "El retry non-EOF debe preceder al fallback de texto parcial")


if __name__ == "__main__":
    unittest.main()
