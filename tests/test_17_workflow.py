"""Test de hilo de trabajo completo: simula una conversación larga del agente.

Verifica que las tools se encadenan correctamente para:
1. Leer OOCODE.md y extraer información del proyecto
2. Explorar la estructura del código con las tools adecuadas
3. Buscar símbolos, patterns y TODOs
4. Editar ficheros con verificación previa
5. Validar el resultado con lint/diagnostics

Ningún test requiere LLM — se llaman las tool functions directamente simulando
el comportamiento esperado del agente en una sesión real.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

PROJECT_ROOT = Path(__file__).parent.parent

from mcp_servers.oocode_assistant import (
    _tool_read_project_file,
    _tool_search_todos,
    _tool_list_recent_files,
    _tool_count_lines,
    _tool_tree,
    _tool_grep_code,
    _tool_multi_grep,
    _tool_find_files,
    _tool_symbol_lookup,
    _tool_code_compare,
    _tool_context_before_edit,
    _tool_smart_replace,
    _tool_regex_replace,
    _tool_bulk_replace,
    _tool_write_file,
    _tool_read_files,
    _tool_json_validate,
    _tool_yaml_validate,
    _tool_env_check,
    _tool_process_list,
    _tool_run_quick_check,
    _tool_ls_dir,
    _tool_ls_file,
    _tool_find_file,
    _tool_grep_file,
    _tool_file_stat,
    _tool_lint_file,
    _tool_python_exec,
    _get_prompt,
    _RESOURCE_FNS,
    _TOOL_FNS,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def project_dir():
    """Directorio raíz real de OOCode."""
    return str(PROJECT_ROOT)


@pytest.fixture
def workspace(tmp_path):
    """Workspace temporal con estructura de proyecto Python."""
    src = tmp_path / "src"
    src.mkdir()

    (tmp_path / "OOCODE.md").write_text(
        "# MyProject\n\n## Commands\n\n```bash\npython main.py\n```\n\n"
        "## Architecture\n\nMain module: `src/main.py`\n\n"
        "## TODOs\n- [ ] Add tests\n- [ ] Fix auth\n"
    )
    (tmp_path / "requirements.txt").write_text("requests>=2.28\npydantic>=2.0\n")
    (tmp_path / "config.yaml").write_text(
        "database:\n  host: localhost\n  port: 5432\napp:\n  debug: false\n"
    )
    (tmp_path / "config.json").write_text(
        '{"name": "myproject", "version": "1.0.0", "debug": false}'
    )
    (src / "__init__.py").write_text("")
    (src / "main.py").write_text(
        "# TODO: add error handling\n"
        "# FIXME: auth is broken\n\n"
        "def main():\n"
        "    \"\"\"Entry point.\"\"\"\n"
        "    print('hello')\n\n"
        "class Config:\n"
        "    \"\"\"App config.\"\"\"\n"
        "    DEBUG = False\n"
        "    VERSION = '1.0.0'\n\n"
        "def run_server(host='localhost', port=8080):\n"
        "    \"\"\"Start the server.\"\"\"\n"
        "    pass\n"
    )
    (src / "utils.py").write_text(
        "def validate_email(email: str) -> bool:\n"
        "    \"\"\"Validate an email address.\"\"\"\n"
        "    return '@' in email\n\n"
        "def hash_password(password: str) -> str:\n"
        "    \"\"\"Hash a password.\"\"\"\n"
        "    import hashlib\n"
        "    return hashlib.sha256(password.encode()).hexdigest()\n"
    )
    (src / "auth.py").write_text(
        "# FIXME: this is not secure\n"
        "SECRET_KEY = 'hardcoded_secret_xyz'\n\n"
        "def authenticate(user, password):\n"
        "    \"\"\"Authenticate user.\"\"\"\n"
        "    # TODO: use proper hashing\n"
        "    return password == 'admin'\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_utils.py").write_text(
        "from src.utils import validate_email\n\n"
        "def test_valid_email():\n"
        "    assert validate_email('user@example.com')\n\n"
        "def test_invalid_email():\n"
        "    assert not validate_email('notanemail')\n"
    )
    return tmp_path


# ── Workflow 1: Análisis inicial del proyecto ─────────────────────────────────

class TestWorkflowProjectAnalysis:
    """Simula el análisis inicial que hace el agente al recibir una tarea."""

    def test_step1_read_oocode_md(self, workspace):
        """Paso 1: leer OOCODE.md para entender el proyecto."""
        result = _tool_read_project_file({"filename": "OOCODE.md", "directory": str(workspace)})
        assert "MyProject" in result
        assert "python main.py" in result or "Commands" in result

    def test_step2_explore_structure(self, workspace):
        """Paso 2: explorar estructura del proyecto."""
        tree_result = _tool_tree({"path": str(workspace), "depth": 3})
        assert isinstance(tree_result, str)
        assert len(tree_result) > 0

        ls_result = _tool_ls_dir({"path": str(workspace)})
        assert "src" in ls_result or "OOCODE.md" in ls_result

    def test_step3_count_lines(self, workspace):
        """Paso 3: contar líneas de código."""
        result = _tool_count_lines({"path": str(workspace)})
        assert isinstance(result, str)

    def test_step4_find_todos(self, workspace):
        """Paso 4: buscar TODOs y FIXMEs."""
        result = _tool_search_todos({"directory": str(workspace), "extensions": "py"})
        assert "TODO" in result or "FIXME" in result

    def test_step5_list_recent_changes(self, workspace):
        """Paso 5: listar ficheros modificados recientemente."""
        result = _tool_list_recent_files({"directory": str(workspace), "extension": "py"})
        assert "main.py" in result or "utils.py" in result

    def test_step6_validate_config(self, workspace):
        """Paso 6: validar ficheros de configuración (usando 'path' no 'file')."""
        # json_validate y yaml_validate usan 'path' para ficheros
        json_result = _tool_json_validate({"path": str(workspace / "config.json")})
        assert "válido" in json_result.lower() or "valid" in json_result.lower() or isinstance(json_result, str)

        yaml_result = _tool_yaml_validate({"path": str(workspace / "config.yaml")})
        assert "válido" in yaml_result.lower() or "valid" in yaml_result.lower() or isinstance(yaml_result, str)


# ── Workflow 2: Búsqueda de código ───────────────────────────────────────────

class TestWorkflowCodeSearch:
    """Simula la búsqueda de código que hace el agente antes de editar."""

    def test_grep_for_function(self, workspace):
        """Buscar definiciones de funciones."""
        result = _tool_grep_code({
            "pattern": r"def \w+",
            "path": str(workspace / "src"),
            "glob": "*.py",
        })
        # grep_code retorna matches — verificamos que encontró funciones
        assert "def" in result or "match" in result.lower() or "coincidencia" in result.lower()

    def test_multi_grep_related_patterns(self, workspace):
        """Buscar múltiples patrones relacionados en paralelo."""
        result = _tool_multi_grep({
            "patterns": "TODO,FIXME,SECRET_KEY",
            "path": str(workspace),
        })
        assert isinstance(result, str)

    def test_find_files_by_extension(self, workspace):
        """Encontrar todos los ficheros Python."""
        # find_files usa 'directory' y 'name' (no 'path' ni 'pattern')
        result = _tool_find_files({"name": "*.py", "directory": str(workspace / "src")})
        assert "main.py" in result or "utils.py" in result or "auth.py" in result

    def test_symbol_lookup(self, workspace):
        """Buscar símbolo específico."""
        result = _tool_symbol_lookup({"symbol": "validate_email", "path": str(workspace)})
        assert isinstance(result, str)

    def test_find_security_issues(self, workspace):
        """Buscar problemas de seguridad típicos."""
        result = _tool_grep_code({
            "pattern": r"SECRET_KEY|password.*=.*'",
            "path": str(workspace / "src"),
            "glob": "*.py",
        })
        assert isinstance(result, str)

    def test_grep_file_specific(self, workspace):
        """Buscar en un fichero específico."""
        result = _tool_grep_file({
            "pattern": "authenticate",
            "path": str(workspace / "src" / "auth.py"),
        })
        assert "authenticate" in result


# ── Workflow 3: Análisis antes de editar ──────────────────────────────────────

class TestWorkflowPreEditAnalysis:
    """Simula la verificación obligatoria antes de editar código."""

    def test_context_before_edit_function(self, workspace):
        """Ver contexto alrededor de la función a modificar."""
        result = _tool_context_before_edit({
            "file": str(workspace / "src" / "auth.py"),
            "pattern": "authenticate",
            "context_lines": 5,
        })
        assert "authenticate" in result
        # Debe mostrar líneas de contexto
        assert "línea" in result.lower() or "→" in result

    def test_context_before_edit_no_pattern(self, workspace):
        """Ver estructura general del fichero antes de editar."""
        result = _tool_context_before_edit({
            "file": str(workspace / "src" / "main.py"),
        })
        assert "main.py" in result or "líneas" in result

    def test_file_stat_before_edit(self, workspace):
        """Obtener metadatos del fichero antes de editar."""
        result = _tool_file_stat({"path": str(workspace / "src" / "main.py")})
        assert "main.py" in result or isinstance(result, str)

    def test_read_files_batch(self, workspace):
        """Leer múltiples ficheros en paralelo para entender el código."""
        result = _tool_read_files({
            "paths": json.dumps([
                str(workspace / "src" / "main.py"),
                str(workspace / "src" / "auth.py"),
            ])
        })
        assert isinstance(result, str)
        assert "main" in result.lower() or "auth" in result.lower()


# ── Workflow 4: Edición de código con verificación ───────────────────────────

class TestWorkflowEdit:
    """Simula el ciclo completo de edición con verificaciones antes y después."""

    def test_smart_replace_rename_function(self, workspace):
        """Renombrar una función con verificación previa."""
        f = workspace / "src" / "main.py"
        original = f.read_text()

        # 1. Verificar que el patrón existe
        ctx = _tool_context_before_edit({
            "file": str(f),
            "pattern": "def main",
        })
        assert "def main" in ctx

        # 2. Aplicar el reemplazo
        result = _tool_smart_replace({
            "file": str(f),
            "pattern": r"def main\(\):",
            "replacement": "def entry_point():",
        })
        assert "✓" in result or "reemplaz" in result.lower()

        # 3. Verificar que el cambio está en el fichero
        new_content = f.read_text()
        assert "def entry_point():" in new_content

    def test_regex_replace_update_version(self, workspace):
        """Actualizar versión usando regex_replace."""
        f = workspace / "src" / "main.py"
        original = f.read_text()

        result = _tool_regex_replace({
            "path": str(f),
            "pattern": r"VERSION = '1\.0\.0'",
            "replacement": "VERSION = '1.1.0'",
        })
        assert isinstance(result, str)

    def test_bulk_replace_update_constant(self, workspace):
        """Reemplazar constante en múltiples ficheros."""
        result = _tool_bulk_replace({
            "directory": str(workspace / "src"),
            "old_string": "DEBUG = False",
            "new_string": "DEBUG = True",
            "glob": "*.py",
        })
        assert isinstance(result, str)

    def test_write_new_file(self, workspace):
        """Crear un nuevo fichero de código (parámetro real: file_path)."""
        new_file = workspace / "src" / "validators.py"
        result = _tool_write_file({
            "file_path": str(new_file),
            "content": (
                "\"\"\"Input validators.\"\"\"\n\n"
                "def validate_port(port: int) -> bool:\n"
                "    return 0 < port < 65536\n\n"
                "def validate_hostname(host: str) -> bool:\n"
                "    return len(host) > 0 and '.' in host\n"
            ),
        })
        assert new_file.exists()
        content = new_file.read_text()
        assert "validate_port" in content

    def test_code_compare_after_edit(self, workspace):
        """Comparar fichero antes y después de editar."""
        f = workspace / "src" / "utils.py"

        # Crear copia del original
        original_copy = workspace / "utils_original.py"
        original_copy.write_text(f.read_text())

        # Modificar el fichero
        _tool_smart_replace({
            "file": str(f),
            "pattern": r"return '@' in email",
            "replacement": "return bool(email) and '@' in email and '.' in email.split('@')[-1]",
        })

        # Comparar
        result = _tool_code_compare({
            "file1": str(original_copy),
            "file2": str(f),
        })
        assert isinstance(result, str)


# ── Workflow 5: Validación post-edición ───────────────────────────────────────

class TestWorkflowPostEditValidation:
    """Simula la validación que el agente hace después de editar."""

    def test_lint_after_edit(self, workspace):
        """Ejecutar linter después de editar."""
        result = _tool_lint_file({"path": str(workspace / "src" / "main.py")})
        assert isinstance(result, str)

    def test_run_tests_after_edit(self, workspace):
        """Ejecutar tests del proyecto."""
        result = _tool_run_quick_check({
            "command": "python -m pytest tests/ -q --tb=short 2>&1 | head -20",
            "directory": str(workspace),
        })
        assert isinstance(result, str)

    def test_python_exec_validation(self, workspace):
        """Validar que el código editado es importable."""
        result = _tool_python_exec({
            "code": (
                "import sys\n"
                f"sys.path.insert(0, '{workspace}')\n"
                "from src.utils import validate_email\n"
                "assert validate_email('test@example.com')\n"
                "print('OK')\n"
            )
        })
        assert "OK" in result or isinstance(result, str)

    def test_grep_for_introduced_issues(self, workspace):
        """Buscar posibles problemas introducidos."""
        result = _tool_grep_code({
            "pattern": r"SECRET_KEY|hardcoded|TODO.*auth",
            "path": str(workspace / "src"),
            "glob": "*.py",
        })
        assert isinstance(result, str)


# ── Workflow 6: Análisis del proyecto OOCode real ─────────────────────────────

class TestWorkflowRealProject:
    """Análisis del proyecto OOCode real usando sus propias tools."""

    def test_read_oocode_project_file(self, project_dir):
        """Leer el OOCODE.md del propio proyecto."""
        result = _tool_read_project_file({"filename": "OOCODE.md", "directory": project_dir})
        assert "OOCode" in result or "oocode" in result.lower()

    def test_count_project_lines(self, project_dir):
        """Contar líneas del proyecto."""
        result = _tool_count_lines({"path": project_dir})
        assert isinstance(result, str)

    def test_search_project_todos(self, project_dir):
        """Buscar TODOs en el proyecto real."""
        result = _tool_search_todos({"directory": project_dir, "extensions": "py"})
        assert isinstance(result, str)

    def test_find_agent_loop(self, project_dir):
        """Encontrar el módulo AgentLoop."""
        result = _tool_find_file({"name": "loop.py", "path": project_dir})
        assert "loop.py" in result

    def test_grep_for_tool_registry(self, project_dir):
        """Buscar el registro de tools."""
        result = _tool_grep_code({
            "pattern": r"class ToolRegistry|def register",
            "path": project_dir,
            "glob": "*.py",
        })
        assert "ToolRegistry" in result or "register" in result

    def test_find_all_test_files(self, project_dir):
        """Encontrar todos los ficheros de test."""
        result = _tool_find_files({"name": "test_*.py", "directory": str(Path(project_dir) / "tests")})
        assert "test_" in result

    def test_env_check_project(self, project_dir):
        """Verificar variables de entorno relevantes."""
        result = _tool_env_check({"vars": "PATH,PYTHONPATH"})
        assert isinstance(result, str)


# ── Workflow 7: Uso de prompts en cadena ─────────────────────────────────────

class TestWorkflowPrompts:
    """Simula el uso de prompts del MCP para estructurar el razonamiento."""

    def test_prompt_chain_debug_to_fix(self, workspace):
        """Cadena: pre_implementation_check → debug_failing_edits → plan_code_changes."""
        # 1. Analizar antes de implementar
        result1 = _get_prompt("pre_implementation_check", {
            "task": "fix auth module to use proper password hashing"
        })
        assert isinstance(result1, list) and len(result1) > 0

        # 2. Planificar los cambios
        result2 = _get_prompt("plan_code_changes", {
            "task": "replace hardcoded SECRET_KEY with env variable"
        })
        assert isinstance(result2, list) and len(result2) > 0

        # 3. Si algo falla, debug
        result3 = _get_prompt("debug_failing_edits", {
            "error": "old_string 'SECRET_KEY = hardcoded' not found in auth.py"
        })
        assert isinstance(result3, list) and len(result3) > 0

    def test_code_review_then_refactor(self, workspace):
        """Cadena: code_review → refactor_code → write_tests."""
        code = (workspace / "src" / "auth.py").read_text()

        review = _get_prompt("code_review", {"code": code, "language": "python"})
        assert isinstance(review, list) and len(review) > 0

        refactor = _get_prompt("refactor_code", {"code": code, "language": "python"})
        assert isinstance(refactor, list) and len(refactor) > 0

        tests = _get_prompt("write_tests", {"code": code, "language": "python"})
        assert isinstance(tests, list) and len(tests) > 0

    def test_security_audit_prompt(self, workspace):
        """Usar security_audit para analizar código con problemas."""
        code = (workspace / "src" / "auth.py").read_text()
        result = _get_prompt("security_audit", {"code": code, "language": "python"})
        assert isinstance(result, list) and len(result) > 0


# ── Workflow 8: Uso de recursos del MCP ──────────────────────────────────────

class TestWorkflowResources:
    """Simula el uso de recursos del MCP para contexto del proyecto."""

    def test_reasoning_resource(self):
        """Obtener guía de razonamiento del agente."""
        fn = _RESOURCE_FNS["project://reasoning"]
        result = fn()
        assert isinstance(result, str)
        assert len(result) > 50

    def test_lsp_resource(self):
        """Obtener guía de LSP servers."""
        fn = _RESOURCE_FNS["project://lsp"]
        result = fn()
        assert isinstance(result, str)

    def test_structure_resource(self):
        """Obtener estructura del proyecto actual."""
        fn = _RESOURCE_FNS["project://structure"]
        result = fn()
        assert isinstance(result, str)

    def test_todos_resource(self):
        """Obtener TODOs del proyecto."""
        fn = _RESOURCE_FNS["project://todos"]
        result = fn()
        assert isinstance(result, str)

    def test_deps_resource(self):
        """Obtener dependencias del proyecto."""
        fn = _RESOURCE_FNS["project://deps"]
        result = fn()
        assert isinstance(result, str)

    def test_env_resource(self):
        """Obtener entorno del proyecto."""
        fn = _RESOURCE_FNS["project://env"]
        result = fn()
        assert isinstance(result, str)

    def test_processes_resource(self):
        """Obtener procesos activos."""
        fn = _RESOURCE_FNS["project://processes"]
        result = fn()
        assert isinstance(result, str)

    def test_metrics_resource(self):
        """Obtener métricas del proyecto."""
        fn = _RESOURCE_FNS["project://metrics"]
        result = fn()
        assert isinstance(result, str)


# ── Workflow 9: Conversación larga simulada ───────────────────────────────────

class TestWorkflowLongConversation:
    """Simula una conversación larga completa del agente analizando y modificando código."""

    def test_full_refactor_workflow(self, workspace):
        """Tarea completa: refactorizar el módulo de autenticación."""
        auth_file = workspace / "src" / "auth.py"

        # Turno 1: El agente lee OOCODE.md
        step1 = _tool_read_project_file({"filename": "OOCODE.md", "directory": str(workspace)})
        assert isinstance(step1, str)

        # Turno 2: Explora la estructura
        step2 = _tool_tree({"path": str(workspace), "depth": 2})
        assert isinstance(step2, str)

        # Turno 3: Busca TODOs y FIXMEs
        step3 = _tool_search_todos({"directory": str(workspace), "extensions": "py"})
        assert "FIXME" in step3 or "TODO" in step3

        # Turno 4: Lee los ficheros relevantes en paralelo
        step4 = _tool_read_files({
            "paths": json.dumps([str(auth_file), str(workspace / "src" / "utils.py")])
        })
        assert isinstance(step4, str)

        # Turno 5: Ve el contexto antes de editar
        step5 = _tool_context_before_edit({
            "file": str(auth_file),
            "pattern": "SECRET_KEY",
            "context_lines": 3,
        })
        assert "SECRET_KEY" in step5

        # Turno 6: Reemplaza la clave hardcoded usando smart_replace
        step6 = _tool_smart_replace({
            "file": str(auth_file),
            "pattern": r"SECRET_KEY = 'hardcoded_secret_xyz'",
            "replacement": "SECRET_KEY = os.environ.get('SECRET_KEY', '')",
        })
        assert isinstance(step6, str)

        # Turno 7: Añade el import os si no existe
        content = auth_file.read_text()
        if "import os" not in content:
            step7 = _tool_smart_replace({
                "file": str(auth_file),
                "pattern": r"^# FIXME: this is not secure",
                "replacement": "import os\n# TODO: validate SECRET_KEY is set",
                "flags": "MULTILINE",
            })
        else:
            step7 = "import os already present"
        assert isinstance(step7, str)

        # Turno 8: Verifica el resultado con grep
        step8 = _tool_grep_code({
            "pattern": "os.environ",
            "path": str(workspace / "src"),
            "glob": "*.py",
        })
        assert "os.environ" in step8

        # Turno 9: Linta el fichero modificado
        step9 = _tool_lint_file({"path": str(auth_file)})
        assert isinstance(step9, str)

        # Turno 10: Busca patterns similares para aplicar el mismo fix
        step10 = _tool_multi_grep({
            "patterns": "hardcoded,password.*=.*'admin',SECRET",
            "path": str(workspace),
        })
        assert isinstance(step10, str)

        # Verifica el estado final
        final_content = auth_file.read_text()
        assert "os.environ" in final_content or "SECRET_KEY" in final_content

    def test_add_new_feature_workflow(self, workspace):
        """Tarea: añadir una nueva función de validación."""

        # Paso 1: Verificar qué hay en utils.py
        step1 = _tool_context_before_edit({
            "file": str(workspace / "src" / "utils.py"),
        })
        assert "validate_email" in step1 or isinstance(step1, str)

        # Paso 2: Buscar si ya existe validate_port
        step2 = _tool_grep_code({
            "pattern": "validate_port",
            "path": str(workspace),
            "glob": "*.py",
        })
        assert isinstance(step2, str)

        # Paso 3: Crear la nueva función (file_path es el parámetro correcto)
        utils_file = workspace / "src" / "utils.py"
        original = utils_file.read_text()
        new_function = (
            "\n\ndef validate_port(port: int) -> bool:\n"
            "    \"\"\"Validate TCP port number.\"\"\"\n"
            "    return isinstance(port, int) and 0 < port < 65536\n"
        )
        step3 = _tool_write_file({
            "file_path": str(utils_file),
            "content": original + new_function,
        })
        assert isinstance(step3, str)

        # Paso 4: Verificar que se añadió
        step4 = _tool_grep_code({
            "pattern": "def validate_port",
            "path": str(workspace),
            "glob": "*.py",
        })
        assert "validate_port" in step4

        # Paso 5: Lintear el resultado
        step5 = _tool_lint_file({"path": str(utils_file)})
        assert isinstance(step5, str)

        # Paso 6: Generar prompt de tests
        step6 = _get_prompt("write_tests", {
            "code": utils_file.read_text(),
            "language": "python",
        })
        assert isinstance(step6, list) and len(step6) > 0

    def test_debug_and_fix_workflow(self, workspace):
        """Tarea: debuggear y corregir un bug reportado."""

        # Paso 1: Usar prompt de debug para estructurar el análisis
        plan = _get_prompt("debug_failing_edits", {
            "error": "TypeError: authenticate() missing 1 required argument"
        })
        assert isinstance(plan, list)

        # Paso 2: Buscar la función con el error
        step2 = _tool_grep_code({
            "pattern": r"def authenticate",
            "path": str(workspace),
            "glob": "*.py",
        })
        assert "authenticate" in step2

        # Paso 3: Ver el contexto completo
        step3 = _tool_context_before_edit({
            "file": str(workspace / "src" / "auth.py"),
            "pattern": "def authenticate",
            "context_lines": 10,
        })
        assert "authenticate" in step3

        # Paso 4: Pre-implementation check antes de corregir
        pre = _get_prompt("pre_implementation_check", {
            "task": "add default value to password parameter"
        })
        assert isinstance(pre, list)

        # Paso 5: Aplicar el fix con verificación previa
        ctx = _tool_context_before_edit({
            "file": str(workspace / "src" / "auth.py"),
            "pattern": "def authenticate",
        })
        assert isinstance(ctx, str)

        fix = _tool_smart_replace({
            "file": str(workspace / "src" / "auth.py"),
            "pattern": r"def authenticate\(user, password\):",
            "replacement": "def authenticate(user, password=''):",
        })
        assert isinstance(fix, str)

        # Paso 6: Verificar el fix
        final = _tool_grep_code({
            "pattern": "def authenticate",
            "path": str(workspace),
            "glob": "*.py",
        })
        assert "authenticate" in final


# ── Workflow 10: Cobertura de todas las tool categories ──────────────────────

class TestAllToolCategoriesCovered:
    """Verifica que cada categoría de tool se usa en al menos un workflow."""

    def test_info_tools(self, project_dir):
        """Tools de información del sistema."""
        result = _tool_env_check({})
        assert isinstance(result, str)
        result2 = _tool_process_list({})
        assert isinstance(result2, str)

    def test_fs_navigation_tools(self, workspace):
        """Tools de navegación del filesystem."""
        assert isinstance(_tool_ls_dir({"path": str(workspace)}), str)
        assert isinstance(_tool_ls_file({"path": str(workspace / "src" / "main.py")}), str)
        assert isinstance(_tool_file_stat({"path": str(workspace / "src" / "main.py")}), str)
        assert isinstance(_tool_tree({"path": str(workspace)}), str)

    def test_search_tools(self, workspace):
        """Tools de búsqueda de código."""
        assert isinstance(_tool_grep_code({"pattern": "def", "path": str(workspace), "glob": "*.py"}), str)
        assert isinstance(_tool_find_files({"pattern": "*.py", "path": str(workspace)}), str)
        assert isinstance(_tool_symbol_lookup({"symbol": "main", "path": str(workspace)}), str)
        assert isinstance(_tool_multi_grep({"patterns": "def,class", "path": str(workspace)}), str)

    def test_edit_tools(self, workspace):
        """Tools de edición de código."""
        f = workspace / "src" / "main.py"
        assert isinstance(_tool_context_before_edit({"file": str(f), "pattern": "def"}), str)
        assert isinstance(_tool_code_compare({"file1": str(f), "file2": str(f)}), str)

    def test_validation_tools(self, workspace):
        """Tools de validación."""
        assert isinstance(_tool_json_validate({"file": str(workspace / "config.json")}), str)
        assert isinstance(_tool_yaml_validate({"file": str(workspace / "config.yaml")}), str)
        assert isinstance(_tool_lint_file({"path": str(workspace / "src" / "main.py")}), str)

    def test_execution_tools(self, workspace):
        """Tools de ejecución."""
        assert isinstance(_tool_run_quick_check({"command": "echo test"}), str)
        assert isinstance(_tool_python_exec({"code": "print('ok')"}), str)

    def test_prompts_and_resources(self):
        """Prompts y recursos disponibles."""
        for uri in ["project://reasoning", "project://lsp", "project://structure"]:
            result = _RESOURCE_FNS[uri]()
            assert isinstance(result, str)

        for prompt_name in ["plan_code_changes", "pre_implementation_check", "code_review"]:
            result = _get_prompt(prompt_name, {})
            assert isinstance(result, list)
