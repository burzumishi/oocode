"""Tests para el dispatch de tools de orquestación (subagentes/equipos).

Regresión: cuando el LLM batcheaba `spawn_subagent` junto a tools de exploración
(`grep_code`, `read_file`…), el dispatch las ejecutaba en paralelo dentro del
ThreadPoolExecutor. El header especial del subagente (● [emoji nombre]: tarea) y
su streaming `│` solo se renderizan en la rama secuencial, así que el output del
subagente quedaba "encerrado" en el bloque de tools anterior y colisionaba en el
live block del padre.

Fix: las tools de `_ORCHESTRATION_TOOLS` fuerzan modo secuencial — su presencia
en un lote pone `_safe_parallel` a False.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from types import SimpleNamespace
from unittest.mock import MagicMock


def _make_loop():
    from agent.loop import AgentLoop
    from tools.registry import ToolRegistry
    from config import OOConfig
    cfg = OOConfig()
    loop = AgentLoop.__new__(AgentLoop)
    loop.config = cfg
    loop.registry = ToolRegistry()
    loop.permissions = MagicMock()
    loop.permissions.check = MagicMock(return_value=True)
    loop.memory = MagicMock()
    loop.is_subagent = False
    loop.capture_output = False
    loop._status_cb = None
    loop._plan_tasks = []
    loop._kill_requested = False
    loop._sep_label = ""
    loop._tool_current_file = ""
    loop.context = MagicMock()
    loop.context.stats.return_value = {"tokens_estimate": 10, "max_tokens": 1000}
    loop.context.compact_threshold = 0.8
    # Mockear ejecución y rendering de headers (no nos interesa el output real)
    loop._execute_tool = MagicMock(return_value="ok")
    loop._run_animated_header = MagicMock(return_value="ok")
    loop._show_tool_running_header = MagicMock()
    loop._webui_emit = MagicMock()
    loop._strip_rich = lambda s: s
    loop._call_context = lambda n, a: ""
    loop._TOOL_DISPLAY_NAMES = {}
    return loop


def _tc(name, args=None):
    return SimpleNamespace(
        function=SimpleNamespace(name=name, arguments=args or {})
    )


def _dispatch(loop, names):
    calls = [_tc(n) for n in names]
    return loop._turn_dispatch_tools(calls, total_inp=0, total_out=0)


def test_orchestration_constant_contents():
    from agent.loop import _ORCHESTRATION_TOOLS
    assert _ORCHESTRATION_TOOLS == frozenset(
        {"spawn_subagent", "spawn_fanout", "create_team", "run_team", "explore"}
    )


def test_mixed_batch_with_spawn_subagent_forces_sequential():
    """spawn_subagent + exploración en el mismo lote → NO paralelo."""
    loop = _make_loop()
    *_, safe_parallel = _dispatch(loop, ["grep_code", "spawn_subagent", "read_file"])
    assert safe_parallel is False


def test_pure_read_batch_stays_parallel():
    """Lote solo de lectura → sí paralelo (comportamiento previo intacto)."""
    loop = _make_loop()
    *_, safe_parallel = _dispatch(loop, ["grep_code", "read_file", "find_file"])
    assert safe_parallel is True


def test_every_orchestration_tool_blocks_parallel():
    """Cualquier tool de orquestación en el lote desactiva el paralelismo."""
    from agent.loop import _ORCHESTRATION_TOOLS
    for orch in _ORCHESTRATION_TOOLS:
        loop = _make_loop()
        *_, safe_parallel = _dispatch(loop, ["read_file", orch])
        assert safe_parallel is False, f"{orch} debería forzar secuencial"


def test_bash_still_blocks_parallel():
    """Regresión: bash sigue forzando secuencial."""
    loop = _make_loop()
    *_, safe_parallel = _dispatch(loop, ["read_file", "bash"])
    assert safe_parallel is False


def test_single_call_never_parallel():
    """Una sola tool nunca activa el modo paralelo."""
    loop = _make_loop()
    *_, safe_parallel = _dispatch(loop, ["read_file"])
    assert safe_parallel is False
