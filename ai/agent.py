from pathlib import Path
from typing import Iterator, List, Optional

from ai.ollama_client import OllamaClient


class AIAgent:
    def __init__(self, model: str = "qwen2.5-coder:3b", base_url: Optional[str] = None):
        self.model = model
        self.client = OllamaClient(base_url=base_url)

    def chat_with_context(self, prompt: str, context: Optional[str] = None, project_index=None) -> str:
        combined_context = context
        if project_index and not combined_context:
            combined_context = project_index.build_context(prompt)
        return self.chat(prompt, context=combined_context)

    def _build_prompt(self, prompt: str, context: Optional[str] = None) -> str:
        if not context:
            return prompt
        return f"Context:\n{context}\n\nUser request:\n{prompt}"

    def chat(self, prompt: str, context: Optional[str] = None) -> str:
        return self.client.generate(self._build_prompt(prompt, context), model=self.model)

    def stream_chat(self, prompt: str, context: Optional[str] = None, stop_event=None) -> Iterator[str]:
        yield from self.client.generate_stream(self._build_prompt(prompt, context), model=self.model, stop_event=stop_event)

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

    def create_file(self, path: str, content: str) -> bool:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return True

    def edit_file(self, path: str, new_content: str) -> bool:
        target = Path(path)
        if not target.exists():
            raise FileNotFoundError(path)
        target.write_text(new_content, encoding="utf-8")
        return True

    def create_project(self, prompt: str, project_root: str) -> List[str]:
        created_files: List[str] = []
        base = Path(project_root)
        base.mkdir(parents=True, exist_ok=True)

        scaffold = f"""# Project scaffold from prompt\n\nPrompt: {prompt}\n\nThis project was created offline using the local AI IDE.\n"""
        readme = base / "README.md"
        readme.write_text(scaffold, encoding="utf-8")
        created_files.append(str(readme))

        main_py = base / "main.py"
        main_py.write_text(
            "print('Hello from the generated project')\n",
            encoding="utf-8",
        )
        created_files.append(str(main_py))

        requirements = base / "requirements.txt"
        requirements.write_text("requests>=2.9.0\n", encoding="utf-8")
        created_files.append(str(requirements))
        return created_files
