"""code_search: búsqueda estructurada de código con ripgrep (rg).

Si rg no está instalado usa grep como fallback. Devuelve resultados
con path, línea, columna y fragmento de código con contexto.
"""
import json
import shutil
import subprocess
from pathlib import Path
from tools.progress import report_progress


_DEFAULT_MAX   = 50
_MAX_RESULT_CHARS = 12_000   # límite de salida para no saturar el contexto


def code_search(
    pattern:       str,
    path:          str  = ".",
    file_type:     str  = "",      # e.g. "py", "js", "ts" — filtra extensiones
    context_lines: int  = 2,       # líneas de contexto antes y después del match
    max_results:   int  = _DEFAULT_MAX,
    case_sensitive: bool = False,
    fixed_string:  bool = False,   # True = sin regex, busca literalmente
    glob:          str  = "",      # patrón de fichero, ej. "*.py" o "src/**/*.ts"
    _max_filesize: str  = "500K",  # tamaño máximo de fichero para rg
) -> str:
    """Busca `pattern` en el código del workspace con ripgrep y devuelve resultados estructurados."""
    root = Path(path).expanduser().resolve()
    if not root.exists():
        return f"Error: ruta no encontrada: {path}"

    if shutil.which("rg"):
        return _search_rg(pattern, root, file_type, context_lines,
                          max_results, case_sensitive, fixed_string, glob, _max_filesize)
    return _search_grep(pattern, root, file_type, context_lines,
                        max_results, case_sensitive, fixed_string)


# ── ripgrep ───────────────────────────────────────────────────────────────────

def _search_rg(pattern, root, file_type, context_lines,
               max_results, case_sensitive, fixed_string,
               glob="", max_filesize="500K") -> str:
    cmd = [
        "rg", "--json",
        f"--context={context_lines}",
        "--no-heading",
        "--follow",
        f"--max-filesize={max_filesize}",
    ]
    if not case_sensitive:
        cmd.append("--ignore-case")
    if fixed_string:
        cmd.append("--fixed-strings")
    if file_type:
        cmd.extend(["-t", file_type.lstrip(".")])
    if glob:
        cmd.extend(["-g", glob])
    cmd += ["--", pattern, str(root)]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        lines, stderr_lines = [], []
        seen_files: set[str] = set()
        import select as _select, sys as _sys
        deadline = __import__("time").time() + 20
        while True:
            if __import__("time").time() > deadline:
                proc.kill()
                return "Timeout: la búsqueda tardó demasiado. Refina el patrón o la ruta."
            ready, _, _ = _select.select([proc.stdout, proc.stderr], [], [], 0.1)
            if proc.stdout in ready:
                chunk = proc.stdout.readline()
                if not chunk:
                    break
                lines.append(chunk)
                # Reportar progreso por cada nuevo fichero encontrado
                try:
                    obj = json.loads(chunk)
                    if obj.get("type") == "match":
                        fp = (obj.get("data", {}).get("path", {}) or {}).get("text", "")
                        if fp and fp not in seen_files:
                            seen_files.add(fp)
                            report_progress(fp)
                except (json.JSONDecodeError, AttributeError):
                    pass
            if proc.stderr in ready:
                chunk = proc.stderr.readline()
                if chunk:
                    stderr_lines.append(chunk)
            if not ready and proc.poll() is not None:
                # Consumir lo que quede
                rest_out = proc.stdout.read()
                rest_err = proc.stderr.read()
                if rest_out:
                    for line in rest_out.splitlines(keepends=True):
                        lines.append(line)
                        try:
                            obj = json.loads(line)
                            if obj.get("type") == "match":
                                fp = (obj.get("data", {}).get("path", {}) or {}).get("text", "")
                                if fp and fp not in seen_files:
                                    seen_files.add(fp)
                                    report_progress(fp)
                        except (json.JSONDecodeError, AttributeError):
                            pass
                if rest_err:
                    stderr_lines.append(rest_err)
                break
        rc = proc.returncode if proc.returncode is not None else proc.wait()
        if rc == 2:
            return f"Error ejecutando rg: {''.join(stderr_lines).strip()[:500]}"
    except Exception as exc:
        return f"Error: {exc}"

    return _parse_rg_json("".join(lines), max_results, context_lines)


def _parse_rg_json(output: str, max_results: int, context_lines: int) -> str:
    matches: list[dict] = []   # {path, line, col, text, context_before, context_after}
    current: dict = {}

    for raw_line in output.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            obj = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        t = obj.get("type")
        data = obj.get("data", {})

        if t == "match":
            path_info = data.get("path", {})
            filepath  = path_info.get("text", "") or path_info.get("bytes", "")
            line_num  = data.get("line_number", 0)
            lines_obj = data.get("lines", {})
            text      = lines_obj.get("text", "") or lines_obj.get("bytes", "")
            # Columna del primer submatch
            submatches = data.get("submatches", [])
            col = submatches[0]["start"] + 1 if submatches else 1
            current = {
                "path": filepath,
                "line": line_num,
                "col":  col,
                "text": text.rstrip("\n"),
                "context": [],
            }
            matches.append(current)
            if len(matches) >= max_results:
                break

        elif t == "context" and current:
            lines_obj = data.get("lines", {})
            text      = lines_obj.get("text", "") or lines_obj.get("bytes", "")
            current["context"].append((data.get("line_number", 0), text.rstrip("\n")))

    if not matches:
        return "Sin resultados."

    return _format_matches(matches, max_results, len(matches) == max_results)


# ── grep fallback ─────────────────────────────────────────────────────────────

def _search_grep(pattern, root, file_type, context_lines,
                 max_results, case_sensitive, fixed_string) -> str:
    cmd = ["grep", "-rn", "--include=*"]
    if not case_sensitive:
        cmd.append("-i")
    if fixed_string:
        cmd.append("-F")
    if file_type:
        cmd[-1] = f"--include=*.{file_type.lstrip('.')}"
    if context_lines > 0:
        cmd.extend([f"-A{context_lines}", f"-B{context_lines}"])
    cmd += [pattern, str(root)]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        return "Timeout: búsqueda tardó demasiado."
    except Exception as exc:
        return f"Error: {exc}"

    if proc.returncode == 1:
        return "Sin resultados."
    if proc.returncode > 1:
        return f"Error grep: {proc.stderr.strip()[:300]}"

    lines   = proc.stdout.splitlines()[:max_results * (1 + context_lines * 2)]
    matches = []
    for line in lines:
        # formato: path:lineno:text
        parts = line.split(":", 2)
        if len(parts) >= 3:
            try:
                matches.append({
                    "path": parts[0],
                    "line": int(parts[1]),
                    "col":  1,
                    "text": parts[2],
                    "context": [],
                })
            except (ValueError, IndexError):
                continue
    if not matches:
        return "Sin resultados."
    return _format_matches(matches[:max_results], max_results,
                           len(matches) >= max_results)


# ── Formateo de resultados ─────────────────────────────────────────────────────

def _format_matches(matches: list[dict], max_results: int,
                    truncated: bool) -> str:
    parts = []
    for m in matches:
        rel  = m["path"]
        line = m["line"]
        col  = m["col"]
        text = m["text"]

        header = f"{rel}:{line}:{col}"
        # Contexto: interleave context + match lines ordenadas por nº de línea
        if m.get("context"):
            ctx_lines = [(line, text, True)] + [(n, t, False) for n, t in m["context"]]
            ctx_lines.sort(key=lambda x: x[0])
            body_lines = []
            for n, t, is_match in ctx_lines:
                prefix = "▶" if is_match else " "
                body_lines.append(f"  {prefix} {n:5d}│ {t}")
            body = "\n".join(body_lines)
        else:
            body = f"  ▶ {line:5d}│ {text}"

        parts.append(f"{header}\n{body}")

    out = "\n\n".join(parts)
    if truncated:
        out += f"\n\n... (mostrando {max_results} resultados — refina el patrón para ver menos)"

    if len(out) > _MAX_RESULT_CHARS:
        out = out[:_MAX_RESULT_CHARS] + "\n... [truncado]"

    total = len(matches)
    header = f"code_search: {total} resultado{'s' if total != 1 else ''}\n{'─'*60}\n"
    return header + out


# ── Schema Ollama ─────────────────────────────────────────────────────────────

def build_code_search_schema(
    max_results: int = 50,
    context_lines: int = 2,
    max_filesize: str = "500K",
):
    """Devuelve [(name, fn, schema)] con los defaults inyectados desde config.

    Crea una closure sobre code_search con los valores por defecto configurables.
    """

    def _code_search(
        pattern:        str,
        path:           str  = ".",
        file_type:      str  = "",
        context_lines_: int  = context_lines,
        max_results_:   int  = max_results,
        case_sensitive: bool = False,
        fixed_string:   bool = False,
        glob:           str  = "",
    ) -> str:
        return code_search(
            pattern=pattern,
            path=path,
            file_type=file_type,
            context_lines=context_lines_,
            max_results=max_results_,
            case_sensitive=case_sensitive,
            fixed_string=fixed_string,
            glob=glob,
            _max_filesize=max_filesize,
        )

    schema = {
        "name": "code_search",
        "description": (
            "Busca un patrón de texto o regex en el código del proyecto usando ripgrep. "
            "Devuelve resultados con ruta, número de línea, columna y contexto. "
            "Más rápido y preciso que grep para buscar en código fuente."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Patrón de búsqueda (regex o texto literal)",
                },
                "path": {
                    "type": "string",
                    "description": "Directorio donde buscar (por defecto: directorio actual)",
                    "default": ".",
                },
                "file_type": {
                    "type": "string",
                    "description": "Extensión de fichero a filtrar: 'py', 'js', 'ts', 'go', 'rs', 'c', etc.",
                    "default": "",
                },
                "context_lines_": {
                    "type": "integer",
                    "description": f"Líneas de contexto antes y después de cada match (0-5, por defecto: {context_lines})",
                    "default": context_lines,
                },
                "max_results_": {
                    "type": "integer",
                    "description": f"Máximo de resultados a devolver (por defecto: {max_results})",
                    "default": max_results,
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Distinguir mayúsculas/minúsculas (por defecto: false)",
                    "default": False,
                },
                "fixed_string": {
                    "type": "boolean",
                    "description": "Buscar como texto literal sin interpretar regex",
                    "default": False,
                },
                "glob": {
                    "type": "string",
                    "description": "Patrón de fichero a filtrar, ej. '*.py', 'src/**/*.ts' (vacío = todos)",
                    "default": "",
                },
            },
            "required": ["pattern"],
        },
    }

    return [("code_search", _code_search, schema)]
