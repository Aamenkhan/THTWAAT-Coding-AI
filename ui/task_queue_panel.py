"""
ui/task_queue_panel.py — Task Queue Panel (Feature 10)
Shows all tasks with stage badges, progress bars, and cancel buttons.
"""

import tkinter as tk
from typing import Any, Dict, Optional

import customtkinter as ctk

from ai.task_queue import Task, TaskStage


_BG      = "#0d1117"
_HDR_BG  = "#161b22"
_FG      = "#e6edf3"
_MUTED   = "#8b949e"
_GREEN   = "#3fb950"
_RED     = "#f85149"
_YELLOW  = "#d29922"
_BLUE    = "#58a6ff"

_STAGE_COLORS = {
    "QUEUED":    _MUTED,
    "ANALYZE":   _BLUE,
    "EDIT":      _YELLOW,
    "TEST":      "#a371f7",
    "REVIEW":    "#79c0ff",
    "COMPLETE":  _GREEN,
    "FAILED":    _RED,
    "CANCELLED": _MUTED,
}


class TaskRow(ctk.CTkFrame):
    """A single row showing one task's progress."""

    def __init__(self, parent, task: Task, on_cancel):
        super().__init__(parent, fg_color="#161b22", corner_radius=6)
        self.task = task
        self._on_cancel = on_cancel
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(1, weight=1)

        # Stage badge
        stage_color = _STAGE_COLORS.get(self.task.stage.name, _MUTED)
        self.stage_label = ctk.CTkLabel(
            self,
            text=self.task.stage_label,
            font=("Segoe UI", 9, "bold"),
            text_color=stage_color,
            width=100,
        )
        self.stage_label.grid(row=0, column=0, padx=8, pady=(6, 0), sticky="w")

        # Goal text
        goal_short = self.task.goal[:60] + ("..." if len(self.task.goal) > 60 else "")
        ctk.CTkLabel(
            self, text=goal_short,
            font=("Segoe UI", 10), anchor="w", text_color=_FG,
        ).grid(row=0, column=1, padx=4, pady=(6, 0), sticky="ew")

        # Cancel button
        self.cancel_btn = ctk.CTkButton(
            self, text="✕", width=28, height=24,
            fg_color="transparent", hover_color=_RED,
            command=lambda: self._on_cancel(self.task.task_id),
        )
        self.cancel_btn.grid(row=0, column=2, padx=4, pady=(6, 0))
        if self.task.is_done:
            self.cancel_btn.configure(state="disabled", text="—")

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(self, height=6)
        self.progress_bar.set(self.task.progress / 100)
        self.progress_bar.grid(row=1, column=0, columnspan=2, padx=8, pady=(4, 2), sticky="ew")

        # Progress label
        self.progress_label = ctk.CTkLabel(
            self,
            text=f"{self.task.progress}%  {self.task.message[:50]}",
            font=("Segoe UI", 9), text_color=_MUTED, anchor="w",
        )
        self.progress_label.grid(row=2, column=0, columnspan=3, padx=8, pady=(0, 6), sticky="w")

    def update(self, task: Task) -> None:
        """Update progress display for the given task."""
        self.task = task
        stage_color = _STAGE_COLORS.get(task.stage.name, _MUTED)
        self.stage_label.configure(text=task.stage_label, text_color=stage_color)
        self.progress_bar.set(task.progress / 100)
        self.progress_label.configure(
            text=f"{task.progress}%  {task.message[:50]}"
        )
        if task.is_done:
            self.cancel_btn.configure(state="disabled", text="—")


class TaskQueuePanel(ctk.CTkFrame):
    """
    Panel displaying all queued/running/done tasks.
    Auto-refreshes via on_progress callbacks.
    """

    def __init__(self, parent, app):
        super().__init__(parent, fg_color=_BG)
        self.app = app
        self._rows: Dict[str, TaskRow] = {}
        self.grid_columnconfigure(0, weight=1)
        self._build()

    def _build(self) -> None:
        # Header
        header = ctk.CTkFrame(self, fg_color=_HDR_BG, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header, text="🗂 Task Queue",
            font=("Segoe UI", 13, "bold"),
        ).grid(row=0, column=0, padx=12, pady=8, sticky="w")

        self._count_label = ctk.CTkLabel(
            header, text="0 tasks", font=("Segoe UI", 10), text_color=_MUTED,
        )
        self._count_label.grid(row=0, column=1, padx=8, sticky="e")

        ctk.CTkButton(
            header, text="Clear Done", width=90, command=self._clear_done,
        ).grid(row=0, column=2, padx=8)

        # Scrollable task list
        self._task_scroll = ctk.CTkScrollableFrame(self, fg_color=_BG, label_text="")
        self._task_scroll.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        self._task_scroll.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # New task input
        input_frame = ctk.CTkFrame(self, fg_color=_HDR_BG, corner_radius=0)
        input_frame.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        input_frame.grid_columnconfigure(0, weight=1)

        self._new_task_entry = ctk.CTkEntry(
            input_frame, placeholder_text="New goal for task queue..."
        )
        self._new_task_entry.grid(row=0, column=0, padx=8, pady=8, sticky="ew")
        self._new_task_entry.bind("<Return>", self._add_task)

        ctk.CTkButton(
            input_frame, text="▶ Queue", width=80,
            command=self._add_task,
        ).grid(row=0, column=1, padx=(0, 8))

        self._empty_label = ctk.CTkLabel(
            self._task_scroll,
            text="No tasks queued.\nUse the input below to add a goal.",
            font=("Segoe UI", 11), text_color=_MUTED,
        )
        self._empty_label.pack(pady=40)

    def _add_task(self, _event=None) -> None:
        goal = self._new_task_entry.get().strip()
        if not goal:
            return
        self._new_task_entry.delete(0, tk.END)

        if not hasattr(self.app, "task_queue") or self.app.task_queue is None:
            return

        task = self.app.task_queue.enqueue(goal, on_progress=self._on_progress)
        self._add_row(task)

    def _on_progress(self, task_id: str, pct: int, stage_label: str, message: str) -> None:
        """Called from background thread — schedule GUI update on main thread."""
        task = self.app.task_queue.get(task_id) if hasattr(self.app, "task_queue") else None
        if task:
            self.after(0, self._update_row, task)

    def _add_row(self, task: Task) -> None:
        if self._empty_label.winfo_ismapped():
            self._empty_label.pack_forget()
        row = TaskRow(self._task_scroll, task, on_cancel=self._cancel_task)
        row.pack(fill="x", padx=4, pady=3)
        self._rows[task.task_id] = row
        self._refresh_count()

    def _update_row(self, task: Task) -> None:
        row = self._rows.get(task.task_id)
        if row:
            row.update(task)

    def _cancel_task(self, task_id: str) -> None:
        if hasattr(self.app, "task_queue") and self.app.task_queue:
            self.app.task_queue.cancel(task_id)

    def _clear_done(self) -> None:
        if hasattr(self.app, "task_queue") and self.app.task_queue:
            self.app.task_queue.clear_done()
        # Remove done rows from UI
        done = [tid for tid, row in self._rows.items() if row.task.is_done]
        for tid in done:
            self._rows[tid].destroy()
            del self._rows[tid]
        if not self._rows:
            self._empty_label.pack(pady=40)
        self._refresh_count()

    def _refresh_count(self) -> None:
        total = len(self._rows)
        active = sum(1 for r in self._rows.values() if not r.task.is_done)
        self._count_label.configure(text=f"{active} active / {total} total")
