import sys
import os
import threading
from pathlib import Path
from PySide6 import QtWidgets, QtCore

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from packaging.packager import bootstrap
config = bootstrap()
from ai.providers import build_router_from_config
from ui.main_window import MainWindow

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
router = build_router_from_config(config)

window = MainWindow()
window.config = config
window.provider_router = router

# Patch DiffViewerDialog to accept automatically and print diffs
import ui.main_window
original_DiffViewerDialog = ui.main_window.DiffViewerDialog
class MockDiffViewerDialog:
    def __init__(self, diff_engine, parent):
        self.diff_engine = diff_engine
        
    def exec(self):
        print("\n=== DIFF VIEWER DIALOG OPENED ===")
        print(f"Pending edits: {len(self.diff_engine.pending_edits())}")
        for edit in self.diff_engine.pending_edits():
            print(f"File: {edit.path}")
            print(f"Description: {edit.description}")
            print(f"Content length: {len(edit.proposed)}")
        print("=================================\n")
        self.diff_engine.accept_all()
        return 1

ui.main_window.DiffViewerDialog = MockDiffViewerDialog

def run_test():
    print("Running optimization end-to-end test...")
    # Create a real file to optimize
    test_file = ROOT / "test_opt.py"
    test_file.write_text("def add(a,b):\n  return a+b\n", encoding="utf-8")
    
    window._on_tree_item_double_clicked = lambda item, col: None # Mock
    window.current_path = str(test_file)
    window.central_editor.open_file(str(test_file))
    
    # Trigger optimize
    window.optimize()
    
    def check():
        out = window.chat_output.toPlainText()
        if 'Changes accepted' in out or 'Optimization cancelled' in out or 'Pipeline completed' in out or 'Pipeline failed' in out:
            print("--- CHAT OUTPUT ---")
            print(out.encode('utf-8'))
            print("-------------------")
            print("TEST FINISHED")
            app.quit()
        else:
            QtCore.QTimer.singleShot(2000, check)
            
    QtCore.QTimer.singleShot(2000, check)

QtCore.QTimer.singleShot(1000, run_test)
# Timeout after 240 seconds because Ollama can be slow
QtCore.QTimer.singleShot(240000, app.quit)
app.exec()
