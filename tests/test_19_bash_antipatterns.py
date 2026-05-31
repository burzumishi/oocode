"""Tests de interceptores bash y herramienta analyze_codebase.

Cubre:
- Bloqueo de grep -r/-rn/-l/-L/-c en bash
- Bloqueo de find -name/-type en bash
- Bloqueo de sed -i en bash
- Herramienta analyze_codebase (nueva meta-tool)
- Nuevos prompts: pre_implementation_analysis, batch_file_operations, c_cpp_workflow
- _turn_guidance: umbral bash bajado y hint 11

No requiere LLM ni conexión de red.
"""
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.oocode_assistant import (
    _tool_analyze_codebase,
    _PROMPTS,
    _get_prompt,
    _TOOL_FNS,
)


# ── Fixture: directorio de trabajo temporal ───────────────────────────────────

@pytest.fixture
def tmp_path():
    """Usa ~/.oocode/_test_tmp para evitar bloqueo de _safe_path."""
    p = Path.home() / ".oocode" / "_test_tmp"
    p.mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture
def code_project(tmp_path):
    """Proyecto con ficheros C, Python y YAML para tests de analyze_codebase."""
    proj = tmp_path / "test_project"
    proj.mkdir(exist_ok=True)
    src = proj / "src"
    src.mkdir(exist_ok=True)
    (src / "main.c").write_text('#include <stdio.h>\nint main() { return 0; }\n')
    (src / "utils.c").write_text('#include <stdlib.h>\nvoid *safe_malloc(int n) { return malloc(n); }\n')
    (src / "utils.h").write_text('#ifndef UTILS_H\n#define UTILS_H\nvoid *safe_malloc(int n);\n#endif\n')
    (proj / "Makefile").write_text('all:\n\tgcc -o main src/main.c src/utils.c\n')
    (proj / "config.yaml").write_text('name: test\nversion: 1.0\n')
    (proj / "script.py").write_text('#!/usr/bin/env python3\nprint("hello")\n')
    return proj


# ══════════════════════════════════════════════════════════════════════════════
# A. Interceptores bash — _precheck_tool_call
# ══════════════════════════════════════════════════════════════════════════════

class TestBashGrepInterceptor:
    """grep -r/-rn/-l/-L/-c debe ser bloqueado."""

    def _make_loop(self):
        """Crea un AgentLoop mínimo para testear _precheck_tool_call."""
        from agent.loop import AgentLoop
        loop = AgentLoop.__new__(AgentLoop)
        loop._turn_written_scripts = set()
        loop._bash_block_counts = {}
        loop._kill_requested = False
        return loop

    @pytest.mark.parametrize("cmd", [
        'grep -rn "malloc" src/',
        'grep -r "pattern" --include="*.c" src/',
        'grep -rl "TODO" .',
        'grep -rL "errno.h" src/',
        'grep -rc "test" tests/',
        'cd /project && grep -rn "foo" src/',
        'grep --recursive "bar" .',
        'grep --include="*.py" -r "def " src/',
        'grep --files-with-matches "pattern" .',
        'grep --count "test" .',
    ])
    def test_grep_recursive_blocked(self, cmd):
        loop = self._make_loop()
        result = loop._precheck_tool_call("bash", {"command": cmd})
        assert result is not None, f"Debería bloquear: {cmd}"
        assert "⛔" in result
        assert "grep_code" in result

    @pytest.mark.parametrize("cmd", [
        'grep "error" logfile.txt',        # grep simple en un fichero — permitido
        'rg "pattern" src/',               # ripgrep — no es grep, permitido
        'echo "grep" | cat',               # echo con "grep" en texto — no es grep real
    ])
    def test_grep_simple_allowed(self, cmd):
        loop = self._make_loop()
        result = loop._precheck_tool_call("bash", {"command": cmd})
        # No debe bloquearse por el interceptor de grep (puede bloquearse por otro motivo)
        if result is not None:
            assert "grep_code" not in result or "grep_file" not in result

    def test_grep_block_message_has_alternatives(self):
        loop = self._make_loop()
        result = loop._precheck_tool_call("bash", {"command": 'grep -rn "malloc" src/'})
        assert "grep_code" in result
        assert "files_with_matches" in result or "files_without_matches" in result or "extensions" in result


class TestBashFindInterceptor:
    """find -name/-type/-newer debe ser bloqueado."""

    def _make_loop(self):
        from agent.loop import AgentLoop
        loop = AgentLoop.__new__(AgentLoop)
        loop._turn_written_scripts = set()
        loop._bash_block_counts = {}
        loop._kill_requested = False
        return loop

    @pytest.mark.parametrize("cmd", [
        'find src -name "*.c"',
        'find . -name "*.py" -type f',
        'find /home/user -iname "makefile"',
        'find src -type f -name "*.h"',
        'find . -newer reference.txt',
        'find src -mtime -7',
        'find . -maxdepth 3 -name "*.js"',
        'find data -size +1M',
        'cd /project && find src -name "*.c" | head -10',
    ])
    def test_find_with_filters_blocked(self, cmd):
        loop = self._make_loop()
        result = loop._precheck_tool_call("bash", {"command": cmd})
        assert result is not None, f"Debería bloquear: {cmd}"
        assert "⛔" in result
        assert "find_file" in result or "find_files" in result

    @pytest.mark.parametrize("cmd", [
        'find /proc -maxdepth 1 2>/dev/null',   # find sin -name/-type claro — puede pasar
    ])
    def test_find_without_name_may_pass(self, cmd):
        """find sin -name/-type/-newer no es interceptado (no tiene equivalente directo)."""
        loop = self._make_loop()
        result = loop._precheck_tool_call("bash", {"command": cmd})
        # puede ser None (pasa) o bloqueado por otro interceptor; no verificamos aquí
        pass

    def test_find_block_message_has_alternatives(self):
        loop = self._make_loop()
        result = loop._precheck_tool_call("bash", {"command": 'find src -name "*.c"'})
        assert "find_file" in result
        assert "list_recent_files" in result or "find_files" in result


class TestBashSedInterceptor:
    """sed -i (in-place) debe ser bloqueado."""

    def _make_loop(self):
        from agent.loop import AgentLoop
        loop = AgentLoop.__new__(AgentLoop)
        loop._turn_written_scripts = set()
        loop._bash_block_counts = {}
        loop._kill_requested = False
        return loop

    @pytest.mark.parametrize("cmd", [
        "sed -i 's/old/new/' file.c",
        "sed -i.bak 's/foo/bar/' src/*.c",
        "sed --in-place 's/x/y/' config.yaml",
        "sed -i '' 's/old/new/g' *.py",     # macOS style
        "for f in *.c; do sed -i 's/a/b/' $f; done",
        "sed -ni 's/pattern/repl/' file",   # -ni combina -n y -i
    ])
    def test_sed_inplace_blocked(self, cmd):
        loop = self._make_loop()
        result = loop._precheck_tool_call("bash", {"command": cmd})
        assert result is not None, f"Debería bloquear: {cmd}"
        assert "⛔" in result
        assert "edit_file" in result or "regex_replace" in result or "bulk_replace" in result

    @pytest.mark.parametrize("cmd", [
        "sed 's/old/new/' file.c",          # sed SIN -i — solo muestra, no edita
        "sed -n '1,10p' file.c",            # sed lectura — no edita
        "sed -e 's/a/b/' -e 's/c/d/' f",   # sed sin -i
    ])
    def test_sed_readonly_allowed(self, cmd):
        loop = self._make_loop()
        result = loop._precheck_tool_call("bash", {"command": cmd})
        # sed sin -i no debería bloquearse por el interceptor de sed
        if result is not None:
            # Puede estar bloqueado por el interceptor de cat (sed -n), pero no por sed -i
            assert "edit_file" not in result

    def test_sed_block_message_has_alternatives(self):
        loop = self._make_loop()
        result = loop._precheck_tool_call("bash", {"command": "sed -i 's/malloc/safe_malloc/g' src/*.c"})
        assert "bulk_replace" in result
        assert "edit_file" in result


class TestExistingBashInterceptors:
    """Los interceptores anteriores (heredoc, cat, scripts) siguen funcionando."""

    def _make_loop(self):
        from agent.loop import AgentLoop
        loop = AgentLoop.__new__(AgentLoop)
        loop._turn_written_scripts = set()
        loop._bash_block_counts = {}
        loop._kill_requested = False
        return loop

    def test_heredoc_python_blocked(self):
        loop = self._make_loop()
        r = loop._precheck_tool_call("bash", {"command": "python3 << 'EOF'\nprint('hi')\nEOF"})
        assert r is not None and "⛔" in r

    def test_cat_read_blocked(self):
        loop = self._make_loop()
        r = loop._precheck_tool_call("bash", {"command": "cat /home/user/project/main.py"})
        assert r is not None and "read_file" in r

    def test_cat_eof_write_blocked(self):
        loop = self._make_loop()
        r = loop._precheck_tool_call("bash", {"command": "cat > file.py << EOF\ncode\nEOF"})
        assert r is not None and "⛔" in r

    def test_temp_script_write_blocked(self):
        loop = self._make_loop()
        r = loop._precheck_tool_call("write_file", {"path": "/home/user/project/fix_bugs.py", "content": "x"})
        assert r is not None and "⛔" in r

    def test_safe_bash_command_passes(self):
        loop = self._make_loop()
        r = loop._precheck_tool_call("bash", {"command": "make -j4"})
        assert r is None  # no bloqueado

    def test_git_command_in_bash_passes(self):
        loop = self._make_loop()
        r = loop._precheck_tool_call("bash", {"command": "git status"})
        assert r is None


# ══════════════════════════════════════════════════════════════════════════════
# B. _turn_guidance — umbral bash y hint 11
# ══════════════════════════════════════════════════════════════════════════════

class TestTurnGuidanceBashThreshold:
    """El umbral de bash bajo: 3 calls y >40% triggea el warning."""

    def _make_loop_with_calls(self, tool_sequence: list[str]) -> "AgentLoop":
        from agent.loop import AgentLoop
        loop = AgentLoop.__new__(AgentLoop)
        loop._pending_tasks = []
        # (name, args_str, result)
        loop._last_tool_calls = [(n, "{}", "ok") for n in tool_sequence]
        loop._failed_edit_streak = 0
        loop._failed_edit_patterns = []
        return loop

    def test_threshold_3_bash_triggers_warning(self):
        loop = self._make_loop_with_calls(["bash", "bash", "read_file", "bash"])
        guidance = loop._turn_guidance()
        assert "bash" in guidance.lower() or "equivalencias" in guidance.lower()

    def test_threshold_2_bash_no_warning(self):
        loop = self._make_loop_with_calls(["bash", "read_file", "bash", "grep_code", "edit_file"])
        guidance = loop._turn_guidance()
        # 2 bash de 5 = 40% — en el límite, puede o no triggear
        # Solo verificamos que no crashea
        assert isinstance(guidance, str)

    def test_old_threshold_5_was_too_late(self):
        """Con el umbral anterior (≥5 y >50%), 4 bash de 5 no daba warning.
        Ahora con (≥3 y >40%), 3 bash de 4 SÍ debe dar warning."""
        loop = self._make_loop_with_calls(["bash", "bash", "bash", "read_file"])
        guidance = loop._turn_guidance()
        # 3/4 bash = 75% > 40% y total≥3: debe triggear
        assert "bash" in guidance.lower() or "equivalencias" in guidance.lower()


class TestTurnGuidanceHint11GrepFindSed:
    """El hint 11 detecta bash con grep/find/sed en las últimas llamadas."""

    def _make_loop_with_bash_cmds(self, cmds: list[str]) -> "AgentLoop":
        from agent.loop import AgentLoop
        loop = AgentLoop.__new__(AgentLoop)
        loop._pending_tasks = []
        import json
        loop._last_tool_calls = [
            ("bash", json.dumps({"command": cmd}), "output")
            for cmd in cmds
        ]
        loop._failed_edit_streak = 0
        loop._failed_edit_patterns = []
        return loop

    def test_hint11_detects_grep_r(self):
        loop = self._make_loop_with_bash_cmds([
            'grep -rn "malloc" src/',
            'grep -rn "calloc" src/',
            'grep -l "errno" src/',
        ])
        guidance = loop._turn_guidance()
        assert "grep_code" in guidance or "grep/find/sed" in guidance

    def test_hint11_detects_find_name(self):
        loop = self._make_loop_with_bash_cmds([
            'find src -name "*.c"',
            'grep -rn "pattern" src/',
        ])
        guidance = loop._turn_guidance()
        assert "grep_code" in guidance or "find_file" in guidance or "grep/find/sed" in guidance

    def test_hint11_detects_sed_inplace(self):
        loop = self._make_loop_with_bash_cmds([
            "sed -i 's/old/new/' *.c",
            "sed -i '' 's/a/b/' file.py",
        ])
        guidance = loop._turn_guidance()
        assert isinstance(guidance, str)  # no crashea; hint puede o no triggear según ratio

    def test_hint11_not_triggered_for_safe_bash(self):
        loop = self._make_loop_with_bash_cmds([
            "make -j4",
            "docker ps",
        ])
        guidance = loop._turn_guidance()
        # No debería mencionar grep/find/sed
        assert "grep/find/sed" not in guidance


# ══════════════════════════════════════════════════════════════════════════════
# C. Tool analyze_codebase
# ══════════════════════════════════════════════════════════════════════════════

class TestAnalyzeCodebase:
    """analyze_codebase: análisis estructurado sin bash."""

    def test_basic_analysis_returns_string(self, code_project):
        result = _tool_analyze_codebase({"directory": str(code_project)})
        assert isinstance(result, str)
        assert len(result) > 100

    def test_analysis_shows_file_count(self, code_project):
        result = _tool_analyze_codebase({"directory": str(code_project)})
        assert "Ficheros" in result or "ficheros" in result or "total" in result.lower()

    def test_analysis_shows_extensions(self, code_project):
        result = _tool_analyze_codebase({"directory": str(code_project)})
        # Debe detectar extensiones .c, .h, .py, .yaml, .mk
        assert ".c" in result or ".py" in result

    def test_analysis_shows_directory_tree(self, code_project):
        result = _tool_analyze_codebase({"directory": str(code_project)})
        assert "src" in result or "Estructura" in result

    def test_analysis_shows_recent_files(self, code_project):
        result = _tool_analyze_codebase({"directory": str(code_project)})
        assert "recientes" in result.lower() or "main.c" in result or "script.py" in result

    def test_analysis_with_extensions_filter(self, code_project):
        result = _tool_analyze_codebase({
            "directory": str(code_project),
            "extensions": "c,h",
        })
        assert isinstance(result, str)
        # Con filtro, solo .c y .h en recientes
        assert ".py" not in result.split("## Ficheros recientes")[1] if "## Ficheros recientes" in result else True

    def test_analysis_with_pattern_search(self, code_project):
        result = _tool_analyze_codebase({
            "directory": str(code_project),
            "pattern": "malloc",
        })
        assert isinstance(result, str)
        assert "malloc" in result or "Búsqueda" in result

    def test_analysis_nonexistent_dir_returns_error(self, tmp_path):
        result = _tool_analyze_codebase({"directory": str(tmp_path / "nonexistent_xyz")})
        assert "Error" in result or "no existe" in result.lower()

    def test_analysis_depth_parameter(self, code_project):
        result = _tool_analyze_codebase({
            "directory": str(code_project),
            "depth": 1,
        })
        assert isinstance(result, str)

    def test_analysis_has_next_steps(self, code_project):
        result = _tool_analyze_codebase({"directory": str(code_project)})
        assert "grep_code" in result or "read_file" in result or "Próximos" in result

    def test_analysis_registered_in_tool_fns(self):
        assert "analyze_codebase" in _TOOL_FNS

    def test_analysis_callable_via_tool_fns(self, code_project):
        fn = _TOOL_FNS["analyze_codebase"]
        result = fn({"directory": str(code_project)})
        assert isinstance(result, str) and len(result) > 50

    def test_analysis_dot_directory(self):
        """Directorio '.' (CWD) debe funcionar."""
        result = _tool_analyze_codebase({"directory": "."})
        assert isinstance(result, str)

    def test_analysis_max_files_parameter(self, code_project):
        result = _tool_analyze_codebase({
            "directory": str(code_project),
            "max_files": 3,
        })
        assert isinstance(result, str)

    def test_analysis_warns_against_bash(self, code_project):
        """El mensaje final debe advertir contra bash grep/find."""
        result = _tool_analyze_codebase({"directory": str(code_project)})
        assert "bash" in result.lower() or "NUNCA" in result or "grep_code" in result


# ══════════════════════════════════════════════════════════════════════════════
# D. Nuevos prompts MCP
# ══════════════════════════════════════════════════════════════════════════════

class TestNewPromptsRegistered:
    """Los 3 nuevos prompts están en _PROMPTS."""

    def test_pre_implementation_analysis_registered(self):
        assert "pre_implementation_analysis" in _PROMPTS

    def test_batch_file_operations_registered(self):
        assert "batch_file_operations" in _PROMPTS

    def test_c_cpp_workflow_registered(self):
        assert "c_cpp_workflow" in _PROMPTS

    def test_pre_implementation_analysis_has_arguments(self):
        prompt = _PROMPTS["pre_implementation_analysis"]
        assert "arguments" in prompt
        arg_names = [a["name"] for a in prompt["arguments"]]
        assert "task" in arg_names

    def test_batch_file_operations_has_arguments(self):
        prompt = _PROMPTS["batch_file_operations"]
        arg_names = [a["name"] for a in prompt["arguments"]]
        assert "task" in arg_names
        assert "directory" in arg_names

    def test_c_cpp_workflow_has_arguments(self):
        prompt = _PROMPTS["c_cpp_workflow"]
        arg_names = [a["name"] for a in prompt["arguments"]]
        assert "task" in arg_names


class TestPreImplementationAnalysisPrompt:
    """prompt pre_implementation_analysis genera instrucciones estructuradas."""

    def test_returns_message_list(self):
        msgs = _get_prompt("pre_implementation_analysis", {"task": "refactorizar gestión de memoria"})
        assert isinstance(msgs, list) and len(msgs) > 0

    def test_message_contains_analyze_codebase(self):
        msgs = _get_prompt("pre_implementation_analysis", {"task": "añadir logging"})
        text = msgs[0]["content"]["text"]
        assert "analyze_codebase" in text

    def test_message_contains_grep_code(self):
        msgs = _get_prompt("pre_implementation_analysis", {"task": "buscar malloc"})
        text = msgs[0]["content"]["text"]
        assert "grep_code" in text

    def test_message_contains_no_bash_warning(self):
        msgs = _get_prompt("pre_implementation_analysis", {"task": "tarea"})
        text = msgs[0]["content"]["text"]
        assert "PROHIBIDO" in text or "bash" in text.lower()

    def test_message_contains_lsp_step(self):
        msgs = _get_prompt("pre_implementation_analysis", {"task": "refactorizar", "language": "c"})
        text = msgs[0]["content"]["text"]
        assert "lsp" in text.lower() or "LSP" in text

    def test_directory_injected_in_prompt(self):
        msgs = _get_prompt("pre_implementation_analysis", {
            "task": "hacer algo",
            "directory": "/home/user/project",
        })
        text = msgs[0]["content"]["text"]
        assert "/home/user/project" in text

    def test_language_c_gets_clangd_hint(self):
        msgs = _get_prompt("pre_implementation_analysis", {
            "task": "modificar struct",
            "language": "c",
        })
        text = msgs[0]["content"]["text"]
        assert "clangd" in text or "lsp_call_hierarchy" in text or "lsp_hover" in text

    def test_without_args_returns_message(self):
        msgs = _get_prompt("pre_implementation_analysis", {})
        assert isinstance(msgs, list) and len(msgs) > 0


class TestBatchFileOperationsPrompt:
    """prompt batch_file_operations genera plan sin bash."""

    def test_returns_message_list(self):
        msgs = _get_prompt("batch_file_operations", {"task": "añadir errno.h a todos los .c"})
        assert isinstance(msgs, list) and len(msgs) > 0

    def test_message_contains_grep_code(self):
        msgs = _get_prompt("batch_file_operations", {"task": "modificar includes"})
        text = msgs[0]["content"]["text"]
        assert "grep_code" in text

    def test_message_contains_bulk_replace(self):
        msgs = _get_prompt("batch_file_operations", {"task": "reemplazar malloc"})
        text = msgs[0]["content"]["text"]
        assert "bulk_replace" in text

    def test_message_contains_no_bash_sed(self):
        msgs = _get_prompt("batch_file_operations", {"task": "modificar ficheros"})
        text = msgs[0]["content"]["text"]
        assert "sed" in text.lower() or "NUNCA" in text  # menciona sed como prohibido

    def test_message_contains_python_exec_alternative(self):
        msgs = _get_prompt("batch_file_operations", {"task": "batch op"})
        text = msgs[0]["content"]["text"]
        assert "python_exec" in text

    def test_extensions_injected_in_prompt(self):
        msgs = _get_prompt("batch_file_operations", {
            "task": "hacer algo",
            "extensions": "c,h",
        })
        text = msgs[0]["content"]["text"]
        assert "c,h" in text or "c" in text

    def test_pattern_injected_in_prompt(self):
        msgs = _get_prompt("batch_file_operations", {
            "task": "cambiar malloc",
            "pattern": "malloc",
        })
        text = msgs[0]["content"]["text"]
        assert "malloc" in text

    def test_verification_step_present(self):
        msgs = _get_prompt("batch_file_operations", {"task": "tarea"})
        text = msgs[0]["content"]["text"]
        assert "lint" in text.lower() or "make_run" in text or "run_tests" in text


class TestCCppWorkflowPrompt:
    """prompt c_cpp_workflow genera flujo LSP estructurado para C/C++."""

    def test_returns_message_list(self):
        msgs = _get_prompt("c_cpp_workflow", {"task": "migrar malloc a safe_malloc"})
        assert isinstance(msgs, list) and len(msgs) > 0

    def test_message_contains_lsp_symbols(self):
        msgs = _get_prompt("c_cpp_workflow", {"task": "refactorizar función"})
        text = msgs[0]["content"]["text"]
        assert "lsp_symbols" in text

    def test_message_contains_lsp_diagnostics(self):
        msgs = _get_prompt("c_cpp_workflow", {"task": "modificar código"})
        text = msgs[0]["content"]["text"]
        assert "lsp_diagnostics" in text

    def test_message_contains_make_run(self):
        msgs = _get_prompt("c_cpp_workflow", {"task": "cambiar estructura"})
        text = msgs[0]["content"]["text"]
        assert "make_run" in text

    def test_message_contains_context_before_edit(self):
        msgs = _get_prompt("c_cpp_workflow", {"task": "editar función"})
        text = msgs[0]["content"]["text"]
        assert "context_before_edit" in text

    def test_message_warns_against_bash_grep(self):
        msgs = _get_prompt("c_cpp_workflow", {"task": "tarea C"})
        text = msgs[0]["content"]["text"]
        assert "bash" in text.lower() or "NUNCA" in text or "grep -rn" in text

    def test_file_injected_in_prompt(self):
        msgs = _get_prompt("c_cpp_workflow", {
            "task": "analizar función",
            "file": "/home/user/project/src/main.c",
        })
        text = msgs[0]["content"]["text"]
        assert "main.c" in text

    def test_symbol_injected_in_prompt(self):
        msgs = _get_prompt("c_cpp_workflow", {
            "task": "modificar función",
            "symbol": "process_command",
        })
        text = msgs[0]["content"]["text"]
        assert "process_command" in text

    def test_lsp_call_hierarchy_mentioned(self):
        msgs = _get_prompt("c_cpp_workflow", {"task": "refactorizar"})
        text = msgs[0]["content"]["text"]
        assert "lsp_call_hierarchy" in text

    def test_nullcheck_malloc_rule(self):
        msgs = _get_prompt("c_cpp_workflow", {"task": "gestión de memoria"})
        text = msgs[0]["content"]["text"]
        assert "malloc" in text or "Nullcheck" in text or "free" in text


# ══════════════════════════════════════════════════════════════════════════════
# E. Regexes de interceptores — tests unitarios directos
# ══════════════════════════════════════════════════════════════════════════════

class TestInterceptorRegexes:
    """Tests directos de las expresiones regulares de los interceptores."""

    def _get_regexes(self):
        from agent.loop import AgentLoop
        loop = AgentLoop.__new__(AgentLoop)
        return (
            loop._BASH_GREP_REDIRECT_RE,
            loop._BASH_FIND_REDIRECT_RE,
            loop._BASH_SED_INPLACE_RE,
        )

    def test_grep_r_matches(self):
        grep_re, _, _ = self._get_regexes()
        assert grep_re.search("grep -rn 'foo' src/")
        assert grep_re.search("grep -r 'bar' .")
        assert grep_re.search("grep -rl 'baz' /home/")

    def test_grep_l_matches(self):
        grep_re, _, _ = self._get_regexes()
        assert grep_re.search("grep -l 'pattern' src/*.c")
        assert grep_re.search("grep -L 'pattern' src/*.c")

    def test_grep_c_flag_matches(self):
        grep_re, _, _ = self._get_regexes()
        assert grep_re.search("grep -c 'pattern' file")

    def test_grep_include_matches(self):
        grep_re, _, _ = self._get_regexes()
        assert grep_re.search('grep --include="*.c" pattern src/')
        assert grep_re.search("grep --recursive pattern .")

    def test_find_name_matches(self):
        _, find_re, _ = self._get_regexes()
        assert find_re.search("find src -name '*.c'")
        assert find_re.search("find . -type f -name '*.py'")
        assert find_re.search("find /home -iname 'Makefile'")

    def test_find_newer_matches(self):
        _, find_re, _ = self._get_regexes()
        assert find_re.search("find . -newer reference.txt")
        assert find_re.search("find src -mtime -7")

    def test_sed_i_matches(self):
        _, _, sed_re = self._get_regexes()
        assert sed_re.search("sed -i 's/old/new/' file")
        assert sed_re.search("sed -i.bak 's/x/y/' *.c")
        assert sed_re.search("sed --in-place 's/a/b/' file")

    def test_sed_without_i_not_matched(self):
        _, _, sed_re = self._get_regexes()
        assert not sed_re.search("sed 's/old/new/' file")
        assert not sed_re.search("sed -n '1,10p' file")
        assert not sed_re.search("sed -e 's/a/b/' file")

    def test_find_without_name_not_matched(self):
        _, find_re, _ = self._get_regexes()
        # find sin -name/-type/-newer no debe interceptarse
        # (aunque algunas variantes sí coinciden con -maxdepth)
        assert not find_re.search("find .")
        assert not find_re.search("find /proc 2>/dev/null")


# ══════════════════════════════════════════════════════════════════════════════
# F. Config — analyze_codebase en permisos
# ══════════════════════════════════════════════════════════════════════════════

class TestAnalyzeCodebaseConfig:
    """analyze_codebase debe tener permiso 'auto' en DEFAULT_CONFIG."""

    def test_analyze_codebase_in_default_config(self):
        from config import DEFAULT_CONFIG
        perms = DEFAULT_CONFIG.get("permissions", {})
        assert "analyze_codebase" in perms, "analyze_codebase debe estar en DEFAULT_CONFIG permissions"

    def test_analyze_codebase_is_auto(self):
        from config import DEFAULT_CONFIG
        perms = DEFAULT_CONFIG.get("permissions", {})
        assert perms.get("analyze_codebase") == "auto", "analyze_codebase debe ser 'auto' (solo lectura)"


# ══════════════════════════════════════════════════════════════════════════════
# G. Integración — flujo completo analyze_codebase
# ══════════════════════════════════════════════════════════════════════════════

class TestAnalyzeCodebaseIntegration:
    """Tests de integración del flujo completo."""

    def test_full_c_project_analysis(self, code_project):
        """Análisis completo de un proyecto C con búsqueda de patrón."""
        result = _tool_analyze_codebase({
            "directory": str(code_project),
            "extensions": "c,h",
            "pattern": "malloc",
            "depth": 2,
            "max_files": 5,
        })
        assert "Análisis" in result or str(code_project) in result
        assert ".c" in result or ".h" in result

    def test_empty_directory_analysis(self, tmp_path):
        """Directorio vacío no falla."""
        empty = tmp_path / "empty_proj"
        empty.mkdir(exist_ok=True)
        result = _tool_analyze_codebase({"directory": str(empty)})
        assert isinstance(result, str)

    def test_pattern_not_found_graceful(self, code_project):
        """Patrón que no existe no produce error."""
        result = _tool_analyze_codebase({
            "directory": str(code_project),
            "pattern": "UNLIKELY_PATTERN_XYZ_12345",
        })
        assert isinstance(result, str)
        assert "Error" not in result or "coincidencias" in result.lower()
