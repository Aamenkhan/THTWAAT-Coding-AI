"""
ui/agent_panel.py — Unified Agent Panel
Phase 4: Replaces AI Chat dock. Single scrollable stream displaying:
         User, Assistant (streaming), Tool Calls, Thinking, Pipeline Progress,
         Approvals, Git Diff, Errors. UI only — backend unchanged.
Phase 5: Pipeline stage rows + inline approval gate embedded in stream.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

# ── Colour palette ────────────────────────────────────────────────────────────
_BG     = "#0d1117"
_HDR_BG = "#161b22"
_FG     = "#e6edf3"
_MUTED  = "#8b949e"
_BLUE   = "#58a6ff"
_GREEN  = "#3fb950"
_RED    = "#f85149"
_YELLOW = "#d29922"
_ORANGE = "#f0883e"
_PURPLE = "#a371f7"


class AgentPanel(QtWidgets.QWidget):
    """
    Unified Agent Panel — replaces the old AI Chat dock widget.

    Public API (called by main_window):
        append_user(text)
        append_assistant_start()
        append_token(token)           ← streaming, appends plain text fast
        end_assistant()
        append_tool_call(name, args)
        append_thinking(text)
        append_pipeline_stage(stage_name, status, pct)
        show_approval_gate(message)
        hide_approval_gate()
        append_diff(diff_text)
        append_error(msg)
        append_system(msg)
        clear()
        set_input_enabled(enabled)
        set_stop_visible(visible)
        set_badge(text, color)

    Signals:
        message_submitted(str)   — user pressed Send
        stop_requested()         — user pressed Stop
        approval_decided(bool)   — Continue=True, Stop=False
        image_attached(str)      — path to attached image file
    """

    message_submitted = QtCore.Signal(str)
    stop_requested    = QtCore.Signal()
    approval_decided  = QtCore.Signal(bool)
    image_attached    = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._in_stream: bool = False   # True while streaming assistant tokens
        self._attached_image: Optional[str] = None
        self._build()

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar
        hdr = QtWidgets.QFrame()
        hdr.setStyleSheet(
            f"background-color: {_HDR_BG};"
            f"border-bottom: 1px solid #30363d;"
        )
        hdr.setFixedHeight(36)
        hdr_lay = QtWidgets.QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(12, 0, 12, 0)
        hdr_lay.setSpacing(8)

        title_lbl = QtWidgets.QLabel("🤖  Agent")
        title_lbl.setStyleSheet(
            f"color: {_FG}; font-weight: bold; font-size: 13px; background: transparent;"
        )

        self._badge = QtWidgets.QLabel("● Ready")
        self._badge.setStyleSheet(
            f"color: {_GREEN}; font-size: 10px; background: transparent;"
        )

        clr_btn = QtWidgets.QPushButton("Clear")
        clr_btn.setFixedSize(48, 22)
        clr_btn.setStyleSheet(f"""
            QPushButton {{
                background: #21262d; color: {_MUTED}; border: 1px solid #30363d;
                border-radius: 4px; font-size: 10px; padding: 0;
            }}
            QPushButton:hover {{ color: {_FG}; border-color: {_MUTED}; }}
        """)
        clr_btn.clicked.connect(self.clear)

        hdr_lay.addWidget(title_lbl)
        hdr_lay.addStretch()
        hdr_lay.addWidget(self._badge)
        hdr_lay.addWidget(clr_btn)
        root.addWidget(hdr)

        # ── Main message stream (scrollable QTextEdit) ───────────────────────
        self.stream = QtWidgets.QTextEdit()
        self.stream.setReadOnly(True)
        self.stream.setStyleSheet(f"""
            QTextEdit {{
                background-color: {_BG};
                color: {_FG};
                border: none;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 13px;
                padding: 8px 10px;
                selection-background-color: #264F78;
            }}
        """)
        self.stream.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        root.addWidget(self.stream, 1)

        # ── Approval gate (Phase 5) — hidden until pipeline requests it ──────
        self._gate = QtWidgets.QFrame()
        self._gate.setStyleSheet(
            "background-color: #1a1200;"
            "border-top: 1px solid #d29922;"
        )
        gate_lay = QtWidgets.QVBoxLayout(self._gate)
        gate_lay.setContentsMargins(12, 8, 12, 8)
        gate_lay.setSpacing(6)

        self._gate_label = QtWidgets.QLabel("")
        self._gate_label.setStyleSheet(
            f"color: {_YELLOW}; font-weight: bold; font-size: 11px;"
            f"background: transparent;"
        )
        self._gate_label.setWordWrap(True)

        gate_btns = QtWidgets.QHBoxLayout()
        gate_btns.setSpacing(8)

        self._approve_btn = QtWidgets.QPushButton("✅  Continue")
        self._approve_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_GREEN}; color: white; border: none;
                border-radius: 4px; padding: 5px 16px; font-weight: bold; font-size: 11px;
            }}
            QPushButton:hover {{ background-color: #2ea043; }}
        """)
        self._approve_btn.clicked.connect(lambda: self.approval_decided.emit(True))

        self._deny_btn = QtWidgets.QPushButton("✗  Stop")
        self._deny_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #21262d; color: white; border: 1px solid {_RED};
                border-radius: 4px; padding: 5px 16px; font-size: 11px;
            }}
            QPushButton:hover {{ background-color: {_RED}; }}
        """)
        self._deny_btn.clicked.connect(lambda: self.approval_decided.emit(False))

        gate_btns.addStretch()
        gate_btns.addWidget(self._approve_btn)
        gate_btns.addWidget(self._deny_btn)
        gate_btns.addStretch()

        gate_lay.addWidget(self._gate_label)
        gate_lay.addLayout(gate_btns)
        self._gate.hide()
        root.addWidget(self._gate)

        # ── Image preview strip ───────────────────────────────────────────────
        self._img_preview = QtWidgets.QLabel()
        self._img_preview.setMaximumHeight(90)
        self._img_preview.setStyleSheet(
            f"background: {_HDR_BG}; border-top: 1px solid #30363d; padding: 4px 10px;"
        )
        self._img_preview.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self._img_preview.hide()
        root.addWidget(self._img_preview)

        # ── Input row ─────────────────────────────────────────────────────────
        inp_frame = QtWidgets.QFrame()
        inp_frame.setStyleSheet(
            f"background-color: {_HDR_BG}; border-top: 1px solid #30363d;"
        )
        inp_lay = QtWidgets.QHBoxLayout(inp_frame)
        inp_lay.setContentsMargins(8, 6, 8, 6)
        inp_lay.setSpacing(4)

        self._attach_btn = QtWidgets.QPushButton("📎")
        self._attach_btn.setFixedSize(30, 30)
        self._attach_btn.setToolTip("Attach Image")
        self._attach_btn.setStyleSheet(f"""
            QPushButton {{
                background: #21262d; border: 1px solid #30363d;
                border-radius: 4px; font-size: 14px; padding: 0;
            }}
            QPushButton:hover {{ border-color: {_BLUE}; background: #2d333b; }}
        """)
        self._attach_btn.clicked.connect(self._on_attach)

        self.input = QtWidgets.QLineEdit()
        self.input.setPlaceholderText("Ask the agent…")
        self.input.setStyleSheet(f"""
            QLineEdit {{
                background: #21262d; color: {_FG};
                border: 1px solid #30363d; border-radius: 4px;
                padding: 4px 8px; font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {_BLUE}; }}
        """)
        self.input.returnPressed.connect(self._on_send)

        self._send_btn = QtWidgets.QPushButton("Send")
        self._send_btn.setFixedWidth(60)
        self._send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_BLUE}; color: white; border: none;
                border-radius: 4px; padding: 4px 10px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #79c0ff; }}
            QPushButton:disabled {{ background: #21262d; color: {_MUTED}; }}
        """)
        self._send_btn.clicked.connect(self._on_send)

        self._stop_btn = QtWidgets.QPushButton("⏹")
        self._stop_btn.setFixedWidth(34)
        self._stop_btn.setToolTip("Stop Generation")
        self._stop_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_RED}; color: white; border: none;
                border-radius: 4px; font-size: 13px; padding: 0;
            }}
            QPushButton:hover {{ background: #da3633; }}
        """)
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        self._stop_btn.hide()

        inp_lay.addWidget(self._attach_btn)
        inp_lay.addWidget(self.input, 1)
        inp_lay.addWidget(self._send_btn)
        inp_lay.addWidget(self._stop_btn)
        root.addWidget(inp_frame)

    # ── Public message API ────────────────────────────────────────────────────

    def append_user(self, text: str) -> None:
        """Render a user message block."""
        self._end_stream()
        html = (
            f'<div style="margin:6px 0 2px 0;">'
            f'<span style="color:{_BLUE};font-weight:bold;">You</span>'
            f'<span style="color:{_MUTED};font-size:11px;"> ›</span><br>'
            f'<span style="display:block;margin-left:4px;white-space:pre-wrap;">'
            f'{self._esc(text)}</span>'
            f'</div>'
            f'<div style="border-top:1px solid #21262d;margin:4px 0;"></div>'
        )
        self.stream.insertHtml(html)
        self._scroll_bottom()

    def append_assistant_start(self) -> None:
        """Insert the 'Agent ›' header to begin an assistant response block."""
        self._end_stream()
        html = (
            f'<div style="margin:6px 0 2px 0;">'
            f'<span style="color:#4EC9B0;font-weight:bold;">Agent</span>'
            f'<span style="color:{_MUTED};font-size:11px;"> ›</span><br>'
        )
        self.stream.insertHtml(html)
        self._in_stream = True
        self._scroll_bottom()

    def append_token(self, token: str) -> None:
        """Append a streamed token (plain text path — fast, no HTML overhead)."""
        self.stream.moveCursor(QtGui.QTextCursor.End)
        self.stream.insertPlainText(token)
        self._scroll_bottom()

    def end_assistant(self) -> None:
        """Close the current assistant response block."""
        if self._in_stream:
            self.stream.insertHtml(
                '</div>'
                '<div style="border-top:1px solid #21262d;margin:4px 0;"></div>'
            )
            self._in_stream = False
            self._scroll_bottom()

    def append_tool_call(self, name: str, args: str = "") -> None:
        """Render a tool-call row (yellow monospace block)."""
        self._end_stream()
        html = (
            f'<div style="margin:3px 0;background:#161b22;border-left:3px solid {_YELLOW};'
            f'padding:4px 8px;border-radius:4px;">'
            f'<span style="color:{_YELLOW};font-family:monospace;font-size:11px;">'
            f'🔧&nbsp;{self._esc(name)}({self._esc(args)})'
            f'</span></div>'
        )
        self.stream.insertHtml(html)
        self._scroll_bottom()

    def append_thinking(self, text: str) -> None:
        """Render a thinking/reasoning block (italic grey)."""
        self._end_stream()
        html = (
            f'<div style="margin:3px 0;background:#0d1117;border-left:3px solid {_MUTED};'
            f'padding:4px 8px;border-radius:4px;">'
            f'<span style="color:{_MUTED};font-style:italic;font-size:11px;">'
            f'💭&nbsp;{self._esc(text)}'
            f'</span></div>'
        )
        self.stream.insertHtml(html)
        self._scroll_bottom()

    def append_pipeline_stage(self, stage_name: str, status: str, pct: int = 0) -> None:
        """Phase 5 — Render a pipeline stage progress row inside the stream."""
        self._end_stream()
        icon  = {"active": "⏳", "done": "✅", "failed": "❌",
                 "waiting": "⏸", "skipped": "⏭"}.get(status, "○")
        color = {"active": _YELLOW, "done": _GREEN, "failed": _RED,
                 "waiting": _ORANGE, "skipped": _MUTED}.get(status, _MUTED)
        html = (
            f'<div style="margin:1px 0;padding:3px 8px;background:#161b22;border-radius:4px;">'
            f'<span style="color:{color};font-size:11px;font-family:monospace;">'
            f'{icon}&nbsp;[{pct:3d}%]&nbsp;&nbsp;{self._esc(stage_name)}'
            f'</span></div>'
        )
        self.stream.insertHtml(html)
        self._scroll_bottom()

    def show_approval_gate(self, message: str) -> None:
        """Phase 5 — Show the inline approval gate banner."""
        self._gate_label.setText(message)
        self._gate.show()
        self._scroll_bottom()

    def hide_approval_gate(self) -> None:
        """Hide the approval gate banner."""
        self._gate.hide()

    def append_diff(self, diff_text: str) -> None:
        """Render a unified diff (green additions, red deletions)."""
        self._end_stream()
        lines_html: list[str] = []
        for line in diff_text.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                color = _GREEN
            elif line.startswith("-") and not line.startswith("---"):
                color = _RED
            elif line.startswith("@@"):
                color = _BLUE
            else:
                color = _MUTED
            lines_html.append(
                f'<span style="color:{color};font-family:monospace;font-size:11px;">'
                f'{self._esc(line)}</span><br>'
            )
        html = (
            f'<div style="margin:4px 0;background:#0d1117;'
            f'border:1px solid #30363d;border-radius:4px;padding:6px 8px;">'
            f'{"".join(lines_html)}'
            f'</div>'
        )
        self.stream.insertHtml(html)
        self._scroll_bottom()

    def append_error(self, msg: str) -> None:
        """Render an error message (red left-bordered block)."""
        self._end_stream()
        html = (
            f'<div style="margin:3px 0;background:#1e0d0d;border-left:3px solid {_RED};'
            f'padding:4px 8px;border-radius:4px;">'
            f'<span style="color:{_RED};font-weight:bold;font-size:11px;">'
            f'⚠&nbsp;{self._esc(msg)}'
            f'</span></div>'
        )
        self.stream.insertHtml(html)
        self._scroll_bottom()

    def append_system(self, msg: str) -> None:
        """Render a system / info message (muted, centred dashes)."""
        self._end_stream()
        html = (
            f'<div style="margin:2px 0;text-align:center;">'
            f'<span style="color:{_MUTED};font-size:11px;">'
            f'── {self._esc(msg)} ──'
            f'</span></div>'
        )
        self.stream.insertHtml(html)
        self._scroll_bottom()

    def clear(self) -> None:
        """Clear the entire stream."""
        self._in_stream = False
        self.stream.clear()

    # ── State control ─────────────────────────────────────────────────────────

    def set_input_enabled(self, enabled: bool) -> None:
        self.input.setEnabled(enabled)
        self._send_btn.setEnabled(enabled)

    def set_stop_visible(self, visible: bool) -> None:
        if visible:
            self._stop_btn.show()
        else:
            self._stop_btn.hide()

    def set_badge(self, text: str, color: str = _GREEN) -> None:
        self._badge.setText(text)
        self._badge.setStyleSheet(
            f"color: {color}; font-size: 10px; background: transparent;"
        )

    # ── Input signal handlers ─────────────────────────────────────────────────

    def _on_send(self) -> None:
        text = self.input.text().strip()
        if not text and not self._attached_image:
            return
        self.input.clear()
        self.message_submitted.emit(text)

    def _on_attach(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Attach Image", "", "Images (*.png *.jpg *.jpeg)"
        )
        if path:
            self._attached_image = path
            pix = QtGui.QPixmap(path).scaledToHeight(80, QtCore.Qt.SmoothTransformation)
            self._img_preview.setPixmap(pix)
            self._img_preview.setToolTip(path)
            self._img_preview.show()
            self.image_attached.emit(path)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _scroll_bottom(self) -> None:
        bar = self.stream.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _end_stream(self) -> None:
        """Auto-close an open assistant stream before inserting a new block."""
        if self._in_stream:
            self.end_assistant()

    @staticmethod
    def _esc(text: str) -> str:
        """Minimal HTML escape for safe insertHtml() calls."""
        return (
            text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )
