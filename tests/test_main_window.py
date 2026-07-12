import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


class MainWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_main_window_creates_with_expected_panels(self):
        window = MainWindow()
        self.assertIsNotNone(window.central_editor)
        self.assertIsNotNone(window.agent_panel)
        self.assertFalse(window.agent_panel.isHidden())
        self.assertFalse(window.bottom_tabs.isHidden())
        self.assertEqual([button.text() for button in window.toolbar_buttons], [
            "New File",
            "Open Folder",
            "Save",
            "Run",
            "AI Edit",
            "Explain",
            "Optimize",
            "Git",
            "⚙ Settings",
        ])
        window.close()


if __name__ == "__main__":
    unittest.main()
