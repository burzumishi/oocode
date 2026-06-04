"""Tests: paridad TUI ↔ WebUI del historial de input del prompt y recuperación de sesiones.

- Historial de input (`~/.oocode/history`): el WebUI escribe/lee el MISMO fichero que
  el TUI (prompt_toolkit FileHistory), en formato compatible (incl. multilínea), y NO
  contamina el historial con respuestas del agente.
- Recuperación de sesiones: el WebUI restaura sesiones pasadas (endpoint + slash /session)
  reusando `AgentLoop.restore_session` (igual que el TUI), sobre el mismo JSONL.

Sin LLM ni red — helpers puros, inspección de rutas Flask y del HTML/JS renderizado.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Historial de input compartido (formato prompt_toolkit) ────────────────────

def test_input_history_roundtrip(tmp_path, monkeypatch):
    import agent.session as S
    monkeypatch.setattr(S, "INPUT_HISTORY_FILE", tmp_path / "history")
    S.append_input_history("hola mundo")
    S.append_input_history("linea1\nlinea2\nlinea3")   # multilínea
    S.append_input_history("/session abc123")
    assert S.load_input_history() == [
        "hola mundo", "linea1\nlinea2\nlinea3", "/session abc123",
    ]


def test_input_history_compatible_with_prompt_toolkit(tmp_path, monkeypatch):
    """Lo que escribe el WebUI lo lee el TUI (prompt_toolkit) y viceversa."""
    import agent.session as S
    from prompt_toolkit.history import FileHistory
    f = tmp_path / "history"
    monkeypatch.setattr(S, "INPUT_HISTORY_FILE", f)

    # WebUI escribe → TUI lee (FileHistory devuelve de más reciente a más antigua)
    S.append_input_history("uno")
    S.append_input_history("dos\ncon salto")
    assert list(FileHistory(str(f)).load_history_strings()) == ["dos\ncon salto", "uno"]

    # TUI escribe → WebUI lee
    FileHistory(str(f)).store_string("tres\nmultilinea")
    assert S.load_input_history()[-1] == "tres\nmultilinea"


def test_input_history_skips_empty(tmp_path, monkeypatch):
    import agent.session as S
    monkeypatch.setattr(S, "INPUT_HISTORY_FILE", tmp_path / "history")
    S.append_input_history("")          # ignorado
    S.append_input_history("   ")       # whitespace → descartado al leer
    S.append_input_history("real")
    assert S.load_input_history() == ["real"]


def test_input_history_missing_file(tmp_path, monkeypatch):
    import agent.session as S
    monkeypatch.setattr(S, "INPUT_HISTORY_FILE", tmp_path / "nope" / "history")
    assert S.load_input_history() == []


# ── El WebUI NO contamina el historial con respuestas del agente ──────────────

def test_webui_send_writes_only_user_input():
    import inspect
    from webui import api_chat
    src = inspect.getsource(api_chat)
    # Usa el helper compartido, no escribe el fichero a mano
    assert "append_input_history(message)" in src
    # Ya NO escribe la respuesta del slash al historial de input
    assert "+{slash_resp}" not in src
    assert "f'+{message}" not in src and 'f"+{message}' not in src


# ── Endpoints de paridad de historial / sesión ────────────────────────────────

def _flask_rules():
    from webui.app import app
    return {r.rule for r in app.url_map.iter_rules()}


def test_input_history_endpoint_registered():
    assert "/api/chat/input_history" in _flask_rules()


def test_load_session_endpoint_registered():
    assert "/api/chat/load_session" in _flask_rules()


# ── Slash /session en el WebUI ────────────────────────────────────────────────

class _FakeSessionMgr:
    def __init__(self):
        self.session_id = "deadbeefcafebabe"

    def load_messages(self, sid):
        return []


class _FakeConfig:
    agent_id = "test-agent-xyz"


class _FakeLoop:
    def __init__(self):
        self.config = _FakeConfig()
        self.session = _FakeSessionMgr()

    def restore_session(self, sid):
        return 0


def test_handle_slash_session_no_args_reports_active():
    from webui.api_chat import _handle_webui_slash
    sess = {"loop": _FakeLoop(), "history": [], "queue": None, "thread": None}
    out = _handle_webui_slash("/session", sess)
    assert out is not None and "deadbeef" in out


def test_handle_slash_session_not_found():
    from webui.api_chat import _handle_webui_slash
    sess = {"loop": _FakeLoop(), "history": [], "queue": None, "thread": None}
    out = _handle_webui_slash("/session noexiste999", sess)
    assert out is not None and "no encontrada" in out


# ── Cableado JS del WebUI ─────────────────────────────────────────────────────

def _chat_src():
    from webui.app import app as _app
    _app.config["TESTING"] = True
    _app.config["SECRET_KEY"] = "test-secret"
    with _app.test_client() as c:
        return c.get("/chat").data.decode("utf-8", errors="replace")


def test_chat_js_loads_shared_input_history():
    h = _chat_src()
    # El recall (flecha arriba) se puebla desde el historial compartido con el TUI
    assert "loadInputHistory" in h
    assert "/api/chat/input_history" in h


def test_chat_js_session_load_button_restores():
    h = _chat_src()
    # El botón "Cargar" del panel llama al endpoint real (no instruye usar /session)
    assert "/api/chat/load_session" in h
    assert "_pendingSessionReload" in h
    # Ya no muestra el mensaje engañoso de usar /session manualmente
    assert "Para continuar una sesión pasada, usa" not in h


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
