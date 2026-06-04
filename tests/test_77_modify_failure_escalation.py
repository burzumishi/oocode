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


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
