"""Tests del pre-flight _precheck_tool_call en AgentLoop (sin LLM)."""
import sys
import re
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Fixture: instancia mínima de AgentLoop ──────────────────────────────────

@pytest.fixture
def loop():
    """AgentLoop con dependencias mockeadas — solo testea _precheck_tool_call."""
    with patch("ollama.Client"), \
         patch("agent.loop.ToolRegistry"), \
         patch("agent.loop.PermissionManager"), \
         patch("agent.loop.MemorySystem"), \
         patch("agent.loop.SessionManager"), \
         patch("agent.loop.ConversationContext"), \
         patch("agent.loop.WorkspaceManager"), \
         patch("agent.loop.ChatLogger"):
        from agent.loop import AgentLoop
        from config import OOConfig
        cfg = OOConfig(model="test", workspace="/tmp")
        lp = AgentLoop.__new__(AgentLoop)
        lp._empty_search_streak = 0
        lp._empty_search_patterns = []
        lp._turn_read_cache = {}
        lp._turn_write_seen = {}
        lp._turn_written_scripts = set()
        lp._turn_read_paths = set()
        lp._pending_tasks = []
        lp._bash_block_counts = {}
        lp._kill_requested = False
        return lp


# ── write_file: scripts temporales ──────────────────────────────────────────

class TestWriteFileTempScript:
    @pytest.mark.parametrize("path", [
        "/home/user/project/fix_imports.py",
        "/tmp/improve_v2.py",
        "migrate_schema.sh",
        "/root/refactor_all.py",
        "temp_converter.py",
        "batch_update.sh",
        "auto_fix.bash",
        "apply_patch.py",
    ])
    def test_blocks_temp_script_names(self, loop, path):
        result = loop._precheck_tool_call("write_file", {"path": path})
        assert result is not None
        assert "⛔" in result
        assert "BLOQUEÓ write_file" in result

    @pytest.mark.parametrize("path", [
        "/home/user/project/main.py",
        "/src/models/user.py",
        "config.py",
        "setup.sh",
        "Makefile",
        "/home/user/project/utils/parser.py",
    ])
    def test_allows_permanent_files(self, loop, path):
        result = loop._precheck_tool_call("write_file", {"path": path})
        assert result is None

    def test_registers_any_py_sh_written(self, loop):
        loop._precheck_tool_call("write_file", {"path": "/project/config.py"})
        assert "config.py" in loop._turn_written_scripts

    def test_registers_basename_of_temp_script(self, loop):
        loop._precheck_tool_call("write_file", {"path": "/project/fix_all.py"})
        assert "fix_all.py" in loop._turn_written_scripts


# ── bash: heredoc Python ─────────────────────────────────────────────────────

class TestBashHeredocPython:
    @pytest.mark.parametrize("command", [
        "python3 << 'EOF'\nprint('hi')\nEOF",
        'python3 <<EOF\nimport os\nEOF',
        "python << 'EOF'\ncode\nEOF",
    ])
    def test_blocks_heredoc_python(self, loop, command):
        result = loop._precheck_tool_call("bash", {"command": command})
        assert result is not None
        assert "⛔" in result
        assert "heredoc" in result.lower() or "python_exec" in result

    def test_allows_normal_python_call(self, loop):
        result = loop._precheck_tool_call("bash", {"command": "python3 manage.py migrate"})
        assert result is None


# ── bash: cat > fichero << EOF ───────────────────────────────────────────────

class TestBashCatEof:
    @pytest.mark.parametrize("command", [
        "cat > config.json << 'EOF'\n{}\nEOF",
        "cat > /tmp/data.txt <<EOF\ndata\nEOF",
    ])
    def test_blocks_cat_eof(self, loop, command):
        result = loop._precheck_tool_call("bash", {"command": command})
        assert result is not None
        assert "⛔" in result
        assert "write_file" in result


# ── bash: ejecutar script escrito este turno ─────────────────────────────────

class TestBashRunScriptThisTurn:
    def test_blocks_running_temp_script_written_this_turn(self, loop):
        # Primero, el modelo "escribe" el script (bloqueado, pero se registra en _turn_written_scripts)
        loop._turn_written_scripts.add("fix_all.py")
        result = loop._precheck_tool_call("bash", {"command": "python3 fix_all.py"})
        assert result is not None
        assert "⛔" in result
        assert "fix_all.py" in result

    def test_blocks_running_script_with_full_path(self, loop):
        loop._turn_written_scripts.add("/project/improve_v3.py")
        result = loop._precheck_tool_call("bash", {"command": "python3 /project/improve_v3.py"})
        assert result is not None
        assert "⛔" in result

    def test_blocks_running_by_temp_name_pattern(self, loop):
        # Incluso sin haberlo "escrito" antes, si el nombre es temp se bloquea
        result = loop._precheck_tool_call("bash", {"command": "python3 migrate_data.py"})
        assert result is not None
        assert "⛔" in result

    def test_allows_running_permanent_project_file(self, loop):
        result = loop._precheck_tool_call("bash", {"command": "python3 main.py"})
        assert result is None

    def test_allows_running_registered_non_temp_script(self, loop):
        loop._turn_written_scripts.add("server.py")
        result = loop._precheck_tool_call("bash", {"command": "python3 server.py"})
        # server.py no es nombre temporal → debe permitirse
        assert result is None


# ── bash: echo/printf redirect a script temporal ─────────────────────────────

class TestBashEchoRedirect:
    @pytest.mark.parametrize("command", [
        "echo 'import os' > fix_imports.py",
        "printf '#!/bin/bash\\nrm -rf' > migrate_all.sh",
        'echo "code" >> temp_script.py',
    ])
    def test_blocks_echo_redirect_to_temp_script(self, loop, command):
        result = loop._precheck_tool_call("bash", {"command": command})
        assert result is not None
        assert "⛔" in result

    def test_allows_echo_redirect_to_normal_file(self, loop):
        result = loop._precheck_tool_call("bash", {"command": "echo 'hello' > config.txt"})
        assert result is None  # .txt no es script


# ── bash: tee a script temporal ──────────────────────────────────────────────

class TestBashTeeScript:
    @pytest.mark.parametrize("command", [
        "cat something | tee fix_all.py",
        "generate_code | tee migrate_db.sh",
    ])
    def test_blocks_tee_to_temp_script(self, loop, command):
        result = loop._precheck_tool_call("bash", {"command": command})
        assert result is not None
        assert "⛔" in result

    def test_allows_tee_to_normal_file(self, loop):
        result = loop._precheck_tool_call("bash", {"command": "cmd | tee output.log"})
        assert result is None


# ── bash: ejecutar .sh con nombre temporal ───────────────────────────────────

class TestBashRunShScript:
    @pytest.mark.parametrize("command", [
        "bash fix_all.sh",
        "&& sh migrate_schema.sh",
        "source temp_setup.bash",
    ])
    def test_blocks_running_temp_sh_script(self, loop, command):
        result = loop._precheck_tool_call("bash", {"command": command})
        assert result is not None
        assert "⛔" in result

    def test_allows_running_normal_sh_script(self, loop):
        result = loop._precheck_tool_call("bash", {"command": "bash setup.sh"})
        assert result is None  # setup.sh no es nombre temporal


# ── _turn_guidance: pre-model evaluation ────────────────────────────────────

class TestTurnGuidance:
    def test_empty_when_no_calls(self, loop):
        loop._last_tool_calls = []
        assert loop._turn_guidance() == ""

    def test_bash_overuse_hint(self, loop):
        loop._last_tool_calls = [
            ("bash", '{"command":"grep x"}', "x found"),
            ("bash", '{"command":"grep y"}', "y found"),
            ("bash", '{"command":"find ."}', "file.py"),
            ("bash", '{"command":"ls"}', "dir"),
            ("bash", '{"command":"wc -l"}', "42"),
            ("read_file", '{"path":"x.py"}', "content"),
        ]
        hint = loop._turn_guidance()
        assert "bash" in hint.lower()
        assert "⚡" in hint

    def test_blocked_streak_hint(self, loop):
        loop._last_tool_calls = [
            ("bash", "{}", "ok result"),
            ("write_file", "{}", "⛔ AGENTE BLOQUEÓ write_file — script temporal"),
            ("bash", "{}", "⛔ AGENTE BLOQUEÓ bash — heredoc"),
        ]
        hint = loop._turn_guidance()
        assert "⚡" in hint
        assert "bloqueo" in hint.lower() or "BLOQUEO" in hint or "consecutivos" in hint

    def test_no_hint_when_calls_ok(self, loop):
        loop._last_tool_calls = [
            ("grep_code", "{}", "found it"),
            ("read_file", "{}", "content"),
            ("edit_file", "{}", "edited"),
            ("run_tests", "{}", "3 passed"),
        ]
        hint = loop._turn_guidance()
        assert hint == ""

    def test_run_tests_before_done_hint_fires(self, loop):
        """Hint 14: edición sin run_tests en el turno → aviso obligatorio."""
        loop._last_tool_calls = [
            ("read_file", '{"path":"main.py"}', "content"),
            ("edit_file", '{"path":"main.py"}', "edited"),
            ("read_file", '{"path":"utils.py"}', "content"),
        ]
        hint = loop._turn_guidance()
        assert "⚡" in hint
        assert "run_tests" in hint or "tests" in hint.lower()

    def test_run_tests_before_done_hint_silent_when_tests_ran(self, loop):
        """Hint 14 silencioso cuando run_tests ya se llamó en el turno."""
        loop._last_tool_calls = [
            ("edit_file", '{"path":"main.py"}', "edited"),
            ("run_tests", '{"path":"tests/"}', "5 passed"),
        ]
        hint = loop._turn_guidance()
        assert "código modificado, tests no ejecutados" not in hint

    def test_run_tests_before_done_hint_silent_without_writes(self, loop):
        """Hint 14 silencioso si el turno no tiene ninguna escritura."""
        loop._last_tool_calls = [
            ("grep_code", "{}", "found it"),
            ("read_file", "{}", "content"),
            ("grep_code", "{}", "match"),
        ]
        hint = loop._turn_guidance()
        assert "código modificado, tests no ejecutados" not in hint

    def test_run_tests_before_done_hint_silent_test_file(self, loop):
        """Hint 14 silencioso cuando test_file fue llamado."""
        loop._last_tool_calls = [
            ("edit_file", '{"path":"main.py"}', "edited"),
            ("test_file", '{"path":"tests/test_main.py"}', "1 passed"),
        ]
        hint = loop._turn_guidance()
        assert "código modificado, tests no ejecutados" not in hint

    def test_edit_without_read_hint(self, loop):
        """Detector 8: edit_file sin lectura previa → warning."""
        loop._last_tool_calls = [
            ("edit_file", '{"path":"main.py"}', "ok"),
            ("edit_file", '{"path":"utils.py"}', "ok"),
        ]
        hint = loop._turn_guidance()
        assert "⚡" in hint
        assert "edición" in hint.lower() or "exploración" in hint.lower()

    def test_no_edit_without_read_hint_when_read_present(self, loop):
        """Si hay read_file antes del edit, no se dispara el detector 8."""
        loop._last_tool_calls = [
            ("read_file", '{"path":"main.py"}', "content"),
            ("edit_file", '{"path":"main.py"}', "ok"),
        ]
        hint = loop._turn_guidance()
        # No debe haber hint de "edición sin exploración"
        assert "edición sin exploración" not in hint

    def test_prolonged_search_without_implementation_hint(self, loop):
        """Detector 9: ≥4 búsquedas y ≥6 calls totales sin escrituras → hint."""
        loop._last_tool_calls = [
            ("grep_code", "{}", "found"),
            ("grep_code", "{}", "found"),
            ("symbol_lookup", "{}", "found"),
            ("find_file", "{}", "found"),
            ("ls_dir", "{}", "dir"),
            ("read_file", '{"path":"x.py"}', "content"),
        ]
        hint = loop._turn_guidance()
        assert "⚡" in hint
        assert "búsquedas" in hint.lower() or "exploración" in hint.lower()

    def test_no_prolonged_search_hint_when_writes_present(self, loop):
        """Si hay escrituras, el detector 9 no se dispara."""
        loop._last_tool_calls = [
            ("grep_code", "{}", "found"),
            ("grep_code", "{}", "found"),
            ("symbol_lookup", "{}", "found"),
            ("find_file", "{}", "found"),
            ("ls_dir", "{}", "dir"),
            ("edit_file", '{"path":"x.py"}', "ok"),
        ]
        hint = loop._turn_guidance()
        assert "búsquedas" not in hint.lower() or "implementación" not in hint.lower()

    def test_web_search_escalation_triggered(self, loop):
        """Hint 12: ≥4 errores técnicos en últimas 6 acciones → web_search obligatorio."""
        loop._last_tool_calls = [
            ("bash", '{"command":"pip install x"}', "ModuleNotFoundError: No module named 'x'"),
            ("bash", '{"command":"python x.py"}', "ImportError: cannot import name 'foo'"),
            ("bash", '{"command":"curl api"}', "HTTP Error 403: Forbidden"),
            ("bash", '{"command":"python run"}', "AttributeError: 'NoneType' object has no attribute 'get'"),
        ]
        hint = loop._turn_guidance()
        assert "⚡" in hint
        assert "web_search" in hint
        assert "errores técnicos" in hint

    def test_web_search_escalation_not_triggered_when_already_searched(self, loop):
        """Hint 12 no se activa si ya se usó web_search en este turno."""
        loop._last_tool_calls = [
            ("bash", '{"command":"pip install x"}', "ModuleNotFoundError: No module named 'x'"),
            ("bash", '{"command":"python x.py"}', "ImportError: cannot import name 'foo'"),
            ("bash", '{"command":"curl api"}', "HTTP Error 403: Forbidden"),
            ("bash", '{"command":"python run"}', "AttributeError: 'NoneType' object"),
            ("web_search", '{"query":"ImportError fix"}', "result: use pip install x"),
        ]
        hint = loop._turn_guidance()
        assert "errores técnicos" not in hint

    def test_web_search_escalation_not_triggered_with_few_errors(self, loop):
        """Hint 12 no se activa con menos de 4 errores técnicos."""
        loop._last_tool_calls = [
            ("bash", '{"command":"pip install x"}', "ModuleNotFoundError: No module named 'x'"),
            ("bash", '{"command":"python x.py"}', "ImportError: cannot import 'foo'"),
            ("bash", '{"command":"ls"}', "file.py"),
            ("edit_file", '{"path":"x.py"}', "ok"),
        ]
        hint = loop._turn_guidance()
        assert "errores técnicos" not in hint

    def test_web_search_escalation_not_triggered_with_less_than_4_calls(self, loop):
        """Hint 12 requiere al menos 4 calls en _last_tool_calls."""
        loop._last_tool_calls = [
            ("bash", '{"command":"x"}', "HTTP Error 404"),
            ("bash", '{"command":"y"}', "ModuleNotFoundError"),
            ("bash", '{"command":"z"}', "ImportError"),
        ]
        hint = loop._turn_guidance()
        assert "errores técnicos" not in hint

    def test_plan_hint_for_complex_query(self, loop):
        """Hint 13: ≥5 exploraciones sin plan ni escrituras → sugerir crear plan."""
        loop._plan_tasks = []
        loop._last_tool_calls = [
            ("read_file",   '{"path":"a.py"}',   "content"),
            ("grep_code",   '{"pattern":"foo"}',  "found"),
            ("grep_code",   '{"pattern":"bar"}',  "found"),
            ("find_files",  '{"directory":"."}',  "list"),
            ("ls_dir",      '{"path":"."}',       "dir"),
            ("lsp_symbols", '{"path":"a.py"}',    "symbols"),
        ]
        hint = loop._turn_guidance()
        assert "⚡" in hint
        assert "plan" in hint.lower() or "explorac" in hint.lower()

    def test_plan_hint_not_triggered_when_plan_exists(self, loop):
        """Hint 13 no se activa si ya hay _plan_tasks."""
        import time
        loop._plan_tasks = [{"text": "T1", "status": "active",
                              "start_ts": time.time(), "end_ts": 0.0}]
        loop._last_tool_calls = [
            ("read_file",  '{"path":"a.py"}', "content"),
            ("grep_code",  '{"pattern":"x"}',  "found"),
            ("find_files", '{"directory":"."}', "list"),
            ("ls_dir",     '{"path":"."}',      "dir"),
            ("lsp_symbols",'{"path":"a.py"}',   "symbols"),
        ]
        hint = loop._turn_guidance()
        assert "sin plan activo" not in hint

    def test_plan_hint_not_triggered_when_writes_exist(self, loop):
        """Hint 13 no se activa si ya se hizo alguna escritura."""
        loop._plan_tasks = []
        loop._last_tool_calls = [
            ("read_file",  '{"path":"a.py"}', "content"),
            ("grep_code",  '{"pattern":"x"}',  "found"),
            ("grep_code",  '{"pattern":"y"}',  "found"),
            ("ls_dir",     '{"path":"."}',      "dir"),
            ("find_files", '{"directory":"."}', "list"),
            ("edit_file",  '{"path":"a.py"}',   "ok"),
        ]
        hint = loop._turn_guidance()
        assert "sin plan activo" not in hint


# ── otras tools: no bloqueadas ───────────────────────────────────────────────

class TestBashCatReadBlock:
    """bash cat <fichero> → redirigir a read_file."""

    @pytest.mark.parametrize("command", [
        "cat /src/main.py",
        "cat /home/user/config.json",
        "cat readme.md",
        "cat /etc/test.yaml",
        "cat script.sh",
    ])
    def test_blocks_cat_reading_file(self, loop, command):
        result = loop._precheck_tool_call("bash", {"command": command})
        assert result is not None
        assert "⛔" in result
        assert "read_file" in result

    @pytest.mark.parametrize("command", [
        "cat > output.txt",            # redirección → no es lectura
        "cat file1.py | grep def",     # pipe → no es lectura simple
        "cat /proc/cpuinfo",           # sin extensión del proyecto
        "ls -la",                      # otra tool
        "make -j4",
    ])
    def test_passthrough_non_read_cat(self, loop, command):
        result = loop._precheck_tool_call("bash", {"command": command})
        # Si hay bloqueo, que no sea por el cat-read (puede ser por otro motivo)
        if result is not None:
            assert "cat" not in result or "write_file" in result or "heredoc" in result


class TestBashDangerousRmBlock:
    """bash rm -rf en rutas del sistema → bloqueo de seguridad."""

    @pytest.mark.parametrize("command", [
        "rm -rf /",
        "rm -rf /*",
        "rm -rf /home",
        "rm -rf /etc",
        "rm -rf ~/",
        "rm -rf ~/*",
        "rm -fr /var",
        "sudo rm -rf /usr",
    ])
    def test_blocks_dangerous_rm(self, loop, command):
        result = loop._precheck_tool_call("bash", {"command": command})
        assert result is not None
        assert "⛔" in result
        assert "PELIGROSO" in result or "BLOQUEÓ" in result

    @pytest.mark.parametrize("command", [
        "rm -rf /tmp/my_project/build",
        "rm -rf ./dist",
        "rm -f /home/user/project/old.py",
        "rm old_file.txt",
    ])
    def test_passthrough_safe_rm(self, loop, command):
        result = loop._precheck_tool_call("bash", {"command": command})
        # No debe bloquearse por dangerous-rm (puede bloquearse por otro motivo)
        if result is not None:
            assert "PELIGROSO" not in result


class TestBashAntipatternsNew:
    """Nuevos antipatrones en tools/bash.py."""

    def test_antipattern_cat_file(self):
        from tools.bash import _check_antipatterns
        warn = _check_antipatterns("cat /src/main.py")
        assert "read_file" in warn

    def test_antipattern_diff(self):
        from tools.bash import _check_antipatterns
        warn = _check_antipatterns("diff file_a.py file_b.py")
        assert "diff_files" in warn

    def test_antipattern_pytest(self):
        from tools.bash import _check_antipatterns
        warn = _check_antipatterns("python3 -m pytest tests/")
        assert "run_tests" in warn

    def test_antipattern_mypy(self):
        from tools.bash import _check_antipatterns
        warn = _check_antipatterns("mypy src/")
        assert "mypy_check" in warn

    def test_antipattern_ruff(self):
        from tools.bash import _check_antipatterns
        warn = _check_antipatterns("ruff check src/")
        assert "lint_file" in warn or "lint_project" in warn

    def test_antipattern_flake8(self):
        from tools.bash import _check_antipatterns
        warn = _check_antipatterns("flake8 main.py")
        assert "lint_file" in warn or "lint_project" in warn


# ── _detect_tasks ────────────────────────────────────────────────────────────

class TestDetectTasks:
    def test_numbered_list(self, loop):
        msg = "Hay 3 problemas:\n1. La alineación de los headers\n2. El timeout MCP sin indent\n3. El logo ╚═══╝ no es blanco"
        tasks = loop._detect_tasks(msg)
        assert len(tasks) == 3
        assert "alineación" in tasks[0]

    def test_bullet_list(self, loop):
        msg = "Necesito que:\n- Corrijas el spinner de status\n- Actualices el toolbar de RAG\n- Añadas auto-continue para planes"
        tasks = loop._detect_tasks(msg)
        assert len(tasks) == 3

    def test_single_item_returns_empty(self, loop):
        msg = "1. Solo hay una tarea importante aquí."
        assert loop._detect_tasks(msg) == []

    def test_short_items_filtered(self, loop):
        msg = "1. A\n2. B\n3. C"
        # cada item < 10 chars → ignorado
        assert loop._detect_tasks(msg) == []

    def test_plain_text_no_tasks(self, loop):
        msg = "¿Puedes explicarme cómo funciona el loop del agente?"
        assert loop._detect_tasks(msg) == []

    def test_mixed_numbered_and_text(self, loop):
        msg = "Revisa estos 5 bugs:\n1. Problema de lint duplicado en Update\n2. Bloque MCP timeout desalineado\n3. Header de tool sale después de ejecutar\n4. Línea inferior logo color dim white\n5. RAG toolbar valores estáticos"
        tasks = loop._detect_tasks(msg)
        assert len(tasks) == 5

    def test_caps_at_12(self, loop):
        lines = "\n".join(f"{i+1}. Tarea número {i+1} con texto suficientemente largo" for i in range(15))
        tasks = loop._detect_tasks(lines)
        assert len(tasks) == 12

    def test_subbullets_not_counted(self, loop):
        """Sub-bullets indentados bajo un item numerado no se cuentan como tareas."""
        msg = (
            "Tareas:\n"
            "1. Revisar nginx y docker-compose.yml:\n"
            "  - Frontend: http://localhost:8080/ -> error 500\n"
            "  - Panel admin: http://localhost:8080/wp-admin -> error 500\n"
            "2. Cuando funcione, configura el tema por defecto\n"
            "3. Actualiza OOCODE.md con los cambios realizados\n"
            "4. Actualiza o crea README.md con info del proyecto\n"
        )
        tasks = loop._detect_tasks(msg)
        assert len(tasks) == 4, f"Esperados 4 (no subbullets), obtenidos: {tasks}"
        assert "nginx" in tasks[0]

    def test_top_level_bullets_only(self, loop):
        """Bullets de primer nivel se cuentan; bullets indentados no."""
        msg = (
            "Necesito que:\n"
            "- Corrijas el spinner de status de la aplicación\n"
            "  - Detalle: el color no parpadea correctamente\n"
            "- Actualices el toolbar de RAG con los nuevos datos\n"
            "- Añadas auto-continue para planes multi-tarea\n"
        )
        tasks = loop._detect_tasks(msg)
        assert len(tasks) == 3
        assert "spinner" in tasks[0]

    def test_pending_tasks_injected_in_guidance(self, loop):
        """_pending_tasks se inyecta en _turn_guidance cuando no hay historial."""
        loop._pending_tasks = ["Corregir alineación de headers", "Actualizar color del logo"]
        loop._last_tool_calls = []
        hint = loop._turn_guidance()
        assert "⚡" in hint
        assert "PLAN OBLIGATORIO" in hint
        assert "Corregir alineación" in hint
        assert "2 tareas" in hint

    def test_pending_tasks_not_injected_when_tools_done(self, loop):
        """Si ya hay historial de tool calls, no se re-inyectan las tareas."""
        loop._pending_tasks = ["Corregir alineación de headers", "Actualizar color del logo"]
        loop._last_tool_calls = [
            ("read_file", '{"path":"main.py"}', "content"),
        ]
        hint = loop._turn_guidance()
        assert "PLAN OBLIGATORIO" not in hint

    def test_no_pending_no_hint(self, loop):
        """Sin _pending_tasks y sin tool_calls → "" (comportamiento original)."""
        loop._pending_tasks = []
        loop._last_tool_calls = []
        assert loop._turn_guidance() == ""


class TestOtherToolsPassThrough:
    @pytest.mark.parametrize("name,args", [
        ("read_file",   {"path": "/project/main.py"}),
        ("grep_code",   {"pattern": "def foo", "directory": "/src"}),
        ("python_exec", {"code": "print(42)"}),
        ("bash",        {"command": "make -j4"}),
        ("bash",        {"command": "git status"}),
        ("bash",        {"command": "./configure && make"}),
        ("bash",        {"command": "cargo build --release"}),
    ])
    def test_other_tools_not_blocked(self, loop, name, args):
        result = loop._precheck_tool_call(name, args)
        assert result is None

    def test_edit_file_allowed_after_read(self, loop):
        """edit_file se permite cuando el path ya fue leído este turno."""
        loop._turn_read_paths.add("/project/config.py")
        result = loop._precheck_tool_call(
            "edit_file", {"path": "/project/config.py", "old_string": "x", "new_string": "y"}
        )
        assert result is None

    def test_edit_file_blocked_without_read(self, loop):
        """edit_file se bloquea cuando el path no ha sido leído este turno."""
        result = loop._precheck_tool_call(
            "edit_file", {"path": "/project/never_read.py", "old_string": "x", "new_string": "y"}
        )
        assert result is not None
        assert "read_file" in result or "leído" in result


class TestIsCompletionReport:
    """Tests para _is_completion_report — distingue informe final de plan."""

    def test_he_completado(self, loop):
        text = "He completado todas las tareas solicitadas. Los cambios están en su lugar."
        assert loop._is_completion_report(text) is True

    def test_todo_listo(self, loop):
        text = "Todo listo. Los 5 ficheros han sido actualizados correctamente."
        assert loop._is_completion_report(text) is True

    def test_resumen_header(self, loop):
        text = "## Resumen de cambios\n- Se migró mud.h\n- Se corrigió handler"
        assert loop._is_completion_report(text) is True

    def test_tareas_completadas(self, loop):
        text = "Las 5 tareas están completadas. Aquí el detalle de cada una."
        assert loop._is_completion_report(text) is True

    def test_plan_not_completion(self, loop):
        text = "1. Voy a leer foo.py\n2. Editaré bar.py\n3. Ejecutaré los tests"
        assert loop._is_completion_report(text) is False

    def test_continuacion_not_completion(self, loop):
        text = "Ahora voy a continuar con la tarea 2 de 5. Primero leeré el fichero."
        assert loop._is_completion_report(text) is False

    def test_short_text_not_completion(self, loop):
        text = "Hecho."
        assert loop._is_completion_report(text) is False

    def test_empty_not_completion(self, loop):
        assert loop._is_completion_report("") is False


# ── _bash_block: escalada de bloqueos bash ──────────────────────────────────

class TestBashBlockEscalation:
    """_bash_block escala el mensaje según el número de reintentos."""

    def test_first_block_returns_base_msg(self, loop):
        """Primera vez: devuelve el mensaje base sin modificar."""
        msg = "⛔ AGENTE BLOQUEÓ bash — usa ls_dir."
        result = loop._bash_block("ls", msg)
        assert result == msg
        assert loop._bash_block_counts["ls"] == 1
        assert loop._kill_requested is False

    def test_second_block_escalates(self, loop):
        """Segunda vez: prefija con aviso de 2.º intento."""
        loop._bash_block("compose", "⛔ base")
        result = loop._bash_block("compose", "⛔ base")
        assert "2.º INTENTO BLOQUEADO" in result
        assert loop._bash_block_counts["compose"] == 2
        assert loop._kill_requested is False

    def test_third_block_force_stops(self, loop):
        """Tercera vez: activa _kill_requested y prefija con BUCLE FATAL."""
        loop._bash_block("grep", "⛔ base")
        loop._bash_block("grep", "⛔ base")
        result = loop._bash_block("grep", "⛔ base")
        assert "BUCLE FATAL" in result
        assert "3" in result
        assert loop._kill_requested is True

    def test_categories_are_independent(self, loop):
        """Bloques de distintas categorías no se interfieren."""
        loop._bash_block("ls", "⛔ ls")
        loop._bash_block("grep", "⛔ grep")
        result_ls = loop._bash_block("ls", "⛔ ls")
        assert "2.º INTENTO" in result_ls
        # grep solo tiene 1 bloqueo → no escalado aún
        assert loop._bash_block_counts["grep"] == 1

    def test_fourth_block_still_force_stops(self, loop):
        """4.º y sucesivos también activan _kill_requested."""
        for _ in range(4):
            loop._bash_block("sed", "⛔ base")
        assert loop._kill_requested is True
        assert loop._bash_block_counts["sed"] == 4

    def test_compose_bash_triggers_escalation_on_retry(self, loop):
        """Simula el escenario del chat.log: compose bloqueado 3 veces."""
        cmd = "docker compose up -d"
        # 1.er intento
        r1 = loop._precheck_tool_call("bash", {"command": cmd})
        assert r1 is not None and "⛔" in r1
        assert loop._kill_requested is False
        # 2.º intento
        r2 = loop._precheck_tool_call("bash", {"command": cmd})
        assert "2.º INTENTO BLOQUEADO" in r2
        assert loop._kill_requested is False
        # 3.er intento → parada forzada
        r3 = loop._precheck_tool_call("bash", {"command": cmd})
        assert "BUCLE FATAL" in r3
        assert loop._kill_requested is True

    def test_ls_bare_is_now_blocked(self, loop):
        """ls sin flags ni directorio también se bloquea (fix _BASH_LS_RE)."""
        result = loop._precheck_tool_call("bash", {"command": "ls -la"})
        assert result is not None
        assert "ls_dir" in result

    def test_ls_without_path_is_blocked(self, loop):
        """ls -la sin directorio se bloquea (bug anterior: no detectado)."""
        result = loop._precheck_tool_call("bash", {"command": "ls -la"})
        assert result is not None
        assert "⛔" in result
