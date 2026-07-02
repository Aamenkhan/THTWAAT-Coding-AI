import json
import os
from typing import Iterator, Optional

import requests


class OllamaClient:
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    def _post(self, prompt: str, model: str, stream: bool):
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": stream},
                timeout=60,
                stream=stream,
            )
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError("Ollama is not running. Start the Ollama service locally and ensure the model is available.") from exc
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"Ollama request failed: {exc}") from exc

        if response.status_code != 200:
            raise RuntimeError(f"Ollama returned status {response.status_code}: {response.text}")
        return response

    def generate(self, prompt: str, model: str = "qwen2.5-coder:3b") -> str:
        response = self._post(prompt, model, stream=False)
        try:
            data = response.json()
        finally:
            response.close()
        return data.get("response", "")

    def generate_stream(self, prompt: str, model: str = "qwen2.5-coder:3b", stop_event=None) -> Iterator[str]:
        response = self._post(prompt, model, stream=True)
        try:
            for line in response.iter_lines(decode_unicode=True):
                if stop_event and stop_event.is_set():
                    break
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                chunk = payload.get("response", "")
                if chunk:
                    yield chunk
        finally:
            response.close()
