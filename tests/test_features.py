import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.project_index import ProjectIndex
from ai.agent import AIAgent


class FeatureTests(unittest.TestCase):
    def test_project_index_lists_source_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("print('hello')\n", encoding="utf-8")
            (root / ".git").mkdir()
            index = ProjectIndex(str(root))
            files = index.list_files(str(root))
            self.assertTrue(any("main.py" in item for item in files))
            self.assertFalse(any(".git" in item for item in files))

    def test_agent_can_create_and_edit_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            agent = AIAgent(model="dummy")
            path = Path(temp_dir) / "demo.py"
            self.assertTrue(agent.create_file(str(path), "print('x')\n"))
            self.assertTrue(agent.edit_file(str(path), "print('y')\n"))
            self.assertEqual(path.read_text(encoding="utf-8"), "print('y')\n")

    def test_git_helpers_are_available(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            (repo / "file.txt").write_text("hello\n", encoding="utf-8")
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
            subprocess.run(["git", "add", "file.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            status = subprocess.run(["git", "status", "--short"], cwd=repo, check=True, capture_output=True, text=True)
            self.assertEqual(status.stdout, "")


if __name__ == "__main__":
    unittest.main()
