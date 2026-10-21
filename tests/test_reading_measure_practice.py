import json
import sqlite3

import mido
import pytest

from practising_piano_easily.midi.state import MidiEvent
from practising_piano_easily.trainers.falling_notes import FallingScore
from test_falling_piano import app, win, downloaded_fixture


@pytest.fixture
def reading_page(win, tmp_path):
    source = downloaded_fixture(tmp_path, "reading-bars")
    midi = mido.MidiFile(ticks_per_beat=480)
    midi.tracks.append(mido.MidiTrack([
        mido.MetaMessage("set_tempo", tempo=500_000),
        mido.MetaMessage("set_tempo", tempo=1_000_000, time=1920),
        mido.MetaMessage("time_signature", numerator=3, denominator=4, time=5760)]))
    notes = mido.MidiTrack()
    previous = 0
    for bar in range(10):
        start = 1920 * bar if bar < 4 else 7680 + (bar - 4) * 1440
        for index in range(3 if bar == 0 else 2):
            tick = start + index * 240
            pitch = 60 + (bar + index) % 5
            notes.append(mido.Message("note_on", note=pitch, velocity=80, time=tick - previous))
            notes.append(mido.Message("note_off", note=pitch, time=120))
            previous = tick + 120
    midi.tracks.append(notes)
    midi.save(tmp_path / "score.mid")
    page = win.online_library.practice
    page.open_score(source, tmp_path)
    win._open_score_practice()
    return page


def finish_with_keys_held(page):
    follower = page.follower
    for index, group in enumerate(follower.groups):
        for note in sorted(group.notes):
            page.controller.demo_note(note, True)
        if index + 1 < len(follower.groups):
            for note in sorted(group.notes):
                page.controller.demo_note(note, False)
    assert follower.finished and not page._running
    return follower


def release_all(page):
    for note in tuple(page.controller.pressed_notes):
        page.controller.demo_note(note, False)


def test_reading_defaults_to_four_real_bars_with_independent_endpoints_and_meter_changes(reading_page):
    page = reading_page
    assert (page.first.value(), page.last.value()) == (1, 4)
    assert page.first.maximum() == page.last.maximum() == 10
    assert len(page._section.groups) == 9  # Four bars are not the first four attack groups.
    page.first.setValue(5)
    assert page.last.value() == 4 and page._section is None
    assert not page.start.isEnabled() and not page.falling_button.isEnabled() and "互不联动" in page.feedback.text()
    page.last.setValue(8)
    assert page.first.value() == 5 and page.start.isEnabled()
    assert page._section.duration == 12 and page._offset == 14
    assert len(page._section.groups) == 8
    page.last.setValue(3)
    assert page.first.value() == 5 and not page.start.isEnabled()
    page.first.setValue(2)
    assert page.last.value() == 3 and page.start.isEnabled()


def test_loop_records_each_completed_passage_once_then_waits_for_release(reading_page, win):
    page = reading_page
    page.loop_current.setChecked(True)
    page.start_practice()
    for iteration in (1, 2):
        follower = finish_with_keys_held(page)
        assert page._repeat_pending and page._saved
        page._save_result()
        rows = win.database.connection.execute("SELECT * FROM attempts").fetchall()
        assert len(rows) == iteration and ":bars:1-4" in rows[-1]["question"]
        metadata = json.loads(rows[-1]["metadata_json"])
        assert (metadata["first_bar"], metadata["last_bar"], metadata["range_unit"]) == (1, 4, "bar")
        release_all(page)
        assert page.follower is not follower and page._running and not page._repeat_pending
        assert page.follower.index == page.follower.mistakes == 0
        assert (page.first.value(), page.last.value()) == (1, 4)
        assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == iteration


@pytest.mark.parametrize("cancel", ["loop_off", "leave", "range", "source"])
def test_waiting_repeat_is_cancelled_and_never_restarts_after_leaving_or_changing_range(reading_page, win, cancel):
    page = reading_page
    page.loop_current.setChecked(True)
    page.start_practice()
    follower = finish_with_keys_held(page)
    if cancel == "loop_off":
        page.loop_current.setChecked(False)
    elif cancel == "leave":
        win.navigation.setCurrentRow(0)
    elif cancel == "range":
        page.last.setValue(3)
    else:
        page.open_score(page.source, page.folder)
    release_all(page)
    assert not page._repeat_pending and not page._running
    if cancel == "loop_off":
        assert page.follower is follower and page.follower.finished
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 1


def test_loop_off_finishes_without_advancing_and_sustain_does_not_block_loop_restart(reading_page):
    page = reading_page
    page.start_practice()
    follower = finish_with_keys_held(page)
    release_all(page)
    assert page.follower is follower and not page._running and not page._repeat_pending
    page.controller._process(MidiEvent("control_change", control=64, value=127))
    page.loop_current.setChecked(True)
    assert page._running and page.follower.index == 0
    follower = finish_with_keys_held(page)
    release_all(page)
    assert page._running and page.follower is not follower


def test_save_failure_blocks_automatic_repeat_until_successful_retry(reading_page, win, monkeypatch):
    from practising_piano_easily.ui.localized_widgets import QMessageBox
    page = reading_page
    record = win.database.record_attempt
    monkeypatch.setattr(win.database, "record_attempt", lambda **_: (_ for _ in ()).throw(sqlite3.OperationalError("locked")))
    monkeypatch.setattr(QMessageBox, "critical", lambda *_: None)
    page.loop_current.setChecked(True)
    page.start_practice()
    follower = finish_with_keys_held(page)
    release_all(page)
    assert page.follower is follower and not page._repeat_pending and page.save.isVisible()
    monkeypatch.setattr(win.database, "record_attempt", record)
    page.save.click()
    assert page._running and page.follower is not follower and page.follower.index == 0
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 1


def test_rest_only_range_does_not_create_grades_or_an_endless_empty_loop(reading_page, win):
    page = reading_page
    original = page.full_score
    page.full_score = FallingScore(tuple(note for note in original.notes if note.start < 2 or note.start >= 6), original.timeline)
    page.first.setValue(2)
    page.last.setValue(2)
    page.loop_current.setChecked(True)
    assert not page._section.groups and not page.start.isEnabled()
    page.start_practice()
    assert not page._running and not page._repeat_pending
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0


def test_tied_in_notes_are_required_at_the_selected_bar_boundary(reading_page):
    from practising_piano_easily.trainers.falling_notes import FallingNote
    page = reading_page
    page.full_score = FallingScore((FallingNote(55, 1.5, 3), FallingNote(60, 3, 4)), page.full_score.timeline)
    page.first.setValue(2)
    page.last.setValue(2)
    page.start_practice()
    assert page.follower.expected == {55} and page.follower.groups[0].time == 0
    assert page._offset == 2


def test_reading_bar_range_handoff_keeps_bar_units_and_selected_track(reading_page, win):
    page = reading_page
    page.last.setValue(8)
    page.first.setValue(5)
    page.falling_button.click()
    falling = win.falling
    assert falling.range_mode.currentIndex() == 0
    assert (falling.first.value(), falling.last.value()) == (5, 8)
    assert falling._offset == page._offset
    assert not falling.session.running


@pytest.mark.parametrize("workspace", ["reading", "falling"])
def test_typing_bar_numbers_commits_one_field_without_changing_the_other(reading_page, win, workspace):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    page = reading_page
    if workspace == "falling":
        win._open_falling_downloaded((page.source, page.folder, -1, 1, 4, "bar"))
        page = win.falling
    page.first.lineEdit().selectAll()
    QTest.keyClicks(page.first.lineEdit(), "7")
    assert (page.first.value(), page.last.value()) == (1, 4)
    QTest.keyClick(page.first.lineEdit(), Qt.Key.Key_Return)
    assert (page.first.value(), page.last.value()) == (7, 4)
    page.last.lineEdit().selectAll()
    QTest.keyClicks(page.last.lineEdit(), "8")
    QTest.keyClick(page.last.lineEdit(), Qt.Key.Key_Return)
    assert (page.first.value(), page.last.value()) == (7, 8)


def test_loop_save_failure_retries_on_exit_without_starting_practice(reading_page, win, monkeypatch):
    page = reading_page
    save = win.database.set_setting
    monkeypatch.setattr(win.database, "set_setting", lambda *_: (_ for _ in ()).throw(sqlite3.OperationalError("locked")))
    page.loop_current.setChecked(True)
    assert page.loop_current.isChecked() and not page._saved_loop and "未能保存" in page.feedback.text()
    monkeypatch.setattr(win.database, "set_setting", save)
    win.navigation.setCurrentRow(0)
    assert win.database.get_setting("reading_loop_current") == "1"
    assert not page._running and not page._repeat_pending
