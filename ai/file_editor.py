from pathlib import Path
from typing import Optional


class FileEditor:
    def __init__(self, path: str):
        self.path = Path(path)
        self.original_text = self.path.read_text(encoding="utf-8", errors="ignore") if self.path.exists() else ""

    def read(self) -> str:
        return self.path.read_text(encoding="utf-8", errors="ignore") if self.path.exists() else ""

    def write(self, content: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(content, encoding="utf-8")

    def patch(self, old_text: str, new_text: str) -> bool:
        current = self.read()
        if old_text not in current:
            return False
        updated = current.replace(old_text, new_text, 1)
        self.write(updated)
        return True

    def revert(self) -> None:
        self.write(self.original_text)
