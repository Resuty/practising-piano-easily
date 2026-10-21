import json
import os
import sqlite3
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import mido
import pytest
from PySide6.QtGui import QPainter, QPdfWriter
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from practising_piano_easily.analysis.falling_score import load_falling_midi
from practising_piano_easily.analysis.online_scores import OnlineScore
from practising_piano_easily.midi.controller import MidiController
from practising_piano_easily.midi.state import MidiEvent
from practising_piano_easily.storage import Database
from practising_piano_easily.trainers.beginner_course import LESSONS, PIECES
from practising_piano_easily.trainers.falling_notes import FallingNote, FallingScore, FallingSession, score_from_lesson
from practising_piano_easily.ui.main_window import MainWindow
from practising_piano_easily.ui.i18n import language
from practising_piano_easily.ui.keyboard_widget import piano_key_rects
from practising_piano_easily.ui.pdf_score_position import first_staff_top
from practising_piano_easily.ui.midi_notation_widget import written_pitch, rhythm_glyph


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, monkeypatch):
    import sounddevice
    monkeypatch.setattr(MidiController, "refresh_devices", lambda self: None)
    monkeypatch.setattr(sounddevice, "query_devices", lambda: [])
    monkeypatch.setattr(sounddevice, "stop", lambda: None)
    monkeypatch.setattr(sounddevice, "OutputStream", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("Test audio disabled")))
    window = MainWindow(Database(":memory:"))
    window._skip_summary = True
    window.show()
    app.processEvents()
    yield window
    window.close()


def on(note):
    return MidiEvent("note_on", note=note, velocity=80)


def off(note):
    return MidiEvent("note_on", note=note, velocity=0)


def test_all_builtins_preserve_note_durations_hands_and_score_sections():
    for lesson in LESSONS + PIECES:
        score = score_from_lesson(lesson)
        assert len(score.groups) == len(lesson.steps)
        assert score.duration == pytest.approx(sum(step.beats for step in lesson.steps) * 0.75)
        assert score.groups[0].notes == lesson.steps[0].notes
        part, offset = score.section(2, len(score.groups))
        assert part.groups[0].time == 0
        assert offset == score.groups[1].time
        assert part.duration == pytest.approx(score.duration - offset)
    assert {note.voice for note in score_from_lesson(LESSONS[5]).notes} == {"right", "left"}


def test_score_validation_and_visibility_include_long_held_notes():
    for args in ((128, 0, 1), (60, 2, 1), (60, -1, 1), (60, 0, float("nan")), (60.5, 0, 1)):
        with pytest.raises(ValueError):
            FallingNote(*args)
    with pytest.raises(ValueError):
        FallingScore(())
    with pytest.raises(ValueError):
        FallingScore((FallingNote(60, 1, 2), FallingNote(62, 0, 1)))
    score = FallingScore((FallingNote(60, 0, 5), FallingNote(64, 1, 1.5), FallingNote(62, 4, 5)))
    assert [note.pitch for note in score.visible_notes(3, 2)] == [60, 62]
    with pytest.raises(ValueError):
        score.section(2, 1)


def test_follow_waits_for_partial_chords_supports_corrections_and_finishes_after_tail():
    score = FallingScore((FallingNote(60, 0, 2), FallingNote(64, 0, 2)))
    session = FallingSession(score)
    session.running = True
    assert session.advance(100) == "waiting" and session.position == 0
    assert session.event(on(60)) == "waiting"
    assert session.event(on(61)) == "extra" and session.follower.mistakes == 1
    session.event(off(61))
    assert session.event(on(64)) == "finished"
    assert not session.finished  # Note attacks complete, but the displayed tail still has duration.
    assert session.advance(2) == "finished"
    assert session.finished and not session.running


def test_early_held_keys_and_repeated_note_ons_cannot_skip_notes():
    score = FallingScore((FallingNote(60, 0, 1), FallingNote(60, 1, 2)))
    session = FallingSession(score)
    session.running = True
    assert session.event(on(60)) == "early"
    session.advance(3)
    assert session.event(on(60)) == "ignored"
    session.event(off(60))
    assert session.event(on(60)) == "advanced"
    session.advance(1)
    assert session.event(on(60)) == "ignored"
    session.event(off(60))
    assert session.event(on(60)) == "finished"
    session.advance(1)
    assert session.finished


def test_preview_speed_pause_and_invalid_elapsed_do_not_change_following_state():
    session = FallingSession(score_from_lesson(LESSONS[0]), preview=True)
    session.running = True
    session.speed = 0.5
    session.advance(2)
    assert session.position == -2
    assert session.event(on(60)) == "ignored"
    session.running = False
    session.advance(100)
    assert session.position == -2
    session.running = True
    assert session.advance(100) == "finished" and session.follower.index == 0
    with pytest.raises(ValueError):
        session.advance(float("nan"))
    with pytest.raises(ValueError):
        session.advance(-1)


def make_midi(path, *, midi_type=1, tempo=1_000_000):
    midi = mido.MidiFile(type=midi_type, ticks_per_beat=480)
    control = mido.MidiTrack()
    control.extend((mido.MetaMessage("set_tempo", tempo=500_000),
                    mido.MetaMessage("set_tempo", tempo=tempo, time=480)))
    notes = mido.MidiTrack()
    notes.extend((mido.Message("note_on", note=60, velocity=80),
                  mido.Message("note_off", note=60, time=960),
                  mido.Message("note_on", note=62, velocity=80),
                  mido.Message("note_off", note=62, time=480)))
    drums = mido.MidiTrack()
    drums.extend((mido.Message("note_on", channel=9, note=38, velocity=80),
                  mido.Message("note_off", channel=9, note=38, time=480)))
    midi.tracks.extend((control, notes, drums))
    midi.save(path)


def test_midi_tempo_map_tracks_and_percussion_are_converted_correctly(tmp_path):
    path = tmp_path / "tempo.mid"
    make_midi(path)
    score, summary = load_falling_midi(path)
    assert [note.pitch for note in score.notes] == [60, 62]
    assert score.notes[0].start == 0 and score.notes[0].end == pytest.approx(1.5)
    assert score.notes[1].start == pytest.approx(1.5) and score.duration == pytest.approx(2.5)
    assert {note.voice for note in score.notes} == {"track:1"}
    assert load_falling_midi(path, 1)[0] == score
    with pytest.raises(ValueError):
        load_falling_midi(path, 2)  # Percussion is never treated as pitched piano notes.
    make_midi(path, midi_type=2)
    with pytest.raises(ValueError, match="synchronous"):
        load_falling_midi(path)
    make_midi(path, tempo=0)
    with pytest.raises(ValueError, match="positive"):
        load_falling_midi(path)


def test_native_entry_maximizes_restores_window_and_labels_black_and_white_keys(win, app):
    size = win.size()
    win._open_falling_lesson(LESSONS[3])
    app.processEvents()
    page = win.falling
    assert win.isMaximized() and win.pages.currentWidget() is page
    assert page.keyboard.label_all_notes and page._lesson.id == "c_chord"
    page.grab()
    note = page.session.score.notes[0]
    rect = page.roll.block_rect(note)
    keys = piano_key_rects(page.keyboard.start_note, page.keyboard.end_note, page.roll.width(), 130)
    assert rect.center().x() == pytest.approx(keys[note.pitch].center().x())
    assert page.roll.width() == page.keyboard.width()
    assert 61 in page.keyboard._key_rects  # Black keys are drawn, clickable, and labeled in this mode.
    page.key_range.setCurrentIndex(1)
    assert (page.keyboard.start_note, page.keyboard.end_note) == (21, 109)
    page.grab()
    assert len(page.keyboard._key_rects) == 88
    win.navigation.setCurrentRow(0)
    app.processEvents()
    assert not win.isMaximized() and win.size() == size


def fake_clock(monkeypatch):
    value = [100.0]
    monkeypatch.setattr("practising_piano_easily.ui.falling_piano_page.time.monotonic", lambda: value[0])
    def advance(page, seconds):
        value[0] += seconds
        page._tick()
    return advance


def start_follow(page):
    """Enter the follow phase; individual regression tests need not replay the demonstration."""
    page.start()
    if page._section_demo:
        page._stop_demo()
        page.session.position = page.session.score.duration
        page._tick()
        page.resume_timer.stop()
        page.session.position = -3
        page._resume_deadline = time.monotonic()
        page._resume_tick()


def test_gui_waiting_completion_records_once_and_other_pages_do_not_consume_input(win, monkeypatch):
    advance = fake_clock(monkeypatch)
    win._open_falling_lesson(LESSONS[3])
    page = win.falling
    page.speed.setValue(100)
    start_follow(page)
    page.timer.stop()
    advance(page, 3)
    assert page.session.waiting
    for note in (60, 64, 66):
        win.controller.demo_note(note, True)
    assert page.session.follower.index == 0 and page.session.follower.mistakes == 1
    win.controller.demo_note(66, False)
    win.controller.demo_note(67, True)
    for note in (60, 64, 67):
        win.controller.demo_note(note, False)
    advance(page, 3)
    for note in (60, 64, 67):
        win.controller.demo_note(note, True)
        win.controller.demo_note(note, False)
    advance(page, 3)
    assert page.session.finished
    rows = win.database.connection.execute("SELECT * FROM attempts").fetchall()
    assert len(rows) == 1 and rows[0]["trainer_type"] == "falling_piano"
    assert not rows[0]["correct"]
    metadata = json.loads(rows[0]["metadata_json"])
    assert metadata["completed"] and not metadata["timing_graded"]
    assert win.trainer.trainer.correct_count == 0 and win.beginner.follower.index == 0
    page._save_result()
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 1


def test_preview_has_no_practice_record_and_builtin_notation_uses_stable_systems(win, monkeypatch):
    advance = fake_clock(monkeypatch)
    win._open_falling_lesson(PIECES[0])
    page = win.falling
    page.mode.setCurrentIndex(1)
    page.speed.setValue(100)
    page.start()
    page.timer.stop()
    advance(page, 15)
    assert page.score_views.currentWidget() is page.midi_staff
    assert page.midi_staff.horizontalScrollBar().value() == 0
    assert page.midi_staff.position > 0 and page.midi_staff.current_measure > 0
    win.controller.demo_note(61, True)
    win.controller.demo_note(61, False)
    assert page.session.follower.mistakes == 0
    advance(page, 100)
    assert page.session.finished
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0


def test_pause_hide_and_held_keys_do_not_resume_or_score_automatically(win, monkeypatch):
    advance = fake_clock(monkeypatch)
    win._open_falling_lesson(LESSONS[0])
    page = win.falling
    start_follow(page)
    page.pause()
    win.controller.demo_note(60, True)
    page.start()
    assert not page.session.running
    win.controller.demo_note(60, False)
    page.start()
    page.timer.stop()
    advance(page, 1)
    position = page.session.position
    page.pause()
    advance(page, 100)
    assert page.session.position == position
    page.start()
    win.navigation.setCurrentRow(0)
    assert not page.session.running and not page.timer.isActive()
    win.controller.demo_note(60, True)
    win.controller.demo_note(60, False)
    assert page.session.follower.index == 0


def test_downloaded_pdf_handoff_preserves_track_range_source_and_language(win, app, tmp_path, monkeypatch):
    folder = tmp_path / "downloaded"
    folder.mkdir()
    make_midi(folder / "score.mid")
    midi = mido.MidiFile(folder / "score.mid")
    midi.tracks[1][2].time = 960  # Move the second attack to bar 2, rather than treating attack group 2 as a bar.
    midi.save(folder / "score.mid")
    writer = QPdfWriter(str(folder / "score.pdf"))
    painter = QPainter(writer)
    painter.drawText(100, 100, "Original PDF fixture")
    writer.newPage()
    painter.drawText(100, 100, "Second page")
    painter.end()
    del painter, writer
    source = OnlineScore("999", "Angel Beats! · Game song", "Arranger", "Public Domain", "https://www.mutopiaproject.org/legal.html", "https://www.mutopiaproject.org/test", "", "")
    win.navigation.setCurrentRow(13)
    original = win.online_library.practice
    original.open_score(source, folder)
    win._open_score_practice()
    original.track.setCurrentIndex(original.track.findData(1))
    original.first.setValue(2)
    original.last.setValue(2)
    original.falling_button.click()
    app.processEvents()
    page = win.falling
    assert win.pages.currentWidget() is page and page.document.pageCount() == 2
    assert page._pdf_start_y == 0  # Non-score PDFs safely retain the page-top fallback.
    assert page.track.currentData() == 1 and page.first.value() == page.last.value() == 2
    assert page.range_mode.currentIndex() == 0
    assert page.session.score.notes[0].pitch == 62 and len(page.session.score.groups) == 1
    assert page.credit.text().startswith("Angel Beats! · Game song")
    session = page.session
    language.set_language("en")
    assert page.session is session and "Angel Beats!" in page.source_picker.currentText()
    language.set_language("zh_CN")
    assert page.session is session
    page.auto_pdf.setChecked(False)
    bar = page.pdf.verticalScrollBar()
    bar.setValue(bar.maximum() // 2)
    previous = bar.value()
    page._render()
    assert bar.value() == previous
    advance = fake_clock(monkeypatch)
    page.speed.setValue(100)
    page.start()
    page.timer.stop()
    advance(page, 3)
    win.controller.demo_note(62, True)
    win.controller.demo_note(62, False)
    advance(page, 1)
    assert page.session.finished
    row = win.database.connection.execute("SELECT * FROM attempts WHERE trainer_type='falling_piano'").fetchone()
    assert json.loads(row["metadata_json"])["source_url"] == source.source_url


def test_pdf_opens_at_first_staff_and_keeps_it_through_resize_restart_and_lead_in(win, app, tmp_path):
    make_midi(tmp_path / "score.mid")
    midi = mido.MidiFile(tmp_path / "score.mid")
    midi.tracks[1][0].time = 480  # Leading silence must not scroll past the opening staff.
    midi.save(tmp_path / "score.mid")
    writer = QPdfWriter(str(tmp_path / "score.pdf"))
    writer.setResolution(72)
    painter = QPainter(writer)
    painter.drawText(100, 60, "A large title and a long blank header")
    for top in (300, 370):
        for line in range(5):
            painter.drawLine(30, top + line * 6, 500, top + line * 6)
    painter.end()
    del painter, writer
    source = OnlineScore("header", "Tall title", "Arranger", "Public Domain", "", "https://www.mutopiaproject.org/test", "", "")
    win._open_falling_downloaded((source, tmp_path, -1, 1, 2))
    app.processEvents()
    page = win.falling
    assert page._offset > 0
    assert 260 < first_staff_top(page.document) < 330
    page.score_mode.setCurrentIndex(1)
    app.processEvents()
    bar = page.pdf.verticalScrollBar()
    assert bar.value() > 0

    def expected_start():
        margins = page.pdf.documentMargins()
        width = page.pdf.viewport().width() - margins.left() - margins.right()
        return min(bar.maximum(), margins.top() + page._pdf_start_y * width / page.document.pagePointSize(0).width())

    assert bar.value() == pytest.approx(expected_start(), abs=1)
    win.showNormal()
    win.resize(1400, 900)
    app.processEvents()
    assert bar.value() == pytest.approx(expected_start(), abs=1)
    page.restart()
    page.timer.stop()
    page.session.advance(1)
    page._render()
    assert bar.value() == pytest.approx(expected_start(), abs=1)
    page.auto_pdf.setChecked(False)
    bar.setValue(bar.maximum() // 2)
    manual = bar.value()
    page._render()
    assert bar.value() == manual
    page.open_downloaded((source, tmp_path, -1, 1, 2))
    app.processEvents()
    assert bar.value() == pytest.approx(expected_start(), abs=1)  # A new opening still starts at the staff in manual mode.


def test_native_measure_highlight_and_harmony_wait_with_the_falling_blocks(win, monkeypatch):
    advance = fake_clock(monkeypatch)
    win._open_falling_lesson(LESSONS[5])
    page = win.falling
    page.speed.setValue(100)
    start_follow(page)
    page.timer.stop()
    advance(page, 3)
    assert page.session.waiting and page.midi_staff.current_measure == 0
    assert page.chord_label.text().startswith("小节 1 /")
    assert page._chord_text == "C"
    win.controller.demo_note(60, True)
    win.controller.demo_note(61, True)
    advance(page, 60)
    assert page.midi_staff.position == 0 and page.midi_staff.current_measure == 0
    win.controller.demo_note(61, False)
    for note in (48, 64, 67):
        win.controller.demo_note(note, True)
    advance(page, 3)
    assert page.midi_staff.current_measure == 1 and page._chord_text == "Am"
    assert page.midi_staff.position == page._offset + page.session.position
    page.grab()
    assert page.midi_staff.measure_rect(1).x() > page.midi_staff.measure_rect(0).x()
    page.pause()
    advance(page, 60)
    assert page.midi_staff.current_measure == 1
    for note in tuple(win.controller.pressed_notes):
        win.controller.demo_note(note, False)


def test_midi_practice_score_follows_tempo_range_and_view_switch_without_reset(win, app, tmp_path, monkeypatch):
    midi = mido.MidiFile(ticks_per_beat=480)
    midi.tracks.append(mido.MidiTrack([mido.MetaMessage("set_tempo", tempo=500_000),
                                     mido.MetaMessage("set_tempo", tempo=1_000_000, time=1920)]))
    for pitches in ((48, 55), (64,)):
        track = mido.MidiTrack()
        for beat in range(32):
            for note in pitches:
                track.append(mido.Message("note_on", note=note, velocity=80))
            for index, note in enumerate(pitches):
                track.append(mido.Message("note_off", note=note, time=480 if index == 0 else 0))
        midi.tracks.append(track)
    midi.save(tmp_path / "score.mid")
    writer = QPdfWriter(str(tmp_path / "score.pdf"))
    painter = QPainter(writer)
    painter.drawText(100, 100, "Original edition, not MIDI notation")
    painter.end()
    del painter, writer
    source = OnlineScore("sync", "Full score", "Arranger", "Public Domain", "", "https://www.mutopiaproject.org/test", "", "")
    win._open_falling_downloaded((source, tmp_path, 2, 5, 20))
    app.processEvents()
    page = win.falling
    assert page.score_mode.currentIndex() == 0
    assert page.score_views.currentWidget() is page.midi_staff
    assert page.midi_staff.current_measure == 1  # The selection starts in measure 2, not a renumbered measure 1.
    assert page._chord_text == "C"  # Full-score harmony remains available while practising the E-only track.
    assert {note.pitch for note in page.midi_staff.score.notes} == {64}
    assert page.midi_staff.timeline is page._all_score.timeline
    page.mode.setCurrentIndex(1)
    advance = fake_clock(monkeypatch)
    page.speed.setValue(100)
    page.start()
    page.timer.stop()
    advance(page, 8)
    assert page.midi_staff.position == page._offset + page.session.position
    assert page.midi_staff.current_measure == 2
    assert page.midi_staff.horizontalScrollBar().value() == 0
    engine = page.session
    position = engine.position
    page.score_mode.setCurrentIndex(1)
    app.processEvents()
    assert page.score_views.currentWidget() is page.pdf and page.document.pageCount() == 1
    page.score_mode.setCurrentIndex(0)
    assert page.session is engine and engine.position == position and engine.running
    language.set_language("en")
    assert page.session is engine and "MIDI inference" in page.chord_label.text()
    language.set_language("zh_CN")
    page.grab()
    page._open_chord_link("chord:C")
    assert win.pages.currentWidget() is win.tutorial
    win._escape()
    assert win.pages.currentWidget() is page
    assert page.session is engine and engine.position == position and not engine.running
    assert page.track.currentData() == 2 and (page.first.value(), page.last.value()) == (5, 20)
    assert page.score_mode.currentIndex() == 0


def test_midi_notation_octaves_and_rhythm_glyphs_are_explicit():
    assert written_pitch(108) == (96, 1)
    assert written_pitch(21) == (33, -1)
    assert written_pitch(61) == (61, 0)
    assert rhythm_glyph(1.5) == (1, True, 0)
    assert rhythm_glyph(.5) == (.5, False, 1)
    assert rhythm_glyph(.25) == (.25, False, 2)
    assert rhythm_glyph(4) == (4, False, 0)


def test_chord_learning_shows_chinese_tones_actual_keys_and_separate_reference_marks(win, monkeypatch):
    win._open_falling_lesson(LESSONS[5])
    page = win.falling
    assert "C 大三和弦" in page.chord_label.text()
    assert 'href="chord:C"' in page.chord_label.text()
    assert "C · E · G" in page.chord_tones.text()
    assert "C3" in page.chord_keys.text() and "C4" in page.chord_keys.text()
    assert page.keyboard.reference_notes == frozenset((48, 60, 64, 67))
    assert page.keyboard.expected_notes == frozenset()  # Reference marks do not create extra practice targets.
    page.keyboard.start_note, page.keyboard.end_note = 60, 84
    page._render()
    assert "部分参考键" in page.chord_keys.text()
    page.key_range.setCurrentIndex(1)
    assert "部分参考键" not in page.chord_keys.text()
    page.keyboard.set_notes(frozenset((60, 61)), correct=frozenset((60,)), incorrect=frozenset((61,)))
    assert page.keyboard._color(60, False).name() == "#22c55e"
    assert page.keyboard._color(61, True).name() == "#ef4444"
    page.keyboard.grab()
    for symbol, notes in (("C", (48, 60, 64, 67)), ("F#", (54, 58, 61))):
        page.keyboard.set_reference_notes(frozenset(notes))
        image = page.keyboard.grab().toImage()
        for note in notes:
            rect = page.keyboard._key_rects[note]
            assert image.pixelColor(round(rect.center().x()), round(rect.bottom() - 34)).name() == "#a855f7"
    language.set_language("en")
    assert "Major triad" in page.chord_label.text()
    language.set_language("zh_CN")
    monkeypatch.setattr("practising_piano_easily.ui.falling_piano_page.harmony_at", lambda *_: ((), (60,)))
    page._harmony_key = None
    page._render()
    assert not page.keyboard.reference_notes
    assert not page.chord_tones.text() and not page.chord_keys.text()
    assert "不能确定和弦" in page.chord_label.text()


def test_chord_links_open_the_exact_tutorial_example_and_escape_returns_without_reset(win, app, monkeypatch):
    advance = fake_clock(monkeypatch)
    win._open_falling_lesson(LESSONS[5])
    page = win.falling
    page.speed.setValue(100)
    start_follow(page)
    page.timer.stop()
    advance(page, 3)
    engine, position = page.session, page.session.position
    win.controller.demo_note(60, True)
    page.chord_label.linkActivated.emit("chord:C")
    app.processEvents()
    assert win.pages.currentWidget() is win.tutorial
    assert win.tutorial.lesson.id == "triads"
    assert win.tutorial.current_example.symbol == "C"
    assert "从乐谱查看和弦： C 大三和弦" in win.tutorial.reader.toPlainText()
    assert not engine.running and not page.timer.isActive()
    assert engine.follower.hits == {60}
    win.activateWindow()
    win.tutorial.reader.setFocus()
    app.processEvents()
    QTest.keyClick(win.tutorial.reader, Qt.Key.Key_Escape)
    app.processEvents()
    assert win.pages.currentWidget() is page
    assert page.session is engine and engine.position == position and not engine.running
    assert engine.follower.hits == {60}
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
    win.controller.demo_note(60, False)
    page.start()
    page.timer.stop()
    assert engine.running
    for note in (48, 60, 64, 67):
        win.controller.demo_note(note, True)
        win.controller.demo_note(note, False)
    advance(page, 3)
    assert "Am 小三和弦" in page.chord_label.text()
    assert "A · C · E" in page.chord_tones.text()


def test_ambiguous_chords_keep_each_name_tone_list_and_its_own_tutorial_link(win, monkeypatch):
    win._open_falling_lesson(LESSONS[5])
    page = win.falling
    monkeypatch.setattr("practising_piano_easily.ui.falling_piano_page.harmony_at", lambda *_: (("C6", "Am7/C"), (48, 60, 64, 67, 69)))
    page._harmony_key = None
    page._render()
    assert "候选" in page.chord_label.text()
    assert 'href="chord:C6"' in page.chord_label.text()
    assert 'href="chord:Am7%2FC"' in page.chord_label.text()
    assert "C · E · G · A" in page.chord_tones.text()
    assert "A · C · E · G" in page.chord_tones.text()
    page.chord_label.linkActivated.emit("chord:Am7%2FC")
    assert win.tutorial.lesson.id == "inversions"
    assert win.tutorial.current_example.symbol == "Am7/C"
    assert "低音： C" in win.tutorial.reader.toPlainText()
    assert min(win.tutorial.current_example.notes) % 12 == 0
    win._escape()
    assert win.pages.currentWidget() is page
    before = win.pages.currentIndex()
    for link in ("https://example.com", "chord:<script>", "chord:NotAChord"):
        page._open_chord_link(link)
        assert win.pages.currentIndex() == before


def test_harmony_explanations_do_not_reflow_the_two_system_score(win, app, monkeypatch):
    win._open_falling_lesson(PIECES[0])
    page = win.falling
    app.processEvents()
    notation = page.midi_staff
    geometry = notation.geometry()
    systems, bounds = notation.systems, notation.measure_bounds
    for names, notes in (((), ()), (("C",), (48, 60, 64, 67)),
                         (("C6", "Am7/C"), (48, 60, 64, 67, 69)), ((), (60,))):
        monkeypatch.setattr("practising_piano_easily.ui.falling_piano_page.harmony_at", lambda *_, value=(names, notes): value)
        page._harmony_key = None
        page._render()
        app.processEvents()
        assert notation.geometry() == geometry
        assert notation.systems == systems and notation.measure_bounds == bounds
    page.chord_tones.setText("\n".join(["C · 组成音： C · E · G"] * 20))
    page.chord_tones.show()
    app.processEvents()
    assert page.harmony_scroll.verticalScrollBar().maximum() > 0
    assert notation.geometry() == geometry and notation.measure_bounds == bounds


def test_small_window_and_splitter_keep_both_score_lines_visible(win, app):
    win._open_falling_lesson(PIECES[0])
    win.showNormal()
    win.resize(1160, 820)
    app.processEvents()
    page = win.falling
    page.splitter.setSizes([100, 600])
    app.processEvents()
    notation = page.midi_staff
    assert page.score_views.height() >= notation.height() >= notation.minimumHeight()
    assert len(notation.systems) >= 2
    second_first = notation.systems[1][0]
    assert notation.viewport().rect().contains(notation.measure_rect(second_first).toAlignedRect())
    win.grab()


def test_tutorial_generated_sharp_example_is_temporary_and_default_escape_behavior_remains(win, app):
    win._open_falling_lesson(LESSONS[5])
    page = win.falling
    page._open_chord_link("chord:F%23m")
    tutorial = win.tutorial
    assert tutorial.current_example.symbol == "F#m"
    assert tutorial.example.count() == len(tutorial.lesson.examples) + 1
    assert "F# · A · C#" in tutorial.reader.toPlainText()
    assert tutorial.keyboard.label_all_notes
    assert frozenset(note % 12 for note in tutorial.current_example.notes) == frozenset((6, 9, 1))
    original_example = tutorial.current_example
    win._tutorial_practice(original_example)
    assert win.trainer.trainer.current_chord.symbol == "F#m"
    assert not win._tutorial_return_to_falling
    win._escape()
    assert win.pages.currentWidget() is win.home
    tutorial.chapter.setCurrentIndex(0)
    assert tutorial.example.count() == len(tutorial.lesson.examples)
    assert tutorial._linked_example is None and tutorial._linked_symbol is None
    assert "从乐谱查看和弦" not in tutorial.reader.toPlainText()
    assert sum(len(lesson.quizzes) for lesson in tutorial.lessons) == 19
    win._open_chord_help("C6/9")
    win._tutorial_practice(tutorial.current_example)
    assert win.trainer.trainer.current_chord.symbol == "C6/9"
    assert win.trainer.mode.currentIndex() == 0  # The slash in 6/9 is not a slash-bass inversion.


@pytest.mark.parametrize("speed", [25, 200])
def test_escape_counts_three_real_seconds_then_resumes_the_same_position(win, monkeypatch, speed):
    clock = [100.0]
    monkeypatch.setattr("practising_piano_easily.ui.falling_piano_page.time.monotonic", lambda: clock[0])
    win._open_falling_lesson(LESSONS[5])
    page = win.falling
    page.speed.setValue(speed)
    start_follow(page)
    page.timer.stop()
    page.session.advance(3 / (speed / 100))
    for note in (48, 60, 64, 67):
        win.controller.demo_note(note, True)
        win.controller.demo_note(note, False)
    page.session.advance(1.25 / (speed / 100))
    page._render()
    engine, position, elapsed = page.session, page.session.position, page.session.elapsed
    win._open_chord_help("C")
    win._escape()
    assert page.resume_timer.isActive() and not engine.running
    assert page.pause_button.isEnabled() and not page.play_button.isEnabled()
    page.resume_timer.stop()  # Drive the timer's callback deterministically with the real-time clock seam.
    for now, digit in ((100, "3"), (100.9, "3"), (101, "2"), (102, "1"), (102.999, "1")):
        clock[0] = now
        page._resume_tick()
        assert digit in page.resume_notice.text() and page.resume_notice.isVisible()
        assert page.session is engine and not engine.running
        assert (engine.position, engine.elapsed) == (position, elapsed)
        assert engine.follower.index == 1
    clock[0] = 103
    page._resume_tick()
    assert engine.running and page.timer.isActive() and page._resume_deadline is None
    assert not page.resume_notice.isVisible() and engine.position == position
    page.timer.stop()
    clock[0] = 103.25
    page._tick()
    assert engine.position == pytest.approx(position + .25 * speed / 100)
    assert engine.elapsed == pytest.approx(elapsed + .25)  # The countdown is not practice/response time.
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0


@pytest.mark.parametrize("preview", [False, True])
def test_countdown_does_not_score_pressed_keys_and_follow_waits_for_release(win, monkeypatch, preview):
    clock = [100.0]
    monkeypatch.setattr("practising_piano_easily.ui.falling_piano_page.time.monotonic", lambda: clock[0])
    win._open_falling_lesson(LESSONS[3])
    page = win.falling
    page.mode.setCurrentIndex(int(preview))
    start_follow(page)
    page.timer.stop()
    page.session.advance(3)
    win._open_chord_help("C")
    win._escape()
    page.resume_timer.stop()
    win.controller.demo_note(60, True)
    win.controller.demo_note(61, True)
    assert page.session.follower.index == 0 and not page.session.follower.hits
    assert page.session.follower.mistakes == 0
    clock[0] = 103
    page._resume_tick()
    if not preview:
        assert not page.session.running and "松开琴键" in page.resume_notice.text()
        win.controller.demo_note(60, False)
        win.controller.demo_note(61, False)
        page._resume_tick()
    assert page.session.running and page._resume_deadline is None
    assert not page.resume_notice.isVisible()
    assert page.session.follower.mistakes == 0
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0


@pytest.mark.parametrize("cancel", ["pause", "navigate", "new_lesson"])
def test_countdown_is_cancelled_by_pause_navigation_or_a_new_lesson(win, monkeypatch, cancel):
    clock = [100.0]
    monkeypatch.setattr("practising_piano_easily.ui.falling_piano_page.time.monotonic", lambda: clock[0])
    win._open_falling_lesson(LESSONS[5])
    page = win.falling
    engine = page.session
    win._open_chord_help("C")
    win._escape()
    assert page.resume_timer.isActive()
    if cancel == "pause":
        page.pause_button.click()
    elif cancel == "navigate":
        win.navigation.setCurrentRow(0)
    else:
        page.open_lesson(LESSONS[1])
    assert not page.resume_timer.isActive() and page._resume_deadline is None
    assert not page.resume_notice.isVisible()
    clock[0] = 200
    page._resume_tick()
    assert not page.session.running and not engine.running
    assert not page.timer.isActive()


def test_escaping_from_a_completed_passage_does_not_restart_it(win):
    win._open_falling_lesson(LESSONS[5])
    page = win.falling
    page.mode.setCurrentIndex(1)
    page.session.running = True
    page.session.advance(100)
    engine = page.session
    assert engine.finished
    win._open_chord_help("C")
    win._escape()
    assert page.session is engine and engine.finished
    assert not engine.running and not page.resume_timer.isActive()


def test_whole_song_demo_resets_passage_lights_keys_and_never_scores(win, monkeypatch):
    import sounddevice
    from test_score_demo import FakeStream
    monkeypatch.setattr(sounddevice, "OutputStream", lambda **kwargs: FakeStream(**kwargs))
    monkeypatch.setattr(sounddevice, "stop", lambda: None)
    win._open_falling_lesson(LESSONS[5])
    page = win.falling
    assert page.speed.value() == 100
    page.first.setValue(2)
    page.last.setValue(2)
    page.demo_button.click()
    page.timer.stop()
    assert page.mode.currentIndex() == 2 and page.session.preview
    assert page.first.value() == 1 and page.last.value() == len(page.full_score.groups)
    assert page.session.score is page._all_score and page._offset == 0
    assert page.demo_player.stream.active
    page.session.position = .1
    page._render()
    assert page.keyboard.pressed == frozenset((48, 60, 64, 67))
    assert not win.controller.pressed_notes
    win.controller.demo_note(61, True)
    assert 61 not in page.keyboard.pressed and page.session.follower.index == 0
    win.controller.demo_note(61, False)
    engine = page.session
    stream = page.demo_player.stream
    win._open_chord_help("C")
    assert stream.closed and not engine.running
    win._escape()
    page.resume_timer.stop()
    page._resume_deadline = 0
    page._resume_tick()
    page.timer.stop()
    assert page.session is engine and engine.running and engine.position == .1
    stream = page.demo_player.stream
    page.session.advance(1000)
    page._save_result()
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
    page.pause()
    assert stream.closed


def test_demo_audio_failure_still_plays_visually_and_finishes_cleanly(win, monkeypatch):
    advance = fake_clock(monkeypatch)
    monkeypatch.setattr(win.falling.demo_player, "start", lambda *args: (_ for _ in ()).throw(RuntimeError("no device")))
    win._open_falling_lesson(LESSONS[3])
    page = win.falling
    page.demo_before.setChecked(True)
    page.demonstrate()
    page.timer.stop()
    assert "音频不可用" in page.feedback.text()
    advance(page, 3.1)
    assert page.keyboard.pressed == frozenset((60, 64, 67))
    advance(page, 100)
    assert page.mode.currentIndex() == 0 and page.range_mode.currentIndex() == 0
    assert page._section_demo and page.session.running
    advance(page, page.session.score.duration)
    assert page.resume_timer.isActive() and not page.session.running
    assert page.demo_player.stream is None
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0


def test_demo_uses_audio_clock_live_speed_and_stops_on_completion(win, monkeypatch):
    from types import SimpleNamespace
    import numpy as np
    import sounddevice
    from test_score_demo import FakeStream
    monkeypatch.setattr(sounddevice, "OutputStream", lambda **kwargs: FakeStream(**kwargs))
    monkeypatch.setattr(sounddevice, "stop", lambda: None)
    win._open_falling_lesson(LESSONS[0])
    page = win.falling
    page.demo_before.setChecked(True)
    page.demonstrate()
    page.timer.stop()
    stream = page.demo_player.stream
    # Advance the audio callback in 1-second buffers; UI uses actual output time, not wall-clock guesses.
    for timestamp in range(4):
        stream.callback(np.empty((44_100, 1), dtype=np.float32), 44_100,
                        SimpleNamespace(outputBufferDacTime=float(timestamp)), None)
    stream.time = 3.1
    page._tick()
    assert page.session.position == pytest.approx(.1)
    assert page.keyboard.pressed == frozenset((60,))
    page.speed.setValue(50)
    page._tick()
    assert page.demo_player.renderer.speed == .5
    assert page.session.position == pytest.approx(.1)
    for timestamp in range(4, 30):
        stream.callback(np.empty((44_100, 1), dtype=np.float32), 44_100,
                        SimpleNamespace(outputBufferDacTime=float(timestamp)), None)
    stream.time = 29.9
    page._tick()
    assert page.mode.currentIndex() == 0 and page._section_demo and page.session.running
    assert stream.closed and page.demo_player.stream is not stream
    assert not win.controller.pressed_notes and page.pause_button.isEnabled()
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0


def downloaded_fixture(folder, id="new-game"):
    make_midi(folder / "score.mid")
    writer = QPdfWriter(str(folder / "score.pdf"))
    painter = QPainter(writer)
    painter.drawText(100, 100, "New game score")
    painter.end()
    del painter, writer
    return OnlineScore(id, "New anime / game song", "Arranger", "Public Domain", "", "https://www.mutopiaproject.org/test", "", "")


@pytest.mark.parametrize("path", ["download", "import"])
def test_new_download_and_import_join_falling_library_without_interrupting_it(win, tmp_path, path):
    source = downloaded_fixture(tmp_path)
    win._open_falling_lesson(LESSONS[5])
    page = win.falling
    page.mode.setCurrentIndex(1)
    page.start()
    page.timer.stop()
    engine, key = page.session, page.source_picker.currentData()
    signal = win.online_library.download_ready if path == "download" else win.online_library.musescore.imported
    signal.emit((source, tmp_path))
    assert page.source_picker.findData("mutopia:new-game") >= 0
    assert page.source_picker.currentData() == key and page.session is engine and engine.running
    page.refresh_sources()
    assert page.session is engine and engine.running
    page.pause()
    page.source_picker.setCurrentIndex(page.source_picker.findData("mutopia:new-game"))
    assert page.source_info == source and page.session.score.notes[0].pitch == 60
    assert page.document.pageCount() == 1


@pytest.mark.parametrize("kind", ["builtin", "download", "missing", "damaged"])
def test_last_song_restores_after_closing_and_reopening_without_autoplay(win, app, tmp_path, monkeypatch, kind):
    from practising_piano_easily.ui.falling_piano_page import FallingPianoPage
    db_path = tmp_path / "preferences.db"
    db = Database(db_path)
    session_id = db.start_session()
    if kind in {"download", "damaged"}:
        source = downloaded_fixture(tmp_path)
        monkeypatch.setattr("practising_piano_easily.ui.falling_piano_page.downloaded_scores", lambda: [source])
        monkeypatch.setattr("practising_piano_easily.ui.falling_piano_page.score_folder", lambda item: tmp_path)
        key = "mutopia:new-game"
    else:
        key = "builtin:" + PIECES[3].id
    first = FallingPianoPage(win.controller, db, session_id)
    first.show()
    first.source_picker.setCurrentIndex(first.source_picker.findData(key))
    first.hide()
    assert db.get_setting("falling_last_song") == key
    first.document.close()
    if kind == "missing":
        db.set_setting("falling_last_song", "mutopia:deleted-song")
    elif kind == "damaged":
        (tmp_path / "score.mid").write_bytes(b"not a MIDI")
    db.close()
    reopened = Database(db_path)
    second = FallingPianoPage(win.controller, reopened, reopened.start_session())
    second.show()
    app.processEvents()
    expected = key if kind in {"builtin", "download"} else "builtin:" + LESSONS[0].id
    assert second.source_picker.currentData() == expected
    assert second.session is not None and not second.session.running and not second.timer.isActive()
    assert second.speed.value() == 100 and second.mode.currentIndex() == 0
    second.hide()
    second.document.close()
    reopened.close()


def test_main_window_close_saves_song_and_database_failure_does_not_break_pause(win, monkeypatch):
    win._open_falling_lesson(PIECES[2])
    db = win.database
    original_close = db.close
    closed_with = []
    monkeypatch.setattr(db, "close", lambda: closed_with.append(db.get_setting("falling_last_song")))
    win.close()
    assert closed_with == ["builtin:" + PIECES[2].id]
    win.falling._last_saved_key = None
    monkeypatch.setattr(db, "set_setting", lambda *args: (_ for _ in ()).throw(sqlite3.OperationalError("locked")))
    win.falling.save_last_song()
    assert "未能保存" in win.falling.feedback.text()
    win.falling.pause()
    # The fixture closes again; keep the real connection alive until that close.
    monkeypatch.setattr(db, "close", original_close)
