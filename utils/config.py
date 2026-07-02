import json
import os
from pathlib import Path
from typing import Dict, Any

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


def load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {"project_root": str(Path(__file__).resolve().parent.parent / "projects"), "model": "qwen2.5-coder:3b"}
    with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_config(config: Dict[str, Any]) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
