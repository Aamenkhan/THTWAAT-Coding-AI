import subprocess
from pathlib import Path
from typing import List, Optional


class GitManager:
    def __init__(self, repo_path: str, ollama_client=None, model: str = "qwen2.5-coder:3b"):
        self.repo_path = str(Path(repo_path).resolve())
        self._client = ollama_client
        self._model = model

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

    def current_branch(self) -> str:
        result = self._run("rev-parse", "--abbrev-ref", "HEAD")
        return result.stdout.strip() if result.returncode == 0 else "unknown"

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

    def checkout(self, target: str) -> str:
        """Checkout a branch or commit hash."""
        return self.switch_branch(target)

    def rollback(self, n: int = 1) -> str:
        """Hard reset to HEAD~n — discards n commits. Requires confirmation."""
        if not self.is_repo():
            return "Repository not initialized"
        result = self._run("reset", "--hard", f"HEAD~{n}", check=False)
        output = result.stdout.strip() or result.stderr.strip()
        if result.returncode != 0:
            return output or f"Rollback by {n} commit(s) failed"
        return output or f"Rolled back {n} commit(s)"

    def diff(self, staged: bool = False) -> str:
        """Return unified diff of working tree (or staged changes)."""
        args = ["diff"]
        if staged:
            args.append("--cached")
        result = self._run(*args)
        return result.stdout if result.returncode == 0 else result.stderr.strip()

    def log(self, n: int = 10) -> List[dict]:
        """Return last n commits as a list of dicts."""
        result = self._run("log", f"-{n}", "--pretty=format:%H|%s|%an|%ar")
        if result.returncode != 0:
            return []
        commits = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("|", 3)
            if len(parts) == 4:
                commits.append({
                    "hash": parts[0][:8],
                    "message": parts[1],
                    "author": parts[2],
                    "ago": parts[3],
                })
        return commits

    def generate_commit_message(self) -> str:
        """Use the LLM to generate a commit message from the current diff."""
        diff_text = self.diff()
        if not diff_text.strip():
            return "chore: minor updates"
        if self._client is None:
            return "feat: AI-assisted changes"
        prompt = (
            "Write a concise, professional git commit message for this diff.\n"
            "Follow Conventional Commits format (e.g. feat:, fix:, refactor:).\n"
            "Single line, max 72 chars. Respond with ONLY the commit message.\n\n"
            f"```diff\n{diff_text[:3000]}\n```"
        )
        try:
            msg = self._client.generate(prompt, model=self._model).strip()
            return msg.splitlines()[0][:72] if msg else "chore: AI-assisted changes"
        except Exception:
            return "chore: AI-assisted changes"

    def list_branches(self) -> List[str]:
        result = self._run("branch", "--list")
        if result.returncode != 0:
            return []
        return [b.strip().lstrip("* ") for b in result.stdout.splitlines() if b.strip()]


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

    def commit(self, message: str, files: list = None, allow_sensitive: bool = False) -> str:
        if not self.is_repo():
            self.init_repo()
            
        if not files:
            return "No explicit files provided for commit."
            
        import fnmatch
        import os
        sensitive_patterns = [".env", "*.key", "*secret*", "*credential*", "crash_reports/*", "config_backups/*"]
        
        for f in files:
            normalized_f = f.replace('\\', '/')
            is_sensitive = any(
                fnmatch.fnmatch(normalized_f, pat) or fnmatch.fnmatch(os.path.basename(normalized_f), pat)
                for pat in sensitive_patterns
            )
            if is_sensitive and not allow_sensitive:
                return f"Safety guard: blocked staging of sensitive file '{f}'"
                
        self._run("add", *files)
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
