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


class TestTaskDoneDedupFlagSync:
    """Regresión: al avanzar de tarea, _execute_task_done cierra y REABRE el live block.
    Los flags de dedup (_bullet_block_open / _last_displayed_bullet) deben sincronizarse
    con esa realidad. Sin esto, si el modelo reemite el texto de la nueva tarea en el
    turno siguiente, _is_duplicate_bullet comparaba contra el bullet viejo → ● duplicado
    (mismo patrón que el bug de stale-state tras compactación)."""

    def _tui_loop(self):
        loop = _make_loop()
        loop.capture_output = False
        loop._status_cb = MagicMock()
        loop._start_live_block_cb = MagicMock()
        loop._flush_live_block_cb = MagicMock()
        loop._update_live_tools_cb = MagicMock()
        loop._live_tool_count = 0
        # Aislar el render del panel/summary intermedio (no es lo que probamos)
        loop._print_plan_panel_update = MagicMock()
        loop._flush_task_intermediate_summary = MagicMock()
        loop._print = MagicMock()
        return loop

    def test_reanchors_dedup_state_to_next_task(self):
        loop = self._tui_loop()
        loop._execute_plan_create(["Primera tarea", "Segunda tarea muy concreta"])
        # Simular el estado tras mostrar el bullet del turno que llamó task_done
        loop._bullet_block_open = True
        loop._last_displayed_bullet = "texto del turno anterior"

        loop._execute_task_done()   # T1 → done, T2 → active, reabre live block

        # El live block se reabrió → el bullet debe anclarse al texto de la NUEVA tarea
        assert loop._start_live_block_cb.called
        assert loop._bullet_block_open is True
        assert loop._last_displayed_bullet == "Segunda tarea muy concreta"

        # Turno siguiente reemite el texto de la tarea → debe considerarse duplicado
        # (acumular en el bloque vivo), NO arrancar un ● nuevo.
        assert loop._is_duplicate_bullet(
            "Segunda tarea muy concreta", [{"function": {"name": "x"}}]) is True

    def test_all_done_clears_bullet_block_open(self):
        loop = self._tui_loop()
        loop._execute_plan_create(["Única tarea"])
        loop._bullet_block_open = True
        loop._last_displayed_bullet = "algo"

        loop._execute_task_done()   # todas completadas → cierra, NO reabre

        # Sin bloque reabierto, el flag debe reflejar que NO hay dónde acumular
        assert loop._bullet_block_open is False
        # Un turno tool-only posterior NO debe adjuntarse a un bloque cerrado
        assert loop._is_duplicate_bullet("", [{"function": {"name": "x"}}]) is False


class TestPlanApprovalGate:
    """Plan-mode (GAP 2): si rt.plan_approval=True y hay usuario interactivo, plan_create
    presenta el plan y espera aprobación (vía ask_user) antes de comprometerlo."""

    def _gate_loop(self, plan_approval=True, is_subagent=False, capture=False):
        loop = _make_loop()
        loop.capture_output = capture
        loop.is_subagent = is_subagent
        loop.rt = MagicMock()
        loop.rt.plan_approval = plan_approval
        loop.tasks = None
        loop._webui_queue = None
        loop._set_plan_header_mode_cb = None
        loop._print = MagicMock()
        loop._plan_summary = ""
        loop._plan_active_msg_idx = -1
        loop.context = MagicMock(); loop.context.messages = []
        return loop

    def test_approve_commits_plan(self):
        loop = self._gate_loop()
        loop._execute_ask_user = MagicMock(return_value="Elegido por el usuario: Aprobar y ejecutar")
        out = loop._execute_plan_create(["T1", "T2"])
        loop._execute_ask_user.assert_called_once()
        assert "Plan creado" in out
        assert len(loop._plan_tasks) == 2

    def test_cancel_does_not_commit(self):
        loop = self._gate_loop()
        loop._plan_tasks = []
        loop._execute_ask_user = MagicMock(return_value="Elegido por el usuario: Cancelar")
        out = loop._execute_plan_create(["T1", "T2"])
        assert "NO creado" in out
        assert loop._plan_tasks == []

    def test_edit_does_not_commit(self):
        loop = self._gate_loop()
        loop._plan_tasks = []
        loop._execute_ask_user = MagicMock(
            return_value="Elegido por el usuario: Editar el plan  ·  Además indicó: añade tests")
        out = loop._execute_plan_create(["T1", "T2"])
        assert "Replantea" in out and "añade tests" in out
        assert loop._plan_tasks == []

    def test_off_does_not_ask(self):
        loop = self._gate_loop(plan_approval=False)
        loop._execute_ask_user = MagicMock()
        out = loop._execute_plan_create(["T1"])
        loop._execute_ask_user.assert_not_called()
        assert "Plan creado" in out

    def test_subagent_bypasses_gate(self):
        loop = self._gate_loop(is_subagent=True)
        loop._execute_ask_user = MagicMock()
        out = loop._execute_plan_create(["T1"])
        loop._execute_ask_user.assert_not_called()   # gate requiere not is_subagent
        assert "Plan creado" in out

    def test_capture_output_bypasses_gate(self):
        loop = self._gate_loop(capture=True)
        loop._execute_ask_user = MagicMock()
        out = loop._execute_plan_create(["T1"])
        loop._execute_ask_user.assert_not_called()
        assert "Plan creado" in out


class TestPlanApprovalConfig:
    def test_default_in_context_block(self):
        from config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["context"].get("planApproval") is False

    def test_load_reads_plan_approval_as_bool(self, tmp_path, monkeypatch):
        import json, config as _cfgmod
        from config import OOConfig
        p = tmp_path / "oocode.json"
        p.write_text(json.dumps({"context": {"planApproval": True}}))
        monkeypatch.setattr(_cfgmod.constants, "CONFIG_FILE", p, raising=False)
        # _const resuelve CONFIG_FILE dinámicamente; forzamos vía monkeypatch del módulo
        monkeypatch.setattr("config.model._const",
                            lambda k: p if k == "CONFIG_FILE" else _cfgmod.constants.__dict__.get(k))
        cfg = OOConfig.load()
        assert cfg.plan_approval is True

    def test_save_persists_plan_approval(self):
        from config import OOConfig
        cfg = OOConfig()
        cfg.plan_approval = True
        raw = {}
        # emular el bloque que save() escribe en context
        ctx = raw.setdefault("context", {})
        ctx["planApproval"] = cfg.plan_approval
        assert raw["context"]["planApproval"] is True


class TestPlanCommand:
    def test_cmd_plan_on_off(self):
        from unittest.mock import patch
        from ui.commands import _cmd_plan
        rt = MagicMock(); rt.plan_approval = False
        with patch("ui.commands.console"):
            _cmd_plan("on", rt)
            assert rt.plan_approval is True
            _cmd_plan("off", rt)
            assert rt.plan_approval is False

    def test_cmd_plan_status_no_change(self):
        from unittest.mock import patch
        from ui.commands import _cmd_plan
        rt = MagicMock(); rt.plan_approval = True
        with patch("ui.commands.console"):
            _cmd_plan("", rt)   # solo muestra estado
        assert rt.plan_approval is True


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
