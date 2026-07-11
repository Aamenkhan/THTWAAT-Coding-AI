"""
ai/tab_complete.py — Gemini-powered Tab Autocomplete Engine
Uses Fill-in-the-Middle (FIM) prompting to suggest code completions.
Completion is triggered after a short debounce delay on every keystroke.
"""

from __future__ import annotations

import threading
import time
import urllib.request
import json
import re
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Completion Result
# ---------------------------------------------------------------------------

class CompletionResult:
    """Holds a single autocomplete suggestion."""
    def __init__(self, text: str, prefix_len: int = 0):
        self.text = text          # The text to insert
        self.prefix_len = prefix_len  # How many chars of prefix are already typed


# ---------------------------------------------------------------------------
# Gemini Tab Autocomplete Engine
# ---------------------------------------------------------------------------

class GeminiTabComplete:
    """
    Provides real-time tab autocomplete powered by Google Gemini.

    Usage:
        engine = GeminiTabComplete(api_key="AIza...")
        engine.request(prefix, suffix, language, callback)
        # callback(CompletionResult) is called on the main thread via `after`
    """

    # Debounce: wait this many ms before sending API request
    DEBOUNCE_MS = 600

    # Max chars sent to API (truncate very large files)
    MAX_PREFIX_CHARS = 3000
    MAX_SUFFIX_CHARS = 1000

    # Gemini model for completions (fast + free)
    MODEL = "gemini-flash-latest"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._pending_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self._last_request_id = 0
        self._enabled = True

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable autocomplete."""
        self._enabled = enabled

    def request(
        self,
        prefix: str,
        suffix: str,
        language: str,
        callback: Callable[[Optional[CompletionResult]], None],
    ) -> None:
        """
        Schedule a completion request with debouncing.
        Only the most recent request within DEBOUNCE_MS will fire.
        """
        if not self._enabled or not self.api_key:
            return

        # Cancel any pending timer
        with self._lock:
            if self._pending_timer:
                self._pending_timer.cancel()
            self._last_request_id += 1
            req_id = self._last_request_id

        delay = self.DEBOUNCE_MS / 1000.0
        timer = threading.Timer(
            delay,
            self._do_request,
            args=(prefix, suffix, language, callback, req_id),
        )
        with self._lock:
            self._pending_timer = timer
        timer.daemon = True
        timer.start()

    def cancel(self) -> None:
        """Cancel any pending completion request."""
        with self._lock:
            if self._pending_timer:
                self._pending_timer.cancel()
                self._pending_timer = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _do_request(
        self,
        prefix: str,
        suffix: str,
        language: str,
        callback: Callable[[Optional[CompletionResult]], None],
        req_id: int,
    ) -> None:
        """Run in background thread — call Gemini API and invoke callback."""
        # Check if still the latest request
        with self._lock:
            if req_id != self._last_request_id:
                return  # Superseded by newer request

        try:
            result = self._call_gemini(prefix, suffix, language)
        except Exception:
            result = None

        # Check again after API call
        with self._lock:
            if req_id != self._last_request_id:
                return

        callback(result)

    def _call_gemini(
        self, prefix: str, suffix: str, language: str
    ) -> Optional[CompletionResult]:
        """Call Gemini API with FIM prompt and return CompletionResult."""
        # Truncate to avoid huge prompts
        prefix = prefix[-self.MAX_PREFIX_CHARS :]
        suffix = suffix[: self.MAX_SUFFIX_CHARS]

        # Skip if last char is a newline or space (user just pressed Enter)
        stripped = prefix.rstrip()
        if not stripped:
            return None

        prompt = (
            f"You are a code completion engine. "
            f"Complete the {language} code at <FILL_HERE>. "
            f"Return ONLY the code to insert — no explanation, no markdown fences, no extra text.\n\n"
            f"```{language}\n"
            f"{prefix}<FILL_HERE>{suffix}\n"
            f"```\n\n"
            f"Code to insert at <FILL_HERE> (single line or short block only):"
        )

        body = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 200,
                "stopSequences": ["\n\n\n"],
            },
        }).encode()

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.MODEL}:generateContent?key={self.api_key}"
        )
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        candidates = data.get("candidates", [])
        if not candidates:
            return None

        text: str = candidates[0]["content"]["parts"][0]["text"]
        text = self._clean_completion(text, prefix)

        if not text:
            return None

        return CompletionResult(text=text)

    @staticmethod
    def _clean_completion(text: str, prefix: str) -> str:
        """Strip markdown fences and obvious noise from the completion."""
        # Remove ```lang ... ``` fences
        text = re.sub(r"^```[\w]*\n?", "", text.strip())
        text = re.sub(r"\n?```$", "", text)

        # Remove leading/trailing blank lines
        text = text.strip("\n")

        # If Gemini repeated the prefix, strip it
        if text.startswith(prefix.lstrip()):
            text = text[len(prefix.lstrip()):]

        return text.rstrip()
