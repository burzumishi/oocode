"""Plugin: todo
Gestión de tareas en el código. Escanea TODOs/FIXMEs del workspace,
mantiene un TODO.md sincronizado y expone herramientas para que el agente
añada, liste y marque tareas como completadas.
"""
import os
import re
import time
from pathlib import Path

NAME        = "todo"
DESCRIPTION = "Gestión de TODOs/FIXMEs del código: lista, añade y marca tareas completadas"
VERSION     = "1.0.0"

_cfg: dict = {"workspace": None}

COMMANDS: dict = {}
TOOLS: list    = []

_TODO_FILE   = "TODO.md"
_PATTERN     = re.compile(
    r"#\s*(TODO|FIXME|HACK|XXX|BUG|NOTE|OPTIMIZE)\s*[:\-]?\s*(.*)",
    re.IGNORECASE,
)
_IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    "dist", "build", "target", ".mypy_cache",
}
_SCAN_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs",
    ".c", ".cpp", ".h", ".java", ".rb", ".sh",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _workspace() -> str:
    return _cfg.get("workspace") or os.getcwd()


def _todo_path(root: str | None = None) -> Path:
    return Path(root or _workspace()) / _TODO_FILE


def _scan_dir(root: str) -> list[dict]:
    """Escanea el directorio buscando comentarios TODO/FIXME/HACK/XXX."""
    items = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]
        for fn in filenames:
            fp = Path(dirpath) / fn
            if fp.suffix.lower() not in _SCAN_EXTS:
                continue
            try:
                for lno, line in enumerate(fp.read_text(errors="replace").splitlines(), 1):
                    m = _PATTERN.search(line)
                    if m:
                        items.append({
                            "tag":  m.group(1).upper(),
                            "text": m.group(2).strip(),
                            "path": str(fp),
                            "line": lno,
                        })
            except Exception:
                continue
    return items


def _load_manual(root: str) -> list[dict]:
    """Carga tareas añadidas manualmente del TODO.md (sección ## Manual)."""
    path = _todo_path(root)
    if not path.exists():
        return []
    manual = []
    in_manual = False
    for line in path.read_text().splitlines():
        if line.startswith("## Manual"):
            in_manual = True
            continue
        if in_manual and line.startswith("## "):
            break
        if in_manual:
            m = re.match(r"- \[( |x)\] (.+)", line)
            if m:
                manual.append({
                    "done": m.group(1) == "x",
                    "text": m.group(2),
                })
    return manual


def _write_todo(root: str, scanned: list[dict], manual: list[dict]) -> None:
    path = _todo_path(root)
    lines = [
        "# TODO.md\n",
        f"_Actualizado: {time.strftime('%Y-%m-%d %H:%M')}_\n\n",
    ]

    if scanned:
        by_tag: dict[str, list[dict]] = {}
        for item in scanned:
            by_tag.setdefault(item["tag"], []).append(item)

        for tag in ["TODO", "FIXME", "BUG", "HACK", "XXX", "NOTE", "OPTIMIZE"]:
            items = by_tag.get(tag, [])
            if not items:
                continue
            lines.append(f"## {tag} ({len(items)})\n\n")
            for it in items:
                rel = os.path.relpath(it["path"], root)
                lines.append(f"- [ ] `{rel}:{it['line']}` {it['text']}\n")
            lines.append("\n")

    lines.append("## Manual\n\n")
    for m in manual:
        check = "x" if m["done"] else " "
        lines.append(f"- [{check}] {m['text']}\n")
    lines.append("\n")

    path.write_text("".join(lines))


# ── Herramientas ──────────────────────────────────────────────────────────────

def todo_list(path: str = "", tag: str = "") -> str:
    """Lista las tareas pendientes del workspace.

    Args:
        path: Directorio a escanear (vacío = workspace).
        tag: Filtrar por etiqueta: TODO, FIXME, BUG, HACK, XXX (vacío = todos).
    """
    root    = path or _workspace()
    scanned = _scan_dir(root)
    manual  = _load_manual(root)

    if tag:
        scanned = [i for i in scanned if i["tag"] == tag.upper()]

    if not scanned and not manual:
        return "Sin tareas pendientes en el workspace."

    lines = []
    if scanned:
        by_tag: dict[str, list[dict]] = {}
        for item in scanned:
            by_tag.setdefault(item["tag"], []).append(item)
        for t, items in sorted(by_tag.items()):
            lines.append(f"[{t}] — {len(items)} tarea(s)")
            for it in items[:10]:
                rel = os.path.relpath(it["path"], root)
                lines.append(f"  {rel}:{it['line']}  {it['text']}")
            if len(items) > 10:
                lines.append(f"  … y {len(items)-10} más")

    pending_manual = [m for m in manual if not m["done"]]
    done_manual    = [m for m in manual if m["done"]]
    if pending_manual:
        lines.append(f"\n[MANUAL] — {len(pending_manual)} pendiente(s)")
        for m in pending_manual:
            lines.append(f"  ☐  {m['text']}")
    if done_manual:
        lines.append(f"\n[COMPLETADAS] — {len(done_manual)}")
        for m in done_manual[:5]:
            lines.append(f"  ✓  {m['text']}")

    return "\n".join(lines)


def todo_add(text: str, path: str = "") -> str:
    """Añade una tarea manual al TODO.md del proyecto.

    Args:
        text: Descripción de la tarea.
        path: Directorio del proyecto (vacío = workspace).
    """
    root    = path or _workspace()
    scanned = _scan_dir(root)
    manual  = _load_manual(root)
    manual.append({"done": False, "text": text})
    _write_todo(root, scanned, manual)
    return f"Tarea añadida: {text}"


def todo_done(text_or_index: str, path: str = "") -> str:
    """Marca una tarea manual como completada.

    Args:
        text_or_index: Número de tarea (1-based) o fragmento del texto.
        path: Directorio del proyecto (vacío = workspace).
    """
    root    = path or _workspace()
    scanned = _scan_dir(root)
    manual  = _load_manual(root)

    pending = [m for m in manual if not m["done"]]
    if not pending:
        return "No hay tareas manuales pendientes."

    target = None
    if text_or_index.isdigit():
        idx = int(text_or_index) - 1
        if 0 <= idx < len(pending):
            target = pending[idx]["text"]
    else:
        for m in pending:
            if text_or_index.lower() in m["text"].lower():
                target = m["text"]
                break

    if target is None:
        return f"Tarea '{text_or_index}' no encontrada."

    for m in manual:
        if m["text"] == target:
            m["done"] = True
            break

    _write_todo(root, scanned, manual)
    return f"Tarea completada: {target}"


def todo_sync(path: str = "") -> str:
    """Regenera TODO.md escaneando el código en busca de TODO/FIXME/etc.

    Args:
        path: Directorio a escanear (vacío = workspace).
    """
    root    = path or _workspace()
    scanned = _scan_dir(root)
    manual  = _load_manual(root)
    _write_todo(root, scanned, manual)
    return (
        f"TODO.md actualizado: {root}\n"
        f"  Encontrados en código : {len(scanned)}\n"
        f"  Tareas manuales       : {len(manual)}"
    )


TOOLS = [
    (
        "todo_list",
        todo_list,
        {
            "name": "todo_list",
            "description": "Lista las tareas pendientes del workspace (TODO, FIXME, HACK, BUG, XXX en el código y tareas manuales).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directorio a escanear (vacío = workspace)"},
                    "tag":  {"type": "string", "description": "Filtrar por etiqueta: TODO, FIXME, BUG, HACK, XXX"},
                },
                "required": [],
            },
        },
    ),
    (
        "todo_add",
        todo_add,
        {
            "name": "todo_add",
            "description": "Añade una tarea manual al TODO.md del proyecto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Descripción de la tarea"},
                    "path": {"type": "string", "description": "Directorio del proyecto (vacío = workspace)"},
                },
                "required": ["text"],
            },
        },
    ),
    (
        "todo_done",
        todo_done,
        {
            "name": "todo_done",
            "description": "Marca una tarea manual como completada por número (1, 2…) o fragmento de texto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text_or_index": {"type": "string", "description": "Número de tarea o texto parcial"},
                    "path":          {"type": "string", "description": "Directorio del proyecto (vacío = workspace)"},
                },
                "required": ["text_or_index"],
            },
        },
    ),
    (
        "todo_sync",
        todo_sync,
        {
            "name": "todo_sync",
            "description": "Regenera TODO.md escaneando el código en busca de TODO/FIXME/BUG/HACK/XXX.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directorio a escanear (vacío = workspace)"},
                },
                "required": [],
            },
        },
    ),
]


def on_start(config) -> None:
    _cfg["workspace"] = config.workspace
    root = config.workspace
    count = len(_scan_dir(root))
    if count > 0:
        from ui.console import console
        console.print(f"  [dim]todo:[/dim] {count} tareas en el workspace  [dim](/todo para ver)[/dim]")


def _cmd_todo(args: str, agent_loop, config) -> None:
    from ui.console import console
    a = args.strip().lower()
    if a.startswith("add "):
        console.print(todo_add(args[4:].strip(), config.workspace))
    elif a.startswith("done "):
        console.print(todo_done(args[5:].strip(), config.workspace))
    elif a == "sync":
        console.print(todo_sync(config.workspace))
    else:
        console.print(todo_list(config.workspace))


COMMANDS = {"/todo": _cmd_todo}
