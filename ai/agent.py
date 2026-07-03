"""
ai/agent.py — Master AI Agent
Stage 3 + Features 4-18: All systems integrated.
Capable of receiving one prompt and autonomously:
  Analyze → Plan → Find Files → Create/Edit → Test → Fix → Show Diffs
  → Commit (after approval) → Summarize
Production-quality. SOLID principles. No placeholder code.
"""

import threading
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

from ai.ollama_client import OllamaClient
from ai.tools import call_tool, list_tools, ToolResult
from ai.diff_engine import DiffEngine
from ai.planner import Planner, Plan, ProgressCallback
from ai.context_engine import ContextEngine
from ai.memory import SessionMemory
from ai.language_support import LanguageSupport
from ai.security import SecurityGuard, SecurityDecision
from ai.error_recovery import ErrorRecovery
from ai.workspace_search import WorkspaceSearch
from ai.code_reviewer import CodeReviewer
from ai.task_queue import TaskQueue
from ai.terminal_agent import TerminalAgent
from ai.git_integration import GitManager


class AIAgent:
    """
    Autonomous coding agent integrating all systems.
    Receives a single high-level goal and executes it end-to-end.
    """

    def __init__(
        self,
        model: str = "qwen2.5-coder:3b",
        base_url: Optional[str] = None,
        project_dir: str = ".",
        memory_path: Optional[str] = None,
    ):
        self.model = model
        self.project_dir = str(Path(project_dir).resolve())

        # Core AI
        self.client = OllamaClient(base_url=base_url)

        # Feature systems
        self.diff_engine    = DiffEngine(on_change=self._on_file_change)
        self.context_engine = ContextEngine(project_dir)
        self.memory         = SessionMemory(persist_path=memory_path)
        self.security       = SecurityGuard(approval_callback=self._security_approval)
        self.error_recovery = ErrorRecovery(self.client, model=model)
        self.workspace      = WorkspaceSearch(project_dir)
        self.reviewer       = CodeReviewer(self.client, model=model)
        self.git            = GitManager(project_dir, ollama_client=self.client, model=model)
        self.language       = LanguageSupport()
        self.task_queue     = TaskQueue(agent=self)
        self.terminal       = TerminalAgent(
            ollama_client=self.client, model=model, default_cwd=self.project_dir
        )
        self.planner        = Planner(
            ollama_client=self.client,
            diff_engine=self.diff_engine,
            project_dir=self.project_dir,
            model=model,
        )

        # Callbacks for UI
        self._security_ui_callback: Optional[Callable] = None
        self._activity_callback: Optional[Callable[[str, str], None]] = None

        # Update memory with current branch
        try:
            self.memory.set_branch(self.git.current_branch())
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Feature 18 — Full Autonomous Goal Execution
    # ------------------------------------------------------------------

    def execute_goal(
        self,
        goal: str,
        on_progress: Optional[ProgressCallback] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> Dict[str, Any]:
        """
        Master autonomous entry point.
        Receives one goal, fully executes it, returns summary.

        Pipeline:
          1. Detect language & build optimized system prompt
          2. Build smart context (only relevant files)
          3. Create step-by-step plan
          4. Execute: find files → create/edit → test → fix errors
          5. Show diffs for user review
          6. After approval: commit with AI-generated message
          7. Summarize everything
        """
        self.memory.set_task(goal)
        self._emit_activity("goal", f"🎯 New goal: {goal}")

        def emit(event: str, message: str, data: Optional[Dict] = None):
            if on_progress:
                on_progress(event, message, data or {})
            self._emit_activity(event, message)

        # 1. Language detection
        lang_profile = self.language.detect_project(self.project_dir)
        lang_system_prompt = (
            self.language.build_system_prompt(lang_profile) if lang_profile
            else "You are an expert software developer. Write production-quality code.\n"
        )

        # 2. Build context
        emit("analyze", "🔍 Analyzing project structure...")
        context = self.context_engine.build_context(goal, budget=3000)

        # 3. Plan
        emit("plan", "📋 Building execution plan...")
        self.planner.project_dir = self.project_dir
        self.planner._system_prefix = lang_system_prompt

        plan = self.planner.run(
            goal,
            on_progress=on_progress,
            stop_event=stop_event,
        )

        # 4. Post-plan: run tests to detect failures
        emit("test", "🧪 Running tests to detect failures...")
        test_result = self.error_recovery.safe_call(
            "RunTests", {"directory": self.project_dir}
        )
        if not test_result.ok:
            emit("test_fail", f"⚠ Tests failed: {test_result.data.get('error', '')}")
            self.memory.add_error(str(test_result.data.get("error", "")), context="post-plan tests")
        else:
            passed = test_result.data.get("passed", 0)
            emit("test_ok", f"✅ Tests: {passed} passed")

        # 5. Code review
        pending = self.diff_engine.pending_edits()
        review_paths = [e.path for e in pending]
        if review_paths:
            emit("review", f"📋 Reviewing {len(review_paths)} changed file(s)...")
            review_results = self.reviewer.review_files(review_paths)
            report = self.reviewer.generate_report(review_results)
            emit("review_done", "Review complete", {"report": report})

        # 6. Summary
        pending_count = len(self.diff_engine.pending_edits())
        summary = self._build_summary(goal, plan, pending_count, test_result)
        emit("complete", summary, {
            "pending_edits": [e.path for e in self.diff_engine.pending_edits()],
            "summary": summary,
        })

        self.memory.complete_task("done")
        return {
            "goal": goal,
            "steps_executed": len(plan.steps),
            "pending_edits": pending_count,
            "summary": summary,
        }

    def _build_summary(self, goal: str, plan: Plan, pending: int, test_result) -> str:
        steps_done = sum(1 for s in plan.steps if s.status == "done")
        steps_fail = sum(1 for s in plan.steps if s.status == "failed")
        lines = [
            f"✅ Goal: {goal}",
            f"📋 Plan: {steps_done}/{len(plan.steps)} steps completed ({steps_fail} failed)",
            f"📝 File changes: {pending} pending review",
        ]
        if test_result.ok:
            lines.append(f"🧪 Tests: {test_result.data.get('passed', '?')} passed")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Planning & execution
    # ------------------------------------------------------------------

    def plan_and_execute(
        self,
        goal: str,
        on_progress: Optional[ProgressCallback] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> Plan:
        self.memory.add_prompt(goal, mode="agent")
        self.planner.project_dir = self.project_dir
        return self.planner.run(goal, on_progress=on_progress, stop_event=stop_event)

    def build_plan_only(self, goal: str) -> Plan:
        self.planner.project_dir = self.project_dir
        return self.planner.build_plan(goal)

    # ------------------------------------------------------------------
    # Basic chat
    # ------------------------------------------------------------------

    def chat(self, prompt: str, context: Optional[str] = None) -> str:
        self.memory.add_prompt(prompt, mode="chat")
        full_context = context
        if not full_context:
            full_context = self.context_engine.build_context(prompt, budget=2000)
        mem_summary = self.memory.get_summary()
        return self.client.generate(
            self._build_prompt(prompt, full_context, mem_summary),
            model=self.model,
        )

    def stream_chat(
        self,
        prompt: str,
        context: Optional[str] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> Iterator[str]:
        self.memory.add_prompt(prompt, mode="chat")
        full_context = context
        if not full_context:
            full_context = self.context_engine.build_context(prompt, budget=2000)
        mem_summary = self.memory.get_summary()
        yield from self.client.generate_stream(
            self._build_prompt(prompt, full_context, mem_summary),
            model=self.model,
            stop_event=stop_event,
        )

    def chat_with_context(
        self,
        prompt: str,
        context: Optional[str] = None,
        project_index=None,
    ) -> str:
        if project_index and not context:
            context = project_index.build_context(prompt)
        return self.chat(prompt, context=context)

    def _build_prompt(
        self,
        prompt: str,
        context: Optional[str] = None,
        memory_summary: Optional[str] = None,
    ) -> str:
        parts = []
        if memory_summary:
            parts.append(memory_summary)
        if context:
            parts.append(f"Project context:\n{context}")
        parts.append(f"User request:\n{prompt}")
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Code actions
    # ------------------------------------------------------------------

    def explain_code(self, code: str) -> str:
        prompt = (
            "Explain the following code clearly and concisely. "
            "Mention purpose, flow, and any important edge cases.\n\n"
            f"```python\n{code}\n```"
        )
        return self.chat(prompt)

    def fix_errors(self, code: str, error_message: str) -> str:
        prompt = (
            "You are a Python debugging assistant. Fix the code and explain the change. "
            "Return only the corrected code and a brief explanation.\n\n"
            f"Error:\n{error_message}\n\nCode:\n```python\n{code}\n```"
        )
        return self.chat(prompt)

    def optimize_code(self, code: str) -> str:
        prompt = (
            "Optimize the following Python code for clarity and maintainability. "
            "Preserve behavior while improving structure.\n\n"
            f"```python\n{code}\n```"
        )
        return self.chat(prompt)

    def review_file(self, path: str):
        return self.reviewer.review_file(path)

    # ------------------------------------------------------------------
    # Tool Registry
    # ------------------------------------------------------------------

    def use_tool(self, tool_name: str, **kwargs) -> ToolResult:
        decision, risk, reason = self.security.check(tool_name + " " + str(kwargs))
        if decision.name == "DENY":
            from ai.tools import ToolResult as TR
            return TR({"error": f"Blocked by security: {reason}"}, ok=False)
        result = self.error_recovery.safe_call(tool_name, kwargs)
        self._emit_activity("tool", f"[{tool_name}] {'OK' if result.ok else 'FAIL'}")
        from ai.tools import ToolResult as TR
        return TR(result.data, ok=result.ok)

    def available_tools(self) -> List[Dict[str, str]]:
        return list_tools()

    # ------------------------------------------------------------------
    # Workspace search
    # ------------------------------------------------------------------

    def find_symbol(self, name: str):
        return self.workspace.find_symbol(name)

    def find_references(self, name: str):
        return self.workspace.find_references(name)

    def rename_symbol(self, old: str, new: str) -> Dict[str, int]:
        return self.workspace.rename_symbol(old, new)

    def go_to_definition(self, name: str):
        return self.workspace.go_to_definition(name)

    def search_project(self, query: str):
        return self.workspace.project_wide_search(query)

    # ------------------------------------------------------------------
    # Diff Engine shortcuts
    # ------------------------------------------------------------------

    def propose_edit(self, path: str, content: str, description: str = ""):
        return self.diff_engine.propose_edit(path, content, description)

    def pending_edits(self):
        return self.diff_engine.pending_edits()

    def accept_edit(self, path: str) -> bool:
        return self.diff_engine.accept(path)

    def reject_edit(self, path: str) -> bool:
        return self.diff_engine.reject(path)

    def accept_all_edits(self) -> List[str]:
        accepted = self.diff_engine.accept_all()
        for p in accepted:
            self.memory.add_edit(p, "Accepted via diff viewer")
        return accepted

    def reject_all_edits(self) -> List[str]:
        return self.diff_engine.reject_all()

    def commit_after_approval(self) -> str:
        """Generate AI commit message and commit all staged changes."""
        msg = self.git.generate_commit_message()
        return self.git.commit(msg)

    # ------------------------------------------------------------------
    # Git shortcuts
    # ------------------------------------------------------------------

    def git_status(self) -> str:
        return self.git.status()

    def git_diff(self) -> str:
        return self.git.diff()

    def git_commit(self, message: str) -> str:
        return self.git.commit(message)

    def git_log(self, n: int = 10):
        return self.git.log(n)

    def git_rollback(self, n: int = 1) -> str:
        decision, _, reason = self.security.check("git reset --hard")
        if decision.name == "DENY":
            return f"Blocked: {reason}"
        return self.git.rollback(n)

    # ------------------------------------------------------------------
    # Legacy direct file ops (backward compat)
    # ------------------------------------------------------------------

    def create_file(self, path: str, content: str) -> bool:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.memory.add_edit(path, "Direct create")
        return True

    def edit_file(self, path: str, new_content: str) -> bool:
        target = Path(path)
        if not target.exists():
            raise FileNotFoundError(path)
        target.write_text(new_content, encoding="utf-8")
        self.memory.add_edit(path, "Direct edit")
        return True

    def create_project(self, prompt: str, project_root: str) -> List[str]:
        created_files: List[str] = []
        base = Path(project_root)
        base.mkdir(parents=True, exist_ok=True)

        readme = base / "README.md"
        readme.write_text(
            f"# Project scaffold from prompt\n\nPrompt: {prompt}\n\n"
            "This project was created using the local AI IDE.\n",
            encoding="utf-8",
        )
        created_files.append(str(readme))

        main_py = base / "main.py"
        main_py.write_text("print('Hello from the generated project')\n", encoding="utf-8")
        created_files.append(str(main_py))

        requirements = base / "requirements.txt"
        requirements.write_text("requests>=2.9.0\n", encoding="utf-8")
        created_files.append(str(requirements))
        return created_files

    # ------------------------------------------------------------------
    # Activity & callback wiring
    # ------------------------------------------------------------------

    def set_activity_callback(self, callback: Callable[[str, str], None]) -> None:
        """Wire the activity panel for live event logging."""
        self._activity_callback = callback

    def set_security_ui_callback(self, callback: Callable) -> None:
        """Wire a UI callback for security approval dialogs."""
        self._security_ui_callback = callback

    def set_terminal_approval_callback(self, callback: Callable) -> None:
        self.terminal.approval_callback = callback

    def _emit_activity(self, event: str, message: str) -> None:
        if self._activity_callback:
            try:
                self._activity_callback(event, message)
            except Exception:
                pass

    def _on_file_change(self, path: str, status: str) -> None:
        self.memory.add_edit(path, f"Diff {status}")
        self._emit_activity("file_change", f"{status}: {path}")

    def _security_approval(self, command: str, reason: str, risk) -> bool:
        """Default security approval — deny unless UI callback is set."""
        if self._security_ui_callback:
            return self._security_ui_callback(command, reason, risk)
        return False  # Safe default: deny dangerous ops without UI

    # ------------------------------------------------------------------
    # Performance — caching
    # ------------------------------------------------------------------

    def invalidate_context_cache(self) -> None:
        """Clear context engine file cache (call when files change)."""
        self.context_engine.invalidate_cache()
