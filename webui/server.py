#!/usr/bin/env python3
"""OOCode WebUI — daemon standalone.

Se invoca como:
    python -m webui.server [host] [port] [log_file]

Y también por oocode internamente para lanzar el servidor como proceso
independiente (start_new_session=True) que persiste tras cerrar el TUI.
"""
import sys
import os
import json
import signal
from pathlib import Path

_STATE_FILE = Path.home() / ".oocode" / "webui_state.json"
_DEFAULT_HOST = "0.0.0.0"
_DEFAULT_PORT = 4000


def _write_state(pid: int, host: str, port: int, log_file: str) -> None:
    import time as _t
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps({
        "running":    True,
        "pid":        pid,
        "started":    __import__("datetime").datetime.now().isoformat(),
        "started_ts": _t.time(),
        "host":       host,
        "port":       port,
        "log":        log_file,
    }, indent=2))


def _clear_state() -> None:
    try:
        _STATE_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def _handle_exit(sig, frame) -> None:
    _clear_state()
    sys.exit(0)


def run(host: str = _DEFAULT_HOST, port: int = _DEFAULT_PORT,
        log_file: str = "") -> None:
    """Arranca Flask y registra estado; limpia al salir."""
    import logging as _logging

    _project_root = str(Path(__file__).parent.parent)
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)

    log_path = (
        Path(log_file).expanduser()
        if log_file
        else Path.home() / ".oocode" / "logs" / "webserver.log"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)

    wz = _logging.getLogger("werkzeug")
    wz.handlers.clear()
    fh = _logging.FileHandler(str(log_path), encoding="utf-8")
    fh.setFormatter(_logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    wz.addHandler(fh)
    wz.propagate = False

    from webui.app import app
    app.logger.handlers.clear()
    app.logger.addHandler(fh)
    app.logger.propagate = False

    _write_state(os.getpid(), host, port, str(log_path))

    signal.signal(signal.SIGTERM, _handle_exit)
    signal.signal(signal.SIGINT, _handle_exit)

    try:
        app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
    finally:
        _clear_state()


if __name__ == "__main__":
    _host     = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_HOST
    _port     = int(sys.argv[2]) if len(sys.argv) > 2 else _DEFAULT_PORT
    _log_file = sys.argv[3] if len(sys.argv) > 3 else ""
    run(_host, _port, _log_file)
