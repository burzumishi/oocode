"""Tests para el tracking de stats de LspClient y LspPool.

Verifica que los contadores (req_sent, last_used, open_files) se actualizan
correctamente para todos los métodos, incluido diagnostics() que usa flujo push
y no llama a _request().
"""
import queue
import threading
import time
import unittest
from unittest.mock import MagicMock, patch


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_client():
    """LspClient mínimo con proceso falso — sin conexión real."""
    from agent.lsp_client import LspClient
    c = LspClient.__new__(LspClient)
    c._cmd             = ["fake-lsp"]
    c._workspace       = __import__("pathlib").Path("/tmp")
    c._timeout         = 5.0
    c._proc            = None
    c._req_id          = 0
    c._id_lock         = threading.Lock()
    c._send_lock       = threading.Lock()
    c._msg_queue       = queue.Queue()
    c._reader_thread   = None
    c._started         = True
    c._dead            = False
    c._open_files      = {}
    c._diag_cache      = {}
    c._req_sent        = 0
    c._req_errors      = 0
    c._last_used       = 0.0
    return c


# ── Tests: _request() actualiza stats ─────────────────────────────────────────

class TestRequestStats(unittest.TestCase):

    def _client_with_response(self, result=None):
        """Cliente que responde inmediatamente con result."""
        c = _make_client()
        orig_send = lambda payload: None  # no-op send

        def _enqueue_response(payload):
            if "id" in payload:
                c._msg_queue.put({"id": payload["id"], "result": result})

        c._send = _enqueue_response
        return c

    def test_request_increments_req_sent(self):
        c = self._client_with_response({"ok": True})
        c._request("test/method", {})
        self.assertEqual(c._req_sent, 1)

    def test_request_updates_last_used(self):
        c = self._client_with_response({"ok": True})
        before = time.monotonic()
        c._request("test/method", {})
        self.assertGreater(c._last_used, before - 0.1)

    def test_request_increments_errors_on_timeout(self):
        c = _make_client()
        c._send = lambda p: None  # no response → timeout
        c._timeout = 0.05
        try:
            c._request("test/method", {})
        except Exception:
            pass
        self.assertEqual(c._req_errors, 1)

    def test_two_requests_accumulate(self):
        c = self._client_with_response(None)
        c._request("m1", {})
        c._request("m2", {})
        self.assertEqual(c._req_sent, 2)


# ── Tests: diagnostics() actualiza stats ────────────────────────────────────

class TestDiagnosticsStats(unittest.TestCase):

    def _client_with_diag(self, path="/tmp/foo.py", diags=None):
        """Cliente que responde al open con un publishDiagnostics."""
        import pathlib
        c = _make_client()
        diags = diags or []
        uri = pathlib.Path(path).as_uri()

        def _fake_send(payload):
            # Cuando recibe didOpen/didChange, encola un publishDiagnostics
            method = payload.get("method", "")
            if method in ("textDocument/didOpen", "textDocument/didChange"):
                c._msg_queue.put({
                    "method": "textDocument/publishDiagnostics",
                    "params": {"uri": uri, "diagnostics": diags},
                })

        c._send = _fake_send
        return c, uri

    def test_diagnostics_increments_req_sent(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("x = 1\n"); path = f.name
        try:
            c, _ = self._client_with_diag(path)
            c.diagnostics(path, wait=0.2)
            self.assertEqual(c._req_sent, 1)
        finally:
            os.unlink(path)

    def test_diagnostics_updates_last_used(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("x = 1\n"); path = f.name
        try:
            c, _ = self._client_with_diag(path)
            before = time.monotonic()
            c.diagnostics(path, wait=0.2)
            self.assertGreater(c._last_used, before - 0.1)
        finally:
            os.unlink(path)

    def test_diagnostics_adds_to_open_files(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("x = 1\n"); path = f.name
        try:
            c, uri = self._client_with_diag(path)
            c.diagnostics(path, wait=0.2)
            self.assertIn(uri, c._open_files)
            self.assertEqual(len(c._open_files), 1)
        finally:
            os.unlink(path)

    def test_diagnostics_two_files_two_open(self):
        import tempfile, os
        files = []
        for _ in range(2):
            f = tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False)
            f.write("x = 1\n"); files.append(f.name); f.close()
        try:
            import pathlib
            c = _make_client()
            def _fake_send(payload):
                method = payload.get("method", "")
                if method in ("textDocument/didOpen", "textDocument/didChange"):
                    # Usa el URI del parámetro enviado
                    td = payload.get("params", {}).get("textDocument", {})
                    uri = td.get("uri", "")
                    c._msg_queue.put({
                        "method": "textDocument/publishDiagnostics",
                        "params": {"uri": uri, "diagnostics": []},
                    })
            c._send = _fake_send
            c.diagnostics(files[0], wait=0.2)
            c.diagnostics(files[1], wait=0.2)
            self.assertEqual(len(c._open_files), 2)
            self.assertEqual(c._req_sent, 2)
        finally:
            for p in files: os.unlink(p)

    def test_diagnostics_same_file_twice_increments_req_sent(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("x = 1\n"); path = f.name
        try:
            c, _ = self._client_with_diag(path)
            c.diagnostics(path, wait=0.2)
            c.diagnostics(path, wait=0.2)
            # req_sent debe ser 2 (dos llamadas), pero open_files sigue siendo 1
            self.assertEqual(c._req_sent, 2)
            self.assertEqual(len(c._open_files), 1)
        finally:
            os.unlink(path)

    def test_diagnostics_returns_cached_on_no_fresh(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("x = 1\n"); path = f.name
        try:
            import pathlib
            c = _make_client()
            uri = pathlib.Path(path).as_uri()
            c._diag_cache[uri] = [{"path": path, "line": 1, "col": 1,
                                   "severity": "error", "message": "cached", "source": "test"}]
            c._send = lambda p: None  # no notifications
            result = c.diagnostics(path, wait=0.05)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["message"], "cached")
        finally:
            os.unlink(path)


# ── Tests: LspPool.status() refleja stats correctos ──────────────────────────

class TestLspPoolStatus(unittest.TestCase):

    def _pool_with_fake_client(self):
        """LspPool con un cliente falso inyectado."""
        from agent.lsp_client import LspPool
        pool = LspPool.__new__(LspPool)
        pool._workspace = "/tmp"
        pool._timeout   = 5.0
        pool._cmds      = {".py": ["pylsp"]}
        pool._clients   = {}
        pool._lock      = threading.Lock()
        c = _make_client()
        c._req_sent  = 3
        c._req_errors = 1
        c._open_files = {"file:///tmp/a.py": 1, "file:///tmp/b.py": 2}
        c._last_used = time.monotonic() - 42.0
        pool._clients[".py"] = c
        return pool, c

    def test_status_returns_requests(self):
        pool, _ = self._pool_with_fake_client()
        s = pool.status()
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]["requests"], 3)

    def test_status_returns_errors(self):
        pool, _ = self._pool_with_fake_client()
        s = pool.status()
        self.assertEqual(s[0]["errors"], 1)

    def test_status_returns_files(self):
        pool, _ = self._pool_with_fake_client()
        s = pool.status()
        self.assertEqual(s[0]["files"], 2)

    def test_status_idle_s_approximation(self):
        pool, _ = self._pool_with_fake_client()
        s = pool.status()
        # idle debería ser ~42s, tolerancia ±3s
        self.assertGreaterEqual(s[0]["idle_s"], 39)
        self.assertLessEqual(s[0]["idle_s"], 45)

    def test_status_idle_s_none_when_never_used(self):
        pool, c = self._pool_with_fake_client()
        c._last_used = 0.0
        s = pool.status()
        self.assertIsNone(s[0]["idle_s"])

    def test_status_alive_true(self):
        pool, c = self._pool_with_fake_client()
        c._started = True
        c._dead    = False
        # proc.poll() == None → is_alive. Simulamos con mock.
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        c._proc = mock_proc
        s = pool.status()
        self.assertTrue(s[0]["alive"])

    def test_status_alive_false_when_dead(self):
        pool, c = self._pool_with_fake_client()
        c._dead = True
        s = pool.status()
        self.assertFalse(s[0]["alive"])

    def test_status_ext_and_cmd(self):
        pool, _ = self._pool_with_fake_client()
        s = pool.status()
        self.assertEqual(s[0]["ext"], ".py")
        self.assertEqual(s[0]["cmd"], "fake-lsp")

    def test_status_after_diagnostics_updates_idle(self):
        """Simula que diagnostics() actualiza last_used y el status lo refleja."""
        pool, c = self._pool_with_fake_client()
        c._last_used = time.monotonic() - 300.0  # antes: 300s de idle
        s_before = pool.status()[0]
        self.assertGreater(s_before["idle_s"], 200)
        # Simular que diagnostics() actualizó last_used
        c._last_used = time.monotonic()
        c._req_sent  += 1
        s_after = pool.status()[0]
        self.assertLessEqual(s_after["idle_s"], 5)
        self.assertEqual(s_after["requests"], 4)


# ── Tests: stats no se actualizan cuando el servidor está muerto ──────────────

class TestDeadClientStats(unittest.TestCase):

    def test_request_raises_when_dead(self):
        from agent.lsp_client import LspError
        c = _make_client()
        c._dead = True
        with self.assertRaises(LspError):
            c._request("test", {})

    def test_req_sent_not_incremented_when_dead(self):
        from agent.lsp_client import LspError
        c = _make_client()
        c._dead = True
        try:
            c._request("test", {})
        except Exception:
            pass
        self.assertEqual(c._req_sent, 0)


if __name__ == "__main__":
    unittest.main()
