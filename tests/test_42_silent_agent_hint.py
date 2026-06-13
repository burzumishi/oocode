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


class TestRenderThinking:
    """El razonamiento del modelo (canal <think>) se muestra como narración tenue;
    antes se descartaba. Da el 'porqué' cuando think_level != off."""

    def _vis_loop(self):
        from rich.console import Console
        loop = _make_loop()
        loop.capture_output = False
        loop._webui_queue = None
        loop.is_subagent = False
        loop.rt.accent_color = "cyan"
        # _print ahora recibe renderables Rich (Padding/Markdown) → renderizar de verdad
        # a texto para inspeccionar alineación y contenido markdown.
        _con = Console(width=100, force_terminal=False)
        printed = []
        def _p(*a, **k):
            with _con.capture() as cap:
                _con.print(*a, **k)
            printed.append(cap.get())
        loop._print = _p
        return loop, printed

    def test_thinking_rendered_but_not_counted_as_narration(self):
        # El 💭 se MUESTRA pero NO cuenta como texto visible: no debe tocar
        # _turn_text_emitted, o el hint #15 quedaría desactivado con /think activo
        # y el agente seguiría mudo pese a razonar.
        loop, printed = self._vis_loop()
        loop._turn_text_emitted = False
        loop._render_thinking("Voy a quitar el typedef _Bool porque ya existe en C99.")
        joined = " ".join(printed)
        assert "Voy a quitar el typedef" in joined and "💭" in joined
        assert loop._turn_text_emitted is False   # el 💭 NO sustituye al texto visible

    def test_thinking_markdown_and_alignment(self):
        """El razonamiento se renderiza como Markdown (listas) y alineado (col ≥2)."""
        loop, printed = self._vis_loop()
        loop._render_thinking("Resumen:\n\n1. **uno** ok\n2. **dos** ok")
        out = "".join(printed)
        # Las líneas no caen a la columna 0 (van indentadas con la conversación)
        body_lines = [l for l in out.split("\n") if l.strip()]
        assert body_lines and all(l.startswith(" ") for l in body_lines)
        # Markdown: los marcadores ** desaparecen al renderizar negrita
        assert "**" not in out

    def test_empty_thinking_noop(self):
        loop, printed = self._vis_loop()
        loop._turn_text_emitted = False
        loop._render_thinking("   ")
        assert printed == []
        assert loop._turn_text_emitted is False

    def test_thinking_inside_open_block_uses_pipe_prefix(self):
        """Con un bloque de tools abierto, el razonamiento intermedio va DENTRO del
        bloque con prefijo │ (no rompe el bloque del fichero)."""
        loop, printed = self._vis_loop()
        loop._bullet_block_open = True
        loop._render_thinking("Veo un else sin if. Voy a reescribir esa sección.")
        out = "".join(printed)
        assert "│" in out and "💭" in out and "else sin if" in out

    def test_thinking_emitted_to_webui(self):
        loop = _make_loop()
        loop.capture_output = False
        emitted = []
        loop._webui_queue = object()
        loop._webui_emit = lambda ev: emitted.append(ev)
        loop._render_thinking("razono esto")
        assert any(e.get("type") == "reasoning" and "razono" in e.get("text", "") for e in emitted)

    def test_reasoning_step_requires_distinct_thinking(self):
        """Paso nuevo por RAZONAMIENTO (2026-06-12, estructura por paso estilo Claude
        Code): un 💭 DISTINTO en una iteración de continuación dup/tool-only abre su
        propio bloque (el 💭 sale entre bloques + ● etiquetado por la 1ª tool), para
        que los pasos no se fusionen en "Used N tools". Pero está GATED para no repetir
        la regresión del flush-incondicional-al-razonar (2026-06-11): exige `_is_dup_bullet`
        + `_thinking_shown` + `tool_calls` + `_bullet_block_open` + `_is_new_reasoning`.
        Razonar repitiendo el MISMO pensamiento (o sin tools) NO abre paso."""
        import inspect
        from agent.loop import AgentLoop
        src = inspect.getsource(AgentLoop.run)
        # _is_dup_bullet se calcula ANTES del cálculo del paso (el flush pone
        # _bullet_block_open=False y haría el dedup siempre False).
        i_dup  = src.index("_is_dup_bullet = self._is_duplicate_bullet")
        i_step = src.index("_reasoning_step = bool(")
        assert i_dup < i_step
        seg = src[i_step:i_step + 320]
        # Todos los guards que impiden trocear deben estar presentes.
        assert "_is_dup_bullet" in seg
        assert "_thinking_shown" in seg
        assert "tool_calls" in seg
        assert "_bullet_block_open" in seg
        assert "_is_new_reasoning" in seg
        # El paso de texto canónico (no-dup) sigue existiendo.
        assert "_text_step = bool(" in src
        assert "_new_step = _text_step or _reasoning_step" in src
        # El flush previo al render del 💭 sigue gateado por _new_step.
        j = src.index("self._render_thinking(self._last_thinking)")
        pre = src[:j]
        k = pre.rindex("self._flush_turn_block()")
        assert "if _new_step:" in pre[max(0, k - 120):k]
        assert "_file_changed" not in src
        assert "_continue_same_file" not in src

    def test_is_new_reasoning_dedupes_identical(self):
        """_is_new_reasoning: vacío/idéntico → False (no trocea); distinto → True."""
        loop = _make_loop()
        loop._last_step_thinking = ""
        assert loop._is_new_reasoning("") is False
        assert loop._is_new_reasoning("Reviso el módulo de monedas") is True
        loop._last_step_thinking = "reviso el módulo de monedas"
        # mismo pensamiento (normalizado: minúsculas + espacios colapsados) → no abre paso
        assert loop._is_new_reasoning("Reviso  el módulo  de monedas") is False
        assert loop._is_new_reasoning("Ahora corrijo el error de sintaxis") is True

    def test_new_text_always_displays_bullet(self):
        """REGRESIÓN (2026-06-11 noche): `_continue_same_file` suprimía el ● del texto
        nuevo cuando había razonamiento sin cambio de fichero — el usuario perdía los
        mensajes del agente (incluida la respuesta final del turno si el bloque seguía
        abierto). Texto nuevo no-duplicado SIEMPRE flushea el bloque previo y muestra
        su ● vía _turn_display_bullet."""
        import inspect
        from agent.loop import AgentLoop
        src = inspect.getsource(AgentLoop.run)
        assert "_continue_same_file" not in src
        assert "if _is_dup_bullet:" in src
        i = src.index("elif (text or tool_calls):")
        seg = src[i:i + 400]
        assert "self._flush_turn_block()" in seg
        assert "self._turn_display_bullet(text, tool_calls)" in seg

    def test_context_file_machinery_removed(self):
        """La maquinaria del flush-por-razonamiento (2026-06-11 noche) se eliminó por
        completo al restaurar el comportamiento bueno: ni helpers ni estado deben
        existir. La agrupación por fichero vive SOLO en el auto-split de las write
        tools (_current_write_target en _show_tool_running_header)."""
        from agent.loop import AgentLoop
        for attr in ("_next_context_file", "_extract_context_file", "_FILE_CONTEXT_TOOLS"):
            assert not hasattr(AgentLoop, attr), f"{attr} debería estar eliminado"
        loop = _make_loop()
        assert not hasattr(loop, "_current_context_file")


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

    def test_flag_per_iteration_not_per_run(self):
        """Regresión: el flag refleja la ÚLTIMA iteración, no todo el run().

        El run loop fija `_turn_text_emitted = bool(text) and not _is_dup_bullet`.
        Antes era un flag de run() que se quedaba en True tras el primer texto, así
        que el modelo encadenaba decenas de tools tool-only sin que el hint #15 se
        re-disparara ("Used 75 tools" sin narración). Verifica la nueva semántica:
        una iteración tool-only (texto vacío) o un preámbulo duplicado → False.
        """
        loop = _make_loop()
        # Iteración 1: narró (texto nuevo, no duplicado)
        text1, dup1 = "Comienzo con la limpieza:", False
        assert (bool(text1) and not dup1) is True
        # Iteración 2: tool-only (texto vacío) → NO narra → flag False → hint re-arma
        text2, dup2 = "", False
        assert (bool(text2) and not dup2) is False
        # Iteración 3: reemite el MISMO preámbulo (duplicado) → tampoco narra
        text3, dup3 = "Comienzo con la limpieza:", True
        assert (bool(text3) and not dup3) is False

    def test_duplicate_preamble_is_not_narration(self):
        """Un preámbulo reemitido palabra por palabra cuenta como duplicado (no narra)."""
        loop = _make_loop()
        loop.capture_output = False
        loop._bullet_block_open = True
        loop._last_displayed_bullet = "Comienzo con la limpieza"
        tc = [("bash", "{}", "ok")]
        # Mismo texto que el último bullet mostrado → duplicado
        assert loop._is_duplicate_bullet("Comienzo con la limpieza", tc) is True
        # Texto vacío con bloque abierto → también se adjunta (tool-only)
        assert loop._is_duplicate_bullet("", tc) is True
        # Texto NUEVO → no es duplicado → sí narra
        assert loop._is_duplicate_bullet("Ahora edito mud.h", tc) is False


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

    def test_hint_names_recent_silent_tools(self):
        """El nudge nombra las últimas tools usadas en silencio (referencia concreta,
        lanza mejor en modelos parcos que solo ejemplos genéricos)."""
        loop = _make_loop()
        loop._last_tool_calls = [
            ("grep_code", '{"pattern":"x"}', "ok"),
            ("read_file", '{"path":"a"}', "ok"),
            ("read_file", '{"path":"b"}', "ok"),
        ]
        loop._turn_text_emitted = False
        result = self._guidance(loop)
        assert "Acabas de usar" in result
        assert "grep_code" in result and "read_file" in result


# ── Tests de SYSTEM_RULES ─────────────────────────────────────────────────────

class TestSystemRulesAnnouncement:
    """SYSTEM_RULES contiene la regla de anuncio obligatorio."""

    def test_mandatory_announcement_rule_present(self):
        """La regla de comunicación con usuario está en SYSTEM_RULES."""
        from agent.loop import SYSTEM_RULES
        assert "Comunicación" in SYSTEM_RULES or "usuario NO ve" in SYSTEM_RULES

    def test_user_cannot_see_tools_explained(self):
        """La regla explica que el usuario NO ve las tools ni sus resultados."""
        from agent.loop import SYSTEM_RULES
        assert "NO VE LAS TOOLS NI SUS RESULTADOS" in SYSTEM_RULES or \
               "NO ve tools" in SYSTEM_RULES or \
               "no ve tools" in SYSTEM_RULES.lower() or \
               "usuario NO ve" in SYSTEM_RULES

    def test_examples_in_rule(self):
        """La regla incluye instrucción de anuncio antes de actuar."""
        from agent.loop import SYSTEM_RULES
        assert ("Antes de actuar" in SYSTEM_RULES or "anuncia brevemente" in SYSTEM_RULES
                or "Comunicación" in SYSTEM_RULES or "Tras exploración" in SYSTEM_RULES)

    def test_verbose_rule_preserved(self):
        """La regla de verbosidad adaptada sigue presente (sin relleno, no silencio)."""
        from agent.loop import SYSTEM_RULES
        assert ("sin relleno" in SYSTEM_RULES or "Sin relleno" in SYSTEM_RULES
                or "Verbosidad" in SYSTEM_RULES)


class TestThinkingPreserved:
    """El razonamiento del modelo NO debe perderse por el camino (causa real de
    "no veo los 💭": cada return de error/retry/sync de _stream_response descartaba
    thinking_parts, y los retries XML van con /no_think → tampoco traen nuevo)."""

    def _src(self):
        import inspect
        from agent.loop import AgentLoop
        return inspect.getsource(AgentLoop._stream_response)

    def test_error_block_preserves_thinking_before_retries(self):
        """Al entrar en el bloque de error, _last_thinking se fija desde
        thinking_parts ANTES de los retries XML (cubre todos los returns)."""
        src = self._src()
        i_err = src.index("if error:")
        i_set = src.index('self._last_thinking = "".join(thinking_parts).strip()', i_err)
        i_retry = src.index("xml_eof_truncation_retry")
        assert i_err < i_set < i_retry

    def test_sync_path_sets_thinking(self):
        """El path sync (subagentes/captura) propaga resp.thinking — los subagentes
        nunca mostraban 💭 aunque el modelo razonara."""
        src = self._src()
        i_sync = src.index("if self.capture_output or self.is_subagent:")
        seg = src[i_sync:i_sync + 1500]
        assert 'self._last_thinking = getattr(resp, "thinking", "")' in seg

    def test_plain_branch_collects_thinking(self):
        """La rama REPL sin fallback también acumula chunk.thinking."""
        src = self._src()
        i_plain = src.index("Sin fallback: comportamiento original")
        seg = src[i_plain:i_plain + 900]
        assert "thinking_parts.append(chunk.thinking)" in seg

    def test_thinking_counts_as_watchdog_activity(self):
        """En modo app, el thinking cuenta como actividad del stream: sin esto el
        watchdog de timeout mataba iteraciones que razonaban largo sin emitir texto
        (paridad con el path REPL, que ya lo sumaba a _out_chars_r)."""
        src = self._src()
        i_bg = src.index("def _stream_bg")
        seg = src[i_bg:i_bg + 1600]
        assert "_out_chars_sh[0] += len(chunk.thinking)" in seg

    def test_response_dataclass_has_thinking(self):
        from api.base import Response
        assert Response(thinking="x").thinking == "x"
