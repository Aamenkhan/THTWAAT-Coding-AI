"""
ai/security.py — Security Guard (Feature 15)
Detects destructive commands and requires user confirmation before execution.
Never executes dangerous operations automatically.
"""

import re
import threading
from enum import Enum, auto
from typing import Callable, List, Optional, Tuple


class RiskLevel(Enum):
    SAFE = auto()
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CRITICAL = auto()


class SecurityDecision(Enum):
    ALLOW = auto()
    DENY = auto()
    PENDING = auto()


# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------

_RULES: List[Tuple[re.Pattern, RiskLevel, str]] = [
    # CRITICAL — data destruction
    (re.compile(r"\bformat\b.*\b(disk|drive|c:|d:)\b", re.I),
     RiskLevel.CRITICAL, "Formats a disk drive — irreversible data loss"),
    (re.compile(r"\brm\s+-rf\b", re.I),
     RiskLevel.CRITICAL, "Recursive force delete — irreversible"),
    (re.compile(r"\bdel\s+/[sqa]", re.I),
     RiskLevel.CRITICAL, "Bulk Windows delete — irreversible"),

    # HIGH — git destructive
    (re.compile(r"\bgit\s+reset\s+--hard\b", re.I),
     RiskLevel.HIGH, "Git hard reset — discards all uncommitted changes"),
    (re.compile(r"\bgit\s+clean\s+-fd\b", re.I),
     RiskLevel.HIGH, "Git clean -fd — deletes untracked files"),
    (re.compile(r"\bgit\s+push\s+.*--force\b", re.I),
     RiskLevel.HIGH, "Force push — rewrites remote history"),

    # HIGH — file deletion
    (re.compile(r"\bdelete[_\s]?file\b", re.I),
     RiskLevel.HIGH, "File deletion operation"),
    (re.compile(r"\bos\.remove\b|\bos\.unlink\b|\bshutil\.rmtree\b", re.I),
     RiskLevel.HIGH, "Python file/directory deletion"),

    # MEDIUM — file moves
    (re.compile(r"\bmove\b.+\b(file|folder|dir)\b", re.I),
     RiskLevel.MEDIUM, "File/folder move operation"),
    (re.compile(r"\bshutil\.move\b|\bos\.rename\b", re.I),
     RiskLevel.MEDIUM, "Python file move/rename"),

    # MEDIUM — shell scripts
    (re.compile(r"\.(sh|bat|cmd|ps1)\b", re.I),
     RiskLevel.MEDIUM, "Shell script execution"),
    (re.compile(r"\bpowershell\b|\bpwsh\b", re.I),
     RiskLevel.MEDIUM, "PowerShell execution"),

    # LOW — network ops
    (re.compile(r"\bcurl\b|\bwget\b", re.I),
     RiskLevel.LOW, "Network download — verify the source"),
    (re.compile(r"\bpip\s+install\b|\bnpm\s+install\b", re.I),
     RiskLevel.LOW, "Package installation from registry"),
]

# Levels that require confirmation
_CONFIRMATION_THRESHOLD = RiskLevel.MEDIUM


class SecurityGuard:
    """
    Evaluates commands/operations for risk level.
    Blocks operations at or above the threshold until user approves.
    Thread-safe.
    """

    def __init__(
        self,
        threshold: RiskLevel = _CONFIRMATION_THRESHOLD,
        approval_callback: Optional[Callable[[str, str, RiskLevel], bool]] = None,
    ):
        """
        Parameters
        ----------
        threshold         : minimum risk level that requires approval
        approval_callback : fn(command, reason, risk) → bool (True=allow, False=deny)
                           If None, all dangerous commands are auto-denied.
        """
        self.threshold = threshold
        self._approval_callback = approval_callback
        self._lock = threading.Lock()

    def evaluate(self, command: str) -> Tuple[RiskLevel, str]:
        """
        Check a command string for risk.
        Returns (RiskLevel, reason_string).
        """
        for pattern, level, reason in _RULES:
            if pattern.search(command):
                return level, reason
        return RiskLevel.SAFE, ""

    def check(self, command: str) -> Tuple[SecurityDecision, RiskLevel, str]:
        """
        Full security check. Returns (decision, risk_level, reason).
        If approval_callback is set, blocks for user input on risky commands.
        """
        risk, reason = self.evaluate(command)
        if risk.value < self.threshold.value:
            return SecurityDecision.ALLOW, risk, reason

        if self._approval_callback is None:
            return SecurityDecision.DENY, risk, reason

        with self._lock:
            allowed = self._approval_callback(command, reason, risk)

        return (SecurityDecision.ALLOW if allowed else SecurityDecision.DENY), risk, reason

    def is_safe(self, command: str) -> bool:
        decision, _, _ = self.check(command)
        return decision == SecurityDecision.ALLOW

    def set_approval_callback(self, callback: Callable[[str, str, RiskLevel], bool]) -> None:
        self._approval_callback = callback

    @staticmethod
    def describe_risk(level: RiskLevel) -> str:
        return {
            RiskLevel.SAFE: "✅ Safe",
            RiskLevel.LOW: "🟡 Low risk",
            RiskLevel.MEDIUM: "🟠 Medium risk — confirmation required",
            RiskLevel.HIGH: "🔴 High risk — confirmation required",
            RiskLevel.CRITICAL: "💀 Critical — this cannot be undone",
        }.get(level, "Unknown")

    @staticmethod
    def all_risk_levels() -> List[str]:
        return [r.name for r in RiskLevel]
