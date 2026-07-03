"""
ui/activity_panel.py — Agent Activity Panel (Feature 17)
Live log of all agent actions, tool calls, and events.
"""

import tkinter as tk
from datetime import datetime
from typing import Optional

import customtkinter as ctk


_BG     = "#0d1117"
_HDR_BG = "#161b22"
_FG     = "#e6edf3"
_MUTED  = "#8b949e"
_GREEN  = "#3fb950"
_RED    = "#f85149"
_YELLOW = "#d29922"
_BLUE   = "#58a6ff"
_PURPLE = "#a371f7"


class ActivityPanel(ctk.CTkFrame):
    """
    Real-time log panel showing what the agent is doing:
    tool calls, plan steps, file operations, errors.
    Color-coded by event type.
    """

    def __init__(self, parent, app=None):
        super().__init__(parent, fg_color=_BG)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._event_count = 0
        self._build()

    def _build(self) -> None:
        # Header
        header = ctk.CTkFrame(self, fg_color=_HDR_BG, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header, text="⚡ Agent Activity",
            font=("Segoe UI", 13, "bold"),
        ).grid(row=0, column=0, padx=12, pady=8, sticky="w")

        self._count_label = ctk.CTkLabel(
            header, text="0 events", font=("Segoe UI", 10), text_color=_MUTED,
        )
        self._count_label.grid(row=0, column=1, sticky="e", padx=8)

        ctk.CTkButton(
            header, text="Clear", width=70,
            command=self.clear,
        ).grid(row=0, column=2, padx=8)

        # Log text widget
        self._log = tk.Text(
            self, bg=_BG, fg=_FG,
            font=("Consolas", 10), wrap="word",
            relief="flat", state="disabled", padx=6, pady=4,
        )
        self._log.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)

        scroll = ctk.CTkScrollbar(self, command=self._log.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self._log.configure(yscrollcommand=scroll.set)

        # Tags
        self._log.tag_configure("ts",      foreground=_MUTED,   font=("Consolas", 9))
        self._log.tag_configure("tool",    foreground=_BLUE,    font=("Consolas", 10, "bold"))
        self._log.tag_configure("success", foreground=_GREEN)
        self._log.tag_configure("error",   foreground=_RED)
        self._log.tag_configure("warn",    foreground=_YELLOW)
        self._log.tag_configure("plan",    foreground=_PURPLE,  font=("Consolas", 10, "bold"))
        self._log.tag_configure("info",    foreground=_FG)
        self._log.tag_configure("diff",    foreground=_YELLOW)

    def log(self, message: str, level: str = "info") -> None:
        """Add an event to the activity log. Thread-safe (uses after())."""
        self.after(0, self._insert, message, level)

    def log_tool(self, tool_name: str, args: dict, ok: bool) -> None:
        status = "✅" if ok else "❌"
        self.log(f"{status} [{tool_name}] args={args}", "tool" if ok else "error")

    def log_step(self, step_index: int, name: str, status: str) -> None:
        icons = {"done": "✅", "failed": "❌", "running": "⏳", "skipped": "⏭"}
        icon = icons.get(status, "○")
        self.log(f"{icon} Step {step_index}: {name}", "plan")

    def log_diff(self, path: str, lines_changed: int) -> None:
        self.log(f"📝 Diff staged: {path} ({lines_changed} lines)", "diff")

    def log_error(self, error: str) -> None:
        self.log(f"💥 {error}", "error")

    def clear(self) -> None:
        self._log.configure(state="normal")
        self._log.delete("1.0", tk.END)
        self._log.configure(state="disabled")
        self._event_count = 0
        self._count_label.configure(text="0 events")

    def _insert(self, message: str, level: str) -> None:
        self._event_count += 1
        ts = datetime.now().strftime("%H:%M:%S")
        self._log.configure(state="normal")
        self._log.insert(tk.END, f"[{ts}] ", "ts")
        self._log.insert(tk.END, f"{message}\n", level)
        self._log.see(tk.END)
        self._log.configure(state="disabled")
        self._count_label.configure(text=f"{self._event_count} events")
