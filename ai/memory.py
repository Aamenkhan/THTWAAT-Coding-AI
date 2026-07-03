"""
ai/memory.py — Session Memory (Feature 6)
Remembers: current task, recent edits, recent prompts,
current files, git branch, and current errors across the session.
"""

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


_MAX_RECENT = 20


class SessionMemory:
    """
    Persistent in-session memory store.
    Optionally serializes to a JSON file for cross-session persistence.
    Thread-safe.
    """

    def __init__(self, persist_path: Optional[str] = None):
        self._lock = threading.Lock()
        self._persist_path = Path(persist_path) if persist_path else None
        self._data: Dict[str, Any] = {
            "current_task": None,
            "recent_edits": [],          # [{path, timestamp, description}]
            "recent_prompts": [],         # [{prompt, timestamp, mode}]
            "current_files": [],          # [path, ...]
            "git_branch": "unknown",
            "current_errors": [],         # [{error, timestamp, context}]
            "agent_runs": [],             # [{goal, timestamp, status}]
        }
        if self._persist_path and self._persist_path.exists():
            self._load()

    # ------------------------------------------------------------------
    # Current task
    # ------------------------------------------------------------------

    def set_task(self, task: str) -> None:
        with self._lock:
            self._data["current_task"] = task
            self._data["agent_runs"].append({
                "goal": task, "timestamp": _ts(), "status": "running"
            })
            self._trim("agent_runs")
        self._save()

    def complete_task(self, status: str = "done") -> None:
        with self._lock:
            if self._data["agent_runs"]:
                self._data["agent_runs"][-1]["status"] = status
        self._save()

    def get_task(self) -> Optional[str]:
        return self._data.get("current_task")

    # ------------------------------------------------------------------
    # Recent edits
    # ------------------------------------------------------------------

    def add_edit(self, path: str, description: str = "") -> None:
        with self._lock:
            self._data["recent_edits"].append({
                "path": path,
                "timestamp": _ts(),
                "description": description,
            })
            self._trim("recent_edits")
        self._save()

    def recent_edits(self, n: int = 5) -> List[Dict]:
        return self._data["recent_edits"][-n:]

    # ------------------------------------------------------------------
    # Recent prompts
    # ------------------------------------------------------------------

    def add_prompt(self, prompt: str, mode: str = "chat") -> None:
        with self._lock:
            self._data["recent_prompts"].append({
                "prompt": prompt[:400],
                "timestamp": _ts(),
                "mode": mode,
            })
            self._trim("recent_prompts")
        self._save()

    def recent_prompts(self, n: int = 5) -> List[Dict]:
        return self._data["recent_prompts"][-n:]

    # ------------------------------------------------------------------
    # Current files
    # ------------------------------------------------------------------

    def set_current_files(self, paths: List[str]) -> None:
        with self._lock:
            self._data["current_files"] = paths[:10]
        self._save()

    def add_current_file(self, path: str) -> None:
        with self._lock:
            files = self._data["current_files"]
            if path not in files:
                files.insert(0, path)
            self._data["current_files"] = files[:10]
        self._save()

    def get_current_files(self) -> List[str]:
        return self._data["current_files"]

    # ------------------------------------------------------------------
    # Git branch
    # ------------------------------------------------------------------

    def set_branch(self, branch: str) -> None:
        with self._lock:
            self._data["git_branch"] = branch
        self._save()

    def get_branch(self) -> str:
        return self._data.get("git_branch", "unknown")

    # ------------------------------------------------------------------
    # Errors
    # ------------------------------------------------------------------

    def add_error(self, error: str, context: str = "") -> None:
        with self._lock:
            self._data["current_errors"].append({
                "error": error[:800],
                "timestamp": _ts(),
                "context": context[:200],
            })
            self._trim("current_errors")
        self._save()

    def clear_errors(self) -> None:
        with self._lock:
            self._data["current_errors"] = []
        self._save()

    def recent_errors(self, n: int = 3) -> List[Dict]:
        return self._data["current_errors"][-n:]

    # ------------------------------------------------------------------
    # Context injection
    # ------------------------------------------------------------------

    def get_summary(self) -> str:
        """Return a compact memory summary for injection into AI context."""
        lines = ["## Session Memory"]
        task = self._data.get("current_task")
        if task:
            lines.append(f"Current task: {task}")
        branch = self._data.get("git_branch", "unknown")
        lines.append(f"Git branch: {branch}")
        files = self._data.get("current_files", [])
        if files:
            lines.append("Open files: " + ", ".join(Path(f).name for f in files[:5]))
        edits = self._data.get("recent_edits", [])[-3:]
        if edits:
            lines.append("Recent edits: " + ", ".join(Path(e["path"]).name for e in edits))
        prompts = self._data.get("recent_prompts", [])[-3:]
        if prompts:
            lines.append("Recent prompts: " + " | ".join(p["prompt"][:60] for p in prompts))
        errors = self._data.get("current_errors", [])[-2:]
        if errors:
            lines.append("Recent errors: " + " | ".join(e["error"][:80] for e in errors))
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data)

    def clear_all(self) -> None:
        with self._lock:
            for key in self._data:
                if isinstance(self._data[key], list):
                    self._data[key] = []
                else:
                    self._data[key] = None
        self._save()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self) -> None:
        if not self._persist_path:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._persist_path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load(self) -> None:
        try:
            loaded = json.loads(self._persist_path.read_text(encoding="utf-8"))
            self._data.update(loaded)
        except Exception:
            pass

    def _trim(self, key: str) -> None:
        if len(self._data[key]) > _MAX_RECENT:
            self._data[key] = self._data[key][-_MAX_RECENT:]


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
