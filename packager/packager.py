"""
packaging/packager.py — Packaging & Distribution (Priority 6)
Windows installer, auto-updater, crash reporter, settings migration, config backup.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


ROOT = Path(__file__).resolve().parent.parent
_VERSION_FILE = ROOT / "version.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_version() -> Dict[str, Any]:
    if _VERSION_FILE.exists():
        return json.loads(_VERSION_FILE.read_text(encoding="utf-8"))
    return {"version": "0.1.0", "channel": "stable"}


def _write_version(data: Dict[str, Any]) -> None:
    _VERSION_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Config Backup & Settings Migration
# ---------------------------------------------------------------------------

class ConfigManager:
    """Settings migration and config backup."""

    SCHEMA_VERSION = 2

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = Path(config_path or ROOT / "config.json")

    def load(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            return self._defaults()
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            return self._migrate(data)
        except Exception:
            return self._defaults()

    def save(self, config: Dict[str, Any]) -> None:
        config["schema_version"] = self.SCHEMA_VERSION
        config["saved_at"] = datetime.utcnow().isoformat() + "Z"
        self.config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    def backup(self) -> Optional[Path]:
        """Create a timestamped backup of the current config."""
        if not self.config_path.exists():
            return None
        backup_dir = self.config_path.parent / "config_backups"
        backup_dir.mkdir(exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        dest = backup_dir / f"config_{ts}.json"
        shutil.copy2(self.config_path, dest)
        # Keep only last 10 backups
        backups = sorted(backup_dir.glob("config_*.json"))
        for old in backups[:-10]:
            old.unlink(missing_ok=True)
        return dest

    def _migrate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        schema = data.get("schema_version", 1)
        if schema < 2:
            # v1 → v2: rename 'model_name' to 'model'
            if "model_name" in data and "model" not in data:
                data["model"] = data.pop("model_name")
            data["schema_version"] = 2
        return {**self._defaults(), **data}

    @staticmethod
    def _defaults() -> Dict[str, Any]:
        return {
            "schema_version": ConfigManager.SCHEMA_VERSION,
            "model": "qwen2.5-coder:3b",
            "theme": "dark",
            "font_size": 13,
            "primary_provider": "ollama",
            "providers": {
                "ollama": {"base_url": "http://localhost:11434"}
            },
            "auto_save": True,
            "show_activity_panel": True,
            "show_pipeline_panel": True,
        }


# ---------------------------------------------------------------------------
# Crash Reporter
# ---------------------------------------------------------------------------

class CrashReporter:
    """Captures uncaught exceptions and writes structured crash reports."""

    def __init__(self, crash_dir: Optional[str] = None):
        self.crash_dir = Path(crash_dir or ROOT / "crash_reports")
        self.crash_dir.mkdir(exist_ok=True)

    def install(self) -> None:
        """Install as global exception hook."""
        sys.excepthook = self._handle_exception

    def _handle_exception(self, exc_type, exc_value, exc_tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        report = self._build_report(exc_type, exc_value, exc_tb)
        path = self._save_report(report)
        print(f"\n[CRASH] Report saved to: {path}", file=sys.stderr)
        print(f"[CRASH] {exc_type.__name__}: {exc_value}", file=sys.stderr)

    def _build_report(self, exc_type, exc_value, exc_tb) -> Dict[str, Any]:
        version = _read_version()
        return {
            "timestamp":   datetime.utcnow().isoformat() + "Z",
            "version":     version.get("version", "unknown"),
            "platform":    platform.platform(),
            "python":      sys.version,
            "exc_type":    exc_type.__name__,
            "exc_message": str(exc_value),
            "traceback":   traceback.format_exception(exc_type, exc_value, exc_tb),
            "argv":        sys.argv,
        }

    def _save_report(self, report: Dict[str, Any]) -> Path:
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        path = self.crash_dir / f"crash_{ts}.json"
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return path

    def list_reports(self) -> list:
        return sorted(self.crash_dir.glob("crash_*.json"), reverse=True)


# ---------------------------------------------------------------------------
# Auto Updater
# ---------------------------------------------------------------------------

class AutoUpdater:
    """
    Checks for new versions and downloads update packages.
    Uses a simple JSON manifest at update_url.
    Manifest format: {"version": "1.2.3", "download_url": "...", "changelog": "..."}
    """

    def __init__(self, update_url: str = "", install_dir: Optional[str] = None):
        self.update_url = update_url
        self.install_dir = Path(install_dir or ROOT)
        self._current = _read_version().get("version", "0.1.0")

    @property
    def current_version(self) -> str:
        return self._current

    def check_for_update(self) -> Optional[Dict[str, Any]]:
        """
        Returns update info dict if a newer version is available, else None.
        Returns None immediately if update_url is not configured.
        """
        if not self.update_url:
            return None
        try:
            import urllib.request
            with urllib.request.urlopen(self.update_url, timeout=5) as r:
                manifest = json.loads(r.read())
            if self._is_newer(manifest.get("version", "0.0.0")):
                return manifest
        except Exception:
            pass
        return None

    def download_and_install(self, manifest: Dict[str, Any]) -> bool:
        """Download the update package and install it."""
        url = manifest.get("download_url")
        if not url:
            return False
        try:
            import urllib.request
            update_path = self.install_dir / "update_package.zip"
            urllib.request.urlretrieve(url, str(update_path))
            shutil.unpack_archive(str(update_path), str(self.install_dir))
            _write_version({"version": manifest["version"], "channel": "stable"})
            update_path.unlink(missing_ok=True)
            return True
        except Exception:
            return False

    def _is_newer(self, remote: str) -> bool:
        def parse(v: str):
            return tuple(int(x) for x in v.split(".")[:3])
        try:
            return parse(remote) > parse(self._current)
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Windows Installer helper
# ---------------------------------------------------------------------------

def build_windows_installer() -> Optional[Path]:
    """
    Generate a NSIS installer script for the application.
    Requires NSIS to be installed. Returns path to the .nsi script.
    """
    version = _read_version().get("version", "0.1.0")
    nsi_content = f"""
; THTWAAT Coding AI — NSIS Installer Script
; Auto-generated by packaging/packager.py

!define APP_NAME "THTWAAT Coding AI"
!define APP_VERSION "{version}"
!define APP_EXE "THTWAAT_CodingAI.exe"

Name "${{APP_NAME}} ${{APP_VERSION}}"
OutFile "dist\\THTWAAT_CodingAI_Setup_{version}.exe"
InstallDir "$PROGRAMFILES64\\THTWAAT Coding AI"
RequestExecutionLevel admin

Section "Main Application"
    SetOutPath "$INSTDIR"
    File /r "dist\\app\\*.*"
    CreateShortCut "$DESKTOP\\${{APP_NAME}}.lnk" "$INSTDIR\\${{APP_EXE}}"
    CreateDirectory "$SMPROGRAMS\\${{APP_NAME}}"
    CreateShortCut "$SMPROGRAMS\\${{APP_NAME}}\\${{APP_NAME}}.lnk" "$INSTDIR\\${{APP_EXE}}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\THATWAATCodingAI" "DisplayName" "${{APP_NAME}}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\THATWAATCodingAI" "DisplayVersion" "${{APP_VERSION}}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\THATWAATCodingAI" "UninstallString" "$INSTDIR\\Uninstall.exe"
    WriteUninstaller "$INSTDIR\\Uninstall.exe"
SectionEnd

Section "Uninstall"
    Delete "$INSTDIR\\*.*"
    RMDir /r "$INSTDIR"
    Delete "$DESKTOP\\${{APP_NAME}}.lnk"
    RMDir /r "$SMPROGRAMS\\${{APP_NAME}}"
    DeleteRegKey HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\THATWAATCodingAI"
SectionEnd
""".strip()

    dist_dir = ROOT / "dist"
    dist_dir.mkdir(exist_ok=True)
    nsi_path = dist_dir / "installer.nsi"
    nsi_path.write_text(nsi_content, encoding="utf-8")
    return nsi_path


# ---------------------------------------------------------------------------
# Bootstrap — called from app.py before window creation
# ---------------------------------------------------------------------------

def bootstrap() -> Dict[str, Any]:
    """
    Run at startup:
    1. Install crash reporter
    2. Back up config
    3. Load and migrate config
    4. Check for updates (non-blocking)
    Returns the loaded config dict.
    """
    CrashReporter().install()
    cfg_manager = ConfigManager()
    cfg_manager.backup()
    config = cfg_manager.load()
    return config
