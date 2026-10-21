"""Local build checks; outputs and temporary user profiles stay under exports/."""

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / "exports" / "packaging-checks"
EXE = ROOT / "exports" / "portfolio" / "practising-piano-easily" / "practising-piano-easily.exe"


def frozen_checks():
    profile = Path(tempfile.mkdtemp(prefix="fresh-frozen-profile-", dir=CHECKS))
    env = {key.upper(): value for key, value in os.environ.items()}
    env["LOCALAPPDATA"] = str(profile)
    system_root = env.get("SYSTEMROOT", "C:\\Windows")
    env["PATH"] = str(Path(system_root) / "System32") + os.pathsep + system_root
    for name in ("PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM"):
        env.pop(name, None)
    result = profile / "midi-scan.json"
    scan = subprocess.run([str(EXE), "--midi-scan", str(result)], cwd=profile, env=env, timeout=15)
    devices = json.loads(result.read_text(encoding="utf-8"))
    assert scan.returncode == 0 and isinstance(devices, list), devices
    assert not (profile / "practising-piano-easily").exists(), "MIDI helper must not create a GUI/profile"
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    process = subprocess.Popen([str(EXE)], cwd=profile, env=env, startupinfo=startup)
    database_path = profile / "practising-piano-easily" / "practice.db"
    try:
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            assert process.poll() is None, f"EXE exited: {process.returncode}"
            time.sleep(0.25)
        assert database_path.is_file()
        with sqlite3.connect(database_path) as database:
            assert database.execute("SELECT value FROM settings WHERE key='language'").fetchone()[0] == "ja"
            assert database.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
        log = (database_path.parent / "application.log").read_text(encoding="utf-8")
        assert not any(marker in log for marker in ("Traceback", " ERROR ", " CRITICAL ")), log
        return {"frozen_midi_helper": "passed", "frozen_startup_clean_path": "passed",
                "frozen_default_language": "ja", "personal_attempts_in_fresh_profile": 0,
                "frozen_note": "Started hidden with normal Windows Qt platform; terminated only this test process after 12 seconds."}
    finally:
        process.terminate()
        process.wait(timeout=5)


def source_ui_checks():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    sys.path.insert(0, str(ROOT))
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont, QFontDatabase
    from practising_piano_easily.storage import Database
    from practising_piano_easily.midi.controller import MidiController
    from practising_piano_easily.ui.i18n import language
    from practising_piano_easily.ui.main_window import MainWindow
    from practising_piano_easily.ui import falling_piano_page, score_practice_page, online_library_page
    import sounddevice
    MidiController.refresh_devices = lambda self: None
    sounddevice.query_devices = lambda: []
    for module in (falling_piano_page, score_practice_page, online_library_page):
        if hasattr(module, "downloaded_scores"):
            module.downloaded_scores = lambda: []
    app = QApplication([])
    # The offscreen platform does not enumerate Windows system fonts automatically.
    for filename in ("YuGothM.ttc", "meiryo.ttc", "seguisym.ttf", "segoeui.ttf"):
        font = Path(os.environ.get("SYSTEMROOT", "C:\\Windows")) / "Fonts" / filename
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont("Yu Gothic", 10))
    database = Database(":memory:")
    database.set_setting("language", "ja")
    window = MainWindow(database)
    window._skip_summary = True
    window.resize(1440, 960)
    window.show()
    pictures = CHECKS / "japanese-ui"
    pictures.mkdir(exist_ok=True)
    for name, page in (("home", window.home), ("beginner", window.beginner), ("tutorial", window.tutorial),
                       ("falling", window.falling), ("score", window.score_practice)):
        window.navigation.setCurrentRow(window.pages.indexOf(page))
        window.showNormal()
        window.resize(1440, 960)
        app.processEvents()
        assert window.grab().save(str(pictures / f"{name}.png"))
    assert language.code == "ja"
    for page in (window.beginner, window.falling, window.score_practice):
        assert page is not None
    window.close()
    return {"source_japanese_ui_render": "passed", "screenshots": 5,
            "source_note": "In-memory database, simulated MIDI discovery/audio inventory; not a physical keyboard test."}


if __name__ == "__main__":
    CHECKS.mkdir(parents=True, exist_ok=True)
    result = frozen_checks() | source_ui_checks()
    (CHECKS / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
