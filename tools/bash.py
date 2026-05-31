import os
import re
import shutil
import signal
import subprocess
import sys

_DEFAULT_MAX_OUTPUT_CHARS = 20_000
_DEFAULT_TIMEOUT = 60   # 60s por defecto; el modelo puede pasar un timeout mayor

# nice disponible en Linux/macOS — reduce prioridad de CPU para no bloquear la TUI
_NICE_CMD = shutil.which("nice") if sys.platform != "win32" else None

# Patrones que indican uso de bash cuando existe una tool especializada mejor
_BASH_ANTIPATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bgrep\s+(-[a-zA-Z]*r[a-zA-Z]*|-[a-zA-Z]*n[a-zA-Z]*|--recursive)', re.I),
     "Usa grep_code en lugar de 'bash grep -rn/-r/-n'. grep_code es más rápido, soporta regex y no requiere cd previo."),
    (re.compile(r'&&\s*grep\s+', re.I),
     "Usa grep_code(directory=...) en lugar de 'cd ... && grep ...' — no necesitas cd, pasa directory= directamente."),
    (re.compile(r'\bgrep\s+-[a-zA-Z0-9]*[lL]\b', re.I),
     "Usa grep_code(files_with_matches=true) o grep_code(files_without_matches=true) en lugar de 'bash grep -l/-L'."),
    (re.compile(r'\bgrep\s+-[a-zA-Z0-9]*c\b', re.I),
     "Usa grep_code(count_only=true) en lugar de 'bash grep -c' para contar coincidencias por fichero."),
    (re.compile(r'\bgrep\s+-[ABCabc]\d*\b', re.I),
     "Usa grep_code con context_lines=N en lugar de 'bash grep -A/-B/-C'."),
    (re.compile(r'\bgrep\s+-[a-zA-Z]*E\b', re.I),
     "Usa grep_code en lugar de 'bash grep -E' — soporta regex extendido directamente."),
    (re.compile(r'\bfind\s+\S+\s+-name\b', re.I),
     "Usa find_file o find_files en lugar de 'bash find -name' — más rápido y con filtros por extensión/tamaño."),
    (re.compile(r'\bfind\s+\S+\s+-type\s+[fd]\b', re.I),
     "Usa find_file (ficheros) o find_dir (directorios) en lugar de 'bash find -type'."),
    (re.compile(r'\bls\s+-la?\b', re.I),
     "Usa ls_dir en lugar de 'bash ls -la' — devuelve JSON estructurado con permisos, tamaño y fecha."),
    (re.compile(r'\bwc\s+-l\b', re.I),
     "Usa file_stat en lugar de 'bash wc -l' — devuelve líneas, bytes y metadatos en una sola llamada."),
    (re.compile(r'\bsed\s+-i\b', re.I),
     "PROHIBIDO: usa edit_file, regex_replace o bulk_replace en lugar de 'bash sed -i' para modificar ficheros."),
    (re.compile(r'python3?\s+<<\s*[\'"]EOF', re.I),
     "PROHIBIDO: usa python_exec en lugar de heredocs 'python3 << EOF' — es más limpio y seguro."),
    (re.compile(r'\bcat\s+>\s+\S+.*<<', re.I),
     "Usa write_file en lugar de 'cat > fichero << EOF' para crear ficheros."),
    (re.compile(r'\bawk\s+', re.I),
     "Considera regex_replace o python_exec en lugar de 'bash awk' para transformar texto."),
    (re.compile(r'\bsed\s+-n\s+[\'"]?\d+', re.I),
     "Usa read_file con offset= y limit= en lugar de 'bash sed -n N,Mp file' para leer rangos de líneas."),
    (re.compile(r'\bhead\s+-\d+\b|\bhead\s+-n\s+\d+', re.I),
     "Usa read_file con limit= en lugar de 'bash head -N' para leer las primeras líneas."),
    (re.compile(r'\btail\s+-\d+\b|\btail\s+-n\s+\d+', re.I),
     "Usa read_file con offset= para leer el final de un fichero en lugar de 'bash tail -N'."),
    (re.compile(r'python3?\s+-c\s+[\'"]', re.I),
     "Usa python_exec en lugar de 'bash python3 -c \"...\"' — soporta código multilínea limpio."),
    # Gestión de paquetes — tools dedicadas
    (re.compile(r'\bpip3?\s+(?:install|uninstall|show|list|freeze)\b', re.I),
     "Usa pip_tool(action='install', packages=[...]) en lugar de 'bash pip install' — devuelve JSON estructurado."),
    (re.compile(r'\bnpm\s+(?:install|i|ci|uninstall|run|list|audit|outdated)\b', re.I),
     "Usa npm_tool(action='install', packages=[...]) en lugar de 'bash npm' — soporta directory= y devuelve JSON."),
    # Build — make_run tiene timeout, jobs y workdir
    (re.compile(r'^\s*make(?:\s+-j\d+)?(?:\s+\w[\w_-]*)?\s*$', re.I),
     "Usa make_run(target='...', jobs=N, directory='...') en lugar de 'bash make' — soporta timeout y workdir."),
    # Control de versiones — git_* tools devuelven JSON estructurado
    (re.compile(r'\bgit\s+(?:status|diff|add|commit|log|branch|stash|push|pull|clone|checkout|reset|merge)\b', re.I),
     "Usa git_status/git_diff/git_add/git_commit/git_log/git_branch/git_stash en lugar de 'bash git'. Devuelven JSON estructurado."),
    # Docker — docker_ps/docker_logs/docker_exec
    (re.compile(r'\bdocker\s+(?:ps|logs|exec|build|run|stop|rm|images|pull)\b', re.I),
     "Usa docker_ps/docker_logs/docker_exec en lugar de 'bash docker'. Devuelven JSON estructurado."),
    # Debugging — tools dedicadas (strace_run, gdb_run, valgrind_run)
    (re.compile(r'\bstrace\s+', re.I),
     "Usa strace_run(command='...', syscalls='...') en lugar de 'bash strace' — filtro por syscalls, salida estructurada."),
    (re.compile(r'\bgdb\s+', re.I),
     "Usa gdb_run(binary='...', commands='...') en lugar de 'bash gdb' — batch mode, sin interactividad."),
    (re.compile(r'\bvalgrind\s+', re.I),
     "Usa valgrind_run(binary='...', tool='memcheck') en lugar de 'bash valgrind' — parse automático de errores."),
    # Lectura de ficheros con cat — read_file soporta offset/limit
    (re.compile(r'^\s*cat\s+(?!>)(\S+\.(?:py|js|ts|c|h|cpp|hpp|rs|go|md|txt|json|yaml|yml|sh|toml|cfg|ini|env|xml|html|css|rb|php|java|kt|swift))\s*$', re.I),
     "Usa read_file(path='...') en lugar de 'bash cat file' — más rápido y soporta offset/limit para ficheros grandes."),
    # Comparar ficheros — diff_files
    (re.compile(r'\bdiff\s+(?:-[a-zA-Z]*\s+)*\S+\s+\S+', re.I),
     "Usa diff_files(file_a='...', file_b='...') en lugar de 'bash diff' — devuelve diff unificado estructurado."),
    # Tests Python — run_tests
    (re.compile(r'python3?\s+-m\s+pytest\b|\bpytest\b', re.I),
     "Usa run_tests(path='...') en lugar de 'bash pytest/python3 -m pytest' — soporta filtros, coverage y workdir."),
    # Type checking — mypy_check
    (re.compile(r'python3?\s+-m\s+mypy\b|\bmypy\s+', re.I),
     "Usa mypy_check(path='...') en lugar de 'bash mypy/python3 -m mypy' — devuelve errores estructurados."),
    # Linting — lint_file / lint_project (ruff, flake8, pylint)
    (re.compile(r'python3?\s+-m\s+(?:ruff|flake8|pylint)\b|\b(?:ruff\s+check|flake8|pylint)\s+', re.I),
     "Usa lint_file(path='...') o lint_project() en lugar de 'bash ruff/flake8/pylint' — devuelve JSON con errores."),
]


def _check_antipatterns(command: str) -> str:
    """Devuelve un mensaje de advertencia si el comando usa bash donde debería usar una tool."""
    warnings = []
    for pattern, msg in _BASH_ANTIPATTERNS:
        if pattern.search(command):
            warnings.append(f"⚠️  {msg}")
    if not warnings:
        return ""
    return "\n\n" + "\n".join(warnings)


def bash_execute(
    command: str,
    timeout: int = _DEFAULT_TIMEOUT,
    workdir: str | None = None,
    max_output_chars: int = _DEFAULT_MAX_OUTPUT_CHARS,
) -> str:
    try:
        # Envolver con nice -n 10 en plataformas POSIX para reducir prioridad de CPU
        if _NICE_CMD:
            actual_cmd: str | list[str] = [_NICE_CMD, "-n", "10", "bash", "-c", command]
            use_shell  = False
        else:
            actual_cmd = command
            use_shell  = True
        proc = subprocess.Popen(
            actual_cmd,
            shell=use_shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,   # evita que procesos esperen stdin
            text=True,
            cwd=workdir,
            start_new_session=True,     # nuevo grupo de procesos → os.killpg mata todo el árbol
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_group(proc)
            return f"Error: el comando superó el timeout de {timeout}s."

        output = (stdout or "") + (stderr or "")
        if len(output) > max_output_chars:
            output = (
                output[:max_output_chars]
                + f"\n... (salida truncada a {max_output_chars} caracteres)"
            )
        if not output.strip():
            output = f"(comando ejecutado, sin salida — código de retorno: {proc.returncode})"
        output += _check_antipatterns(command)
        return output

    except Exception as e:
        return f"Error ejecutando bash: {e}"


def _kill_group(proc: subprocess.Popen) -> None:
    """Mata el grupo de procesos completo y espera a que terminen."""
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        try:
            proc.kill()
        except Exception:
            pass
    try:
        proc.communicate(timeout=5)
    except Exception:
        pass


def build_bash_schema(
    max_output_chars: int = _DEFAULT_MAX_OUTPUT_CHARS,
    default_timeout: int = _DEFAULT_TIMEOUT,
) -> tuple:
    """Devuelve el schema de bash con defaults inyectados desde config."""

    def _bash(command: str, timeout: int = default_timeout, workdir: str | None = None) -> str:
        return bash_execute(command, timeout=timeout, workdir=workdir, max_output_chars=max_output_chars)

    schema = {
        "name": "bash",
        "description": (
            "Ejecuta un comando de shell (bash -c). ÚLTIMO RECURSO — usa siempre la tool especializada si existe: "
            "grep_code (no bash grep), find_file/find_files (no bash find), ls_dir (no bash ls), "
            "file_stat (no bash wc -l), edit_file/regex_replace (no bash sed -i), "
            "python_exec (no python3 heredocs), git_* (no bash git), docker_* (no bash docker). "
            "Úsalo solo para: compilar (make, cargo, go build), instalar paquetes, "
            "comandos de sistema que no tienen tool equivalente. "
            f"Timeout por defecto: {default_timeout}s — pasa timeout=N para comandos lentos."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string",  "description": "Comando shell a ejecutar. Usa rutas absolutas. NO uses 'cd /ruta && cmd' — pasa workdir en su lugar."},
                "timeout": {"type": "integer", "description": f"Timeout en segundos (por defecto {default_timeout}). Aumenta para scripts lentos."},
                "workdir": {"type": "string",  "description": "Directorio de trabajo con ruta absoluta. Úsalo en lugar de 'cd /ruta &&' al inicio del comando."},
            },
            "required": ["command"],
        },
    }
    return "bash", _bash, schema


# Compatibilidad: schema con defaults sin config
BASH_SCHEMA = build_bash_schema()
