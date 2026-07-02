import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from editor.code_editor import CodeEditor
from PySide6.QtWidgets import QApplication


class CodeEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_editor_can_be_created_and_used(self):
        editor = CodeEditor()
        editor.set_text("print('hello')")
        self.assertEqual(editor.text().strip(), "print('hello')")


if __name__ == "__main__":
    unittest.main()
