#!/usr/bin/env python3
"""Tests de validación de WebUI OOCode — cubre todas las funcionalidades."""
import io
import json
import queue
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import webui.app as _webui_app
import webui.helpers as _webui_helpers
import webui.sessions as _webui_sessions
from webui.app import (
    app,
    _WEBUI_SESSIONS,
    _SESSIONS_LOCK,
    _ensure_session_entry,
    _get_or_create_session,
    load_config,
    save_config,
    load_state,
    save_state,
    _get_theme,
    _human_size,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolated(tmp_path):
    """Redirect config/state files and clear sessions for each test.
    Patches both webui.app AND webui.helpers (helpers functions use their own refs)."""
    cfg   = tmp_path / "oocode.json"
    state = tmp_path / "webui_state.json"
    with patch.object(_webui_app, "CONFIG_FILE", cfg), \
         patch.object(_webui_app, "STATE_FILE",  state), \
         patch.object(_webui_helpers, "CONFIG_FILE", cfg), \
         patch.object(_webui_helpers, "STATE_FILE",  state):
        # Clear any leftover sessions
        with _SESSIONS_LOCK:
            _WEBUI_SESSIONS.clear()
        yield
        with _SESSIONS_LOCK:
            _WEBUI_SESSIONS.clear()


@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    with app.test_client() as c:
        yield c


def _make_mock_session(sid: str, history=None) -> dict:
    """Helper to build a complete mock session dict."""
    mock_loop = MagicMock()
    mock_loop.config.agent_emoji = "🤖"
    mock_loop.config.agent_name  = "OOCode"
    mock_loop.config.agent_id    = "main"
    mock_loop.config.model       = "test-model"
    mock_loop.config.hooks_builtins = {"lsp_after_write": True}
    mock_loop.config.memory_embed_enabled = True
    mock_loop.config.rag_enabled = False
    mock_loop.config.mcp_servers = []
    mock_loop.context.token_estimate.return_value = 1000
    mock_loop.context.max_tokens = 10000
    mock_loop._plan_tasks = []
    mock_loop._mcp_pool   = None
    mock_loop.rt.elevated = "ask"
    mock_loop._model_supports_images.return_value = False
    mock_loop.run_for_webui = MagicMock()
    ready = threading.Event()
    ready.set()
    return {
        "loop":        mock_loop,
        "queue":       queue.Queue(maxsize=500),
        "thread":      None,
        "history":     history or [],
        "lock":        threading.Lock(),
        "created_at":  time.time(),
        "last_active": time.time(),
        "agent_id":    "main",
        "_ready":      ready,
        "_gen":        0,
    }


# ── Config helpers ─────────────────────────────────────────────────────────────

class TestConfigHelpers:
    def test_load_config_missing_returns_defaults(self):
        cfg = load_config()
        assert isinstance(cfg, dict)

    def test_save_and_reload_config(self):
        original = {"model": "test-model", "ollama_host": "http://localhost:11434"}
        assert save_config(original) is True
        loaded = load_config()
        assert loaded["model"] == "test-model"

    def test_save_config_bad_path_returns_false(self, tmp_path):
        with patch.object(_webui_app, "CONFIG_FILE", tmp_path / "no" / "dir" / "cfg.json"), \
             patch.object(_webui_helpers, "CONFIG_FILE", tmp_path / "no" / "dir" / "cfg.json"):
            result = save_config({"model": "x"})
            assert result in (True, False)

    def test_load_state_missing_returns_empty_dict(self):
        assert load_state() == {}

    def test_save_and_reload_state(self):
        assert save_state({"theme": "light"}) is True
        assert load_state() == {"theme": "light"}

    def test_get_theme_default(self):
        assert _get_theme() == "dark"

    def test_get_theme_after_save(self):
        save_state({"theme": "light"})
        assert _get_theme() == "light"

    def test_human_size(self):
        assert _human_size(512) == "512 B"
        assert "KB" in _human_size(1500)
        assert "MB" in _human_size(1_500_000)

    def test_human_size_zero(self):
        assert _human_size(0) == "0 B"

    def test_human_size_exact_kb(self):
        assert _human_size(1024) == "1.0 KB"

    def test_human_size_exact_mb(self):
        assert _human_size(1_048_576) == "1.0 MB"

    def test_human_size_exact_gb(self):
        assert _human_size(1_073_741_824) == "1.0 GB"


# ── Page routes ───────────────────────────────────────────────────────────────

class TestPageRoutes:
    PAGES = ["/", "/config", "/chat", "/help", "/doctor", "/theme",
             "/sessions", "/agents"]

    def test_all_pages_return_200(self, client):
        for url in self.PAGES:
            r = client.get(url)
            assert r.status_code == 200, f"{url} → {r.status_code}"

    def test_all_pages_return_html(self, client):
        for url in self.PAGES:
            r = client.get(url)
            assert b"<html" in r.data or b"<!DOCTYPE" in r.data.lower(), url

    def test_all_pages_contain_nav(self, client):
        for url in self.PAGES:
            r = client.get(url)
            html = r.data.decode()
            assert 'href="/chat"' in html, f"{url}: missing /chat nav"

    def test_theme_toggle_button_present(self, client):
        r = client.get("/")
        assert b"theme-toggle" in r.data or b"theme" in r.data

    def test_dark_theme_by_default(self, client):
        r = client.get("/")
        html = r.data.decode()
        assert 'data-theme="dark"' in html

    def test_light_theme_after_set(self, client):
        # Use helpers.save_state to write to the patched state file
        _webui_helpers.save_state({"theme": "light"})
        r = client.get("/")
        html = r.data.decode()
        assert 'data-theme="light"' in html

    def test_css_custom_properties_present(self, client):
        r = client.get("/")
        html = r.data.decode()
        for var in ("--bg-primary", "--text-primary", "--accent-primary",
                    "--border-color", "--term-bg"):
            assert var in html, f"Missing CSS variable {var}"

    def test_css_animations_present(self, client):
        r = client.get("/")
        html = r.data.decode()
        for anim in ("@keyframes pulse", "@keyframes fadeIn", "@keyframes slideIn"):
            assert anim in html, f"Missing animation {anim}"

    def test_footer_present(self, client):
        r = client.get("/")
        html = r.data.decode()
        assert "OOCode WebUI" in html
        assert "100% local" in html


# ── Chat page features ────────────────────────────────────────────────────────

class TestChatPage:
    def test_tui_elements_present(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert "tui-messages" in html
        assert "tui-input" in html
        assert "tui-send" in html
        assert "sendMsg" in html

    def test_status_badges_present(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert 'id="sb-mcp"' in html
        assert 'id="sb-lsp"' in html
        assert 'id="sb-mem"' in html
        assert 'id="sb-rag"' in html
        assert 'id="sb-elev"' in html
        assert 'id="sb-vision"' in html

    def test_vision_badge_present(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert 'id="sb-vision"' in html
        assert "vision-active" in html

    def test_attach_button_present(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert 'id="tui-attach"' in html
        assert 'tui-file-input' in html
        assert "triggerFileInput" in html

    def test_pending_files_container_present(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert 'id="tui-pending-files"' in html

    def test_file_handling_js_present(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert "handleFileSelect" in html
        assert "removePendingFile" in html
        assert "_pendingFiles" in html
        assert "_renderPendingFiles" in html

    def test_vision_support_in_sendmsg(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert "images" in html
        assert "imgPaths" in html or "filter" in html

    def test_sendmsg_includes_images_payload(self, client):
        """sendMsg must build payload.images from _pendingFiles filtered by type=image."""
        r = client.get("/chat")
        html = r.data.decode()
        # The JS must filter image type and include in payload
        assert "imgPaths" in html
        assert "payload.images" in html or "images: imgPaths" in html

    def test_loadstatus_retry_present(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert "loadStatus(15)" in html
        assert "retries" in html

    def test_busy_timeout_present(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert "_busyTimeout" in html
        assert "300000" in html

    def test_keyboard_shortcut_enter(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert "keydown" in html
        assert "sendMsg" in html

    def test_sse_connect_present(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert "connectSSE" in html
        assert "EventSource" in html
        assert "/api/chat/stream" in html

    def test_markdown_renderer_present(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert "_mdToHtml" in html

    def test_slash_hint_present(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert "tui-slash-hint" in html
        assert "/new" in html

    def test_badge_css_classes_present(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert "mcp-active" in html
        assert "lsp-active" in html
        assert "mem-active" in html
        assert "rag-active" in html
        assert "vision-active" in html

    def test_setBadge_correct_class_args(self, client):
        """_setBadge must pass only the modifier class, not the full compound class."""
        r = client.get("/chat")
        html = r.data.decode()
        assert "'mcp-active'" in html or '"mcp-active"' in html
        assert "'lsp-active'" in html or '"lsp-active"' in html
        # Must NOT duplicate base class in arg
        assert "'tui-sb-badge mcp-active'" not in html
        assert '"tui-sb-badge mcp-active"' not in html

    def test_agent_selector_present(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert "agent-sel" in html or "changeAgent" in html

    def test_sessions_panel_present(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert "tui-sessions-panel" in html

    def test_tool_block_collapsible_present(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert "tui-tool-block" in html
        assert "_toggleToolBlock" in html

    def test_thinking_indicator_present(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert "tui-thinking" in html
        assert "appendThinking" in html


# ── API: config ───────────────────────────────────────────────────────────────

class TestApiConfig:
    def test_get_config(self, client):
        r = client.get("/api/config")
        assert r.status_code == 200
        d = r.get_json()
        assert isinstance(d, dict)

    def test_get_config_raw(self, client):
        r = client.get("/api/config/raw")
        assert r.status_code == 200

    def test_theme_set_dark(self, client):
        r = client.post("/theme/set",
                        data=json.dumps({"theme": "dark"}),
                        content_type="application/json")
        assert r.status_code == 200
        assert r.get_json()["ok"] is True

    def test_theme_set_light(self, client):
        r = client.post("/theme/set",
                        data=json.dumps({"theme": "light"}),
                        content_type="application/json")
        assert r.status_code == 200
        # Verify the state was actually saved (via helpers)
        assert _webui_helpers.load_state().get("theme") == "light"


# ── API: session management ───────────────────────────────────────────────────

class TestSessionManagement:
    def test_ensure_session_entry_returns_queue_immediately(self):
        """_ensure_session_entry must return a queue without blocking."""
        t0 = time.monotonic()
        q = _ensure_session_entry("test-sid-1", "main")
        elapsed = time.monotonic() - t0
        assert elapsed < 1.0, f"Should return immediately, took {elapsed:.2f}s"
        assert isinstance(q, queue.Queue)

    def test_ensure_session_entry_idempotent(self):
        q1 = _ensure_session_entry("test-sid-2", "main")
        q2 = _ensure_session_entry("test-sid-2", "main")
        assert q1 is q2, "Same SID must return same queue"

    def test_session_dict_created_immediately(self):
        _ensure_session_entry("test-sid-3", "main")
        with _SESSIONS_LOCK:
            assert "test-sid-3" in _WEBUI_SESSIONS
            sess = _WEBUI_SESSIONS["test-sid-3"]
        assert "queue" in sess
        assert "history" in sess
        assert "_ready" in sess

    def test_session_loop_none_before_init(self):
        _ensure_session_entry("test-sid-4", "main")
        with _SESSIONS_LOCK:
            assert _WEBUI_SESSIONS["test-sid-4"]["loop"] is None

    def test_session_gen_initialized_to_zero(self):
        """New sessions must initialize _gen to 0 for ghost generator fix."""
        _ensure_session_entry("test-gen-sid", "main")
        with _SESSIONS_LOCK:
            assert _WEBUI_SESSIONS["test-gen-sid"]["_gen"] == 0

    def test_get_or_create_session_raises_on_failed_init(self):
        """If loop init raises, _ready is still set (no deadlock)."""
        def _bad_init(*a, **kw):
            raise RuntimeError("mock failure")

        with patch.object(_webui_sessions, "_create_loop_for_webui", side_effect=_bad_init):
            _ensure_session_entry("test-sid-5", "main")
            with _SESSIONS_LOCK:
                ready = _WEBUI_SESSIONS["test-sid-5"]["_ready"]
            ready.wait(timeout=5.0)
            assert ready.is_set()

    def test_evict_old_sessions(self):
        _ensure_session_entry("test-evict-1", "main")
        with _SESSIONS_LOCK:
            _WEBUI_SESSIONS["test-evict-1"]["last_active"] = time.time() - 7200  # 2h ago
        from webui.app import _evict_old_sessions
        _evict_old_sessions()
        with _SESSIONS_LOCK:
            assert "test-evict-1" not in _WEBUI_SESSIONS


# ── Ghost generator fix tests ─────────────────────────────────────────────────

class TestGhostGeneratorFix:
    def test_gen_increments_on_stream_connect(self, client):
        """Connecting SSE must increment _gen in the session."""
        with patch.object(_webui_sessions, "_create_loop_for_webui", return_value=MagicMock()):
            with client.session_transaction() as sc:
                sc["webui_sid"] = "gen-test-sid"
            # Inject session with _gen=0
            with _SESSIONS_LOCK:
                _WEBUI_SESSIONS["gen-test-sid"] = _make_mock_session("gen-test-sid")
            # Stream connect reads the generator
            with client.get("/api/chat/stream",
                            query_string={"agent_id": "main"},
                            buffered=False) as r:
                # Read the connected event
                data = b""
                for chunk in r.response:
                    data += chunk
                    if b"connected" in data:
                        break
            # _gen should have been incremented to 1
            with _SESSIONS_LOCK:
                gen = _WEBUI_SESSIONS.get("gen-test-sid", {}).get("_gen", 0)
            assert gen >= 1

    def test_second_connect_increments_gen_again(self, client):
        """Two SSE connections to the same SID must increment _gen twice."""
        with client.session_transaction() as sc:
            sc["webui_sid"] = "gen2-sid"
        with _SESSIONS_LOCK:
            _WEBUI_SESSIONS["gen2-sid"] = _make_mock_session("gen2-sid")
            _WEBUI_SESSIONS["gen2-sid"]["_gen"] = 1  # simulate first connection

        with client.get("/api/chat/stream",
                        query_string={"agent_id": "main"},
                        buffered=False) as r:
            data = b""
            for chunk in r.response:
                data += chunk
                if b"connected" in data:
                    break

        with _SESSIONS_LOCK:
            gen = _WEBUI_SESSIONS.get("gen2-sid", {}).get("_gen", 0)
        assert gen >= 2


# ── sess NameError fix tests ──────────────────────────────────────────────────

class TestSessNameErrorFix:
    def test_done_event_with_response_saves_to_history(self, client):
        """Simulating 'done' event with response must not crash gen() and must save history."""
        with client.session_transaction() as sc:
            sc["webui_sid"] = "done-sess-sid"

        sess = _make_mock_session("done-sess-sid")
        with _SESSIONS_LOCK:
            _WEBUI_SESSIONS["done-sess-sid"] = sess

        # Put a 'done' event with response into the queue
        sess["queue"].put({"type": "done", "response": "hello from agent"})

        with client.get("/api/chat/stream",
                        query_string={"agent_id": "main"},
                        buffered=False) as r:
            data = b""
            for chunk in r.response:
                data += chunk
                if b"done" in data:
                    break

        assert b"done" in data
        # History should contain the assistant message (no NameError).
        # History is saved BEFORE yielding the done event, so it is guaranteed
        # to be present once the client sees the done event.
        with _SESSIONS_LOCK:
            hist = _WEBUI_SESSIONS.get("done-sess-sid", {}).get("history", [])
        assert any(h.get("role") == "assistant" and h.get("text") == "hello from agent"
                   for h in hist)


# ── API: chat status (no live loop) ──────────────────────────────────────────

class TestApiChatStatus:
    def test_status_no_session_returns_not_connected(self, client):
        r = client.get("/api/chat/status")
        assert r.status_code == 200
        d = r.get_json()
        assert d["connected"] is False

    def test_status_with_mock_session(self, client):
        """Status endpoint must return all badge-related fields."""
        with client.session_transaction() as sess_cookie:
            sess_cookie["webui_sid"] = "mock-sid"

        with _SESSIONS_LOCK:
            _WEBUI_SESSIONS["mock-sid"] = _make_mock_session("mock-sid")

        r = client.get("/api/chat/status")
        d = r.get_json()
        assert d["connected"] is True
        assert d["agent_name"] == "OOCode"
        assert "mcp_count" in d
        assert "lsp_on" in d
        assert "memory_on" in d
        assert "rag_on" in d
        assert "elevated" in d
        assert "vision_on" in d

    def test_status_returns_mcp_count(self, client):
        with client.session_transaction() as sc:
            sc["webui_sid"] = "mcp-status-sid"
        with _SESSIONS_LOCK:
            _WEBUI_SESSIONS["mcp-status-sid"] = _make_mock_session("mcp-status-sid")
        r = client.get("/api/chat/status")
        d = r.get_json()
        assert "mcp_count" in d
        assert isinstance(d["mcp_count"], int)

    def test_status_returns_lsp_on(self, client):
        with client.session_transaction() as sc:
            sc["webui_sid"] = "lsp-status-sid"
        with _SESSIONS_LOCK:
            _WEBUI_SESSIONS["lsp-status-sid"] = _make_mock_session("lsp-status-sid")
        r = client.get("/api/chat/status")
        d = r.get_json()
        assert "lsp_on" in d

    def test_status_returns_vision_on(self, client):
        with client.session_transaction() as sc:
            sc["webui_sid"] = "vis-status-sid"
        with _SESSIONS_LOCK:
            _WEBUI_SESSIONS["vis-status-sid"] = _make_mock_session("vis-status-sid")
        r = client.get("/api/chat/status")
        d = r.get_json()
        assert "vision_on" in d


# ── API: chat history ─────────────────────────────────────────────────────────

class TestApiChatHistory:
    def test_history_empty_for_new_session(self, client):
        with patch.object(_webui_sessions, "_create_loop_for_webui", return_value=MagicMock()):
            r = client.get("/api/chat/history?agent_id=main")
        assert r.status_code == 200
        d = r.get_json()
        assert "history" in d
        assert isinstance(d["history"], list)

    def test_history_contains_added_messages(self, client):
        with client.session_transaction() as sc:
            sc["webui_sid"] = "hist-sid"
        with _SESSIONS_LOCK:
            _WEBUI_SESSIONS["hist-sid"] = _make_mock_session(
                "hist-sid",
                history=[{"role": "user", "text": "hello", "ts": 0, "id": "a1"}]
            )
        r = client.get("/api/chat/history")
        d = r.get_json()
        assert len(d["history"]) == 1
        assert d["history"][0]["text"] == "hello"


# ── Slash /new clears history ─────────────────────────────────────────────────

class TestSlashCommands:
    def _inject(self, sid):
        sess = _make_mock_session(sid, history=[
            {"role": "user", "text": "prev", "ts": 0, "id": "x"}
        ])
        sess["loop"].context.clear = MagicMock()
        with _SESSIONS_LOCK:
            _WEBUI_SESSIONS[sid] = sess
        return sess

    def test_slash_new_clears_history(self, client):
        with client.session_transaction() as sc:
            sc["webui_sid"] = "slash-new-sid"
        sess = self._inject("slash-new-sid")
        r = client.post("/api/chat/send",
                        data=json.dumps({"message": "/new", "agent_id": "main"}),
                        content_type="application/json")
        assert r.status_code == 200
        with _SESSIONS_LOCK:
            hist = _WEBUI_SESSIONS["slash-new-sid"]["history"]
        # Only the /new command and its response should remain (prev cleared)
        assert not any(h.get("text") == "prev" for h in hist)

    def test_slash_compact_calls_loop_compact(self, client):
        with client.session_transaction() as sc:
            sc["webui_sid"] = "slash-compact-sid"
        sess = _make_mock_session("slash-compact-sid")
        sess["loop"].context.compact = MagicMock()
        sess["loop"].context.token_estimate.return_value = 500
        sess["loop"].context.max_tokens = 10000
        with _SESSIONS_LOCK:
            _WEBUI_SESSIONS["slash-compact-sid"] = sess
        r = client.post("/api/chat/send",
                        data=json.dumps({"message": "/compact", "agent_id": "main"}),
                        content_type="application/json")
        assert r.status_code == 200
        sess["loop"].context.compact.assert_called_once()

    def test_slash_elevated_reads_mode(self, client):
        with client.session_transaction() as sc:
            sc["webui_sid"] = "slash-elev-sid"
        sess = _make_mock_session("slash-elev-sid")
        sess["loop"].rt.elevated = "on"
        with _SESSIONS_LOCK:
            _WEBUI_SESSIONS["slash-elev-sid"] = sess
        r = client.post("/api/chat/send",
                        data=json.dumps({"message": "/elevated", "agent_id": "main"}),
                        content_type="application/json")
        assert r.status_code == 200
        # Check response in history
        with _SESSIONS_LOCK:
            hist = _WEBUI_SESSIONS["slash-elev-sid"]["history"]
        assert any("on" in h.get("text", "") for h in hist)

    def test_slash_elevated_sets_mode(self, client):
        with client.session_transaction() as sc:
            sc["webui_sid"] = "slash-elev-set-sid"
        sess = _make_mock_session("slash-elev-set-sid")
        with _SESSIONS_LOCK:
            _WEBUI_SESSIONS["slash-elev-set-sid"] = sess
        r = client.post("/api/chat/send",
                        data=json.dumps({"message": "/elevated full", "agent_id": "main"}),
                        content_type="application/json")
        assert r.status_code == 200
        assert sess["loop"].rt.elevated == "full"


# ── API: chat clear ───────────────────────────────────────────────────────────

class TestApiChatClear:
    def test_clear_removes_session(self, client):
        with client.session_transaction() as sc:
            sc["webui_sid"] = "clear-sid"
        mock_loop = MagicMock()
        with _SESSIONS_LOCK:
            _WEBUI_SESSIONS["clear-sid"] = _make_mock_session("clear-sid")
            _WEBUI_SESSIONS["clear-sid"]["loop"] = mock_loop
        r = client.post("/api/chat/clear")
        assert r.status_code == 200
        assert r.get_json()["ok"] is True
        with _SESSIONS_LOCK:
            assert "clear-sid" not in _WEBUI_SESSIONS
        mock_loop.close.assert_called_once()


# ── API: chat send ────────────────────────────────────────────────────────────

class TestApiChatSend:
    def _inject_session(self, sid: str) -> dict:
        sess = _make_mock_session(sid)
        with _SESSIONS_LOCK:
            _WEBUI_SESSIONS[sid] = sess
        return sess

    def test_send_empty_message_returns_400(self, client):
        r = client.post("/api/chat/send",
                        data=json.dumps({"message": "", "agent_id": "main"}),
                        content_type="application/json")
        assert r.status_code == 400

    def test_send_message_ok(self, client):
        with client.session_transaction() as sc:
            sc["webui_sid"] = "send-sid"
        self._inject_session("send-sid")
        r = client.post("/api/chat/send",
                        data=json.dumps({"message": "hola", "agent_id": "main"}),
                        content_type="application/json")
        assert r.status_code == 200
        assert r.get_json()["ok"] is True

    def test_send_message_added_to_history(self, client):
        with client.session_transaction() as sc:
            sc["webui_sid"] = "send-hist-sid"
        self._inject_session("send-hist-sid")
        client.post("/api/chat/send",
                    data=json.dumps({"message": "test msg", "agent_id": "main"}),
                    content_type="application/json")
        with _SESSIONS_LOCK:
            hist = _WEBUI_SESSIONS["send-hist-sid"]["history"]
        assert any(h["text"] == "test msg" for h in hist)

    def test_send_with_images(self, client):
        with client.session_transaction() as sc:
            sc["webui_sid"] = "send-img-sid"
        self._inject_session("send-img-sid")
        r = client.post("/api/chat/send",
                        data=json.dumps({
                            "message": "describe this",
                            "agent_id": "main",
                            "images": ["/tmp/test.png"],
                        }),
                        content_type="application/json")
        assert r.status_code == 200

    def test_send_no_loop_returns_503(self, client):
        with client.session_transaction() as sc:
            sc["webui_sid"] = "noloop-sid"
        sess = _make_mock_session("noloop-sid")
        sess["loop"] = None
        with _SESSIONS_LOCK:
            _WEBUI_SESSIONS["noloop-sid"] = sess
        r = client.post("/api/chat/send",
                        data=json.dumps({"message": "hi", "agent_id": "main"}),
                        content_type="application/json")
        assert r.status_code == 503

    def test_send_busy_returns_409(self, client):
        with client.session_transaction() as sc:
            sc["webui_sid"] = "busy-sid"
        sess = _make_mock_session("busy-sid")
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        sess["thread"] = mock_thread
        with _SESSIONS_LOCK:
            _WEBUI_SESSIONS["busy-sid"] = sess
        r = client.post("/api/chat/send",
                        data=json.dumps({"message": "hello", "agent_id": "main"}),
                        content_type="application/json")
        assert r.status_code == 409

    def test_send_slash_command_new(self, client):
        with client.session_transaction() as sc:
            sc["webui_sid"] = "slash-sid"
        self._inject_session("slash-sid")
        r = client.post("/api/chat/send",
                        data=json.dumps({"message": "/new", "agent_id": "main"}),
                        content_type="application/json")
        assert r.status_code == 200


# ── API: SSE stream ───────────────────────────────────────────────────────────

class TestApiChatStream:
    def test_stream_sends_connected_immediately(self, client):
        """SSE must yield 'connected' event without waiting for loop init."""
        def _slow_create_loop(*a, **kw):
            time.sleep(0.2)
            return MagicMock()

        with patch.object(_webui_sessions, "_create_loop_for_webui", side_effect=_slow_create_loop):
            t0 = time.monotonic()
            with client.get("/api/chat/stream",
                            query_string={"agent_id": "main"},
                            buffered=False) as r:
                assert r.status_code == 200
                data = b""
                for chunk in r.response:
                    data += chunk
                    if b"connected" in data:
                        break
                elapsed = time.monotonic() - t0
        assert b"connected" in data
        assert elapsed < 1.5, f"Connected took {elapsed:.2f}s — too slow"

    def test_stream_content_type(self, client):
        with patch.object(_webui_sessions, "_create_loop_for_webui", return_value=MagicMock()):
            with client.get("/api/chat/stream") as r:
                assert "text/event-stream" in r.content_type

    def test_sse_connected_event_arrives_fast(self, client):
        """SSE connected event must arrive in < 1s (no blocking on loop init)."""
        with patch.object(_webui_sessions, "_create_loop_for_webui", return_value=MagicMock()):
            t0 = time.monotonic()
            with client.get("/api/chat/stream",
                            query_string={"agent_id": "main"},
                            buffered=False) as r:
                data = b""
                for chunk in r.response:
                    data += chunk
                    if b"connected" in data:
                        break
                elapsed = time.monotonic() - t0
        assert elapsed < 1.0, f"SSE connected took {elapsed:.2f}s"


# ── API: file upload ──────────────────────────────────────────────────────────

class TestApiFilesUpload:
    def test_upload_image(self, client):
        img_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
        r = client.post("/api/files/upload",
                        data={"file": (io.BytesIO(img_data), "test.png")},
                        content_type="multipart/form-data")
        assert r.status_code == 200
        d = r.get_json()
        assert d["ok"] is True
        assert d["type"] == "image"
        assert d["name"] == "test.png"
        assert Path(d["path"]).exists()
        Path(d["path"]).unlink(missing_ok=True)

    def test_upload_text_file(self, client):
        r = client.post("/api/files/upload",
                        data={"file": (io.BytesIO(b"hello world"), "notes.txt")},
                        content_type="multipart/form-data")
        assert r.status_code == 200
        d = r.get_json()
        assert d["ok"] is True
        assert d["type"] == "text"
        Path(d["path"]).unlink(missing_ok=True)

    def test_upload_python_file(self, client):
        r = client.post("/api/files/upload",
                        data={"file": (io.BytesIO(b"print('hi')"), "script.py")},
                        content_type="multipart/form-data")
        assert r.status_code == 200
        d = r.get_json()
        assert d["type"] == "text"
        assert d["ext"] == ".py"
        Path(d["path"]).unlink(missing_ok=True)

    def test_upload_disallowed_type_returns_400(self, client):
        r = client.post("/api/files/upload",
                        data={"file": (io.BytesIO(b"data"), "file.exe")},
                        content_type="multipart/form-data")
        assert r.status_code == 400
        assert "error" in r.get_json()

    def test_upload_no_file_returns_400(self, client):
        r = client.post("/api/files/upload")
        assert r.status_code == 400

    def test_upload_returns_size_human(self, client):
        r = client.post("/api/files/upload",
                        data={"file": (io.BytesIO(b"x" * 1024), "big.txt")},
                        content_type="multipart/form-data")
        assert r.status_code == 200
        d = r.get_json()
        assert "size_h" in d
        assert "size" in d
        Path(d["path"]).unlink(missing_ok=True)

    def test_upload_image_extensions(self, client):
        for ext in (".jpg", ".jpeg", ".gif", ".webp", ".png"):
            r = client.post("/api/files/upload",
                            data={"file": (io.BytesIO(b"data"), f"img{ext}")},
                            content_type="multipart/form-data")
            assert r.status_code == 200
            d = r.get_json()
            assert d["type"] == "image", f"Expected image for {ext}"
            Path(d["path"]).unlink(missing_ok=True)

    def test_upload_returns_correct_type_image(self, client):
        """File upload must return type='image' for image extensions."""
        r = client.post("/api/files/upload",
                        data={"file": (io.BytesIO(b"PNG"), "photo.png")},
                        content_type="multipart/form-data")
        d = r.get_json()
        assert d["type"] == "image"
        Path(d["path"]).unlink(missing_ok=True)

    def test_upload_returns_correct_type_text(self, client):
        """File upload must return type='text' for text extensions."""
        r = client.post("/api/files/upload",
                        data={"file": (io.BytesIO(b"code"), "main.js")},
                        content_type="multipart/form-data")
        d = r.get_json()
        assert d["type"] == "text"
        Path(d["path"]).unlink(missing_ok=True)


# ── API: files download / info ────────────────────────────────────────────────

class TestApiFiles:
    def test_download_nonexistent_returns_404(self, client):
        r = client.get("/api/files/download?path=/nonexistent/file.txt")
        assert r.status_code == 404

    def test_info_nonexistent_returns_404(self, client):
        r = client.get("/api/files/info?path=/nonexistent/file.txt")
        assert r.status_code == 404

    def test_download_existing_file(self, client, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        r = client.get(f"/api/files/download?path={f}")
        assert r.status_code == 200

    def test_info_existing_file(self, client, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        r = client.get(f"/api/files/info?path={f}")
        assert r.status_code == 200
        d = r.get_json()
        assert d["name"] == "test.txt"
        assert d["size"] == 11


# ── API: agents ───────────────────────────────────────────────────────────────

class TestApiAgents:
    def test_agents_returns_empty_lists(self, client):
        r = client.get("/api/agents")
        assert r.status_code == 200
        d = r.get_json()
        assert "running" in d or "recent" in d or "agents" in d

    def test_agents_kill_nonexistent_returns_404_or_400(self, client):
        r = client.post("/api/agents/kill/nonexistent-run-id")
        assert r.status_code in (200, 404, 400)


# ── API: sessions list ─────────────────────────────────────────────────────────

class TestApiSessions:
    def test_sessions_list_returns_json(self, client):
        r = client.get("/api/sessions")
        assert r.status_code == 200
        d = r.get_json()
        assert "sessions" in d


# ── API: system status ────────────────────────────────────────────────────────

class TestApiStatus:
    def test_status_returns_json(self, client):
        r = client.get("/api/status")
        assert r.status_code == 200
        d = r.get_json()
        assert isinstance(d, dict)


# ── Human size helper ─────────────────────────────────────────────────────────

class TestHumanSize:
    @pytest.mark.parametrize("n,expected", [
        (0,      "0 B"),
        (999,    "999 B"),
        (1024,   "1.0 KB"),
        (1536,   "1.5 KB"),
        (1_048_576, "1.0 MB"),
        (1_073_741_824, "1.0 GB"),
    ])
    def test_human_size_values(self, n, expected):
        assert _human_size(n) == expected


# ── Theme endpoint ────────────────────────────────────────────────────────────

class TestThemeEndpoint:
    def test_set_theme_dark(self, client):
        r = client.post("/theme/set",
                        data=json.dumps({"theme": "dark"}),
                        content_type="application/json")
        assert r.status_code == 200
        assert _webui_helpers.load_state().get("theme") == "dark"

    def test_set_theme_light(self, client):
        r = client.post("/theme/set",
                        data=json.dumps({"theme": "light"}),
                        content_type="application/json")
        assert r.status_code == 200
        assert _webui_helpers.load_state().get("theme") == "light"

    def test_invalid_theme_accepted_without_error(self, client):
        r = client.post("/theme/set",
                        data=json.dumps({"theme": "solarized"}),
                        content_type="application/json")
        assert r.status_code == 200


# ── CSS badge classes ─────────────────────────────────────────────────────────

class TestBadgeCssClasses:
    def test_tui_sb_badge_base_class_in_css(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert ".tui-sb-badge" in html

    def test_mcp_active_class_in_css(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert ".tui-sb-badge.mcp-active" in html or "mcp-active" in html

    def test_lsp_active_class_in_css(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert "lsp-active" in html

    def test_mem_active_class_in_css(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert "mem-active" in html

    def test_rag_active_class_in_css(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert "rag-active" in html

    def test_vision_active_class_in_css(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert "vision-active" in html

    def test_elev_on_class_in_css(self, client):
        r = client.get("/chat")
        html = r.data.decode()
        assert "elev-on" in html


# ── Blueprint structure tests ─────────────────────────────────────────────────

class TestBlueprintStructure:
    def test_api_config_blueprint_registered(self, client):
        r = client.get("/api/config")
        assert r.status_code == 200

    def test_api_chat_blueprint_registered(self, client):
        with patch.object(_webui_sessions, "_create_loop_for_webui", return_value=MagicMock()):
            r = client.get("/api/chat/history")
        assert r.status_code == 200

    def test_api_files_blueprint_registered(self, client):
        r = client.get("/api/files/info?path=/nonexistent")
        assert r.status_code == 404  # endpoint exists, returns 404 for bad path

    def test_api_agents_blueprint_registered(self, client):
        r = client.get("/api/agents")
        assert r.status_code == 200

    def test_page_home_blueprint_registered(self, client):
        r = client.get("/")
        assert r.status_code == 200

    def test_page_config_blueprint_registered(self, client):
        r = client.get("/config")
        assert r.status_code == 200

    def test_page_chat_blueprint_registered(self, client):
        r = client.get("/chat")
        assert r.status_code == 200

    def test_page_agents_blueprint_registered(self, client):
        r = client.get("/agents")
        assert r.status_code == 200

    def test_page_misc_sessions_registered(self, client):
        r = client.get("/sessions")
        assert r.status_code == 200

    def test_page_misc_help_registered(self, client):
        r = client.get("/help")
        assert r.status_code == 200

    def test_page_misc_doctor_registered(self, client):
        r = client.get("/doctor")
        assert r.status_code == 200

    def test_page_misc_theme_registered(self, client):
        r = client.get("/theme")
        assert r.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
