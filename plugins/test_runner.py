"""Plugin: test_runner
Detecta el framework de tests del proyecto y ejecuta suites o tests individuales.
Tras editar un fichero, lanza automáticamente los tests relacionados.
Sin dependencias externas: usa pytest, jest, go test, cargo test, etc. del sistema.
"""
import os
import re
import subprocess
from pathlib import Path

NAME        = "test_runner"
DESCRIPTION = "Ejecución de tests (pytest/jest/go/cargo/make) con detección automática del framework"
VERSION     = "1.0.0"

_cfg: dict = {"workspace": None, "auto": True}

COMMANDS: dict = {}
TOOLS: list    = []

_MAX_OUTPUT = 6000


# ── Detección de framework ─────────────────────────────────────────────────────

def _detect_framework(root: Path) -> str | None:
    if (root / "pytest.ini").exists() or (root / "pyproject.toml").exists():
        if any(root.rglob("test_*.py")) or any(root.rglob("*_test.py")):
            return "pytest"
    if list(root.rglob("*.py")):
        if any(root.rglob("test_*.py")) or any(root.rglob("*_test.py")):
            return "pytest"
    if (root / "package.json").exists():
        try:
            import json
            pkg = json.loads((root / "package.json").read_text())
            scripts = pkg.get("scripts", {})
            if "test" in scripts:
                return "npm_test"
        except Exception:
            pass
        if (root / "jest.config.js").exists() or (root / "jest.config.ts").exists():
            return "jest"
    if (root / "go.mod").exists():
        return "go"
    if (root / "Cargo.toml").exists():
        return "cargo"
    if (root / "Makefile").exists():
        content = (root / "Makefile").read_text()
        if re.search(r"^test\s*:", content, re.MULTILINE):
            return "make"
    return None


def _run_cmd(cmd: list[str], cwd: str, timeout: int = 120) -> tuple[int, str]:
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            cwd=cwd,
            start_new_session=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "NO_COLOR": "1"},
        )
        try:
            out, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                import signal
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                proc.kill()
            proc.communicate()
            return -1, f"Tests superaron el timeout de {timeout}s."
        return proc.returncode, (out or "").strip()
    except FileNotFoundError:
        return -2, f"herramienta no instalada: {cmd[0]}"
    except Exception as e:
        return -3, str(e)


def _trim(out: str) -> str:
    if len(out) <= _MAX_OUTPUT:
        return out
    half = _MAX_OUTPUT // 2
    return out[:half] + "\n\n… (salida recortada) …\n\n" + out[-half:]


# ── Herramientas ──────────────────────────────────────────────────────────────

def run_tests(path: str = "", filter: str = "") -> str:
    """Ejecuta los tests del proyecto y devuelve el resultado.

    Args:
        path: Directorio del proyecto o fichero de test (vacío = workspace).
        filter: Filtro de tests (nombre de test, patrón grep, etc.).
    """
    root_str = path or _cfg.get("workspace") or os.getcwd()
    root     = Path(root_str)

    # Si se pasa un fichero, usar su directorio como root para detección
    if root.is_file():
        test_file = str(root)
        root      = root.parent
    else:
        test_file = ""

    framework = _detect_framework(root)
    if framework is None:
        return (
            f"No se detectó framework de tests en '{root}'.\n"
            "Frameworks soportados: pytest, jest, go test, cargo test, make test."
        )

    if framework == "pytest":
        cmd = ["python3", "-m", "pytest", "-v", "--tb=short", "--no-header"]
        if test_file:
            cmd.append(test_file)
        elif filter:
            cmd += ["-k", filter]
        elif path:
            cmd.append(str(root))

    elif framework == "jest":
        cmd = ["npx", "jest", "--no-coverage"]
        if test_file:
            cmd.append(test_file)
        elif filter:
            cmd += ["--testNamePattern", filter]

    elif framework == "npm_test":
        cmd = ["npm", "test", "--", "--no-coverage"]

    elif framework == "go":
        cmd = ["go", "test", "-v", "./..."]
        if filter:
            cmd += ["-run", filter]

    elif framework == "cargo":
        cmd = ["cargo", "test"]
        if filter:
            cmd += [filter]

    elif framework == "make":
        cmd = ["make", "test"]

    else:
        return f"Framework '{framework}' no soportado."

    rc, out = _run_cmd(cmd, cwd=str(root))
    trimmed = _trim(out)
    status  = "✓ PASARON" if rc == 0 else "✗ FALLARON"
    return f"Tests [{framework}] — {status}\n\n{trimmed}"


def test_file(path: str) -> str:
    """Ejecuta únicamente los tests de un fichero específico.

    Args:
        path: Ruta al fichero de test o al fichero fuente (se busca el test correspondiente).
    """
    p = Path(path)
    if not p.exists():
        return f"Error: fichero no encontrado: {path}"

    # Si es un fichero fuente Python, buscar test correspondiente
    if p.suffix == ".py" and not p.stem.startswith("test_") and not p.stem.endswith("_test"):
        # buscar test_<name>.py o <name>_test.py
        candidates = [
            p.parent / f"test_{p.stem}.py",
            p.parent / f"{p.stem}_test.py",
            p.parent / "tests" / f"test_{p.stem}.py",
            p.parent.parent / "tests" / f"test_{p.stem}.py",
        ]
        for c in candidates:
            if c.exists():
                p = c
                break

    return run_tests(str(p))


TOOLS = [
    (
        "run_tests",
        run_tests,
        {
            "name": "run_tests",
            "description": "Ejecuta los tests del proyecto. Detecta automáticamente pytest, jest, go test, cargo test o make test.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":   {"type": "string", "description": "Directorio o fichero de test (vacío = workspace)"},
                    "filter": {"type": "string", "description": "Filtro de tests: nombre, patrón o expresión según el framework"},
                },
                "required": [],
            },
        },
    ),
    (
        "test_file",
        test_file,
        {
            "name": "test_file",
            "description": "Ejecuta los tests asociados a un fichero fuente concreto (busca test_<nombre>.py automáticamente).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Fichero fuente o fichero de test"},
                },
                "required": ["path"],
            },
        },
    ),
]


# ── Hook: tests automáticos tras editar ──────────────────────────────────────

_IGNORE_PATTERNS = re.compile(
    r"(config|settings|__init__|migration|schema|\.min\.|vendor)", re.I
)


def on_tool_result(name: str, args: dict, result: str) -> None:
    if not _cfg.get("auto"):
        return
    if name not in ("write_file", "edit_file"):
        return
    path = args.get("path", "")
    if not path:
        return
    p = Path(path)
    # Solo ficheros de código, no configs ni migraciones
    if p.suffix.lower() not in (".py", ".js", ".ts", ".go", ".rs"):
        return
    if _IGNORE_PATTERNS.search(str(p)):
        return

    from ui.console import console
    out = test_file(path)
    icon = "✓" if "PASARON" in out else "✗"
    color = "green" if "PASARON" in out else "yellow"
    # Solo imprimir si hay algo interesante (no imprimir cuando no hay tests)
    if "No se detectó" not in out and "no encontrado" not in out:
        # Solo mostrar la parte final (resumen) para no saturar
        lines   = out.splitlines()
        summary = [ln for ln in lines[-20:] if ln.strip()]
        fname   = Path(path).name
        console.print(f"\n  [{color}]{icon}[/{color}]  tests  [dim]{fname}[/dim]")
        for ln in summary:
            console.print(f"     {ln}")
        console.print()


def on_start(config) -> None:
    _cfg["workspace"] = config.workspace
    _cfg["auto"]      = True


def _cmd_test(args: str, agent_loop, config) -> None:
    from ui.console import console
    path   = args.strip() or config.workspace
    result = run_tests(path)
    console.print(result)


COMMANDS = {"/test": _cmd_test}
