from typing import Dict, List

# ---------------------------------------------------------------------------
# Chat system prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are an offline AI coding assistant for a Windows desktop IDE.\n"
    "You help with coding, debugging, explaining code, creating files, and scaffolding projects.\n"
    "Always prefer concise, practical answers.\n"
)

# ---------------------------------------------------------------------------
# Planning prompts
# ---------------------------------------------------------------------------

PLANNING_SYSTEM_PROMPT = """\
You are an autonomous coding agent with access to a structured tool registry.
When given a goal, produce a JSON execution plan — nothing else.

JSON schema:
{
  "goal": "<restate the goal>",
  "steps": [
    {
      "step": <int>,
      "name": "<human-readable step name>",
      "tool": "<ToolName>",
      "args": { ... }
    }
  ]
}

Rules:
- Respond with ONLY valid JSON. No markdown code fences, no extra text.
- Use only tools from the provided list.
- For any write/create/delete, first read the file to understand current state.
- Keep plans 3-8 steps for simple goals, up to 15 for complex ones.
- All paths must be relative to the project directory unless absolute is needed.
"""

PLANNING_USER_TEMPLATE = (
    "Available tools:\n{tool_list}\n\n"
    "Project directory: {directory}\n\n"
    "Goal: {goal}"
)

# ---------------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------------

def build_context_prompt(files: List[str], user_request: str) -> str:
    file_list = "\n".join(files[:20])
    return (
        f"You are working with the following project files:\n{file_list}\n\n"
        f"User request:\n{user_request}\n"
    )


def build_tool_list_text(tools: List[Dict[str, str]]) -> str:
    """Format tool list for inclusion in planning prompts."""
    return "\n".join(f"  - {t['name']}: {t['description']}" for t in tools)
