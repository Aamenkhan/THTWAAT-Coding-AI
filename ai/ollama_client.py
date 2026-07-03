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
            err_msg = "Ollama is not running. Start the Ollama service locally and ensure the model is available."
            print(f"Ollama API Error: {err_msg}")
            raise RuntimeError(err_msg) from exc
        except requests.exceptions.RequestException as exc:
            err_msg = f"Ollama request failed: {exc}"
            print(f"Ollama API Error: {err_msg}")
            raise RuntimeError(err_msg) from exc

        if response.status_code != 200:
            err_msg = f"Ollama returned status {response.status_code}: {response.text}"
            print(f"Ollama API Error: {err_msg}")
            raise RuntimeError(err_msg)
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
                except json.JSONDecodeError as exc:
                    print(f"Failed to parse JSON line from Ollama: {line!r} - {exc}")
                    continue
                
                if "error" in payload:
                    raise RuntimeError(f"Ollama API error: {payload['error']}")
                    
                chunk = payload.get("response", "")
                if chunk:
                    yield chunk
        finally:
            response.close()
