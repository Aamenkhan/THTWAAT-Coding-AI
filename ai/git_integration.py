import subprocess
from pathlib import Path
from typing import Optional


class GitManager:
    def __init__(self, repo_path: str):
        self.repo_path = str(Path(repo_path).resolve())

    def _run(self, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo_path,
            text=True,
            capture_output=True,
            check=check,
        )

    def init_repo(self) -> str:
        if self.is_repo():
            return "Repository already initialized"
        result = self._run("init")
        if result.returncode != 0:
            return result.stderr.strip() or result.stdout.strip() or "Failed to initialize repository"
        return "Repository initialized"

    def is_repo(self) -> bool:
        result = self._run("rev-parse", "--is-inside-work-tree", check=False)
        return result.returncode == 0 and result.stdout.strip() == "true"

    def status(self) -> str:
        if not self.is_repo():
            return "Repository not initialized"
        result = self._run("status", "--short", "--branch")
        if result.returncode != 0:
            return result.stderr.strip() or result.stdout.strip() or "Status failed"
        output = result.stdout.strip() or "No changes"
        if output.startswith("## "):
            branch = output[3:].split("...")[0].strip()
            return f"On branch {branch}\n{output}"
        return output

    def commit(self, message: str) -> str:
        if not self.is_repo():
            self.init_repo()
        self._run("add", "-A")
        result = self._run("commit", "-m", message, check=False)
        output = result.stdout.strip() or result.stderr.strip()
        if result.returncode != 0:
            return output or "Nothing to commit"
        return output or "Committed changes"

    def create_branch(self, branch_name: str) -> str:
        if not self.is_repo():
            self.init_repo()
        result = self._run("checkout", "-b", branch_name, check=False)
        output = result.stdout.strip() or result.stderr.strip()
        if result.returncode != 0:
            return output or f"Unable to create branch {branch_name}"
        return output or f"Created branch {branch_name}"

    def switch_branch(self, branch_name: str) -> str:
        if not self.is_repo():
            self.init_repo()
        result = self._run("checkout", branch_name, check=False)
        output = result.stdout.strip() or result.stderr.strip()
        if result.returncode != 0:
            return output or f"Unable to switch to {branch_name}"
        return output or f"Switched to {branch_name}"
