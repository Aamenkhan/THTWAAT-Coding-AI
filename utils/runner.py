import os
import subprocess
from pathlib import Path
from typing import Optional


def run_python_file(path: str) -> str:
    path_obj = Path(path)
    if not path_obj.exists():
        raise FileNotFoundError(path)
    result = subprocess.run(["python", str(path_obj)], capture_output=True, text=True, cwd=str(path_obj.parent))
    output = []
    if result.stdout:
        output.append(result.stdout)
    if result.stderr:
        output.append(result.stderr)
    return "".join(output)
