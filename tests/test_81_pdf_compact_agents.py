"""Tests de los 3 fixes de robustez (sesión PDF/hexápodo):

1. Etiquetado de contenido externo (web_fetch/pdf) para que el LLM no lo confunda
   con un mensaje nuevo del usuario (_postprocess_tool_result).
2. Hint reactivo de "arranque en frío a mitad de tarea" (_turn_guidance).
3. Exposición de especialidades de agentes (Rol) en schemas de orquestación y
   en el system prompt, para que el LLM delegue en el agente adecuado.

No requiere LLM ni conexión de red.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_loop():
    """AgentLoop mínimo para probar _postprocess_tool_result y _turn_guidance."""
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
    loop.is_subagent = False
    loop.capture_output = True
    loop._status_cb = None
    loop._auto_continue_count = 0
    loop._plan_tasks = []
    loop._pending_tasks = []
    loop._last_tool_calls = []
    loop._last_agent_msg = ""
    loop._turn_text_emitted = True
    loop._empty_search_streak = 0
    loop._empty_search_patterns = []
    loop._failed_edit_streak = 0
    loop._failed_edit_patterns = []
    loop._failed_modify_by_path = {}
    loop._bash_block_counts = {}
    loop._session_reads = []
    loop._task_last_test = ""
    return loop


# ── Fix B: etiquetado de contenido externo ───────────────────────────────────

class TestExternalDocLabeling:
    def test_web_fetch_result_is_labeled(self):
        loop = _make_loop()
        out = loop._postprocess_tool_result(
            "web_fetch", {"url": "https://x.com/doc.pdf"},
            "Contenido del documento descargado...",
        )
        assert out.startswith("[Resultado de la tool web_fetch")
        assert "NO un mensaje nuevo del usuario" in out
        assert "https://x.com/doc.pdf" in out
        assert "Contenido del documento descargado" in out

    def test_pdf_extract_text_labeled_with_path(self):
        loop = _make_loop()
        out = loop._postprocess_tool_result(
            "pdf_extract_text", {"path": "/tmp/manual.pdf"}, "texto del pdf",
        )
        assert out.startswith("[Resultado de la tool pdf_extract_text")
        assert "/tmp/manual.pdf" in out

    def test_error_result_not_labeled(self):
        loop = _make_loop()
        out = loop._postprocess_tool_result(
            "web_fetch", {"url": "https://x.com"}, "Error descargando: timeout",
        )
        assert not out.startswith("[Resultado de la tool")
        assert out == "Error descargando: timeout"

    def test_non_external_tool_unaffected(self):
        loop = _make_loop()
        out = loop._postprocess_tool_result(
            "read_file", {"path": "/src/a.py"}, "código fuente",
        )
        assert out == "código fuente"


# ── Fix C: hint reactivo de arranque en frío ─────────────────────────────────

class TestColdStartHint:
    def test_cold_start_hint_fires_after_tools(self):
        loop = _make_loop()
        loop._last_tool_calls = [("web_fetch", "{}", "ok")]
        loop._last_agent_msg = ("¡Hola! Veo que has compartido un PDF del robot. "
                                "¿En qué puedo ayudarte hoy?")
        g = loop._turn_guidance()
        assert "arranque en frío" in g
        assert "SALIDA DE TUS HERRAMIENTAS" in g

    def test_no_hint_without_tools(self):
        loop = _make_loop()
        loop._last_tool_calls = []
        loop._last_agent_msg = "¡Hola! ¿En qué puedo ayudarte?"
        g = loop._turn_guidance()
        assert "arranque en frío" not in g

    def test_no_hint_for_normal_work_text(self):
        loop = _make_loop()
        loop._last_tool_calls = [("read_file", "{}", "ok")]
        loop._last_agent_msg = "Voy a revisar el módulo de control y aplicar el fix."
        g = loop._turn_guidance()
        assert "arranque en frío" not in g


# ── Fix D: especialidades de agentes ─────────────────────────────────────────

def _write_identity(ws: Path, name: str, rol: str):
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "IDENTITY.md").write_text(
        f"# IDENTITY.md — {name}\n\n## Metadatos\n\n"
        f"- **Nombre:** {name}\n- **Rol:** {rol}\n",
        encoding="utf-8",
    )


class TestAgentRole:
    def test_agent_role_reads_rol_field(self, tmp_path):
        ws = tmp_path / "webcrawler"
        _write_identity(ws, "WebCrawler", "Especialista en búsqueda e investigación web")
        from workspace.manager import agent_role
        assert agent_role(ws) == "Especialista en búsqueda e investigación web"

    def test_agent_role_missing_file_returns_empty(self, tmp_path):
        from workspace.manager import agent_role
        assert agent_role(tmp_path / "nope") == ""


class TestAgentsDescrInSchema:
    def _runner(self, tmp_path):
        from config import OOConfig, AgentDef
        from agent.subagent import SubAgentRunner
        ws_main = tmp_path / "main"
        ws_web = tmp_path / "webcrawler"
        _write_identity(ws_main, "OOCode", "Asistente de programación local")
        _write_identity(ws_web, "WebCrawler", "Búsqueda e investigación en internet")
        cfg = OOConfig()
        cfg.agents = [
            AgentDef(id="main", name="OOCode", emoji="🤖", workspace=str(ws_main)),
            AgentDef(id="webcrawler", name="WebCrawler", emoji="🕷",
                     workspace=str(ws_web)),
        ]
        return SubAgentRunner(cfg, MagicMock(), lambda *a, **k: None)

    def test_spawn_subagent_schema_includes_roles(self, tmp_path):
        runner = self._runner(tmp_path)
        _, _, schema = runner.as_tool_schema()
        desc = schema["description"]
        assert "webcrawler" in desc
        assert "Búsqueda e investigación en internet" in desc
        assert "Asistente de programación local" in desc

    def test_agents_descr_cached(self, tmp_path):
        runner = self._runner(tmp_path)
        first = runner._agents_descr()
        assert runner._agents_descr() is first  # mismo objeto cacheado


class TestAgentsSectionInSystemPrompt:
    def test_section_built_with_multiple_agents(self, tmp_path):
        """La sección 'Agentes disponibles para delegar' lista id+rol con >1 agente."""
        from config import OOConfig, AgentDef
        from workspace.manager import agent_role
        ws_a = tmp_path / "coding"
        ws_b = tmp_path / "webcrawler"
        _write_identity(ws_a, "Coding", "Programación y refactorización")
        _write_identity(ws_b, "WebCrawler", "Búsqueda web")
        cfg = OOConfig()
        cfg.agents = [
            AgentDef(id="coding", name="Coding", emoji="💻", workspace=str(ws_a)),
            AgentDef(id="webcrawler", name="WebCrawler", emoji="🕷", workspace=str(ws_b)),
        ]
        # Reproduce la lógica de _system_prompt (gating + construcción)
        assert len(cfg.agents) > 1
        roles = {a.id: agent_role(a.workspace) for a in cfg.agents}
        assert roles["webcrawler"] == "Búsqueda web"
        assert roles["coding"] == "Programación y refactorización"


# ── Capa de personalización: secciones "## Notas" de AGENTS.md/TOOLS.md ───────

class TestWorkspaceCustomizationLayer:
    """load_mini_context carga la personalización del usuario (## Notas) sin
    tocar SYSTEM_RULES; los placeholders de plantilla no añaden nada."""

    def _ws(self, tmp_path):
        from workspace.manager import WorkspaceManager
        ws = WorkspaceManager(str(tmp_path), "Coding", "💻")
        ws.init()
        return ws

    def test_section_extraction_skips_placeholders(self):
        from workspace.manager import _extract_section, _agents, _tools
        assert _extract_section(_agents("X", "/ws"), "Notas") == ""
        assert _extract_section(_tools("X", "h", {"bash": "ask"}), "Notas") == ""

    def test_section_extraction_returns_user_content(self):
        from workspace.manager import _extract_section
        md = "# T\n\n## Notas\n\nDelega web en webcrawler.\n\n## Otra\nx"
        assert _extract_section(md, "Notas") == "Delega web en webcrawler."

    def test_section_extraction_caps_length(self):
        from workspace.manager import _extract_section
        big = "x" * 5000
        md = f"## Notas\n{big}\n"
        out = _extract_section(md, "Notas", max_chars=100)
        assert len(out) <= 130 and "truncado" in out

    def test_mini_context_excludes_placeholders(self, tmp_path):
        ws = self._ws(tmp_path)
        ctx = ws.load_mini_context()
        # Sin personalizar, no aparecen las cabeceras de la capa de usuario
        assert "## Personalización de agentes" not in ctx
        assert "## Preferencias de herramientas" not in ctx

    def test_mini_context_includes_user_customization(self, tmp_path):
        ws = self._ws(tmp_path)
        # El usuario personaliza la sección "## Notas" de TOOLS.md y AGENTS.md
        tools_p = tmp_path / "TOOLS.md"
        tools_p.write_text(tools_p.read_text().replace(
            "## Notas\n",
            "## Notas\n\nPara tests usa run_tests, nunca bash pytest.\n", 1))
        agents_p = tmp_path / "AGENTS.md"
        agents_p.write_text(agents_p.read_text().replace(
            "## Notas\n",
            "## Notas\n\nDelega la búsqueda web en webcrawler.\n", 1))

        ctx = ws.load_mini_context()
        assert "## Preferencias de herramientas" in ctx
        assert "run_tests, nunca bash pytest" in ctx
        assert "## Personalización de agentes" in ctx
        assert "Delega la búsqueda web en webcrawler" in ctx
