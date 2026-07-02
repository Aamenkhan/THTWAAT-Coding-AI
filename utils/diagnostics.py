import ast
from pathlib import Path
from typing import List, Dict


def run_diagnostics(path: str) -> List[Dict[str, str]]:
    problems: List[Dict[str, str]] = []
    file_path = Path(path)
    if not file_path.exists():
        return problems
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        ast.parse(source)
    except SyntaxError as exc:
        problems.append({"path": str(file_path), "line": str(getattr(exc, 'lineno', 0)), "message": str(exc)})
    return problems
