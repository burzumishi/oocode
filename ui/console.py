"""Consola Rich compartida con DynamicFile — sigue siempre a sys.stdout actual."""
import sys
from rich.console import Console


class _DynamicFile:
    """Wrapper que escribe siempre al sys.stdout ACTUAL (permite redirección)."""

    def write(self, text: str) -> int:
        return sys.stdout.write(text)

    def flush(self) -> None:
        try:
            sys.stdout.flush()
        except Exception:
            pass

    @property
    def encoding(self) -> str:
        return getattr(sys.stdout, "encoding", "utf-8")

    def fileno(self) -> int:
        return sys.__stdout__.fileno()


_dynamic_file = _DynamicFile()

# Consola única compartida por todos los módulos.
# Como usa _DynamicFile, cualquier redirección de sys.stdout se refleja aquí.
console = Console(file=_dynamic_file, force_terminal=True, highlight=False)
