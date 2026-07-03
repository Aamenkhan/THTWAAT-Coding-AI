"""
app.py — Application entry point
QApplication MUST be created before any QWidget.
Bootstraps: crash reporter, config migration, provider router.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Bootstrap: crash reporter + config migration BEFORE any imports that may fail
from packaging.packager import bootstrap, ConfigManager
config = bootstrap()

from PySide6 import QtWidgets

from ui.main_window import MainWindow


def main() -> None:
    os.makedirs(ROOT / "projects", exist_ok=True)
    os.makedirs(ROOT / "build", exist_ok=True)
    os.makedirs(ROOT / "crash_reports", exist_ok=True)

    # QApplication MUST come before any QWidget / QMainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setApplicationName("THTWAAT Coding AI")
    app.setOrganizationName("THTWAAT")
    app.setApplicationVersion(config.get("version", "0.1.0"))

    from ui.theme import VS_CODE_DARK_THEME
    app.setStyleSheet(VS_CODE_DARK_THEME)

    # Build provider router from config
    from ai.providers import build_router_from_config
    router = build_router_from_config(config)

    window = MainWindow()
    window.config = config
    window.provider_router = router
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
