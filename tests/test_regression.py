"""
tests/test_regression.py — Full Regression Test Suite (Priority 5)
Tests every module: Planner, Pipeline, Context Engine, Diff Engine,
Memory, Tool Registry, Workspace Search, Git, Terminal Agent, Security, Providers, Reliability.
Runs headlessly — no UI, no Ollama required for most tests.
"""

import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

# Ensure project root is on path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------

class TestToolRegistry(unittest.TestCase):

    def test_list_tools_returns_14_tools(self):
        from ai.tools import list_tools
        tools = list_tools()
        self.assertGreaterEqual(len(tools), 14)
        names = [t["name"] for t in tools]
        for expected in ["ReadFile", "WriteFile", "SearchFiles", "RunTests", "GitStatus"]:
            self.assertIn(expected, names, f"Missing tool: {expected}")

    def test_read_file_tool_returns_content(self):
        from ai.tools import call_tool
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write("print('hello')\n")
            path = f.name
        try:
            result = call_tool("ReadFile", {"path": path})
            self.assertTrue(result.ok)
            self.assertIn("hello", result.data["content"])
        finally:
            os.unlink(path)

    def test_write_file_tool_creates_file(self):
        from ai.tools import call_tool
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "out.py")
            result = call_tool("WriteFile", {"path": path, "content": "x = 1\n"})
            self.assertTrue(result.ok)
            self.assertTrue(Path(path).exists())

    def test_list_directory_tool(self):
        from ai.tools import call_tool
        result = call_tool("ListDirectory", {"directory": str(ROOT)})
        self.assertTrue(result.ok)
        self.assertGreater(len(result.data), 0)

    def test_search_files_tool(self):
        from ai.tools import call_tool
        result = call_tool("SearchFiles", {"query": "class AIAgent", "directory": str(ROOT)})
        self.assertTrue(result.ok)
        self.assertGreater(result.data["count"], 0)

    def test_failed_tool_returns_ok_false(self):
        from ai.tools import call_tool
        result = call_tool("ReadFile", {"path": "/nonexistent/path/abc.xyz"})
        self.assertFalse(result.ok)
        self.assertIn("error", result.data)


# ---------------------------------------------------------------------------
# Diff Engine
# ---------------------------------------------------------------------------

class TestDiffEngine(unittest.TestCase):

    def setUp(self):
        from ai.diff_engine import DiffEngine
        self.engine = DiffEngine()

    def test_propose_edit_stages_change(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write("# original\n")
            self.path = f.name
        edit = self.engine.propose_edit(self.path, "# modified\n", "test edit")
        self.assertIsNotNone(edit)
        self.assertEqual(edit.path, str(Path(self.path).resolve()))
        self.assertIn("modified", edit.diff)

    def test_accept_applies_change(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write("# original\n")
            path = f.name
        self.engine.propose_edit(path, "# modified\n", "test")
        ok = self.engine.accept(path)
        self.assertTrue(ok)
        self.assertEqual(Path(path).read_text(encoding="utf-8"), "# modified\n")
        os.unlink(path)

    def test_reject_discards_change(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write("# original\n")
            path = f.name
        self.engine.propose_edit(path, "# modified\n", "test")
        ok = self.engine.reject(path)
        self.assertTrue(ok)
        self.assertEqual(Path(path).read_text(encoding="utf-8"), "# original\n")
        self.assertEqual(len(self.engine.pending_edits()), 0)
        os.unlink(path)

    def test_accept_all_returns_paths(self):
        with tempfile.TemporaryDirectory() as d:
            files = []
            for i in range(3):
                p = os.path.join(d, f"f{i}.py")
                Path(p).write_text(f"# file {i}\n", encoding="utf-8")
                self.engine.propose_edit(p, f"# modified {i}\n", "test")
                files.append(p)
            accepted = self.engine.accept_all()
            self.assertEqual(len(accepted), 3)

    def test_pending_edits_is_empty_after_accept_all(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.py")
            Path(p).write_text("x\n")
            self.engine.propose_edit(p, "y\n")
            self.engine.accept_all()
            self.assertEqual(len(self.engine.pending_edits()), 0)


# ---------------------------------------------------------------------------
# Context Engine
# ---------------------------------------------------------------------------

class TestContextEngine(unittest.TestCase):

    def setUp(self):
        from ai.context_engine import ContextEngine
        self.engine = ContextEngine(str(ROOT))

    def test_build_context_respects_token_budget(self):
        ctx = self.engine.build_context("agent planner", budget=500)
        # 500 tokens * 4 chars = ~2000 chars max
        self.assertLessEqual(len(ctx), 3000)

    def test_get_relevant_files_returns_list(self):
        files = self.engine.get_relevant_files("AIAgent planner", top_n=5)
        self.assertIsInstance(files, list)
        self.assertLessEqual(len(files), 5)

    def test_relevant_files_contain_agent(self):
        files = self.engine.get_relevant_files("AIAgent", top_n=10)
        basenames = [Path(f).name for f in files]
        self.assertIn("agent.py", basenames)

    def test_invalidate_cache(self):
        self.engine.build_context("test")
        self.engine.invalidate_cache()
        self.assertEqual(len(self.engine._file_cache), 0)


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class TestSessionMemory(unittest.TestCase):

    def setUp(self):
        from ai.memory import SessionMemory
        self.mem = SessionMemory()

    def test_set_and_get_task(self):
        self.mem.set_task("Build auth system")
        self.assertEqual(self.mem.get_task(), "Build auth system")

    def test_add_and_get_prompts(self):
        self.mem.add_prompt("Create login page", mode="agent")
        self.mem.add_prompt("Fix bug", mode="chat")
        prompts = self.mem.recent_prompts(2)
        self.assertEqual(len(prompts), 2)
        self.assertEqual(prompts[-1]["prompt"], "Fix bug")

    def test_add_edit_appears_in_summary(self):
        self.mem.add_edit("auth/login.py", "Created login module")
        summary = self.mem.get_summary()
        self.assertIn("login.py", summary)

    def test_branch_in_summary(self):
        self.mem.set_branch("feature/auth")
        summary = self.mem.get_summary()
        self.assertIn("feature/auth", summary)

    def test_add_error(self):
        self.mem.add_error("ImportError: no module named foo", "context: login")
        errors = self.mem.recent_errors(1)
        self.assertEqual(len(errors), 1)
        self.assertIn("foo", errors[0]["error"])

    def test_clear_errors(self):
        self.mem.add_error("some error")
        self.mem.clear_errors()
        self.assertEqual(len(self.mem.recent_errors()), 0)

    def test_memory_summary_contains_all_sections(self):
        self.mem.set_task("task")
        self.mem.set_branch("main")
        self.mem.add_current_file("app.py")
        summary = self.mem.get_summary()
        self.assertIn("Session Memory", summary)
        self.assertIn("main", summary)


# ---------------------------------------------------------------------------
# Workspace Search
# ---------------------------------------------------------------------------

class TestWorkspaceSearch(unittest.TestCase):

    def setUp(self):
        from ai.workspace_search import WorkspaceSearch
        self.ws = WorkspaceSearch(str(ROOT))

    def test_find_symbol_locates_class(self):
        results = self.ws.find_symbol("AIAgent")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].symbol_type, "class")

    def test_find_symbol_locates_function(self):
        results = self.ws.find_symbol("build_context")
        self.assertGreater(len(results), 0)

    def test_project_wide_search_returns_results(self):
        results = self.ws.project_wide_search("class.*Provider", case_sensitive=False)
        self.assertGreater(len(results), 0)

    def test_rename_symbol_in_temp_dir(self):
        from ai.workspace_search import WorkspaceSearch
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "sample.py"
            f.write_text("def old_func():\n    pass\n\nold_func()\n")
            ws = WorkspaceSearch(d)
            changed = ws.rename_symbol("old_func", "new_func")
            self.assertIn(str(f), changed)
            content = f.read_text(encoding="utf-8")
            self.assertIn("new_func", content)
            self.assertNotIn("old_func", content)
            ws.close()

    def test_go_to_definition_returns_location(self):
        loc = self.ws.go_to_definition("Pipeline")
        self.assertIsNotNone(loc)
        self.assertGreater(loc.line, 0)


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

class TestSecurityGuard(unittest.TestCase):

    def setUp(self):
        from ai.security import SecurityGuard
        self.guard = SecurityGuard()

    def test_safe_command_passes(self):
        from ai.security import RiskLevel
        risk, reason = self.guard.evaluate("python app.py")
        self.assertEqual(risk, RiskLevel.SAFE)

    def test_rm_rf_is_critical(self):
        from ai.security import RiskLevel
        risk, reason = self.guard.evaluate("rm -rf /")
        self.assertEqual(risk, RiskLevel.CRITICAL)
        self.assertTrue(len(reason) > 0)

    def test_git_reset_hard_is_high(self):
        from ai.security import RiskLevel
        risk, reason = self.guard.evaluate("git reset --hard HEAD~1")
        self.assertEqual(risk, RiskLevel.HIGH)

    def test_shell_script_is_medium(self):
        from ai.security import RiskLevel
        risk, reason = self.guard.evaluate("./setup.sh")
        self.assertEqual(risk, RiskLevel.MEDIUM)

    def test_check_denies_without_callback(self):
        from ai.security import SecurityDecision
        decision, _, _ = self.guard.check("rm -rf /tmp/test")
        self.assertEqual(decision, SecurityDecision.DENY)

    def test_check_allows_with_approving_callback(self):
        from ai.security import SecurityDecision, SecurityGuard
        g = SecurityGuard(approval_callback=lambda cmd, reason, risk: True)
        decision, _, _ = g.check("git reset --hard HEAD~1")
        self.assertEqual(decision, SecurityDecision.ALLOW)


# ---------------------------------------------------------------------------
# Git Manager
# ---------------------------------------------------------------------------

class TestGitManager(unittest.TestCase):

    def setUp(self):
        from ai.git_integration import GitManager
        self.git = GitManager(str(ROOT))

    def test_is_repo_returns_true(self):
        self.assertTrue(self.git.is_repo())

    def test_status_returns_string(self):
        status = self.git.status()
        self.assertIsInstance(status, str)
        self.assertTrue(len(status) > 0)

    def test_current_branch_returns_string(self):
        branch = self.git.current_branch()
        self.assertIsInstance(branch, str)
        self.assertTrue(len(branch) > 0)

    def test_log_returns_commits(self):
        commits = self.git.log(n=3)
        self.assertIsInstance(commits, list)

    def test_diff_returns_string(self):
        diff = self.git.diff()
        self.assertIsInstance(diff, str)

    def test_list_branches(self):
        branches = self.git.list_branches()
        self.assertIsInstance(branches, list)


# ---------------------------------------------------------------------------
# Terminal Agent
# ---------------------------------------------------------------------------

class TestTerminalAgent(unittest.TestCase):

    def setUp(self):
        from ai.terminal_agent import TerminalAgent
        self.agent = TerminalAgent(default_cwd=str(ROOT))

    def test_pre_approved_command_runs(self):
        cmd = self.agent.run_approved("echo hello")
        self.assertEqual(cmd.returncode, 0)
        self.assertIn("hello", cmd.stdout)

    def test_denied_command_is_skipped(self):
        from ai.terminal_agent import CommandStatus
        cmd = self.agent.run_with_approval("echo denied")
        self.assertEqual(cmd.status, CommandStatus.DENIED)

    def test_approved_via_callback(self):
        from ai.terminal_agent import TerminalAgent, CommandStatus
        agent = TerminalAgent(
            approval_callback=lambda c: True,
            default_cwd=str(ROOT),
        )
        cmd = agent.run_with_approval("echo approved")
        self.assertEqual(cmd.returncode, 0)

    def test_history_tracks_commands(self):
        self.agent.run_approved("echo a")
        self.agent.run_approved("echo b")
        self.assertEqual(len(self.agent.history()), 2)

    def test_failed_command_has_nonzero_exit(self):
        cmd = self.agent.run_approved("python -c \"raise SystemExit(42)\"")
        self.assertEqual(cmd.returncode, 42)


# ---------------------------------------------------------------------------
# Reliability Layer
# ---------------------------------------------------------------------------

class TestReliability(unittest.TestCase):

    def test_reliable_call_succeeds_first_try(self):
        from ai.reliability import reliable_call
        result = reliable_call(lambda: 42, name="test_fn")
        self.assertEqual(result, 42)

    def test_reliable_call_retries_on_failure(self):
        from ai.reliability import reliable_call, ReliabilityConfig
        attempts = []

        def flaky():
            attempts.append(1)
            if len(attempts) < 3:
                raise ValueError("not yet")
            return "ok"

        cfg = ReliabilityConfig(max_retries=3, retry_delay=0.01)
        result = reliable_call(flaky, config=cfg, name="flaky_fn")
        self.assertEqual(result, "ok")
        self.assertEqual(len(attempts), 3)

    def test_reliable_call_times_out(self):
        from ai.reliability import reliable_call, ReliabilityConfig
        cfg = ReliabilityConfig(max_retries=1, timeout_seconds=0.1, retry_delay=0.0)
        with self.assertRaises(TimeoutError):
            reliable_call(lambda: time.sleep(5), config=cfg, name="slow_fn")

    def test_metrics_records_calls(self):
        from ai.reliability import reliable_call, metrics
        metrics.clear()
        reliable_call(lambda: "x", name="metric_test")
        summary = metrics.summary()
        self.assertGreaterEqual(summary["total_calls"], 1)

    def test_stage_timer_records_duration(self):
        from ai.reliability import StageTimer
        with StageTimer("TestStage") as t:
            time.sleep(0.05)
        self.assertGreater(t.duration_ms, 40)

    def test_with_reliability_decorator(self):
        from ai.reliability import with_reliability
        @with_reliability(max_retries=1, timeout=5.0, component="test")
        def my_fn(x):
            return x * 2
        self.assertEqual(my_fn(21), 42)


# ---------------------------------------------------------------------------
# Provider Router
# ---------------------------------------------------------------------------

class TestProviderRouter(unittest.TestCase):

    def test_register_and_resolve_provider(self):
        from ai.providers import ProviderRouter, OllamaProvider
        router = ProviderRouter()
        p = OllamaProvider()
        router.register(p)
        self.assertIn("ollama", router.available_providers())

    def test_build_router_from_config(self):
        from ai.providers import build_router_from_config
        config = {
            "primary_provider": "ollama",
            "providers": {
                "ollama": {"base_url": "http://localhost:11434"},
            }
        }
        router = build_router_from_config(config)
        self.assertIn("ollama", router.available_providers())

    def test_openai_provider_lists_models(self):
        from ai.providers import OpenAIProvider
        p = OpenAIProvider(api_key="test-key")
        models = p.list_models()
        self.assertIn("gpt-4o", models)

    def test_claude_provider_lists_models(self):
        from ai.providers import ClaudeProvider
        p = ClaudeProvider(api_key="test-key")
        models = p.list_models()
        self.assertIn("claude-3-5-sonnet-20241022", models)

    def test_gemini_provider_lists_models(self):
        from ai.providers import GeminiProvider
        p = GeminiProvider(api_key="test-key")
        models = p.list_models()
        self.assertIn("gemini-flash-latest", models)

    def test_no_providers_raises(self):
        from ai.providers import ProviderRouter
        router = ProviderRouter()
        with self.assertRaises(RuntimeError):
            router.generate("test", "model")


# ---------------------------------------------------------------------------
# Language Support
# ---------------------------------------------------------------------------

class TestLanguageSupport(unittest.TestCase):

    def setUp(self):
        from ai.language_support import LanguageSupport
        self.ls = LanguageSupport()

    def test_detect_python_file(self):
        profile = self.ls.detect("app.py")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.name, "Python")

    def test_detect_typescript_file(self):
        profile = self.ls.detect("index.tsx")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.name, "TypeScript")

    def test_detect_project_language(self):
        profile = self.ls.detect_project(str(ROOT))
        self.assertIsNotNone(profile)
        self.assertEqual(profile.name, "Python")

    def test_all_supported_has_12_languages(self):
        langs = self.ls.all_supported()
        self.assertGreaterEqual(len(langs), 12)

    def test_build_system_prompt_contains_idioms(self):
        profile = self.ls.detect("app.py")
        prompt = self.ls.build_system_prompt(profile)
        self.assertIn("SOLID", prompt)
        self.assertIn("Python", prompt)


# ---------------------------------------------------------------------------
# Task Queue
# ---------------------------------------------------------------------------

class TestTaskQueue(unittest.TestCase):

    def test_enqueue_creates_task(self):
        from ai.task_queue import TaskQueue
        tq = TaskQueue()
        task = tq.enqueue("Test goal")
        self.assertIsNotNone(task.task_id)
        self.assertEqual(task.goal, "Test goal")

    def test_cancel_marks_task(self):
        from ai.task_queue import TaskQueue
        tq = TaskQueue()
        task = tq.enqueue("Long goal")
        time.sleep(0.1)
        ok = tq.cancel(task.task_id)
        self.assertTrue(ok)

    def test_all_tasks_returns_list(self):
        from ai.task_queue import TaskQueue
        tq = TaskQueue()
        tq.enqueue("goal a")
        tq.enqueue("goal b")
        self.assertGreaterEqual(len(tq.all_tasks()), 2)


# ---------------------------------------------------------------------------
# Pipeline (unit — no LLM required)
# ---------------------------------------------------------------------------

class TestPipelineStages(unittest.TestCase):

    def test_pipeline_order_is_correct(self):
        from ai.pipeline import _PIPELINE_ORDER, Stage
        names = [s.name for s in _PIPELINE_ORDER]
        self.assertEqual(names[0], "ANALYZE")
        self.assertEqual(names[-1], "DONE")
        review_idx  = names.index("REVIEW")
        tests_idx   = names.index("RUN_TESTS")
        fix_idx     = names.index("FIX_ERRORS")
        commit_idx  = names.index("COMMIT")
        self.assertLess(review_idx, tests_idx)
        self.assertLess(tests_idx, fix_idx)
        self.assertLess(fix_idx, commit_idx)

    def test_pipeline_run_progress_increases(self):
        from ai.pipeline import PipelineRun, Stage, _PIPELINE_ORDER
        run = PipelineRun(goal="test", run_id="x")
        prev = -1
        for stage in _PIPELINE_ORDER:
            run.stage = stage
            self.assertGreaterEqual(run.progress_percent, prev)
            prev = run.progress_percent

    def test_all_stages_have_labels_and_icons(self):
        from ai.pipeline import _STAGE_LABELS, _STAGE_ICONS, _PIPELINE_ORDER
        for s in _PIPELINE_ORDER:
            self.assertIn(s, _STAGE_LABELS)
            self.assertIn(s, _STAGE_ICONS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
