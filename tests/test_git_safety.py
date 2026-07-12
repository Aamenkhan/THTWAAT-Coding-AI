import os
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.agent import AIAgent
from ai.pipeline import Pipeline, PipelineRun, Stage, StageResult
from ai.planner import Plan, PlanStep
from ai.tools import ToolResult

class TestGitSafety(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name)
        
        subprocess.run(["git", "init"], cwd=self.repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=self.repo_dir, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.repo_dir, check=True)
        
        (self.repo_dir / "main.py").write_text("print('hello')", encoding="utf-8")
        subprocess.run(["git", "add", "main.py"], cwd=self.repo_dir, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.repo_dir, check=True, capture_output=True)

        from ai.ollama_client import OllamaClient
        OllamaClient.check_model = lambda self: True
        OllamaClient.chat = lambda self, *a, **k: "mock chat response"

        self.agent = AIAgent(model="dummy", project_dir=str(self.repo_dir))
        self.pipeline = Pipeline(self.agent)

        # Mock dependencies to make pipeline run fast
        self.agent.error_recovery.safe_call = lambda *a, **k: ToolResult({"passed": 1, "failed": 0}, ok=True)
        self.agent.reviewer.review_files = lambda *a, **k: []
        self.agent.reviewer.generate_report = lambda *a, **k: "Mock report"
        self.agent.git.generate_commit_message = lambda *a, **k: "feat: mock commit"

    def tearDown(self):
        self.agent.close()
        self.temp_dir.cleanup()

    def test_pipeline_commits_only_accepted_files_and_ignores_stray_untracked(self):
        # a. Creates a dummy untracked file simulating a stray system/secret file
        stray = self.repo_dir / "SERVICE-FATAL.err"
        stray.write_text("error", encoding="utf-8")
        
        # Mock planner to make ONE specific edit
        valid_file = self.repo_dir / "main.py"
        def mock_build_plan(goal):
            step = PlanStep(index=1, name="dummy", tool="WriteFile", args={"path": str(valid_file), "content": "print('hello world')"})
            return Plan(goal="dummy", steps=[step])
        self.agent.planner.build_plan = mock_build_plan
        
        # b. Runs the pipeline commit with only ONE specific accepted edit
        run_res = self.pipeline.start("Update main", on_approval=lambda r, s: True)
        
        if run_res.stage == Stage.FAILED:
            print("PIPELINE ERROR:", run_res.stage_results)
        self.assertEqual(run_res.stage, Stage.DONE)
        
        # Check git log to see what was actually committed
        log = subprocess.run(["git", "show", "--name-status", "HEAD"], cwd=self.repo_dir, capture_output=True, text=True).stdout
        
        # c. Confirms the dummy untracked file is NOT included in the commit
        self.assertIn("main.py", log)
        self.assertNotIn("SERVICE-FATAL.err", log)

    def test_pipeline_skips_commit_if_zero_files_accepted(self):
        # Create a stray untracked file
        stray = self.repo_dir / "stray.txt"
        stray.write_text("stray", encoding="utf-8")
        
        # Mock planner to do NOTHING (0 edits)
        def mock_build_plan_empty(goal):
            return Plan(goal="dummy", steps=[])
        self.agent.planner.build_plan = mock_build_plan_empty
        
        run_res = self.pipeline.start("Do nothing", on_approval=lambda r, s: True)
        
        if run_res.stage == Stage.FAILED:
            print("PIPELINE ERROR:", run_res.stage_results)
        self.assertEqual(run_res.stage, Stage.DONE)
        
        # d. Confirms a 0-accepted-files run does NOT create any commit
        commit_msg = run_res.stage_results.get(Stage.COMMIT).message
        self.assertEqual(commit_msg, "Nothing to commit — no changes were accepted.")
        
        # Verify HEAD is still "init"
        log = subprocess.run(["git", "log", "-1", "--oneline"], cwd=self.repo_dir, capture_output=True, text=True).stdout
        self.assertIn("init", log)

    def test_sensitive_file_flagged_in_diff_viewer(self):
        # e. simulate AI proposing an edit to .env, confirm UI flags it
        from PySide6 import QtWidgets
        from ai.diff_engine import DiffEngine, PendingEdit
        from ui.diff_viewer import DiffViewerDialog
        
        app = QtWidgets.QApplication.instance()
        if not app:
            app = QtWidgets.QApplication(sys.argv)
            
        de = DiffEngine(str(self.repo_dir))
        env_file = self.repo_dir / ".env"
        env_file.write_text("OLD=1", encoding="utf-8")
        
        # bypass error checks to inject pending edit directly
        de._queue[str(env_file)] = PendingEdit(str(env_file), "OLD=1", "NEW=2", "instruction")
        
        dialog = DiffViewerDialog(de)
        
        item = dialog.file_list.item(0)
        self.assertIsNotNone(item, "DiffViewer did not list the pending edit.")
        self.assertIn("⚠️ [SENSITIVE]", item.text(), "Sensitive file was not flagged in UI.")
        
        accepted_files = []
        original_accept = de.accept
        def mock_accept(path):
            accepted_files.append(path)
            return original_accept(path)
        de.accept = mock_accept

        # mock-approve by returning Yes in the prompt
        import unittest.mock
        with unittest.mock.patch('PySide6.QtWidgets.QMessageBox.question', return_value=QtWidgets.QMessageBox.Yes):
            dialog.btn_accept_all.click()
            
        self.assertIn(str(env_file), accepted_files, "Mock-approval failed to place file in accepted edits.")

    def test_accept_all_blocks_on_sensitive_files(self):
        from PySide6 import QtWidgets
        from ai.diff_engine import DiffEngine, PendingEdit
        from ui.diff_viewer import DiffViewerDialog
        import unittest.mock
        
        app = QtWidgets.QApplication.instance()
        if not app:
            app = QtWidgets.QApplication(sys.argv)
            
        de = DiffEngine(str(self.repo_dir))
        
        normal_file = self.repo_dir / "normal.txt"
        env_file = self.repo_dir / ".env"
        
        de._queue[str(normal_file)] = PendingEdit(str(normal_file), "OLD", "NEW", "msg")
        de._queue[str(env_file)] = PendingEdit(str(env_file), "OLD", "NEW", "msg")
        
        dialog = DiffViewerDialog(de)
        
        with unittest.mock.patch('PySide6.QtWidgets.QMessageBox.question', return_value=QtWidgets.QMessageBox.No) as mock_qbox:
            dialog.btn_accept_all.click()
            mock_qbox.assert_called_once()
            
            self.assertEqual(len(de._queue), 2, "Accept All did not abort when user clicked No!")

if __name__ == '__main__':
    unittest.main()
