import tempfile
import unittest
from pathlib import Path

from ai.git_integration import GitManager
from ai.project_index import ProjectIndex
from ai.plugins import PluginManager


class V02FeatureTests(unittest.TestCase):
    def test_git_manager_status_and_branch_switch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            manager = GitManager(str(repo))
            manager.init_repo()
            (repo / "README.md").write_text("hello\n", encoding="utf-8")
            manager.commit("initial")
            manager.create_branch("feature")
            status = manager.status()
            self.assertIn("On branch", status)
            self.assertIn("feature", status)

    def test_project_index_builds_context_for_query(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")
            index = ProjectIndex(str(root))
            context = index.build_context("hello function")
            self.assertIn("main.py", context)
            self.assertIn("hello", context)

    def test_plugin_manager_discovers_enabled_plugins(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            plugins_dir = Path(temp_dir) / "plugins"
            plugins_dir.mkdir()
            (plugins_dir / "demo_plugin.py").write_text(
                "from ai.plugins import BasePlugin\n"
                "class DemoPlugin(BasePlugin):\n"
                "    name = 'demo'\n"
                "    description = 'demo'\n"
                "    def process(self, text, app=None):\n"
                "        return 'handled'\n",
                encoding="utf-8",
            )
            manager = PluginManager(str(plugins_dir))
            plugins = manager.load_plugins()
            self.assertEqual(len(plugins), 1)
            self.assertEqual(plugins[0].name, "demo")


if __name__ == "__main__":
    unittest.main()
