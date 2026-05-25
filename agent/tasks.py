"""Sistema de tareas persistentes: todo / wip / done + Agent Teams."""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from config import CONFIG_DIR

TASKS_FILE = CONFIG_DIR / "tasks.json"

STATUSES = ("todo", "wip", "done")


class AgentTeam:
    """Estructura de equipo de agentes con lead agent.
    
    El lead agent coordina, asigna subtasks y fusiona resultados.
    """
    
    def __init__(self, team_id: str, lead_agent_id: str, members: Optional[list[str]] = None,
                 team_file: Optional[str] = None):
        self.team_id = team_id
        self.lead_agent_id = lead_agent_id
        self.members = members or [lead_agent_id]
        self.subtasks: list[dict] = []
        self.results: dict[str, str] = {}  # subtask_id -> resultado
        self.status = "idle"  # idle | active | completed | failed
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.team_file = Path(team_file) if team_file else CONFIG_DIR / f"teams/{team_id}.json"
        self.team_file.parent.mkdir(parents=True, exist_ok=True)
        self._load()
    
    def _load(self) -> None:
        """Carga el equipo desde el archivo JSON."""
        if self.team_file.exists():
            try:
                data = json.loads(self.team_file.read_text())
                self.team_id = data.get("team_id", self.team_id)
                self.lead_agent_id = data.get("lead_agent_id", self.lead_agent_id)
                self.members = data.get("members", self.members)
                self.subtasks = data.get("subtasks", [])
                self.results = data.get("results", {})
                self.status = data.get("status", self.status)
                self.created_at = data.get("created_at", self.created_at)
                self.completed_at = data.get("completed_at")
            except Exception:
                self._save()
    
    def _save(self) -> None:
        """Guarda el equipo en el archivo JSON."""
        self.team_file.parent.mkdir(parents=True, exist_ok=True)
        self.team_file.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))
    
    def add_subtask(self, description: str, assign_to: str) -> dict:
        """Añade una subtask y la asigna a un miembro del equipo."""
        subtask_id = str(uuid.uuid4())[:8]
        subtask = {
            "id": subtask_id,
            "description": description,
            "assign_to": assign_to,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.subtasks.append(subtask)
        return subtask
    
    def complete_subtask(self, subtask_id: str, result: str) -> None:
        """Marca una subtask como completada y guarda el resultado."""
        for subtask in self.subtasks:
            if subtask["id"] == subtask_id:
                subtask["status"] = "completed"
                subtask["completed_at"] = datetime.now(timezone.utc).isoformat()
                self.results[subtask_id] = result
                break
    
    def get_pending_subtasks(self) -> list[dict]:
        """Devuelve las subtasks pendientes."""
        return [s for s in self.subtasks if s["status"] == "pending"]
    
    def is_all_completed(self) -> bool:
        """Verifica si todas las subtasks están completadas."""
        return all(s["status"] == "completed" for s in self.subtasks)
    
    def mark_completed(self) -> None:
        """Marca el equipo como completado."""
        self.status = "completed"
        self.completed_at = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self) -> dict:
        """Serializa el equipo a dict."""
        return {
            "team_id": self.team_id,
            "lead_agent_id": self.lead_agent_id,
            "members": self.members,
            "subtasks": self.subtasks,
            "results": self.results,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": getattr(self, "completed_at", None),
        }


class TaskManager:
    def __init__(self):
        TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._tasks: dict[str, dict] = {}
        self._load()

    def add(self, title: str, description: str = "") -> dict:
        task_id = str(uuid.uuid4())[:8]
        task = {
            "id": task_id,
            "title": title,
            "description": description,
            "status": "todo",
            "created_at": _now(),
            "updated_at": _now(),
        }
        self._tasks[task_id] = task
        self._save()
        return task

    def all_tasks(self, status: Optional[str] = None) -> list[dict]:
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t["status"] == status]
        order = {"todo": 0, "wip": 1, "done": 2}
        tasks.sort(key=lambda t: (order.get(t["status"], 9), t["created_at"]))
        return tasks

    def update(self, task_id: str, **fields) -> Optional[dict]:
        task = self._find(task_id)
        if not task:
            return None
        for k, v in fields.items():
            if k in ("title", "description", "status"):
                task[k] = v
        task["updated_at"] = _now()
        self._save()
        return task

    def delete(self, task_id: str) -> bool:
        task = self._find(task_id)
        if not task:
            return False
        del self._tasks[task["id"]]
        self._save()
        return True

    def clear_done(self) -> int:
        before = len(self._tasks)
        self._tasks = {k: v for k, v in self._tasks.items() if v["status"] != "done"}
        self._save()
        return before - len(self._tasks)

    def _find(self, task_id: str) -> Optional[dict]:
        if task_id in self._tasks:
            return self._tasks[task_id]
        matches = [t for tid, t in self._tasks.items() if tid.startswith(task_id)]
        return matches[0] if len(matches) == 1 else None

    def _load(self) -> None:
        if TASKS_FILE.exists():
            try:
                self._tasks = json.loads(TASKS_FILE.read_text())
            except Exception:
                self._tasks = {}

    def _save(self) -> None:
        TASKS_FILE.write_text(json.dumps(self._tasks, indent=2, ensure_ascii=False))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_team(team_id: str, lead_agent_id: str, members: Optional[list[str]]) -> dict:
    """Crea un nuevo equipo de agentes."""
    team = AgentTeam(team_id, lead_agent_id, members)
    return team.to_dict()


def load_team(team_id: str) -> Optional[dict]:
    """Carga un equipo existente desde su archivo JSON."""
    team_file = CONFIG_DIR / f"teams/{team_id}.json"
    if team_file.exists():
        try:
            data = json.loads(team_file.read_text())
            team = AgentTeam(data["team_id"], data["lead_agent_id"], data.get("members"), str(team_file))
            return team.to_dict()
        except Exception:
            return None
    return None


def add_subtask(team_id: str, description: str, assign_to: str) -> dict:
    """Añade una subtask a un equipo existente."""
    team = load_team(team_id)
    if not team:
        return {"error": f"Equipo '{team_id}' no encontrado"}
    subtask = team.add_subtask(description, assign_to)
    team._save()
    return subtask


def complete_subtask(team_id: str, subtask_id: str, result: str) -> dict:
    """Marca una subtask como completada."""
    team = load_team(team_id)
    if not team:
        return {"error": f"Equipo '{team_id}' no encontrado"}
    team.complete_subtask(subtask_id, result)
    team._save()
    return {"status": "completed", "subtask_id": subtask_id, "result": result}


def get_pending_subtasks(team_id: str) -> list[dict]:
    """Devuelve las subtasks pendientes de un equipo."""
    team = load_team(team_id)
    if not team:
        return []
    return team.get_pending_subtasks()


def is_team_completed(team_id: str) -> bool:
    """Verifica si un equipo está completado."""
    team = load_team(team_id)
    if not team:
        return False
    return team.is_all_completed() and team.status == "completed"


def get_team_status(team_id: str) -> dict:
    """Devuelve el estado de un equipo."""
    team = load_team(team_id)
    if not team:
        return {"error": f"Equipo '{team_id}' no encontrado"}
    return {
        "team_id": team.team_id,
        "status": team.status,
        "members": team.members,
        "pending_subtasks": len(team.get_pending_subtasks()),
        "completed_subtasks": len([s for s in team.subtasks if s["status"] == "completed"]),
        "created_at": team.created_at,
        "completed_at": team.completed_at,
    }
