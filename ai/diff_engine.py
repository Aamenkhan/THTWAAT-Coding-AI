"""
ai/diff_engine.py — Multi-file Diff Engine
Generates unified diffs for proposed changes.
Never writes directly — all changes go through accept().
Supports preview, accept, reject, accept-all, reject-all.
"""

import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional


@dataclass
class PendingEdit:
    """A proposed change to a single file, not yet applied."""
    path: str
    original: str
    proposed: str
    diff: str
    description: str = ""
    accepted: Optional[bool] = None   # None=pending, True=accepted, False=rejected

    @property
    def is_pending(self) -> bool:
        return self.accepted is None

    @property
    def is_new_file(self) -> bool:
        return self.original == "" and not Path(self.path).exists()


class DiffEngine:
    """
    Manages a queue of proposed file edits.
    Flow:
        propose_edit() → generates diff, adds to queue
        preview(path)  → returns PendingEdit for inspection
        accept(path)   → writes file to disk
        reject(path)   → discards change, file untouched
    """

    def __init__(self, on_change: Optional[Callable[[str, str], None]] = None):
        """
        on_change: optional callback(path, status) called after accept/reject.
        status is one of 'accepted' | 'rejected'.
        """
        self._queue: Dict[str, PendingEdit] = {}  # keyed by resolved path
        self._on_change = on_change

    # ------------------------------------------------------------------
    # Proposing edits
    # ------------------------------------------------------------------

    def propose_edit(
        self,
        path: str,
        proposed_content: str,
        description: str = "",
    ) -> PendingEdit:
        """
        Stage a proposed change to *path* without writing to disk.
        If the file already has a pending edit the new proposal replaces it.
        """
        p = Path(path).resolve()
        original = p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""
        diff = self._make_diff(original, proposed_content, str(p))
        edit = PendingEdit(
            path=str(p),
            original=original,
            proposed=proposed_content,
            diff=diff,
            description=description,
        )
        self._queue[str(p)] = edit
        return edit

    def propose_replace(
        self,
        path: str,
        old_text: str,
        new_text: str,
        description: str = "",
    ) -> Optional[PendingEdit]:
        """Stage a targeted text replacement inside a file.

        Line endings are normalised to ``\\n`` before comparison so that
        model-generated patterns (always ``\\n``) match Windows files (``\\r\\n``).
        The proposed content is written back with the file's original line
        ending style so disk files are not inadvertently converted.
        """
        p = Path(path).resolve()
        if not p.exists():
            return None
        original = p.read_text(encoding="utf-8", errors="ignore")
        uses_crlf = "\r\n" in original

        # Normalise both sides to \n for matching
        original_norm = original.replace("\r\n", "\n")
        old_text_norm = old_text.replace("\r\n", "\n")
        new_text_norm = new_text.replace("\r\n", "\n")

        if old_text_norm not in original_norm:
            return None

        proposed_norm = original_norm.replace(old_text_norm, new_text_norm, 1)

        # Restore original line-ending style so we don't silently convert files
        proposed = proposed_norm.replace("\n", "\r\n") if uses_crlf else proposed_norm
        return self.propose_edit(str(p), proposed, description)

    # ------------------------------------------------------------------
    # Reviewing
    # ------------------------------------------------------------------

    def preview(self, path: str) -> Optional[PendingEdit]:
        """Return the pending edit for *path*, or None if none exists."""
        return self._queue.get(str(Path(path).resolve()))

    def pending_edits(self) -> List[PendingEdit]:
        """Return all edits that have not yet been accepted or rejected."""
        return [e for e in self._queue.values() if e.is_pending]

    def all_edits(self) -> List[PendingEdit]:
        return list(self._queue.values())

    # ------------------------------------------------------------------
    # Accepting / Rejecting
    # ------------------------------------------------------------------

    def accept(self, path: str) -> bool:
        """Write the proposed content to disk. Returns True on success."""
        edit = self._queue.get(str(Path(path).resolve()))
        if edit is None:
            return False
        try:
            p = Path(edit.path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(edit.proposed, encoding="utf-8")
            edit.accepted = True
            if self._on_change:
                self._on_change(edit.path, "accepted")
            return True
        except Exception:
            return False

    def reject(self, path: str) -> bool:
        """Discard the proposed change — file on disk is untouched."""
        edit = self._queue.get(str(Path(path).resolve()))
        if edit is None:
            return False
        edit.accepted = False
        if self._on_change:
            self._on_change(edit.path, "rejected")
        return True

    def accept_all(self) -> List[str]:
        """Accept every pending edit. Returns list of accepted paths."""
        return [e.path for e in self.pending_edits() if self.accept(e.path)]

    def reject_all(self) -> List[str]:
        """Reject every pending edit. Returns list of rejected paths."""
        return [e.path for e in self.pending_edits() if self.reject(e.path)]

    def clear(self) -> None:
        """Remove all edits from the queue (accepted, rejected, and pending)."""
        self._queue.clear()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_diff(original: str, proposed: str, path: str) -> str:
        """Generate a unified diff string."""
        name = Path(path).name
        lines = list(difflib.unified_diff(
            original.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            fromfile=f"a/{name}",
            tofile=f"b/{name}",
            lineterm="\n",
        ))
        return "".join(lines) if lines else "(no changes)"

    @staticmethod
    def colorize_diff(diff: str) -> List[tuple]:
        """
        Parse a unified diff into a list of (text, tag) tuples.
        Tags: 'add' | 'remove' | 'hunk' | 'normal'
        Suitable for rendering in a Tkinter Text widget.
        """
        result: List[tuple] = []
        for line in diff.splitlines(keepends=True):
            if line.startswith("+") and not line.startswith("+++"):
                result.append((line, "add"))
            elif line.startswith("-") and not line.startswith("---"):
                result.append((line, "remove"))
            elif line.startswith("@@"):
                result.append((line, "hunk"))
            else:
                result.append((line, "normal"))
        return result
