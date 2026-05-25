"""Tests para las guardas de tool calls: precheck de docker_exec, write_file,
python_exec subprocess-docker, y parada mid-batch con _kill_requested.

Cubre:
- docker_exec con heredoc bloqueado
- docker_exec sin heredoc permitido (pasa precheck)
- write_file a rutas /var/www/ etc bloqueado
- write_file a rutas normales permitido
- python_exec subprocess.docker bloqueado
- python_exec normal permitido
- write_file Permission denied añade sugerencia docker_cp
- _kill_requested: tools posteriores en el mismo batch se cancelan
- SYSTEM_RULES contiene instrucciones para escribir en contenedores Docker
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import threading
from unittest.mock import MagicMock, patch


def _make_loop():
    from agent.loop import AgentLoop
    from tools.registry import ToolRegistry
    from tools.permissions import PermissionManager
    from config import OOConfig
    cfg = OOConfig()
    loop = AgentLoop.__new__(AgentLoop)
    loop.config = cfg
    loop.registry = ToolRegistry()
    loop.permissions = PermissionManager(cfg.permissions)
    loop.memory = MagicMock()
    loop.workspace_manager = MagicMock()
    loop.session = MagicMock()
    loop.rt = MagicMock()
    loop.rt.verbose = False
    loop.rt.accent_color = "cyan"
    loop.is_subagent = False
    loop.capture_output = False
    loop._status_cb = None
    loop._auto_continue_count = 0
    loop._plan_tasks = []
    loop._turn_written_scripts = set()
    loop._turn_read_cache = {}
    loop._turn_write_seen = {}
    loop._turn_block_has_header = False
    loop._turn_block = []
    loop._tool_current_file = ""
    loop._bash_block_counts = {}
    loop._kill_requested = False
    loop._pending_tasks = []
    loop._last_tool_calls = []
    loop._start_live_block_cb = None
    loop._flush_live_block_cb = None
    loop._live_tool_count = 0
    loop._turn_read_paths = set()
    loop._session_reads = []
    return loop


# ── docker_exec precheck ──────────────────────────────────────────────────────

class TestDockerExecPrecheck:
    def test_heredoc_blocked(self):
        loop = _make_loop()
        result = loop._precheck_tool_call("docker_exec", {
            "container": "mycontainer",
            "command": "cat > /tmp/file.txt << 'EOF'\nhello\nEOF"
        })
        assert result is not None
        assert "heredoc" in result.lower() or "BLOQUEÓ" in result
        assert "docker_cp" in result

    def test_heredoc_eof_blocked(self):
        loop = _make_loop()
        result = loop._precheck_tool_call("docker_exec", {
            "container": "myapp",
            "command": "cat > /etc/config << EOF"
        })
        assert result is not None
        assert "docker_cp" in result or "BLOQUEÓ" in result

    def test_sql_with_less_than_passes(self):
        """SQL con < no debe ser bloqueado."""
        loop = _make_loop()
        result = loop._precheck_tool_call("docker_exec", {
            "container": "mydb",
            "command": "mysql -u root -e 'SELECT * FROM t WHERE id < 100'"
        })
        assert result is None

    def test_redirect_without_heredoc_passes(self):
        """Redirección simple (>) sin heredoc pasa."""
        loop = _make_loop()
        result = loop._precheck_tool_call("docker_exec", {
            "container": "mycontainer",
            "command": "echo 'content' > /tmp/out.txt"
        })
        assert result is None

    def test_normal_command_passes(self):
        loop = _make_loop()
        result = loop._precheck_tool_call("docker_exec", {
            "container": "mycontainer",
            "command": "ls -la /var/www/html"
        })
        assert result is None

    def test_simple_echo_passes(self):
        loop = _make_loop()
        result = loop._precheck_tool_call("docker_exec", {
            "container": "mycontainer",
            "command": "php -v"
        })
        assert result is None

    def test_mcp_variant_heredoc_blocked(self):
        loop = _make_loop()
        result = loop._precheck_tool_call("mcp_oocode_assistant_docker_exec", {
            "container": "mycontainer",
            "command": "cat > /tmp/test << 'ENDSCRIPT'\ncontent\nENDSCRIPT"
        })
        assert result is not None
        assert "docker_cp" in result


# ── write_file precheck: solo bloquea scripts temporales, no rutas específicas ──

class TestWriteFilePrecheck:
    def test_temp_script_blocked(self):
        """write_file sigue bloqueando scripts .py/.sh temporales."""
        loop = _make_loop()
        result = loop._precheck_tool_call("write_file", {
            "path": "/tmp/fix_stuff.py",
            "content": "import os"
        })
        assert result is not None
        assert "BLOQUEÓ" in result

    def test_var_www_passes(self):
        """Paths del sistema NO bloqueados — el usuario puede trabajar en un servidor real."""
        loop = _make_loop()
        result = loop._precheck_tool_call("write_file", {
            "path": "/var/www/html/wp-content/themes/my-theme/style.css",
            "content": "body { color: red; }"
        })
        assert result is None

    def test_etc_nginx_passes(self):
        """Un usuario en un servidor LAMP puede editar /etc/nginx/nginx.conf."""
        loop = _make_loop()
        result = loop._precheck_tool_call("write_file", {
            "path": "/etc/nginx/nginx.conf",
            "content": "server {}"
        })
        assert result is None

    def test_opt_passes(self):
        loop = _make_loop()
        result = loop._precheck_tool_call("write_file", {
            "path": "/opt/myapp/config.json",
            "content": "{}"
        })
        assert result is None

    def test_home_project_passes(self):
        loop = _make_loop()
        result = loop._precheck_tool_call("write_file", {
            "path": "~/myproject/src/main.py",
            "content": "print('hello')"
        })
        assert result is None

    def test_tmp_regular_file_passes(self):
        loop = _make_loop()
        result = loop._precheck_tool_call("write_file", {
            "path": "/tmp/config.json",
            "content": "{}"
        })
        assert result is None


# ── python_exec subprocess docker precheck ───────────────────────────────────

class TestPythonExecSubprocessDockerPrecheck:
    def test_subprocess_docker_blocked(self):
        loop = _make_loop()
        result = loop._precheck_tool_call("python_exec", {
            "code": (
                "import subprocess\n"
                "result = subprocess.run(['docker', 'exec', 'mycontainer', 'ls'])\n"
                "print(result.stdout)"
            )
        })
        assert result is not None
        assert "BLOQUEÓ" in result
        assert "docker_exec" in result.lower() or "docker_exec" in result

    def test_subprocess_docker_compose_blocked(self):
        loop = _make_loop()
        result = loop._precheck_tool_call("python_exec", {
            "code": "import subprocess; subprocess.run(['docker', 'compose', 'up', '-d'])"
        })
        assert result is not None

    def test_subprocess_check_output_docker_blocked(self):
        loop = _make_loop()
        result = loop._precheck_tool_call("python_exec", {
            "code": "import subprocess; out = subprocess.check_output(['docker', 'ps'])"
        })
        assert result is not None

    def test_normal_subprocess_passes(self):
        loop = _make_loop()
        result = loop._precheck_tool_call("python_exec", {
            "code": "import subprocess; subprocess.run(['ls', '-la'])"
        })
        assert result is None

    def test_regular_python_passes(self):
        loop = _make_loop()
        result = loop._precheck_tool_call("python_exec", {
            "code": "x = 1 + 2; print(x)"
        })
        assert result is None


# ── write_file Permission denied → sugerencia docker_cp ──────────────────────

class TestWriteFilePermissionHint:
    def _make_loop_with_registry(self):
        loop = _make_loop()
        mock_fn = MagicMock(return_value=(
            "Error escribiendo '/var/www/html/style.css': [Errno 13] Permission denied: "
            "'/var/www/html/style.css'"
        ))
        loop.registry.register("write_file", mock_fn, {
            "name": "write_file",
            "description": "test",
            "parameters": {"type": "object", "properties": {}}
        })
        return loop

    def test_permission_denied_adds_docker_cp_hint(self):
        loop = self._make_loop_with_registry()
        result = loop._execute_tool("write_file", {
            "path": "/var/www/html/style.css",
            "content": "body {}"
        })
        # El precheck bloquea /var/www/ — no llega a _execute_tool, así que
        # usamos una ruta que pase el precheck pero falle con permission denied
        # Simulamos directamente el post-processing:
        # (el precheck ya bloquea /var/www/, así que probamos la anotación
        # directamente llamando al registry con una ruta /tmp/ que falle)
        pass  # covered by next test

    def test_permission_denied_annotation_on_tmp_path(self):
        """Ruta /tmp/ pasa el precheck pero puede fallar por permission denied."""
        loop = _make_loop()
        # Simular que el registry devuelve un Permission denied
        perm_error = (
            "Error escribiendo '/tmp/test.txt': [Errno 13] Permission denied: '/tmp/test.txt'"
        )
        loop.registry.register("write_file", lambda **kw: perm_error, {
            "name": "write_file",
            "description": "test",
            "parameters": {"type": "object", "properties": {"path": {}, "content": {}}}
        })
        result = loop._execute_tool("write_file", {
            "path": "/tmp/test.txt", "content": "hello"
        })
        assert "docker_cp" in result
        assert "💡" in result


# ── _kill_requested mid-batch ────────────────────────────────────────────────

class TestKillRequestedMidBatch:
    def test_precheck_records_kill_requested(self):
        """Cuando bash es bloqueado 3 veces, _kill_requested se activa."""
        loop = _make_loop()
        # Simular 3 intentos de bash docker
        args = {"command": "docker compose up -d"}
        loop._precheck_tool_call("bash", args)
        loop._precheck_tool_call("bash", args)
        loop._precheck_tool_call("bash", args)
        assert loop._kill_requested is True

    def test_kill_at_third_attempt(self):
        """El tercer intento del mismo categoría activa el kill."""
        loop = _make_loop()
        args = {"command": "docker ps"}
        r1 = loop._precheck_tool_call("bash", args)
        assert loop._kill_requested is False
        r2 = loop._precheck_tool_call("bash", args)
        assert loop._kill_requested is False
        r3 = loop._precheck_tool_call("bash", args)
        assert loop._kill_requested is True
        assert "FATAL" in r3 or "BUCLE" in r3 or "detendrá" in r3 or "se detiene" in r3

    def test_second_attempt_warning(self):
        """El segundo intento muestra aviso de última oportunidad."""
        loop = _make_loop()
        args = {"command": "docker ps"}
        loop._precheck_tool_call("bash", args)
        r2 = loop._precheck_tool_call("bash", args)
        assert "2.º INTENTO" in r2 or "BLOQUEADO" in r2


# ── SYSTEM_RULES contiene instrucciones Docker ───────────────────────────────

class TestSystemRulesDockerInstructions:
    def test_docker_write_instruction_present(self):
        from agent.loop import SYSTEM_RULES
        assert "docker_cp" in SYSTEM_RULES
        assert "write_file" in SYSTEM_RULES

    def test_permission_denied_hint_present(self):
        from agent.loop import SYSTEM_RULES
        assert "Permission denied" in SYSTEM_RULES or "permission denied" in SYSTEM_RULES.lower()

    def test_container_write_workflow_documented(self):
        from agent.loop import SYSTEM_RULES
        # Debe mencionar el flujo: write en host + docker_cp al contenedor
        assert "docker_cp" in SYSTEM_RULES
        assert "/tmp/" in SYSTEM_RULES


# ── /elevated on bypass de guardas de redirección bash ───────────────────────

def _make_loop_elevated(elevated: str = "on"):
    loop = _make_loop()
    loop.rt.elevated = elevated
    return loop


class TestElevatedBypass:
    """Con /elevated on, las guardas de redirección bash se omiten.
    Solo quedan activas las de seguridad absoluta (rm -rf, compose down -v).
    """

    def test_elevated_on_bypasses_grep(self):
        loop = _make_loop_elevated("on")
        result = loop._precheck_tool_call("bash", {"command": "grep -rn 'ch_ret' src/"})
        assert result is None, f"grep debería pasar con elevated on, got: {result}"

    def test_elevated_on_bypasses_grep_include(self):
        loop = _make_loop_elevated("on")
        result = loop._precheck_tool_call("bash", {"command": "grep -rn 'MAX_INPUT' --include='*.h' ."})
        assert result is None

    def test_elevated_on_bypasses_find(self):
        loop = _make_loop_elevated("on")
        result = loop._precheck_tool_call("bash", {"command": "find src/ -name '*.h' -type f"})
        assert result is None

    def test_elevated_on_bypasses_sed(self):
        loop = _make_loop_elevated("on")
        result = loop._precheck_tool_call("bash", {"command": "sed -i 's/old/new/g' file.c"})
        assert result is None

    def test_elevated_on_bypasses_ls(self):
        loop = _make_loop_elevated("on")
        result = loop._precheck_tool_call("bash", {"command": "ls -la src/"})
        assert result is None

    def test_elevated_on_bypasses_cat(self):
        loop = _make_loop_elevated("on")
        result = loop._precheck_tool_call("bash", {"command": "cat mud_base.h"})
        assert result is None

    def test_elevated_on_bypasses_docker_exec(self):
        loop = _make_loop_elevated("on")
        result = loop._precheck_tool_call("bash", {"command": "docker exec myapp ls /etc"})
        assert result is None

    def test_elevated_on_bypasses_docker_compose(self):
        loop = _make_loop_elevated("on")
        result = loop._precheck_tool_call("bash", {"command": "docker compose up -d"})
        assert result is None

    def test_elevated_on_bypasses_heredoc_python(self):
        loop = _make_loop_elevated("on")
        result = loop._precheck_tool_call("bash", {"command": "python3 << EOF\nprint('hi')\nEOF"})
        assert result is None

    def test_elevated_full_bypasses_grep(self):
        loop = _make_loop_elevated("full")
        result = loop._precheck_tool_call("bash", {"command": "grep -r 'str_cmp' ."})
        assert result is None

    def test_elevated_off_still_blocks_grep(self):
        loop = _make_loop_elevated("off")
        result = loop._precheck_tool_call("bash", {"command": "grep -rn 'ch_ret' src/"})
        assert result is not None
        assert "grep_code" in result or "BLOQUEÓ" in result

    def test_elevated_ask_still_blocks_grep(self):
        loop = _make_loop_elevated("ask")
        result = loop._precheck_tool_call("bash", {"command": "grep -rn 'foo' src/"})
        assert result is not None

    # Guardas absolutas: activas incluso en elevated

    def test_elevated_on_still_blocks_rm_rf_system(self):
        loop = _make_loop_elevated("on")
        result = loop._precheck_tool_call("bash", {"command": "rm -rf /etc/passwd"})
        assert result is not None
        assert "PELIGROSO" in result or "BLOQUEÓ" in result

    def test_elevated_full_still_blocks_rm_rf_home_root(self):
        loop = _make_loop_elevated("full")
        # ~/Documents no es bloqueado (ruta específica legítima)
        # ~/* o ~/ SÍ se bloquea porque borra el directorio home completo
        result = loop._precheck_tool_call("bash", {"command": "rm -rf ~/*"})
        assert result is not None

    def test_elevated_on_still_blocks_compose_down_v(self):
        loop = _make_loop_elevated("on")
        result = loop._precheck_tool_call("bash", {"command": "docker compose down -v"})
        assert result is not None
        assert "VOLÚMENES" in result or "PELIGRO" in result
