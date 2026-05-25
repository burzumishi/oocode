"""Tests para el task progress panel: _plan_tasks, _advance_plan_task, _set_plan_task_active,
_turn_guidance plan injection, spinner label, y hook quick_syntax_after_write."""
import time
import unittest
from unittest.mock import MagicMock, patch


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_loop():
    """Construye un AgentLoop mínimo para tests sin conexión a Ollama."""
    from agent.loop import AgentLoop
    from config import OOConfig
    cfg = OOConfig(model="test-model", ollama_host="http://localhost:11434")
    loop = AgentLoop.__new__(AgentLoop)
    # Estado mínimo requerido
    loop.config       = cfg
    loop.capture_output = False
    loop.is_subagent  = False
    loop._plan_tasks  = []
    loop._auto_continue_count = 0
    loop._last_tool_calls = []
    loop._pending_tasks   = []
    loop._empty_search_streak  = 0
    loop._empty_search_patterns = []
    loop._failed_edit_streak   = 0
    loop._failed_edit_patterns = []
    loop._turn_read_cache  = {}
    loop._turn_write_seen  = {}
    loop._turn_written_scripts = set()
    loop._status_cb    = None
    loop._sep_label    = ""
    loop.memory        = MagicMock(last_hits=0)
    loop._workspace_rag = None
    loop._turn_inp     = 0
    return loop


def _make_tasks(texts):
    return [{"text": t, "status": "pending", "start_ts": 0.0, "end_ts": 0.0}
            for t in texts]


# ── Tests: _set_plan_task_active ──────────────────────────────────────────────

class TestSetPlanTaskActive(unittest.TestCase):

    def _loop_with_tasks(self, n=4):
        loop = _make_loop()
        loop._plan_tasks = _make_tasks([f"Tarea {i+1}" for i in range(n)])
        loop._plan_tasks[0]["status"] = "active"
        loop._plan_tasks[0]["start_ts"] = time.time()
        return loop

    def test_first_task_active_on_init(self):
        loop = self._loop_with_tasks(3)
        self.assertEqual(loop._plan_tasks[0]["status"], "active")
        self.assertEqual(loop._plan_tasks[1]["status"], "pending")
        self.assertEqual(loop._plan_tasks[2]["status"], "pending")

    def test_advance_to_second(self):
        loop = self._loop_with_tasks(3)
        loop._set_plan_task_active(1)
        self.assertEqual(loop._plan_tasks[0]["status"], "done")
        self.assertEqual(loop._plan_tasks[1]["status"], "active")
        self.assertEqual(loop._plan_tasks[2]["status"], "pending")

    def test_advance_to_last(self):
        loop = self._loop_with_tasks(3)
        loop._set_plan_task_active(2)
        self.assertEqual(loop._plan_tasks[0]["status"], "done")
        self.assertEqual(loop._plan_tasks[1]["status"], "done")
        self.assertEqual(loop._plan_tasks[2]["status"], "active")

    def test_end_ts_set_when_done(self):
        loop = self._loop_with_tasks(2)
        before = time.time()
        loop._set_plan_task_active(1)
        after = time.time()
        ts = loop._plan_tasks[0]["end_ts"]
        self.assertGreaterEqual(ts, before)
        self.assertLessEqual(ts, after)

    def test_active_task_gets_start_ts(self):
        loop = self._loop_with_tasks(3)
        # tarea 2 no tiene start_ts
        self.assertEqual(loop._plan_tasks[1]["start_ts"], 0.0)
        loop._set_plan_task_active(1)
        self.assertGreater(loop._plan_tasks[1]["start_ts"], 0.0)

    def test_idempotent_already_active(self):
        loop = self._loop_with_tasks(2)
        # Llamar 2 veces: no debe cambiar estado
        loop._set_plan_task_active(0)
        loop._set_plan_task_active(0)
        self.assertEqual(loop._plan_tasks[0]["status"], "active")
        self.assertEqual(loop._plan_tasks[1]["status"], "pending")


# ── Tests: _advance_plan_task ─────────────────────────────────────────────────

class TestAdvancePlanTask(unittest.TestCase):

    def _loop_with_tasks(self, n=4):
        loop = _make_loop()
        loop._plan_tasks = _make_tasks([f"Tarea {i+1}: descripción larga de la tarea" for i in range(n)])
        loop._plan_tasks[0]["status"] = "active"
        loop._plan_tasks[0]["start_ts"] = time.time()
        return loop

    def test_no_tasks_noop(self):
        loop = _make_loop()
        # No debe lanzar excepción
        loop._advance_plan_task("Tarea 2: hola")

    def test_explicit_tarea_n_advances(self):
        loop = self._loop_with_tasks(4)
        loop._advance_plan_task("Tarea 3: reviso los tests")
        self.assertEqual(loop._plan_tasks[0]["status"], "done")
        self.assertEqual(loop._plan_tasks[1]["status"], "done")
        self.assertEqual(loop._plan_tasks[2]["status"], "active")
        self.assertEqual(loop._plan_tasks[3]["status"], "pending")

    def test_explicit_paso_n_advances(self):
        loop = self._loop_with_tasks(3)
        loop._advance_plan_task("Paso 2: implementando mejoras")
        self.assertEqual(loop._plan_tasks[0]["status"], "done")
        self.assertEqual(loop._plan_tasks[1]["status"], "active")

    def test_out_of_range_uses_fallback(self):
        loop = self._loop_with_tasks(3)
        loop._auto_continue_count = 1
        # Tarea 99 no existe → fallback a auto_continue_count
        loop._advance_plan_task("Tarea 99: imposible")
        # fallback: min(1, 2) = 1 → segunda tarea activa
        self.assertEqual(loop._plan_tasks[1]["status"], "active")

    def test_fallback_uses_auto_continue_count(self):
        loop = self._loop_with_tasks(4)
        loop._auto_continue_count = 2
        loop._advance_plan_task("texto sin anuncio explícito")
        # target = min(2, 3) = 2
        self.assertEqual(loop._plan_tasks[2]["status"], "active")

    def test_text_beyond_300_ignored(self):
        loop = self._loop_with_tasks(3)
        # Anuncio de "Tarea 2" está en posición > 300 → no se detecta
        padding = "a" * 301
        loop._advance_plan_task(padding + " Tarea 2: hola")
        # Fallback: auto_continue_count=0 → tarea 0 sigue activa
        self.assertEqual(loop._plan_tasks[0]["status"], "active")

    def test_case_insensitive(self):
        loop = self._loop_with_tasks(3)
        loop._advance_plan_task("TAREA 2: mayúsculas")
        self.assertEqual(loop._plan_tasks[1]["status"], "active")


# ── Tests: _turn_guidance con plan activo ─────────────────────────────────────

class TestTurnGuidancePlanInjection(unittest.TestCase):

    def _loop_with_active_plan(self, n=3, active_idx=1):
        loop = _make_loop()
        loop._plan_tasks = _make_tasks([f"Tarea {i+1} del plan" for i in range(n)])
        loop._plan_tasks[active_idx]["status"] = "active"
        for i in range(active_idx):
            loop._plan_tasks[i]["status"] = "done"
        loop._last_tool_calls = [("read_file", "{}", "ok")]  # simula iteración no-primera
        return loop

    def test_plan_status_injected_when_tasks_and_tool_calls(self):
        loop = self._loop_with_active_plan(3, active_idx=1)
        guidance = loop._turn_guidance()
        self.assertIn("📋 PLAN EN CURSO", guidance)
        self.assertIn("2/3", guidance)

    def test_plan_shows_checkmarks_for_done(self):
        loop = self._loop_with_active_plan(3, active_idx=1)
        guidance = loop._turn_guidance()
        self.assertIn("✔", guidance)  # tarea 0 done
        self.assertIn("◼", guidance)  # tarea 1 active
        self.assertIn("◻", guidance)  # tarea 2 pending

    def test_next_task_hint_present(self):
        loop = self._loop_with_active_plan(3, active_idx=1)
        guidance = loop._turn_guidance()
        self.assertIn("Tarea 3", guidance)

    def test_last_task_no_next_hint(self):
        loop = self._loop_with_active_plan(3, active_idx=2)
        guidance = loop._turn_guidance()
        self.assertIn("última tarea", guidance)
        self.assertNotIn("Tarea 4", guidance)

    def test_no_plan_tasks_no_injection(self):
        loop = _make_loop()
        loop._last_tool_calls = [("read_file", "{}", "ok")]
        guidance = loop._turn_guidance()
        self.assertNotIn("📋 PLAN EN CURSO", guidance)

    def test_no_tool_calls_no_plan_injection(self):
        loop = _make_loop()
        loop._plan_tasks = _make_tasks(["Tarea 1", "Tarea 2"])
        loop._plan_tasks[0]["status"] = "active"
        loop._last_tool_calls = []  # primera iteración
        guidance = loop._turn_guidance()
        # No debe inyectar "PLAN EN CURSO" (solo en iteraciones con tool calls)
        self.assertNotIn("📋 PLAN EN CURSO", guidance)


# ── Tests: task panel en status window (lógica, sin TUI real) ─────────────────

class TestStatusWindowHeight(unittest.TestCase):

    def _make_app(self, n_tasks=0):
        """Crea mock de OOCodeApp con _plan_tasks."""
        from ui.app import OOCodeApp
        app = OOCodeApp.__new__(OOCodeApp)
        mock_loop = MagicMock()
        mock_loop._plan_tasks = _make_tasks([f"t{i}" for i in range(n_tasks)])
        app._agent_loop = mock_loop
        return app

    def test_no_tasks_height_3(self):
        app = self._make_app(0)
        self.assertEqual(app._status_window_height(), 3)

    def test_3_tasks_height_5(self):
        app = self._make_app(3)
        # spinner(1) + 3 tasks + summary(1) = 5  (sin tip cuando tasks activas)
        self.assertEqual(app._status_window_height(), 5)

    def test_7_tasks_height_7(self):
        app = self._make_app(7)
        # spinner(1) + 5 visible (max) + summary(1) = 7
        self.assertEqual(app._status_window_height(), 7)

    def test_10_tasks_clamped_to_7(self):
        app = self._make_app(10)
        # spinner(1) + 5 visible (max) + summary(1) = 7
        self.assertEqual(app._status_window_height(), 7)


# ── Tests: quick_syntax_after_write hook ─────────────────────────────────────

class TestQuickSyntaxHook(unittest.TestCase):

    def _hook(self):
        from tools.hooks import _builtin_quick_syntax_after_write
        return _builtin_quick_syntax_after_write

    def test_non_write_tool_ignored(self):
        hook = self._hook()
        res = hook("read_file", {"file_path": "/tmp/test.py"}, "ok")
        self.assertIsNone(res)

    def test_error_result_ignored(self):
        hook = self._hook()
        res = hook("write_file", {"file_path": "/tmp/test.py"}, "Error: algo falló")
        self.assertIsNone(res)

    def test_non_py_file_ignored(self):
        hook = self._hook()
        res = hook("write_file", {"file_path": "/tmp/test.js"}, "ok")
        self.assertIsNone(res)

    def test_valid_py_returns_none(self):
        import tempfile, os
        hook = self._hook()
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("def foo():\n    return 42\n")
            f.flush()
            path = f.name
        try:
            res = hook("write_file", {"file_path": path}, "ok")
            self.assertIsNone(res)
        finally:
            os.unlink(path)

    def test_syntax_error_py_returns_warning(self):
        import tempfile, os
        hook = self._hook()
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("def foo(:\n    pass\n")  # syntax error: missing )
            f.flush()
            path = f.name
        try:
            res = hook("write_file", {"file_path": path}, "ok")
            self.assertIsNotNone(res)
            self.assertIn("SyntaxError", res)
        finally:
            os.unlink(path)

    def test_edit_files_multi_path_checked(self):
        import tempfile, os
        hook = self._hook()
        # Crea un fichero con error y otro válido
        files = []
        for src in ["def ok(): pass\n", "def bad(:\n    pass\n"]:
            f = tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False)
            f.write(src); f.flush()
            files.append(f.name)
            f.close()
        try:
            args = {"edits": [{"path": files[0]}, {"path": files[1]}]}
            res = hook("edit_files", args, "ok")
            self.assertIsNotNone(res)
            self.assertIn("SyntaxError", res)
        finally:
            for p in files:
                os.unlink(p)

    def test_hook_registered_in_builtins(self):
        from tools.hooks import _BUILTINS
        self.assertIn("quick_syntax_after_write", _BUILTINS)

    def test_hook_in_default_config(self):
        from config import DEFAULT_CONFIG
        builtins = DEFAULT_CONFIG["hooks"]["builtins"]
        self.assertIn("quick_syntax_after_write", builtins)


# ── Tests: _plan_tasks init en run() (detección) ──────────────────────────────

class TestPlanTasksInit(unittest.TestCase):

    def test_detect_tasks_populates_plan(self):
        """Verifica que _detect_tasks produce la lista correcta."""
        from agent.loop import AgentLoop
        tasks = AgentLoop._detect_tasks(
            "Necesito que hagas:\n"
            "1. Analizar el código existente\n"
            "2. Implementar las mejoras\n"
            "3. Ejecutar los tests\n"
        )
        self.assertEqual(len(tasks), 3)
        self.assertIn("Analizar", tasks[0])

    def test_single_item_not_detected(self):
        from agent.loop import AgentLoop
        tasks = AgentLoop._detect_tasks("1. Solo una tarea larga aquí")
        self.assertEqual(tasks, [])

    def test_plan_tasks_structure(self):
        """La estructura de _plan_tasks es correcta."""
        tasks_text = ["Analizar código", "Implementar mejoras"]
        tasks = [{"text": t, "status": "pending", "start_ts": 0.0, "end_ts": 0.0}
                 for t in tasks_text]
        tasks[0]["status"] = "active"
        self.assertEqual(tasks[0]["status"], "active")
        self.assertEqual(tasks[1]["status"], "pending")
        for k in ("text", "status", "start_ts", "end_ts"):
            self.assertIn(k, tasks[0])


if __name__ == "__main__":
    unittest.main()
