"""
ai/code_reviewer.py — Code Review Agent (Feature 8)
Automatically reviews code after edits.
Finds bugs, security issues, suggests optimizations,
and generates a full improvement report.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class ReviewResult:
    path: str
    bugs: List[str] = field(default_factory=list)
    security_issues: List[str] = field(default_factory=list)
    optimizations: List[str] = field(default_factory=list)
    summary: str = ""
    score: int = 0          # 0-100 quality score
    raw_response: str = ""

    def to_markdown(self) -> str:
        """Generate a Markdown improvement report."""
        lines = [f"## Code Review: `{Path(self.path).name}`", f"**Quality Score**: {self.score}/100", ""]
        if self.bugs:
            lines += ["### 🐛 Bugs Found"] + [f"- {b}" for b in self.bugs] + [""]
        if self.security_issues:
            lines += ["### 🔒 Security Issues"] + [f"- {s}" for s in self.security_issues] + [""]
        if self.optimizations:
            lines += ["### ⚡ Optimization Suggestions"] + [f"- {o}" for o in self.optimizations] + [""]
        if self.summary:
            lines += ["### 📋 Summary", self.summary]
        return "\n".join(lines)

    @property
    def has_issues(self) -> bool:
        return bool(self.bugs or self.security_issues)

    @property
    def total_issues(self) -> int:
        return len(self.bugs) + len(self.security_issues)


_REVIEW_PROMPT = """\
You are an expert code reviewer. Review the following code and respond in this exact format:

BUGS:
- <bug 1>
- <bug 2>
(or "None found" if no bugs)

SECURITY:
- <issue 1>
(or "None found")

OPTIMIZATIONS:
- <suggestion 1>
- <suggestion 2>
(or "None needed")

SCORE: <0-100>

SUMMARY:
<2-3 sentence overall assessment>

Code to review ({language}):
```
{code}
```
"""


class CodeReviewer:
    """
    Reviews code files using the LLM.
    Can be triggered manually or automatically after accepted edits.
    """

    def __init__(self, ollama_client, model: str = "qwen2.5-coder:3b"):
        self.client = ollama_client
        self.model = model

    def review_file(self, path: str) -> ReviewResult:
        """Review a single file and return a structured ReviewResult."""
        p = Path(path)
        if not p.exists():
            return ReviewResult(path=path, summary=f"File not found: {path}", score=0)

        code = p.read_text(encoding="utf-8", errors="ignore")
        if not code.strip():
            return ReviewResult(path=path, summary="Empty file.", score=100)

        language = _detect_language(p.suffix)
        # Truncate large files for review
        if len(code) > 8000:
            code = code[:8000] + "\n... (truncated for review)"

        prompt = _REVIEW_PROMPT.format(language=language, code=code)
        try:
            raw = self.client.generate(prompt, model=self.model)
            return _parse_review(path, raw)
        except Exception as exc:
            return ReviewResult(path=path, summary=f"Review failed: {exc}", score=0, raw_response=str(exc))

    def review_files(self, paths: List[str]) -> List[ReviewResult]:
        """Review multiple files."""
        return [self.review_file(p) for p in paths]

    def generate_report(self, results: List[ReviewResult]) -> str:
        """Generate a combined Markdown improvement report for multiple files."""
        if not results:
            return "No files reviewed."
        total_bugs = sum(r.total_issues for r in results)
        avg_score = sum(r.score for r in results) // len(results) if results else 0
        lines = [
            "# 📋 Code Review Report",
            f"**Files reviewed**: {len(results)}",
            f"**Total issues found**: {total_bugs}",
            f"**Average quality score**: {avg_score}/100",
            "",
        ]
        for result in results:
            if result.has_issues or result.optimizations:
                lines.append(result.to_markdown())
                lines.append("---")
        if not any(r.has_issues for r in results):
            lines.append("✅ No critical issues found across all reviewed files.")
        return "\n".join(lines)

    def quick_check(self, code: str, language: str = "python") -> str:
        """Quick inline review of a code snippet (returns plain text)."""
        prompt = (
            f"Quickly review this {language} code snippet. "
            "In 3 bullet points, highlight the most important issues or improvements:\n\n"
            f"```{language}\n{code[:3000]}\n```"
        )
        try:
            return self.client.generate(prompt, model=self.model)
        except Exception as exc:
            return f"Quick review failed: {exc}"


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_review(path: str, raw: str) -> ReviewResult:
    import re
    result = ReviewResult(path=path, raw_response=raw)

    def extract_section(header: str) -> List[str]:
        pattern = re.compile(rf"{header}:\s*\n(.*?)(?=\n[A-Z]+:|\Z)", re.S | re.I)
        match = pattern.search(raw)
        if not match:
            return []
        block = match.group(1).strip()
        if "none" in block.lower():
            return []
        items = [l.lstrip("- •").strip() for l in block.splitlines() if l.strip().startswith("-")]
        return [i for i in items if i]

    result.bugs = extract_section("BUGS")
    result.security_issues = extract_section("SECURITY")
    result.optimizations = extract_section("OPTIMIZATIONS")

    score_match = re.search(r"SCORE:\s*(\d+)", raw, re.I)
    if score_match:
        result.score = max(0, min(100, int(score_match.group(1))))
    else:
        result.score = max(0, 100 - len(result.bugs) * 10 - len(result.security_issues) * 15)

    summary_match = re.search(r"SUMMARY:\s*\n(.*)", raw, re.S | re.I)
    if summary_match:
        result.summary = summary_match.group(1).strip()[:500]

    return result


def _detect_language(ext: str) -> str:
    return {
        ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
        ".tsx": "TypeScript/React", ".jsx": "JavaScript/React",
        ".java": "Java", ".cs": "C#", ".go": "Go", ".rs": "Rust",
        ".php": "PHP", ".dart": "Dart/Flutter", ".rb": "Ruby",
        ".cpp": "C++", ".c": "C",
    }.get(ext.lower(), "Code")
