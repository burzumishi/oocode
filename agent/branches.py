"""Ramas de conversación: snapshots guardados en disco para retomar puntos anteriores."""
import json
import re
from datetime import datetime, timezone
from typing import Optional
from config import CONFIG_DIR

BRANCHES_DIR = CONFIG_DIR / "branches"


class BranchManager:
    def __init__(self, agent_id: str):
        self.dir = BRANCHES_DIR / agent_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self._index_file = self.dir / "index.json"

    def save(self, name: str, messages: list[dict], summary: str = "") -> str:
        slug = _slugify(name)
        data = {
            "name": name,
            "slug": slug,
            "created_at": _now(),
            "message_count": len(messages),
            "summary": summary,
            "messages": messages,
        }
        path = self.dir / f"{slug}.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        self._update_index(slug, name, len(messages))
        return str(path)

    def all_branches(self) -> list[dict]:
        if not self._index_file.exists():
            return []
        try:
            return sorted(
                json.loads(self._index_file.read_text()).values(),
                key=lambda b: b.get("created_at", ""),
                reverse=True,
            )
        except Exception:
            return []

    def load(self, name: str) -> Optional[dict]:
        slug = _slugify(name)
        path = self.dir / f"{slug}.json"
        if not path.exists():
            # intenta prefijo
            matches = list(self.dir.glob(f"{slug}*.json"))
            if len(matches) == 1:
                path = matches[0]
            else:
                return None
        try:
            return json.loads(path.read_text())
        except Exception:
            return None

    def delete(self, name: str) -> bool:
        slug = _slugify(name)
        path = self.dir / f"{slug}.json"
        if not path.exists():
            return False
        path.unlink()
        idx = {}
        if self._index_file.exists():
            try:
                idx = json.loads(self._index_file.read_text())
            except Exception:
                pass
        idx.pop(slug, None)
        self._index_file.write_text(json.dumps(idx, indent=2, ensure_ascii=False))
        return True

    def _update_index(self, slug: str, name: str, msg_count: int) -> None:
        idx = {}
        if self._index_file.exists():
            try:
                idx = json.loads(self._index_file.read_text())
            except Exception:
                pass
        idx[slug] = {
            "slug": slug,
            "name": name,
            "created_at": _now(),
            "message_count": msg_count,
        }
        self._index_file.write_text(json.dumps(idx, indent=2, ensure_ascii=False))


def _slugify(name: str) -> str:
    return re.sub(r"[^\w\-]", "_", name.lower().strip()) or "branch"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
