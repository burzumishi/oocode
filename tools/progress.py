"""Mecanismo de progreso para tools de larga duración.

Permite que las tools de búsqueda y lectura reporten el fichero actual
mientras se están ejecutando, para que el display del agente lo muestre
en tiempo real en el spinner o en la línea de progreso.

Uso en una tool:
    from tools.progress import report_progress
    report_progress("src/main.py")

El AgentLoop registra el callback antes de ejecutar la tool y lo limpia
después:
    from tools import progress as _prog
    _prog.set_progress_callback(lambda f: setattr(self, '_tool_current_file', f))
    result = self._execute_tool(name, args)
    _prog.set_progress_callback(None)
"""
import threading
from typing import Callable, Optional

_local = threading.local()


def set_progress_callback(cb: Optional[Callable[[str], None]]) -> None:
    """Registra (o limpia con None) el callback de progreso para el hilo actual."""
    _local.callback = cb


def report_progress(file_path: str) -> None:
    """Notifica el fichero actual al callback registrado en este hilo (si hay uno)."""
    cb: Optional[Callable[[str], None]] = getattr(_local, "callback", None)
    if cb is not None:
        try:
            cb(file_path)
        except Exception:
            pass
