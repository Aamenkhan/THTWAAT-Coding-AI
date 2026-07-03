"""
ai/tools.py — Centralized Tool Registry
Every tool is a callable that returns a structured JSON-serializable dict.
"""

import os
import re
import shlex
import subprocess
import difflib
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class ToolResult:
    """Thin wrapper so callers can check .ok / .data uniformly."""

    def __init__(self, data: Dict[str, Any], ok: bool = True):
        self.data = data
        self.ok = ok

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, **self.data}


def _err(msg: str) -> ToolResult:
    return ToolResult({"error": msg}, ok=False)


# ---------------------------------------------------------------------------
# Individual tool functions
# ---------------------------------------------------------------------------

def tool_read_file(path: str, **_) -> ToolResult:
    """ReadFile — Read the content of a file."""
    p = Path(path)
    if not p.exists():
        return _err(f"File not found: {path}")
    try:
        content = p.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        return ToolResult({
            "path": str(p.resolve()),
            "content": content,
            "lines": len(lines),
        })
    except Exception as exc:
        return _err(str(exc))


def tool_write_file(path: str, content: str, **_) -> ToolResult:
    """WriteFile — Write content to a file (creates parents if needed)."""
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return ToolResult({"path": str(p.resolve()), "status": "written", "bytes": len(content)})
    except Exception as exc:
        return _err(str(exc))


def tool_search_files(query: str, directory: str = ".", case_sensitive: bool = False, **_) -> ToolResult:
    """SearchFiles — Search for a text pattern across all project files."""
    matches: List[Dict[str, Any]] = []
    base = Path(directory)
    if not base.exists():
        return _err(f"Directory not found: {directory}")
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        pattern = re.compile(query, flags)
    except re.error:
        pattern = re.compile(re.escape(query), flags)
    skip = {"__pycache__", ".git", ".venv", "venv", "node_modules", "build", "dist"}
    for file_path in sorted(base.rglob("*")):
        if file_path.is_file() and not any(p in skip for p in file_path.parts):
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
                for i, line in enumerate(text.splitlines(), 1):
                    if pattern.search(line):
                        matches.append({
                            "path": str(file_path.resolve()),
                            "line": i,
                            "text": line.strip(),
                        })
            except Exception:
                continue
    return ToolResult({"query": query, "matches": matches, "count": len(matches)})


def tool_replace_text(path: str, old_text: str, new_text: str, **_) -> ToolResult:
    """ReplaceText — Replace an exact string in a file and return the unified diff."""
    p = Path(path)
    if not p.exists():
        return _err(f"File not found: {path}")
    try:
        original = p.read_text(encoding="utf-8", errors="ignore")
        if old_text not in original:
            return _err(f"Text not found in {path}")
        updated = original.replace(old_text, new_text, 1)
        diff = "\n".join(difflib.unified_diff(
            original.splitlines(),
            updated.splitlines(),
            fromfile=f"a/{p.name}",
            tofile=f"b/{p.name}",
            lineterm="",
        ))
        p.write_text(updated, encoding="utf-8")
        return ToolResult({"path": str(p.resolve()), "status": "replaced", "diff": diff})
    except Exception as exc:
        return _err(str(exc))


def tool_create_file(path: str, content: str = "", **_) -> ToolResult:
    """CreateFile — Create a new file (errors if already exists)."""
    p = Path(path)
    if p.exists():
        return _err(f"File already exists: {path}")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return ToolResult({"path": str(p.resolve()), "status": "created"})
    except Exception as exc:
        return _err(str(exc))


def tool_delete_file(path: str, **_) -> ToolResult:
    """DeleteFile — Delete a file."""
    p = Path(path)
    if not p.exists():
        return _err(f"File not found: {path}")
    try:
        p.unlink()
        return ToolResult({"path": str(p.resolve()), "status": "deleted"})
    except Exception as exc:
        return _err(str(exc))


def tool_list_directory(directory: str = ".", **_) -> ToolResult:
    """ListDirectory — List all files and subdirectories."""
    base = Path(directory)
    if not base.exists():
        return _err(f"Directory not found: {directory}")
    skip = {"__pycache__", ".git", ".venv", "venv", "node_modules"}
    entries: List[Dict[str, Any]] = []
    try:
        for item in sorted(base.iterdir()):
            if item.name in skip:
                continue
            entries.append({
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
            })
        return ToolResult({"directory": str(base.resolve()), "entries": entries, "count": len(entries)})
    except Exception as exc:
        return _err(str(exc))


def tool_run_terminal(command: str, cwd: str = ".", timeout: int = 30, **_) -> ToolResult:
    """RunTerminal — Execute a shell command and capture output."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(Path(cwd).resolve()),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return ToolResult({
            "command": command,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }, ok=(result.returncode == 0))
    except subprocess.TimeoutExpired:
        return _err(f"Command timed out after {timeout}s: {command}")
    except Exception as exc:
        return _err(str(exc))


def tool_git_status(directory: str = ".", **_) -> ToolResult:
    """GitStatus — Return git status as structured data."""
    try:
        result = subprocess.run(
            ["git", "status", "--short", "--branch"],
            cwd=str(Path(directory).resolve()),
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            return _err(result.stderr.strip() or "git status failed")
        lines = result.stdout.strip().splitlines()
        branch = lines[0].lstrip("## ").split("...")[0].strip() if lines else "unknown"
        changes = [{"status": l[:2].strip(), "file": l[3:].strip()} for l in lines[1:] if l.strip()]
        return ToolResult({"branch": branch, "changes": changes, "clean": len(changes) == 0})
    except Exception as exc:
        return _err(str(exc))


def tool_git_diff(directory: str = ".", **_) -> ToolResult:
    """GitDiff — Return unified git diff of working tree."""
    try:
        result = subprocess.run(
            ["git", "diff"],
            cwd=str(Path(directory).resolve()),
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            return _err(result.stderr.strip() or "git diff failed")
        return ToolResult({"diff": result.stdout, "has_changes": bool(result.stdout.strip())})
    except Exception as exc:
        return _err(str(exc))


def tool_git_commit(message: str, directory: str = ".", files: list = None, **_) -> ToolResult:
    """GitCommit — Stage explicitly provided files and commit."""
    if not files:
        return _err("No explicit files provided. You must specify 'files' as a list.")
        
    try:
        import fnmatch
        import os
        sensitive_patterns = [".env", "*.key", "*secret*", "*credential*", "crash_reports/*", "config_backups/*"]
        
        for f in files:
            normalized_f = f.replace('\\', '/')
            is_sensitive = any(
                fnmatch.fnmatch(normalized_f, pat) or fnmatch.fnmatch(os.path.basename(normalized_f), pat)
                for pat in sensitive_patterns
            )
            if is_sensitive:
                return _err(f"Safety guard: blocked staging of sensitive file '{f}'")
                
        cwd = str(Path(directory).resolve())
        subprocess.run(["git", "add", *files], cwd=cwd, capture_output=True)
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=cwd, capture_output=True, text=True,
        )
        output = result.stdout.strip() or result.stderr.strip()
        return ToolResult({"status": "committed" if result.returncode == 0 else "failed",
                           "message": message, "output": output},
                          ok=(result.returncode == 0))
    except Exception as exc:
        return _err(str(exc))


def tool_run_tests(directory: str = ".", args: str = "", **_) -> ToolResult:
    """RunTests — Run pytest and return structured results."""
    try:
        cmd = f"python -m pytest {args} --tb=short -q"
        result = subprocess.run(
            cmd, shell=True,
            cwd=str(Path(directory).resolve()),
            capture_output=True, text=True, timeout=120,
        )
        output = result.stdout + result.stderr
        passed = len(re.findall(r" passed", output))
        failed = len(re.findall(r" failed", output))
        errors = len(re.findall(r" error", output))
        return ToolResult({
            "passed": passed, "failed": failed,
            "errors": errors, "output": output,
            "returncode": result.returncode,
        }, ok=(result.returncode == 0))
    except subprocess.TimeoutExpired:
        return _err("Tests timed out after 120s")
    except Exception as exc:
        return _err(str(exc))


def tool_search_symbols(symbol: str, directory: str = ".", **_) -> ToolResult:
    """SearchSymbols — Find class/function definitions by name."""
    results: List[Dict[str, Any]] = []
    base = Path(directory)
    pattern = re.compile(rf"^\s*(def|class)\s+{re.escape(symbol)}\b", re.MULTILINE)
    skip = {"__pycache__", ".git", "venv", ".venv"}
    for file_path in sorted(base.rglob("*.py")):
        if any(p in skip for p in file_path.parts):
            continue
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            for match in pattern.finditer(content):
                line_num = content[: match.start()].count("\n") + 1
                results.append({
                    "path": str(file_path.resolve()),
                    "type": match.group(1),
                    "name": symbol,
                    "line": line_num,
                })
        except Exception:
            continue
    return ToolResult({"symbol": symbol, "results": results, "count": len(results)})


def tool_project_index(query: str, directory: str = ".", **_) -> ToolResult:
    """ProjectIndex — Build relevant project context for a query."""
    base = Path(directory)
    skip = {"__pycache__", ".git", "venv", ".venv", "build", "dist"}
    all_files: List[str] = []
    for p in sorted(base.rglob("*")):
        if p.is_file() and not any(s in p.parts for s in skip):
            all_files.append(str(p.resolve()))
    relevant: List[Dict[str, str]] = []
    q = query.lower()
    for fp in all_files:
        try:
            content = Path(fp).read_text(encoding="utf-8", errors="ignore")
            if q in content.lower():
                relevant.append({"path": fp, "snippet": content[:800]})
        except Exception:
            continue
    if not relevant:
        relevant = [{"path": fp, "snippet": Path(fp).read_text(encoding="utf-8", errors="ignore")[:600]}
                    for fp in all_files[:5]]
    context_parts = [f"File: {r['path']}\n{r['snippet']}" for r in relevant[:6]]
    return ToolResult({
        "query": query,
        "context": "\n\n---\n\n".join(context_parts),
        "files": [r["path"] for r in relevant[:6]],
        "total_files": len(all_files),
    })


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

TOOL_REGISTRY: Dict[str, Callable[..., ToolResult]] = {
    "ReadFile":      tool_read_file,
    "WriteFile":     tool_write_file,
    "SearchFiles":   tool_search_files,
    "ReplaceText":   tool_replace_text,
    "CreateFile":    tool_create_file,
    "DeleteFile":    tool_delete_file,
    "ListDirectory": tool_list_directory,
    "RunTerminal":   tool_run_terminal,
    "GitStatus":     tool_git_status,
    "GitDiff":       tool_git_diff,
    "GitCommit":     tool_git_commit,
    "RunTests":      tool_run_tests,
    "SearchSymbols": tool_search_symbols,
    "ProjectIndex":  tool_project_index,
}


def call_tool(name: str, args: Dict[str, Any]) -> ToolResult:
    """Dispatch a tool call by name with keyword arguments."""
    if name not in TOOL_REGISTRY:
        return _err(f"Unknown tool: '{name}'. Available: {list(TOOL_REGISTRY.keys())}")
    try:
        return TOOL_REGISTRY[name](**args)
    except Exception as exc:
        return _err(f"Tool '{name}' raised: {exc}")


def list_tools() -> List[Dict[str, str]]:
    """Return a list of all tools with their names and docstrings."""
    return [
        {"name": name, "description": (fn.__doc__ or "").strip().splitlines()[0]}
        for name, fn in TOOL_REGISTRY.items()
    ]
