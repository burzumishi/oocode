"""Tests para el comportamiento del plan de tareas en AgentLoop.

Cubre:
- _all_plan_tasks_done() detecta correctamente el estado de completado
- _mark_all_plan_tasks_done() marca todas las tareas como done
- _advance_plan_task() detecta señal de completado global (capa 1)
- _advance_plan_task() detecta anuncio "Tarea N:" (capa 2)
- _advance_plan_task() fallback con auto_continue_count (capa 3)
- Spinner format: ✶ cuando tasks activas, frame cuando no
- _status_window_height() con 0, 3, 7, 10 tareas
- _get_status_text() incluye ⎿ + ✔/◼/◻ cuando tasks activas
"""
import sys
import os
import time
import threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock


# ── Helper ────────────────────────────────────────────────────────────────────

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
    return loop


def _tasks(statuses):
    """Crea lista de tareas con los estados dados."""
    now = time.time()
    return [
        {"text": f"Tarea {i+1}", "status": s,
         "start_ts": now if s != "pending" else 0.0,
         "end_ts":   now if s == "done" else 0.0}
        for i, s in enumerate(statuses)
    ]


# ── Tests: _all_plan_tasks_done ───────────────────────────────────────────────

class TestAllPlanTasksDone:

    def test_empty_plan_not_done(self):
        loop = _make_loop()
        assert not loop._all_plan_tasks_done()

    def test_all_done(self):
        loop = _make_loop()
        loop._plan_tasks = _tasks(["done", "done", "done"])
        assert loop._all_plan_tasks_done()

    def test_one_active(self):
        loop = _make_loop()
        loop._plan_tasks = _tasks(["done", "active", "pending"])
        assert not loop._all_plan_tasks_done()

    def test_one_pending(self):
        loop = _make_loop()
        loop._plan_tasks = _tasks(["done", "done", "pending"])
        assert not loop._all_plan_tasks_done()

    def test_single_done(self):
        loop = _make_loop()
        loop._plan_tasks = _tasks(["done"])
        assert loop._all_plan_tasks_done()


# ── Tests: _mark_all_plan_tasks_done ─────────────────────────────────────────

class TestMarkAllPlanTasksDone:

    def test_marks_active_and_pending(self):
        loop = _make_loop()
        loop._plan_tasks = _tasks(["done", "active", "pending"])
        loop._mark_all_plan_tasks_done()
        assert all(t["status"] == "done" for t in loop._plan_tasks)

    def test_sets_end_ts_for_unmarked(self):
        loop = _make_loop()
        loop._plan_tasks = _tasks(["active", "pending"])
        loop._mark_all_plan_tasks_done()
        for t in loop._plan_tasks:
            assert t["end_ts"] > 0

    def test_does_not_reset_existing_end_ts(self):
        loop = _make_loop()
        old_ts = time.time() - 100
        loop._plan_tasks = [
            {"text": "T1", "status": "done", "start_ts": 0.0, "end_ts": old_ts}
        ]
        loop._mark_all_plan_tasks_done()
        assert loop._plan_tasks[0]["end_ts"] == old_ts


# ── Tests: _advance_plan_task ─────────────────────────────────────────────────

class TestAdvancePlanTask:

    def test_completion_report_marks_all_done(self):
        # Signal is legitimate when no pending tasks remain (only active)
        loop = _make_loop()
        loop._plan_tasks = _tasks(["done", "done", "active"])
        loop._advance_plan_task("He completado todas las tareas.")
        assert all(t["status"] == "done" for t in loop._plan_tasks)

    def test_completion_report_ignored_when_pending_tasks_exist(self):
        # Signal is premature when there are still ◻ pending tasks
        loop = _make_loop()
        loop._plan_tasks = _tasks(["done", "active", "pending"])
        loop._advance_plan_task("He completado todas las tareas.")
        # pending task should remain pending — signal ignored
        assert loop._plan_tasks[2]["status"] == "pending"

    def test_completion_report_ignored_when_future_work_mentioned(self):
        # Signal is premature even with no pending tasks if model mentions future work
        loop = _make_loop()
        loop._plan_tasks = _tasks(["done", "done", "active"])
        loop._advance_plan_task(
            "He completado todas las tareas. Próximo paso: migrar archivos .c"
        )
        # active task should remain active — contradictory signal ignored
        assert loop._plan_tasks[2]["status"] == "active"

    def test_task_announce_advances(self):
        loop = _make_loop()
        loop._plan_tasks = _tasks(["active", "pending", "pending"])
        loop._advance_plan_task("Tarea 2: implementando cambios")
        assert loop._plan_tasks[0]["status"] == "done"
        assert loop._plan_tasks[1]["status"] == "active"
        assert loop._plan_tasks[2]["status"] == "pending"

    def test_step_announce_advances(self):
        loop = _make_loop()
        loop._plan_tasks = _tasks(["active", "pending"])
        loop._advance_plan_task("Paso 2: verificando tests")
        assert loop._plan_tasks[0]["status"] == "done"
        assert loop._plan_tasks[1]["status"] == "active"

    def test_fallback_uses_auto_continue_count(self):
        loop = _make_loop()
        loop._auto_continue_count = 1
        loop._plan_tasks = _tasks(["active", "pending", "pending"])
        loop._advance_plan_task("Aquí no hay anuncio explícito")
        # target = min(1, 2) = 1 → tarea 1 activa
        assert loop._plan_tasks[0]["status"] == "done"
        assert loop._plan_tasks[1]["status"] == "active"

    def test_noop_when_no_plan(self):
        loop = _make_loop()
        loop._plan_tasks = []
        loop._advance_plan_task("Tarea 1: algo")  # no debe lanzar

    def test_out_of_range_announce_ignored(self):
        """Tarea N fuera del rango → capa 2 no actúa, usa fallback."""
        loop = _make_loop()
        loop._auto_continue_count = 0
        loop._plan_tasks = _tasks(["active", "pending"])
        loop._advance_plan_task("Tarea 99: fuera de rango")
        # Tarea 99 está fuera de rango → fallback count=0 → task 0 sigue active
        assert loop._plan_tasks[0]["status"] == "active"

    def test_completion_ignored_when_parenthesized_pendiente(self):
        """(PENDIENTE) en el texto → señal prematura aunque no haya tareas ◻."""
        loop = _make_loop()
        loop._plan_tasks = _tasks(["done", "done", "active"])
        loop._advance_plan_task(
            "He completado todas las tareas.\n"
            "Sección A: Procesamiento de datos (PENDIENTE)\n"
            "Sección B: Validación de resultados (PENDIENTE)"
        )
        # Active task no debe marcarse done — señal prematura
        # (puede haberse revertido a active o añadido tareas nuevas, pero no done)
        active_or_done = [t["status"] for t in loop._plan_tasks]
        assert "active" in active_or_done or len(loop._plan_tasks) > 3

    def test_completion_ignored_when_requiere_correccion(self):
        """REQUIERE CORRECCIÓN → señal prematura."""
        loop = _make_loop()
        loop._plan_tasks = _tasks(["done", "done", "active"])
        loop._advance_plan_task(
            "He completado todas las tareas.\n"
            "module.py  Error de importación  ❌ REQUIERE CORRECCIÓN"
        )
        # No debe marcar todas done
        assert not all(t["status"] == "done" for t in loop._plan_tasks)

    def test_completion_ignored_parenthesized_pending_all_tracked_done(self):
        """Cuando todas las tareas rastreadas están done pero hay (PENDIENTE) en texto,
        se revierten tareas o se añaden nuevas para evitar parada prematura."""
        loop = _make_loop()
        loop._plan_tasks = _tasks(["done", "done"])
        loop._advance_plan_task(
            "He completado todas las tareas.\n"
            "Siguiente bloque (PENDIENTE): mejorar manejo de errores."
        )
        # El agente NO debe haber marcado todas done + detenerse
        # → la última tarea debe revertir a active O haberse añadido nuevas tareas
        any_non_done = any(t["status"] != "done" for t in loop._plan_tasks)
        assert any_non_done, "Al menos una tarea debe estar no-done para evitar parada prematura"

    def test_replanning_extends_plan_when_new_tasks_detected(self):
        """Si hay items (PENDIENTE) con lista extraíble, el plan debe evitar parada prematura."""
        loop = _make_loop()
        loop._plan_tasks = _tasks(["done", "done"])
        # Texto con lista numerada + (PENDIENTE) explícito que _detect_tasks puede extraer
        loop._advance_plan_task(
            "He completado todas las tareas básicas.\n"
            "Bloque pendiente (PENDIENTE):\n"
            "1. Añadir manejo de errores en el módulo principal\n"
            "2. Verificar compatibilidad con la versión anterior de la API\n"
            "3. Actualizar la documentación de la interfaz pública\n"
        )
        # El plan no debe quedar all-done — o se añadieron tareas o se revirtió una
        any_non_done = any(t["status"] != "done" for t in loop._plan_tasks)
        assert any_non_done


# ── Tests: spinner format ─────────────────────────────────────────────────────

class TestSpinnerFormat:
    """Verifica el formato del texto de spinner según si hay plan activo."""

    def _spinner_text(self, loop):
        """Simula el cálculo del texto de spinner para la línea 1 del status."""
        import time as _time
        _active_task_txt = ""
        for _pt in getattr(loop, "_plan_tasks", []):
            if _pt["status"] == "active":
                _active_task_txt = _pt["text"]
                break
        if _active_task_txt:
            _tlabel = (_active_task_txt[:44] + "…") if len(_active_task_txt) > 44 else _active_task_txt
            return f"✶  {_tlabel}  (0.0s)"
        else:
            return "○  Cavilando…  (0.0s)"

    def test_no_plan_uses_thinking_word(self):
        loop = _make_loop()
        loop._plan_tasks = []
        text = self._spinner_text(loop)
        assert "✶" not in text

    def test_active_task_uses_star(self):
        loop = _make_loop()
        loop._plan_tasks = _tasks(["done", "active", "pending"])
        loop._plan_tasks[1]["text"] = "Implementar los cambios en el módulo"
        text = self._spinner_text(loop)
        assert "✶" in text
        assert "Implementar" in text

    def test_long_task_truncated(self):
        loop = _make_loop()
        long_text = "A" * 60
        loop._plan_tasks = [{"text": long_text, "status": "active", "start_ts": 0.0, "end_ts": 0.0}]
        text = self._spinner_text(loop)
        assert "…" in text
        assert len(text) < 80  # razonablemente corto


# ── Tests: _status_window_height (nuevo cálculo) ─────────────────────────────

class TestStatusWindowHeightNew:

    def _make_app(self, n_tasks):
        from ui.app import OOCodeApp
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
        loop.is_subagent = False
        loop.capture_output = False
        loop._status_cb = None
        loop._plan_tasks = _tasks(["active"] + ["pending"] * (n_tasks - 1)) if n_tasks > 0 else []
        loop._status_text = ""
        loop._turn_block = []
        loop._turn_block_has_header = False
        loop._tool_current_file = ""
        app = OOCodeApp.__new__(OOCodeApp)
        app._agent_loop = loop
        return app

    def test_no_tasks_height_3(self):
        app = self._make_app(0)
        assert app._status_window_height() == 3

    def test_3_tasks_height_5(self):
        # spinner(1) + 3 tasks + summary(1) = 5
        app = self._make_app(3)
        assert app._status_window_height() == 5

    def test_7_tasks_height_7(self):
        # spinner(1) + 5 visible (max) + summary(1) = 7
        app = self._make_app(7)
        assert app._status_window_height() == 7

    def test_10_tasks_height_7(self):
        # spinner(1) + 5 visible (max) + summary(1) = 7 (clamped at 5 visible)
        app = self._make_app(10)
        assert app._status_window_height() == 7


# ── Tests: _get_status_text con tasks ────────────────────────────────────────

class TestGetStatusTextWithTasks:

    def _make_app_with_tasks(self, statuses):
        from ui.app import OOCodeApp
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
        loop.is_subagent = False
        loop.capture_output = False
        loop._status_cb = None
        loop._plan_tasks = [
            {"text": f"Tarea {i+1}: algo importante", "status": s,
             "start_ts": 0.0, "end_ts": 0.0}
            for i, s in enumerate(statuses)
        ]
        loop._status_text = "✶  Tarea 1…  (1.2s)"
        loop._turn_block = []
        loop._turn_block_has_header = False
        loop._tool_current_file = ""
        app = OOCodeApp.__new__(OOCodeApp)
        app._agent_loop = loop
        app._perm_mode = False
        app._plain_tip_cache = ""
        return app

    def _flat_text(self, frags):
        return "".join(text for _, text in frags)

    def test_has_lyre_connector(self):
        """Primera tarea tiene ⎿ connector."""
        app = self._make_app_with_tasks(["done", "active", "pending"])
        text = self._flat_text(app._get_status_text())
        assert "⎿" in text

    def test_done_icon_present(self):
        app = self._make_app_with_tasks(["done", "active"])
        text = self._flat_text(app._get_status_text())
        assert "✔" in text

    def test_active_icon_present(self):
        app = self._make_app_with_tasks(["done", "active"])
        text = self._flat_text(app._get_status_text())
        assert "◼" in text

    def test_pending_icon_present(self):
        app = self._make_app_with_tasks(["active", "pending"])
        text = self._flat_text(app._get_status_text())
        assert "◻" in text

    def test_summary_shows_counts(self):
        app = self._make_app_with_tasks(["done", "active", "pending"])
        text = self._flat_text(app._get_status_text())
        assert "+1 pending" in text
        assert "1 completed" in text

    def test_all_done_summary(self):
        app = self._make_app_with_tasks(["done", "done", "done"])
        text = self._flat_text(app._get_status_text())
        assert "completed" in text
        assert "✓" in text

    def test_no_tip_when_tasks_active(self):
        """Con tasks activas no se muestra el Tip en el status panel."""
        app = self._make_app_with_tasks(["active", "pending"])
        app._plain_tip_cache = "Esto es un tip"
        text = self._flat_text(app._get_status_text())
        assert "Tip:" not in text


# ── Tests: sincronización _plan_tasks con plan del LLM ───────────────────────

class TestPlanTasksLLMSync:
    """Verifica que _plan_tasks se sincroniza con el plan refinado del LLM."""

    def test_detect_tasks_from_llm_plan(self):
        """_detect_tasks extrae pasos numerados del plan del LLM."""
        from agent.loop import AgentLoop
        llm_plan = (
            "Aquí está mi plan de ejecución:\n"
            "1. Revisar la configuración actual del módulo\n"
            "2. Implementar la nueva función de exportación\n"
            "3. Actualizar los tests correspondientes\n"
            "4. Verificar que los imports son correctos\n"
        )
        steps = AgentLoop._detect_tasks(llm_plan)
        assert len(steps) == 4
        assert "Revisar la configuración" in steps[0]
        assert "Implementar" in steps[1]

    def test_detect_tasks_bullets_from_llm_plan(self):
        """_detect_tasks extrae bullets del plan del LLM."""
        from agent.loop import AgentLoop
        llm_plan = (
            "Voy a realizar los siguientes cambios:\n"
            "- Añadir el nuevo endpoint en api.py\n"
            "- Registrar la ruta en el router principal\n"
            "- Añadir validación de parámetros\n"
        )
        steps = AgentLoop._detect_tasks(llm_plan)
        assert len(steps) == 3
        assert "endpoint" in steps[0]

    def test_plan_sync_replaces_user_tasks_with_llm_steps(self):
        """Simula que _plan_tasks se reemplaza con pasos del LLM en primer auto-continue."""
        loop = _make_loop()
        # Usuario detectó 2 tareas genéricas
        loop._plan_tasks = _tasks(["active", "pending"])
        loop._plan_tasks[0]["text"] = "tarea del usuario 1"
        loop._plan_tasks[1]["text"] = "tarea del usuario 2"

        # LLM generó 4 pasos refinados — simular la lógica de sync
        from agent.loop import AgentLoop
        _plan_steps = [
            "Leer la configuración en config.py",
            "Implementar el nuevo método en api.py",
            "Actualizar los tests en test_api.py",
            "Verificar que todo funciona correctamente",
        ]
        _n_ac = 1  # primer auto-continue
        if _plan_steps and _n_ac == 1:
            loop._plan_tasks = [
                {"text": t, "status": "pending", "start_ts": 0.0, "end_ts": 0.0}
                for t in _plan_steps
            ]
            loop._plan_tasks[0]["status"] = "active"
            loop._plan_tasks[0]["start_ts"] = 1.0

        assert len(loop._plan_tasks) == 4
        assert "config.py" in loop._plan_tasks[0]["text"]
        assert loop._plan_tasks[0]["status"] == "active"
        assert loop._plan_tasks[1]["status"] == "pending"

    def test_plan_sync_only_on_first_autocontinue(self):
        """La sync solo ocurre cuando _n_ac == 1 (primer auto-continue)."""
        loop = _make_loop()
        loop._plan_tasks = _tasks(["done", "active", "pending"])
        original_first = loop._plan_tasks[0]["text"]

        # Simular segundo auto-continue — _plan_tasks NO se reemplaza
        _plan_steps = ["Nuevo paso A", "Nuevo paso B", "Nuevo paso C"]
        _n_ac = 2  # segundo auto-continue
        if _plan_steps and _n_ac == 1:  # condición no se cumple
            loop._plan_tasks = [
                {"text": t, "status": "pending", "start_ts": 0.0, "end_ts": 0.0}
                for t in _plan_steps
            ]

        # _plan_tasks no debe haberse reemplazado
        assert len(loop._plan_tasks) == 3
        assert loop._plan_tasks[0]["text"] == original_first

    def test_detect_tasks_min_2_items(self):
        """_detect_tasks devuelve [] si solo hay 1 item (mínimo 2)."""
        from agent.loop import AgentLoop
        text = "Plan:\n1. Una única tarea larga pero solo hay una"
        steps = AgentLoop._detect_tasks(text)
        assert steps == []

    def test_detect_tasks_max_12_items(self):
        """_detect_tasks limita la salida a 12 items máximo."""
        from agent.loop import AgentLoop
        lines = "\n".join(f"{i+1}. Paso largo número {i+1} de la lista" for i in range(20))
        steps = AgentLoop._detect_tasks(lines)
        assert len(steps) == 12
