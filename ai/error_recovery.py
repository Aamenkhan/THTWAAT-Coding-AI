"""
ai/error_recovery.py — Error Recovery System (Feature 12)
Retries failed tool calls, asks LLM to explain failures,
and suggests fixes. Never raises — always returns a result.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ai.tools import call_tool, ToolResult


@dataclass
class RecoveryResult:
    tool_name: str
    args: Dict[str, Any]
    ok: bool
    data: Dict[str, Any]
    attempts: int
    explanation: Optional[str] = None
    suggestions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "tool": self.tool_name,
            "attempts": self.attempts,
            **self.data,
            **({"explanation": self.explanation} if self.explanation else {}),
            **({"suggestions": self.suggestions} if self.suggestions else {}),
        }


class ErrorRecovery:
    """
    Wraps tool calls with retry logic and LLM-assisted failure explanation.
    """

    def __init__(
        self,
        ollama_client=None,
        model: str = "qwen2.5-coder:3b",
        max_retries: int = 3,
        retry_delay: float = 0.5,
    ):
        self.client = ollama_client
        self.model = model
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def safe_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        context: str = "",
    ) -> RecoveryResult:
        """
        Call a tool with automatic retry and failure explanation.
        Never raises — always returns RecoveryResult.
        """
        last_result: Optional[ToolResult] = None
        last_error: str = ""

        for attempt in range(1, self.max_retries + 1):
            try:
                result = call_tool(tool_name, args)
                if result.ok:
                    return RecoveryResult(
                        tool_name=tool_name,
                        args=args,
                        ok=True,
                        data=result.data,
                        attempts=attempt,
                    )
                last_result = result
                last_error = result.data.get("error", "Unknown error")
            except Exception as exc:
                last_error = str(exc)
                last_result = None

            if attempt < self.max_retries:
                time.sleep(self.retry_delay * attempt)

        # All retries exhausted — explain and suggest
        explanation = self.explain_failure(tool_name, last_error, args, context)
        suggestions = self.suggest_fixes(tool_name, last_error, args)

        return RecoveryResult(
            tool_name=tool_name,
            args=args,
            ok=False,
            data=last_result.data if last_result else {"error": last_error},
            attempts=self.max_retries,
            explanation=explanation,
            suggestions=suggestions,
        )

    def explain_failure(
        self,
        tool_name: str,
        error: str,
        args: Dict[str, Any],
        context: str = "",
    ) -> str:
        """Ask the LLM to explain why the tool failed."""
        if not self.client:
            return f"Tool '{tool_name}' failed: {error}"

        prompt = (
            f"A coding tool '{tool_name}' failed with this error:\n\n"
            f"Error: {error}\n\n"
            f"Arguments used: {args}\n\n"
            f"{'Context: ' + context[:400] if context else ''}\n\n"
            "In 2-3 sentences, explain why this failed in plain English. "
            "Be specific and actionable."
        )
        try:
            return self.client.generate(prompt, model=self.model)
        except Exception as exc:
            return f"Tool '{tool_name}' failed: {error} (explanation unavailable: {exc})"

    def suggest_fixes(
        self,
        tool_name: str,
        error: str,
        args: Dict[str, Any],
    ) -> List[str]:
        """Generate a list of fix suggestions."""
        if not self.client:
            return [f"Check the arguments passed to '{tool_name}'"]

        prompt = (
            f"Tool '{tool_name}' failed with: {error}\n"
            f"Args: {args}\n\n"
            "List 3 specific, actionable fixes as a numbered list. "
            "Each fix on a new line starting with a number."
        )
        try:
            raw = self.client.generate(prompt, model=self.model)
            lines = [l.strip() for l in raw.splitlines() if l.strip()]
            suggestions = [re.sub(r"^\d+[\.\)]\s*", "", l) for l in lines if l]
            return suggestions[:5]
        except Exception:
            return [f"Verify the path/args for '{tool_name}' are correct"]


# Lazy import for regex
import re
