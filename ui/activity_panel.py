"""
ui/activity_panel.py — Agent Activity Panel (Feature 17)
Live log of all agent actions, tool calls, and events.
"""

import html
from datetime import datetime
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

_BG     = "#0d1117"
_HDR_BG = "#161b22"
_FG     = "#e6edf3"
_MUTED  = "#8b949e"
_GREEN  = "#3fb950"
_RED    = "#f85149"
_YELLOW = "#d29922"
_BLUE   = "#58a6ff"
_PURPLE = "#a371f7"


class ActivityPanel(QtWidgets.QFrame):
    """
    Real-time log panel showing what the agent is doing:
    tool calls, plan steps, file operations, errors.
    Color-coded by event type.
    """
    
    # Thread-safe signal for cross-thread logging
    log_requested = QtCore.Signal(str, str)

    def __init__(self, parent=None, app=None):
        super().__init__(parent)
        self.app = app
        self._event_count = 0
        
        self.log_requested.connect(self._insert)
        
        self.setStyleSheet(f"QFrame {{ background-color: {_BG}; }}")
        self._build()

    def _build(self) -> None:
        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QtWidgets.QFrame(self)
        header.setStyleSheet(f"QFrame {{ background-color: {_HDR_BG}; }}")
        header_layout = QtWidgets.QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(8)
        
        title_lbl = QtWidgets.QLabel("⚡ Agent Activity")
        title_lbl.setStyleSheet(f"color: {_FG}; font-family: 'Segoe UI'; font-size: 13px; font-weight: bold;")
        
        self._count_label = QtWidgets.QLabel("0 events")
        self._count_label.setStyleSheet(f"color: {_MUTED}; font-family: 'Segoe UI'; font-size: 10px;")
        
        clear_btn = QtWidgets.QPushButton("Clear")
        clear_btn.setFixedWidth(70)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #21262d;
                color: {_FG};
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 4px;
            }}
            QPushButton:hover {{
                background-color: #30363d;
            }}
        """)
        clear_btn.clicked.connect(self.clear)
        
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        header_layout.addWidget(self._count_label)
        header_layout.addWidget(clear_btn)
        
        layout.addWidget(header, 0, 0)
        
        # Log text widget
        self._log = QtWidgets.QTextEdit(self)
        self._log.setReadOnly(True)
        self._log.setLineWrapMode(QtWidgets.QTextEdit.WidgetWidth)
        self._log.setStyleSheet(f"""
            QTextEdit {{
                background-color: {_BG};
                color: {_FG};
                font-family: Consolas, 'Courier New', monospace;
                font-size: 10px;
                border: none;
                padding: 4px;
            }}
        """)
        
        layout.addWidget(self._log, 1, 0)
        layout.setRowStretch(1, 1)

    def log(self, message: str, level: str = "info") -> None:
        """Add an event to the activity log. Thread-safe (uses signals)."""
        self.log_requested.emit(message, level)

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
        self._log.clear()
        self._event_count = 0
        self._count_label.setText("0 events")

    @QtCore.Slot(str, str)
    def _insert(self, message: str, level: str) -> None:
        self._event_count += 1
        ts = datetime.now().strftime("%H:%M:%S")
        
        # Tags mapping
        colors = {
            "tool": _BLUE,
            "success": _GREEN,
            "error": _RED,
            "warn": _YELLOW,
            "plan": _PURPLE,
            "info": _FG,
            "diff": _YELLOW
        }
        color = colors.get(level, _FG)
        bold = level in ["tool", "plan"]
        
        font_weight = "bold" if bold else "normal"
        
        # Escape HTML characters to prevent rendering issues with < or >
        escaped_message = html.escape(message)
        
        # We use a span-based approach for appending rich text
        html_str = f'<span style="color: {_MUTED}; font-size: 9pt;">[{ts}] </span>' \
                   f'<span style="color: {color}; font-weight: {font_weight};">{escaped_message}</span>'
        
        self._log.append(html_str)
        
        # Auto-scroll to bottom
        scrollbar = self._log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
        self._count_label.setText(f"{self._event_count} events")
