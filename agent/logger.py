"""Sistema de logs persistente para OOCode — fichero rotativo + interfaz simple."""
import logging
import logging.handlers
from pathlib import Path
from config import CONFIG_DIR

LOG_DIR  = CONFIG_DIR / "logs"
_LOG_FILE = LOG_DIR / "oocode.log"

_logger:  logging.Logger | None = None
_enabled: bool = False
_log_path: Path = _LOG_FILE


def init(
    enabled:    bool = True,
    log_file:   str  = "",
    level:      str  = "info",
    max_size_mb: int = 5,
    max_files:  int  = 3,
) -> None:
    global _logger, _enabled, _log_path
    _enabled = enabled
    if not enabled:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _log_path = Path(log_file).expanduser() if log_file else _LOG_FILE

    lvl = {
        "debug":   logging.DEBUG,
        "info":    logging.INFO,
        "warn":    logging.WARNING,
        "warning": logging.WARNING,
        "error":   logging.ERROR,
    }.get(level.lower(), logging.INFO)

    handler = logging.handlers.RotatingFileHandler(
        _log_path,
        maxBytes=max(1, max_size_mb) * 1024 * 1024,
        backupCount=max(1, max_files),
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    _logger = logging.getLogger("oocode")
    _logger.setLevel(lvl)
    _logger.handlers.clear()
    _logger.addHandler(handler)
    _logger.propagate = False


def _log(level: str, msg: str, **kwargs) -> None:
    if not _enabled or _logger is None:
        return
    extra = "  " + "  ".join(f"{k}={v!r}" for k, v in kwargs.items()) if kwargs else ""
    getattr(_logger, level, _logger.info)(f"{msg}{extra}")


def debug(msg: str, **kw) -> None:   _log("debug",   msg, **kw)
def info(msg: str, **kw) -> None:    _log("info",    msg, **kw)
def warn(msg: str, **kw) -> None:    _log("warning", msg, **kw)
def error(msg: str, **kw) -> None:   _log("error",   msg, **kw)


def recent(n: int = 80) -> list[str]:
    """Devuelve las últimas n líneas del log activo."""
    if not _log_path.exists():
        return []
    try:
        return _log_path.read_text(encoding="utf-8").splitlines()[-n:]
    except Exception:
        return []


def log_file_path() -> Path:
    return _log_path


def is_enabled() -> bool:
    return _enabled
