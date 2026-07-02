import tempfile
import unittest
import zipfile
from pathlib import Path

from ai.project_index import ProjectIndex
from utils.build_tools import BuildManager
from utils.diagnostics import run_diagnostics


class V03FeatureTests(unittest.TestCase):
    def test_project_index_supports_symbols_outline_and_rename(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            src = root / "src"
            src.mkdir()
            file_path = src / "main.py"
            file_path.write_text(
                "def greet(name):\n    return f'Hello {name}'\n\nprint(greet('world'))\n",
                encoding="utf-8",
            )
            index = ProjectIndex(str(root))
            outline = index.get_outline(str(file_path))
            self.assertTrue(any(item["name"] == "greet" for item in outline))
            definitions = index.find_definition("greet")
            self.assertTrue(any(item["path"].endswith("main.py") for item in definitions))
            references = index.find_references("greet")
            self.assertTrue(any(item["path"].endswith("main.py") for item in references))
            updated = index.rename_symbol(str(file_path), "greet", "welcome")
            self.assertTrue(updated)

    def test_diagnostics_report_syntax_errors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "broken.py"
            path.write_text("def broken(:\n    pass\n", encoding="utf-8")
            problems = run_diagnostics(str(path))
            self.assertTrue(problems)

    def test_build_zip_package_creates_archive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "demo.txt").write_text("demo", encoding="utf-8")
            archive_path = root / "bundle.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.write(root / "demo.txt", arcname="demo.txt")
            self.assertTrue(archive_path.exists())

    def test_build_exe_returns_status(self):
        manager = BuildManager(str(Path(__file__).resolve().parents[1]))
        result = manager.build_exe()
        self.assertIn(result["status"], {"ok", "failed"})
        self.assertIn("log", result)


if __name__ == "__main__":
    unittest.main()
