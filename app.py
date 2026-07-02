import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from ui.main_window import MainWindow


def main() -> None:
    os.makedirs(ROOT / "projects", exist_ok=True)
    os.makedirs(ROOT / "build", exist_ok=True)
    app = MainWindow()
    app.run()


if __name__ == "__main__":
    main()
