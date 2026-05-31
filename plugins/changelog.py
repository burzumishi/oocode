"""Plugin: changelog
Diario automático de cambios por sesión. Registra cada edición con timestamp,
fichero, líneas +/- y genera un resumen al final del turno. Sin dependencias
externas: solo Python + el modelo ya cargado.
"""
import os
import time
from pathlib import Path
from config import CONFIG_DIR

NAME        = "changelog"
DESCRIPTION = "Diario automático de cambios: registra ediciones y genera resumen por sesión"
VERSION     = "1.0.0"

_CHANGES_DIR = CONFIG_DIR / "changelogs"

_state: dict = {
    "agent_id":    "main",
    "workspace":   None,
    "session_id":  None,
    "changes":     [],   # lista de dicts {ts, file, op, added, removed, note}
    "turn_changes": [],  # cambios del turno actual (se vacía al resumir)
}

COMMANDS: dict = {}
TOOLS: list    = []


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log_path() -> Path:
    _CHANGES_DIR.mkdir(parents=True, exist_ok=True)
    agent = _state.get("agent_id", "main")
    date  = time.strftime("%Y-%m-%d")
    return _CHANGES_DIR / f"{agent}_{date}.log"


def _diff_lines(old: str, new: str) -> tuple[int, int]:
    """Cuenta líneas añadidas y eliminadas de forma aproximada."""
    old_lines = set(old.splitlines())
    new_lines = set(new.splitlines())
    added   = len(new_lines - old_lines)
    removed = len(old_lines - new_lines)
    return added, removed


def _append_log(entry: dict) -> None:
    ts   = time.strftime("%H:%M:%S", time.localtime(entry["ts"]))
    op   = entry.get("op", "edit")
    path = entry.get("file", "?")
    note = entry.get("note", "")
    plus = entry.get("added", 0)
    minus = entry.get("removed", 0)
    rel  = os.path.relpath(path, _state.get("workspace") or os.getcwd())
    line = f"[{ts}] {op:<6}  {rel}"
    if plus or minus:
        line += f"  +{plus}/-{minus}"
    if note:
        line += f"  # {note}"
    try:
        with _log_path().open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── Herramientas ──────────────────────────────────────────────────────────────

def changelog_today(path: str = "", lines: int = 50) -> str:
    """Muestra el registro de cambios del día de hoy.

    Args:
        path: Filtrar por fichero o directorio (vacío = todos).
        lines: Número máximo de entradas a mostrar.
    """
    log = _log_path()
    if not log.exists():
        return "Sin cambios registrados hoy."

    entries = log.read_text(errors="replace").splitlines()
    if path:
        rel = os.path.relpath(path, _state.get("workspace") or os.getcwd())
        entries = [e for e in entries if rel in e or path in e]

    total   = len(entries)
    shown   = entries[-lines:]
    result  = [f"Cambios hoy ({total} total):\n"]
    result += shown
    return "\n".join(result)


def changelog_session() -> str:
    """Muestra los cambios realizados en la sesión actual."""
    changes = _state["changes"]
    if not changes:
        return "Sin cambios en esta sesión."
    lines = [f"Cambios en sesión ({len(changes)} operaciones):\n"]
    for c in changes[-30:]:
        ts  = time.strftime("%H:%M:%S", time.localtime(c["ts"]))
        rel = os.path.relpath(c.get("file", "?"), _state.get("workspace") or os.getcwd())
        op  = c.get("op", "edit")
        plus  = c.get("added", 0)
        minus = c.get("removed", 0)
        lines.append(f"  [{ts}] {op:<6}  {rel}  +{plus}/-{minus}")
    return "\n".join(lines)


def changelog_week(agent: str = "") -> str:
    """Muestra un resumen de cambios de la última semana.

    Args:
        agent: ID del agente (vacío = agente actual).
    """
    agent_id = agent or _state.get("agent_id", "main")
    _CHANGES_DIR.mkdir(parents=True, exist_ok=True)
    logs = sorted(_CHANGES_DIR.glob(f"{agent_id}_*.log"))[-7:]
    if not logs:
        return f"Sin registros de cambios para el agente '{agent_id}'."

    lines = [f"Cambios última semana ({agent_id}):\n"]
    for log in logs:
        date    = log.stem.split("_", 1)[-1]
        entries = log.read_text(errors="replace").splitlines()
        lines.append(f"\n── {date} ({len(entries)} cambios)")
        for e in entries[:10]:
            lines.append(f"   {e}")
        if len(entries) > 10:
            lines.append(f"   … y {len(entries)-10} más")
    return "\n".join(lines)


TOOLS = [
    (
        "changelog_today",
        changelog_today,
        {
            "name": "changelog_today",
            "description": "Muestra el registro de cambios de ficheros del día de hoy.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":  {"type": "string", "description": "Filtrar por fichero o directorio"},
                    "lines": {"type": "integer", "description": "Número máximo de entradas"},
                },
                "required": [],
            },
        },
    ),
    (
        "changelog_session",
        changelog_session,
        {
            "name": "changelog_session",
            "description": "Muestra los cambios realizados en la sesión actual.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    ),
    (
        "changelog_week",
        changelog_week,
        {
            "name": "changelog_week",
            "description": "Muestra un resumen de cambios de la última semana.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "description": "ID del agente (vacío = actual)"},
                },
                "required": [],
            },
        },
    ),
]


# ── Hooks ─────────────────────────────────────────────────────────────────────

_old_contents: dict[str, str] = {}


def on_tool_result(name: str, args: dict, result: str) -> None:
    if name not in ("write_file", "edit_file", "bash"):
        return

    if name == "bash":
        # Solo registrar comandos con efecto visible en el workspace
        cmd = args.get("command", "")
        if not any(k in cmd for k in ("git commit", "git push", "mv ", "cp ", "rm ", "mkdir")):
            return
        entry = {"ts": time.time(), "file": cmd[:80], "op": "bash", "added": 0, "removed": 0}
        _state["changes"].append(entry)
        _state["turn_changes"].append(entry)
        _append_log(entry)
        return

    path = args.get("path", "")
    if not path:
        return

    op = "write" if name == "write_file" else "edit"
    try:
        current = Path(path).read_text(errors="replace") if Path(path).exists() else ""
        old     = _old_contents.get(path, "")
        added, removed = _diff_lines(old, current)
        _old_contents[path] = current
    except Exception:
        added, removed = 0, 0

    entry = {
        "ts":      time.time(),
        "file":    path,
        "op":      op,
        "added":   added,
        "removed": removed,
    }
    _state["changes"].append(entry)
    _state["turn_changes"].append(entry)
    _append_log(entry)


def on_message(role: str, content: str) -> None:
    """Al inicio de cada respuesta del asistente, limpia los cambios del turno."""
    if role == "assistant":
        _state["turn_changes"] = []


def on_start(config) -> None:
    _state["agent_id"]   = config.agent_id
    _state["workspace"]  = config.workspace
    _state["session_id"] = str(int(time.time()))

    # Pre-cargar contenido actual de ficheros para poder calcular diffs
    root = Path(config.workspace)
    if root.is_dir():
        for ext in (".py", ".js", ".ts", ".go", ".rs", ".c", ".cpp"):
            for p in list(root.rglob(f"*{ext}"))[:50]:
                try:
                    _old_contents[str(p)] = p.read_text(errors="replace")
                except Exception:
                    pass


def on_end() -> None:
    changes = _state["changes"]
    if not changes:
        return
    # Escribir resumen de sesión al final
    try:
        with _log_path().open("a", encoding="utf-8") as f:
            f.write(f"\n── Fin de sesión {time.strftime('%H:%M:%S')} "
                    f"({len(changes)} cambios) ──\n\n")
    except Exception:
        pass


def _cmd_changelog(args: str, agent_loop, config) -> None:
    from ui.console import console
    a = args.strip().lower()
    if a == "semana" or a == "week":
        console.print(changelog_week())
    elif a == "sesion" or a == "session":
        console.print(changelog_session())
    else:
        console.print(changelog_today())


COMMANDS = {"/changelog": _cmd_changelog}
