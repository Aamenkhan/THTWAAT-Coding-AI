"""
ai/providers.py — AI Provider Router (Priority 4)
Abstraction layer so the agent NEVER calls any API directly.
Supports: Ollama, Claude, OpenAI, Gemini, LMStudio.
"""

from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional


# ---------------------------------------------------------------------------
# Base provider interface
# ---------------------------------------------------------------------------

class AIProvider(abc.ABC):
    """
    Abstract base for all AI providers.
    The agent only depends on this interface — never on any concrete provider.
    """

    name: str = "base"

    @abc.abstractmethod
    def generate(
        self,
        prompt: str,
        model: str,
        system: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        """Generate a complete response from the model."""

    @abc.abstractmethod
    def generate_stream(
        self,
        prompt: str,
        model: str,
        system: Optional[str] = None,
        stop_event: Optional[Any] = None,
    ) -> Iterator[str]:
        """Stream tokens from the model."""

    @abc.abstractmethod
    def list_models(self) -> List[str]:
        """Return available model names for this provider."""

    @abc.abstractmethod
    def health_check(self) -> bool:
        """Return True if the provider is reachable."""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"


# ---------------------------------------------------------------------------
# Ollama Provider
# ---------------------------------------------------------------------------

class OllamaProvider(AIProvider):
    """Local Ollama inference server."""

    name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")
        # Import lazily to keep startup fast
        from ai.ollama_client import OllamaClient
        self._client = OllamaClient(base_url=base_url)

    def generate(self, prompt, model, system=None, temperature=0.2, max_tokens=4096) -> str:
        full = f"{system}\n\n{prompt}" if system else prompt
        return self._client.generate(full, model=model)

    def generate_stream(self, prompt, model, system=None, stop_event=None) -> Iterator[str]:
        full = f"{system}\n\n{prompt}" if system else prompt
        yield from self._client.generate_stream(full, model=model, stop_event=stop_event)

    def list_models(self) -> List[str]:
        try:
            import urllib.request, json
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=4) as r:
                data = json.loads(r.read())
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return ["qwen2.5-coder:3b", "llama3.2", "phi3"]

    def health_check(self) -> bool:
        try:
            import urllib.request
            urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=3)
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# OpenAI Provider
# ---------------------------------------------------------------------------

class OpenAIProvider(AIProvider):
    """OpenAI API (GPT-4o, GPT-4-turbo, etc.)"""

    name = "openai"

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self.base_url = base_url

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def generate(self, prompt, model, system=None, temperature=0.2, max_tokens=4096) -> str:
        import urllib.request, json
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body = json.dumps({
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body, headers=self._headers(), method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        return data["choices"][0]["message"]["content"]

    def generate_stream(self, prompt, model, system=None, stop_event=None) -> Iterator[str]:
        # Simplified: non-streaming fallback for OpenAI
        yield self.generate(prompt, model, system)

    def list_models(self) -> List[str]:
        return ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo", "gpt-4o-mini"]

    def health_check(self) -> bool:
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self.base_url}/models",
                headers=self._headers(),
            )
            urllib.request.urlopen(req, timeout=4)
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Claude (Anthropic) Provider
# ---------------------------------------------------------------------------

class ClaudeProvider(AIProvider):
    """Anthropic Claude API."""

    name = "claude"

    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com"):
        self.api_key = api_key
        self.base_url = base_url

    def _headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def generate(self, prompt, model, system=None, temperature=0.2, max_tokens=4096) -> str:
        import urllib.request, json
        body = json.dumps({
            "model": model,
            "max_tokens": max_tokens,
            **({"system": system} if system else {}),
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/v1/messages",
            data=body, headers=self._headers(), method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        return data["content"][0]["text"]

    def generate_stream(self, prompt, model, system=None, stop_event=None) -> Iterator[str]:
        yield self.generate(prompt, model, system)

    def list_models(self) -> List[str]:
        return ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"]

    def health_check(self) -> bool:
        return bool(self.api_key)


# ---------------------------------------------------------------------------
# Gemini Provider
# ---------------------------------------------------------------------------

class GeminiProvider(AIProvider):
    """Google Gemini API."""

    name = "gemini"

    def __init__(self, api_key: str, base_url: str = "https://generativelanguage.googleapis.com"):
        self.api_key = api_key
        self.base_url = base_url

    def generate(self, prompt, model, system=None, temperature=0.2, max_tokens=4096) -> str:
        import urllib.request, json
        full = f"{system}\n\n{prompt}" if system else prompt
        body = json.dumps({
            "contents": [{"parts": [{"text": full}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }).encode()
        url = f"{self.base_url}/v1beta/models/{model}:generateContent?key={self.api_key}"
        req = urllib.request.Request(url, data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        return data["candidates"][0]["content"]["parts"][0]["text"]

    def generate_stream(self, prompt, model, system=None, stop_event=None) -> Iterator[str]:
        yield self.generate(prompt, model, system)

    def list_models(self) -> List[str]:
        return ["gemini-flash-latest", "gemini-2.0-flash", "gemini-2.0-flash-lite"]

    def health_check(self) -> bool:
        return bool(self.api_key)


# ---------------------------------------------------------------------------
# LMStudio Provider (OpenAI-compatible local server)
# ---------------------------------------------------------------------------

class LMStudioProvider(AIProvider):
    """LM Studio local server (OpenAI-compatible API)."""

    name = "lmstudio"

    def __init__(self, base_url: str = "http://localhost:1234"):
        self.base_url = base_url.rstrip("/")
        # Reuse OpenAI provider since LMStudio uses the same API format
        self._openai = OpenAIProvider(api_key="lm-studio", base_url=f"{self.base_url}/v1")

    def generate(self, prompt, model, system=None, temperature=0.2, max_tokens=4096) -> str:
        return self._openai.generate(prompt, model, system, temperature, max_tokens)

    def generate_stream(self, prompt, model, system=None, stop_event=None) -> Iterator[str]:
        yield from self._openai.generate_stream(prompt, model, system, stop_event)

    def list_models(self) -> List[str]:
        try:
            import urllib.request, json
            req = urllib.request.Request(
                f"{self.base_url}/v1/models",
                headers={"Authorization": "Bearer lm-studio"},
            )
            with urllib.request.urlopen(req, timeout=4) as r:
                data = json.loads(r.read())
            return [m["id"] for m in data.get("data", [])]
        except Exception:
            return []

    def health_check(self) -> bool:
        try:
            import urllib.request
            urllib.request.urlopen(f"{self.base_url}/v1/models", timeout=3)
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Provider Router
# ---------------------------------------------------------------------------

@dataclass
class ProviderRouter:
    """
    Routes AI requests to the appropriate provider.
    The agent interacts ONLY with this router — never with providers directly.

    Supports:
    - Primary provider with automatic fallback chain
    - Health-check-based routing
    - Per-request provider override
    """

    _providers: Dict[str, AIProvider] = field(default_factory=dict)
    _primary: str = "ollama"
    _fallback_chain: List[str] = field(default_factory=list)

    def register(self, provider: AIProvider) -> "ProviderRouter":
        self._providers[provider.name] = provider
        return self

    def set_primary(self, name: str) -> "ProviderRouter":
        self._primary = name
        return self

    def set_fallback_chain(self, names: List[str]) -> "ProviderRouter":
        self._fallback_chain = names
        return self

    def generate(
        self,
        prompt: str,
        model: str,
        system: Optional[str] = None,
        provider_name: Optional[str] = None,
    ) -> str:
        provider = self._resolve(provider_name)
        return provider.generate(prompt, model, system=system)

    def generate_stream(
        self,
        prompt: str,
        model: str,
        system: Optional[str] = None,
        stop_event: Optional[Any] = None,
        provider_name: Optional[str] = None,
    ) -> Iterator[str]:
        provider = self._resolve(provider_name)
        yield from provider.generate_stream(prompt, model, system=system, stop_event=stop_event)

    def list_models(self, provider_name: Optional[str] = None) -> List[str]:
        provider = self._resolve(provider_name)
        return provider.list_models()

    def available_providers(self) -> List[str]:
        return list(self._providers.keys())

    def healthy_providers(self) -> List[str]:
        return [n for n, p in self._providers.items() if p.health_check()]

    def _resolve(self, name: Optional[str] = None) -> AIProvider:
        """Pick provider by name, or fall through primary → fallback chain."""
        candidates = [name, self._primary] + self._fallback_chain
        for candidate in candidates:
            if candidate and candidate in self._providers:
                p = self._providers[candidate]
                if p.health_check():
                    return p
        # Last resort: return primary even if unhealthy
        if self._primary in self._providers:
            return self._providers[self._primary]
        if self._providers:
            return next(iter(self._providers.values()))
        raise RuntimeError("No AI providers registered. Call router.register(provider).")


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------

def build_router_from_config(config: Dict[str, Any]) -> ProviderRouter:
    """
    Build a ProviderRouter from a config dict.

    Config format:
    {
        "primary_provider": "ollama",
        "providers": {
            "ollama":    {"base_url": "http://localhost:11434"},
            "openai":    {"api_key": "sk-..."},
            "claude":    {"api_key": "sk-ant-..."},
            "gemini":    {"api_key": "AIza..."},
            "lmstudio":  {"base_url": "http://localhost:1234"}
        }
    }
    """
    router = ProviderRouter()
    provider_configs = config.get("providers", {})

    _factories = {
        "ollama":   lambda c: OllamaProvider(base_url=c.get("base_url", "http://localhost:11434")),
        "openai":   lambda c: OpenAIProvider(api_key=c.get("api_key", ""), base_url=c.get("base_url", "https://api.openai.com/v1")),
        "claude":   lambda c: ClaudeProvider(api_key=c.get("api_key", "")),
        "gemini":   lambda c: GeminiProvider(api_key=c.get("api_key", "")),
        "lmstudio": lambda c: LMStudioProvider(base_url=c.get("base_url", "http://localhost:1234")),
    }

    for pname, pcfg in provider_configs.items():
        factory = _factories.get(pname)
        if factory:
            router.register(factory(pcfg))

    primary = config.get("primary_provider", "ollama")
    router.set_primary(primary)

    # Default fallback order
    all_providers = list(provider_configs.keys())
    router.set_fallback_chain([p for p in all_providers if p != primary])

    return router
