import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import List, Dict


class BuildManager:
    def __init__(self, project_root: str):
        self.project_root = Path(project_root).resolve()

    def build_exe(self) -> Dict[str, str]:
        spec_path = self.project_root / "build.spec"
        output_dir = self.project_root / "build"
        if not spec_path.exists():
            return {"status": "failed", "log": "build.spec not found"}
        output = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--clean", str(spec_path)],
            cwd=self.project_root,
            capture_output=True,
            text=True,
            timeout=1800,
        )
        log = (output.stdout or "") + (output.stderr or "")
        return {"status": "ok" if output.returncode == 0 else "failed", "log": log}

    def build_zip(self) -> Dict[str, str]:
        archive_path = self.project_root / "dist" / "workspace.zip"
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in self.project_root.rglob("*"):
                if path.is_file() and not any(part in {"build", "dist", ".git", "venv", "__pycache__"} for part in path.parts):
                    archive.write(path, arcname=path.relative_to(self.project_root))
        return {"status": "ok", "path": str(archive_path)}
