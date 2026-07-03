"""
ui/pipeline_panel.py — Pipeline Visualization Panel
Shows the 10-stage autonomous pipeline as a live flowchart.
Handles pause/resume at approval gates, displays stage details.
"""

import threading
import tkinter as tk
from typing import Any, Dict, Optional

import customtkinter as ctk

from ai.pipeline import Stage, PipelineRun, _STAGE_ICONS, _STAGE_LABELS, _PIPELINE_ORDER


_BG        = "#0d1117"
_HDR_BG    = "#161b22"
_FG        = "#e6edf3"
_MUTED     = "#8b949e"
_GREEN     = "#3fb950"
_RED       = "#f85149"
_YELLOW    = "#d29922"
_BLUE      = "#58a6ff"
_PURPLE    = "#a371f7"
_INACTIVE  = "#21262d"
_CONNECTOR = "#30363d"

_STAGE_COLORS = {
    Stage.ANALYZE:        _BLUE,
    Stage.PLAN:           _PURPLE,
    Stage.RELEVANT_FILES: _BLUE,
    Stage.CREATE_DIFFS:   _YELLOW,
    Stage.REVIEW:         "#f0883e",
    Stage.RUN_TESTS:      _PURPLE,
    Stage.FIX_ERRORS:     _RED,
    Stage.REVIEW_CODE:    "#79c0ff",
    Stage.COMMIT:         "#f0883e",
    Stage.SUMMARY:        _GREEN,
    Stage.DONE:           _GREEN,
    Stage.FAILED:         _RED,
    Stage.CANCELLED:      _MUTED,
}

_STATUS_COLORS = {
    "pending":  _MUTED,
    "active":   _YELLOW,
    "done":     _GREEN,
    "failed":   _RED,
    "skipped":  _MUTED,
    "waiting":  "#f0883e",
}


class StageCard(ctk.CTkFrame):
    """A single stage card in the pipeline visualization."""

    def __init__(self, parent, stage: Stage):
        super().__init__(parent, fg_color=_INACTIVE, corner_radius=8)
        self.stage = stage
        self._status = "pending"
        self.grid_columnconfigure(1, weight=1)

        # Icon
        self._icon_lbl = ctk.CTkLabel(
            self, text=_STAGE_ICONS.get(stage, "○"),
            font=("Segoe UI", 14), width=30,
        )
        self._icon_lbl.grid(row=0, column=0, padx=(8, 4), pady=6, sticky="w")

        # Label
        self._name_lbl = ctk.CTkLabel(
            self,
            text=_STAGE_LABELS.get(stage, stage.name),
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        self._name_lbl.grid(row=0, column=1, padx=4, pady=6, sticky="ew")

        # Status badge
        self._status_lbl = ctk.CTkLabel(
            self, text="●  pending",
            font=("Segoe UI", 9), text_color=_MUTED, width=80,
        )
        self._status_lbl.grid(row=0, column=2, padx=8, pady=6, sticky="e")

        # Message (hidden until active)
        self._msg_lbl = ctk.CTkLabel(
            self, text="", font=("Segoe UI", 9),
            text_color=_MUTED, anchor="w", wraplength=220,
        )
        self._msg_lbl.grid(row=1, column=0, columnspan=3, padx=12, pady=(0, 0), sticky="ew")

    def set_status(self, status: str, message: str = "") -> None:
        self._status = status
        color = _STATUS_COLORS.get(status, _MUTED)
        stage_color = _STAGE_COLORS.get(self.stage, _BLUE)
        labels = {
            "pending": "●  pending",
            "active":  "⏳ running",
            "done":    "✅ done",
            "failed":  "❌ failed",
            "skipped": "⏭ skipped",
            "waiting": "⏸ waiting",
        }
        self._status_lbl.configure(text=labels.get(status, status), text_color=color)
        if status == "active":
            self.configure(fg_color=_HDR_BG, border_color=stage_color, border_width=1)
            self._name_lbl.configure(text_color=stage_color)
        elif status == "done":
            self.configure(fg_color="#0d2118", border_color=_GREEN, border_width=1)
            self._name_lbl.configure(text_color=_GREEN)
        elif status == "failed":
            self.configure(fg_color="#1e0d0d", border_color=_RED, border_width=1)
            self._name_lbl.configure(text_color=_RED)
        elif status == "waiting":
            self.configure(fg_color="#1a1200", border_color=_YELLOW, border_width=1)
            self._name_lbl.configure(text_color=_YELLOW)
        else:
            self.configure(fg_color=_INACTIVE, border_width=0)
            self._name_lbl.configure(text_color=_FG)
        if message:
            self._msg_lbl.configure(text=message[:80], pady=4)
        else:
            self._msg_lbl.configure(text="", pady=0)


class PipelinePanel(ctk.CTkFrame):
    """
    Left-sidebar pipeline panel showing all 10 stages with live status.
    Provides approval buttons at REVIEW and COMMIT gates.
    """

    def __init__(self, parent, app):
        super().__init__(parent, fg_color=_BG, width=270)
        self.app = app
        self._run: Optional[PipelineRun] = None
        self._gate_event: Optional[threading.Event] = None
        self._gate_decision: bool = False
        self._cards: Dict[Stage, StageCard] = {}

        self.grid_columnconfigure(0, weight=1)
        self._build()

    def _build(self) -> None:
        # Header
        header = ctk.CTkFrame(self, fg_color=_HDR_BG, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header, text="🚀 Pipeline",
            font=("Segoe UI", 13, "bold"),
        ).grid(row=0, column=0, padx=12, pady=8, sticky="w")

        self._progress_label = ctk.CTkLabel(
            header, text="idle", font=("Segoe UI", 10), text_color=_MUTED,
        )
        self._progress_label.grid(row=0, column=1, sticky="e", padx=10)

        # Progress bar
        self._pbar = ctk.CTkProgressBar(self, height=4)
        self._pbar.set(0)
        self._pbar.grid(row=1, column=0, sticky="ew", padx=0, pady=0)

        # Goal input
        goal_frame = ctk.CTkFrame(self, fg_color=_HDR_BG, corner_radius=0)
        goal_frame.grid(row=2, column=0, sticky="ew")
        goal_frame.grid_columnconfigure(0, weight=1)

        self._goal_entry = ctk.CTkEntry(
            goal_frame, placeholder_text="Describe your goal...",
            height=32,
        )
        self._goal_entry.grid(row=0, column=0, padx=8, pady=6, sticky="ew")
        self._goal_entry.bind("<Return>", self._start)

        self._start_btn = ctk.CTkButton(
            goal_frame, text="▶ Run", width=70, command=self._start,
            fg_color=_GREEN, hover_color="#2ea043",
        )
        self._start_btn.grid(row=0, column=1, padx=(0, 8))

        # Stage cards scrollable area
        self._stages_frame = ctk.CTkScrollableFrame(self, fg_color=_BG, label_text="")
        self._stages_frame.grid(row=3, column=0, sticky="nsew", padx=4, pady=4)
        self._stages_frame.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        visible_stages = [s for s in _PIPELINE_ORDER if s != Stage.DONE]
        for i, stage in enumerate(visible_stages):
            card = StageCard(self._stages_frame, stage)
            card.grid(row=i * 2, column=0, sticky="ew", padx=4, pady=2)
            self._cards[stage] = card

            # Connector arrow between stages
            if i < len(visible_stages) - 1:
                arrow = ctk.CTkLabel(
                    self._stages_frame, text="↓",
                    font=("Segoe UI", 12), text_color=_CONNECTOR,
                )
                arrow.grid(row=i * 2 + 1, column=0)

        # Approval gate controls (hidden until needed)
        self._gate_frame = ctk.CTkFrame(self, fg_color="#1a1200", corner_radius=0)
        self._gate_label = ctk.CTkLabel(
            self._gate_frame,
            text="", font=("Segoe UI", 10, "bold"),
            text_color=_YELLOW, wraplength=220,
        )
        self._gate_label.pack(padx=10, pady=(8, 4))

        gate_btn_row = ctk.CTkFrame(self._gate_frame, fg_color="transparent")
        gate_btn_row.pack(pady=(0, 8))
        self._approve_btn = ctk.CTkButton(
            gate_btn_row, text="✅ Continue", width=110,
            fg_color=_GREEN, hover_color="#2ea043",
            command=self._approve,
        )
        self._approve_btn.pack(side="left", padx=4)
        self._deny_btn = ctk.CTkButton(
            gate_btn_row, text="✗ Stop", width=80,
            fg_color="#21262d", hover_color=_RED,
            command=self._deny,
        )
        self._deny_btn.pack(side="left", padx=4)

    # ------------------------------------------------------------------
    # Start pipeline
    # ------------------------------------------------------------------

    def _start(self, _event=None) -> None:
        goal = self._goal_entry.get().strip()
        if not goal:
            return
        if not hasattr(self.app, "agent") or not self.app.agent:
            return

        self._start_btn.configure(state="disabled")
        self._goal_entry.configure(state="disabled")
        self._reset_cards()
        self._pbar.set(0)
        self._progress_label.configure(text="Starting...")

        from ai.pipeline import Pipeline
        pipeline = Pipeline(self.app.agent)

        def on_progress(run: PipelineRun, stage: Stage, msg: str, data: Dict):
            self.after(0, self._on_stage_update, run, stage, msg, data)

        def on_approval(run: PipelineRun, gate: Stage) -> bool:
            return self._wait_for_approval(run, gate)

        def run_pipeline():
            stop = threading.Event()
            result = pipeline.start(
                goal,
                on_progress=on_progress,
                on_approval=on_approval,
                stop_event=stop,
            )
            self.after(0, self._on_pipeline_done, result)

        threading.Thread(target=run_pipeline, daemon=True).start()

    # ------------------------------------------------------------------
    # Progress updates
    # ------------------------------------------------------------------

    def _on_stage_update(self, run: PipelineRun, stage: Stage, msg: str, data: Dict) -> None:
        self._run = run
        # Update progress bar
        self._pbar.set(run.progress_percent / 100)
        self._progress_label.configure(text=f"{run.progress_percent}%  {run.stage_label}")

        # Update card statuses
        terminal = {Stage.DONE, Stage.FAILED, Stage.CANCELLED}
        for s, card in self._cards.items():
            if s == stage and stage not in terminal:
                if stage in {Stage.REVIEW, Stage.COMMIT}:
                    card.set_status("waiting", msg)
                else:
                    card.set_status("active", msg)
            elif s in run.stage_results:
                result = run.stage_results[s]
                card.set_status("done" if result.ok else "failed", result.message)

        # Post to activity panel if available
        if hasattr(self.app, "activity_panel") and self.app.activity_panel:
            self.app.activity_panel.log(msg, "plan" if stage in _PIPELINE_ORDER else "info")

    def _on_pipeline_done(self, run: PipelineRun) -> None:
        self._gate_frame.grid_forget()
        self._start_btn.configure(state="normal")
        self._goal_entry.configure(state="normal")
        self._pbar.set(1.0 if run.stage == Stage.DONE else run.progress_percent / 100)

        # Final card states
        for s, result in run.stage_results.items():
            card = self._cards.get(s)
            if card:
                card.set_status("done" if result.ok else "failed", result.message)

        if run.stage == Stage.DONE:
            self._progress_label.configure(text="✅ Complete", text_color=_GREEN)
            # Show summary in chat panel
            if hasattr(self.app, "chat_panel") and run.summary:
                self.app.chat_panel.append_message("Agent", run.summary)
        elif run.stage == Stage.CANCELLED:
            self._progress_label.configure(text="⏹ Cancelled", text_color=_MUTED)
        elif run.stage == Stage.FAILED:
            self._progress_label.configure(text="❌ Failed", text_color=_RED)

    # ------------------------------------------------------------------
    # Approval gate (blocking call from background thread)
    # ------------------------------------------------------------------

    def _wait_for_approval(self, run: PipelineRun, gate: Stage) -> bool:
        """Block the pipeline thread until user clicks Continue or Stop."""
        event = threading.Event()
        self._gate_event = event
        self._gate_decision = False

        gate_messages = {
            Stage.REVIEW: f"⏸ {len(run.pending_edits)} file change(s) ready. Review and continue?",
            Stage.COMMIT: f"⏸ Commit: '{run.commit_message[:60]}' — proceed?",
        }
        msg = gate_messages.get(gate, f"⏸ Approval needed for: {gate.name}")
        self.after(0, self._show_gate, msg)

        # Block pipeline thread — wait up to 10 minutes
        event.wait(timeout=600)
        self.after(0, self._hide_gate)
        return self._gate_decision

    def _show_gate(self, message: str) -> None:
        self._gate_label.configure(text=message)
        self._gate_frame.grid(row=4, column=0, sticky="ew", pady=(0, 4))

    def _hide_gate(self) -> None:
        self._gate_frame.grid_forget()

    def _approve(self) -> None:
        self._gate_decision = True
        if self._gate_event:
            self._gate_event.set()

    def _deny(self) -> None:
        self._gate_decision = False
        if self._gate_event:
            self._gate_event.set()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _reset_cards(self) -> None:
        for card in self._cards.values():
            card.set_status("pending", "")
