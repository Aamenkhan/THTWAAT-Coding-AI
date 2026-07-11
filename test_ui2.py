import sys
import os
from pathlib import Path
from PySide6 import QtWidgets, QtCore

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from packager.packager import bootstrap
config = bootstrap()
from ai.providers import build_router_from_config
from ui.main_window import MainWindow

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
router = build_router_from_config(config)

window = MainWindow()
window.config = config
window.provider_router = router

def run_test():
    print("Running test...")
    window.chat_input.setText('write a python calculator')
    window._submit_chat()
    
    def check():
        out = window.chat_output.toPlainText()
        print('--- CHAT OUTPUT ---')
        print(out.encode('utf-8'))
        print('-------------------')
        if 'Agent:' in out and len(out.split('Agent:')[1]) > 10:
            print("SUCCESS")
            app.quit()
        elif '[Error:' in out:
            print("ERROR IN UI")
            app.quit()
        elif hasattr(window, 'ai_worker') and not window.ai_worker.isRunning():
            print("WORKER STOPPED BUT NO OUTPUT")
            app.quit()
        else:
            QtCore.QTimer.singleShot(2000, check)
    
    QtCore.QTimer.singleShot(2000, check)

QtCore.QTimer.singleShot(1000, run_test)
QtCore.QTimer.singleShot(15000, app.quit)
app.exec()
