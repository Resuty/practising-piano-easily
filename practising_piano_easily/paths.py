"""Writable user data stays outside a frozen application's bundled resources."""

import os
import sys
from pathlib import Path


def data_directory() -> Path:
    if getattr(sys, "frozen", False):
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        current = base / "practising-piano-easily"
        legacy = base / "MusicTrainingLab"
        # Reuse an existing installation's data without moving or copying its database.
        if not current.exists() and (legacy / "music_training_lab.db").is_file():
            return legacy
        return current
    return Path(__file__).resolve().parent.parent / "data"


def database_path() -> Path:
    directory = data_directory()
    current = directory / "practice.db"
    legacy = directory / "music_training_lab.db"
    return legacy if not current.exists() and legacy.is_file() else current
