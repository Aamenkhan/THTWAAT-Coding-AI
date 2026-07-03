"""
ai/pipeline.py — Autonomous Execution Pipeline (Feature 18)

The complete, connected 10-stage pipeline:
  Analyze → Plan → Relevant Files → Create Diffs → Review →
  Run Tests → Fix Errors → Review Code → Commit (after approval) → Summary

Each stage is a distinct PipelineStage with typed input/output.
The pipeline supports:
  - Pause at user-approval gates (diff review, commit approval)
  - Progress callbacks at each stage transition
  - Error recovery: auto-retry + LLM fix suggestions
  - Stop/cancel at any point via stop_event
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ai.planner import Plan, PlanStep
from ai.diff_engine import DiffEngine, PendingEdit
from ai.tools import call_tool


# ---------------------------------------------------------------------------
# Stage definitions
# ---------------------------------------------------------------------------

class Stage(Enum):
    IDLE          = auto()
    ANALYZE       = auto()
    PLAN          = auto()
    RELEVANT_FILES = auto()
    CREATE_DIFFS  = auto()
    REVIEW        = auto()       # ← User approval gate
    RUN_TESTS     = auto()
    FIX_ERRORS    = auto()
    REVIEW_CODE   = auto()
    COMMIT        = auto()       # ← User approval gate
    SUMMARY       = auto()
    DONE          = auto()
    FAILED        = auto()
    CANCELLED     = auto()


_STAGE_ICONS = {
    Stage.IDLE:           "⏸",
    Stage.ANALYZE:        "🔍",
    Stage.PLAN:           "📋",
    Stage.RELEVANT_FILES: "📁",
    Stage.CREATE_DIFFS:   "✏️",
    Stage.REVIEW:         "👁️",
    Stage.RUN_TESTS:      "🧪",
    Stage.FIX_ERRORS:     "🔧",
    Stage.REVIEW_CODE:    "📝",
    Stage.COMMIT:         "💾",
    Stage.SUMMARY:        "📊",
    Stage.DONE:           "✅",
    Stage.FAILED:         "❌",
    Stage.CANCELLED:      "⏹",
}

_STAGE_LABELS = {
    Stage.IDLE:           "Idle",
    Stage.ANALYZE:        "Analyzing Project",
    Stage.PLAN:           "Building Plan",
    Stage.RELEVANT_FILES: "Finding Relevant Files",
    Stage.CREATE_DIFFS:   "Creating Diffs",
    Stage.REVIEW:         "Awaiting Diff Review",
    Stage.RUN_TESTS:      "Running Tests",
    Stage.FIX_ERRORS:     "Fixing Errors",
    Stage.REVIEW_CODE:    "Reviewing Code",
    Stage.COMMIT:         "Awaiting Commit Approval",
    Stage.SUMMARY:        "Generating Summary",
    Stage.DONE:           "Complete",
    Stage.FAILED:         "Failed",
    Stage.CANCELLED:      "Cancelled",
}

# Ordered pipeline (excluding terminal states)
_PIPELINE_ORDER = [
    Stage.ANALYZE,
    Stage.PLAN,
    Stage.RELEVANT_FILES,
    Stage.CREATE_DIFFS,
    Stage.REVIEW,
    Stage.RUN_TESTS,
    Stage.FIX_ERRORS,
    Stage.REVIEW_CODE,
    Stage.COMMIT,
    Stage.SUMMARY,
    Stage.DONE,
]

# Gates that pause execution until the user explicitly continues
_APPROVAL_GATES = {Stage.REVIEW, Stage.COMMIT}


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class StageResult:
    stage: Stage
    ok: bool
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0


@dataclass
class PipelineRun:
    goal: str
    run_id: str
    stage: Stage = Stage.IDLE
    stage_results: Dict[Stage, StageResult] = field(default_factory=dict)
    plan: Optional[Plan] = None
    relevant_files: List[str] = field(default_factory=list)
    pending_edits: List[PendingEdit] = field(default_factory=list)
    test_passed: bool = False
    test_output: str = ""
    fix_attempts: int = 0
    review_report: str = ""
    commit_message: str = ""
    commit_hash: str = ""
    summary: str = ""
    start_time: float = field(default_factory=time.time)

    @property
    def progress_percent(self) -> int:
        try:
            idx = _PIPELINE_ORDER.index(self.stage)
            return int(idx / len(_PIPELINE_ORDER) * 100)
        except ValueError:
            return 0

    @property
    def stage_icon(self) -> str:
        return _STAGE_ICONS.get(self.stage, "○")

    @property
    def stage_label(self) -> str:
        return _STAGE_LABELS.get(self.stage, self.stage.name)

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time


# ---------------------------------------------------------------------------
# Progress callback type
# ---------------------------------------------------------------------------
# (run, stage, message, data)
PipelineCallback = Callable[[PipelineRun, Stage, str, Dict[str, Any]], None]


# ---------------------------------------------------------------------------
# Approval gate callback
# ---------------------------------------------------------------------------
# (run, gate_stage) → True to continue, False to stop
ApprovalCallback = Callable[[PipelineRun, Stage], bool]


# ---------------------------------------------------------------------------
# Pipeline Engine
# ---------------------------------------------------------------------------

class Pipeline:
    """
    The autonomous coding pipeline.

    Usage:
        pipeline = Pipeline(agent)
        run = pipeline.start(goal, on_progress=my_callback, on_approval=my_approval_fn)

    The pipeline pauses at REVIEW and COMMIT gates, calling on_approval.
    on_approval must return True to continue, False to cancel.
    If on_approval is None, gates auto-proceed.
    """

    MAX_FIX_ATTEMPTS = 3

    def __init__(self, agent: Any):
        """
        Parameters
        ----------
        agent : AIAgent instance (imported lazily to avoid circular imports)
        """
        self.agent = agent
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def start(
        self,
        goal: str,
        on_progress: Optional[PipelineCallback] = None,
        on_approval: Optional[ApprovalCallback] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> PipelineRun:
        """
        Execute the full pipeline synchronously.
        Call this from a background thread.
        """
        import uuid
        run = PipelineRun(goal=goal, run_id=str(uuid.uuid4())[:8])
        stop_event = stop_event or threading.Event()

        def emit(stage: Stage, msg: str, data: Optional[Dict] = None) -> None:
            run.stage = stage
            if on_progress:
                try:
                    on_progress(run, stage, msg, data or {})
                except Exception:
                    pass

        def check_stop() -> bool:
            return stop_event.is_set()

        try:
            # ── Stage 1: ANALYZE ──────────────────────────────────────
            emit(Stage.ANALYZE, "Scanning project structure and detecting language...")
            t0 = time.time()
            lang_profile = self.agent.language.detect_project(self.agent.project_dir)
            project_files = self._list_project_files()
            run.stage_results[Stage.ANALYZE] = StageResult(
                stage=Stage.ANALYZE, ok=True,
                message=f"Detected {lang_profile.name if lang_profile else 'unknown'} project — {len(project_files)} files",
                data={"language": lang_profile.name if lang_profile else "unknown", "file_count": len(project_files)},
                duration_ms=int((time.time() - t0) * 1000),
            )
            if check_stop(): return self._cancel(run, emit)

            # ── Stage 2: PLAN ─────────────────────────────────────────
            emit(Stage.PLAN, "Building step-by-step execution plan...")
            t0 = time.time()
            lang_prefix = (
                self.agent.language.build_system_prompt(lang_profile) if lang_profile
                else "Write production-quality, fully implemented code. Follow SOLID principles.\n"
            )
            try:
                self.agent.planner.project_dir = self.agent.project_dir
                if hasattr(self.agent.planner, "_system_prefix"):
                    self.agent.planner._system_prefix = lang_prefix
                plan = self.agent.planner.build_plan(goal)
                run.plan = plan
                run.stage_results[Stage.PLAN] = StageResult(
                    stage=Stage.PLAN, ok=True,
                    message=f"Plan ready — {len(plan.steps)} steps",
                    data={"steps": len(plan.steps), "goal": plan.goal},
                    duration_ms=int((time.time() - t0) * 1000),
                )
                emit(Stage.PLAN, f"✅ Plan ready — {len(plan.steps)} steps",
                     {"plan": self._plan_to_dict(plan)})
            except Exception as exc:
                run.stage_results[Stage.PLAN] = StageResult(
                    stage=Stage.PLAN, ok=False, message=f"Plan failed: {exc}"
                )
                return self._fail(run, emit, f"Planning failed: {exc}")
            if check_stop(): return self._cancel(run, emit)

            # ── Stage 3: RELEVANT FILES ───────────────────────────────
            emit(Stage.RELEVANT_FILES, "Selecting relevant files for context...")
            t0 = time.time()
            relevant = self.agent.context_engine.get_relevant_files(goal, top_n=8)
            run.relevant_files = relevant
            run.stage_results[Stage.RELEVANT_FILES] = StageResult(
                stage=Stage.RELEVANT_FILES, ok=True,
                message=f"Selected {len(relevant)} relevant file(s)",
                data={"files": [Path(f).name for f in relevant]},
                duration_ms=int((time.time() - t0) * 1000),
            )
            if check_stop(): return self._cancel(run, emit)

            # ── Stage 4: CREATE DIFFS ─────────────────────────────────
            emit(Stage.CREATE_DIFFS, "Executing plan steps and staging file changes...")
            t0 = time.time()

            def on_plan_progress(event: str, message: str, data: Optional[Dict] = None):
                emit(Stage.CREATE_DIFFS, message, data)

            self.agent.planner.run(
                goal,
                on_progress=on_plan_progress,
                stop_event=stop_event,
            )
            pending = self.agent.diff_engine.pending_edits()
            run.pending_edits = list(pending)
            run.stage_results[Stage.CREATE_DIFFS] = StageResult(
                stage=Stage.CREATE_DIFFS, ok=True,
                message=f"{len(pending)} file change(s) staged",
                data={"pending": [e.path for e in pending]},
                duration_ms=int((time.time() - t0) * 1000),
            )
            if check_stop(): return self._cancel(run, emit)

            # ── Stage 5: REVIEW (approval gate) ──────────────────────
            emit(Stage.REVIEW, f"⏸ {len(pending)} change(s) ready for review. Awaiting approval...",
                 {"pending_edits": [e.path for e in pending]})

            if on_approval:
                allowed = on_approval(run, Stage.REVIEW)
                if not allowed:
                    return self._cancel(run, emit)

            # After user reviews: apply accepted edits
            accepted = self.agent.diff_engine.accept_all()
            run.stage_results[Stage.REVIEW] = StageResult(
                stage=Stage.REVIEW, ok=True,
                message=f"Review done — {len(accepted)} file(s) accepted",
                data={"accepted": accepted},
            )
            if check_stop(): return self._cancel(run, emit)

            # ── Stage 6: RUN TESTS ────────────────────────────────────
            emit(Stage.RUN_TESTS, "Running test suite...")
            t0 = time.time()
            test_result = self.agent.error_recovery.safe_call(
                "RunTests", {"directory": self.agent.project_dir}
            )
            passed = test_result.data.get("passed", 0)
            failed = test_result.data.get("failed", 0)
            run.test_passed = test_result.ok and failed == 0
            run.test_output = test_result.data.get("output", "")
            run.stage_results[Stage.RUN_TESTS] = StageResult(
                stage=Stage.RUN_TESTS, ok=run.test_passed,
                message=f"Tests: {passed} passed, {failed} failed",
                data={"passed": passed, "failed": failed},
                duration_ms=int((time.time() - t0) * 1000),
            )
            if check_stop(): return self._cancel(run, emit)

            # ── Stage 7: FIX ERRORS ───────────────────────────────────
            if not run.test_passed and failed > 0:
                emit(Stage.FIX_ERRORS, f"Fixing {failed} test failure(s)...")
                t0 = time.time()
                fix_ok = self._fix_errors(run, stop_event)
                run.stage_results[Stage.FIX_ERRORS] = StageResult(
                    stage=Stage.FIX_ERRORS, ok=fix_ok,
                    message=f"Fix {'successful' if fix_ok else 'exhausted'} after {run.fix_attempts} attempt(s)",
                    duration_ms=int((time.time() - t0) * 1000),
                )
            else:
                emit(Stage.FIX_ERRORS, "✅ No errors to fix")
                run.stage_results[Stage.FIX_ERRORS] = StageResult(
                    stage=Stage.FIX_ERRORS, ok=True, message="No errors"
                )
            if check_stop(): return self._cancel(run, emit)

            # ── Stage 8: REVIEW CODE ──────────────────────────────────
            accepted_files = run.stage_results.get(Stage.REVIEW, StageResult(Stage.REVIEW, False, "")).data.get("accepted", [])
            if accepted_files:
                emit(Stage.REVIEW_CODE, f"Reviewing {len(accepted_files)} file(s) for bugs & security...")
                t0 = time.time()
                try:
                    results = self.agent.reviewer.review_files(accepted_files)
                    report = self.agent.reviewer.generate_report(results)
                    run.review_report = report
                    total_issues = sum(r.total_issues for r in results)
                    run.stage_results[Stage.REVIEW_CODE] = StageResult(
                        stage=Stage.REVIEW_CODE, ok=True,
                        message=f"Code review complete — {total_issues} issue(s) found",
                        data={"issues": total_issues, "report": report[:500]},
                        duration_ms=int((time.time() - t0) * 1000),
                    )
                except Exception as exc:
                    run.stage_results[Stage.REVIEW_CODE] = StageResult(
                        stage=Stage.REVIEW_CODE, ok=False, message=f"Review error: {exc}"
                    )
            else:
                emit(Stage.REVIEW_CODE, "No files to review")
                run.stage_results[Stage.REVIEW_CODE] = StageResult(
                    stage=Stage.REVIEW_CODE, ok=True, message="Skipped — no accepted files"
                )
            if check_stop(): return self._cancel(run, emit)

            # ── Stage 9: COMMIT (approval gate) ──────────────────────
            emit(Stage.COMMIT, "⏸ Generating commit message. Awaiting commit approval...")
            try:
                run.commit_message = self.agent.git.generate_commit_message()
            except Exception:
                run.commit_message = f"feat: {goal[:60]}"

            emit(Stage.COMMIT, f"Proposed message: '{run.commit_message}'",
                 {"commit_message": run.commit_message})

            if on_approval:
                allowed = on_approval(run, Stage.COMMIT)
                if allowed:
                    try:
                        run.commit_hash = self.agent.git.commit(run.commit_message)
                        run.stage_results[Stage.COMMIT] = StageResult(
                            stage=Stage.COMMIT, ok=True,
                            message=f"Committed: {run.commit_message}",
                            data={"hash": run.commit_hash, "message": run.commit_message},
                        )
                    except Exception as exc:
                        run.stage_results[Stage.COMMIT] = StageResult(
                            stage=Stage.COMMIT, ok=False, message=f"Commit failed: {exc}"
                        )
                else:
                    run.stage_results[Stage.COMMIT] = StageResult(
                        stage=Stage.COMMIT, ok=True, message="Commit skipped by user"
                    )
            else:
                run.stage_results[Stage.COMMIT] = StageResult(
                    stage=Stage.COMMIT, ok=True, message="Commit gate skipped (no approval fn)"
                )

            # ── Stage 10: SUMMARY ─────────────────────────────────────
            emit(Stage.SUMMARY, "Generating final summary...")
            run.summary = self._build_summary(run)
            run.stage_results[Stage.SUMMARY] = StageResult(
                stage=Stage.SUMMARY, ok=True,
                message="Summary ready",
                data={"summary": run.summary},
            )
            emit(Stage.DONE, run.summary, {"summary": run.summary, "run": run})
            self.agent.memory.complete_task("done")

        except Exception as exc:
            run = self._fail(run, emit, str(exc))

        return run

    # ------------------------------------------------------------------
    # Stage helpers
    # ------------------------------------------------------------------

    def _fix_errors(
        self, run: PipelineRun, stop_event: threading.Event
    ) -> bool:
        """Ask the LLM to fix test failures, up to MAX_FIX_ATTEMPTS times."""
        for attempt in range(1, self.MAX_FIX_ATTEMPTS + 1):
            if stop_event.is_set():
                return False
            run.fix_attempts = attempt

            # Gather failed test info
            error_context = run.test_output[-2000:] if run.test_output else "Test failures"
            relevant = self.agent.context_engine.build_context(
                f"fix test failures: {error_context}", budget=2000
            )
            fix_prompt = (
                f"The following tests are failing:\n\n{error_context}\n\n"
                f"Relevant code:\n{relevant}\n\n"
                "Fix the failing tests. Return the fixed code for each file that needs changes. "
                "Be specific and implement complete fixes — no placeholders."
            )
            try:
                fix_response = self.agent.client.generate(fix_prompt, model=self.agent.model)
                # Parse file blocks and stage diffs
                self._apply_fix_response(fix_response, run)
                # Re-accept all and re-run tests
                self.agent.diff_engine.accept_all()
                test_result = self.agent.error_recovery.safe_call(
                    "RunTests", {"directory": self.agent.project_dir}
                )
                failed = test_result.data.get("failed", 0)
                run.test_output = test_result.data.get("output", "")
                if failed == 0:
                    run.test_passed = True
                    return True
            except Exception:
                pass
        return False

    def _apply_fix_response(self, response: str, run: PipelineRun) -> None:
        """Extract code blocks from LLM response and stage them as diffs."""
        import re
        # Match ```path\ncontent``` or # filename\n```content``` patterns
        pattern = re.compile(
            r"(?:#+\s*)?(?P<fname>[\w./\\-]+\.\w+)\s*\n```[^\n]*\n(?P<code>.*?)```",
            re.S,
        )
        for match in pattern.finditer(response):
            fname = match.group("fname").strip()
            code = match.group("code")
            candidate = Path(self.agent.project_dir) / fname
            if candidate.exists():
                self.agent.diff_engine.propose_edit(str(candidate), code, f"Fix: {fname}")

    def _build_summary(self, run: PipelineRun) -> str:
        lines = [
            f"# 📊 Pipeline Summary",
            f"**Goal**: {run.goal}",
            f"**Duration**: {run.elapsed:.1f}s",
            "",
            "## Stage Results",
        ]
        for stage in _PIPELINE_ORDER[:-1]:  # Exclude DONE
            result = run.stage_results.get(stage)
            if result:
                icon = "✅" if result.ok else "⚠️"
                lines.append(f"- {icon} **{_STAGE_LABELS[stage]}**: {result.message} ({result.duration_ms}ms)")

        if run.plan:
            done_steps = sum(1 for s in run.plan.steps if s.status == "done")
            lines += ["", f"**Steps completed**: {done_steps}/{len(run.plan.steps)}"]
        if run.pending_edits:
            lines.append(f"**Files changed**: {len(run.pending_edits)}")
        if run.commit_hash:
            lines.append(f"**Committed**: `{run.commit_hash}`")
        if run.review_report:
            lines += ["", "## Code Review", run.review_report[:600]]
        return "\n".join(lines)

    def _list_project_files(self) -> List[str]:
        skip = {"__pycache__", ".git", ".venv", "venv", "node_modules"}
        root = Path(self.agent.project_dir)
        return [
            str(p) for p in root.rglob("*")
            if p.is_file() and not any(s in p.parts for s in skip)
        ]

    @staticmethod
    def _plan_to_dict(plan: Plan) -> Dict[str, Any]:
        return {
            "goal": plan.goal,
            "steps": [
                {"step": s.index, "name": s.name, "tool": s.tool, "status": s.status}
                for s in plan.steps
            ],
        }

    @staticmethod
    def _cancel(run: PipelineRun, emit: Callable) -> PipelineRun:
        run.stage = Stage.CANCELLED
        emit(Stage.CANCELLED, "Pipeline cancelled by user.")
        return run

    @staticmethod
    def _fail(run: PipelineRun, emit: Callable, reason: str) -> PipelineRun:
        run.stage = Stage.FAILED
        emit(Stage.FAILED, f"Pipeline failed: {reason}")
        return run
