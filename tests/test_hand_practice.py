import json
import sqlite3

import pytest

from practising_piano_easily.storage import Database
from practising_piano_easily.trainers.beginner_course import LESSONS
from practising_piano_easily.trainers.falling_notes import FallingNote, FallingScore
from practising_piano_easily.trainers.score_timeline import ScoreTimeline
from test_falling_piano import app, win, downloaded_fixture, make_midi
from test_measure_practice import finish_passage


@pytest.mark.parametrize("hand,pitches", [("both", {48, 72}), ("right", {48}), ("left", {72})])
def test_explicit_hands_override_pitch_register(hand, pitches):
    score = FallingScore((FallingNote(48, 0, 1, "right"), FallingNote(72, 1, 2, "left")),
                         ScoreTimeline(((0, 0, .5),), ((0, 4, 4),), 16), span=8)
    part = score.practice_part(hand, 60)
    assert {note.pitch for note in part.notes} == pitches
    assert part.timeline is score.timeline and part.duration == 8


@pytest.mark.parametrize("hand,split,pitches", [("both", 60, {48, 60, 72}), ("right", 60, {60, 72}),
                                              ("left", 60, {48}), ("left", 72, {48, 60})])
def test_imported_hand_split_is_explicitly_register_based(hand, split, pitches):
    score = FallingScore(tuple(FallingNote(note, 0, 1, "track:1") for note in (48, 60, 72)),
                         ScoreTimeline(((0, 0, .5),), ((0, 4, 4),), 16), span=8)
    part = score.practice_part(hand, split)
    assert {note.pitch for note in part.notes} == pitches
    assert part.timeline is score.timeline and part.duration == 8
    assert part.practice_part("right", 108).measure_section(2, 4)[0].duration == 6


def test_manual_track_assignment_keeps_crossing_notes_and_empty_hands_keep_bars():
    score = FallingScore((FallingNote(80, 0, 1, "track:1"), FallingNote(30, 0, 2, "track:2")),
                         ScoreTimeline(((0, 0, .5),), ((0, 4, 4),), 16), span=8)
    assert {note.pitch for note in score.practice_part("left", 60, 1).notes} == {80}
    empty = score.practice_part("right", 108)
    assert not empty.notes and empty.duration == 8 and empty.timeline is score.timeline
    assert empty.measure_section(1, 4)[0].duration == 8
    with pytest.raises(ValueError):
        score.practice_part("unknown")


@pytest.mark.parametrize("hand,voice", [("right", "right"), ("left", "left")])
def test_falling_single_hand_only_requires_selected_notes_and_records_separate_results(win, monkeypatch, hand, voice):
    win._open_falling_lesson(LESSONS[5])
    page = win.falling
    page.hands.hand.setCurrentIndex(page.hands.hand.findData(hand))
    assert {note.voice for note in page.full_score.notes} == {voice}
    assert page.full_score.timeline is page._all_score.timeline
    clock = [100.]
    monkeypatch.setattr("practising_piano_easily.ui.falling_piano_page.time.monotonic", lambda: clock[0])
    finish_passage(page, clock)
    row = win.database.connection.execute("SELECT * FROM attempts").fetchone()
    metadata = json.loads(row["metadata_json"])
    assert metadata["practice_hand"] == hand and metadata["hand_assignment"] == "explicit"
    assert ":hand:" + hand + ":explicit" in row["question"]
    assert row["correct"]


def test_missing_hand_does_not_crash_or_create_a_fake_grade(win):
    win._open_falling_lesson(LESSONS[0])
    page = win.falling
    page.hands.hand.setCurrentIndex(2)
    assert not page.session.score.notes and page.keyboard.end_note > page.keyboard.start_note
    page._save_result()
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
    page.range_mode.setCurrentIndex(1)
    page.mode.setCurrentIndex(2)
    assert page.session is None and not page.play_button.isEnabled()
    win._open_score_practice()
    reading = win.score_practice.practice
    reading.open_lesson(LESSONS[0])
    reading.hands.hand.setCurrentIndex(2)
    assert not reading.start.isEnabled() and not reading._section.notes
    assert "休止" in reading.feedback.text()


@pytest.mark.parametrize("hand", ["right", "left"])
def test_builtin_score_practice_uses_one_hand_and_handoff_keeps_range_and_hand(win, hand):
    win._open_score_practice()
    workspace = win.score_practice
    workspace.source_picker.setCurrentIndex(workspace.source_picker.findData("builtin:" + LESSONS[5].id))
    page = workspace.practice
    page.hands.hand.setCurrentIndex(page.hands.hand.findData(hand))
    page.last.setValue(3)
    page.first.setValue(2)
    assert {note.voice for note in page._section.notes} == {hand}
    page.start_practice()
    for group in page.follower.groups:
        for note in sorted(group.notes):
            win.controller.demo_note(note, True)
            win.controller.demo_note(note, False)
    row = win.database.connection.execute("SELECT * FROM attempts").fetchone()
    assert json.loads(row["metadata_json"])["practice_hand"] == hand
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts WHERE trainer_type='beginner_course'").fetchone()[0] == 0
    page.falling_button.click()
    assert win.pages.currentWidget() is win.falling
    assert (win.falling.first.value(), win.falling.last.value()) == (2, 3)
    assert win.falling.hands.hand.currentData() == hand
    assert {note.voice for note in win.falling.full_score.notes} == {hand}


def test_imported_reading_hand_split_adjustment_and_selected_track_override(win, tmp_path):
    source = downloaded_fixture(tmp_path, "hands")
    make_midi(tmp_path / "score.mid")
    win._open_score_practice()
    page = win.score_practice.practice
    page.open_score(source, tmp_path)
    page.hands.hand.setCurrentIndex(2)
    assert not page._section.groups and "音域" in page.hands.hint.text()
    page.hands.split.setValue(72)
    assert {note.pitch for note in page.full_score.notes} == {60, 62}
    page.track.setCurrentIndex(page.track.findData(1))
    page.hands.split.setValue(21)
    assert {note.pitch for note in page.full_score.notes} == {60, 62}
    assert not page.hands.split.isEnabled() and "所选音轨" in page.hands.hint.text()
    page.falling_button.click()
    assert win.falling.hands.values() == ("left", 21)
    assert {note.pitch for note in win.falling.full_score.notes} == {60, 62}


def test_direct_score_page_has_builtins_without_visiting_library_and_only_one_reader(win):
    from PySide6.QtWidgets import QPushButton
    next(button for button in win.findChildren(QPushButton) if button.text() == "乐谱练习" and button.isVisible()).click()
    workspace = win.score_practice
    assert win.pages.currentWidget() is workspace and workspace.practice._active
    assert workspace.practice is win.online_library.practice
    assert workspace.source_picker.findData("builtin:" + LESSONS[5].id) >= 0
    assert not workspace.practice._running
    workspace.practice.start_practice()
    follower = workspace.practice.follower
    workspace.refresh_sources()
    assert workspace.practice.follower is follower and workspace.practice._running
    win.navigation.setCurrentRow(0)
    assert not workspace.practice._active and not workspace.practice._running


def test_switching_hand_preserves_custom_bar_range_and_stops_incomplete_practice(win):
    win._open_score_practice()
    page = win.score_practice.practice
    page.open_lesson(LESSONS[5])
    page.last.setValue(3)
    page.first.setValue(2)
    page.start_practice()
    page.hands.hand.setCurrentIndex(2)
    assert (page.first.value(), page.last.value()) == (2, 3)
    assert not page._running and not page._repeat_pending and page.follower is None
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0


def test_new_local_score_joins_direct_picker_without_interrupting_follow_and_library_can_open_it(win, tmp_path):
    win._open_score_practice()
    workspace = win.score_practice
    workspace.practice.start_practice()
    follower, key = workspace.practice.follower, workspace.source_picker.currentData()
    source = downloaded_fixture(tmp_path, "direct-entry")
    win.online_library.score_available.emit((source, tmp_path))
    assert workspace.source_picker.findData("mutopia:direct-entry") >= 0
    assert workspace.source_picker.currentData() == key and workspace.practice.follower is follower
    assert workspace.practice._running
    win.navigation.setCurrentRow(13)
    win.online_library._download_done((source, tmp_path))
    assert win.pages.currentWidget() is workspace and workspace.practice._active
    assert workspace.source_picker.currentData() == "mutopia:direct-entry"


def test_hand_preferences_restore_per_page_without_autoplay(win, tmp_path):
    path = tmp_path / "hands.db"
    first = type(win)(Database(path))
    first._skip_summary = True
    first.falling.hands.hand.setCurrentIndex(2)
    first.falling.hands.split.setValue(66)
    first.score_practice.practice.hands.hand.setCurrentIndex(1)
    first.score_practice.practice.hands.split.setValue(54)
    first.close()
    second = type(win)(Database(path))
    second._skip_summary = True
    try:
        assert second.falling.hands.values() == ("left", 66)
        assert second.score_practice.practice.hands.values() == ("right", 54)
        assert not second.falling.session.running and not second.score_practice.practice._running
    finally:
        second.close()


def test_hand_save_failure_keeps_current_filter_and_retries_on_exit(win, monkeypatch):
    win._open_score_practice()
    page = win.score_practice.practice
    save = win.database.set_settings
    monkeypatch.setattr(win.database, "set_settings", lambda *_: (_ for _ in ()).throw(sqlite3.OperationalError("locked")))
    page.hands.hand.setCurrentIndex(2)
    assert page.hands.values()[0] == "left" and "未能保存" in page.hands.hint.text()
    monkeypatch.setattr(win.database, "set_settings", save)
    win.navigation.setCurrentRow(0)
    assert win.database.get_setting("reading_hand") == "left"
