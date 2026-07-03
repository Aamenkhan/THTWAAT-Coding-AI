"""
ai/terminal_agent.py — Terminal Agent (Feature 7)
Queues terminal commands for user approval before execution.
Reads output, detects failures, suggests next actions via LLM.
"""

import queue
import subprocess
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Iterator, List, Optional


class CommandStatus(Enum):
    PENDING   = auto()
    APPROVED  = auto()
    DENIED    = auto()
    RUNNING   = auto()
    DONE      = auto()
    FAILED    = auto()


@dataclass
class TerminalCommand:
    command: str
    cwd: str
    reason: str                 # Why the agent wants to run this
    status: CommandStatus = CommandStatus.PENDING
    stdout: str = ""
    stderr: str = ""
    returncode: Optional[int] = None
    next_action: Optional[str] = None   # LLM-suggested follow-up


OutputCallback = Callable[[str, str], None]  # (stream_name, text)
ApprovalCallback = Callable[[TerminalCommand], bool]  # True=approve


class TerminalAgent:
    """
    Manages terminal command execution with user approval.
    Features:
    - Queue commands → wait for approval callback
    - Stream stdout/stderr live via output_callback
    - Detect failures and ask LLM for next action
    """

    def __init__(
        self,
        approval_callback: Optional[ApprovalCallback] = None,
        output_callback: Optional[OutputCallback] = None,
        ollama_client=None,
        model: str = "qwen2.5-coder:3b",
        default_cwd: str = ".",
    ):
        self.approval_callback = approval_callback
        self.output_callback = output_callback
        self.client = ollama_client
        self.model = model
        self.default_cwd = default_cwd
        self._history: List[TerminalCommand] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_with_approval(
        self,
        command: str,
        reason: str = "",
        cwd: Optional[str] = None,
        output_callback: Optional[OutputCallback] = None,
    ) -> TerminalCommand:
        """
        Propose a command, wait for approval, then execute it.
        Blocks the calling thread until complete.
        """
        cmd = TerminalCommand(
            command=command,
            cwd=str(cwd or self.default_cwd),
            reason=reason or f"Execute: {command}",
        )
        with self._lock:
            self._history.append(cmd)

        # Request approval
        if self.approval_callback:
            approved = self.approval_callback(cmd)
            cmd.status = CommandStatus.APPROVED if approved else CommandStatus.DENIED
        else:
            cmd.status = CommandStatus.DENIED  # Deny by default if no callback

        if cmd.status == CommandStatus.DENIED:
            cmd.stdout = ""
            cmd.stderr = "Command denied by user."
            return cmd

        # Execute
        return self._execute(cmd, output_callback or self.output_callback)

    def run_approved(
        self,
        command: str,
        cwd: Optional[str] = None,
        output_callback: Optional[OutputCallback] = None,
    ) -> TerminalCommand:
        """Run a command that is pre-approved (e.g., safe read-only commands)."""
        cmd = TerminalCommand(
            command=command,
            cwd=str(cwd or self.default_cwd),
            reason="Pre-approved command",
            status=CommandStatus.APPROVED,
        )
        with self._lock:
            self._history.append(cmd)
        return self._execute(cmd, output_callback or self.output_callback)

    def history(self) -> List[TerminalCommand]:
        return list(self._history)

    def last_output(self) -> str:
        if not self._history:
            return ""
        last = self._history[-1]
        return last.stdout + (f"\n[stderr]\n{last.stderr}" if last.stderr.strip() else "")

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _execute(
        self,
        cmd: TerminalCommand,
        output_callback: Optional[OutputCallback],
    ) -> TerminalCommand:
        cmd.status = CommandStatus.RUNNING

        try:
            process = subprocess.Popen(
                cmd.command,
                shell=True,
                cwd=cmd.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            stdout_lines: List[str] = []
            stderr_lines: List[str] = []

            def stream_pipe(pipe, lines, stream_name):
                for line in pipe:
                    lines.append(line)
                    if output_callback:
                        output_callback(stream_name, line)

            t1 = threading.Thread(target=stream_pipe, args=(process.stdout, stdout_lines, "stdout"), daemon=True)
            t2 = threading.Thread(target=stream_pipe, args=(process.stderr, stderr_lines, "stderr"), daemon=True)
            t1.start(); t2.start()
            process.wait(timeout=120)
            t1.join(); t2.join()

            cmd.stdout = "".join(stdout_lines)
            cmd.stderr = "".join(stderr_lines)
            cmd.returncode = process.returncode
            cmd.status = CommandStatus.DONE if process.returncode == 0 else CommandStatus.FAILED

            # On failure — ask LLM what to do next
            if cmd.status == CommandStatus.FAILED and self.client:
                cmd.next_action = self._suggest_next(cmd)

        except subprocess.TimeoutExpired:
            cmd.status = CommandStatus.FAILED
            cmd.stderr = "Command timed out after 120 seconds."
            cmd.returncode = -1
        except Exception as exc:
            cmd.status = CommandStatus.FAILED
            cmd.stderr = str(exc)
            cmd.returncode = -1

        return cmd

    # ------------------------------------------------------------------
    # LLM-assisted next action
    # ------------------------------------------------------------------

    def _suggest_next(self, cmd: TerminalCommand) -> str:
        prompt = (
            f"A terminal command failed:\n\n"
            f"Command: {cmd.command}\n"
            f"Return code: {cmd.returncode}\n"
            f"stdout: {cmd.stdout[-600:]}\n"
            f"stderr: {cmd.stderr[-600:]}\n\n"
            "Suggest the single best next action to fix this. "
            "Be specific and concise (1-2 sentences)."
        )
        try:
            return self.client.generate(prompt, model=self.model)
        except Exception:
            return "Check the error output and verify dependencies are installed."
