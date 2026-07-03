"""
ui/chat.py — AI Chat Panel
Stage 3: Integrated with Planning Agent and Diff Viewer.
Supports: streaming chat, plan visualization, diff preview, Accept/Reject.
"""

import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import Any, Dict, List, Optional

import customtkinter as ctk
import markdown2
import pyperclip

from ai.diff_engine import PendingEdit


# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
_BG         = "#11151f"
_BOX_BG     = "#0d1117"
_FG         = "#e6edf3"
_MUTED      = "#8b949e"
_ACCENT     = "#58a6ff"
_GREEN      = "#3fb950"
_RED        = "#f85149"
_YELLOW     = "#d29922"
_STEP_DONE  = "#3fb950"
_STEP_FAIL  = "#f85149"
_STEP_RUN   = "#d29922"
_STEP_PEND  = "#8b949e"


class ChatPanel(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, width=420, fg_color=_BG)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._stop_generation = threading.Event()
        self._generation_thread: Optional[threading.Thread] = None

        # ---- Header ----
        header = ctk.CTkFrame(self, fg_color=_BG)
        header.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(header, text="AI Chat", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        self._mode_label = ctk.CTkLabel(
            header, text="● Chat", font=("Segoe UI", 10),
            text_color=_ACCENT,
        )
        self._mode_label.grid(row=0, column=1, sticky="e")

        # ---- Chat box ----
        self.chat_box = tk.Text(
            self, bg=_BOX_BG, fg=_FG, wrap="word",
            font=("Segoe UI", 11), relief="flat", padx=8, pady=6,
        )
        self.chat_box.grid(row=1, column=0, padx=10, pady=(0, 4), sticky="nsew")
        self._configure_tags()

        # ---- Mode toggle ----
        mode_row = ctk.CTkFrame(self, fg_color=_BG)
        mode_row.grid(row=2, column=0, padx=10, pady=(0, 2), sticky="ew")
        mode_row.grid_columnconfigure((0, 1), weight=1)
        self._mode_var = tk.StringVar(value="chat")
        ctk.CTkRadioButton(
            mode_row, text="💬 Chat", variable=self._mode_var, value="chat",
            command=self._on_mode_change,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkRadioButton(
            mode_row, text="🤖 Agent", variable=self._mode_var, value="agent",
            command=self._on_mode_change,
        ).grid(row=0, column=1, sticky="w")

        # ---- Input row ----
        bottom = ctk.CTkFrame(self, fg_color=_BG)
        bottom.grid(row=3, column=0, padx=10, pady=(0, 6), sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)

        self.input_box = ctk.CTkEntry(
            bottom, placeholder_text="Ask the AI to explain, fix, or create..."
        )
        self.input_box.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.input_box.bind("<Return>", self.send_message)

        self.send_btn = ctk.CTkButton(bottom, text="Send", width=60, command=self.send_message)
        self.send_btn.grid(row=0, column=1, padx=(0, 4))

        self.stop_btn = ctk.CTkButton(
            bottom, text="Stop", width=50, command=self.stop_generation, state="disabled"
        )
        self.stop_btn.grid(row=0, column=2)

        # ---- Action buttons ----
        actions = ctk.CTkFrame(self, fg_color=_BG)
        actions.grid(row=4, column=0, padx=10, pady=(0, 8), sticky="ew")
        actions.grid_columnconfigure((0, 1, 2), weight=1)

        self.copy_btn = ctk.CTkButton(
            actions, text="📋 Copy", command=self.copy_selected_code,
            state="disabled", width=90,
        )
        self.copy_btn.grid(row=0, column=0, padx=2)

        self.diff_btn = ctk.CTkButton(
            actions, text="🔍 Review Changes",
            command=self.open_diff_viewer, state="disabled",
            fg_color="#1f3a5f", hover_color="#2563eb", width=140,
        )
        self.diff_btn.grid(row=0, column=1, padx=2)

        self.clear_btn = ctk.CTkButton(
            actions, text="🗑 Clear", command=self.clear_chat, width=80,
        )
        self.clear_btn.grid(row=0, column=2, padx=2)

    # ------------------------------------------------------------------
    # Tag configuration
    # ------------------------------------------------------------------

    def _configure_tags(self) -> None:
        self.chat_box.tag_configure("role_user", font=("Segoe UI", 10, "bold"), foreground=_ACCENT)
        self.chat_box.tag_configure("role_ai",   font=("Segoe UI", 10, "bold"), foreground=_GREEN)
        self.chat_box.tag_configure("role_sys",  font=("Segoe UI", 10, "bold"), foreground=_YELLOW)
        self.chat_box.tag_configure("code",      font=("Consolas", 10), foreground="#86efac")
        self.chat_box.tag_configure("muted",     foreground=_MUTED)
        # Plan step tags
        self.chat_box.tag_configure("step_pending", foreground=_STEP_PEND)
        self.chat_box.tag_configure("step_running", foreground=_STEP_RUN)
        self.chat_box.tag_configure("step_done",    foreground=_STEP_DONE)
        self.chat_box.tag_configure("step_fail",    foreground=_STEP_FAIL)
        self.chat_box.tag_configure("plan_header",  font=("Segoe UI", 11, "bold"), foreground=_ACCENT)
        self.chat_box.tag_configure("diff_add",     foreground=_GREEN)
        self.chat_box.tag_configure("diff_remove",  foreground=_RED)
        self.chat_box.tag_configure("diff_hunk",    foreground=_ACCENT)

    # ------------------------------------------------------------------
    # Basic message rendering
    # ------------------------------------------------------------------

    def append_message(self, role: str, message: str) -> None:
        if role == "You":
            self.chat_box.insert(tk.END, f"{role}:\n", "role_user")
        elif role == "AI":
            self.chat_box.insert(tk.END, f"{role}:\n", "role_ai")
        else:
            self.chat_box.insert(tk.END, f"{role}:\n", "role_sys")
        self._insert_markdown(message)
        self.chat_box.insert(tk.END, "\n\n")
        self.chat_box.see(tk.END)

    def append_stream(self, chunk: str) -> None:
        self.chat_box.insert(tk.END, chunk)
        self.chat_box.see(tk.END)

    def clear_chat(self) -> None:
        self.chat_box.delete("1.0", tk.END)

    # ------------------------------------------------------------------
    # Plan visualization
    # ------------------------------------------------------------------

    def show_plan(self, plan_data: Dict[str, Any]) -> None:
        """Render a structured plan with step list in the chat box."""
        goal = plan_data.get("goal", "")
        steps = plan_data.get("steps", [])
        self.chat_box.insert(tk.END, f"🤖 Plan: {goal}\n", "plan_header")
        for s in steps:
            icon = {"done": "✅", "failed": "❌", "running": "⏳", "skipped": "⏭"}.get(
                s.get("status", "pending"), "○"
            )
            tag = {
                "done": "step_done", "failed": "step_fail",
                "running": "step_running",
            }.get(s.get("status", "pending"), "step_pending")
            line = f"  {icon} Step {s['step']}: {s['name']}  [{s['tool']}]\n"
            self.chat_box.insert(tk.END, line, tag)
        self.chat_box.insert(tk.END, "\n")
        self.chat_box.see(tk.END)

    def update_step_status(self, step_index: int, status: str, message: str) -> None:
        """Update the last occurrence of a step line in the chat box (best-effort)."""
        tag = {
            "done": "step_done", "failed": "step_fail",
            "running": "step_running",
        }.get(status, "step_pending")
        self.chat_box.insert(tk.END, f"  {message}\n", tag)
        self.chat_box.see(tk.END)

    # ------------------------------------------------------------------
    # Diff preview
    # ------------------------------------------------------------------

    def notify_pending_diffs(self, paths: List[str]) -> None:
        """Show a notification that file changes are ready for review."""
        if not paths:
            return
        n = len(paths)
        self.chat_box.insert(
            tk.END,
            f"\n📝 {n} file change(s) staged for review. Click 'Review Changes'.\n",
            "plan_header",
        )
        self.chat_box.see(tk.END)
        self.diff_btn.configure(state="normal")

    def open_diff_viewer(self) -> None:
        """Open the diff viewer dialog."""
        from ui.diff_viewer import DiffViewerDialog
        if not hasattr(self.app, "agent") or not self.app.agent:
            return
        pending = self.app.agent.pending_edits()
        if not pending:
            messagebox.showinfo("No Changes", "No pending file changes to review.")
            return

        def on_done():
            remaining = len(self.app.agent.pending_edits())
            if remaining == 0:
                self.diff_btn.configure(state="disabled")
            self.append_message("System", f"✅ Review done. {remaining} pending change(s) remaining.")

        DiffViewerDialog(self, self.app.agent.diff_engine, on_done=on_done)

    # ------------------------------------------------------------------
    # Mode switch
    # ------------------------------------------------------------------

    def _on_mode_change(self) -> None:
        mode = self._mode_var.get()
        if mode == "agent":
            self._mode_label.configure(text="● Agent", text_color=_GREEN)
            self.input_box.configure(placeholder_text="Describe a goal for the AI agent...")
        else:
            self._mode_label.configure(text="● Chat", text_color=_ACCENT)
            self.input_box.configure(placeholder_text="Ask the AI to explain, fix, or create...")

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def set_generating(self, generating: bool) -> None:
        state = "disabled" if generating else "normal"
        self.input_box.configure(state=state)
        self.send_btn.configure(state=state)
        self.stop_btn.configure(state="normal" if generating else "disabled")
        self.copy_btn.configure(state=state)
        if hasattr(self.app, "toolbar"):
            self.app.toolbar.set_state(not generating)
        if hasattr(self.app, "editor_panel"):
            self.app.editor_panel.set_enabled(not generating)

    def stop_generation(self) -> None:
        self._stop_generation.set()

    # ------------------------------------------------------------------
    # Clipboard
    # ------------------------------------------------------------------

    def copy_selected_code(self) -> None:
        try:
            selected = self.chat_box.get("sel.first", "sel.last")
            if selected:
                pyperclip.copy(selected)
                messagebox.showinfo("Copy", "Selected text copied to clipboard.")
        except tk.TclError:
            messagebox.showwarning("Copy", "No text selected.")

    # ------------------------------------------------------------------
    # Markdown rendering
    # ------------------------------------------------------------------

    def _insert_markdown(self, message: str) -> None:
        lines = message.splitlines() or [message]
        in_code = False
        code_lines = []
        for line in lines:
            if line.strip().startswith("```"):
                if in_code:
                    self.chat_box.insert(tk.END, "\n".join(code_lines) + "\n", "code")
                    code_lines = []
                    in_code = False
                else:
                    in_code = True
                    self.chat_box.insert(tk.END, "\n")
                continue
            if in_code:
                code_lines.append(line)
            else:
                self.chat_box.insert(tk.END, line + "\n")
        if in_code and code_lines:
            self.chat_box.insert(tk.END, "\n".join(code_lines) + "\n", "code")

    # ------------------------------------------------------------------
    # Send message — Chat mode OR Agent mode
    # ------------------------------------------------------------------

    def send_message(self, _event=None) -> None:
        if self._generation_thread and self._generation_thread.is_alive():
            return
        text = self.input_box.get().strip()
        if not text:
            return
        self.input_box.delete(0, tk.END)
        self.append_message("You", text)
        self._stop_generation = threading.Event()
        self.set_generating(True)

        mode = self._mode_var.get()
        if mode == "agent":
            self._generation_thread = threading.Thread(
                target=self._agent_worker, args=(text,), daemon=True
            )
        else:
            self._generation_thread = threading.Thread(
                target=self._chat_worker, args=(text,), daemon=True
            )
        self._generation_thread.start()

    # ------------------------------------------------------------------
    # Workers
    # ------------------------------------------------------------------

    def _chat_worker(self, text: str) -> None:
        """Standard streaming chat worker."""
        try:
            # Legacy command shortcuts
            if text.lower().startswith("create project"):
                prompt = text[len("create project"):].strip()
                self.app.generate_project(prompt)
                self.chat_box.after(0, self.set_generating, False)
                return

            if text.lower().startswith("edit files"):
                parts = text[len("edit files"):].strip()
                edits = {}
                for entry in parts.split(";"):
                    if "|" not in entry:
                        continue
                    path, content = entry.split("|", 1)
                    edits[path.strip()] = content.strip()
                if edits:
                    self.app.preview_file_edits(edits)
                    self.chat_box.after(0, self.set_generating, False)
                    return

            if text.lower().startswith("create file"):
                parts = text.split("|", 1)
                if len(parts) == 2:
                    path = parts[0].split("create file", 1)[1].strip()
                    content = parts[1].strip()
                    self.app.agent.create_file(path, content)
                    if hasattr(self.app, "refresh_project"):
                        self.app.refresh_project()
                    self.chat_box.after(0, self.append_message, "AI", f"Created file: {path}")
                    self.chat_box.after(0, self.set_generating, False)
                    return

            context_text = None
            if hasattr(self.app, "current_path") and self.app.current_path:
                try:
                    with open(self.app.current_path, "r", encoding="utf-8", errors="ignore") as fh:
                        context_text = fh.read()
                except Exception:
                    pass
            if hasattr(self.app, "project_index") and self.app.project_index and not context_text:
                context_text = self.app.project_index.build_context(text)
            if hasattr(self.app, "plugin_manager") and self.app.plugin_manager:
                text = self.app.plugin_manager.run_plugins(text, app=self.app)

            self.chat_box.after(0, self.append_message, "AI", "")
            chunks = self.app.agent.stream_chat(
                text, context=context_text, stop_event=self._stop_generation
            )
            for chunk in chunks:
                if self._stop_generation.is_set():
                    break
                self.chat_box.after(0, lambda v=chunk: self.append_stream(v))

        except Exception as exc:
            err = str(exc)
            self.chat_box.after(0, lambda e=err: self.append_message("AI", f"Error: {e}"))
        finally:
            self.chat_box.after(0, self.set_generating, False)

    def _agent_worker(self, goal: str) -> None:
        """Autonomous agent worker: plan → execute → diff review."""
        def on_progress(event: str, message: str, data: Optional[Dict] = None):
            data = data or {}
            if event == "plan_ready":
                plan_data = data.get("plan", {})
                self.chat_box.after(0, self.show_plan, plan_data)
            elif event in ("step_start", "step_done", "step_fail"):
                step = data.get("step", "?")
                self.chat_box.after(0, self.update_step_status, step, event.replace("step_", ""), message)
            elif event == "complete":
                paths = data.get("pending_edits", [])
                self.chat_box.after(0, self.notify_pending_diffs, paths)
            elif event == "error":
                self.chat_box.after(0, self.append_message, "System", f"⚠ {message}")

        try:
            self.chat_box.after(0, self.append_message, "Agent", f"🎯 Goal: {goal}\nBuilding plan...")
            self.app.agent.plan_and_execute(
                goal,
                on_progress=on_progress,
                stop_event=self._stop_generation,
            )
        except Exception as exc:
            err = str(exc)
            self.chat_box.after(0, lambda e=err: self.append_message("Agent", f"Error: {e}"))
        finally:
            self.chat_box.after(0, self.set_generating, False)
