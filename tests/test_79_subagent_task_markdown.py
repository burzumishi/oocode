"""Tests para el render de tareas markdown en los headers de orquestación (TUI).

Regresión: cuando el agente principal pasaba un `task` multilínea en markdown a
`spawn_subagent` (o a `explore`), el header lo volcaba en crudo vía `_esc()`
(que escapa markup Rich pero NO renderiza markdown). El resultado en pantalla era
markdown literal (`**Contexto actual:**`, `- bullets`) sin interpretar, escapando
al formato de la conversación.

Fix: la 1.ª línea del task va inline en el header; el resto se renderiza como
Markdown indentado (`Padding(Markdown(...))`).
"""
import io
import os
import sys
from contextlib import redirect_stdout
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_MD_TASK = (
    "Continuar con el próximo sprint del robot hexápodo Bicho.\n\n"
    "**Contexto actual:**\n"
    "- Sprint 8 completado\n"
    "- Sprint 9 pendiente\n\n"
    "**Tareas prioritarias:**\n"
    "1. Mejorar reconocimiento facial\n"
    "2. Añadir nuevos gestos"
)


def _make_parent_loop():
    from agent.loop import AgentLoop
    from config import OOConfig
    loop = AgentLoop.__new__(AgentLoop)
    loop.config = OOConfig()
    loop.is_subagent = False
    loop.capture_output = False
    loop._webui_queue = None
    loop._status_cb = None
    loop._update_live_tool_start_cb = None
    loop._flush_live_block_cb = None
    loop._sub_lines_shown = 0
    loop._call_context = lambda n, a: ""
    loop._strip_rich = lambda s: s
    loop._webui_emit = MagicMock()
    return loop


def test_spawn_subagent_header_renders_markdown_task():
    """El header de spawn_subagent NO debe mostrar markdown en crudo."""
    loop = _make_parent_loop()
    agent_id = "coding"

    buf = io.StringIO()
    with redirect_stdout(buf):
        loop._show_tool_running_header(
            "spawn_subagent", {"agent_id": agent_id, "task": _MD_TASK}
        )
    out = buf.getvalue()

    # Los asteriscos de markdown NO deben aparecer literalmente (Rich los consume
    # al renderizar **negrita**).
    assert "**Contexto actual:**" not in out
    assert "**Tareas prioritarias:**" not in out
    # El contenido textual SÍ aparece (renderizado), incluida la 1.ª línea inline.
    assert "Continuar con el próximo sprint" in out
    assert "Contexto actual" in out
    assert "Mejorar reconocimiento facial" in out
    # El header del subagente se imprimió.
    assert "spawn_subagent" in out


def test_spawn_subagent_header_single_line_task_inline():
    """Task de una sola línea: header inline sin bloque markdown extra."""
    loop = _make_parent_loop()
    agent_id = "coding"

    buf = io.StringIO()
    with redirect_stdout(buf):
        loop._show_tool_running_header(
            "spawn_subagent", {"agent_id": agent_id, "task": "Tarea simple de una línea"}
        )
    out = buf.getvalue()
    assert "Tarea simple de una línea" in out
    assert "spawn_subagent" in out


def test_explore_header_renders_markdown_task():
    """El header de explore renderiza markdown y escapa markup Rich de la 1.ª línea."""
    from agent.subagent import SubAgentRunner
    import inspect
    # Verifica que el código fuente de explore ya no vuelca el task crudo en un solo
    # f-string sin Markdown (regresión de implementación).
    src = inspect.getsource(SubAgentRunner)
    assert "🔍 Explorando:" in src
    # La 1.ª línea se escapa y el resto se renderiza como Markdown.
    assert "_esc(_t_head)" in src
    assert "Markdown" in src or "_Md" in src


def test_subagent_panel_header_ctx_is_subagent_not_main():
    """El % ctx del header del panel de subagentes refleja el ctx del SUBAGENTE
    activo, no el del agente principal (context.stats())."""
    from ui.app import OOCodeApp
    import inspect
    src = inspect.getsource(OOCodeApp._get_subagent_panel_text)
    # La línea de ctx del header se calcula desde un subagente (s.ctx_pct), no
    # desde el contexto del agente principal.
    assert "_ctx_sub" in src
    assert ".ctx_pct" in src
    # Tras el fix, el header ya NO deriva ctx_str de _agent_loop.context.stats().
    header_region = src.split("result: list")[0]
    assert "context.stats()" not in header_region


# ── Barra de subagentes activos: tarea a UNA línea ───────────────────────────
# Regresión: sub.task puede ser un plan markdown multilínea; la barra de estado
# (_get_subagents_text) lo volcaba entero (con \n) rompiendo el layout. _task_one_line
# lo reduce a la 1.ª línea útil, sin markdown de cabecera y truncado.

def test_task_one_line_collapses_markdown_plan():
    from ui.app import _task_one_line
    out = _task_one_line(
        "# 🚀 Tarea: Continuar Implementación de Sprints WebUI OOCode\n\n"
        "## Plan\n- paso 1\n- paso 2"
    )
    assert "\n" not in out
    assert not out.startswith("#")
    assert out.startswith("🚀 Tarea:")
    assert len(out) <= 60


def test_task_one_line_truncates_long_first_line():
    from ui.app import _task_one_line
    out = _task_one_line("x" * 200)
    assert len(out) == 60
    assert out.endswith("…")


def test_task_one_line_skips_leading_blank_lines():
    from ui.app import _task_one_line
    out = _task_one_line("\n\n   \n- primera línea real")
    assert out == "primera línea real"


def test_task_one_line_empty_and_plain():
    from ui.app import _task_one_line
    assert _task_one_line("") == ""
    assert _task_one_line("analizar main.py") == "analizar main.py"


def test_subagents_bar_uses_one_line_helper():
    """La barra de subagentes (_get_subagent_panel_text) pasa sub.task por _task_one_line."""
    from ui.app import OOCodeApp
    import inspect
    src = inspect.getsource(OOCodeApp._get_subagent_panel_text)
    assert "_task_one_line(sub.task)" in src
