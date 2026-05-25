"""Gestión de sesiones: persistencia JSONL, índice, carga y estadísticas + Background Agents."""
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from config import CONFIG_DIR

SESSIONS_ROOT = CONFIG_DIR / "sessions"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _ago(ts_iso: str) -> str:
    """Devuelve 'hace X min/h/días' desde una ISO timestamp."""
    try:
        dt = datetime.fromisoformat(ts_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        diff = datetime.now(timezone.utc) - dt
        s = int(diff.total_seconds())
        if s < 60:
            return "ahora"
        if s < 3600:
            return f"hace {s // 60} min"
        if s < 86400:
            return f"hace {s // 3600} h"
        return f"hace {s // 86400} días"
    except Exception:
        return "—"


class BackgroundSession:
    """Sesión de background agent para ejecución paralela.
    
    Permite ejecutar varios agentes en paralelo sin bloquear la sesión principal.
    """
    
    def __init__(self, session_id: str, agent_id: str, task: str, priority: int = 0,
                 max_concurrent: int = 4, resource_pool: Optional[dict] = None):
        self.session_id = session_id
        self.agent_id = agent_id
        self.task = task
        self.priority = priority
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.started_at: Optional[str] = None
        self.completed_at: Optional[str] = None
        self.status = "pending"  # pending | running | completed | failed
        self.output: list[str] = []
        self.error: Optional[str] = None
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.message_count: int = 0
        self.tool_calls_count: int = 0
        self.max_concurrent = max_concurrent
        self.resource_pool = resource_pool or {
            "max_memory_mb": 512,
            "max_cpu_percent": 50,
            "max_tokens_per_minute": 10000,
        }
        self._lock = threading.Lock()
        self._queue: list["BackgroundSession"] = []
        self._running_count: int = 0
    
    def start(self) -> None:
        """Inicia la sesión de background con control de recursos."""
        with self._lock:
            if self._running_count >= self.max_concurrent:
                self.status = "queued"
                self._queue.append(self)
                return
            
            self.status = "running"
            self.started_at = datetime.now(timezone.utc).isoformat()
            self._running_count += 1
    
    def complete(self, result: str, tokens: Optional[tuple[int, int]] = None) -> None:
        """Marca la sesión como completada y libera recursos."""
        with self._lock:
            self.status = "completed"
            self.completed_at = datetime.now(timezone.utc).isoformat()
            if tokens:
                self.input_tokens = tokens[0]
                self.output_tokens = tokens[1]
            self._running_count -= 1
            self._process_queue()
    
    def fail(self, error: str) -> None:
        """Marca la sesión como fallida y libera recursos."""
        with self._lock:
            self.status = "failed"
            self.completed_at = datetime.now(timezone.utc).isoformat()
            self.error = error
            self._running_count -= 1
            self._process_queue()
    
    def _process_queue(self) -> None:
        """Procesa la cola de sesiones en espera."""
        while self._queue and self._running_count < self.max_concurrent:
            session = self._queue.pop(0)
            session.start()
    
    def to_dict(self) -> dict:
        """Serializa la sesión a dict."""
        return {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "task": self.task,
            "priority": self.priority,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "output": self.output,
            "error": self.error,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "message_count": self.message_count,
            "tool_calls_count": self.tool_calls_count,
            "queue_position": self._queue.index(self) + 1 if self.status == "queued" else None,
            "resource_pool": self.resource_pool,
        }


class SessionManager:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.sessions_dir = SESSIONS_ROOT / agent_id
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        self.session_id: str = str(uuid.uuid4())
        self.started_at: str = _now_iso()
        self.model: str = ""
        self.workspace: str = ""
        self._jsonl: Optional[Path] = None
        self._index_file = self.sessions_dir / "sessions.json"

        # Contadores
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.message_count: int = 0
        self.tool_calls_count: int = 0
        self.compaction_count: int = 0

    # ── Ciclo de vida ──────────────────────────────────────────────────────────

    def start(self, model: str, workspace: str) -> None:
        self.model = model
        self.workspace = workspace
        self._jsonl = self.sessions_dir / f"{self.session_id}.jsonl"
        self._append({
            "type": "session",
            "version": 1,
            "id": self.session_id,
            "timestamp": self.started_at,
            "agent_id": self.agent_id,
            "model": model,
            "workspace": workspace,
        })
        self._update_index()

    def end(self) -> None:
        self._append({
            "type": "session_end",
            "id": self.session_id,
            "timestamp": _now_iso(),
            "message_count": self.message_count,
            "tool_calls": self.tool_calls_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        })
        self._update_index(ended=True)

    # ── Logging de eventos ─────────────────────────────────────────────────────

    def log_message(self, role: str, content: str) -> None:
        self.message_count += 1
        self._append({
            "type": "message",
            "id": str(uuid.uuid4())[:8],
            "timestamp": _now_iso(),
            "message": {"role": role, "content": content[:2000]},
        })
        self._update_index()

    def log_tool_call(self, name: str, args: dict, result: str) -> None:
        self.tool_calls_count += 1
        self._append({
            "type": "tool_call",
            "id": str(uuid.uuid4())[:8],
            "timestamp": _now_iso(),
            "name": name,
            "args": args,
            "result_preview": result[:200],
        })

    def log_usage(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self._append({
            "type": "usage",
            "timestamp": _now_iso(),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_input": self.input_tokens,
            "total_output": self.output_tokens,
        })
        self._update_index()

    def log_compaction(self, messages_removed: int) -> None:
        self.compaction_count += 1
        self._append({
            "type": "compaction",
            "timestamp": _now_iso(),
            "messages_removed": messages_removed,
            "compaction_count": self.compaction_count,
        })

    def log_model_change(self, new_model: str) -> None:
        self.model = new_model
        self._append({
            "type": "model_change",
            "timestamp": _now_iso(),
            "model": new_model,
        })
        self._update_index()

    # ── Consulta ───────────────────────────────────────────────────────────────

    def list_sessions(self, limit: int = 15) -> list[dict]:
        """Lee el índice y devuelve las últimas `limit` sesiones."""
        if not self._index_file.exists():
            return []
        try:
            index = json.loads(self._index_file.read_text())
            sessions = list(index.values())
            sessions.sort(key=lambda s: s.get("started_at", ""), reverse=True)
            return sessions[:limit]
        except Exception:
            return []

    def load_messages(self, session_id: str) -> list[dict]:
        """Carga los mensajes de una sesión pasada para restaurar el contexto."""
        jsonl = self.sessions_dir / f"{session_id}.jsonl"
        if not jsonl.exists():
            return []
        messages = []
        try:
            for line in jsonl.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                if event.get("type") == "message":
                    msg = event.get("message", {})
                    if msg.get("role") in ("user", "assistant"):
                        messages.append(msg)
        except Exception:
            pass
        return messages

    def stats(self) -> dict:
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "model": self.model,
            "workspace": self.workspace,
            "message_count": self.message_count,
            "tool_calls": self.tool_calls_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "compactions": self.compaction_count,
        }

    # ── Privado ────────────────────────────────────────────────────────────────

    def _append(self, event: dict) -> None:
        if self._jsonl is None:
            return
        with self._jsonl.open("a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _update_index(self, ended: bool = False) -> None:
        index: dict = {}
        if self._index_file.exists():
            try:
                index = json.loads(self._index_file.read_text())
            except Exception:
                pass
        index[self.session_id] = {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "ended_at": _now_iso() if ended else None,
            "model": self.model,
            "workspace": self.workspace,
            "message_count": self.message_count,
            "tool_calls": self.tool_calls_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "compactions": self.compaction_count,
        }
        self._index_file.write_text(json.dumps(index, indent=2, ensure_ascii=False))


def start_background_session(agent_id: str, task: str, priority: int = 0,
                              max_concurrent: int = 4, resource_pool: Optional[dict] = None) -> dict:
    """Inicia una sesión de background para ejecutar en paralelo con control de recursos."""
    session_id = str(uuid.uuid4())[:8]
    bg_session = BackgroundSession(session_id, agent_id, task, priority, max_concurrent, resource_pool)
    bg_session.start()
    return bg_session.to_dict()


def complete_background_session(session_id: str, result: str, tokens: tuple[int, int] = (0, 0)) -> dict:
    """Marca una sesión de background como completada."""
    bg_session = BackgroundSession(session_id, "", "", 0)
    bg_session.complete(result, tokens)
    return bg_session.to_dict()


def fail_background_session(session_id: str, error: str) -> dict:
    """Marca una sesión de background como fallida."""
    bg_session = BackgroundSession(session_id, "", "", 0)
    bg_session.fail(error)
    return bg_session.to_dict()


def get_background_sessions() -> list[dict]:
    """Devuelve todas las sesiones de background activas."""
    # Implementación pendiente: persistencia externa requerida
    return []


def get_background_session(session_id: str) -> Optional[dict]:
    """Devuelve una sesión de background por ID."""
    bg_session = BackgroundSession(session_id, "", "", 0)
    return bg_session.to_dict()
