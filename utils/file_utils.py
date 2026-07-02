import os
from pathlib import Path
from typing import List


def ensure_directory(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def list_project_files(root: str) -> List[str]:
    root_path = Path(root)
    if not root_path.exists():
        return []
    return [str(path.resolve()) for path in sorted(root_path.rglob("*")) if path.is_file()]


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def write_text(path: str, content: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content, encoding="utf-8")
