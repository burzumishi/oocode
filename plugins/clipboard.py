"""Plugin: clipboard
Integración con el portapapeles del sistema. Permite al agente copiar resultados
y al usuario pegar contenido (errores, stacks, código) directamente en el chat.
Detecta automáticamente xclip, xsel, wl-copy (Wayland) o xdotool.
"""
import os
import shutil
import subprocess

NAME        = "clipboard"
DESCRIPTION = "Portapapeles del sistema: copiar resultados y pegar contenido como input"
VERSION     = "1.0.0"

COMMANDS: dict = {}
TOOLS: list    = []

_MAX_PASTE = 20_000


# ── Backend de portapapeles ───────────────────────────────────────────────────

def _detect_backend() -> str | None:
    """Detecta el backend disponible según el entorno (X11 o Wayland)."""
    wayland = os.environ.get("WAYLAND_DISPLAY")
    if wayland:
        for b in ("wl-copy", "wl-paste", "xclip", "xsel"):
            if shutil.which(b):
                return "wl" if b.startswith("wl") else b
    for b in ("xclip", "xsel", "xdotool"):
        if shutil.which(b):
            return b
    return None


def _copy_cmd(backend: str, text: str) -> list[str] | None:
    if backend == "xclip":
        return ["xclip", "-selection", "clipboard"]
    if backend == "xsel":
        return ["xsel", "--clipboard", "--input"]
    if backend == "wl":
        return ["wl-copy"]
    return None


def _paste_cmd(backend: str) -> list[str] | None:
    if backend == "xclip":
        return ["xclip", "-selection", "clipboard", "-o"]
    if backend == "xsel":
        return ["xsel", "--clipboard", "--output"]
    if backend == "wl":
        return ["wl-paste"]
    return None


def _run_copy(text: str) -> str:
    backend = _detect_backend()
    if backend is None:
        return "Error: no hay backend de portapapeles (instala xclip, xsel o wl-clipboard)."
    cmd = _copy_cmd(backend, text)
    if cmd is None:
        return f"Error: backend '{backend}' no soportado para copiar."
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        _, err = proc.communicate(input=text.encode("utf-8"), timeout=5)
        if proc.returncode != 0 and err:
            return f"Error copiando: {err.decode(errors='replace').strip()}"
        return f"Copiado al portapapeles ({len(text)} caracteres)."
    except Exception as e:
        return f"Error: {e}"


def _run_paste() -> str:
    backend = _detect_backend()
    if backend is None:
        return "Error: no hay backend de portapapeles."
    cmd = _paste_cmd(backend)
    if cmd is None:
        return f"Error: backend '{backend}' no soportado para pegar."
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        out, err = proc.communicate(timeout=5)
        text = (out or b"").decode("utf-8", errors="replace")
        if not text and err:
            return f"Error leyendo portapapeles: {err.decode(errors='replace').strip()}"
        return text[:_MAX_PASTE]
    except Exception as e:
        return f"Error: {e}"


# ── Herramientas ──────────────────────────────────────────────────────────────

def clipboard_copy(text: str) -> str:
    """Copia texto al portapapeles del sistema.

    Args:
        text: Texto a copiar.
    """
    return _run_copy(text)


def clipboard_paste() -> str:
    """Lee el contenido actual del portapapeles del sistema.
    Útil para que el usuario pegue errores, stacks o código sin escribirlos.
    """
    content = _run_paste()
    if content.startswith("Error"):
        return content
    if not content.strip():
        return "(Portapapeles vacío)"
    lines = content.splitlines()
    preview = "\n".join(lines[:5])
    suffix  = f"\n… ({len(lines)-5} líneas más)" if len(lines) > 5 else ""
    return f"Contenido del portapapeles ({len(lines)} líneas):\n{preview}{suffix}\n\n{content}"


TOOLS = [
    (
        "clipboard_copy",
        clipboard_copy,
        {
            "name": "clipboard_copy",
            "description": "Copia texto al portapapeles del sistema para que el usuario pueda pegarlo en otra aplicación.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Texto a copiar al portapapeles"},
                },
                "required": ["text"],
            },
        },
    ),
    (
        "clipboard_paste",
        clipboard_paste,
        {
            "name": "clipboard_paste",
            "description": "Lee el contenido del portapapeles del sistema. Útil cuando el usuario quiere que el agente analice algo que ha copiado (un error, un stack trace, código de otra app).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    ),
]


def _cmd_paste(args: str, agent_loop, config) -> None:
    """Pega el portapapeles como mensaje al agente."""
    from ui.console import console
    content = _run_paste()
    if content.startswith("Error"):
        console.print(f"  [red]{content}[/red]")
        return
    if not content.strip():
        console.print("  [dim](Portapapeles vacío)[/dim]")
        return

    prefix = args.strip() or "Analiza el siguiente contenido del portapapeles:"
    msg    = f"{prefix}\n\n{content}"
    console.print(f"  [dim]Enviando portapapeles al agente ({len(content)} chars)…[/dim]")

    import threading
    def _run():
        agent_loop.run(msg)

    threading.Thread(target=_run, daemon=True, name="oocode-paste").start()


def _cmd_copy(args: str, agent_loop, config) -> None:
    from ui.console import console
    if args.strip():
        console.print(_run_copy(args.strip()))
    else:
        console.print("  Uso: /copy <texto>  o usa el botón Copiar de la respuesta")


COMMANDS = {
    "/paste": _cmd_paste,
    "/clip":  _cmd_copy,
}
