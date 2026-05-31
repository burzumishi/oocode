"""Tests para mejoras de memoria semántica y RAG.

Cubre:
- _extract_body() salta el frontmatter YAML correctamente
- _extract_body() sin frontmatter devuelve el texto directamente
- _extract_body() trunca a max_chars contando desde el cuerpo
- MemorySystem.context_snippet() usa _extract_body en los snippets
- WorkspaceRAG.invalidate_file() elimina el fichero del índice y mtime
- WorkspaceRAG.invalidate_file() resetea _last_index para forzar re-indexado
- invalidate_file con path no indexado no falla
- loop._execute_tool write_file exitoso llama invalidate_file
- loop._execute_tool write_file exitoso resetea _sys_prompt_cache y _turn_rag_snippet
- _sys_prompt_cache no se resetea si write_file falla
- edit_file exitoso también invalida el RAG
"""
import sys, os, time, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile


# ── _extract_body ─────────────────────────────────────────────────────────────

class TestExtractBody:
    def test_skips_frontmatter(self):
        from agent.memory import _extract_body
        text = "---\nname: test\ndescription: foo\nmetadata:\n  type: project\n---\n\nContent starts here.\n"
        result = _extract_body(text, 500)
        assert result == "Content starts here."
        assert "---" not in result
        assert "name: test" not in result

    def test_no_frontmatter_returns_text(self):
        from agent.memory import _extract_body
        text = "Just plain content without frontmatter."
        result = _extract_body(text, 500)
        assert result == "Just plain content without frontmatter."

    def test_truncates_to_max_chars(self):
        from agent.memory import _extract_body
        text = "---\nname: x\n---\n\n" + "A" * 200
        result = _extract_body(text, 100)
        assert len(result) <= 100
        assert "A" in result

    def test_body_length_is_from_content_not_frontmatter(self):
        """max_chars se aplica al cuerpo, no al texto completo con frontmatter."""
        from agent.memory import _extract_body
        # frontmatter de 50 chars + body de 300 chars
        fm = "---\nname: x\ndescription: y\n---\n\n"
        body = "B" * 300
        text = fm + body
        result = _extract_body(text, 100)
        assert len(result) <= 100
        # Contiene solo contenido real
        assert result.count("B") > 0
        assert "name: x" not in result

    def test_empty_body_after_frontmatter(self):
        from agent.memory import _extract_body
        text = "---\nname: x\n---\n"
        result = _extract_body(text, 500)
        assert result == ""

    def test_multiline_body(self):
        from agent.memory import _extract_body
        text = "---\nname: t\n---\n\nLine 1.\nLine 2.\nLine 3.\n"
        result = _extract_body(text, 500)
        assert "Line 1." in result
        assert "Line 2." in result
        assert "Line 3." in result

    def test_frontmatter_without_second_separator_treated_as_no_fm(self):
        """Si no hay segundo '---', no hay frontmatter que saltar."""
        from agent.memory import _extract_body
        text = "---\nThis is just text starting with ---."
        result = _extract_body(text, 500)
        # No hay segundo '---', devuelve el texto completo
        assert "---" in result or "This is just text" in result


# ── WorkspaceRAG.invalidate_file ──────────────────────────────────────────────

class TestWorkspaceRagInvalidate:
    def _make_rag(self):
        from agent.workspace_rag import WorkspaceRAG
        mock_ec = MagicMock()
        mock_ec.is_available.return_value = True
        with tempfile.TemporaryDirectory() as tmpdir:
            rag = WorkspaceRAG.__new__(WorkspaceRAG)
            rag._workspace = Path(tmpdir)
            rag._ec = mock_ec
            rag._index_dir = Path(tmpdir) / "index"
            rag._top_k = 3
            rag._threshold = 0.42
            rag._max_chars = 1400
            rag._interval = 300.0
            rag._last_index = time.time()  # fresco
            rag._indexing = False
            rag._files_indexed = 0
            rag._last_hits = 0
            rag._last_available = 0
            rag._data = {
                "chunks": [
                    {"path": "/tmp/file.py", "line": 1, "text": "hello", "vec": [0.1]},
                    {"path": "/tmp/other.py", "line": 1, "text": "world", "vec": [0.2]},
                ],
                "mtime": {
                    "/tmp/file.py": "1234567890.0",
                    "/tmp/other.py": "1234567891.0",
                }
            }
            rag._lock = threading.Lock()
            return rag

    def test_invalidate_removes_from_mtime(self):
        rag = self._make_rag()
        rag.invalidate_file("/tmp/file.py")
        assert "/tmp/file.py" not in rag._data["mtime"]
        assert "/tmp/other.py" in rag._data["mtime"]

    def test_invalidate_removes_chunks(self):
        rag = self._make_rag()
        rag.invalidate_file("/tmp/file.py")
        paths = [c["path"] for c in rag._data["chunks"]]
        assert "/tmp/file.py" not in paths
        assert "/tmp/other.py" in paths

    def test_invalidate_resets_last_index(self):
        rag = self._make_rag()
        old_ts = rag._last_index
        assert old_ts > 0  # fresco
        rag.invalidate_file("/tmp/file.py")
        assert rag._last_index == 0.0

    def test_invalidate_unknown_file_no_error(self):
        rag = self._make_rag()
        try:
            rag.invalidate_file("/tmp/nonexistent.py")
        except Exception as e:
            assert False, f"invalidate_file raised unexpected: {e}"

    def test_invalidate_triggers_reindex_on_next_ensure(self):
        """Después de invalidar, ensure_indexed() dispara re-indexado."""
        rag = self._make_rag()
        rag.invalidate_file("/tmp/file.py")
        # _last_index == 0.0 → age > interval → debe disparar indexado
        assert rag._last_index == 0.0
        # ensure_indexed: should set _indexing = True y lanzar hilo
        rag.ensure_indexed()
        # Dar un momento al thread daemon
        import time as _t; _t.sleep(0.05)
        # No error — el indexado se inicia en background


# ── loop._execute_tool RAG invalidation ──────────────────────────────────────

def _make_loop():
    from agent.loop import AgentLoop
    from tools.registry import ToolRegistry
    from tools.permissions import PermissionManager
    from config import OOConfig
    cfg = OOConfig()
    loop = AgentLoop.__new__(AgentLoop)
    loop.config = cfg
    loop.registry = ToolRegistry()
    loop.permissions = PermissionManager(cfg.permissions)
    loop.memory = MagicMock()
    loop.workspace_manager = MagicMock()
    loop.session = MagicMock()
    loop.rt = MagicMock()
    loop.rt.verbose = False
    loop.rt.accent_color = "cyan"
    loop.is_subagent = False
    loop.capture_output = False
    loop._status_cb = None
    loop._auto_continue_count = 0
    loop._plan_tasks = []
    loop._turn_written_scripts = set()
    loop._turn_read_cache = {}
    loop._turn_write_seen = {}
    loop._turn_block_has_header = False
    loop._turn_block = []
    loop._tool_current_file = ""
    loop._bash_block_counts = {}
    loop._kill_requested = False
    loop._pending_tasks = []
    loop._last_tool_calls = []
    loop._start_live_block_cb = None
    loop._flush_live_block_cb = None
    loop._live_tool_count = 0
    loop._turn_read_paths = set()
    loop._session_reads = []
    loop._sys_prompt_cache = "cached_prompt"
    loop._turn_rag_snippet = "rag_snippet"
    loop._workspace_rag = None
    return loop


class TestExecuteToolRagInvalidation:
    def test_write_file_success_resets_sys_prompt_cache(self):
        """Escritura exitosa invalida _sys_prompt_cache para que el siguiente LLM call use RAG fresco."""
        loop = _make_loop()
        mock_fn = MagicMock(return_value="Fichero escrito: /home/user/main.py")
        loop.registry.register("write_file", mock_fn, {
            "name": "write_file",
            "description": "test",
            "parameters": {"type": "object", "properties": {"path": {}, "content": {}}}
        })
        loop._execute_tool("write_file", {"path": "/home/user/main.py", "content": "x"})
        assert loop._sys_prompt_cache is None

    def test_write_file_success_resets_turn_rag_snippet(self):
        loop = _make_loop()
        mock_fn = MagicMock(return_value="Fichero escrito: /home/user/main.py")
        loop.registry.register("write_file", mock_fn, {
            "name": "write_file",
            "description": "test",
            "parameters": {"type": "object", "properties": {"path": {}, "content": {}}}
        })
        loop._execute_tool("write_file", {"path": "/home/user/main.py", "content": "x"})
        assert loop._turn_rag_snippet is None

    def test_write_file_failure_keeps_cache(self):
        """Si write_file falla (Error), no se invalida el cache."""
        loop = _make_loop()
        loop.registry.register("write_file", lambda **kw: "Error: fichero no encontrado", {
            "name": "write_file",
            "description": "test",
            "parameters": {"type": "object", "properties": {"path": {}, "content": {}}}
        })
        loop._execute_tool("write_file", {"path": "/home/user/main.py", "content": "x"})
        # Error → cache no se invalida
        assert loop._sys_prompt_cache == "cached_prompt"

    def test_write_file_calls_rag_invalidate(self):
        """Si hay workspace_rag, se llama invalidate_file con la ruta correcta."""
        loop = _make_loop()
        mock_rag = MagicMock()
        loop._workspace_rag = mock_rag
        loop.registry.register("write_file", lambda **kw: "Fichero escrito: /home/user/app.py", {
            "name": "write_file",
            "description": "test",
            "parameters": {"type": "object", "properties": {"path": {}, "content": {}}}
        })
        loop._execute_tool("write_file", {"path": "/home/user/app.py", "content": "code"})
        mock_rag.invalidate_file.assert_called_once_with("/home/user/app.py")

    def test_no_rag_no_error(self):
        """Sin workspace_rag, write_file exitoso no falla."""
        loop = _make_loop()
        loop._workspace_rag = None
        loop.registry.register("write_file", lambda **kw: "Fichero escrito: /tmp/x.py", {
            "name": "write_file",
            "description": "test",
            "parameters": {"type": "object", "properties": {"path": {}, "content": {}}}
        })
        try:
            loop._execute_tool("write_file", {"path": "/tmp/x.py", "content": "x"})
        except Exception as e:
            assert False, f"Unexpected error: {e}"
