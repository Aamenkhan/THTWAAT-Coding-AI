"""
ui/terminal_approval_dialog.py — Terminal Approval Dialog (Feature 7)
Shows proposed command with risk level, Run/Skip buttons,
and streams live output after approval.
"""

import threading
import tkinter as tk
from typing import Optional

import customtkinter as ctk

from ai.security import SecurityGuard, RiskLevel


_BG       = "#0d1117"
_HDR_BG   = "#161b22"
_FG       = "#e6edf3"
_MUTED    = "#8b949e"
_GREEN    = "#3fb950"
_RED      = "#f85149"
_YELLOW   = "#d29922"
_BLUE     = "#58a6ff"
_CODE_BG  = "#090d13"


class TerminalApprovalDialog(ctk.CTkToplevel):
    """
    Modal dialog that presents a proposed terminal command to the user.
    After approval, streams live stdout/stderr output.

    Usage:
        dialog = TerminalApprovalDialog(parent, command, reason, on_decision)
    """

    def __init__(
        self,
        parent,
        command: str,
        reason: str = "",
        on_decision: Optional[callable] = None,
        cwd: str = ".",
    ):
        super().__init__(parent)
        self.command = command
        self.reason = reason
        self.cwd = cwd
        self.on_decision = on_decision
        self._decided = False
        self._approved = False

        self.title("Terminal — Command Approval Required")
        self.geometry("700x480")
        self.configure(fg_color=_BG)
        self.resizable(True, True)
        self.grab_set()

        # Evaluate risk
        guard = SecurityGuard()
        risk, risk_reason = guard.evaluate(command)

        self._build_ui(risk, risk_reason)

    def _build_ui(self, risk: RiskLevel, risk_reason: str) -> None:
        # Header
        header = ctk.CTkFrame(self, fg_color=_HDR_BG, corner_radius=0)
        header.pack(fill="x")
        ctk.CTkLabel(
            header, text="⚡ Terminal Command Request",
            font=("Segoe UI", 14, "bold"),
        ).pack(side="left", padx=14, pady=10)

        risk_color = {
            RiskLevel.SAFE: _GREEN,
            RiskLevel.LOW: _BLUE,
            RiskLevel.MEDIUM: _YELLOW,
            RiskLevel.HIGH: _RED,
            RiskLevel.CRITICAL: "#ff0000",
        }.get(risk, _MUTED)

        ctk.CTkLabel(
            header,
            text=SecurityGuard.describe_risk(risk),
            font=("Segoe UI", 10),
            text_color=risk_color,
        ).pack(side="right", padx=14)

        # Reason
        if self.reason:
            ctk.CTkLabel(
                self, text=f"Reason: {self.reason}",
                font=("Segoe UI", 11), text_color=_MUTED, anchor="w",
            ).pack(fill="x", padx=14, pady=(8, 0))

        # Command box
        ctk.CTkLabel(self, text="Command:", anchor="w", font=("Segoe UI", 11)).pack(fill="x", padx=14, pady=(8, 2))
        cmd_frame = ctk.CTkFrame(self, fg_color=_CODE_BG, corner_radius=6)
        cmd_frame.pack(fill="x", padx=14, pady=(0, 6))
        ctk.CTkLabel(
            cmd_frame,
            text=self.command,
            font=("Consolas", 11),
            text_color=_GREEN,
            anchor="w",
            wraplength=640,
        ).pack(padx=10, pady=8, anchor="w")

        if risk_reason:
            ctk.CTkLabel(
                self, text=f"⚠ {risk_reason}",
                font=("Segoe UI", 10), text_color=_YELLOW, anchor="w",
            ).pack(fill="x", padx=14, pady=(0, 6))

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color=_BG)
        btn_frame.pack(fill="x", padx=14, pady=4)
        ctk.CTkButton(
            btn_frame, text="▶ Run", fg_color=_GREEN, hover_color="#2ea043",
            command=self._approve, width=110,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_frame, text="✗ Skip", fg_color="#21262d", hover_color=_RED,
            command=self._deny, width=90,
        ).pack(side="left")

        # Output area
        ctk.CTkLabel(self, text="Output:", anchor="w", font=("Segoe UI", 11)).pack(fill="x", padx=14, pady=(8, 2))
        out_frame = ctk.CTkFrame(self, fg_color=_CODE_BG)
        out_frame.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        self._output = tk.Text(
            out_frame, bg=_CODE_BG, fg=_FG,
            font=("Consolas", 10), wrap="word", relief="flat",
        )
        self._output.pack(fill="both", expand=True, padx=4, pady=4)
        self._output.tag_configure("stderr", foreground=_RED)
        self._output.tag_configure("success", foreground=_GREEN)
        self._output.tag_configure("info", foreground=_BLUE)

        # Close button
        ctk.CTkButton(self, text="Close", command=self.destroy).pack(pady=(0, 10))

    def _approve(self) -> None:
        if self._decided:
            return
        self._decided = True
        self._approved = True
        self._append_output(f"$ {self.command}\n", "info")
        if self.on_decision:
            threading.Thread(target=self._run_with_callback, daemon=True).start()

    def _deny(self) -> None:
        if self._decided:
            return
        self._decided = True
        self._append_output("Command skipped by user.\n", "stderr")
        if self.on_decision:
            self.on_decision(False, "", "", -1)

    def _run_with_callback(self) -> None:
        import subprocess
        try:
            process = subprocess.Popen(
                self.command, shell=True, cwd=self.cwd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1,
            )
            for line in process.stdout:
                self.after(0, self._append_output, line, "")
            for line in process.stderr:
                self.after(0, self._append_output, line, "stderr")
            process.wait(timeout=120)
            if process.returncode == 0:
                self.after(0, self._append_output, f"\n✅ Completed (exit 0)\n", "success")
            else:
                self.after(0, self._append_output, f"\n❌ Failed (exit {process.returncode})\n", "stderr")
            if self.on_decision:
                import io
                self.on_decision(True, "", "", process.returncode)
        except Exception as exc:
            self.after(0, self._append_output, f"\nError: {exc}\n", "stderr")

    def _append_output(self, text: str, tag: str = "") -> None:
        self._output.insert(tk.END, text, tag)
        self._output.see(tk.END)
