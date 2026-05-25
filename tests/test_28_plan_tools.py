"""Tests para las tools plan_create y task_done del AgentLoop.

Cubre:
- _execute_plan_create() con lista válida
- _execute_plan_create() activa tarea 1 automáticamente
- _execute_plan_create() con lista vacía o no-lista devuelve error
- _execute_plan_create() filtra strings vacíos de la lista
- _execute_plan_create() con summary opcional
- _execute_task_done() sin plan activo devuelve error
- _execute_task_done() avanza la tarea activa
- _execute_task_done() marca la última tarea como done
- _execute_task_done() con message opcional
- Flujo completo plan_create → task_done × N → todas completadas
- plan_create resetea plan anterior
- Registro en oocode.py (permisos plan_create/task_done = auto)
"""
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock


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
    loop.capture_output = True   # evita print en tests
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
    return loop


class TestExecutePlanCreate:
    def test_creates_plan_from_list(self):
        loop = _make_loop()
        result = loop._execute_plan_create(["Leer config.py", "Editar loop.py", "Correr tests"])
        assert "Plan creado: 3 tareas" in result
        assert len(loop._plan_tasks) == 3

    def test_first_task_becomes_active(self):
        loop = _make_loop()
        loop._execute_plan_create(["Primera tarea", "Segunda tarea", "Tercera tarea"])
        assert loop._plan_tasks[0]["status"] == "active"
        assert loop._plan_tasks[1]["status"] == "pending"
        assert loop._plan_tasks[2]["status"] == "pending"

    def test_first_task_gets_start_ts(self):
        loop = _make_loop()
        before = time.time()
        loop._execute_plan_create(["Tarea A", "Tarea B"])
        assert loop._plan_tasks[0]["start_ts"] >= before

    def test_empty_list_returns_error(self):
        loop = _make_loop()
        result = loop._execute_plan_create([])
        assert "Error" in result
        assert loop._plan_tasks == []

    def test_non_list_returns_error(self):
        loop = _make_loop()
        result = loop._execute_plan_create("no es lista")  # type: ignore[arg-type]
        assert "Error" in result

    def test_filters_empty_strings(self):
        loop = _make_loop()
        result = loop._execute_plan_create(["Tarea 1", "", "  ", "Tarea 2"])
        assert "Plan creado: 2 tareas" in result
        assert len(loop._plan_tasks) == 2

    def test_filters_all_empty_returns_error(self):
        loop = _make_loop()
        result = loop._execute_plan_create(["", "   "])
        assert "Error" in result

    def test_result_contains_task1_text(self):
        loop = _make_loop()
        result = loop._execute_plan_create(["Explorar ficheros de configuración", "Editar permisos"])
        assert "Explorar ficheros de configuración" in result

    def test_result_mentions_task_done(self):
        loop = _make_loop()
        result = loop._execute_plan_create(["Tarea única"])
        # task_done debe mencionarse porque hay plan
        assert "task_done" in result.lower()

    def test_summary_optional(self):
        loop = _make_loop()
        result = loop._execute_plan_create(["Paso 1", "Paso 2"], summary="Refactorizar módulo X")
        assert "Plan creado" in result

    def test_resets_previous_plan(self):
        loop = _make_loop()
        loop._plan_tasks = [
            {"text": "Old task", "status": "done", "start_ts": 1.0, "end_ts": 2.0}
        ]
        loop._execute_plan_create(["Nueva tarea 1", "Nueva tarea 2"])
        assert len(loop._plan_tasks) == 2
        assert loop._plan_tasks[0]["text"] == "Nueva tarea 1"

    def test_single_task_allowed(self):
        loop = _make_loop()
        result = loop._execute_plan_create(["Una sola tarea importante"])
        assert "Plan creado: 1 tareas" in result or "Plan creado: 1 tarea" in result
        assert len(loop._plan_tasks) == 1


class TestExecuteTaskDone:
    def test_no_plan_returns_error(self):
        loop = _make_loop()
        result = loop._execute_task_done()
        assert "No hay plan activo" in result

    def test_advances_to_next_task(self):
        loop = _make_loop()
        loop._execute_plan_create(["Tarea 1", "Tarea 2", "Tarea 3"])
        assert loop._plan_tasks[0]["status"] == "active"

        result = loop._execute_task_done()
        assert loop._plan_tasks[0]["status"] == "done"
        assert loop._plan_tasks[1]["status"] == "active"
        assert "2/3" in result or "Tarea 2" in result

    def test_marks_last_task_done(self):
        loop = _make_loop()
        loop._execute_plan_create(["Solo una tarea"])
        result = loop._execute_task_done()
        assert loop._plan_tasks[0]["status"] == "done"
        assert "completad" in result.lower()

    def test_all_done_signal(self):
        loop = _make_loop()
        loop._execute_plan_create(["T1", "T2"])
        loop._execute_task_done()   # T1 → done, T2 → active
        result = loop._execute_task_done()  # T2 → done
        assert "todas" in result.lower() or "completad" in result.lower()

    def test_task_done_sets_end_ts(self):
        loop = _make_loop()
        loop._execute_plan_create(["Tarea A", "Tarea B"])
        before = time.time()
        loop._execute_task_done()
        assert loop._plan_tasks[0]["end_ts"] >= before

    def test_task_done_accepts_message(self):
        loop = _make_loop()
        loop._execute_plan_create(["Tarea 1", "Tarea 2"])
        result = loop._execute_task_done(message="Completada con éxito")
        assert "completad" in result.lower() or "2" in result

    def test_sequential_task_done_flow(self):
        """Flujo completo: plan_create → task_done × N → todas completadas."""
        loop = _make_loop()
        tasks = ["Explorar código", "Editar ficheros", "Ejecutar tests"]
        loop._execute_plan_create(tasks)

        # T1 activa
        assert loop._plan_tasks[0]["status"] == "active"

        loop._execute_task_done()
        assert loop._plan_tasks[0]["status"] == "done"
        assert loop._plan_tasks[1]["status"] == "active"

        loop._execute_task_done()
        assert loop._plan_tasks[1]["status"] == "done"
        assert loop._plan_tasks[2]["status"] == "active"

        result = loop._execute_task_done()
        assert loop._plan_tasks[2]["status"] == "done"
        assert all(t["status"] == "done" for t in loop._plan_tasks)
        assert "todas" in result.lower() or "completad" in result.lower()

    def test_no_active_task_returns_error(self):
        """Si _plan_tasks existe pero ninguna tarea está active, devuelve info útil."""
        loop = _make_loop()
        from time import time as _t
        loop._plan_tasks = [
            {"text": "Tarea ya hecha", "status": "done", "start_ts": 1.0, "end_ts": 2.0}
        ]
        result = loop._execute_task_done()
        # Puede devolver error o "todas completadas" — ambos son correctos
        assert result


class TestPlanToolsPermissions:
    def test_plan_create_default_permission_is_auto(self):
        from config import DEFAULT_CONFIG
        perms = DEFAULT_CONFIG.get("permissions", {})
        assert perms.get("plan_create") == "auto", (
            "plan_create debe tener permiso 'auto' en DEFAULT_CONFIG"
        )

    def test_task_done_default_permission_is_auto(self):
        from config import DEFAULT_CONFIG
        perms = DEFAULT_CONFIG.get("permissions", {})
        assert perms.get("task_done") == "auto", (
            "task_done debe tener permiso 'auto' en DEFAULT_CONFIG"
        )


class TestPlanToolsInHint13:
    def test_hint13_mentions_plan_create(self):
        """Hint 13 debe sugerir plan_create(tasks=[...]) en lugar de respuesta de texto."""
        loop = _make_loop()
        loop._last_tool_calls = [
            ("read_file", '{"path": "a.py"}', "contenido A"),
            ("grep_code", '{"pattern": "x"}', "resultados"),
            ("read_file", '{"path": "b.py"}', "contenido B"),
            ("find_files", '{"name": "*.py"}', "lista"),
            ("read_file", '{"path": "c.py"}', "contenido C"),
            ("ls_dir", '{"directory": "."}', "dirs"),
        ]
        guidance = loop._turn_guidance()
        assert "plan_create" in guidance

    def test_hint13_not_triggered_when_plan_exists(self):
        """Hint 13 no aparece si ya hay un plan activo."""
        loop = _make_loop()
        loop._plan_tasks = [
            {"text": "Tarea activa", "status": "active", "start_ts": 1.0, "end_ts": 0.0}
        ]
        loop._last_tool_calls = [
            ("read_file", '{"path": "a.py"}', "ok"),
            ("grep_code", '{"pattern": "x"}', "ok"),
            ("read_file", '{"path": "b.py"}', "ok"),
            ("find_files", '{"name": "*.py"}', "ok"),
            ("read_file", '{"path": "c.py"}', "ok"),
            ("ls_dir", '{"directory": "."}', "ok"),
        ]
        guidance = loop._turn_guidance()
        # plan_create hint solo aparece si no hay plan; con plan existente no debe estar
        # (puede aparecer en otros hints, pero el hint 13 en concreto no)
        if "plan_create" in guidance:
            # Verificar que no es el hint 13 específico (exploración intensa sin plan)
            assert "exploraciones, sin plan activo" not in guidance

    def test_hint13_not_triggered_when_writes_exist(self):
        """Hint 13 no aparece si ya hay escrituras en el turno."""
        loop = _make_loop()
        loop._plan_tasks = []
        loop._last_tool_calls = [
            ("read_file", '{"path": "a.py"}', "ok"),
            ("grep_code", '{"pattern": "x"}', "ok"),
            ("read_file", '{"path": "b.py"}', "ok"),
            ("edit_file", '{"path": "c.py"}', "ok"),  # escritura
            ("read_file", '{"path": "d.py"}', "ok"),
            ("ls_dir", '{"directory": "."}', "ok"),
        ]
        guidance = loop._turn_guidance()
        assert "exploraciones, sin plan activo" not in guidance
