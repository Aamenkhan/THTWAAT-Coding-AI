"""
ai/plugins.py — Enhanced Plugin System (Feature 13)
Plugins can register: Tools, Commands, Prompts, Context providers.
"""

import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ai.tools import TOOL_REGISTRY


# ---------------------------------------------------------------------------
# Plugin Registry Singleton
# ---------------------------------------------------------------------------

class PluginRegistry:
    """Central registry that plugins write into during load."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools: Dict[str, Callable] = {}
            cls._instance._commands: Dict[str, Callable] = {}
            cls._instance._prompts: Dict[str, str] = {}
            cls._instance._context_providers: List[Callable] = []
        return cls._instance

    def register_tool(self, name: str, fn: Callable) -> None:
        """Register a tool into the global TOOL_REGISTRY."""
        self._tools[name] = fn
        TOOL_REGISTRY[name] = fn

    def register_command(self, name: str, fn: Callable) -> None:
        """Register a chat slash-command handler."""
        self._commands[name.lstrip("/")] = fn

    def register_prompt(self, name: str, template: str) -> None:
        """Register a named prompt template."""
        self._prompts[name] = template

    def register_context_provider(self, fn: Callable[..., str]) -> None:
        """Register a context provider function(query) -> str."""
        self._context_providers.append(fn)

    def get_command(self, name: str) -> Optional[Callable]:
        return self._commands.get(name.lstrip("/"))

    def get_prompt(self, name: str) -> Optional[str]:
        return self._prompts.get(name)

    def run_context_providers(self, query: str) -> str:
        """Collect context from all registered providers."""
        parts = []
        for provider in self._context_providers:
            try:
                result = provider(query)
                if result:
                    parts.append(str(result))
            except Exception:
                continue
        return "\n\n".join(parts)

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())

    def list_commands(self) -> List[str]:
        return list(self._commands.keys())

    def list_prompts(self) -> List[str]:
        return list(self._prompts.keys())

    def summary(self) -> str:
        return (
            f"Tools: {len(self._tools)} | "
            f"Commands: {len(self._commands)} | "
            f"Prompts: {len(self._prompts)} | "
            f"Context providers: {len(self._context_providers)}"
        )


# ---------------------------------------------------------------------------
# Base Plugin
# ---------------------------------------------------------------------------

class BasePlugin:
    name = "base"
    description = "Base plugin"
    version = "1.0.0"
    author = ""

    def on_load(self, registry: PluginRegistry) -> None:
        """Called when the plugin is loaded. Register tools/commands here."""

    def process(self, text: str, app=None) -> str:
        """Legacy text processor hook (called in chat pipeline)."""
        return text

    def register_tools(self, registry: PluginRegistry) -> None:
        """Override to register custom tools."""

    def register_commands(self, registry: PluginRegistry) -> None:
        """Override to register chat commands."""

    def register_prompts(self, registry: PluginRegistry) -> None:
        """Override to register prompt templates."""

    def register_context_provider(self, registry: PluginRegistry) -> None:
        """Override to register a context provider function."""


# ---------------------------------------------------------------------------
# Plugin Manager
# ---------------------------------------------------------------------------

class PluginManager:
    def __init__(self, plugins_dir: Optional[str] = None):
        self.plugins_dir = Path(
            plugins_dir or Path(__file__).resolve().parent.parent / "plugins"
        ).resolve()
        self.plugins: List[BasePlugin] = []
        self.enabled_names: set = set()
        self.registry = PluginRegistry()

    def load_plugins(self, enabled_names: Optional[List[str]] = None) -> List[BasePlugin]:
        self.plugins = []
        if enabled_names is not None:
            self.enabled_names = {n.lower() for n in enabled_names}
        if not self.plugins_dir.exists():
            return self.plugins

        for plugin_file in sorted(self.plugins_dir.glob("*.py")):
            if plugin_file.name.startswith("_"):
                continue
            spec = importlib.util.spec_from_file_location(plugin_file.stem, plugin_file)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[plugin_file.stem] = module
            try:
                spec.loader.exec_module(module)
            except Exception:
                continue

            for _, obj in vars(module).items():
                if isinstance(obj, type) and issubclass(obj, BasePlugin) and obj is not BasePlugin:
                    plugin = obj()
                    if self.enabled_names and plugin.name.lower() not in self.enabled_names:
                        continue
                    # Full registration lifecycle
                    plugin.register_tools(self.registry)
                    plugin.register_commands(self.registry)
                    plugin.register_prompts(self.registry)
                    plugin.register_context_provider(self.registry)
                    plugin.on_load(self.registry)
                    self.plugins.append(plugin)

        return self.plugins

    def run_plugins(self, text: str, app=None) -> str:
        result = text
        for plugin in self.plugins:
            try:
                processed = plugin.process(result, app=app)
                if processed is not None:
                    result = processed
            except Exception:
                continue
        return result

    def run_command(self, command: str, args: str = "", app=None) -> Optional[str]:
        """Execute a registered slash command. Returns output string or None."""
        handler = self.registry.get_command(command)
        if handler:
            try:
                return str(handler(args, app=app))
            except Exception as exc:
                return f"Command '/{command}' failed: {exc}"
        return None

    def get_context(self, query: str) -> str:
        """Aggregate context from all plugin context providers."""
        return self.registry.run_context_providers(query)

    def summary(self) -> str:
        return f"{len(self.plugins)} plugins loaded. {self.registry.summary()}"
