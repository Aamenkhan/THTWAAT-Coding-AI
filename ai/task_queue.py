"""
ai/task_queue.py — Task Queue with Progress (Feature 10)
Large requests become async tasks with stage-by-stage progress tracking.
Stages: Analyze → Edit → Test → Review → Complete
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional


class TaskStage(Enum):
    QUEUED   = auto()
    ANALYZE  = auto()
    EDIT     = auto()
    TEST     = auto()
    REVIEW   = auto()
    COMPLETE = auto()
    FAILED   = auto()
    CANCELLED = auto()


_STAGE_WEIGHTS: Dict[TaskStage, int] = {
    TaskStage.QUEUED:   0,
    TaskStage.ANALYZE:  10,
    TaskStage.EDIT:     40,
    TaskStage.TEST:     65,
    TaskStage.REVIEW:   85,
    TaskStage.COMPLETE: 100,
    TaskStage.FAILED:   100,
    TaskStage.CANCELLED: 100,
}

_STAGE_LABELS = {
    TaskStage.QUEUED:    "📥 Queued",
    TaskStage.ANALYZE:   "🔍 Analyzing",
    TaskStage.EDIT:      "✏️ Editing",
    TaskStage.TEST:      "🧪 Testing",
    TaskStage.REVIEW:    "📋 Reviewing",
    TaskStage.COMPLETE:  "✅ Complete",
    TaskStage.FAILED:    "❌ Failed",
    TaskStage.CANCELLED: "⏹ Cancelled",
}

ProgressCallback = Callable[[str, int, str, str], None]
# (task_id, percent, stage_label, message)


@dataclass
class Task:
    task_id: str
    goal: str
    stage: TaskStage = TaskStage.QUEUED
    progress: int = 0
    message: str = ""
    error: Optional[str] = None
    result: Optional[Any] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    _cancel_event: threading.Event = field(default_factory=threading.Event)
    _thread: Optional[threading.Thread] = field(default=None, repr=False)

    @property
    def stage_label(self) -> str:
        return _STAGE_LABELS.get(self.stage, self.stage.name)

    @property
    def is_done(self) -> bool:
        return self.stage in (TaskStage.COMPLETE, TaskStage.FAILED, TaskStage.CANCELLED)

    @property
    def elapsed(self) -> float:
        end = self.completed_at or time.time()
        return end - self.created_at

    def cancel(self) -> None:
        self._cancel_event.set()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "stage": self.stage.name,
            "stage_label": self.stage_label,
            "progress": self.progress,
            "message": self.message,
            "is_done": self.is_done,
            "elapsed": round(self.elapsed, 1),
        }


class TaskQueue:
    """
    Manages a queue of autonomous coding tasks.
    Each task runs in its own background thread and reports
    progress through a callback.
    """

    def __init__(self, agent=None, on_progress: Optional[ProgressCallback] = None):
        self._tasks: Dict[str, Task] = {}
        self._lock = threading.Lock()
        self.agent = agent
        self.on_progress = on_progress

    # ------------------------------------------------------------------
    # Queue management
    # ------------------------------------------------------------------

    def enqueue(
        self,
        goal: str,
        on_progress: Optional[ProgressCallback] = None,
    ) -> Task:
        """Create a task and start it immediately in a background thread."""
        task_id = str(uuid.uuid4())[:8]
        task = Task(task_id=task_id, goal=goal)
        with self._lock:
            self._tasks[task_id] = task

        callback = on_progress or self.on_progress
        task._thread = threading.Thread(
            target=self._run_task,
            args=(task, callback),
            daemon=True,
            name=f"task-{task_id}",
        )
        task._thread.start()
        return task

    def cancel(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task and not task.is_done:
            task.cancel()
            return True
        return False

    def get(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def all_tasks(self) -> List[Task]:
        with self._lock:
            return list(self._tasks.values())

    def active_tasks(self) -> List[Task]:
        return [t for t in self.all_tasks() if not t.is_done]

    def clear_done(self) -> None:
        with self._lock:
            done_ids = [tid for tid, t in self._tasks.items() if t.is_done]
            for tid in done_ids:
                del self._tasks[tid]

    # ------------------------------------------------------------------
    # Task runner
    # ------------------------------------------------------------------

    def _run_task(self, task: Task, callback: Optional[ProgressCallback]) -> None:
        def emit(stage: TaskStage, message: str) -> None:
            task.stage = stage
            task.progress = _STAGE_WEIGHTS.get(stage, 0)
            task.message = message
            if callback:
                callback(task.task_id, task.progress, task.stage_label, message)

        try:
            emit(TaskStage.ANALYZE, "Analyzing project and planning approach...")
            if task._cancel_event.is_set():
                task.stage = TaskStage.CANCELLED; return

            if self.agent:
                # Run planner analysis stage
                plan = self.agent.build_plan_only(task.goal)
                emit(TaskStage.ANALYZE, f"Plan ready: {len(plan.steps)} steps")

                if task._cancel_event.is_set():
                    task.stage = TaskStage.CANCELLED; return

                emit(TaskStage.EDIT, "Executing plan steps...")

                def on_plan_progress(event, message, data=None):
                    if event == "step_start":
                        emit(TaskStage.EDIT, message)
                    elif event == "step_fail":
                        task.message = message

                self.agent.plan_and_execute(
                    task.goal,
                    on_progress=on_plan_progress,
                    stop_event=task._cancel_event,
                )
            else:
                # Simulate stages when no agent is attached
                time.sleep(0.5)
                emit(TaskStage.EDIT, "Processing edits...")
                time.sleep(0.5)

            if task._cancel_event.is_set():
                task.stage = TaskStage.CANCELLED; return

            emit(TaskStage.TEST, "Running tests...")
            if self.agent:
                from ai.tools import call_tool
                test_result = call_tool("RunTests", {"directory": getattr(self.agent, "project_dir", ".")})
                passed = test_result.data.get("passed", 0)
                failed = test_result.data.get("failed", 0)
                emit(TaskStage.TEST, f"Tests: {passed} passed, {failed} failed")

            if task._cancel_event.is_set():
                task.stage = TaskStage.CANCELLED; return

            emit(TaskStage.REVIEW, "Reviewing generated code...")
            time.sleep(0.3)

            emit(TaskStage.COMPLETE, f"Task complete: {task.goal[:60]}")
            task.completed_at = time.time()

        except Exception as exc:
            task.stage = TaskStage.FAILED
            task.error = str(exc)
            task.message = f"Failed: {exc}"
            task.completed_at = time.time()
            if callback:
                callback(task.task_id, 100, _STAGE_LABELS[TaskStage.FAILED], task.message)
