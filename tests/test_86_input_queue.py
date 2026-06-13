"""Cola FIFO de entradas mientras el agente está ocupado (ui/app.py).

Comportamiento: con un turno en curso, los mensajes normales y los slash MUTADORES se
encolan (FIFO) y se procesan al terminar el turno; los slash de display/control pasan al
momento. El routing de _append_output manda la salida de hilos NO-agente al buffer
estático (visible al momento) en vez del cuerpo del live block.
"""
import threading
from unittest.mock import MagicMock, patch

from ui.app import OOCodeApp, _QUEUE_SLASH_CMDS


def _bare_app():
    app = OOCodeApp.__new__(OOCodeApp)
    app._lock = threading.RLock()
    app._pending_queue = []
    app._agent_thread = None
    app._agent_loop = MagicMock()
    app._config = MagicMock()
    app._app = MagicMock()
    return app


class TestQueueSlashClassification:
    def test_mutators_in_queue_set(self):
        for c in ("/new", "/reset", "/clear", "/compact", "/resume", "/model",
                  "/switch", "/agent", "/session", "/branch", "/elevated",
                  "/think", "/reasoning", "/ctx", "/init"):
            assert c in _QUEUE_SLASH_CMDS, f"{c} debería encolarse"

    def test_passthrough_not_in_queue_set(self):
        # Display/control: NO se encolan (pasan al momento)
        for c in ("/help", "/mcp", "/steer", "/kill", "/usage", "/config",
                  "/status", "/agents", "/sessions", "/abort", "/exit", "/diff"):
            assert c not in _QUEUE_SLASH_CMDS, f"{c} NO debería encolarse"


class TestEnqueuePending:
    def test_appends_and_notifies(self):
        app = _bare_app()
        with patch("sys.stdout") as _out:
            app._enqueue_pending("message", "haz X")
        assert app._pending_queue == [{"kind": "message", "text": "haz X"}]

    def test_fifo_order(self):
        app = _bare_app()
        with patch("sys.stdout"):
            app._enqueue_pending("message", "uno")
            app._enqueue_pending("slash", "/compact")
            app._enqueue_pending("message", "dos")
        assert [i["text"] for i in app._pending_queue] == ["uno", "/compact", "dos"]


class TestDrainPendingQueue:
    def test_empty_is_noop(self):
        app = _bare_app()
        app._start_agent_turn = MagicMock()
        app._drain_pending_queue()
        app._start_agent_turn.assert_not_called()

    def test_leading_slash_runs_then_stops_at_message(self):
        app = _bare_app()
        app._pending_queue = [
            {"kind": "slash", "text": "/compact"},
            {"kind": "message", "text": "sigue"},
            {"kind": "slash", "text": "/model x"},
        ]
        app._start_agent_turn = MagicMock()
        with patch("ui.commands.handle_slash") as _hs, patch("sys.stdout"):
            app._drain_pending_queue()
        # El slash inicial se ejecuta; al llegar al mensaje arranca el turno y PARA
        _hs.assert_called_once_with("/compact", app._agent_loop, app._config)
        app._start_agent_turn.assert_called_once_with("sigue")
        # El resto queda en cola → lo drenará el finally del turno encadenado
        assert app._pending_queue == [{"kind": "slash", "text": "/model x"}]

    def test_only_slashes_drain_fully_no_turn(self):
        app = _bare_app()
        app._pending_queue = [
            {"kind": "slash", "text": "/compact"},
            {"kind": "slash", "text": "/model x"},
        ]
        app._start_agent_turn = MagicMock()
        with patch("ui.commands.handle_slash") as _hs, patch("sys.stdout"):
            app._drain_pending_queue()
        assert _hs.call_count == 2
        app._start_agent_turn.assert_not_called()
        assert app._pending_queue == []

    def test_slash_error_does_not_break_drain(self):
        app = _bare_app()
        app._pending_queue = [
            {"kind": "slash", "text": "/boom"},
            {"kind": "slash", "text": "/compact"},
        ]
        app._start_agent_turn = MagicMock()
        with patch("ui.commands.handle_slash", side_effect=[RuntimeError("x"), None]) as _hs, \
             patch("sys.stdout"):
            app._drain_pending_queue()
        assert _hs.call_count == 2   # el error del primero no aborta el drenaje
        assert app._pending_queue == []


class TestAppendOutputThreadRouting:
    def _app_for_routing(self):
        app = _bare_app()
        app._live_block_active = True
        app._live_block_plan_mode = False
        app._live_block_body = []
        app._live_block_plan_header = []
        app._output_parts = []
        app._output_chars = 0
        app._output_line_count = 0
        app._output_static_key = 0
        app._output_cache_key = 0
        app._MAX_OUTPUT_CHARS = 1_000_000
        return app

    def test_non_agent_thread_goes_to_static(self):
        """Output de un hilo que NO es el del agente (echo del event loop, slash) va al
        buffer estático aunque el live block esté activo → visible al momento."""
        app = self._app_for_routing()
        app._agent_thread = threading.Thread(target=lambda: None)  # otro hilo, no el actual
        app._append_output("salida de slash\n")
        assert app._output_parts == ["salida de slash\n"]
        assert app._live_block_body == []

    def test_agent_thread_goes_to_live_block_body(self):
        """Output del hilo del agente sí va al cuerpo del live block."""
        app = self._app_for_routing()
        app._agent_thread = threading.current_thread()   # simulamos ser el hilo del agente
        app._append_output("texto del agente\n")
        assert app._live_block_body == ["texto del agente\n"]
        assert app._output_parts == []

    def test_no_live_block_goes_to_static(self):
        app = self._app_for_routing()
        app._live_block_active = False
        app._agent_thread = threading.current_thread()
        app._append_output("idle\n")
        assert app._output_parts == ["idle\n"]
