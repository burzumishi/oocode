"""Tool ask_user v2 (multi-pregunta): formulario con varias preguntas, multiSelect,
opción de texto libre y navegación por chips. Schema canónico questions[]; tolerante con
la forma plana question/options (modelo pequeño → 1 pregunta).
"""
import threading
from unittest.mock import MagicMock

from agent.loop import AgentLoop
from agent.loop_helpers import normalize_ask_questions, format_ask_questions_result


def _bare_loop(is_subagent=False, capture=False, webui=False):
    loop = AgentLoop.__new__(AgentLoop)
    loop.is_subagent = is_subagent
    loop.capture_output = capture
    loop._webui_queue = MagicMock() if webui else None
    loop._kill_requested = False
    return loop


# ── normalize_ask_questions ──────────────────────────────────────────────────

class TestSystemRulesCoversCompletionQuestion:
    """SYSTEM_RULES debe enrutar por ask_user también las preguntas sí/no de
    continuación al CERRAR una tarea ('¿Deseas que continúe?') — el modelo no las
    veía como 'opciones' y las dejaba en texto plano (logs reales 2026-06-12)."""

    def test_rule_mentions_yes_no_continuation(self):
        from agent.loop import SYSTEM_RULES
        assert "¿Sigo corrigiendo?" in SYSTEM_RULES or "¿Deseas que continúe" in SYSTEM_RULES

    def test_rule_applies_even_when_done(self):
        from agent.loop import SYSTEM_RULES
        assert "AUNQUE consideres la tarea completada" in SYSTEM_RULES


class TestNormalize:
    def test_flat_form_wraps_to_one(self):
        qs = normalize_ask_questions(question="¿A o B?", options=["A", "B"])
        assert len(qs) == 1
        assert qs[0]["question"] == "¿A o B?"
        assert [o["label"] for o in qs[0]["options"]] == ["A", "B"]

    def test_canonical_multi(self):
        qs = normalize_ask_questions(questions=[
            {"header": "H1", "question": "q1", "options": [{"label": "a"}, {"label": "b"}], "multiSelect": True},
            {"question": "q2", "options": ["x", "y", "z"]},
        ])
        assert len(qs) == 2
        assert qs[0]["header"] == "H1" and qs[0]["multiSelect"] is True
        assert qs[1]["header"] == "q2"[:12]   # fallback al texto

    def test_drops_questions_with_under_2_options(self):
        assert normalize_ask_questions(questions=[{"question": "q", "options": ["solo"]}]) == []

    def test_caps_4_questions_6_options(self):
        qs = normalize_ask_questions(questions=[
            {"question": f"q{i}", "options": [f"o{j}" for j in range(8)]} for i in range(7)
        ])
        assert len(qs) == 4
        assert all(len(q["options"]) == 6 for q in qs)

    def test_empty_when_nothing(self):
        assert normalize_ask_questions() == []

    def test_header_fallback_breaks_on_word(self):
        """El header auto-generado corta por palabra (no a media palabra) y quita ¿."""
        from agent.loop_helpers import _short_header
        assert _short_header("¿Apruebo y ejecuto este plan de 12 tareas?") == "Apruebo y"
        assert _short_header("¿Cómo seguimos con las tools?") == "Cómo seguimos"
        # sin header explícito → usa el fallback por palabra (sin signos finales)
        qs = normalize_ask_questions(question="¿Apruebo el plan?", options=["Sí", "No"])
        assert qs[0]["header"] == "Apruebo el plan"


# ── Navegación del formulario (cursor ↑/↓ por opciones) ──────────────────────

class TestQuestionOptionCursor:
    """OOCodeApp._move_question_option: ↑/↓ mueven el cursor de opción con wrap, e
    incluyen la fila de texto libre (nopts). No aplica en el chip Submit."""

    def _fake_app(self, questions, idx=0, opt_idx=0):
        from types import SimpleNamespace
        from ui.app import OOCodeApp
        fake = SimpleNamespace(
            _perm_mode=True,
            _question={"questions": questions, "idx": idx, "opt_idx": opt_idx},
            _app=SimpleNamespace(invalidate=lambda: None),
        )
        fake._move_question_option = OOCodeApp._move_question_option.__get__(fake)
        return fake

    def _q(self, nopts=3):
        return [{"header": "H", "question": "q",
                 "options": [{"label": f"o{i}"} for i in range(nopts)],
                 "multiSelect": False}]

    def test_down_advances_cursor(self):
        app = self._fake_app(self._q(3), opt_idx=0)
        assert app._move_question_option(+1) is True
        assert app._question["opt_idx"] == 1

    def test_down_includes_free_text_row_then_wraps(self):
        # 3 opciones → filas 0,1,2 + libre(3); wrap a 0
        app = self._fake_app(self._q(3), opt_idx=2)
        app._move_question_option(+1)
        assert app._question["opt_idx"] == 3          # fila de texto libre
        app._move_question_option(+1)
        assert app._question["opt_idx"] == 0          # wrap

    def test_up_wraps_to_free_text(self):
        app = self._fake_app(self._q(3), opt_idx=0)
        app._move_question_option(-1)
        assert app._question["opt_idx"] == 3          # fila de texto libre (wrap arriba)

    def test_no_op_on_submit_chip(self):
        app = self._fake_app(self._q(3), idx=1)       # idx == len(questions) → Submit
        assert app._move_question_option(+1) is False

    def test_no_op_when_not_perm_mode(self):
        app = self._fake_app(self._q(3))
        app._perm_mode = False
        assert app._move_question_option(+1) is False


# ── format_ask_questions_result ──────────────────────────────────────────────

class TestFormatResult:
    def _qs(self):
        return normalize_ask_questions(questions=[
            {"header": "Modos", "question": "¿modos?", "options": [{"label": "choice"}, {"label": "multi"}], "multiSelect": True},
            {"header": "UI", "question": "¿UI?", "options": ["TUI", "WebUI"]},
        ])

    def test_pairs_and_agent_text(self):
        qs = self._qs()
        ag, pairs = format_ask_questions_result(qs, [
            {"selection": [0, 1], "free_text": ""},
            {"selection": [], "free_text": "las dos"},
        ])
        assert pairs == [("¿modos?", "choice, multi"), ("¿UI?", "las dos")]
        assert "El usuario respondió" in ag and "choice, multi" in ag

    def test_no_answer_marks_sin_respuesta(self):
        qs = self._qs()
        _, pairs = format_ask_questions_result(qs, [{"selection": [], "free_text": ""}, {}])
        assert pairs[0][1] == "(sin respuesta)"


# ── _execute_ask_user: validación + fallback ─────────────────────────────────

class TestExecuteValidation:
    def test_no_valid_questions(self):
        assert _bare_loop()._execute_ask_user(question="", options=[]).startswith("Error")

    def test_subagent_fallback(self):
        out = _bare_loop(is_subagent=True)._execute_ask_user(question="¿A o B?", options=["A", "B"])
        assert "no disponible" in out and "SIN preguntar" in out

    def test_capture_fallback(self):
        out = _bare_loop(capture=True)._execute_ask_user(question="¿?", options=["A", "B"])
        assert "no disponible" in out

    def test_no_callback_fallback(self):
        assert "no disponible" in _bare_loop()._execute_ask_user(question="¿?", options=["A", "B"])


class TestExecuteElevated:
    """`ask_user` es una pregunta GENUINA del agente → SIEMPRE se muestra, también en
    /elevated (elevated afecta a permisos de tools, no a las preguntas al usuario). La
    aprobación de plan SÍ se salta en elevado, pero eso se gestiona en _execute_plan_create."""

    def _loop(self, level):
        loop = _bare_loop()
        loop.permissions = MagicMock()
        loop.permissions._elevated = level
        loop._render_ask_answers = lambda pairs: None
        return loop

    def test_elevated_full_still_asks(self):
        asked = {}
        loop = self._loop("full")
        loop._ask_user_cb = lambda qs: asked.update(q=qs) or [{"selection": [0], "free_text": ""}]
        loop._execute_ask_user(question="¿A o B?", options=["A", "B"])
        assert asked, "ask_user debe preguntar al usuario incluso en elevated full"

    def test_elevated_on_still_asks(self):
        asked = {}
        loop = self._loop("on")
        loop._ask_user_cb = lambda qs: asked.update(q=qs) or [{"selection": [0], "free_text": ""}]
        loop._execute_ask_user(question="¿A o B?", options=["A", "B"])
        assert asked, "ask_user debe preguntar al usuario incluso en elevated on"

    def test_elevated_ask_still_prompts(self):
        loop = self._loop("ask")
        loop._ask_user_cb = lambda qs: [{"selection": [0], "free_text": ""}]
        out = loop._execute_ask_user(question="¿A o B?", options=["A", "B"])
        assert "auto-resuelto" not in out


# ── _execute_ask_user: TUI callback (multi-pregunta) ─────────────────────────

class TestExecuteTUI:
    def test_relays_and_renders(self):
        loop = _bare_loop()
        captured = {}
        # cb recibe la lista normalizada de preguntas y devuelve answers
        loop._ask_user_cb = lambda qs: (captured.update(qs=qs) or
                                        [{"selection": [0], "free_text": ""}])
        rendered = []
        loop._render_ask_answers = lambda pairs: rendered.append(pairs)
        out = loop._execute_ask_user(questions=[
            {"header": "H", "question": "¿elige?", "options": ["A", "B"]}])
        assert "El usuario respondió" in out and "→ A" in out
        assert len(captured["qs"]) == 1
        assert rendered and rendered[0] == [("¿elige?", "A")]

    def test_cancel_returns_fallback(self):
        loop = _bare_loop()
        loop._ask_user_cb = lambda qs: None    # cancelado
        loop._render_ask_answers = lambda pairs: None
        out = loop._execute_ask_user(question="¿?", options=["A", "B"])
        assert "no respondió o canceló" in out

    def test_callback_exception_safe(self):
        loop = _bare_loop()
        def _cb(qs):
            raise RuntimeError("boom")
        loop._ask_user_cb = _cb
        loop._render_ask_answers = lambda p: None
        assert "falló" in loop._execute_ask_user(question="¿?", options=["A", "B"])


# ── _ask_user_webui (multi) ──────────────────────────────────────────────────

class TestAskUserWebui:
    def test_emits_questions_and_blocks(self):
        loop = _bare_loop(webui=True)
        emitted = []
        loop._webui_emit = lambda ev: emitted.append(ev)
        def _answer():
            import time
            while getattr(loop, "_webui_question_event", None) is None:
                time.sleep(0.005)
            loop._webui_question_answer = [{"selection": [1], "free_text": ""}]
            loop._webui_question_event.set()
        threading.Thread(target=_answer, daemon=True).start()
        qs = normalize_ask_questions(question="¿A o B?", options=["A", "B"])
        out = loop._ask_user_webui(qs)
        assert emitted and emitted[0]["type"] == "question"
        assert emitted[0]["questions"][0]["question"] == "¿A o B?"
        assert out == [{"selection": [1], "free_text": ""}]

    def test_kill_returns_none(self):
        loop = _bare_loop(webui=True)
        loop._webui_emit = lambda ev: None
        def _kill():
            import time
            while getattr(loop, "_webui_question_event", None) is None:
                time.sleep(0.005)
            loop._kill_requested = True
            loop._webui_question_event.set()
        threading.Thread(target=_kill, daemon=True).start()
        qs = normalize_ask_questions(question="¿?", options=["A", "B"])
        assert loop._ask_user_webui(qs) is None


# ── _render_ask_answers ──────────────────────────────────────────────────────

class TestRenderAnswers:
    def test_webui_emits_ask_answers(self):
        loop = _bare_loop(webui=True)
        emitted = []
        loop._webui_emit = lambda ev: emitted.append(ev)
        loop._render_ask_answers([("¿q1?", "A"), ("¿q2?", "B")])
        assert emitted[0]["type"] == "ask_answers"
        assert emitted[0]["pairs"] == [{"q": "¿q1?", "a": "A"}, {"q": "¿q2?", "a": "B"}]

    def test_tui_prints(self):
        loop = _bare_loop()
        loop.capture_output = False
        lines = []
        loop._print = lambda s: lines.append(s)
        loop._render_ask_answers([("¿q1?", "A")])
        joined = " ".join(lines)
        assert "User answered OOCode's questions" in joined and "¿q1?" in joined and "A" in joined


class TestRegistered:
    def test_method_exists(self):
        assert callable(AgentLoop._execute_ask_user)
        assert callable(AgentLoop._ask_user_webui)
        assert callable(AgentLoop._render_ask_answers)


class TestAskUserIntegration:
    """ask_user integrada coherentemente: permiso auto (no circular), no-cache, y la
    forma plana (que usan los backstops de _turn_guidance) sigue siendo válida."""

    def test_permission_is_auto(self):
        from config import OOConfig
        from tools.permissions import PermissionManager
        pm = PermissionManager(OOConfig.load().permissions)
        assert pm.resolve_mode("ask_user") == "auto"

    def test_is_no_cache(self):
        from tools.registry import _is_no_cache
        assert _is_no_cache("ask_user") is True

    def test_flat_form_tolerated_for_backstops(self):
        # Los hints de _turn_guidance sugieren ask_user(question, options=[…]); debe normalizar.
        qs = normalize_ask_questions(question="¿saltar o reintentar?",
                                     options=["saltar", "reintentar"])
        assert len(qs) == 1 and len(qs[0]["options"]) == 2

    def test_default_permission_in_config_block(self):
        from config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["permissions"].get("ask_user") == "auto"
