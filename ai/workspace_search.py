"""
ai/workspace_search.py — Workspace Search (Feature 11)
Find symbol, find references, rename symbol, go to definition,
project-wide full-text search.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
import difflib


_SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules", "build", "dist"}
_CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".cs", ".go", ".rs", ".php", ".dart"}


@dataclass
class SymbolLocation:
    path: str
    line: int
    column: int
    symbol_type: str    # 'class' | 'function' | 'method' | 'variable' | 'reference'
    context: str        # surrounding line text


@dataclass
class SearchResult:
    path: str
    line: int
    text: str
    context_before: str = ""
    context_after: str = ""


class WorkspaceSearch:
    """
    Full workspace search and symbol navigation.
    Works with any language that uses common definition patterns.
    """

    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir).resolve()

    # ------------------------------------------------------------------
    # Symbol definition
    # ------------------------------------------------------------------

    def find_symbol(self, name: str) -> List[SymbolLocation]:
        """Find the definition location(s) of a class, function, or method."""
        results: List[SymbolLocation] = []
        patterns = [
            (re.compile(rf"^\s*def\s+{re.escape(name)}\s*\(", re.M), "function"),
            (re.compile(rf"^\s*class\s+{re.escape(name)}\s*[:(]", re.M), "class"),
            (re.compile(rf"^\s*async\s+def\s+{re.escape(name)}\s*\(", re.M), "async function"),
            (re.compile(rf"\b(function|const|let|var)\s+{re.escape(name)}\b", re.M), "js function"),
            (re.compile(rf"\bpublic\s+\w+\s+{re.escape(name)}\s*\(", re.M), "method"),
        ]
        for path in self._all_files():
            content = self._read(path)
            for pattern, sym_type in patterns:
                for match in pattern.finditer(content):
                    line_no = content[: match.start()].count("\n") + 1
                    col = match.start() - content.rfind("\n", 0, match.start()) - 1
                    ctx = content.splitlines()[line_no - 1] if line_no <= len(content.splitlines()) else ""
                    results.append(SymbolLocation(
                        path=str(path),
                        line=line_no,
                        column=col,
                        symbol_type=sym_type,
                        context=ctx.strip(),
                    ))
        return results

    def go_to_definition(self, name: str) -> Optional[SymbolLocation]:
        """Return the primary definition of a symbol (first found)."""
        results = self.find_symbol(name)
        return results[0] if results else None

    # ------------------------------------------------------------------
    # References
    # ------------------------------------------------------------------

    def find_references(self, name: str) -> List[SymbolLocation]:
        """Find all usages (references) of a symbol across the project."""
        results: List[SymbolLocation] = []
        pattern = re.compile(rf"\b{re.escape(name)}\b")
        for path in self._all_files():
            content = self._read(path)
            for match in pattern.finditer(content):
                line_no = content[: match.start()].count("\n") + 1
                col = match.start() - content.rfind("\n", 0, match.start()) - 1
                lines = content.splitlines()
                ctx = lines[line_no - 1].strip() if line_no <= len(lines) else ""
                results.append(SymbolLocation(
                    path=str(path),
                    line=line_no,
                    column=col,
                    symbol_type="reference",
                    context=ctx,
                ))
        return results

    # ------------------------------------------------------------------
    # Rename
    # ------------------------------------------------------------------

    def rename_symbol(
        self,
        old_name: str,
        new_name: str,
        file_filter: Optional[str] = None,
        dry_run: bool = False
    ) -> Dict[str, str]:
        """
        Rename all occurrences of a symbol across the project.
        If dry_run is True, returns {file_path: diff_string} without writing.
        Otherwise, writes to disk and returns {file_path: "success"}.
        """
        pattern = re.compile(rf"\b{re.escape(old_name)}\b")
        results: Dict[str, str] = {}
        for path in self._all_files():
            if file_filter and file_filter.lower() not in str(path).lower():
                continue
            content = self._read(path)
            new_content, count = pattern.subn(new_name, content)
            if count > 0:
                if dry_run:
                    results[str(path)] = new_content
                else:
                    path.write_text(new_content, encoding="utf-8")
                    results[str(path)] = f"Replaced {count} instances"
        return results

    # ------------------------------------------------------------------
    # Full-text search
    # ------------------------------------------------------------------

    def project_wide_search(
        self,
        query: str,
        case_sensitive: bool = False,
        context_lines: int = 2,
    ) -> List[SearchResult]:
        """Full-text search across all project files with context lines."""
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            pattern = re.compile(query, flags)
        except re.error:
            pattern = re.compile(re.escape(query), flags)

        results: List[SearchResult] = []
        for path in self._all_files():
            content = self._read(path)
            lines = content.splitlines()
            for i, line in enumerate(lines):
                if pattern.search(line):
                    before = "\n".join(lines[max(0, i - context_lines): i])
                    after = "\n".join(lines[i + 1: i + 1 + context_lines])
                    results.append(SearchResult(
                        path=str(path),
                        line=i + 1,
                        text=line.strip(),
                        context_before=before,
                        context_after=after,
                    ))
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _all_files(self) -> List[Path]:
        paths = []
        for p in sorted(self.project_dir.rglob("*")):
            if p.is_file() and p.suffix in _CODE_EXTS:
                if not any(skip in p.parts for skip in _SKIP_DIRS):
                    paths.append(p)
        return paths

    def _read(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""
