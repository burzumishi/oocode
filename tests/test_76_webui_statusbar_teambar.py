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


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
