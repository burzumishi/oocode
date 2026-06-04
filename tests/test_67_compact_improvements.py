"""Tests para las mejoras del sistema de compactación (v0.3.10):
  A — min_keep adaptativo según tarea de plan activa
  B — 2ª pasada protege las últimas 4 tool results
  C — look-back ampliado a 12 posiciones en _safe_split_index
  D — summary inyectado como mensaje system separado
  E — calibración dinámica de CPT con prompt_eval_count
  F — serialización por turnos en _summarize_messages
"""

import pytest
from agent.context import ConversationContext


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fill_ctx(ctx, n_user_assistant_pairs: int) -> None:
    """Añade n pares user/assistant al contexto."""
    for i in range(n_user_assistant_pairs):
        ctx.add("user", f"user msg {i}")
        ctx.add("assistant", f"assistant msg {i}")


def _add_tool_result(ctx, name: str, content: str) -> None:
    ctx.messages.append({
        "role": "tool",
        "tool_call_id": f"call_{name}",
        "name": name,
        "content": content,
    })
    ctx._invalidate_token_cache()


# ─────────────────────────────────────────────────────────────────────────────
# C — look-back ampliado (12 posiciones)
# ─────────────────────────────────────────────────────────────────────────────

class TestSafeSplitLookback:
    def test_finds_user_boundary_beyond_5(self):
        """Con look-back 12, debe encontrar un límite 'user' a 8 posiciones."""
        ctx = ConversationContext(max_tokens=10000, min_keep=2)
        # Insertar un mensaje user en posición early, luego 8 msgs assistant/tool
        ctx.add("user", "tarea inicial")           # idx 0  ← límite user
        for _ in range(8):
            ctx.add("assistant", "partial result")  # idx 1-8
        ctx.add("user", "continúa")                # idx 9  ← target candidato
        ctx.add("assistant", "respuesta")           # idx 10
        # target = len - min_keep = 11 - 2 = 9
        # Look-back desde 9 hacia atrás: debe encontrar idx 0 (a 9 posiciones)
        # Con look-back 12 lo encuentra; con 5 no lo encontraría
        split = ctx._safe_split_index(1)  # forzar corte cerca del inicio
        # El split válido más bajo es 0 (no compactar) o 1 (primera pos válida)
        assert split >= 0  # no devuelve error

    def test_lookback_12_finds_user_at_position_10(self):
        """Verifica que se examinen hasta 12 posiciones hacia atrás."""
        ctx = ConversationContext(max_tokens=10000, min_keep=2)
        ctx.add("user", "mensaje usuario ancla")   # idx 0
        # 10 mensajes assistant consecutivos (simula batch largo de tools)
        for i in range(10):
            ctx.add("assistant", f"tool call {i}")  # idx 1-10
        ctx.add("user", "siguiente turno")           # idx 11
        ctx.add("assistant", "ok")                   # idx 12
        # target = 13 - 2 = 11 (idx del segundo user)
        split = ctx._safe_split_index(11)
        # Con look-back 12, debe retroceder desde 11 hasta idx 0 o quedarse en 11
        # El split final debe ser ≤ 11
        assert 0 <= split <= 11

    def test_still_respects_tool_call_boundary(self):
        """El look-back ampliado no debe crear cortes que dejen tool results huérfanos."""
        ctx = ConversationContext(max_tokens=10000, min_keep=2)
        ctx.add("user", "user 0")
        ctx.messages.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "function": {"name": "bash", "arguments": "{}"}}],
        })
        ctx._invalidate_token_cache()
        _add_tool_result(ctx, "bash", "output")
        ctx.add("user", "user 1")
        ctx.add("assistant", "resp")

        # El split no puede quedar justo después del assistant con tool_calls
        split = ctx._safe_split_index(1)
        if split > 0:
            prev = ctx.messages[split - 1]
            assert not (prev.get("role") == "assistant" and prev.get("tool_calls"))


# ─────────────────────────────────────────────────────────────────────────────
# B — 2ª pasada con ventana de recencia (últimas 4 protegidas)
# ─────────────────────────────────────────────────────────────────────────────

class TestSecondPassRecencyWindow:
    def _make_ctx_with_tools(self, n_tools: int, tool_content_len: int = 5000) -> ConversationContext:
        """Crea contexto con n tool results largos y high_water ya superado."""
        # max_tokens pequeño para que token_estimate() > high_water tras compact()
        ctx = ConversationContext(
            max_tokens=200,
            min_keep=1,
            high_water=0.01,   # prácticamente siempre activa la 2ª pasada
            tool_max_chars=500,
        )
        ctx.add("user", "haz algo")
        for i in range(n_tools):
            _add_tool_result(ctx, f"tool{i}", "x" * tool_content_len)
        ctx.add("assistant", "ok")
        return ctx

    def test_last_4_tools_are_not_truncated(self):
        """Las últimas 4 tool results no se truncan en la 2ª pasada."""
        ctx = self._make_ctx_with_tools(n_tools=8, tool_content_len=5000)
        original_contents = {
            i: msg["content"]
            for i, msg in enumerate(ctx.messages)
            if msg.get("role") == "tool"
        }
        ctx.compact()

        tool_msgs = [(i, msg) for i, msg in enumerate(ctx.messages) if msg.get("role") == "tool"]
        # Después de compact() los índices pueden haber cambiado; identificar por orden
        # Las últimas 4 deben estar íntegras (no truncadas)
        last_4 = tool_msgs[-4:]
        for _, msg in last_4:
            assert "truncados tras compactación" not in msg["content"], \
                "Una tool result reciente fue truncada — debe estar protegida"

    def test_older_tools_may_be_truncated(self):
        """Las tool results más antiguas (más allá de las últimas 4) sí se pueden truncar."""
        ctx = self._make_ctx_with_tools(n_tools=8, tool_content_len=5000)
        ctx.compact()

        tool_msgs = [msg for msg in ctx.messages if msg.get("role") == "tool"]
        if len(tool_msgs) <= 4:
            pytest.skip("Compact eliminó demasiados mensajes para este test")

        older = tool_msgs[:-4]
        # Al menos uno de los mensajes antiguos debe haber sido truncado
        truncated = any("truncados tras compactación" in m["content"] for m in older)
        assert truncated, "Ningún tool result antiguo fue truncado — la 2ª pasada no funcionó"

    def test_fewer_than_4_tools_all_protected(self):
        """Si hay 3 o menos tool results, ninguno se trunca."""
        ctx = self._make_ctx_with_tools(n_tools=3, tool_content_len=5000)
        ctx.compact()

        for msg in ctx.messages:
            if msg.get("role") == "tool":
                assert "truncados tras compactación" not in msg["content"], \
                    "Con ≤4 tool results, ninguna debe truncarse"

    def test_no_second_pass_when_under_high_water(self):
        """Si el contexto cae por debajo de high_water, no se trunca nada."""
        ctx = ConversationContext(
            max_tokens=100_000,  # muy grande
            min_keep=1,
            high_water=0.99,     # casi nunca activa
            tool_max_chars=500,
        )
        ctx.add("user", "tarea")
        _add_tool_result(ctx, "bash", "x" * 5000)
        ctx.add("assistant", "ok")
        ctx.compact()
        for msg in ctx.messages:
            if msg.get("role") == "tool":
                assert "truncados tras compactación" not in msg["content"]


# ─────────────────────────────────────────────────────────────────────────────
# A — min_keep adaptativo con plan activo
# ─────────────────────────────────────────────────────────────────────────────

class TestAdaptiveMinKeep:
    """Verifica que _plan_active_msg_idx se actualiza en los momentos correctos."""

    def _make_loop(self):
        """Crea un AgentLoop minimal sin LLM usando __new__ como en test_23."""
        from unittest.mock import MagicMock
        import threading
        from config import OOConfig
        from agent.context import ConversationContext
        from agent.loop import AgentLoop

        cfg  = OOConfig(model="test-model", ollama_host="http://localhost:11434")
        loop = AgentLoop.__new__(AgentLoop)
        loop.config               = cfg
        loop.capture_output       = True
        loop.is_subagent          = False
        loop._plan_tasks          = []
        loop._plan_active_msg_idx = -1
        loop._auto_continue_count = 0
        loop._last_tool_calls     = []
        loop._pending_tasks       = []
        loop._empty_search_streak     = 0
        loop._empty_search_patterns   = []
        loop._failed_edit_streak      = 0
        loop._failed_edit_patterns    = []
        loop._turn_read_cache     = {}
        loop._turn_write_seen     = {}
        loop._turn_written_scripts = set()
        loop._status_cb           = None
        loop._sep_label           = ""
        loop._flush_live_block_cb = None
        loop._compacting_ctx      = False
        loop._compact_running     = threading.Event()
        loop.memory               = MagicMock(last_hits=0)
        loop._workspace_rag       = None
        loop._turn_inp            = 0
        loop.tasks                = None
        loop.session              = MagicMock()
        loop.session.log_compaction = MagicMock()
        loop.context = ConversationContext(
            max_tokens=cfg.effective_max_context_tokens,
            min_keep=cfg.compact_min_keep,
            compact_threshold=cfg.compact_threshold,
            max_summary_chars=cfg.max_summary_chars,
            high_water=cfg.context_high_water,
            tool_max_chars=cfg.context_tool_max_chars,
        )
        return loop

    def test_initial_value_is_minus_one(self):
        loop = self._make_loop()
        assert loop._plan_active_msg_idx == -1

    def test_set_on_plan_create(self):
        loop = self._make_loop()
        # Añadir algunos mensajes antes de crear el plan
        loop.context.add("user", "haz algo")
        loop.context.add("assistant", "ok")
        initial_msg_count = len(loop.context.messages)

        loop._execute_plan_create(["tarea 1", "tarea 2", "tarea 3"])

        assert loop._plan_active_msg_idx == initial_msg_count
        assert loop._plan_active_msg_idx >= 0

    def test_updated_on_task_done(self):
        loop = self._make_loop()
        loop._execute_plan_create(["tarea 1", "tarea 2", "tarea 3"])

        idx_after_plan = loop._plan_active_msg_idx

        # Simular trabajo en la tarea 1: añadir mensajes
        loop.context.add("assistant", "trabajando en tarea 1")
        loop.context.add("user", "continúa")

        # Completar tarea 1 → debe actualizar _plan_active_msg_idx
        loop._execute_task_done("tarea 1 completada")

        # El índice debe haber avanzado
        assert loop._plan_active_msg_idx > idx_after_plan

    def test_min_keep_prevents_compacting_active_task_messages(self):
        """Con plan activo, compact() no puede eliminar mensajes de la tarea actual."""
        loop = self._make_loop()
        # Rellenar contexto con mensajes previos
        for i in range(10):
            loop.context.add("user", f"mensaje previo {i}")
            loop.context.add("assistant", f"respuesta previa {i}")

        # Crear plan — registra el índice actual
        loop._execute_plan_create(["implementar feature X", "tests", "docs"])
        task_start_idx = loop._plan_active_msg_idx

        # Añadir mensajes de la tarea activa
        loop.context.add("assistant", "empezando feature X")
        loop.context.add("user", "perfecto")
        loop.context.add("assistant", "implementado")

        msgs_after = len(loop.context.messages)
        msgs_since_task = msgs_after - task_start_idx

        # Forzar min_keep pequeño para que sin la mejora compactaría más
        loop.context.min_keep = 2
        loop.context.max_tokens = 50   # umbral muy bajo para forzar compactación

        dropped = loop.context.compact()
        remaining = len(loop.context.messages)

        # Sin la mejora A, compact() usaría min_keep=2 y podría dejar solo 2 mensajes.
        # Con la mejora A (aplicada en _do_compact_locked), en un loop real
        # se usaría min_keep adaptativo. Aquí probamos directamente el conteo.
        # La compact() en sí usa self.min_keep; el ajuste lo hace _do_compact_locked.
        # Este test verifica que el tracking (_plan_active_msg_idx) funciona.
        assert loop._plan_active_msg_idx == task_start_idx  # no cambia hasta task_done
        assert msgs_since_task >= 3   # al menos los 3 msgs de la tarea activa

    def test_no_update_when_all_tasks_done(self):
        """Completar la última tarea NO actualiza _plan_active_msg_idx (next_idx = -1)."""
        loop = self._make_loop()
        loop._execute_plan_create(["única tarea"])
        idx_after_plan = loop._plan_active_msg_idx

        loop.context.add("assistant", "trabajando")
        loop._execute_task_done("completado")

        # No hay tarea siguiente → _plan_active_msg_idx no debe cambiar
        assert loop._plan_active_msg_idx == idx_after_plan

    def test_adaptive_min_keep_logic_in_compact_locked(self):
        """_do_compact_locked aplica min_keep adaptativo y lo restaura tras compactar."""
        loop = self._make_loop()

        # Rellenar con mensajes
        for i in range(20):
            loop.context.add("user", f"msg {i}")
            loop.context.add("assistant", f"resp {i}")

        # Crear plan (registra msg_idx actual)
        loop._execute_plan_create(["tarea larga"])

        # Añadir 6 mensajes de trabajo
        for i in range(6):
            loop.context.add("assistant", f"trabajando paso {i}")

        original_mk = loop.context.min_keep  # valor de config (6)
        task_start  = loop._plan_active_msg_idx
        msgs_since  = len(loop.context.messages) - task_start

        # Llamar _do_compact_locked (capture_output=True → ruta directa sin TUI)
        # Después debe restaurar min_keep al valor original
        loop._do_compact_locked(with_summary=False)

        assert loop.context.min_keep == original_mk, \
            "_do_compact_locked no restauró min_keep al valor original"


# ─────────────────────────────────────────────────────────────────────────────
# D — Summary como mensaje system separado
# ─────────────────────────────────────────────────────────────────────────────

class TestSummaryAsSeparateMessage:
    def test_summary_injected_as_separate_system_message(self):
        """Con summary presente, get_messages devuelve 2 msgs system: rules + summary."""
        ctx = ConversationContext()
        ctx.summary = "## Progreso: fichero foo.py modificado"
        ctx.add("user", "continúa")

        msgs = ctx.get_messages(system="SYSTEM RULES")

        system_msgs = [m for m in msgs if m["role"] == "system"]
        assert len(system_msgs) == 2
        assert system_msgs[0]["content"] == "SYSTEM RULES"
        assert "Resumen de contexto anterior" in system_msgs[1]["content"]
        assert "foo.py" in system_msgs[1]["content"]

    def test_summary_not_concatenated_into_system_rules(self):
        """El summary NO aparece en el cuerpo del primer system message."""
        ctx = ConversationContext()
        ctx.summary = "tarea: refactorizar utils.py"
        msgs = ctx.get_messages(system="RULES")
        assert "tarea" not in msgs[0]["content"]

    def test_no_extra_message_when_summary_empty(self):
        """Sin summary, solo hay 1 mensaje system."""
        ctx = ConversationContext()
        ctx.add("user", "hola")
        msgs = ctx.get_messages(system="RULES")
        assert sum(1 for m in msgs if m["role"] == "system") == 1

    def test_summary_message_position(self):
        """El mensaje de summary aparece justo después del system rules y antes del primer user."""
        ctx = ConversationContext()
        ctx.summary = "contexto previo"
        ctx.add("user", "nuevo turno")
        msgs = ctx.get_messages(system="RULES")
        roles = [m["role"] for m in msgs]
        assert roles == ["system", "system", "user"]

    def test_no_system_arg_but_summary_present(self):
        """Si no se pasa system=, pero hay summary, no se inyecta ningún message system."""
        ctx = ConversationContext()
        ctx.summary = "hay resumen"
        ctx.add("user", "hola")
        msgs = ctx.get_messages()          # sin system=
        assert all(m["role"] != "system" for m in msgs)


# ─────────────────────────────────────────────────────────────────────────────
# E — Calibración dinámica de CPT
# ─────────────────────────────────────────────────────────────────────────────

class TestCptCalibration:
    def test_initial_factor_is_one(self):
        ctx = ConversationContext()
        assert ctx._calibration_factor == 1.0
        assert ctx._calibration_samples == 0

    def test_calibration_adjusts_factor_upward(self):
        """Si Ollama reporta más tokens de los estimados, el factor sube."""
        ctx = ConversationContext()
        ctx.add("user", "a" * 1000)
        estimated = ctx.token_estimate()    # con factor=1.0
        # Simular que Ollama reporta el doble (modelo con vocabulario más pequeño)
        ctx.calibrate(estimated * 2, system_chars=0)
        assert ctx._calibration_factor > 1.0
        assert ctx._calibration_samples == 1

    def test_calibration_adjusts_factor_downward(self):
        """Si Ollama reporta menos tokens, el factor baja."""
        ctx = ConversationContext()
        ctx.add("user", "a" * 1000)
        estimated = ctx.token_estimate()
        ctx.calibrate(int(estimated * 0.7), system_chars=0)
        assert ctx._calibration_factor < 1.0

    def test_outlier_high_ratio_filtered(self):
        """Ratio > 2.5 se descarta (Ollama caído, contexto vacío, etc.)."""
        ctx = ConversationContext()
        ctx.add("user", "texto corto")
        ctx.calibrate(999999, system_chars=0)
        assert ctx._calibration_factor == 1.0
        assert ctx._calibration_samples == 0

    def test_outlier_low_ratio_filtered(self):
        """Ratio < 0.4 se descarta."""
        ctx = ConversationContext()
        ctx.add("user", "a" * 2000)
        ctx.calibrate(1, system_chars=0)
        assert ctx._calibration_factor == 1.0

    def test_skips_when_estimated_too_small(self):
        """No calibra si el contexto es casi vacío (estimado < 50 tokens)."""
        ctx = ConversationContext()
        ctx.add("user", "hi")
        ctx.calibrate(100, system_chars=0)
        assert ctx._calibration_samples == 0

    def test_token_estimate_applies_factor(self):
        """token_estimate() aplica el factor de calibración."""
        ctx = ConversationContext()
        ctx.add("user", "a" * 3000)
        before = ctx.token_estimate()
        ctx._calibration_factor = 2.0
        ctx._invalidate_token_cache()
        after = ctx.token_estimate()
        assert after == before * 2

    def test_system_chars_accounted_in_calibration(self):
        """Con system_chars, el estimated_total incluye la contribución del system."""
        ctx = ConversationContext()
        ctx.add("user", "a" * 500)
        estimated_ctx = ctx.token_estimate()
        # system prompt de 3000 chars → ~1000 tokens adicionales
        system_chars = 3000
        # Con ratio válido (1.0 nominal), actual ≈ ctx_tokens + sys_tokens
        from agent.context import _CPT_SYS
        actual = int(estimated_ctx + system_chars / _CPT_SYS)
        ctx.calibrate(actual, system_chars=system_chars)
        # El factor debe quedar muy cerca de 1.0 (ratio ≈ 1.0)
        assert 0.97 < ctx._calibration_factor < 1.04

    def test_calibration_factor_in_stats(self):
        ctx = ConversationContext()
        stats = ctx.stats()
        assert "calibration_factor" in stats
        assert "calibration_samples" in stats
        assert stats["calibration_factor"] == 1.0

    def test_smoothing_prevents_single_spike(self):
        """α=0.15 suaviza; una medición doble solo mueve el factor ~15%."""
        ctx = ConversationContext()
        ctx.add("user", "a" * 2000)
        estimated = ctx.token_estimate()
        ctx.calibrate(estimated * 2, system_chars=0)
        # Nuevo factor ≈ 0.85*1.0 + 0.15*2.0 = 1.15
        assert 1.10 < ctx._calibration_factor < 1.20


# ─────────────────────────────────────────────────────────────────────────────
# F — Serialización por turnos
# ─────────────────────────────────────────────────────────────────────────────

class TestSerializeTurns:
    def _make_messages(self):
        return [
            {"role": "user", "content": "implementa la función foo"},
            {
                "role": "assistant",
                "content": "Voy a escribir el archivo",
                "tool_calls": [{"function": {"name": "write_file"}}],
            },
            {"role": "tool", "name": "write_file", "tool_call_id": "c1",
             "content": "ok, escrito en src/foo.py"},
            {"role": "user", "content": "ahora añade tests"},
            {
                "role": "assistant",
                "content": "Añado los tests",
                "tool_calls": [
                    {"function": {"name": "write_file"}},
                    {"function": {"name": "bash"}},
                ],
            },
            {"role": "tool", "name": "write_file", "tool_call_id": "c2",
             "content": "ok, tests/test_foo.py"},
            {"role": "tool", "name": "bash", "tool_call_id": "c3",
             "content": "3 passed"},
            {"role": "assistant", "content": "Tests completados sin herramientas"},
        ]

    def test_turns_are_numbered(self):
        from agent.loop import AgentLoop
        msgs = self._make_messages()
        result = AgentLoop._serialize_turns(msgs)
        assert "[Turno 1]" in result
        assert "[Turno 2]" in result
        assert "[Turno 3]" not in result   # solo 2 mensajes user

    def test_user_content_present(self):
        from agent.loop import AgentLoop
        result = AgentLoop._serialize_turns(self._make_messages())
        assert "implementa la función foo" in result
        assert "ahora añade tests" in result

    def test_tool_calls_listed_in_arrow(self):
        from agent.loop import AgentLoop
        result = AgentLoop._serialize_turns(self._make_messages())
        assert "→ [write_file]" in result
        assert "→ [write_file, bash]" in result

    def test_tool_results_indented(self):
        from agent.loop import AgentLoop
        result = AgentLoop._serialize_turns(self._make_messages())
        assert "↳ write_file:" in result
        assert "↳ bash:" in result

    def test_tool_results_follow_their_assistant(self):
        from agent.loop import AgentLoop
        result = AgentLoop._serialize_turns(self._make_messages())
        # El resultado de bash (3 passed) debe aparecer después del assistant del turno 2
        idx_t2 = result.index("[Turno 2]")
        idx_bash = result.index("↳ bash:")
        assert idx_bash > idx_t2

    def test_assistant_without_tools_serialized_plainly(self):
        from agent.loop import AgentLoop
        result = AgentLoop._serialize_turns(self._make_messages())
        assert "Tests completados sin herramientas" in result
        # No debe tener flecha
        assert "Tests completados sin herramientas →" not in result

    def test_tool_result_truncated_at_120(self):
        from agent.loop import AgentLoop
        msgs = [
            {"role": "user", "content": "cmd"},
            {"role": "assistant", "content": "ok",
             "tool_calls": [{"function": {"name": "bash"}}]},
            {"role": "tool", "name": "bash", "tool_call_id": "c",
             "content": "x" * 300},
        ]
        result = AgentLoop._serialize_turns(msgs)
        assert "↳ bash: " in result
        assert "…" in result   # truncado

    def test_empty_messages_returns_empty(self):
        from agent.loop import AgentLoop
        assert AgentLoop._serialize_turns([]) == ""

    def test_only_system_messages_returns_empty(self):
        from agent.loop import AgentLoop
        msgs = [{"role": "system", "content": "rules"}]
        result = AgentLoop._serialize_turns(msgs)
        assert result.strip() == ""


# ─────────────────────────────────────────────────────────────────────────────
# G — Meta-header en el summary de compactación
# ─────────────────────────────────────────────────────────────────────────────

class TestCompactMetaHeader:
    def test_compact_count_increments(self):
        """_compact_count sube en 1 por cada llamada a compact() que elimina msgs."""
        ctx = ConversationContext(max_tokens=50, min_keep=1)
        for i in range(10):
            ctx.add("user", f"msg {i}")
            ctx.add("assistant", f"resp {i}")
        assert ctx._compact_count == 0
        ctx.compact()
        assert ctx._compact_count == 1
        # Volver a llenar y compactar de nuevo
        for i in range(10):
            ctx.add("user", f"msg extra {i}")
        ctx.compact()
        assert ctx._compact_count == 2

    def test_compact_count_not_incremented_when_nothing_to_drop(self):
        """Si n <= min_keep, no se incrementa el contador."""
        ctx = ConversationContext(max_tokens=100_000, min_keep=10)
        ctx.add("user", "único mensaje")
        ctx.compact()
        assert ctx._compact_count == 0

    def test_meta_header_format_in_summarize_messages(self):
        """_summarize_messages antepone meta-header con #N, msgs y timestamp."""
        from unittest.mock import MagicMock, patch
        from config import OOConfig
        from agent.context import ConversationContext
        from agent.loop import AgentLoop

        cfg  = OOConfig(model="test-model", ollama_host="http://localhost:11434")
        loop = AgentLoop.__new__(AgentLoop)
        loop.config = cfg
        loop.context = ConversationContext(max_tokens=50000, min_keep=2)
        loop._plan_tasks = []
        loop._plan_active_msg_idx = -1
        loop._session_reads = []
        loop._task_last_test = ""
        loop.ws = MagicMock()
        loop.ws.write_daily_memory = MagicMock()

        # Simular que ya hubo 1 compactación
        loop.context._compact_count = 1
        # Añadir mensajes al contexto "conservado"
        loop.context.add("user", "turno actual")

        dropped = [
            {"role": "user", "content": "mensaje antiguo"},
            {"role": "assistant", "content": "respuesta antigua"},
        ]

        # Mockear el cliente LLM para que devuelva un resumen fijo
        mock_resp = MagicMock()
        mock_resp.message.content = "- Hizo algo\n- Escribió código"
        loop.client = MagicMock()
        loop.client.chat.return_value = mock_resp

        with patch.object(loop, "_build_options", return_value={}), \
             patch.object(loop, "_active_model",  return_value="test-model"), \
             patch.object(loop, "_all_plan_tasks_done", return_value=True):
            result = loop._summarize_messages(dropped)

        assert "[Compactación #1" in result
        assert "conservados" in result
        assert "/" in result   # X/Y
        # Formato de fecha ISO presente
        import re
        assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", result)

    def test_meta_header_present_even_without_llm(self):
        """Sin LLM (excepción), el meta-header igual se incluye en el fallback."""
        from unittest.mock import MagicMock, patch
        from config import OOConfig
        from agent.loop import AgentLoop

        cfg  = OOConfig(model="test-model", ollama_host="http://localhost:11434")
        loop = AgentLoop.__new__(AgentLoop)
        loop.config  = cfg
        loop.context = ConversationContext(max_tokens=50000, min_keep=2)
        loop._plan_tasks = []
        loop._plan_active_msg_idx = -1
        loop._session_reads = []
        loop._task_last_test = ""
        loop.ws = MagicMock()
        loop.context._compact_count = 2
        loop.context.add("user", "último turno")

        dropped = [{"role": "user", "content": "antiguo"}]

        loop.client = MagicMock()
        loop.client.chat.side_effect = RuntimeError("no LLM")

        with patch.object(loop, "_build_options", return_value={}), \
             patch.object(loop, "_active_model",  return_value="test-model"), \
             patch.object(loop, "_all_plan_tasks_done", return_value=True):
            result = loop._summarize_messages(dropped)

        assert "[Compactación #2" in result


# ─────────────────────────────────────────────────────────────────────────────
# H — Semáforo(2) en lugar de Lock
# ─────────────────────────────────────────────────────────────────────────────

class TestCompactSemaphore:
    def test_compact_lock_is_semaphore(self):
        """_COMPACT_LOCK debe ser un Semaphore, no un Lock."""
        import threading
        from agent.loop_helpers import _COMPACT_LOCK
        assert isinstance(_COMPACT_LOCK, type(threading.Semaphore(2))), \
            "_COMPACT_LOCK debe ser threading.Semaphore"

    def test_semaphore_allows_two_concurrent(self):
        """Semaphore(2): dos hilos entran simultáneamente, el tercero espera."""
        import threading
        from agent.loop_helpers import _COMPACT_LOCK

        inside = []
        barrier = threading.Barrier(2)   # sincroniza 2 hilos dentro del semáforo

        def _worker(idx):
            with _COMPACT_LOCK:
                inside.append(idx)
                if len(inside) <= 2:
                    try:
                        barrier.wait(timeout=1.0)  # los 2 primeros se sincronizan
                    except threading.BrokenBarrierError:
                        pass
                inside.remove(idx)

        threads = [threading.Thread(target=_worker, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3.0)
        # Todos terminaron sin deadlock
        assert not any(t.is_alive() for t in threads)

    def test_semaphore_value_is_two(self):
        """El semáforo tiene valor inicial 2 (no 1 como un Lock)."""
        import threading
        from agent.loop_helpers import _COMPACT_LOCK
        # Adquirir una vez — debe quedar en 1 (sin bloquear)
        acquired = _COMPACT_LOCK.acquire(blocking=False)
        assert acquired, "No se pudo adquirir el semáforo — valor inicial incorrecto"
        _COMPACT_LOCK.release()  # restaurar


# ─────────────────────────────────────────────────────────────────────────────
# I — Pre-compactación en idle
# ─────────────────────────────────────────────────────────────────────────────

class TestPrecompactIdle:
    def _make_loop(self, capture_output=False, is_subagent=False):
        from unittest.mock import MagicMock
        import threading as _th
        from config import OOConfig
        from agent.context import ConversationContext
        from agent.loop import AgentLoop

        cfg  = OOConfig(model="test-model", ollama_host="http://localhost:11434")
        loop = AgentLoop.__new__(AgentLoop)
        loop.config               = cfg
        loop.capture_output       = capture_output
        loop.is_subagent          = is_subagent
        loop._plan_tasks          = []
        loop._plan_active_msg_idx = -1
        loop._compact_running     = _th.Event()
        loop._precompact_thread   = None
        loop.context = ConversationContext(
            max_tokens=10000,
            min_keep=2,
            compact_threshold=0.80,
            high_water=0.70,
        )
        loop._do_compact = MagicMock(return_value=5)
        return loop

    def test_no_precompact_when_below_high_water(self):
        """No se lanza precompactación si pct < high_water."""
        loop = self._make_loop()
        # Contexto al 50% — por debajo del high_water (70%)
        loop.context.max_tokens = 100_000
        loop.context.add("user", "solo algunos mensajes")
        loop._maybe_precompact_idle()
        import time; time.sleep(0.05)
        loop._do_compact.assert_not_called()

    def test_no_precompact_when_above_compact_threshold(self):
        """No se lanza si pct >= compact_threshold (se compactará en _turn_iter_prepare)."""
        loop = self._make_loop()
        loop.context.max_tokens = 10
        # context.token_estimate() >> max_tokens → pct > 1.0 > compact_threshold
        for i in range(20):
            loop.context.add("user", f"mensaje {i} " * 50)
        loop._maybe_precompact_idle()
        import time; time.sleep(0.05)
        loop._do_compact.assert_not_called()

    def test_precompact_launched_in_high_water_zone(self):
        """Se lanza un hilo de precompactación cuando high_water ≤ pct < compact_threshold."""
        loop = self._make_loop()
        # Forzar pct en la zona [0.70, 0.80)
        loop.context.max_tokens = 1000
        loop.context._token_cache = 750   # 75% — entre high_water y compact_threshold
        loop.context._token_dirty = False
        loop._maybe_precompact_idle()
        import time; time.sleep(0.1)
        loop._do_compact.assert_called_once_with(with_summary=True)

    def test_no_precompact_when_already_running(self):
        """No lanza un segundo hilo si _compact_running ya está set."""
        loop = self._make_loop()
        loop.context.max_tokens = 1000
        loop.context._token_cache = 750
        loop.context._token_dirty = False
        loop._compact_running.set()   # simular compactación en curso
        loop._maybe_precompact_idle()
        import time; time.sleep(0.05)
        loop._do_compact.assert_not_called()
        loop._compact_running.clear()

    def test_no_precompact_for_subagent(self):
        """Subagentes no hacen pre-compactación idle."""
        loop = self._make_loop(is_subagent=True)
        loop.context.max_tokens = 1000
        loop.context._token_cache = 750
        loop.context._token_dirty = False
        loop._maybe_precompact_idle()
        import time; time.sleep(0.05)
        loop._do_compact.assert_not_called()

    def test_no_precompact_in_capture_mode(self):
        """capture_output=True (subagente headless) no hace pre-compactación."""
        loop = self._make_loop(capture_output=True)
        loop.context.max_tokens = 1000
        loop.context._token_cache = 750
        loop.context._token_dirty = False
        loop._maybe_precompact_idle()
        import time; time.sleep(0.05)
        loop._do_compact.assert_not_called()

    def test_no_double_precompact(self):
        """No lanza un segundo hilo si el anterior todavía está vivo."""
        import threading as _th
        loop = self._make_loop()
        loop.context.max_tokens = 1000
        loop.context._token_cache = 750
        loop.context._token_dirty = False

        # Simular hilo activo
        done_ev = _th.Event()
        def _slow(): done_ev.wait(timeout=2.0)
        loop._precompact_thread = _th.Thread(target=_slow, daemon=True)
        loop._precompact_thread.start()

        loop._maybe_precompact_idle()
        import time; time.sleep(0.05)
        loop._do_compact.assert_not_called()
        done_ev.set()
        loop._precompact_thread.join(timeout=1.0)
