"""Tests del panel visual y formato exacto de plan_create / task_done.

Basado en prueba real de consola 2026-05-20. Cubre:

Panel visual (capture_output=False):
- _print se llama exactamente cuando capture_output=False
- _print NO se llama cuando capture_output=True
- Panel contiene ◈, "Plan de ejecución", ◼/◻, ↻
- Summary se muestra si se pasa; no aparece si no se pasa
- Singular "1 tarea" vs plural "N tareas"
- Tareas >12: panel muestra "+ N más"
- Tareas largas (>80 chars): truncadas en panel con "…"

Formato exacto de retorno:
- plan_create: "Plan creado: N tareas. Activa ahora [1/N]: 'texto'. Usa task_done()..."
- task_done (normal): "✔ Tarea N/M completada. Activa ahora [N+1/M]: 'texto'. Continúa..."
- task_done (última): "✔ Todas las N tareas completadas. ... 'He completado todas las tareas.'"
- task_done sin plan: "No hay plan activo. Usa plan_create(tasks=[...]) primero."
- task_done todas ya done: "Todas las tareas ya están completadas."

Casos límite:
- active_idx=-1 pero hay pending: task_done lo recupera correctamente
- Non-string items en tasks: coercionados a str()
- Tarea >80 chars: guardada completa en _plan_tasks pero truncada en retorno
- plan_create con 1 sola tarea: funciona (singular en panel)
- _all_plan_tasks_done() integración con plan_create/task_done
"""
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock


def _make_loop(capture_output: bool = True):
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
    loop.capture_output = capture_output
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


def _make_visual_loop():
    """Loop con capture_output=False y _print capturado en lista."""
    loop = _make_loop(capture_output=False)
    printed: list[str] = []
    loop._print = lambda msg, **kw: printed.append(msg)
    return loop, printed


# ── Panel visual (capture_output=False) ──────────────────────────────────────

class TestPlanCreateVisualPanel:
    def test_print_called_when_not_capture(self):
        loop, printed = _make_visual_loop()
        loop._execute_plan_create(["Tarea A", "Tarea B"])
        assert len(printed) > 0

    def test_print_not_called_when_capture(self):
        loop = _make_loop(capture_output=True)
        calls = []
        loop._print = lambda msg, **kw: calls.append(msg)
        loop._execute_plan_create(["Tarea A", "Tarea B"])
        assert calls == []

    def test_panel_contains_icon(self):
        loop, printed = _make_visual_loop()
        loop._execute_plan_create(["T1", "T2"])
        all_text = "\n".join(printed)
        assert "◈" in all_text

    def test_panel_contains_plan_label(self):
        loop, printed = _make_visual_loop()
        loop._execute_plan_create(["T1", "T2"])
        all_text = "\n".join(printed)
        assert "Plan de ejecución" in all_text

    def test_panel_task1_has_active_icon(self):
        """Primera tarea usa ◼ (activa)."""
        loop, printed = _make_visual_loop()
        loop._execute_plan_create(["Paso 1", "Paso 2", "Paso 3"])
        task_lines = [m for m in printed if "◼" in m or "◻" in m]
        # La primera debe tener ◼
        first_task_line = next((m for m in task_lines if "1." in m), "")
        assert "◼" in first_task_line

    def test_panel_other_tasks_have_pending_icon(self):
        """Tareas 2+ usan ◻ (pendientes)."""
        loop, printed = _make_visual_loop()
        loop._execute_plan_create(["T1", "T2", "T3"])
        task_lines = [m for m in printed if "◼" in m or "◻" in m]
        second_task_line = next((m for m in task_lines if "2." in m), "")
        assert "◻" in second_task_line

    def test_panel_contains_execute_line(self):
        """Línea ↻ 'Ejecutando tarea 1/N' al final del panel."""
        loop, printed = _make_visual_loop()
        loop._execute_plan_create(["T1", "T2"])
        all_text = "\n".join(printed)
        assert "↻" in all_text
        assert "Ejecutando tarea 1/2" in all_text

    def test_panel_shows_summary_when_provided(self):
        loop, printed = _make_visual_loop()
        loop._execute_plan_create(["T1", "T2"], summary="Refactorizar módulo de permisos")
        all_text = "\n".join(printed)
        assert "Refactorizar módulo de permisos" in all_text

    def test_panel_no_summary_line_when_not_provided(self):
        loop, printed = _make_visual_loop()
        loop._execute_plan_create(["T1", "T2"])
        # Solo las tareas y header: exactamente 4 líneas (header + 2 tasks + ↻ execute)
        # Sin summary, no debe haber línea extra de texto italic
        non_task_lines = [m for m in printed if "dim italic" in m]
        assert non_task_lines == []

    def test_panel_singular_tarea_for_one_task(self):
        loop, printed = _make_visual_loop()
        loop._execute_plan_create(["Una única tarea"])
        header_line = next((m for m in printed if "Plan de ejecución" in m), "")
        assert "(1 tarea)" in header_line
        assert "tareas" not in header_line

    def test_panel_plural_tareas_for_multiple(self):
        loop, printed = _make_visual_loop()
        loop._execute_plan_create(["T1", "T2", "T3"])
        header_line = next((m for m in printed if "Plan de ejecución" in m), "")
        assert "(3 tareas)" in header_line

    def test_panel_shows_more_line_for_over_12_tasks(self):
        loop, printed = _make_visual_loop()
        tasks = [f"Tarea {i}" for i in range(1, 16)]  # 15 tareas
        loop._execute_plan_create(tasks)
        all_text = "\n".join(printed)
        assert "+3 más" in all_text  # 15 - 12 = 3

    def test_panel_shows_exactly_12_task_lines_when_over_12(self):
        loop, printed = _make_visual_loop()
        tasks = [f"Tarea {i}" for i in range(1, 16)]
        loop._execute_plan_create(tasks)
        task_lines = [m for m in printed if ("◼" in m or "◻" in m) and "más" not in m]
        assert len(task_lines) == 12

    def test_panel_truncates_long_task_name_with_ellipsis(self):
        """Tareas >80 chars se truncan en el panel con '…'."""
        loop, printed = _make_visual_loop()
        long_task = "Esta tarea tiene una descripción extremadamente larga que supera los ochenta caracteres"
        loop._execute_plan_create([long_task, "T2"])
        task1_line = next((m for m in printed if "1." in m), "")
        assert "…" in task1_line

    def test_panel_line_count_with_summary(self):
        """Con summary: header + summary + N tareas + ↻ = N + 3 líneas."""
        loop, printed = _make_visual_loop()
        loop._execute_plan_create(["T1", "T2", "T3"], summary="Mi plan")
        # 1 header + 1 summary + 3 tasks + 1 execute = 6
        assert len(printed) == 6

    def test_panel_line_count_without_summary(self):
        """Sin summary: header + N tareas + ↻ = N + 2 líneas."""
        loop, printed = _make_visual_loop()
        loop._execute_plan_create(["T1", "T2", "T3"])
        # 1 header + 3 tasks + 1 execute = 5
        assert len(printed) == 5


# ── Formato exacto de retorno ─────────────────────────────────────────────────

class TestPlanCreateReturnFormat:
    def test_return_starts_with_plan_creado(self):
        loop = _make_loop()
        r = loop._execute_plan_create(["T1", "T2", "T3"])
        assert r.startswith("Plan creado: 3 tareas.")

    def test_return_contains_task_count(self):
        loop = _make_loop()
        r = loop._execute_plan_create(["A", "B", "C", "D"])
        assert "4 tareas" in r

    def test_return_contains_active_bracket_notation(self):
        loop = _make_loop()
        r = loop._execute_plan_create(["T1", "T2"])
        assert "[1/2]" in r

    def test_return_contains_first_task_text(self):
        loop = _make_loop()
        r = loop._execute_plan_create(["Explorar configuración", "Editar código"])
        assert "'Explorar configuración'" in r

    def test_return_mentions_task_done(self):
        loop = _make_loop()
        r = loop._execute_plan_create(["T1", "T2"])
        assert "task_done()" in r

    def test_return_truncates_task_name_at_80(self):
        """Nombre en retorno truncado a 80 chars."""
        loop = _make_loop()
        long_task = "X" * 100
        r = loop._execute_plan_create([long_task, "T2"])
        assert "X" * 80 in r
        assert "X" * 81 not in r

    def test_return_task_stored_full_in_plan_tasks(self):
        """El texto completo se guarda en _plan_tasks aunque el retorno esté truncado."""
        loop = _make_loop()
        long_task = "X" * 100
        loop._execute_plan_create([long_task, "T2"])
        assert loop._plan_tasks[0]["text"] == long_task  # sin truncar


class TestTaskDoneReturnFormat:
    def test_normal_return_starts_with_checkmark(self):
        loop = _make_loop()
        loop._execute_plan_create(["T1", "T2", "T3"])
        r = loop._execute_task_done()
        assert r.startswith("✔")

    def test_normal_return_contains_position(self):
        loop = _make_loop()
        loop._execute_plan_create(["T1", "T2", "T3"])
        r = loop._execute_task_done()
        assert "1/3" in r

    def test_normal_return_contains_next_bracket(self):
        loop = _make_loop()
        loop._execute_plan_create(["T1", "T2", "T3"])
        r = loop._execute_task_done()
        assert "[2/3]" in r

    def test_normal_return_contains_next_task_text(self):
        loop = _make_loop()
        loop._execute_plan_create(["T1", "Tarea siguiente importante", "T3"])
        r = loop._execute_task_done()
        assert "Tarea siguiente importante" in r

    def test_normal_return_says_continua(self):
        loop = _make_loop()
        loop._execute_plan_create(["T1", "T2"])
        r = loop._execute_task_done()
        assert "Continúa" in r

    def test_final_return_contains_todas_completadas(self):
        loop = _make_loop()
        loop._execute_plan_create(["T1", "T2"])
        loop._execute_task_done()
        r = loop._execute_task_done()
        assert "Todas las 2 tareas completadas" in r

    def test_final_return_contains_completion_phrase(self):
        loop = _make_loop()
        loop._execute_plan_create(["T1"])
        r = loop._execute_task_done()
        assert "He completado todas las tareas." in r

    def test_no_plan_return_exact(self):
        loop = _make_loop()
        r = loop._execute_task_done()
        assert "No hay plan activo" in r
        assert "plan_create(tasks=[...])" in r

    def test_all_already_done_return(self):
        loop = _make_loop()
        loop._execute_plan_create(["T1", "T2"])
        loop._execute_task_done()
        loop._execute_task_done()
        r = loop._execute_task_done()  # ya todas done
        assert "ya están completadas" in r or "He completado todas" in r

    def test_second_task_done_references_correct_position(self):
        loop = _make_loop()
        loop._execute_plan_create(["Alpha", "Beta", "Gamma"])
        loop._execute_task_done()   # T1 → done, T2 → active
        r = loop._execute_task_done()  # T2 → done, T3 → active
        assert "2/3" in r
        assert "[3/3]" in r
        assert "Gamma" in r


# ── Casos límite descubiertos en prueba de consola ────────────────────────────

class TestPlanCreateEdgeCases:
    def test_non_string_items_coerced_to_str(self):
        """Ítems no-string (int, float, None) se convierten a str()."""
        loop = _make_loop()
        r = loop._execute_plan_create([1, 2.5, "texto", None])
        assert "Plan creado: 4 tareas" in r
        texts = [t["text"] for t in loop._plan_tasks]
        assert "1" in texts
        assert "2.5" in texts
        assert "texto" in texts
        assert "None" in texts

    def test_long_task_stored_full_in_plan_tasks(self):
        loop = _make_loop()
        long = "Descripción muy larga que supera los ochenta caracteres del límite"
        assert len(long) > 60
        loop._execute_plan_create([long, "Corta"])
        assert loop._plan_tasks[0]["text"] == long

    def test_single_task_plan_creates_correctly(self):
        loop = _make_loop()
        r = loop._execute_plan_create(["Única tarea del plan"])
        assert "1 tarea" in r or "1 tareas" in r
        assert len(loop._plan_tasks) == 1

    def test_plan_create_resets_all_previous_tasks(self):
        loop = _make_loop()
        loop._execute_plan_create(["Old A", "Old B", "Old C"])
        loop._execute_task_done()  # Old A → done
        loop._execute_plan_create(["New X", "New Y"])
        assert len(loop._plan_tasks) == 2
        assert all(t["status"] in ("active", "pending") for t in loop._plan_tasks)
        assert loop._plan_tasks[0]["text"] == "New X"

    def test_plan_create_new_plan_first_task_active(self):
        loop = _make_loop()
        loop._execute_plan_create(["Old"])
        loop._execute_task_done()
        loop._execute_plan_create(["Fresh A", "Fresh B"])
        assert loop._plan_tasks[0]["status"] == "active"
        assert loop._plan_tasks[1]["status"] == "pending"


class TestTaskDoneEdgeCases:
    def test_active_idx_minus1_recovers_first_pending(self):
        """Si ninguna tarea está active pero hay pending, task_done activa y completa la primera pending."""
        loop = _make_loop()
        loop._plan_tasks = [
            {"text": "T1", "status": "pending", "start_ts": 0.0, "end_ts": 0.0},
            {"text": "T2", "status": "pending", "start_ts": 0.0, "end_ts": 0.0},
        ]
        r = loop._execute_task_done()
        assert loop._plan_tasks[0]["status"] == "done"
        assert loop._plan_tasks[1]["status"] == "active"
        assert "1/2" in r

    def test_task_done_sets_done_end_ts(self):
        loop = _make_loop()
        loop._execute_plan_create(["T1", "T2"])
        t_before = time.time()
        loop._execute_task_done()
        assert loop._plan_tasks[0]["end_ts"] >= t_before

    def test_task_done_sets_next_start_ts(self):
        loop = _make_loop()
        loop._execute_plan_create(["T1", "T2"])
        t_before = time.time()
        loop._execute_task_done()
        assert loop._plan_tasks[1]["start_ts"] >= t_before

    def test_task_done_idempotent_after_all_done(self):
        """Llamadas extra a task_done tras terminar todas no deben romper el plan."""
        loop = _make_loop()
        loop._execute_plan_create(["T1"])
        loop._execute_task_done()
        r1 = loop._execute_task_done()
        r2 = loop._execute_task_done()
        assert r1 and r2  # devuelve string, no lanza excepción


# ── Integración con _all_plan_tasks_done() ───────────────────────────────────

class TestPlanCreateAllTasksDoneIntegration:
    def test_all_done_false_after_plan_create(self):
        loop = _make_loop()
        loop._execute_plan_create(["T1", "T2"])
        assert not loop._all_plan_tasks_done()

    def test_all_done_false_mid_progress(self):
        loop = _make_loop()
        loop._execute_plan_create(["T1", "T2", "T3"])
        loop._execute_task_done()
        assert not loop._all_plan_tasks_done()

    def test_all_done_true_after_all_task_done(self):
        loop = _make_loop()
        loop._execute_plan_create(["T1", "T2", "T3"])
        loop._execute_task_done()
        loop._execute_task_done()
        loop._execute_task_done()
        assert loop._all_plan_tasks_done()

    def test_all_done_resets_on_new_plan(self):
        loop = _make_loop()
        loop._execute_plan_create(["T1"])
        loop._execute_task_done()
        assert loop._all_plan_tasks_done()
        loop._execute_plan_create(["New T1", "New T2"])
        assert not loop._all_plan_tasks_done()

    def test_sequential_status_flow(self):
        """Verificar la secuencia completa de estados para 3 tareas."""
        loop = _make_loop()
        loop._execute_plan_create(["Alpha", "Beta", "Gamma"])

        assert loop._plan_tasks[0]["status"] == "active"
        assert loop._plan_tasks[1]["status"] == "pending"
        assert loop._plan_tasks[2]["status"] == "pending"

        loop._execute_task_done()
        assert loop._plan_tasks[0]["status"] == "done"
        assert loop._plan_tasks[1]["status"] == "active"
        assert loop._plan_tasks[2]["status"] == "pending"

        loop._execute_task_done()
        assert loop._plan_tasks[0]["status"] == "done"
        assert loop._plan_tasks[1]["status"] == "done"
        assert loop._plan_tasks[2]["status"] == "active"

        loop._execute_task_done()
        assert all(t["status"] == "done" for t in loop._plan_tasks)
        assert loop._all_plan_tasks_done()
