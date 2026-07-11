"""
ui/pipeline_panel.py — Pipeline Visualization Panel
Shows the 10-stage autonomous pipeline as a live flowchart.
Handles pause/resume at approval gates, displays stage details.
"""

import threading
from typing import Any, Dict, Optional

from PySide6 import QtCore, QtGui, QtWidgets

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

class StageCard(QtWidgets.QFrame):
    """A single stage card in the pipeline visualization."""

    def __init__(self, parent, stage: Stage):
        super().__init__(parent)
        self.stage = stage
        self._status = "pending"
        
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {_INACTIVE};
                border-radius: 8px;
                border: 0px solid transparent;
            }}
        """)
        
        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        
        # Icon
        self._icon_lbl = QtWidgets.QLabel(_STAGE_ICONS.get(stage, "○"))
        self._icon_lbl.setStyleSheet(f"font-family: 'Segoe UI'; font-size: 14px; background: transparent; border: none;")
        self._icon_lbl.setFixedWidth(30)
        layout.addWidget(self._icon_lbl, 0, 0, QtCore.Qt.AlignLeft)
        
        # Label
        self._name_lbl = QtWidgets.QLabel(_STAGE_LABELS.get(stage, stage.name))
        self._name_lbl.setStyleSheet(f"color: {_FG}; font-family: 'Segoe UI'; font-size: 10px; font-weight: bold; background: transparent; border: none;")
        layout.addWidget(self._name_lbl, 0, 1, QtCore.Qt.AlignLeft)
        
        # Status badge
        self._status_lbl = QtWidgets.QLabel("●  pending")
        self._status_lbl.setStyleSheet(f"color: {_MUTED}; font-family: 'Segoe UI'; font-size: 9px; background: transparent; border: none;")
        self._status_lbl.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self._status_lbl.setFixedWidth(80)
        layout.addWidget(self._status_lbl, 0, 2, QtCore.Qt.AlignRight)
        
        # Message (hidden until active)
        self._msg_lbl = QtWidgets.QLabel("")
        self._msg_lbl.setStyleSheet(f"color: {_MUTED}; font-family: 'Segoe UI'; font-size: 9px; background: transparent; border: none;")
        self._msg_lbl.setWordWrap(True)
        layout.addWidget(self._msg_lbl, 1, 0, 1, 3)
        self._msg_lbl.hide()
        
        layout.setColumnStretch(1, 1)

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
        self._status_lbl.setText(labels.get(status, status))
        self._status_lbl.setStyleSheet(f"color: {color}; font-family: 'Segoe UI'; font-size: 9px; background: transparent; border: none;")
        
        if status == "active":
            self.setStyleSheet(f"QFrame {{ background-color: {_HDR_BG}; border: 1px solid {stage_color}; border-radius: 8px; }}")
            self._name_lbl.setStyleSheet(f"color: {stage_color}; font-family: 'Segoe UI'; font-size: 10px; font-weight: bold; background: transparent; border: none;")
        elif status == "done":
            self.setStyleSheet(f"QFrame {{ background-color: #0d2118; border: 1px solid {_GREEN}; border-radius: 8px; }}")
            self._name_lbl.setStyleSheet(f"color: {_GREEN}; font-family: 'Segoe UI'; font-size: 10px; font-weight: bold; background: transparent; border: none;")
        elif status == "failed":
            self.setStyleSheet(f"QFrame {{ background-color: #1e0d0d; border: 1px solid {_RED}; border-radius: 8px; }}")
            self._name_lbl.setStyleSheet(f"color: {_RED}; font-family: 'Segoe UI'; font-size: 10px; font-weight: bold; background: transparent; border: none;")
        elif status == "waiting":
            self.setStyleSheet(f"QFrame {{ background-color: #1a1200; border: 1px solid {_YELLOW}; border-radius: 8px; }}")
            self._name_lbl.setStyleSheet(f"color: {_YELLOW}; font-family: 'Segoe UI'; font-size: 10px; font-weight: bold; background: transparent; border: none;")
        else:
            self.setStyleSheet(f"QFrame {{ background-color: {_INACTIVE}; border: 0px solid transparent; border-radius: 8px; }}")
            self._name_lbl.setStyleSheet(f"color: {_FG}; font-family: 'Segoe UI'; font-size: 10px; font-weight: bold; background: transparent; border: none;")
            
        if message:
            self._msg_lbl.setText(message[:80])
            self._msg_lbl.show()
        else:
            self._msg_lbl.setText("")
            self._msg_lbl.hide()


class PipelinePanel(QtWidgets.QFrame):
    """
    Left-sidebar pipeline panel showing all 10 stages with live status.
    Provides approval buttons at REVIEW and COMMIT gates.
    """
    
    stage_update_requested = QtCore.Signal(object, object, str, dict)
    pipeline_done_requested = QtCore.Signal(object)
    show_gate_requested = QtCore.Signal(str)
    hide_gate_requested = QtCore.Signal()

    def __init__(self, parent=None, app=None):
        super().__init__(parent)
        self.app = app
        self._run: Optional[PipelineRun] = None
        self._gate_event: Optional[threading.Event] = None
        self._gate_decision: bool = False
        self._cards: Dict[Stage, StageCard] = {}
        
        self.setMinimumWidth(270)
        self.setStyleSheet(f"QFrame {{ background-color: {_BG}; }}")
        
        self.stage_update_requested.connect(self._on_stage_update)
        self.pipeline_done_requested.connect(self._on_pipeline_done)
        self.show_gate_requested.connect(self._show_gate)
        self.hide_gate_requested.connect(self._hide_gate)

        self._build()

    def _build(self) -> None:
        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QtWidgets.QFrame(self)
        header.setStyleSheet(f"QFrame {{ background-color: {_HDR_BG}; }}")
        header_layout = QtWidgets.QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 10, 8)
        
        title_lbl = QtWidgets.QLabel("🚀 Pipeline")
        title_lbl.setStyleSheet(f"color: {_FG}; font-family: 'Segoe UI'; font-size: 13px; font-weight: bold;")
        
        self._progress_label = QtWidgets.QLabel("idle")
        self._progress_label.setStyleSheet(f"color: {_MUTED}; font-family: 'Segoe UI'; font-size: 10px;")
        self._progress_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        header_layout.addWidget(self._progress_label)
        
        layout.addWidget(header, 0, 0)
        
        # Progress bar
        self._pbar = QtWidgets.QProgressBar(self)
        self._pbar.setFixedHeight(4)
        self._pbar.setTextVisible(False)
        self._pbar.setRange(0, 100)
        self._pbar.setValue(0)
        self._pbar.setStyleSheet(f"""
            QProgressBar {{ background-color: {_HDR_BG}; border: none; }}
            QProgressBar::chunk {{ background-color: {_BLUE}; }}
        """)
        layout.addWidget(self._pbar, 1, 0)
        
        # Goal input
        goal_frame = QtWidgets.QFrame(self)
        goal_frame.setStyleSheet(f"QFrame {{ background-color: {_HDR_BG}; }}")
        goal_layout = QtWidgets.QHBoxLayout(goal_frame)
        goal_layout.setContentsMargins(8, 6, 8, 6)
        goal_layout.setSpacing(8)
        
        self._goal_entry = QtWidgets.QLineEdit(goal_frame)
        self._goal_entry.setPlaceholderText("Describe your goal...")
        self._goal_entry.setFixedHeight(32)
        self._goal_entry.setStyleSheet(f"QLineEdit {{ background-color: {_BG}; color: {_FG}; border: 1px solid {_CONNECTOR}; border-radius: 4px; padding-left: 8px; }}")
        self._goal_entry.returnPressed.connect(self._start)
        
        self._start_btn = QtWidgets.QPushButton("▶ Run", goal_frame)
        self._start_btn.setFixedWidth(70)
        self._start_btn.setFixedHeight(32)
        self._start_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {_GREEN}; color: white; font-weight: bold; border-radius: 4px; border: none; }}
            QPushButton:hover {{ background-color: #2ea043; }}
            QPushButton:disabled {{ background-color: {_MUTED}; }}
        """)
        self._start_btn.clicked.connect(self._start)
        
        goal_layout.addWidget(self._goal_entry, 1)
        goal_layout.addWidget(self._start_btn)
        
        layout.addWidget(goal_frame, 2, 0)
        
        # Stage cards scrollable area
        scroll_area = QtWidgets.QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet(f"QScrollArea {{ border: none; background-color: {_BG}; }}")
        
        self._stages_frame = QtWidgets.QFrame(scroll_area)
        self._stages_frame.setStyleSheet(f"QFrame {{ background-color: {_BG}; }}")
        stages_layout = QtWidgets.QVBoxLayout(self._stages_frame)
        stages_layout.setContentsMargins(4, 4, 4, 4)
        stages_layout.setSpacing(2)
        
        visible_stages = [s for s in _PIPELINE_ORDER if s != Stage.DONE]
        for i, stage in enumerate(visible_stages):
            card = StageCard(self._stages_frame, stage)
            stages_layout.addWidget(card)
            self._cards[stage] = card
            
            # Connector arrow
            if i < len(visible_stages) - 1:
                arrow = QtWidgets.QLabel("↓")
                arrow.setAlignment(QtCore.Qt.AlignCenter)
                arrow.setStyleSheet(f"color: {_CONNECTOR}; font-family: 'Segoe UI'; font-size: 12px;")
                stages_layout.addWidget(arrow)
                
        stages_layout.addStretch()
        scroll_area.setWidget(self._stages_frame)
        
        layout.addWidget(scroll_area, 3, 0)
        layout.setRowStretch(3, 1)
        
        # Approval gate controls
        self._gate_frame = QtWidgets.QFrame(self)
        self._gate_frame.setStyleSheet("QFrame { background-color: #1a1200; }")
        gate_layout = QtWidgets.QVBoxLayout(self._gate_frame)
        gate_layout.setContentsMargins(10, 8, 10, 8)
        gate_layout.setSpacing(8)
        
        self._gate_label = QtWidgets.QLabel("")
        self._gate_label.setStyleSheet(f"color: {_YELLOW}; font-family: 'Segoe UI'; font-size: 10px; font-weight: bold; background: transparent;")
        self._gate_label.setWordWrap(True)
        self._gate_label.setAlignment(QtCore.Qt.AlignCenter)
        
        gate_btn_row = QtWidgets.QFrame(self._gate_frame)
        gate_btn_row.setStyleSheet("background: transparent;")
        gate_btn_layout = QtWidgets.QHBoxLayout(gate_btn_row)
        gate_btn_layout.setContentsMargins(0, 0, 0, 0)
        gate_btn_layout.setSpacing(8)
        
        self._approve_btn = QtWidgets.QPushButton("✅ Continue")
        self._approve_btn.setFixedWidth(110)
        self._approve_btn.setStyleSheet(f"QPushButton {{ background-color: {_GREEN}; color: white; border-radius: 4px; padding: 4px; }} QPushButton:hover {{ background-color: #2ea043; }}")
        self._approve_btn.clicked.connect(self._approve)
        
        self._deny_btn = QtWidgets.QPushButton("✗ Stop")
        self._deny_btn.setFixedWidth(80)
        self._deny_btn.setStyleSheet(f"QPushButton {{ background-color: #21262d; color: white; border-radius: 4px; padding: 4px; border: 1px solid {_RED}; }} QPushButton:hover {{ background-color: {_RED}; }}")
        self._deny_btn.clicked.connect(self._deny)
        
        gate_btn_layout.addStretch()
        gate_btn_layout.addWidget(self._approve_btn)
        gate_btn_layout.addWidget(self._deny_btn)
        gate_btn_layout.addStretch()
        
        gate_layout.addWidget(self._gate_label)
        gate_layout.addWidget(gate_btn_row)
        
        layout.addWidget(self._gate_frame, 4, 0)
        self._gate_frame.hide()

    # ------------------------------------------------------------------
    # Start pipeline
    # ------------------------------------------------------------------

    def _start(self, _event=None) -> None:
        goal = self._goal_entry.text().strip()
        if not goal:
            return
        if not hasattr(self.app, "agent") or not self.app.agent:
            return

        self._start_btn.setEnabled(False)
        self._goal_entry.setEnabled(False)
        self._reset_cards()
        self._pbar.setValue(0)
        self._progress_label.setText("Starting...")
        self._progress_label.setStyleSheet(f"color: {_MUTED}; font-family: 'Segoe UI'; font-size: 10px;")

        from ai.pipeline import Pipeline
        pipeline = Pipeline(self.app.agent)

        def on_progress(run: PipelineRun, stage: Stage, msg: str, data: Dict):
            self.stage_update_requested.emit(run, stage, msg, data)

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
            self.pipeline_done_requested.emit(result)

        threading.Thread(target=run_pipeline, daemon=True).start()

    # ------------------------------------------------------------------
    # Progress updates
    # ------------------------------------------------------------------

    @QtCore.Slot(object, object, str, dict)
    def _on_stage_update(self, run: PipelineRun, stage: Stage, msg: str, data: Dict) -> None:
        self._run = run
        # Update progress bar
        self._pbar.setValue(int(run.progress_percent))
        self._progress_label.setText(f"{int(run.progress_percent)}%  {run.stage_label}")

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

    @QtCore.Slot(object)
    def _on_pipeline_done(self, run: PipelineRun) -> None:
        self._gate_frame.hide()
        self._start_btn.setEnabled(True)
        self._goal_entry.setEnabled(True)
        self._pbar.setValue(100 if run.stage == Stage.DONE else int(run.progress_percent))

        # Final card states
        for s, result in run.stage_results.items():
            card = self._cards.get(s)
            if card:
                card.set_status("done" if result.ok else "failed", result.message)

        if run.stage == Stage.DONE:
            self._progress_label.setText("✅ Complete")
            self._progress_label.setStyleSheet(f"color: {_GREEN}; font-family: 'Segoe UI'; font-size: 10px;")
            # Show summary in chat panel
            if hasattr(self.app, "chat_panel") and run.summary:
                self.app.chat_panel.append_message("Agent", run.summary)
        elif run.stage == Stage.CANCELLED:
            self._progress_label.setText("⏹ Cancelled")
            self._progress_label.setStyleSheet(f"color: {_MUTED}; font-family: 'Segoe UI'; font-size: 10px;")
        elif run.stage == Stage.FAILED:
            self._progress_label.setText("❌ Failed")
            self._progress_label.setStyleSheet(f"color: {_RED}; font-family: 'Segoe UI'; font-size: 10px;")

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
        self.show_gate_requested.emit(msg)

        # Block pipeline thread — wait up to 10 minutes
        event.wait(timeout=600)
        self.hide_gate_requested.emit()
        return self._gate_decision

    @QtCore.Slot(str)
    def _show_gate(self, message: str) -> None:
        self._gate_label.setText(message)
        self._gate_frame.show()

    @QtCore.Slot()
    def _hide_gate(self) -> None:
        self._gate_frame.hide()

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
