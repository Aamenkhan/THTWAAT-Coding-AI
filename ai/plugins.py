import importlib.util
import sys
from pathlib import Path
from typing import List, Optional


class BasePlugin:
    name = "base"
    description = "Base plugin"

    def process(self, text: str, app=None) -> str:
        return text


class PluginManager:
    def __init__(self, plugins_dir: str | None = None):
        self.plugins_dir = Path(plugins_dir or Path(__file__).resolve().parent.parent / "plugins").resolve()
        self.plugins: List[BasePlugin] = []
        self.enabled_names: set[str] = set()

    def load_plugins(self, enabled_names: Optional[List[str]] | None = None) -> List[BasePlugin]:
        self.plugins = []
        if enabled_names is not None:
            self.enabled_names = {name.lower() for name in enabled_names}
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
            spec.loader.exec_module(module)
            for _, obj in vars(module).items():
                if isinstance(obj, type) and issubclass(obj, BasePlugin) and obj is not BasePlugin:
                    plugin = obj()
                    if self.enabled_names and plugin.name.lower() not in self.enabled_names:
                        continue
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
