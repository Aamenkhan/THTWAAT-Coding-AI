import sys, os
from pathlib import Path
from PySide6 import QtWidgets, QtCore

ROOT = Path('e:/AI_Project')
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

window.chat_input.setText('write a python calculator')
print('Input set')
window._submit_chat()

def check():
    out = window.chat_output.toPlainText()
    print('--- CHAT OUTPUT ---')
    print(out)
    print('-------------------')
    if 'Agent:' in out and len(out.split('Agent:')[1]) > 10:
        app.quit()
    elif '[Error:' in out:
        app.quit()
    elif hasattr(window, 'ai_worker') and not window.ai_worker.isRunning():
        app.quit()
    else:
        QtCore.QTimer.singleShot(1000, check)

QtCore.QTimer.singleShot(1000, check)
QtCore.QTimer.singleShot(15000, app.quit)
app.exec()

print('FINAL OUTPUT:')
print(window.chat_output.toPlainText())
