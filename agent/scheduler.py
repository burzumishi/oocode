"""Planificador de tareas periódicas: jobs con intervalo en minutos."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from config import CONFIG_DIR

SCHEDULE_FILE = CONFIG_DIR / "schedule.json"


class Scheduler:
    def __init__(self):
        SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, dict] = {}
        self._load()

    def add(self, command: str, interval_minutes: int, description: str = "") -> dict:
        job_id = str(uuid.uuid4())[:8]
        job = {
            "id": job_id,
            "command": command,
            "interval_minutes": max(1, interval_minutes),
            "description": description,
            "created_at": _now(),
            "last_run": None,
            "run_count": 0,
            "enabled": True,
        }
        self._jobs[job_id] = job
        self._save()
        return job

    def all_jobs(self) -> list[dict]:
        return sorted(self._jobs.values(), key=lambda j: j["created_at"], reverse=True)

    def delete(self, job_id: str) -> bool:
        job = self._find(job_id)
        if not job:
            return False
        del self._jobs[job["id"]]
        self._save()
        return True

    def toggle(self, job_id: str) -> Optional[bool]:
        job = self._find(job_id)
        if not job:
            return None
        job["enabled"] = not job["enabled"]
        self._save()
        return job["enabled"]

    def due(self) -> list[dict]:
        """Devuelve jobs que deben ejecutarse ahora."""
        now = datetime.now(timezone.utc)
        result = []
        for job in self._jobs.values():
            if not job["enabled"]:
                continue
            last = job.get("last_run")
            if last is None:
                result.append(job)
                continue
            last_dt = datetime.fromisoformat(last)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            if now - last_dt >= timedelta(minutes=job["interval_minutes"]):
                result.append(job)
        return result

    def mark_run(self, job_id: str) -> None:
        if job_id in self._jobs:
            self._jobs[job_id]["last_run"] = _now()
            self._jobs[job_id]["run_count"] = self._jobs[job_id].get("run_count", 0) + 1
            self._save()

    def next_run(self, job: dict) -> str:
        """Devuelve cuándo toca la próxima ejecución (string legible)."""
        last = job.get("last_run")
        if not last:
            return "ahora"
        try:
            last_dt = datetime.fromisoformat(last)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            next_dt = last_dt + timedelta(minutes=job["interval_minutes"])
            now = datetime.now(timezone.utc)
            diff = int((next_dt - now).total_seconds())
            if diff <= 0:
                return "ahora"
            if diff < 60:
                return f"en {diff}s"
            if diff < 3600:
                return f"en {diff // 60} min"
            return f"en {diff // 3600} h"
        except Exception:
            return "—"

    def _find(self, job_id: str) -> Optional[dict]:
        if job_id in self._jobs:
            return self._jobs[job_id]
        matches = [j for jid, j in self._jobs.items() if jid.startswith(job_id)]
        return matches[0] if len(matches) == 1 else None

    def _load(self) -> None:
        if SCHEDULE_FILE.exists():
            try:
                self._jobs = json.loads(SCHEDULE_FILE.read_text())
            except Exception:
                self._jobs = {}

    def _save(self) -> None:
        SCHEDULE_FILE.write_text(json.dumps(self._jobs, indent=2, ensure_ascii=False))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
