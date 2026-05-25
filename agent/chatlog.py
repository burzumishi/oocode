"""Registro human-readable de conversaciones en ~/.oocode/logs/chat.log."""
import json
from datetime import datetime
from pathlib import Path

_DEFAULT_LOG = Path.home() / ".oocode" / "logs" / "chat.log"


class ChatLogger:
    def __init__(self, enabled: bool = False, path: str = "", max_size_mb: int = 10):
        self.enabled = enabled
        self._path = Path(path).expanduser() if path else _DEFAULT_LOG
        self._max_size_mb = max_size_mb
        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        if self.enabled:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._rotate_if_needed()
            self._write(
                f"\n{'='*72}\n"
                f"SESIÓN {self._session_id}\n"
                f"Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"{'='*72}\n"
            )

    def _rotate_if_needed(self) -> None:
        if not self._path.exists():
            return
        size_mb = self._path.stat().st_size / (1024 * 1024)
        if size_mb > self._max_size_mb:
            backup = self._path.with_suffix(".log.1")
            if backup.exists():
                backup.unlink()
            self._path.rename(backup)

    def _write(self, text: str) -> None:
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass

    def _ts(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def log_user(self, text: str) -> None:
        if not self.enabled:
            return
        self._write(f"\n[{self._ts()}] USUARIO\n{text}\n")

    def log_assistant(self, text: str) -> None:
        if not self.enabled:
            return
        self._write(f"\n[{self._ts()}] AGENTE\n{text}\n")

    def log_tool_call(self, name: str, args: dict, result: str) -> None:
        if not self.enabled:
            return
        args_str = json.dumps(args, ensure_ascii=False)[:500]
        result_preview = (result or "")[:1000]
        ellipsis = "…" if len(result or "") > 1000 else ""
        self._write(
            f"\n[{self._ts()}] TOOL: {name}\n"
            f"  args: {args_str}\n"
            f"  result: {result_preview}{ellipsis}\n"
        )

    def log_session_end(self) -> None:
        if not self.enabled:
            return
        self._write(
            f"\n[{self._ts()}] FIN SESIÓN {self._session_id}\n"
            f"{'─'*72}\n"
        )
