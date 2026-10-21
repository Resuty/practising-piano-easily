import json
import sys
from pathlib import Path

from practising_piano_easily import paths
from practising_piano_easily.app import scan_midi
from practising_piano_easily.midi.controller import MidiController


def test_source_data_location_is_unchanged(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert paths.data_directory() == Path(paths.__file__).resolve().parents[1] / "data"


def test_frozen_data_is_not_written_into_bundle(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "日本語ユーザー"))
    assert paths.data_directory() == tmp_path / "日本語ユーザー" / "practising-piano-easily"


def test_existing_frozen_profile_is_reused_without_moving_data(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    legacy = tmp_path / "MusicTrainingLab"
    legacy.mkdir()
    database = legacy / "music_training_lab.db"
    database.write_bytes(b"existing user data")
    assert paths.data_directory() == legacy
    assert paths.database_path() == database
    assert database.read_bytes() == b"existing user data"
    assert not (tmp_path / "practising-piano-easily").exists()


def test_current_profile_takes_priority_over_legacy(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    current = tmp_path / "practising-piano-easily"
    current.mkdir()
    assert paths.data_directory() == current
    assert paths.database_path() == current / "practice.db"


def test_source_keeps_existing_database_filename(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "data_directory", lambda: tmp_path)
    legacy = tmp_path / "music_training_lab.db"
    legacy.write_bytes(b"existing")
    assert paths.database_path() == legacy
    current = tmp_path / "practice.db"
    current.write_bytes(b"new")
    assert paths.database_path() == current


def test_windowless_scan_writes_unicode_result(monkeypatch, tmp_path):
    import mido
    monkeypatch.setattr(mido, "get_input_names", lambda: ["日本語 MIDI 入力"])
    result = tmp_path / "devices.json"
    assert scan_midi(result) == 0
    assert json.loads(result.read_text(encoding="utf-8")) == ["日本語 MIDI 入力"]


def test_scan_error_is_reported_without_a_gui(monkeypatch, tmp_path):
    import mido
    def fail():
        raise RuntimeError("device unavailable")
    monkeypatch.setattr(mido, "get_input_names", fail)
    result = tmp_path / "devices.json"
    assert scan_midi(result) == 1
    assert json.loads(result.read_text(encoding="utf-8")) == {"error": "device unavailable"}


def test_frozen_scan_relaunches_as_helper_not_python_c(monkeypatch):
    from practising_piano_easily.midi import controller
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    commands = []
    class Process:
        returncode = 0
        def __init__(self, command, **kwargs):
            commands.append(command)
            Path(command[-1]).write_text('["テスト鍵盤"]', encoding="utf-8")
        def communicate(self, timeout):
            return "", ""
    monkeypatch.setattr(controller.subprocess, "Popen", Process)
    midi = MidiController()
    results = []
    midi.devices_ready.connect(results.append)
    midi._refresh_worker()
    assert commands[0][1] == "--midi-scan"
    assert results == [["テスト鍵盤"]]
    assert not Path(commands[0][-1]).exists()
