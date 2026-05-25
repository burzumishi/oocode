"""Tests de mem_save, _execute_mem_save, _auto_save_task_memory (sin LLM)."""
import sys
import json
import shutil
import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Fixture: AgentLoop mínimo ────────────────────────────────────────────────

@pytest.fixture
def tmp_mem_dir(tmp_path):
    d = tmp_path / "memory"
    d.mkdir()
    return d


@pytest.fixture
def loop(tmp_mem_dir):
    """AgentLoop con memoria real en directorio temporal."""
    with patch("ollama.Client"), \
         patch("agent.loop.ToolRegistry"), \
         patch("agent.loop.PermissionManager"), \
         patch("agent.loop.SessionManager"), \
         patch("agent.loop.ConversationContext"), \
         patch("agent.loop.WorkspaceManager"), \
         patch("agent.loop.ChatLogger"):
        from agent.loop import AgentLoop
        from agent.memory import MemorySystem
        from config import OOConfig

        mem = MemorySystem(embed_client=None, memory_dir=tmp_mem_dir)
        cfg = OOConfig(model="test", workspace="/tmp")

        lp = AgentLoop.__new__(AgentLoop)
        lp.memory              = mem
        lp.config              = cfg
        lp.capture_output      = False
        lp._tool_phase         = ""
        lp._last_tool_calls    = []
        lp._turn_written_scripts = set()
        lp._turn_read_paths    = set()
        lp._empty_search_streak  = 0
        lp._empty_search_patterns = []
        lp._turn_read_cache    = {}
        lp._turn_write_seen    = {}
        lp._status_cb          = None
        lp._session_reads      = []
        lp._session_mems       = []
        lp._clear_output_cb    = None
        lp.is_subagent         = False
        lp.rt                  = MagicMock()
        lp.rt.verbose          = False
        return lp


# ── _execute_mem_save ────────────────────────────────────────────────────────

class TestExecuteMemSave:
    def test_saves_memory_file(self, loop, tmp_mem_dir):
        result = loop._execute_mem_save({
            "name": "test_memory",
            "content": "# Test\nImportant fact",
            "description": "A test memory",
        })
        assert "wrote 1 memory" in result
        assert "test_memory" in result
        assert (tmp_mem_dir / "test_memory.md").exists()

    def test_result_contains_recall_count(self, loop):
        result = loop._execute_mem_save({
            "name": "new_mem",
            "content": "content here",
        })
        assert "Recalled" in result
        assert "wrote 1 memory" in result

    def test_clears_tool_phase_after_save(self, loop):
        loop._execute_mem_save({"name": "x", "content": "y"})
        assert loop._tool_phase == ""

    def test_sets_tool_phase_during_execution(self, loop, tmp_mem_dir):
        """Verifica que _tool_phase se actualiza con las fases de progreso."""
        phases_seen = []

        original_save = loop.memory.save
        def intercept_save(name, content, description=""):
            phases_seen.append(loop._tool_phase)
            return original_save(name, content, description)

        loop.memory.save = intercept_save
        loop._execute_mem_save({"name": "phase_test", "content": "data"})

        assert len(phases_seen) == 1
        assert "writing" in phases_seen[0].lower() or "memory" in phases_seen[0].lower()

    def test_memory_file_content_correct(self, loop, tmp_mem_dir):
        loop._execute_mem_save({
            "name": "project_facts",
            "content": "# Facts\n- Fact 1\n- Fact 2",
            "description": "Key project facts",
        })
        saved = (tmp_mem_dir / "project_facts.md").read_text()
        assert "Fact 1" in saved

    def test_index_updated(self, loop, tmp_mem_dir):
        loop._execute_mem_save({
            "name": "arch_decisions",
            "content": "Use PostgreSQL",
            "description": "Architecture choices",
        })
        index = (tmp_mem_dir / "MEMORY.md").read_text()
        assert "arch_decisions" in index


# ── _auto_save_task_memory ───────────────────────────────────────────────────

class TestAutoSaveTaskMemory:
    def test_skips_when_no_tool_calls(self, loop, tmp_mem_dir):
        loop._last_tool_calls = []
        loop._auto_save_task_memory(["Good response"])
        assert not list(tmp_mem_dir.glob("task_*.md"))

    def test_skips_when_too_few_calls(self, loop, tmp_mem_dir):
        loop._last_tool_calls = [
            ("read_file", "{}", "content"),
            ("grep_code", "{}", "found"),
            ("bash",      "{}", "ok"),
        ]
        loop._auto_save_task_memory(["Short response"])
        assert not list(tmp_mem_dir.glob("task_*.md"))

    def test_skips_when_no_writes(self, loop, tmp_mem_dir):
        loop._last_tool_calls = [
            ("bash",      "{}", "ok"),
            ("read_file", "{}", "content"),
            ("grep_code", "{}", "found"),
            ("bash",      "{}", "ok"),
            ("bash",      "{}", "ok"),
        ]
        loop._auto_save_task_memory(["No writes happened here."])
        assert not list(tmp_mem_dir.glob("task_*.md"))

    def test_saves_when_significant_task(self, loop, tmp_mem_dir):
        loop._last_tool_calls = [
            ("read_file", '{"path":"/src/main.py"}', "content"),
            ("grep_code", "{}", "found"),
            ("edit_file", '{"path":"/src/main.py"}', "edited"),
            ("bash",      "{}", "ok"),
            ("bash",      "{}", "ok"),
        ]
        loop._auto_save_task_memory([
            "I updated the main.py file to fix the login bug. "
            "The issue was in the authentication middleware."
        ])
        saved = list(tmp_mem_dir.glob("task_*.md"))
        assert len(saved) == 1
        content = saved[0].read_text()
        assert "login" in content or "authentication" in content

    def test_skips_when_mem_save_already_called(self, loop, tmp_mem_dir):
        loop._last_tool_calls = [
            ("edit_file", '{"path":"/src/x.py"}', "ok"),
            ("bash",      "{}", "ok"),
            ("bash",      "{}", "ok"),
            ("bash",      "{}", "ok"),
            ("mem_save",  '{"name":"x"}', "saved"),
        ]
        loop._auto_save_task_memory(["Task done. Important findings saved."])
        assert not list(tmp_mem_dir.glob("task_*.md"))

    def test_skips_capture_output_mode(self, loop, tmp_mem_dir):
        loop.capture_output = True
        loop._last_tool_calls = [
            ("edit_file", '{"path":"/src/x.py"}', "ok"),
            ("bash", "{}", "ok"), ("bash", "{}", "ok"),
            ("bash", "{}", "ok"), ("bash", "{}", "ok"),
        ]
        loop._auto_save_task_memory(["Significant task completed."])
        assert not list(tmp_mem_dir.glob("task_*.md"))
        loop.capture_output = False

    def test_skips_short_response(self, loop, tmp_mem_dir):
        loop._last_tool_calls = [
            ("edit_file", '{"path":"/src/x.py"}', "ok"),
            ("bash", "{}", "ok"), ("bash", "{}", "ok"),
            ("bash", "{}", "ok"), ("bash", "{}", "ok"),
        ]
        loop._auto_save_task_memory(["Done."])  # muy corta
        assert not list(tmp_mem_dir.glob("task_*.md"))


# ── Display names y _MEM_TOOLS ───────────────────────────────────────────────

class TestMemToolAttributes:
    def test_mem_save_in_display_names(self):
        from agent.loop import AgentLoop
        assert "mem_save" in AgentLoop._TOOL_DISPLAY_NAMES
        assert AgentLoop._TOOL_DISPLAY_NAMES["mem_save"] == "Memory"

    def test_workspace_remember_in_display_names(self):
        from agent.loop import AgentLoop
        assert "workspace_remember" in AgentLoop._TOOL_DISPLAY_NAMES
        assert AgentLoop._TOOL_DISPLAY_NAMES["workspace_remember"] == "OOCODE"

    def test_mem_tools_frozenset(self):
        from agent.loop import AgentLoop
        assert "mem_save" in AgentLoop._MEM_TOOLS
        assert "workspace_remember" in AgentLoop._MEM_TOOLS


# ── _show_compact_reset ──────────────────────────────────────────────────────

class TestShowCompactReset:
    def test_session_reads_cleared_after_reset(self, loop, tmp_mem_dir):
        loop._session_reads = [
            ("/src/main.py", 120, False),
            ("/src/util.py", None, True),
        ]
        cleared = []
        loop._clear_output_cb = lambda: cleared.append(True)

        with patch("ui.renderer.print_compact_banner"):
            loop._show_compact_reset(5, 1000, False)

        assert loop._session_reads == []

    def test_clear_output_cb_called(self, loop):
        called = []
        loop._clear_output_cb = lambda: called.append(True)
        loop._session_reads = []

        with patch("ui.renderer.print_compact_banner"):
            loop._show_compact_reset(3, 500, False)

        assert called == [True]

    def test_no_crash_without_clear_cb(self, loop):
        loop._clear_output_cb = None
        loop._session_reads = []

        with patch("ui.renderer.print_compact_banner"), \
             patch("sys.stdout") as mock_stdout:
            loop._show_compact_reset(2, 300, False)

        mock_stdout.write.assert_called()

    def test_session_reads_tracked_in_execute_tool(self, loop, tmp_mem_dir):
        """read_file exitoso se registra en _session_reads."""
        from unittest.mock import MagicMock
        loop.registry = MagicMock()
        loop.registry.call.return_value = "línea1\nlínea2\nlínea3"

        loop._execute_tool("read_file", {"path": "/src/main.py"})

        assert len(loop._session_reads) == 1
        path, n_lines, is_edit = loop._session_reads[0]
        assert path == "/src/main.py"
        assert n_lines == 3
        assert is_edit is False

    def test_write_tool_tracked_in_execute_tool(self, loop, tmp_mem_dir):
        """edit_file exitoso se registra en _session_reads como edición."""
        from unittest.mock import MagicMock
        loop.registry = MagicMock()
        loop.registry.call.return_value = "Fichero editado."

        loop._turn_read_paths.add("/src/main.py")
        loop._execute_tool("edit_file", {"path": "/src/main.py"})

        assert len(loop._session_reads) == 1
        path, n_lines, is_edit = loop._session_reads[0]
        assert path == "/src/main.py"
        assert n_lines is None
        assert is_edit is True

    def test_compact_banner_exists(self):
        from ui.renderer import print_compact_banner, LOGO_COMPACT
        assert len(LOGO_COMPACT) == 3
        assert callable(print_compact_banner)

    def test_session_mems_shown_in_compact_reset(self, loop):
        """Memorias guardadas aparecen en el reset visual de compactación."""
        loop._session_reads = []
        loop._session_mems  = ["arch_decisions", "bug_fix_auth"]
        captured = []
        loop._clear_output_cb = lambda: None

        with patch("ui.renderer.print_compact_banner"), \
             patch("ui.console.console") as mock_con:
            mock_con.print = lambda *a, **kw: captured.append(str(a))
            loop._show_compact_reset(5, 1000, False)

        assert loop._session_mems == []
        full = " ".join(captured)
        assert "arch_decisions" in full or "Memory saved" in full

    def test_session_mems_cleared_after_reset(self, loop):
        """_session_mems se vacía tras _show_compact_reset."""
        loop._session_reads = []
        loop._session_mems  = ["my_memory"]
        loop._clear_output_cb = lambda: None

        with patch("ui.renderer.print_compact_banner"), \
             patch("ui.console.console"):
            loop._show_compact_reset(1, 100, False)

        assert loop._session_mems == []

    def test_execute_mem_save_registers_in_session_mems(self, loop, tmp_mem_dir):
        """_execute_mem_save añade el nombre a _session_mems."""
        loop._execute_mem_save({"name": "my_fact", "content": "important"})
        assert "my_fact" in loop._session_mems


# ── Filtrado de secciones de hooks en _show_tool_block ───────────────────────

class TestShowToolBlockHookFiltering:
    """_show_tool_block no muestra secciones [Lint]/[LSP] que los hooks ya mostraron."""

    @pytest.fixture
    def loop_display(self, tmp_mem_dir):
        """AgentLoop mínimo con captura de output."""
        with patch("ollama.Client"), \
             patch("agent.loop.ToolRegistry"), \
             patch("agent.loop.PermissionManager"), \
             patch("agent.loop.SessionManager"), \
             patch("agent.loop.ConversationContext"), \
             patch("agent.loop.WorkspaceManager"), \
             patch("agent.loop.ChatLogger"):
            from agent.loop import AgentLoop
            from agent.memory import MemorySystem
            from agent.runtime import RuntimeSettings
            from config import OOConfig

            lp = AgentLoop.__new__(AgentLoop)
            lp.capture_output      = False
            lp.is_subagent         = False
            lp.rt                  = RuntimeSettings()
            lp.rt.verbose          = False
            lp._MEM_TOOLS          = AgentLoop._MEM_TOOLS
            lp._TOOL_DISPLAY_NAMES = AgentLoop._TOOL_DISPLAY_NAMES
            return lp

    def test_lint_section_not_shown_in_update_block(self, loop_display):
        """[Lint] añadido por el hook no aparece en el ● Update display."""
        displayed = []
        loop_display._print = lambda *a, **kw: displayed.append(str(a))

        result = (
            "Edición aplicada en '/src/news.h'.\n\n"
            "[Lint] /src/news.h:\n  ✗  cppcheck (rc=-1):\n     Timeout (30s)"
        )
        loop_display._show_tool_block("edit_file", {"path": "/src/news.h"}, result, allowed=True)

        full = " ".join(displayed)
        assert "Edición aplicada" in full
        assert "[Lint]" not in full
        assert "cppcheck" not in full

    def test_lsp_section_not_shown_in_update_block(self, loop_display):
        """[LSP Diagnósticos] añadido por el hook no aparece en el display."""
        displayed = []
        loop_display._print = lambda *a, **kw: displayed.append(str(a))

        result = (
            "Fichero guardado.\n\n"
            "[LSP Diagnósticos] /src/main.py:\n  ERROR: undefined variable"
        )
        loop_display._show_tool_block("write_file", {"path": "/src/main.py"}, result, allowed=True)

        full = " ".join(displayed)
        assert "Fichero guardado" in full
        assert "[LSP Diagnósticos]" not in full

    def test_result_without_hook_section_shown_fully(self, loop_display):
        """Resultado sin secciones de hook se muestra completo."""
        displayed = []
        loop_display._print = lambda *a, **kw: displayed.append(str(a))

        result = "Edición aplicada en '/src/main.py'."
        loop_display._show_tool_block("edit_file", {"path": "/src/main.py"}, result, allowed=True)

        full = " ".join(displayed)
        assert "Edición aplicada" in full


# ── /mem slash-command handlers (usan memory._dir, no MEMORY_DIR global) ─────

@pytest.fixture
def mem(tmp_path):
    """MemorySystem real con directorio per-agente temporal."""
    from agent.memory import MemorySystem
    d = tmp_path / "memory" / "main"
    d.mkdir(parents=True)
    return MemorySystem(embed_client=None, memory_dir=d)


class TestMemCommandHandlers:
    """Verifica que _mem_list, _mem_rm, _mem_rebuild, _mem_clear y
    _remove_from_index operan sobre memory._dir (per-agente), no MEMORY_DIR global."""

    def _save_raw(self, mem, name: str, content: str = "test content") -> None:
        mem.save(name, content, description="test")

    def test_mem_list_uses_agent_dir(self, mem):
        self._save_raw(mem, "fact_one", "# Fact 1")
        self._save_raw(mem, "fact_two", "# Fact 2")
        names = mem.list_all()
        assert "fact_one.md" in names
        assert "fact_two.md" in names

    def test_mem_rm_removes_from_agent_dir(self, mem):
        self._save_raw(mem, "to_delete", "content")
        md_path = mem._dir / "to_delete.md"
        assert md_path.exists()

        from ui.commands import _mem_rm
        with patch("ui.commands._tui_ask", return_value="s"), \
             patch("ui.commands.console"):
            _mem_rm("to_delete", mem)

        assert not md_path.exists()

    def test_mem_rm_clears_vec_cache(self, mem):
        self._save_raw(mem, "cached_mem", "data")
        mem._vec_cache["cached_mem.md"] = [0.1, 0.2, 0.3]

        from ui.commands import _mem_rm
        with patch("ui.commands._tui_ask", return_value="s"), \
             patch("ui.commands.console"):
            _mem_rm("cached_mem", mem)

        assert "cached_mem.md" not in mem._vec_cache

    def test_mem_rm_resets_file_list_cache(self, mem):
        self._save_raw(mem, "x", "data")
        mem._file_list_ts = 9999999.0

        from ui.commands import _mem_rm
        with patch("ui.commands._tui_ask", return_value="s"), \
             patch("ui.commands.console"):
            _mem_rm("x", mem)

        assert mem._file_list_ts == 0.0

    def test_mem_rm_also_deletes_emb(self, mem):
        self._save_raw(mem, "emb_mem", "data")
        emb_path = mem._dir / "emb_mem.emb.json"
        emb_path.write_text("[0.1,0.2]")

        from ui.commands import _mem_rm
        with patch("ui.commands._tui_ask", return_value="s"), \
             patch("ui.commands.console"):
            _mem_rm("emb_mem", mem)

        assert not emb_path.exists()

    def test_mem_rm_updates_index(self, mem):
        self._save_raw(mem, "indexed_mem", "content")
        assert "indexed_mem" in mem._index.read_text()

        from ui.commands import _mem_rm
        with patch("ui.commands._tui_ask", return_value="s"), \
             patch("ui.commands.console"):
            _mem_rm("indexed_mem", mem)

        assert "indexed_mem" not in mem._index.read_text()

    def test_mem_rm_cancelled_leaves_file(self, mem):
        self._save_raw(mem, "keep_me", "data")
        from ui.commands import _mem_rm
        with patch("ui.commands._tui_ask", return_value="n"), \
             patch("ui.commands.console"):
            _mem_rm("keep_me", mem)

        assert (mem._dir / "keep_me.md").exists()

    def test_mem_clear_removes_all(self, mem):
        for name in ("alpha", "beta", "gamma"):
            self._save_raw(mem, name, "content")
        assert len(mem.list_all()) == 3

        from ui.commands import _mem_clear
        with patch("ui.commands._tui_ask", return_value="s"), \
             patch("ui.commands.console"):
            _mem_clear(mem)

        assert mem.list_all() == []

    def test_mem_clear_resets_vec_cache(self, mem):
        self._save_raw(mem, "a", "data")
        mem._vec_cache["a.md"] = [0.5]

        from ui.commands import _mem_clear
        with patch("ui.commands._tui_ask", return_value="s"), \
             patch("ui.commands.console"):
            _mem_clear(mem)

        assert mem._vec_cache == {}

    def test_mem_clear_resets_file_list_ts(self, mem):
        self._save_raw(mem, "b", "data")
        mem._file_list_ts = 9999999.0

        from ui.commands import _mem_clear
        with patch("ui.commands._tui_ask", return_value="s"), \
             patch("ui.commands.console"):
            _mem_clear(mem)

        assert mem._file_list_ts == 0.0

    def test_mem_clear_rewrites_index(self, mem):
        self._save_raw(mem, "z", "data")
        assert "z.md" in mem._index.read_text()

        from ui.commands import _mem_clear
        with patch("ui.commands._tui_ask", return_value="s"), \
             patch("ui.commands.console"):
            _mem_clear(mem)

        idx = mem._index.read_text()
        assert "z.md" not in idx
        assert "Memory Index" in idx

    def test_mem_rebuild_updates_vec_cache(self, mem):
        self._save_raw(mem, "rebuild_me", "important content")
        mock_embed = MagicMock()
        mock_embed.is_available.return_value = True
        mock_embed.embed.return_value = [0.1, 0.2, 0.3]
        mem._embed = mock_embed

        from ui.commands import _mem_rebuild
        with patch("ui.commands.console"):
            _mem_rebuild(mem)

        assert "rebuild_me.md" in mem._vec_cache
        assert mem._vec_cache["rebuild_me.md"] == [0.1, 0.2, 0.3]

    def test_mem_rebuild_writes_emb_json(self, mem):
        self._save_raw(mem, "needs_emb", "data to embed")
        mock_embed = MagicMock()
        mock_embed.is_available.return_value = True
        mock_embed.embed.return_value = [0.9, 0.8, 0.7]
        mem._embed = mock_embed

        from ui.commands import _mem_rebuild
        with patch("ui.commands.console"):
            _mem_rebuild(mem)

        emb_path = mem._dir / "needs_emb.emb.json"
        assert emb_path.exists()
        import json as _json
        assert _json.loads(emb_path.read_text()) == [0.9, 0.8, 0.7]

    def test_mem_rebuild_resets_file_list_ts(self, mem):
        self._save_raw(mem, "ts_test", "data")
        mem._file_list_ts = 9999999.0
        mock_embed = MagicMock()
        mock_embed.is_available.return_value = True
        mock_embed.embed.return_value = [0.1]
        mem._embed = mock_embed

        from ui.commands import _mem_rebuild
        with patch("ui.commands.console"):
            _mem_rebuild(mem)

        assert mem._file_list_ts == 0.0

    def test_remove_from_index_uses_memory_index(self, mem):
        self._save_raw(mem, "to_remove", "content")
        assert "to_remove" in mem._index.read_text()

        from ui.commands import _remove_from_index
        _remove_from_index("to_remove.md", mem)

        assert "to_remove" not in mem._index.read_text()

    def test_mem_save_slash_uses_agent_dir(self, mem):
        from types import SimpleNamespace
        agent_loop = SimpleNamespace(memory=mem)

        from ui.commands import _mem_save
        with patch("ui.commands._tui_ask", side_effect=["My content here", "Test desc"]), \
             patch("ui.commands.console"):
            _mem_save("my_note", agent_loop)

        assert (mem._dir / "my_note.md").exists()
        assert "My content" in (mem._dir / "my_note.md").read_text()
