"""
ai/context_engine.py — Smart Context Engine (Feature 5)
Never sends the entire project. Picks the most relevant files
within a configurable token budget for maximum context efficiency.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Approximate chars per token (rough estimate for LLMs)
_CHARS_PER_TOKEN = 4
_SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules", "build", "dist", ".pytest_cache"}
_CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".cs", ".go", ".rs",
    ".php", ".cpp", ".c", ".h", ".rb", ".swift", ".kt", ".md", ".txt",
    ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".env",
}


def _token_estimate(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _score_file(path: Path, query: str, symbols: List[str]) -> float:
    """Score a file's relevance to the query (higher = more relevant)."""
    score = 0.0
    name_lower = path.name.lower()
    query_lower = query.lower()
    query_words = set(re.split(r"\W+", query_lower))

    # Filename matches
    for word in query_words:
        if word and word in name_lower:
            score += 3.0

    # Extension boost for common entry points
    if path.name in ("main.py", "app.py", "index.py", "server.py", "__init__.py"):
        score += 2.0

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        content_lower = content.lower()

        # Keyword frequency
        for word in query_words:
            if word and len(word) > 2:
                count = content_lower.count(word)
                score += min(count * 0.5, 5.0)

        # Symbol matches
        for sym in symbols:
            if sym.lower() in content_lower:
                score += 4.0

        # Recency heuristic: shorter files are cheaper — slight bias toward small files
        lines = content.count("\n")
        score -= lines * 0.002

    except Exception:
        pass

    return score


class ContextEngine:
    """
    Selects the most relevant project files for a given query
    while staying within a token budget.
    """

    def __init__(self, project_dir: str, token_budget: int = 4000):
        self.project_dir = Path(project_dir).resolve()
        self.token_budget = token_budget
        self._file_cache: Dict[str, str] = {}

    def build_context(
        self,
        query: str,
        extra_files: Optional[List[str]] = None,
        budget: Optional[int] = None,
    ) -> str:
        """
        Build a context string from the most relevant files.

        Parameters
        ----------
        query       : the user's prompt / goal
        extra_files : additional files to always include (e.g., currently open file)
        budget      : override token budget for this call
        """
        budget = budget or self.token_budget
        symbols = self._extract_symbols(query)
        candidates = self._gather_candidates()

        # Score all candidates
        scored: List[Tuple[float, Path]] = []
        for p in candidates:
            s = _score_file(p, query, symbols)
            if s > 0:
                scored.append((s, p))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Always include extra_files first
        selected: List[Tuple[Path, str]] = []
        used_tokens = 0
        forced = set()

        if extra_files:
            for ef in extra_files:
                ep = Path(ef)
                if ep.exists():
                    content = self._read(ep)
                    tokens = _token_estimate(content)
                    selected.append((ep, content[:budget * _CHARS_PER_TOKEN // 2]))
                    used_tokens += tokens
                    forced.add(str(ep.resolve()))

        # Fill remaining budget with highest-scored files
        for score, path in scored:
            if used_tokens >= budget:
                break
            key = str(path.resolve())
            if key in forced:
                continue
            content = self._read(path)
            tokens = _token_estimate(content)
            if used_tokens + tokens > budget:
                # Include a truncated snippet
                chars = (budget - used_tokens) * _CHARS_PER_TOKEN
                if chars > 200:
                    selected.append((path, content[:chars] + "\n... (truncated)"))
                    used_tokens = budget
                break
            selected.append((path, content))
            used_tokens += tokens

        if not selected:
            return ""

        parts = []
        for path, content in selected:
            rel = self._rel(path)
            parts.append(f"### {rel}\n```\n{content}\n```")

        return "\n\n".join(parts)

    def get_relevant_files(self, query: str, top_n: int = 10) -> List[str]:
        """Return the top-N most relevant file paths for a query."""
        symbols = self._extract_symbols(query)
        candidates = self._gather_candidates()
        scored = [(s, p) for p in candidates if (s := _score_file(p, query, symbols)) > 0]
        scored.sort(reverse=True)
        return [str(p.resolve()) for _, p in scored[:top_n]]

    def invalidate_cache(self) -> None:
        self._file_cache.clear()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _gather_candidates(self) -> List[Path]:
        paths = []
        for p in sorted(self.project_dir.rglob("*")):
            if p.is_file() and p.suffix in _CODE_EXTENSIONS:
                if not any(skip in p.parts for skip in _SKIP_DIRS):
                    paths.append(p)
        return paths

    def _read(self, path: Path) -> str:
        key = str(path.resolve())
        if key not in self._file_cache:
            try:
                self._file_cache[key] = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                self._file_cache[key] = ""
        return self._file_cache[key]

    def _rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.project_dir))
        except ValueError:
            return path.name

    @staticmethod
    def _extract_symbols(query: str) -> List[str]:
        """Extract potential symbol names (CamelCase or snake_case words) from the query."""
        camel = re.findall(r"\b[A-Z][a-zA-Z0-9]+\b", query)
        snake = re.findall(r"\b[a-z][a-z0-9_]{2,}\b", query)
        return list(set(camel + snake))
