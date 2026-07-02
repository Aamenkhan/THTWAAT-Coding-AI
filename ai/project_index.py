import os
import re
from pathlib import Path
from typing import List, Dict


class ProjectIndex:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.index_cache: Dict[str, str] = {}
        self._watchers: Dict[str, List[object]] = {}

    def list_files(self, directory: str | None = None) -> List[str]:
        base = Path(directory or self.root)
        if not base.exists():
            return []
        files: List[str] = []
        for path in sorted(base.rglob("*")):
            if path.is_file() and not any(part in {"__pycache__", ".git", ".venv", "venv"} for part in path.parts):
                files.append(str(path.resolve()))
        return files

    def read_text(self, path: str) -> str:
        return Path(path).read_text(encoding="utf-8", errors="ignore")

    def search(self, query: str, directory: str | None = None) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        for file_path in self.list_files(directory):
            content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
            if query.lower() in content.lower():
                results.append({"path": file_path, "content": content})
        return results

    def build_context(self, query: str, directory: str | None = None) -> str:
        relevant_files: List[Dict[str, str]] = []
        for file_path in self.list_files(directory):
            content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
            if query.lower() in content.lower():
                relevant_files.append({"path": file_path, "content": content[:1200]})
        if not relevant_files:
            relevant_files = [{"path": path, "content": self.read_text(path)[:800]} for path in self.list_files(directory)[:5]]
        context_sections = []
        for item in relevant_files[:5]:
            context_sections.append(f"File: {item['path']}\n{item['content']}")
        return "\n\n".join(context_sections)

    def get_outline(self, path: str) -> List[Dict[str, str]]:
        content = Path(path).read_text(encoding="utf-8", errors="ignore")
        outline: List[Dict[str, str]] = []
        for match in re.finditer(r"^\s*(def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", content, re.MULTILINE):
            outline.append({"type": match.group(1), "name": match.group(2), "line": str(content[:match.start()].count("\n") + 1)})
        return outline

    def find_definition(self, symbol: str, directory: str | None = None) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        for file_path in self.list_files(directory):
            content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
            if re.search(rf"^\s*(def|class)\s+{re.escape(symbol)}\b", content, re.MULTILINE):
                results.append({"path": file_path, "symbol": symbol})
        return results

    def find_references(self, symbol: str, directory: str | None = None) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        for file_path in self.list_files(directory):
            content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
            if re.search(rf"\b{re.escape(symbol)}\b", content):
                results.append({"path": file_path, "symbol": symbol})
        return results

    def rename_symbol(self, path: str, old_name: str, new_name: str) -> bool:
        target = Path(path)
        if not target.exists():
            return False
        content = target.read_text(encoding="utf-8", errors="ignore")
        updated = re.sub(rf"\b{re.escape(old_name)}\b", new_name, content)
        if updated == content:
            return False
        target.write_text(updated, encoding="utf-8")
        return True

    def watch(self, path: str, callback) -> None:
        self._watchers[str(Path(path).resolve())] = [callback]
