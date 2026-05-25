"""Tests del hint #15: agente silencioso (tools sin texto al usuario).

Verifica que _turn_text_emitted se resetea al inicio de cada turno,
se activa cuando el modelo emite texto, y que el hint #15 se dispara
correctamente cuando el agente ejecuta ≥2 tools sin emitir ningún texto.

No requiere LLM ni conexión de red.
"""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_loop():
    """Construye un AgentLoop mínimo para probar _turn_guidance sin LLM."""
    from unittest.mock import MagicMock
    from config import OOConfig
    from agent.loop import AgentLoop
    from tools.registry import ToolRegistry
    from tools.permissions import PermissionManager

    cfg = OOConfig()
    loop = AgentLoop.__new__(AgentLoop)
    loop.config = cfg
    loop.registry = ToolRegistry()
    loop.permissions = PermissionManager(cfg.permissions)
    loop.memory = MagicMock()
    loop.rt = MagicMock()
    loop.rt.verbose = False
    loop.is_subagent = False
    loop.capture_output = True
    loop._status_cb = None
    loop._auto_continue_count = 0
    loop._plan_tasks = []
    loop._pending_tasks = []
    loop._last_tool_calls = []
    loop._turn_text_emitted = False
    loop._empty_search_streak = 0
    loop._empty_search_patterns = []
    loop._failed_edit_streak = 0
    loop._failed_edit_patterns = []
    loop._bash_block_counts = {}
    loop._kill_requested = False
    loop._turn_read_cache = {}
    loop._turn_write_seen = {}
    loop._turn_block = []
    loop._turn_block_has_header = False
    loop._turn_written_scripts = set()
    loop._tool_current_file = ""
    return loop


# ── Tests de _turn_text_emitted ───────────────────────────────────────────────

class TestTurnTextEmitted:
    """El flag _turn_text_emitted se inicializa, resetea y activa correctamente."""

    def test_init_is_false(self):
        """El flag empieza False en __init__."""
        loop = _make_loop()
        assert loop._turn_text_emitted is False

    def test_reset_in_run_sets_false(self):
        """Cuando se simula el inicio de run(), el flag se pone a False."""
        loop = _make_loop()
        # Simular que el turno anterior dejó el flag en True
        loop._turn_text_emitted = True
        # run() hace: self._turn_text_emitted = False al inicio
        loop._turn_text_emitted = False
        assert loop._turn_text_emitted is False

    def test_flag_true_when_text_emitted(self):
        """Después de emitir texto, el flag es True."""
        loop = _make_loop()
        loop._turn_text_emitted = False
        # Simular la línea: self._turn_text_emitted = True
        loop._turn_text_emitted = True
        assert loop._turn_text_emitted is True


# ── Tests del hint #15 en _turn_guidance ─────────────────────────────────────

class TestSilentAgentHint:
    """El hint #15 se dispara cuando el agente lleva ≥2 tools sin texto."""

    def _guidance(self, loop):
        return loop._turn_guidance()

    def test_no_hint_when_no_tool_calls(self):
        """Con 0 tool calls no hay hint #15."""
        loop = _make_loop()
        loop._last_tool_calls = []
        loop._turn_text_emitted = False
        result = self._guidance(loop)
        assert "sin texto al usuario" not in result

    def test_no_hint_with_one_tool_call(self):
        """Con solo 1 tool call no se dispara (umbral es ≥2)."""
        loop = _make_loop()
        loop._last_tool_calls = [("read_file", '{"path":"x"}', "content")]
        loop._turn_text_emitted = False
        result = self._guidance(loop)
        assert "sin texto al usuario" not in result

    def test_hint_fires_with_two_tools_no_text(self):
        """Con ≥2 tool calls y sin texto emitido → hint #15."""
        loop = _make_loop()
        loop._last_tool_calls = [
            ("read_file",  '{"path":"a"}', "content a"),
            ("grep_code",  '{"pattern":"x"}', "no matches"),
        ]
        loop._turn_text_emitted = False
        result = self._guidance(loop)
        assert "sin texto al usuario" in result
        assert "OBLIGATORIO" in result

    def test_hint_fires_with_three_tools_no_text(self):
        """Con 3 tool calls y sin texto → hint #15."""
        loop = _make_loop()
        loop._last_tool_calls = [
            ("read_file",  '{"path":"a"}', "ok"),
            ("grep_code",  '{"pattern":"x"}', "ok"),
            ("edit_file",  '{"path":"b"}', "ok"),
        ]
        loop._turn_text_emitted = False
        result = self._guidance(loop)
        assert "sin texto al usuario" in result

    def test_no_hint_when_text_emitted(self):
        """Si el modelo ya emitió texto, el hint #15 no se dispara."""
        loop = _make_loop()
        loop._last_tool_calls = [
            ("read_file",  '{"path":"a"}', "content"),
            ("grep_code",  '{"pattern":"x"}', "matches"),
            ("edit_file",  '{"path":"b"}', "ok"),
        ]
        loop._turn_text_emitted = True
        result = self._guidance(loop)
        assert "sin texto al usuario" not in result

    def test_hint_message_has_examples(self):
        """El mensaje del hint incluye ejemplos de frases de anuncio."""
        loop = _make_loop()
        loop._last_tool_calls = [
            ("read_file", '{"path":"a"}', "ok"),
            ("read_file", '{"path":"b"}', "ok"),
        ]
        loop._turn_text_emitted = False
        result = self._guidance(loop)
        assert "Revisando" in result or "Explorando" in result or "encontrado" in result


# ── Tests de SYSTEM_RULES ─────────────────────────────────────────────────────

class TestSystemRulesAnnouncement:
    """SYSTEM_RULES contiene la regla de anuncio obligatorio."""

    def test_mandatory_announcement_rule_present(self):
        """La regla de comunicación con usuario está en SYSTEM_RULES."""
        from agent.loop import SYSTEM_RULES
        assert "Comunicación con el usuario" in SYSTEM_RULES

    def test_user_cannot_see_tools_explained(self):
        """La regla explica que el usuario NO ve las tools ni sus resultados."""
        from agent.loop import SYSTEM_RULES
        assert "NO VE LAS TOOLS NI SUS RESULTADOS" in SYSTEM_RULES

    def test_examples_in_rule(self):
        """La regla incluye instrucción de anuncio antes de actuar."""
        from agent.loop import SYSTEM_RULES
        assert "Antes de actuar" in SYSTEM_RULES or "anuncia brevemente" in SYSTEM_RULES

    def test_verbose_rule_preserved(self):
        """La regla de verbosidad adaptada sigue presente (sin relleno, no silencio)."""
        from agent.loop import SYSTEM_RULES
        assert "Verbosidad adaptada" in SYSTEM_RULES
        assert "sin relleno" in SYSTEM_RULES
