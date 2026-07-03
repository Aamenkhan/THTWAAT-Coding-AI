"""
ai/planner.py — Planning Agent
Builds step-by-step execution plans, runs them with progress callbacks,
and routes file-modifying tools through the DiffEngine.
"""

import json
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ai.tools import call_tool, list_tools, ToolResult
from ai.diff_engine import DiffEngine


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PlanStep:
    index: int
    name: str
    tool: str
    args: Dict[str, Any]
    status: str = "pending"   # pending | running | done | failed | skipped
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class Plan:
    goal: str
    steps: List[PlanStep] = field(default_factory=list)
    status: str = "pending"   # pending | running | done | failed


# ---------------------------------------------------------------------------
# Progress callback type
# ---------------------------------------------------------------------------
ProgressCallback = Callable[[str, str, Optional[Dict[str, Any]]], None]
# signature: (event_type, message, data)
# event_types: "plan_ready" | "step_start" | "step_done" | "step_fail" | "complete" | "error"


# ---------------------------------------------------------------------------
# FILE-MODIFYING TOOLS — route through DiffEngine instead of writing directly
# ---------------------------------------------------------------------------
_WRITE_TOOLS = {"WriteFile", "CreateFile", "ReplaceText", "DeleteFile"}

_PLAN_SYSTEM_PROMPT = """You are an autonomous coding agent. When given a goal, produce a JSON execution plan.

RULES:
- Respond ONLY with valid JSON — no markdown, no explanation outside the JSON.
- The JSON must have keys "goal" (string) and "steps" (array).
- Each step must have: "step" (int), "name" (string), "tool" (string), "args" (object).
- Choose tools only from this list:
{tool_list}
- CRITICAL: To modify an existing file, you MUST use WriteFile with the COMPLETE new file content in the "content" field. NEVER use ReplaceText to modify existing files — it is unreliable. Only use WriteFile.
- The WriteFile args MUST have exactly two fields: "path" (the file path) and "content" (the full new file content as a string). No other field names are valid.
- Always ReadFile first to get the current content before writing.
- Keep plans concise: 2–5 steps.

EXAMPLE OUTPUT:
{{
  "goal": "Add a docstring to all functions in utils.py",
  "steps": [
    {{"step": 1, "name": "Read the file", "tool": "ReadFile", "args": {{"path": "utils.py"}}}},
    {{"step": 2, "name": "Write improved version", "tool": "WriteFile", "args": {{"path": "utils.py", "content": "def foo():\n    \"\"\"Does foo.\"\"\"\n    pass\n"}}}}
  ]
}}
"""

_PLAN_USER_TEMPLATE = "Goal: {goal}\n\nProject directory: {directory}"


class Planner:
    """
    Orchestrates goal → plan → execute → progress reporting.

    Usage:
        planner = Planner(ollama_client, diff_engine, project_dir)
        planner.run(goal, on_progress=my_callback, stop_event=evt)
    """

    def __init__(
        self,
        ollama_client,
        diff_engine: DiffEngine,
        project_dir: str = ".",
        model: str = "qwen2.5-coder:3b",
    ):
        self.client = ollama_client
        self.diff_engine = diff_engine
        self.project_dir = project_dir
        self.model = model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_plan(self, goal: str) -> Plan:
        """Ask the LLM to produce a JSON plan for *goal*."""
        tool_list = "\n".join(f"  - {t['name']}: {t['description']}" for t in list_tools())
        system = _PLAN_SYSTEM_PROMPT.format(tool_list=tool_list)
        user_msg = _PLAN_USER_TEMPLATE.format(goal=goal, directory=self.project_dir)
        full_prompt = f"{system}\n\n{user_msg}"

        # Attempt 1
        raw = self.client.generate(full_prompt, model=self.model, format="json")
        print(f"RAW JSON (format='json' Attempt 1):\n{raw}\n---", flush=True)
        try:
            return self._parse_plan(raw, goal)
        except (json.JSONDecodeError, ValueError) as exc:
            print(f"First JSON parsing attempt failed: {exc}\nRetrying...")
            # Attempt 2
            retry_prompt = f"{full_prompt}\n\nSYSTEM WARNING: Your previous output was invalid JSON. You must return ONLY valid JSON and nothing else."
            raw2 = self.client.generate(retry_prompt, model=self.model, format="json")
            print(f"RAW JSON (format='json' Attempt 2):\n{raw2}\n---", flush=True)
            try:
                return self._parse_plan(raw2, goal)
            except (json.JSONDecodeError, ValueError):
                raise RuntimeError("AI failed to generate a valid plan. Try again or switch to a different model.")

    def run(
        self,
        goal: str,
        on_progress: Optional[ProgressCallback] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> Plan:
        """
        Full autonomous loop:
          1. Build plan
          2. Emit plan_ready
          3. Execute each step
          4. Route writes through DiffEngine
          5. Emit progress events throughout
        """
        def emit(event: str, msg: str, data: Optional[Dict] = None):
            if on_progress:
                on_progress(event, msg, data)

        # --- Build plan ---
        try:
            plan = self.build_plan(goal)
        except Exception as exc:
            emit("error", f"Failed to build plan: {exc}")
            p = Plan(goal=goal, status="failed")
            return p

        plan.status = "running"
        emit("plan_ready", f"Plan ready ({len(plan.steps)} steps)", {"plan": self._plan_to_dict(plan)})

        # --- Execute steps ---
        for step in plan.steps:
            if stop_event and stop_event.is_set():
                step.status = "skipped"
                emit("step_fail", f"⏹ Step {step.index}: {step.name} — stopped", {"step": step.index})
                continue

            step.status = "running"
            emit("step_start", f"⏳ Step {step.index}: {step.name}...", {"step": step.index, "tool": step.tool})

            try:
                result = self._execute_step(step)
                step.result = result.to_dict()
                if result.ok:
                    step.status = "done"
                    emit("step_done", f"✅ Step {step.index}: {step.name}", {"step": step.index, "result": step.result})
                else:
                    step.status = "failed"
                    emit("step_fail", f"❌ Step {step.index}: {step.name} — {result.data.get('error', '')}", {"step": step.index})
            except Exception as exc:
                step.status = "failed"
                step.error = str(exc)
                emit("step_fail", f"❌ Step {step.index}: {step.name} — {exc}", {"step": step.index})

        plan.status = "done"
        pending = self.diff_engine.pending_edits()
        emit("complete", f"Plan complete. {len(pending)} file change(s) pending review.", {
            "pending_edits": [e.path for e in pending],
        })
        return plan

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _execute_step(self, step: PlanStep) -> ToolResult:
        """Execute a single plan step, routing writes through DiffEngine."""
        tool_name = step.tool
        args = dict(step.args)

        # Inject project directory as default for directory/path args
        if "directory" not in args and "path" not in args:
            args.setdefault("directory", self.project_dir)

        if tool_name in _WRITE_TOOLS:
            return self._route_write_tool(tool_name, args)

        return call_tool(tool_name, args)

    def _route_write_tool(self, tool_name: str, args: Dict[str, Any]) -> ToolResult:
        """
        Instead of writing directly, stage the change in DiffEngine.
        Returns a ToolResult indicating the diff was staged.
        """
        from ai.tools import ToolResult as TR

        path = args.get("path", "")
        if not path:
            return TR({"error": "No path provided"}, ok=False)

        if tool_name == "WriteFile":
            content = args.get("content", "")
            if not content or content.strip() in ("", "..."):
                return TR({"error": "WriteFile missing non-empty content"}, ok=False)
            edit = self.diff_engine.propose_edit(path, content, description=f"WriteFile: {path}")
        elif tool_name == "CreateFile":
            content = args.get("content", "")
            edit = self.diff_engine.propose_edit(path, content, description=f"CreateFile: {path}")
        elif tool_name == "ReplaceText":
            old_text = args.get("old_text") or args.get("search") or args.get("pattern") or ""
            new_text = args.get("new_text") or args.get("replace") or args.get("replacement") or ""
            if not old_text:
                return TR({"error": "ReplaceText missing old_text to replace"}, ok=False)
            
            edit = self.diff_engine.propose_replace(path, old_text, new_text, description=f"ReplaceText: {path}")
            if edit is None:
                return TR({"error": f"Text not found in {path}"}, ok=False)
        elif tool_name == "DeleteFile":
            edit = self.diff_engine.propose_edit(path, "", description=f"DeleteFile: {path}")
        else:
            return TR({"error": f"Unknown write tool: {tool_name}"}, ok=False)

        return TR({
            "path": edit.path,
            "status": "staged",
            "diff": edit.diff,
            "message": "Change staged for review — use Accept/Reject to apply.",
        })

    def _parse_plan(self, raw: str, goal: str) -> Plan:
        """Extract JSON from LLM response and build a Plan object."""
        # Try to find a JSON block in the response
        json_match = re.search(r"\{[\s\S]*\}", raw)
        if not json_match:
            raise ValueError(f"LLM did not return valid JSON plan.\nRaw: {raw[:400]}")
        data = json.loads(json_match.group(0))
        steps = []
        for raw_step in data.get("steps", []):
            steps.append(PlanStep(
                index=raw_step.get("step", len(steps) + 1),
                name=raw_step.get("name", "Unnamed step"),
                tool=raw_step.get("tool", ""),
                args=raw_step.get("args", {}),
            ))
        return Plan(goal=data.get("goal", goal), steps=steps)

    @staticmethod
    def _plan_to_dict(plan: Plan) -> Dict[str, Any]:
        return {
            "goal": plan.goal,
            "steps": [
                {"step": s.index, "name": s.name, "tool": s.tool, "status": s.status}
                for s in plan.steps
            ],
        }
