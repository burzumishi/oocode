"""Tests WebUI: status bar única (paridad TUI) + team-bar con detalle por subagente.

- Status bar: una sola barra (al fondo), sin la duplicada superior bb-* (agente/
  modelo/ctx aparecían arriba Y abajo). updateStatus ya no toca elementos bb-*.
- Team-bar: muestra tarea/elapsed/estado/ctx% por subagente (no solo nombre), y
  auto-descubre subagentes de team/fanout desde sus eventos tagged 'subagent'.

Sin LLM ni red — inspección del HTML/JS renderizado.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _chat_src():
    from webui.app import app as _app
    _app.config["TESTING"] = True
    _app.config["SECRET_KEY"] = "test-secret"
    with _app.test_client() as c:
        return c.get("/chat").data.decode("utf-8", errors="replace")


# ── Status bar única (sin duplicación top/bottom) ─────────────────────────────

def test_single_statusbar_no_bottom_duplicate():
    h = _chat_src()
    # Una sola barra de estado con los ids canónicos sb-*
    assert h.count('id="tui-statusbar"') == 1
    assert h.count('id="sb-agent"') == 1
    assert h.count('id="sb-ctx"') == 1
    # La barra inferior duplicada bb-* desaparece
    assert 'id="bb-agent"' not in h
    assert 'id="bb-model"' not in h
    assert 'id="bb-ctx"' not in h


def test_updatestatus_no_bb_refs():
    h = _chat_src()
    # updateStatus ya no actualiza elementos bb-* (estaban duplicados)
    assert "getElementById('bb-agent')" not in h
    assert "getElementById('bb-model')" not in h
    assert "getElementById('bb-ctx')" not in h


# ── Status bar bajo el prompt, sobre MCP/LSP (paridad TUI) ───────────────────

def test_statusbar_above_mcp_lsp_rows():
    """La barra agente/modelo/ctx va justo bajo el prompt y la team-bar, sobre MCP/LSP."""
    h = _chat_src()
    i_team = h.index('id="tui-team-bar"')
    i_sb   = h.index('id="tui-statusbar"')
    i_mcp  = h.index('id="tui-sb2-mcp"')
    i_lsp  = h.index('id="tui-sb2-lsp"')
    # Orden DOM (= visual, flex column): team-bar → status bar → MCP → LSP
    assert i_team < i_sb < i_mcp < i_lsp


# ── Team-bar: SOLO cabecera (el detalle vive en la conversación) ─────────────

def test_teambar_header_only_no_detail_lines():
    h = _chat_src()
    assert "_ensureSubagentEntry" in h
    assert "renderTeamBar" in h
    # Cabecera compacta: «Main 💬 Sub · N subagente(s)»
    assert "subagente(s)" in h
    assert "team-chat" in h
    assert "team-sub" in h
    # El detalle largo (tarea/elapsed/ctx%) YA NO se renderiza en la barra de status
    assert "team-line" not in h
    assert "team-task" not in h
    assert "team-meta" not in h
    assert "_fmtElapsed" not in h
    assert "% ctx" not in h


def test_subagent_task_seeded_in_conversation():
    """La tarea del subagente se siembra en su bloque de conversación, no en el status."""
    h = _chat_src()
    assert "_seedSubagentTask" in h
    assert "tui-subagent-task" in h
    # Se llama desde el handler subagent_start
    assert "_seedSubagentTask(ev.agent_emoji" in h
    # Se inserta en el cuerpo del bloque del subagente (conversación)
    assert "entry.div.insertBefore" in h


def test_teambar_autodiscovers_subagents():
    h = _chat_src()
    # Eventos tagged 'subagent' alimentan la team-bar (team/fanout sin subagent_start)
    assert "ev.subagent && ev.subagent_name" in h
    # status de subagente captura ctx%, NO toca la barra principal
    assert "if (!ev.subagent) updateStatus(ev)" in h


def test_subagent_start_carries_task():
    """El evento subagent_start propaga la tarea (para sembrarla en la conversación)."""
    from agent import loop  # noqa: F401
    import inspect
    src = inspect.getsource(loop)
    assert '"task": _stask' in src


# ── Corrección 3: spawn_subagent no crea bloque de tool huérfano en WebUI ────

def test_spawn_subagent_no_main_toolstart_in_webui():
    """spawn_subagent NO emite tool_start de agente principal (sería un bloque colgado)."""
    from agent import loop
    import inspect
    src = inspect.getsource(loop)
    # El emit de tool_start excluye spawn_subagent
    assert 'name != "spawn_subagent"' in src
    # El path paralelo también lo excluye
    assert '_pn not in ("spawn_subagent", "plan_create")' in src


# ── Corrección 4: la barra "Pensando" (status) no muestra títulos de tools ───

def test_thinking_bar_not_hijacked_by_tool_title():
    h = _chat_src()
    # En tool_start NO se sobreescribe el label del spinner con el nombre del tool;
    # el tool va solo al bloque de la conversación (appendToolStart).
    assert "_setThinkingLabel('◐ '" not in h
    assert "appendToolStart(ev.tool" in h


# ── Indicadores think/mem/rag junto a MCP/LSP (paridad toolbar TUI línea 1) ──

def test_capability_badges_present():
    """think/mem:N/rag:Nf/Mc del toolbar TUI tienen equivalente en el WebUI (badges)."""
    h = _chat_src()
    for bid in ('id="sb-think"', 'id="sb-memcap"', 'id="sb-ragcap"'):
        assert bid in h, bid
    # Se rellenan desde el evento /api/chat/status con el mismo formato del TUI
    assert "'think:' + lvl" in h
    assert "'⬢ mem:' + n" in h
    assert "'✦ rag:' + f + 'f/' + c + 'c'" in h


def test_status_endpoint_emits_capability_fields():
    """/api/chat/status devuelve think_level/reasoning/mem_count/rag_files/rag_chunks."""
    from webui import api_chat
    import inspect
    src = inspect.getsource(api_chat)
    for key in ('"think_level":', '"reasoning":', '"mem_count":',
                '"rag_files":', '"rag_chunks":'):
        assert key in src, key


def test_webui_status_event_carries_think_for_vim():
    """El status SSE (_webui_status) lleva think_level/reasoning (Vim header + WebUI badge)."""
    from webui import loop_webui
    import inspect
    src = inspect.getsource(loop_webui.WebUIMixin._webui_status)
    assert '"think_level":' in src
    assert '"reasoning":' in src
    # whitelist defensiva (evita valores raros en el header)
    assert '"minimal", "low", "medium", "high"' in src


# ── Auto-split de bloques de tools por fichero (paridad TUI) ──────────────────

def test_tool_start_emits_modify_and_target():
    """El tool_start del WebUI propaga is_modify/write_target para el auto-split."""
    from agent import loop
    import inspect
    src = inspect.getsource(loop)
    assert '"is_modify": _wt_modify' in src
    assert '"write_target": _wt_base' in src


def test_webui_reasoning_nests_or_flushes_by_step():
    """appendReasoning del WebUI: con newStep=false (default) mete el 💭 DENTRO del
    bloque abierto (│ 💭); sin bloque va al nivel superior. Paridad con el TUI: razonar
    NO cierra el bloque (el split por fichero lo dirige tool_start is_modify/write_target)."""
    h = _chat_src()
    assert "function appendReasoning(text, newStep)" in h
    assert "appendReasoning(ev.text || '', !!ev.new_step)" in h
    # rama "dentro del bloque" gateada por !newStep
    assert "if (!newStep && _toolBlockInner" in h
    assert "tui-tool-reasoning" in h
    # el servidor emite new_step en el evento reasoning
    from agent import loop
    import inspect
    src = inspect.getsource(loop)
    assert '"new_step": bool(getattr(self, "_reasoning_new_step"' in src


def test_reasoning_does_not_drive_block_flush():
    """REGRESIÓN (2026-06-11 noche): run() NO decide flush del bloque al RAZONAR
    (ni incondicional ni por cambio de fichero) — eso troceaba los bloques del TUI y
    suprimía ●. El flag new_step del WebUI (2026-06-12) se fija con la frontera del
    TEXTO nuevo no-duplicado (`_new_step`, misma condición que el flush del ●), nunca
    con una decisión por fichero en el momento de razonar. El split por fichero lo
    sigue haciendo el auto-split de las write tools."""
    from agent import loop
    import inspect
    src = inspect.getsource(loop.AgentLoop.run)
    assert "self._reasoning_new_step = _file_changed" not in src
    assert "_continue_same_file" not in src
    assert "self._reasoning_new_step = _new_step" in src


def test_webui_tool_block_splits_per_file():
    """appendToolStart cierra el bloque al cambiar de fichero (no acumula +50 tools)."""
    h = _chat_src()
    # Recibe los flags y los usa para el split
    assert "function appendToolStart(tool, ctx, isModify, writeTarget)" in h
    assert "appendToolStart(ev.tool, ev.context || '', !!ev.is_modify, ev.write_target || '')" in h
    # La condición de split: write a fichero DISTINTO con bloque con contenido
    assert "writeTarget !== _blockWriteTarget" in h
    assert "_finishToolBlock();" in h
    # El estado del fichero del bloque se resetea al crear/cerrar bloque
    assert h.count("_blockWriteTarget = '';") >= 2


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
