"""Renderizado visual de diffs al estilo Claude Code.

Módulo autónomo: no importa nada de plugins/. Es importado por:
  - tools/hooks.py  (builtin diff_after_write)
  - ui/commands.py  (comando /diff)
"""
import difflib
import re
import shutil
from pathlib import Path
from rich.markup import escape as _esc
from rich.text import Text

from ui.console import console

# ── Redirección TUI: el loop puede inyectar self._print para mostrar diffs ────
# Set by agent/loop.py at the start of each run(); reset to None at end.
_dprint_fn = None


def _dprint(x) -> None:
    fn = _dprint_fn
    if fn is not None:
        fn(x)
    else:
        console.print(x)


# ── Historial de sesión ────────────────────────────────────────────────────────

_history: list[dict] = []
_MAX_HISTORY   = 50
_MAX_DIFF_LINES = 400
_CONTEXT_LINES  = 2

# ── Paleta ─────────────────────────────────────────────────────────────────────

_C_PATH   = "bold cyan"
_C_SEP    = "dim"
_C_HUNK   = "dim"
_C_CTX    = "dim"
_C_LNO    = "dim"
_C_HEADER = "bold"

_C_ADD_FG  = "bold green"
_C_ADD_DIM = "green"
_C_ADD_BG  = "on #0d1f0d"

_C_DEL_FG  = "bold red"
_C_DEL_DIM = "red"
_C_DEL_BG  = "on #1f0d0d"

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)")


# ── Helpers de renderizado ─────────────────────────────────────────────────────

def _tw() -> int:
    try:
        return shutil.get_terminal_size((100, 24)).columns
    except Exception:
        return 100


def _sep_line() -> Text:
    width = min(_tw(), 60)
    return Text("  " + "─" * (width - 2), style=_C_SEP)


def _header_line(path: str, added: int, removed: int, is_new: bool) -> Text:
    t = Text()
    icon = "✚" if is_new else "✎"
    t.append(f"  {icon}  ", style=_C_HEADER)
    t.append(_esc(path),    style=_C_PATH)
    t.append("  ·  ",       style=_C_SEP)
    if added:
        t.append(f"+{added}",   style="bold green")
        t.append("  ",          style="")
    if removed:
        t.append(f"─{removed}", style="bold red")
    return t


def _hunk_header(header: str) -> Text:
    m = _HUNK_RE.match(header)
    if m:
        label = f"  ·· -{m.group(1)},{m.group(2) or '1'}  +{m.group(3)},{m.group(4) or '1'} ··"
        ctx   = m.group(5).strip()
        t     = Text()
        t.append(label, style=_C_HUNK)
        if ctx:
            t.append(f"  {ctx[:40]}", style=_C_HUNK + " italic")
        return t
    return Text(f"  {header}", style=_C_HUNK)


def _code_line(lno_old, lno_new, kind: str, text: str) -> Text:
    code_w = max(_tw() - 2, 40)
    if kind == "add":
        lno_str = f"{lno_new or '':>4}"
        prefix  = f" {lno_str}  +  "
        avail   = max(0, code_w - len(prefix))
        padded  = (text[:avail] if len(text) > avail else text).ljust(avail)
        t = Text("  ")
        t.append(prefix, style=f"{_C_ADD_FG} {_C_ADD_BG}")
        t.append(padded, style=f"{_C_ADD_DIM} {_C_ADD_BG}")
    elif kind == "del":
        lno_str = f"{lno_old or '':>4}"
        prefix  = f" {lno_str}  ─  "
        avail   = max(0, code_w - len(prefix))
        padded  = (text[:avail] if len(text) > avail else text).ljust(avail)
        t = Text("  ")
        t.append(prefix, style=f"{_C_DEL_FG} {_C_DEL_BG}")
        t.append(padded, style=f"{_C_DEL_DIM} {_C_DEL_BG}")
    else:
        lno_str = f"{lno_new or '':>4}"
        t = Text()
        t.append(f"  {lno_str}     ", style=_C_LNO)
        t.append(text,               style=_C_CTX)
    return t


# ── Parser ─────────────────────────────────────────────────────────────────────

def _parse_hunks(old_lines: list[str], new_lines: list[str]) -> list[dict]:
    raw = list(difflib.unified_diff(old_lines, new_lines, lineterm="", n=_CONTEXT_LINES))
    hunks: list[dict] = []
    current: dict | None = None
    old_lno = new_lno = 0

    for line in raw:
        if line.startswith("--- ") or line.startswith("+++ "):
            continue
        m = _HUNK_RE.match(line)
        if m:
            old_lno = int(m.group(1))
            new_lno = int(m.group(3))
            header  = f"@@ -{m.group(1)},{m.group(2) or '1'} +{m.group(3)},{m.group(4) or '1'} @@{m.group(5)}"
            current = {"header": header, "lines": []}
            hunks.append(current)
            continue
        if current is None:
            continue
        text = line[1:]
        if line.startswith("+"):
            current["lines"].append({"kind": "add", "old_lno": None,    "new_lno": new_lno, "text": text})
            new_lno += 1
        elif line.startswith("-"):
            current["lines"].append({"kind": "del", "old_lno": old_lno, "new_lno": None,    "text": text})
            old_lno += 1
        else:
            current["lines"].append({"kind": "ctx", "old_lno": old_lno, "new_lno": new_lno, "text": text})
            old_lno += 1
            new_lno += 1
    return hunks


# ── Renderizado principal ──────────────────────────────────────────────────────

def _render_diff(path: str, old: str, new: str) -> None:
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    hunks     = _parse_hunks(old_lines, new_lines)
    if not hunks:
        return

    all_lines = [l for h in hunks for l in h["lines"]]
    added     = sum(1 for l in all_lines if l["kind"] == "add")
    removed   = sum(1 for l in all_lines if l["kind"] == "del")
    total     = sum(len(h["lines"]) for h in hunks)
    is_new    = not bool(old.strip())

    diff_text = "\n".join(
        f"{'+'if l['kind']=='add' else '-' if l['kind']=='del' else ' '}{l['text']}"
        for h in hunks for l in h["lines"]
    )
    _history.append({"path": path, "diff": diff_text, "added": added, "removed": removed})
    if len(_history) > _MAX_HISTORY:
        _history.pop(0)

    _dprint("")
    _dprint(_header_line(path, added, removed, is_new))
    _dprint(_sep_line())

    rendered  = 0
    truncated = total > _MAX_DIFF_LINES
    for hunk in hunks:
        if rendered >= _MAX_DIFF_LINES:
            break
        if len(hunks) > 1:
            _dprint(_hunk_header(hunk["header"]))
        for entry in hunk["lines"]:
            if rendered >= _MAX_DIFF_LINES:
                break
            _dprint(_code_line(entry["old_lno"], entry["new_lno"], entry["kind"], entry["text"]))
            rendered += 1

    if truncated:
        _dprint(Text(
            f"  … {total - _MAX_DIFF_LINES} líneas más — /diff {Path(path).name} para ver completo",
            style=_C_SEP,
        ))
    _dprint(_sep_line())
    _dprint("")


def _render_diff_from_unified(path: str, unified_text: str) -> None:
    """Renderiza un diff unificado recibido como texto (de MCP write_file)."""
    old_lines: list[str] = []
    new_lines: list[str] = []
    in_diff = False
    for line in unified_text.splitlines():
        if line.startswith("---") or line.startswith("+++"):
            in_diff = True
            continue
        if line.startswith("@@"):
            in_diff = True
            continue
        if not in_diff:
            continue
        if line.startswith("+"):
            new_lines.append(line[1:])
        elif line.startswith("-"):
            old_lines.append(line[1:])
        else:
            ctx = line[1:] if line.startswith(" ") else line
            old_lines.append(ctx)
            new_lines.append(ctx)
    if old_lines or new_lines:
        _render_diff(path, "\n".join(old_lines), "\n".join(new_lines))


# ── API pública para hooks y comandos ──────────────────────────────────────────

def render_edit_diff(args: dict, result: str) -> None:
    """Renderiza diff para un tool call edit_file."""
    if "Error" in result:
        return
    path       = args.get("path") or args.get("file_path", "")
    old_string = args.get("old_string", "")
    new_string = args.get("new_string", "")
    if not path or old_string == new_string:
        return
    p = Path(path)
    try:
        new_content = p.read_text(errors="replace")
        old_content = new_content.replace(new_string, old_string, 1)
        _render_diff(path, old_content, new_content)
    except Exception:
        _render_diff(path, old_string, new_string)


def render_write_diff(args: dict, result: str) -> None:
    """Renderiza diff para un tool call write_file.

    - Si el resultado MCP incluye un bloque ```diff```, lo usa directamente.
    - Si no (direct write_file), usa el fichero .bak creado por backup_before_write.
    """
    if "Error" in result:
        return
    path = args.get("file_path") or args.get("path", "")
    if not path:
        return
    # Caso MCP: resultado contiene bloque diff
    m = re.search(r"```diff\n(.*?)```", result, re.DOTALL)
    if m:
        _render_diff_from_unified(path, m.group(1))
        return
    # Caso direct write_file: comparar con .bak si existe, si no tratar como fichero nuevo
    new_content = args.get("content", "")
    if not new_content:
        return
    bak = Path(path + ".bak")
    try:
        old_content = bak.read_text(errors="replace") if bak.exists() else ""
    except Exception:
        old_content = ""
    if old_content != new_content:
        _render_diff(path, old_content, new_content)


def render_replace_diff(args: dict, result: str) -> None:
    """Renderiza diff para regex_replace y smart_replace (el resultado contiene unified diff)."""
    if "Error" in result or "no encontr" in result.lower() or "NO encontrado" in result:
        return
    path = args.get("file", "")
    if not path:
        return
    parts = result.split("\n\n", 1)
    if len(parts) < 2:
        return
    diff_text = parts[1].strip()
    if not diff_text:
        return
    first = diff_text.splitlines()[0]
    if not (first.startswith("---") or first.startswith("@@") or first.startswith("diff")):
        return
    _render_diff_from_unified(path, diff_text)


def _render_patch_sections(patch_text: str) -> None:
    """Divide un patch multi-fichero en secciones y renderiza cada una."""
    sections: list[str] = []
    current: list[str] = []
    for line in patch_text.splitlines():
        if line.startswith("--- ") and current:
            sections.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("\n".join(current))

    for section in sections:
        if not section.strip():
            continue
        lines = section.splitlines()
        if not lines[0].startswith("---"):
            continue
        path: str | None = None
        for line in lines[:3]:
            if line.startswith("+++ "):
                raw = line[4:].strip()
                if raw.startswith("b/"):
                    raw = raw[2:]
                if raw and raw != "/dev/null":
                    path = raw
                break
        if path:
            _render_diff_from_unified(path, section)


def render_patch_diff(args: dict, result: str) -> None:
    """Renderiza visualmente el patch aplicado por patch_apply."""
    if "FALLO" in result or "Error" in result:
        return
    patch_text = args.get("patch", "")
    if not patch_text:
        patch_file = args.get("patch_file", "")
        if patch_file:
            try:
                patch_text = Path(patch_file).read_text(errors="replace")
            except Exception:
                return
    if not patch_text:
        return
    _render_patch_sections(patch_text)


def render_bulk_diff(args: dict, result: str) -> None:
    """Renderiza diffs de bulk_replace desde marcadores ###FILE: incluidos en el resultado."""
    import re as _re
    for m in _re.finditer(r'###FILE:([^\n]+)\n```diff\n(.*?)```', result, _re.DOTALL):
        file_path = m.group(1).strip()
        diff_text = m.group(2)
        if diff_text.strip():
            _render_diff_from_unified(file_path, diff_text)


def get_history() -> list[dict]:
    return list(_history)


def clear_history() -> None:
    _history.clear()


def rerender_entry(entry: dict) -> None:
    """Re-renderiza una entrada del historial en la consola."""
    added   = entry.get("added", 0)
    removed = entry.get("removed", 0)
    path    = entry["path"]
    is_new  = removed == 0
    code_w  = max(_tw() - 2, 40)

    console.print()
    console.print(_header_line(path, added, removed, is_new))
    console.print(_sep_line())

    for line in entry["diff"].splitlines()[:_MAX_DIFF_LINES]:
        if not line:
            continue
        kind   = "add" if line[0] == "+" else "del" if line[0] == "-" else "ctx"
        text   = line[1:]
        if kind == "add":
            prefix = "      +  "
            avail  = max(0, code_w - len(prefix))
            padded = (text[:avail] if len(text) > avail else text).ljust(avail)
            t = Text("  ")
            t.append(prefix, style=f"{_C_ADD_FG} {_C_ADD_BG}")
            t.append(padded, style=f"{_C_ADD_DIM} {_C_ADD_BG}")
        elif kind == "del":
            prefix = "      ─  "
            avail  = max(0, code_w - len(prefix))
            padded = (text[:avail] if len(text) > avail else text).ljust(avail)
            t = Text("  ")
            t.append(prefix, style=f"{_C_DEL_FG} {_C_DEL_BG}")
            t.append(padded, style=f"{_C_DEL_DIM} {_C_DEL_BG}")
        else:
            t = Text()
            t.append("           ", style="")
            t.append(text,         style=_C_CTX)
        console.print(t)

    console.print(_sep_line())
    console.print()
