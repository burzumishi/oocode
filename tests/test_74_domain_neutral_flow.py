"""Tests: flujo de conversación agnóstico de dominio (gaps A y B).

A — SYSTEM_RULES tiene un núcleo neutral (clasifica→reúne→actúa→verifica→finaliza)
    aplicable a cualquier dominio, con la disciplina de código en un bloque
    condicional ("Cuando trabajes con código").

B — Los hints dinámicos no asumen edición de código:
    - #14 (escrituras sin tests) solo se dispara si se tocó CÓDIGO real
      (por extensión); un agente que genera .docx/.xlsx/.md no recibe el aviso.
    - #6/#9 usan wording neutral (no mandan "usa edit_file/write_file").

Sin LLM ni red.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import MagicMock


def _make_loop():
    from config import OOConfig
    from agent.loop import AgentLoop
    from tools.registry import ToolRegistry

    cfg = OOConfig()
    loop = AgentLoop.__new__(AgentLoop)
    loop.config = cfg
    loop.registry = ToolRegistry()
    loop.memory = MagicMock()
    loop.rt = MagicMock()
    loop.is_subagent = False
    loop.capture_output = True
    loop._status_cb = None
    loop._auto_continue_count = 0
    loop._plan_tasks = []
    loop._pending_tasks = []
    loop._last_tool_calls = []
    loop._turn_text_emitted = True   # evitar hint #15 en estos tests
    loop._session_reads = []
    loop._task_last_test = ""
    return loop


# ── A — SYSTEM_RULES neutral ──────────────────────────────────────────────────

def test_system_rules_has_neutral_core():
    from agent.loop import SYSTEM_RULES
    assert "Aplica el ciclo a tu dominio" in SYSTEM_RULES
    # El paso de acción ya no es exclusivo de edición de ficheros
    assert "editar, crear, enviar, ejecutar" in SYSTEM_RULES


def test_system_rules_code_block_is_conditional():
    from agent.loop import SYSTEM_RULES
    assert "**Cuando trabajes con código:**" in SYSTEM_RULES
    # La disciplina de ficheros grandes y edición segura vive dentro del bloque condicional
    assert "code_outline" in SYSTEM_RULES
    assert "Edición segura" in SYSTEM_RULES


def test_system_rules_preserves_communication_rule():
    from agent.loop import SYSTEM_RULES
    assert "Comunicación" in SYSTEM_RULES
    assert "usuario NO ve" in SYSTEM_RULES
    # La regla mantiene el "no trabajar en silencio" y distingue calidez de relleno hueco.
    assert "relleno HUECO" in SYSTEM_RULES
    assert "nunca trabajes en silencio" in SYSTEM_RULES


# ── B — hint #14 por extensión ────────────────────────────────────────────────

def test_hint14_fires_for_code_edit():
    loop = _make_loop()
    loop._last_tool_calls = [
        ("read_file", '{"path":"main.py"}', "content"),
        ("edit_file", '{"path":"main.py"}', "edited"),
    ]
    hint = loop._turn_guidance()
    assert "tests no ejecutados" in hint


def test_hint14_suppressed_for_docx_only():
    """Un agente de ofimática que genera un .docx NO debe recibir el aviso de tests."""
    loop = _make_loop()
    loop._last_tool_calls = [
        ("read_file", '{"path":"datos.csv"}', "content"),
        ("write_file", '{"path":"/home/u/informe.docx"}', "ok"),
    ]
    hint = loop._turn_guidance()
    assert "tests no ejecutados" not in hint


def test_hint14_suppressed_for_markdown_only():
    loop = _make_loop()
    loop._last_tool_calls = [
        ("write_file", '{"path":"README.md"}', "ok"),
        ("write_file", '{"path":"notas.txt"}', "ok"),
    ]
    hint = loop._turn_guidance()
    assert "tests no ejecutados" not in hint


def test_hint14_fires_when_mixed_code_and_doc():
    """Si entre las escrituras hay código, sí avisa (conservador)."""
    loop = _make_loop()
    loop._last_tool_calls = [
        ("write_file", '{"path":"informe.docx"}', "ok"),
        ("edit_file", '{"path":"app.py"}', "edited"),
    ]
    hint = loop._turn_guidance()
    assert "tests no ejecutados" in hint


def test_hint14_fires_when_path_unknown():
    """Sin ruta detectable → conservador → avisa."""
    loop = _make_loop()
    loop._last_tool_calls = [
        ("read_file", '{"path":"x"}', "c"),
        ("edit_files", '{"foo":"bar"}', "ok"),
    ]
    hint = loop._turn_guidance()
    assert "tests no ejecutados" in hint


def test_hint14_silent_when_tests_ran():
    loop = _make_loop()
    loop._last_tool_calls = [
        ("edit_file", '{"path":"main.py"}', "edited"),
        ("run_tests", '{"path":"tests/"}', "5 passed"),
    ]
    hint = loop._turn_guidance()
    assert "tests no ejecutados" not in hint


# ── B — wording neutral en #6 y #9 ────────────────────────────────────────────

def test_hint6_wording_is_domain_neutral():
    loop = _make_loop()
    loop._last_tool_calls = [("read_file", "{}", "c")] * 9 + [("grep_code", "{}", "m")]
    hint = loop._turn_guidance()
    assert "exploración sin acción" in hint
    # No debe mandar específicamente editar ficheros de código
    assert "usa edit_file, write_file o bulk_replace" not in hint


def test_hint9_wording_is_domain_neutral():
    loop = _make_loop()
    loop._last_tool_calls = [
        ("grep_code", "{}", "f"),
        ("grep_code", "{}", "f"),
        ("symbol_lookup", "{}", "f"),
        ("find_file", "{}", "f"),
        ("ls_dir", "{}", "d"),
        ("read_file", '{"path":"x.py"}', "c"),
    ]
    hint = loop._turn_guidance()
    assert "búsquedas sin avance" in hint
    assert "di 'Implemento:' antes de editar" not in hint


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
