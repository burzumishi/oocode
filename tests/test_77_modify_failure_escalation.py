"""Tests: escalada unificada de fallos de modificación por fichero.

Caso real: el agente cicla edit_file (PRE-EDIT FALLIDO) → regex_replace (duplicado)
→ write_file (duplicado) sobre el MISMO fichero sin avanzar, porque el old_string
ya no existe (el cambio suele estar YA aplicado). Antes solo escalaban los regex sin
coincidencias; edit_file y duplicados no contaban, así que nunca se rompía el bucle.

Ahora `_modify_failure_guidance(path)` cuenta TODOS los fallos por fichero y escala:
- 1.º: instrucción de leer.
- 2.º: inyecta el CONTENIDO REAL del fichero (ground truth).
- 3.º+: parada en seco ("el cambio puede estar ya aplicado, no edites").

Sin LLM ni red.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import MagicMock


def _bare_loop():
    from agent.loop import AgentLoop
    loop = AgentLoop.__new__(AgentLoop)
    loop._failed_modify_by_path = {}
    return loop


# ── Escalada del helper ───────────────────────────────────────────────────────

def test_escalation_first_failure_asks_to_read(tmp_path):
    f = tmp_path / "mapping.py"
    f.write_text("def dist(a, b):\n    return (a[0]-b[0])**2\n")
    loop = _bare_loop()
    msg = loop._modify_failure_guidance(str(f))
    assert "fallo al modificar" in msg
    assert "read_file" in msg
    assert "CONTENIDO REAL" not in msg
    assert "STOP" not in msg


def test_escalation_second_failure_injects_content(tmp_path):
    f = tmp_path / "mapping.py"
    f.write_text("def dist(a, b):\n    return (a[0]-b[0])**2\n")
    loop = _bare_loop()
    loop._modify_failure_guidance(str(f))            # 1.º
    msg = loop._modify_failure_guidance(str(f))      # 2.º
    assert "CONTENIDO REAL ACTUAL" in msg
    assert "def dist(a, b):" in msg                  # contenido literal inyectado
    assert "ya está hecho" in msg.lower()


def test_escalation_third_failure_hard_stop(tmp_path):
    f = tmp_path / "mapping.py"
    f.write_text("x = 1\n")
    loop = _bare_loop()
    for _ in range(2):
        loop._modify_failure_guidance(str(f))
    msg = loop._modify_failure_guidance(str(f))      # 3.º
    assert "STOP" in msg
    assert "NO vuelvas a editar" in msg
    assert "ya está aplicado" in msg.lower()


def test_counter_is_per_file(tmp_path):
    fa = tmp_path / "a.py"; fa.write_text("a=1\n")
    fb = tmp_path / "b.py"; fb.write_text("b=1\n")
    loop = _bare_loop()
    loop._modify_failure_guidance(str(fa))
    loop._modify_failure_guidance(str(fa))
    # b.py arranca de cero pese a los fallos en a.py
    msg_b = loop._modify_failure_guidance(str(fb))
    assert "fallo al modificar" in msg_b
    assert "STOP" not in msg_b


def test_lazy_init_without_attr(tmp_path):
    """El helper funciona aunque _failed_modify_by_path no esté inicializado."""
    from agent.loop import AgentLoop
    loop = AgentLoop.__new__(AgentLoop)   # sin _failed_modify_by_path
    f = tmp_path / "x.py"; f.write_text("x=1\n")
    msg = loop._modify_failure_guidance(str(f))
    assert "fallo al modificar" in msg
    assert isinstance(loop._failed_modify_by_path, dict)


def test_recovery_snippet_caps_large_file(tmp_path):
    f = tmp_path / "big.py"
    f.write_text("\n".join(f"line{i}" for i in range(200)))
    loop = _bare_loop()
    snip = loop._recovery_snippet(str(f), max_lines=50)
    assert "L1: line0" in snip
    assert "líneas más" in snip          # indica truncado
    assert "line199" not in snip


# ── Integración: cross-tool sobre el mismo fichero ────────────────────────────

def test_cross_tool_loop_escalates(tmp_path):
    """edit (PRE-EDIT) → regex/write duplicados sobre el mismo fichero escalan juntos."""
    f = tmp_path / "mapping.py"
    f.write_text("def dist(a, b):\n    return 0\n")
    loop = _bare_loop()
    p = str(f)
    m1 = loop._modify_failure_guidance(p)   # edit_file PRE-EDIT
    m2 = loop._modify_failure_guidance(p)   # regex duplicado
    m3 = loop._modify_failure_guidance(p)   # write duplicado
    assert "CONTENIDO REAL" in m2
    assert "STOP" in m3


# ── Fix 2026-06: steer hacia tools robustas + detección de fallos de smart_replace/edit_files ──

def test_third_failure_suggests_ask_user(tmp_path):
    """GAP 3: en la parada en seco (3.er fallo), la guía sugiere ask_user para que el
    usuario decida, en vez de solo 'explica el bloqueo'."""
    f = tmp_path / "x.c"; f.write_text("int x;\n")
    loop = _bare_loop()
    for _ in range(2):
        loop._modify_failure_guidance(str(f))
    msg = loop._modify_failure_guidance(str(f))   # 3.º
    assert "STOP" in msg
    assert "ask_user" in msg


def test_first_failure_suggests_robust_tools(tmp_path):
    """1.er fallo: la guía debe empujar a smart_replace/regex_replace (toleran espacios) y
    a context_before_edit, no solo a reintentar edit_file exacto."""
    f = tmp_path / "db.c"; f.write_text("int x;\n")
    loop = _bare_loop()
    msg = loop._modify_failure_guidance(str(f))
    assert "smart_replace" in msg
    assert "regex_replace" in msg
    assert "context_before_edit" in msg
    assert "NO reintentes el mismo edit_file" in msg


def test_second_failure_suggests_alternatives_when_no_snippet():
    """2.º fallo sin snippet (fichero inexistente) → sugiere context_before_edit/smart_replace."""
    loop = _bare_loop()
    p = "/nonexistent/path/foo.c"
    loop._modify_failure_guidance(p)        # 1.º
    msg = loop._modify_failure_guidance(p)  # 2.º
    assert "context_before_edit" in msg or "smart_replace" in msg


def _postproc_loop():
    """Loop mínimo para ejercitar _postprocess_tool_result en las ramas de edición."""
    from agent.loop import AgentLoop
    loop = AgentLoop.__new__(AgentLoop)
    loop._failed_modify_by_path = {}
    loop._failed_edit_streak = 0
    loop._failed_edit_patterns = []
    loop._empty_search_streak = 0
    loop._empty_search_patterns = []
    loop._last_tool_calls = []
    return loop


def test_smart_replace_no_match_triggers_guidance(tmp_path):
    f = tmp_path / "act.c"; f.write_text("void f(void) {}\n")
    loop = _postproc_loop()
    res = f"⚠ smart_replace: patrón 'xyz' NO encontrado en '{f.name}' (1 líneas)."
    out = loop._postprocess_tool_result("smart_replace", {"path": str(f), "pattern": "xyz"}, res)
    assert "fallo al modificar" in out
    assert "smart_replace" in out      # la guía propone alternativas robustas
    assert loop._failed_modify_by_path[str(f)] == 1


def test_edit_files_validation_failure_triggers_guidance(tmp_path):
    f = tmp_path / "Makefile.am"; f.write_text("bin_PROGRAMS = myapp\n")
    loop = _postproc_loop()
    res = (f"Validación fallida — no se escribió ningún fichero:\n"
           f"Edición 1 ({f}): cadena no encontrada.")
    out = loop._postprocess_tool_result(
        "edit_files", {"edits": [{"path": str(f), "old_string": "zzz"}]}, res)
    assert "ATÓMICO" in out                       # explica por qué falló todo el lote
    assert "UNA EN UNA" in out or "smart_replace" in out
    assert loop._failed_modify_by_path[str(f)] == 1


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
