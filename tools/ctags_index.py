"""Indexación de símbolos con universal-ctags.

Módulo autónomo: no importa nada de plugins/. Es importado por:
  - tools/hooks.py  (builtin ctags_after_write)
  - ui/commands.py  (comando /symbols)
  - oocode.py       (indexación inicial en startup)
"""
import os
import subprocess
from pathlib import Path

_TAGS_FILE = ".oocode_tags"

_KINDS: dict[str, str] = {
    "c": "clase",
    "f": "función",
    "m": "método",
    "v": "variable",
    "i": "interfaz",
    "s": "struct",
    "e": "enum",
    "t": "tipo",
    "d": "define",
    "n": "namespace",
    "p": "prototipo",
}

_workspace_root: str = ""


def set_workspace(path: str) -> None:
    global _workspace_root
    _workspace_root = path


def _workspace() -> str:
    return _workspace_root or os.getcwd()


def _has_ctags() -> bool:
    import shutil
    return bool(shutil.which("ctags") or shutil.which("universal-ctags"))


def _ctags_bin() -> str:
    import shutil
    return shutil.which("ctags") or shutil.which("universal-ctags") or "ctags"


def _tags_path(root: str | None = None) -> Path:
    return Path(root or _workspace()) / _TAGS_FILE


def _build_index(root: str | None = None) -> str:
    """Ejecuta ctags. Devuelve '' si OK, mensaje de error si falla."""
    if not _has_ctags():
        return "ctags no instalado (apt install universal-ctags)"
    wd   = root or _workspace()
    tags = _tags_path(wd)
    try:
        proc = subprocess.Popen(
            [_ctags_bin(), "-R", "--fields=+n", "--extras=+q",
             "--tag-relative=yes", "--output-format=u-ctags", "-f", str(tags), "."],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            cwd=wd,
            start_new_session=True,
        )
        _, err = proc.communicate(timeout=60)
        if proc.returncode != 0 and err:
            return err.strip()
        return ""
    except subprocess.TimeoutExpired:
        try:
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            proc.kill()
        proc.communicate()
        return "Timeout al generar índice de ctags."
    except Exception as e:
        return str(e)


def _read_tags(root: str | None = None) -> list[dict]:
    tags_path = _tags_path(root)
    if not tags_path.exists():
        return []
    results = []
    try:
        for line in tags_path.read_text(errors="replace").splitlines():
            if line.startswith("!"):
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            name  = parts[0]
            fpath = parts[1]
            lno   = "?"
            kind  = ""
            for field in parts[3:]:
                if field.startswith("line:"):
                    lno = field[5:]
                elif len(field) == 1 and field.isalpha():
                    kind = field
            results.append({"name": name, "path": fpath, "line": lno, "kind": kind})
    except Exception:
        pass
    return results


# ── API pública ────────────────────────────────────────────────────────────────

def ensure_initial_index() -> None:
    """Genera el índice inicial si ctags está disponible y el índice no existe."""
    if _has_ctags() and not _tags_path().exists():
        _build_index()


def build_index_for_file(path: str) -> None:
    """Reindexea el directorio padre de un fichero tras editarlo."""
    root = str(Path(path).parent)
    _build_index(root)


def build_symbol_index(path: str = "") -> str:
    """Genera o actualiza el índice de símbolos del proyecto."""
    root = path or _workspace()
    if not Path(root).is_dir():
        return f"Error: directorio no encontrado: {root}"
    err = _build_index(root)
    if err:
        return f"Error generando índice: {err}"
    count = len(_read_tags(root))
    return f"Índice generado en {root} — {count} símbolos."


def find_symbol(name: str, kind: str = "", path: str = "") -> str:
    """Busca un símbolo por nombre en el proyecto."""
    root = path or _workspace()
    tags = _read_tags(root)
    if not tags:
        err = _build_index(root)
        if err:
            return f"Sin índice y falló la generación: {err}"
        tags = _read_tags(root)
    if not tags:
        return "No hay símbolos en el índice."

    lower_name = name.lower()
    kind_key   = kind.lower()[:1] if kind else ""
    matches    = []
    for t in tags:
        if lower_name not in t["name"].lower():
            continue
        if kind_key and t["kind"] != kind_key:
            full_kind = _KINDS.get(t["kind"], "")
            if kind_key not in full_kind:
                continue
        matches.append(t)

    if not matches:
        return f"Símbolo '{name}' no encontrado."

    lines = [f"Símbolo: «{name}»  ({len(matches)} resultado(s))\n"]
    for m in matches[:30]:
        k = _KINDS.get(m["kind"], m["kind"])
        lines.append(f"  {m['path']}:{m['line']}  [{k}]  {m['name']}")
    if len(matches) > 30:
        lines.append(f"  … y {len(matches)-30} más.")
    return "\n".join(lines)


def list_symbols(path: str, kinds: str = "") -> str:
    """Lista todos los símbolos definidos en un fichero."""
    p = Path(path)
    if not p.exists():
        return f"Error: fichero no encontrado: {path}"

    root = str(p.parent)
    tags = _read_tags(root)
    if not tags:
        _build_index(root)
        tags = _read_tags(root)

    rel         = p.name
    kind_filter = set(k.strip()[:1] for k in kinds.split(",") if k.strip()) if kinds else set()
    symbols     = [
        t for t in tags
        if Path(t["path"]).name == rel
        and (not kind_filter or t["kind"] in kind_filter)
    ]
    symbols.sort(key=lambda t: int(t["line"]) if t["line"].isdigit() else 0)

    if not symbols:
        return f"Sin símbolos en '{p.name}'."

    lines = [f"Símbolos en {p.name}:\n"]
    for s in symbols:
        k = _KINDS.get(s["kind"], s["kind"])
        lines.append(f"  :{s['line']:<6} [{k:<10}]  {s['name']}")
    return "\n".join(lines)
