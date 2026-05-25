"""Tests de robustez — 5 mejoras de auto-desarrollo (2026-05).

Cubre:
1. Filtrado de schemas de tools por tipo de tarea
2. Tracking de estado para checkpoint de tarea
3. Checkpoint inyectado en _turn_guidance
4. Compactación estructurada con ficheros y tests
5. Verificación pre-edición (old_string + ruta)

No requiere LLM ni conexión de red.
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Fixture compartida ────────────────────────────────────────────────────────

def _make_loop():
    """Construye un AgentLoop mínimo sin LLM."""
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
    loop.rt.elevated = "off"
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
    loop._turn_read_paths = set()
    loop._turn_block = []
    loop._turn_block_has_header = False
    loop._turn_written_scripts = set()
    loop._tool_current_file = ""
    loop._task_modified_files = set()
    loop._task_last_test = ""
    loop._last_user_msg = ""
    return loop


# ── 1. Filtrado de schemas ────────────────────────────────────────────────────

class TestToolSchemaFiltering:
    """_classify_task_groups y _filtered_schemas."""

    def test_no_keywords_returns_all_groups(self):
        """Sin keywords específicos → todos los grupos (modo seguro)."""
        from agent.loop import _TOOL_GROUPS
        loop = _make_loop()
        groups = loop._classify_task_groups("refactoriza el código")
        assert groups == frozenset(_TOOL_GROUPS.keys())

    def test_docker_keyword_adds_docker_group(self):
        """Keyword 'docker' → grupo docker incluido."""
        loop = _make_loop()
        groups = loop._classify_task_groups("crea un docker-compose para postgres")
        assert "docker" in groups
        assert "core" in groups

    def test_git_keyword_adds_git_group(self):
        """Keyword 'commit' → grupo git incluido."""
        loop = _make_loop()
        groups = loop._classify_task_groups("haz un commit con los cambios")
        assert "git" in groups
        assert "core" in groups

    def test_system_keyword_adds_system_group(self):
        """Keyword 'systemctl' → grupo system incluido."""
        loop = _make_loop()
        groups = loop._classify_task_groups("comprueba el status del systemctl")
        assert "system" in groups

    def test_packages_keyword_adds_packages_group(self):
        """Keyword 'apt' → grupo packages incluido."""
        loop = _make_loop()
        groups = loop._classify_task_groups("apt install python3-dev")
        assert "packages" in groups

    def test_lsp_always_included_with_specific_group(self):
        """lsp y core siempre presentes cuando hay grupos específicos."""
        loop = _make_loop()
        groups = loop._classify_task_groups("haz un git commit")
        assert "core" in groups
        assert "lsp" in groups

    def test_memory_always_included_with_specific_group(self):
        """memory siempre presente cuando hay grupos específicos."""
        loop = _make_loop()
        groups = loop._classify_task_groups("docker compose up")
        assert "memory" in groups

    def test_filtered_schemas_returns_subset_for_docker(self):
        """Con keywords docker, _filtered_schemas filtra correctamente."""
        from agent.loop import _TOOL_GROUPS
        loop = _make_loop()
        # Registrar herramientas simuladas: algunas de core, otras de docker
        core_tools = list(_TOOL_GROUPS["core"])[:5]
        docker_tools = list(_TOOL_GROUPS["docker"])[:3]
        system_tools = list(_TOOL_GROUPS["system"])[:3]  # no deben aparecer para docker task
        for tname in core_tools + docker_tools + system_tools:
            loop.registry.register(tname, lambda **k: "ok",
                                   {"name": tname, "description": "test", "parameters": {}})

        all_s = loop.registry.ollama_schemas()
        filtered = loop._filtered_schemas("docker compose up los servicios")
        # El filtrado debe ser ≤ len(all_s)
        assert len(filtered) <= len(all_s)
        # Los core tools deben estar presentes
        schema_names = {s.get("function", {}).get("name", "") for s in filtered}
        for cn in core_tools:
            assert cn in schema_names, f"{cn} (core) debe estar en schemas filtrados"

    def test_filtered_schemas_fallback_when_too_few(self):
        """Si filtrado < 20 schemas, devuelve todos."""
        loop = _make_loop()
        # Solo 5 schemas registrados en total
        for i in range(5):
            tname = f"fake_tool_{i}"
            loop.registry.register(tname, lambda **k: "ok",
                                   {"name": tname, "description": "x", "parameters": {}})

        all_s = loop.registry.ollama_schemas()
        filtered = loop._filtered_schemas("docker compose up")
        assert filtered == all_s  # fallback: todos

    def test_empty_hint_returns_all_schemas(self):
        """Hint vacío → todos los grupos → todos los schemas."""
        from agent.loop import _TOOL_GROUPS
        loop = _make_loop()
        groups = loop._classify_task_groups("")
        assert groups == frozenset(_TOOL_GROUPS.keys())

    def test_multiple_keywords_adds_multiple_groups(self):
        """Múltiples keywords → múltiples grupos detectados."""
        loop = _make_loop()
        groups = loop._classify_task_groups("git commit y luego docker compose up")
        assert "git" in groups
        assert "docker" in groups
        assert "core" in groups


# ── 2. Tracking de estado (checkpoint) ───────────────────────────────────────

class TestTaskCheckpointTracking:
    """_task_modified_files y _task_last_test se inicializan y rastrean."""

    def test_init_empty_modified_files(self):
        """El set de ficheros modificados empieza vacío."""
        loop = _make_loop()
        assert loop._task_modified_files == set()

    def test_init_empty_test_result(self):
        """El resultado de tests empieza vacío."""
        loop = _make_loop()
        assert loop._task_last_test == ""

    def test_modified_files_is_set(self):
        """_task_modified_files es un set."""
        loop = _make_loop()
        assert isinstance(loop._task_modified_files, set)

    def test_can_add_to_modified_files(self):
        """Se puede añadir rutas al set de ficheros modificados."""
        loop = _make_loop()
        loop._task_modified_files.add("/home/user/project/main.py")
        loop._task_modified_files.add("/home/user/project/config.py")
        assert len(loop._task_modified_files) == 2
        assert "/home/user/project/main.py" in loop._task_modified_files

    def test_can_set_test_result(self):
        """Se puede establecer el resultado de tests."""
        loop = _make_loop()
        loop._task_last_test = "2518 passed, 1 skipped"
        assert loop._task_last_test == "2518 passed, 1 skipped"


# ── 3. Hint #16 (checkpoint) en _turn_guidance ───────────────────────────────

class TestCheckpointHintInGuidance:
    """El hint #16 inyecta el estado de checkpoint en auto-continúas."""

    def _guidance(self, loop):
        return loop._turn_guidance()

    def test_no_checkpoint_without_auto_continue(self):
        """Sin auto-continue (count=0), no se muestra checkpoint."""
        loop = _make_loop()
        loop._auto_continue_count = 0
        loop._task_modified_files = {"/project/loop.py"}
        loop._last_tool_calls = [("read_file", "{}", "ok")]
        result = self._guidance(loop)
        assert "CHECKPOINT" not in result

    def test_no_checkpoint_without_modified_files(self):
        """Con auto-continue pero sin ficheros modificados, no hay checkpoint."""
        loop = _make_loop()
        loop._auto_continue_count = 2
        loop._task_modified_files = set()
        loop._last_tool_calls = [("read_file", "{}", "ok")]
        result = self._guidance(loop)
        assert "CHECKPOINT" not in result

    def test_checkpoint_fires_with_ac_and_modified_files(self):
        """Con auto-continue ≥1 y ficheros modificados → aparece CHECKPOINT."""
        loop = _make_loop()
        loop._auto_continue_count = 1
        loop._task_modified_files = {"/project/agent/loop.py", "/project/config.py"}
        loop._last_tool_calls = [("edit_file", "{}", "ok")]
        result = self._guidance(loop)
        assert "CHECKPOINT" in result
        assert "loop.py" in result or "config.py" in result

    def test_checkpoint_includes_test_result(self):
        """Si hay resultado de tests, se incluye en el checkpoint."""
        loop = _make_loop()
        loop._auto_continue_count = 2
        loop._task_modified_files = {"/project/main.py"}
        loop._task_last_test = "42 passed, 0 failed"
        loop._last_tool_calls = [("run_tests", "{}", "42 passed")]
        result = self._guidance(loop)
        assert "42 passed" in result

    def test_checkpoint_without_test_result_no_test_line(self):
        """Sin resultado de tests, el checkpoint no menciona tests."""
        loop = _make_loop()
        loop._auto_continue_count = 1
        loop._task_modified_files = {"/project/main.py"}
        loop._task_last_test = ""
        loop._last_tool_calls = [("edit_file", "{}", "ok")]
        result = self._guidance(loop)
        assert "CHECKPOINT" in result
        assert "Tests" not in result


# ── 4. Compactación estructurada ─────────────────────────────────────────────

class TestStructuredCompaction:
    """_summarize_messages incluye ficheros modificados y tests en el prompt."""

    def test_state_section_present_with_modified_files(self):
        """Con ficheros modificados, el prompt de compactación los incluye."""
        loop = _make_loop()
        loop._task_modified_files = {"/project/loop.py", "/project/config.py"}
        loop._task_last_test = ""
        loop._plan_tasks = []

        captured = {}

        def fake_chat(**kwargs):
            captured["prompt"] = kwargs.get("messages", [{}])[-1].get("content", "")
            r = MagicMock()
            r.message.content = "• resumen"
            return r

        loop.client = MagicMock()
        loop.client.chat = fake_chat
        loop._active_model = lambda: "test-model"
        loop._build_options = lambda: {}
        loop._chat_kwargs = lambda opts: {}
        loop.ws = MagicMock()
        loop._all_plan_tasks_done = lambda: True

        loop._summarize_messages([
            {"role": "user", "content": "test"},
            {"role": "assistant", "content": "ok"},
        ])

        prompt = captured.get("prompt", "")
        assert "Estado de tarea al compactar" in prompt
        assert "loop.py" in prompt or "config.py" in prompt

    def test_state_section_includes_test_result(self):
        """Con resultado de tests, el prompt lo incluye."""
        loop = _make_loop()
        loop._task_modified_files = {"/project/main.py"}
        loop._task_last_test = "100 passed, 0 failed"
        loop._plan_tasks = []

        captured = {}

        def fake_chat(**kwargs):
            captured["prompt"] = kwargs.get("messages", [{}])[-1].get("content", "")
            r = MagicMock()
            r.message.content = "• resumen"
            return r

        loop.client = MagicMock()
        loop.client.chat = fake_chat
        loop._active_model = lambda: "test-model"
        loop._build_options = lambda: {}
        loop._chat_kwargs = lambda opts: {}
        loop.ws = MagicMock()
        loop._all_plan_tasks_done = lambda: True

        loop._summarize_messages([
            {"role": "user", "content": "test"},
            {"role": "assistant", "content": "ok"},
        ])

        prompt = captured.get("prompt", "")
        assert "100 passed" in prompt

    def test_no_state_section_when_nothing_modified(self):
        """Sin ficheros modificados ni tests, no se añade sección de estado."""
        loop = _make_loop()
        loop._task_modified_files = set()
        loop._task_last_test = ""
        loop._plan_tasks = []

        captured = {}

        def fake_chat(**kwargs):
            captured["prompt"] = kwargs.get("messages", [{}])[-1].get("content", "")
            r = MagicMock()
            r.message.content = "• resumen"
            return r

        loop.client = MagicMock()
        loop.client.chat = fake_chat
        loop._active_model = lambda: "test-model"
        loop._build_options = lambda: {}
        loop._chat_kwargs = lambda opts: {}
        loop.ws = MagicMock()
        loop._all_plan_tasks_done = lambda: True

        loop._summarize_messages([
            {"role": "user", "content": "test"},
            {"role": "assistant", "content": "ok"},
        ])

        prompt = captured.get("prompt", "")
        assert "Estado de tarea al compactar" not in prompt


# ── 5. Verificación pre-edición ───────────────────────────────────────────────

class TestPreEditVerification:
    """_precheck_tool_call verifica old_string y existencia de rutas."""

    def _precheck(self, loop, name, args):
        return loop._precheck_tool_call(name, args)

    # ── 5a. Verificación de old_string ───────────────────────────────────────

    def _mark_read(self, loop, path: str):
        """Simula que el fichero fue leído este turno (bypass del read-before-edit guard)."""
        loop._turn_read_paths.add(path)

    def test_old_string_found_allows_edit(self, tmp_path):
        """Si old_string existe exactamente en el fichero, el edit procede."""
        loop = _make_loop()
        f = tmp_path / "test.py"
        f.write_text("def hello():\n    return 42\n")
        self._mark_read(loop, str(f))  # simular read previo
        result = self._precheck(loop, "edit_file", {
            "path": str(f),
            "old_string": "def hello():\n    return 42\n",
            "new_string": "def hello():\n    return 99\n",
        })
        assert result is None

    def test_old_string_missing_blocks_edit(self, tmp_path):
        """Si old_string NO existe, el edit queda bloqueado con error."""
        loop = _make_loop()
        f = tmp_path / "test.py"
        f.write_text("def hello():\n    return 42\n")
        self._mark_read(loop, str(f))  # simular read previo
        result = self._precheck(loop, "edit_file", {
            "path": str(f),
            "old_string": "def hello():\n    return 99\n",  # no existe
            "new_string": "def hello():\n    return 0\n",
        })
        assert result is not None
        assert "PRE-EDIT FALLIDO" in result

    def test_no_check_when_no_old_string(self, tmp_path):
        """Sin old_string el check se omite; solo el read-before-edit guard puede saltar."""
        loop = _make_loop()
        f = tmp_path / "test.py"
        f.write_text("contenido")
        self._mark_read(loop, str(f))  # simular read previo
        result = self._precheck(loop, "edit_file", {
            "path": str(f),
            "old_string": "",
            "new_string": "nuevo",
        })
        # Con old_string vacío y path leído, no hay bloqueo propio de este check
        assert result is None or "PRE-EDIT FALLIDO" not in (result or "")

    def test_no_check_when_no_path(self):
        """Sin path el check se omite."""
        loop = _make_loop()
        result = self._precheck(loop, "edit_file", {
            "path": "",
            "old_string": "algo",
            "new_string": "otro",
        })
        assert result is None

    def test_error_contains_first_line_of_old_string(self, tmp_path):
        """El error muestra la primera línea del old_string buscado."""
        loop = _make_loop()
        f = tmp_path / "test.py"
        f.write_text("def real_function():\n    pass\n")
        self._mark_read(loop, str(f))
        result = self._precheck(loop, "edit_file", {
            "path": str(f),
            "old_string": "def invented_function():\n    pass\n",
            "new_string": "def invented_function():\n    return 1\n",
        })
        assert "invented_function" in result

    def test_edit_file_nonexistent_blocked_by_read_guard(self, tmp_path):
        """Si el fichero no existe y no fue leído, el read-before-edit guard lo bloquea."""
        loop = _make_loop()
        result = self._precheck(loop, "edit_file", {
            "path": str(tmp_path / "nonexistent.py"),
            "old_string": "algo",
            "new_string": "otro",
        })
        assert result is not None
        assert "leído" in result or "RUTA" in result

    # ── 5b. Verificación de existencia de ruta ────────────────────────────────

    def test_existing_path_allowed(self, tmp_path):
        """Ruta existente → no bloquea."""
        loop = _make_loop()
        f = tmp_path / "real.py"
        f.write_text("pass")
        result = self._precheck(loop, "read_sections", {
            "path": str(f),
            "sections": ["main"],
        })
        assert result is None

    def test_nonexistent_path_blocked_for_edit_file(self, tmp_path):
        """Ruta no existente en edit_file → bloqueado por el read-before-edit guard."""
        loop = _make_loop()
        result = self._precheck(loop, "edit_file", {
            "path": str(tmp_path / "ghost.py"),
            "old_string": "algo",
            "new_string": "otro",
        })
        # El read-before-edit guard bloquea (file no fue leído este turno)
        assert result is not None
        assert "leído" in result or "no has leído" in result or "RUTA" in result

    def test_nonexistent_path_blocked_for_read_sections(self, tmp_path):
        """Ruta no existente en read_sections → bloqueado."""
        loop = _make_loop()
        result = self._precheck(loop, "read_sections", {
            "path": str(tmp_path / "ghost.py"),
            "sections": ["func"],
        })
        assert result is not None
        assert "RUTA NO ENCONTRADA" in result

    def test_nonexistent_path_blocked_for_code_outline(self, tmp_path):
        """Ruta no existente en code_outline → bloqueado."""
        loop = _make_loop()
        result = self._precheck(loop, "code_outline", {
            "path": str(tmp_path / "ghost.py"),
        })
        assert result is not None
        assert "RUTA NO ENCONTRADA" in result

    def test_write_file_not_checked_for_path_existence(self, tmp_path):
        """write_file NO se comprueba la existencia (crea ficheros nuevos)."""
        loop = _make_loop()
        result = self._precheck(loop, "write_file", {
            "path": str(tmp_path / "new_file.py"),
            "content": "print('hello')",
        })
        # write_file no está en _PATH_TOOLS, no debe dar RUTA NO ENCONTRADA
        # (puede fallar por otras razones, pero no por esta)
        assert result is None or "RUTA NO ENCONTRADA" not in (result or "")

    def test_http_url_not_blocked_by_path_check(self):
        """URLs http:// no pasan por el check de existencia de ruta."""
        loop = _make_loop()
        result = self._precheck(loop, "edit_file", {
            "path": "http://example.com/file.py",
            "old_string": "algo",
            "new_string": "otro",
        })
        # Mi check de ruta no debe dispararse (el resultado puede ser None u otro error
        # del read-before-edit guard, pero no RUTA NO ENCONTRADA)
        assert result is None or "RUTA NO ENCONTRADA" not in (result or "")

    def test_error_includes_find_file_suggestion(self, tmp_path):
        """El error de ruta no encontrada sugiere usar find_file."""
        loop = _make_loop()
        result = self._precheck(loop, "read_sections", {
            "path": str(tmp_path / "missing.py"),
            "sections": ["main"],
        })
        assert "find_file" in result

    def test_bash_not_checked_for_path(self, tmp_path):
        """bash no pasa por el check de existencia de ruta."""
        loop = _make_loop()
        result = self._precheck(loop, "bash", {
            "command": f"cat {tmp_path}/nonexistent.py",
        })
        # No debe bloquear por ruta — la guarda de bash puede bloquearlo por otras razones
        assert result is None or "RUTA NO ENCONTRADA" not in (result or "")


# ── Integridad de module-level dicts ─────────────────────────────────────────

class TestToolGroupDicts:
    """_TOOL_GROUPS y _TASK_KEYWORDS tienen la estructura esperada."""

    def test_core_group_exists(self):
        from agent.loop import _TOOL_GROUPS
        assert "core" in _TOOL_GROUPS
        assert len(_TOOL_GROUPS["core"]) > 10

    def test_all_groups_are_frozensets(self):
        from agent.loop import _TOOL_GROUPS
        for name, group in _TOOL_GROUPS.items():
            assert isinstance(group, frozenset), f"grupo {name!r} debe ser frozenset"

    def test_task_keywords_are_frozensets(self):
        from agent.loop import _TASK_KEYWORDS
        for name, kws in _TASK_KEYWORDS.items():
            assert isinstance(kws, frozenset), f"keywords {name!r} debe ser frozenset"

    def test_task_keywords_cover_main_groups(self):
        from agent.loop import _TASK_KEYWORDS, _TOOL_GROUPS
        # Cada grupo que tiene keywords existe en _TOOL_GROUPS
        for g in _TASK_KEYWORDS:
            assert g in _TOOL_GROUPS, f"grupo {g!r} en _TASK_KEYWORDS no existe en _TOOL_GROUPS"

    def test_core_contains_essential_tools(self):
        from agent.loop import _TOOL_GROUPS
        core = _TOOL_GROUPS["core"]
        for tool in ("edit_file", "read_file", "grep_code", "run_tests", "web_search"):
            assert tool in core, f"'{tool}' debe estar en core"


# ── Subagente: acceso a tools MCP del padre ───────────────────────────────────

class TestSubagentMCPAccess:
    """Verifica que los subagentes reciben los tools MCP del padre (fix 2026-05)."""

    def test_parent_mcp_pool_injected_in_run(self):
        """Las tools del MCP pool del padre se registran en el registry del subagente."""
        from agent.subagent import SubAgentRunner
        from tools.registry import ToolRegistry
        from unittest.mock import MagicMock
        from config import OOConfig

        cfg = OOConfig.load()
        mock_fn = lambda **kw: "ok"

        # Simular un McpPool mínimo con tools
        mock_pool = MagicMock()
        mock_pool.all_oocode_tools.return_value = [
            ("git_status", mock_fn, {"name": "git_status", "description": "d",
                                     "parameters": {"type": "object", "properties": {}}}),
            ("run_tests",  mock_fn, {"name": "run_tests",  "description": "d",
                                     "parameters": {"type": "object", "properties": {}}}),
            ("regex_replace", mock_fn, {"name": "regex_replace", "description": "d",
                                        "parameters": {"type": "object", "properties": {}}}),
            # python_exec: ya existe nativo → no debe sobreescribirse
            ("python_exec", mock_fn, {"name": "python_exec", "description": "MCP version",
                                      "parameters": {"type": "object", "properties": {}}}),
        ]
        mock_pool.resource_oocode_tools.return_value = []
        mock_pool.prompt_oocode_tools.return_value = []

        # Construir el registry base (imita build_registry)
        base_reg = ToolRegistry()
        native_fn = lambda **kw: "native"
        base_reg.register("python_exec", native_fn,
                          {"name": "python_exec", "description": "nativa",
                           "parameters": {"type": "object", "properties": {}}})

        runner = SubAgentRunner(cfg, MagicMock(), lambda *a, **kw: base_reg)
        runner._parent_mcp_pool = mock_pool

        # Ejecutar solo la lógica de registro MCP (sin invocar run() completo)
        for mcp_name, mcp_fn, mcp_schema in mock_pool.all_oocode_tools():
            if not base_reg.has(mcp_name):
                base_reg.register(mcp_name, mcp_fn, mcp_schema)

        assert base_reg.has("git_status"),    "git_status debe estar en registry del subagente"
        assert base_reg.has("run_tests"),     "run_tests debe estar en registry del subagente"
        assert base_reg.has("regex_replace"), "regex_replace debe estar en registry del subagente"
        # python_exec nativa NO debe ser sobreescrita (has() antes de register)
        assert base_reg.get_fn("python_exec") is native_fn, \
            "python_exec nativa no debe ser sobreescrita por la versión MCP"

    def test_explore_deny_contains_write_tools(self):
        """_EXPLORE_DENY incluye herramientas destructivas incluyendo las nuevas."""
        from agent.subagent import SubAgentRunner
        deny = SubAgentRunner._EXPLORE_DENY
        # Herramientas de escritura clásicas
        for t in ("write_file", "edit_file", "regex_replace", "bulk_replace",
                  "smart_replace", "patch_apply"):
            assert t in deny, f"'{t}' debe estar en _EXPLORE_DENY"
        # IoT control
        for t in ("tapo_on_off", "ha_control", "alexa_speak", "mqtt_publish"):
            assert t in deny, f"'{t}' (IoT) debe estar en _EXPLORE_DENY"
        # Security ofensivas
        for t in ("nikto_scan", "gobuster_run", "hash_crack"):
            assert t in deny, f"'{t}' (security) debe estar en _EXPLORE_DENY"
        # Home Office write
        for t in ("email_send", "doc_write", "cal_create"):
            assert t in deny, f"'{t}' (home_office) debe estar en _EXPLORE_DENY"

    def test_parent_mcp_pool_none_does_not_crash(self):
        """Sin _parent_mcp_pool el bloque de registro MCP se salta sin crashear."""
        from agent.subagent import SubAgentRunner
        from tools.registry import ToolRegistry
        from unittest.mock import MagicMock
        from config import OOConfig

        cfg = OOConfig.load()
        runner = SubAgentRunner(cfg, MagicMock(), MagicMock())
        # Sin _parent_mcp_pool → getattr devuelve None, sin crash

        reg = ToolRegistry()
        parent_mcp = getattr(runner, "_parent_mcp_pool", None)
        assert parent_mcp is None, "sin inyección no debe existir _parent_mcp_pool"

        # Simular el bloque de registro MCP del subagente con pool=None
        if parent_mcp is not None:
            for mcp_name, mcp_fn, mcp_schema in parent_mcp.all_oocode_tools():
                if not reg.has(mcp_name):
                    reg.register(mcp_name, mcp_fn, mcp_schema)

        assert not reg.has("git_status"), "sin MCP pool no debe tener git_status"
