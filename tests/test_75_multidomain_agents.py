"""Tests: personalización por dominio (/agent new) + flujo multi-agente (gaps C-F).

#4 — _classify_agent_domain + _write_domain_soul: agentes no-código no heredan
     la plantilla code-céntrica.
C  — frases preflight neutras (sin "código") + dominios web/data/office.
D  — SYSTEM_RULES exige pre-anuncio de equipo y síntesis tras run_team.
E  — _TOOL_LIVE_VERBS cubre tools MCP (email/doc/iot/db/web).

Sin LLM ni red.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── #4 — clasificación de dominio + SOUL fallback ─────────────────────────────

def test_classify_domains():
    from ui.commands import _classify_agent_domain
    assert _classify_agent_domain("asistente de oficina, informes Word y Excel") == "office"
    assert _classify_agent_domain("pentesting, CTF y análisis de vulnerabilidades") == "security"
    assert _classify_agent_domain("webcrawler de noticias y research") == "web"
    assert _classify_agent_domain("control de luces TAPO y sensores MQTT") == "iot"
    assert _classify_agent_domain("análisis de datos SQL y métricas") == "data"
    assert _classify_agent_domain("asistente de programación backend Python") == "code"
    assert _classify_agent_domain("ayudante") == "general"


def test_write_domain_soul_office_no_code(tmp_path):
    from ui.commands import _write_domain_soul
    ok = _write_domain_soul(str(tmp_path), "Oficina", "🏠",
                            "informes corporativos", "office")
    assert ok is True
    soul = (tmp_path / "SOUL.md").read_text()
    # Persona de dominio, no de programación
    assert "ofimática" in soul
    assert "run_tests" not in soul
    assert "lint" not in soul.lower()
    # Conserva el principio agnóstico clave
    assert "El usuario NO ve las tools" in soul


def test_write_domain_soul_skips_code_domain(tmp_path):
    """Para dominio 'code' no se escribe fallback (usa la plantilla de programación)."""
    from ui.commands import _write_domain_soul
    assert _write_domain_soul(str(tmp_path), "Dev", "🤖", "código", "code") is False
    assert not (tmp_path / "SOUL.md").exists()


def test_domain_profiles_cover_all_keys():
    from ui.commands import _AGENT_DOMAIN_PROFILES
    for key in ("code", "office", "security", "iot", "web", "data", "devops", "general"):
        prof = _AGENT_DOMAIN_PROFILES[key]
        assert {"label", "gather", "act", "verify", "areas"} <= set(prof)


# ── C — preflight neutral + dominios ──────────────────────────────────────────

def test_preflight_explain_is_neutral():
    from agent.loop_helpers import _PF_PHRASES
    for phrase in _PF_PHRASES[("explain", None)]:
        assert "código" not in phrase and "módulo" not in phrase


def test_preflight_search_is_neutral():
    from agent.loop_helpers import _PF_PHRASES
    for phrase in _PF_PHRASES[("search", None)]:
        assert "código" not in phrase


def test_preflight_new_domains_detected():
    from agent.loop_helpers import _pick_preflight_phrase, _PF_PHRASES
    # web/crawl → acción 'create' + dominio 'web' (cualquiera de sus frases)
    r = _pick_preflight_phrase("haz crawl de las noticias")
    assert r in _PF_PHRASES[("create", "web")], r
    # office (dominio 'docs') → todas las frases de create/docs mencionan "documento"
    p = _pick_preflight_phrase("genera un informe word")
    assert p in _PF_PHRASES[("create", "docs")], p
    assert "documento" in p.lower()


# ── D — narración de teams en SYSTEM_RULES ────────────────────────────────────

def test_system_rules_team_preannounce_and_synthesis():
    from agent.loop import SYSTEM_RULES
    assert "anuncia al usuario en 1 frase la composición" in SYSTEM_RULES
    assert "SINTETIZA" in SYSTEM_RULES
    # Ya no manda task_done() inmediato sin síntesis
    assert "task_done() inmediatamente" not in SYSTEM_RULES


# ── E — verbos de dominio en el live block ────────────────────────────────────

def test_live_verbs_cover_mcp_domains():
    from agent.loop_helpers import _TOOL_LIVE_VERBS
    assert _TOOL_LIVE_VERBS["email_send"].startswith("Sending")
    assert _TOOL_LIVE_VERBS["doc_create"] == "Generating"
    assert _TOOL_LIVE_VERBS["sqlite_query"] == "Querying"
    assert _TOOL_LIVE_VERBS["tapo_on_off"] == "Controlling"
    assert _TOOL_LIVE_VERBS["web_fetch"] == "Fetching"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
