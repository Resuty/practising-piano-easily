import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from practising_piano_easily.audio import Synthesizer
from practising_piano_easily.core import parse_chord
from practising_piano_easily.midi.controller import MidiController
from practising_piano_easily.storage import Database
from practising_piano_easily.trainers.beginner_course import (
    LESSONS, PIECES, PianoLesson, ScoreStep, ScoreFollower, completed_lessons, next_lesson_index,
)
from practising_piano_easily.ui.main_window import MainWindow
from practising_piano_easily.ui.score_widget import note_y


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, monkeypatch):
    import sounddevice

    monkeypatch.setattr(MidiController, "refresh_devices", lambda self: None)
    monkeypatch.setattr(sounddevice, "query_devices", lambda: [])
    window = MainWindow(Database(":memory:"))
    window._skip_summary = True
    window.show()
    app.processEvents()
    yield window
    window.close()


def test_builtin_scores_are_complete_bars_and_have_consistent_staff_positions():
    assert len(LESSONS) == 24 and len(PIECES) == 12
    assert len({lesson.id for lesson in LESSONS + PIECES}) == 36
    for lesson in LESSONS + PIECES:
        assert sum(step.beats for step in lesson.steps) % 4 == 0
        for step in lesson.steps:
            for note in step.right:
                assert isinstance(note_y(note, "right"), (int, float))
            for note in step.left:
                assert isinstance(note_y(note, "left"), (int, float))
    assert note_y(64, "right") == 94  # E4: bottom treble line
    assert note_y(60, "right") == 104  # C4: first lower ledger line
    assert note_y(43, "left") == 234  # G2: bottom bass line
    assert note_y(57, "left") == 194  # A3: top bass line
    with pytest.raises(ValueError):
        PianoLesson("bad", "", "", (ScoreStep((60,), beats=2),))


def test_follower_waits_for_partial_chords_and_accepts_corrections_without_full_release():
    follower = ScoreFollower(LESSONS[3])
    assert follower.update(frozenset({60})) == "waiting"
    assert follower.update(frozenset({60, 64})) == "waiting"
    assert follower.mistakes == 0
    assert follower.update(frozenset({60, 64, 66})) == "extra"
    follower.update(frozenset({60, 64, 66}))
    assert follower.mistakes == 1
    assert follower.update(frozenset({60, 64, 67})) == "matched"
    assert follower.index == 0
    assert follower.update(frozenset({60, 64, 67})) == "release"
    assert follower.update(frozenset({60})) == "release"
    assert follower.update(frozenset()) == "advanced"
    assert follower.index == 1
    assert follower.update(frozenset({60, 64, 67})) == "matched"
    assert follower.update(frozenset()) == "finished"


def test_score_following_requires_the_written_octave_and_both_hands():
    follower = ScoreFollower(LESSONS[5])
    assert follower.update(frozenset({60, 64, 67})) == "waiting"
    assert follower.update(frozenset({36, 60, 64, 67})) == "extra"
    assert follower.update(frozenset({48, 60, 64, 67})) == "matched"


def test_timed_demo_has_the_notated_duration_and_validates_tempo():
    synth = Synthesizer(sample_rate=1000)
    rendered = synth.render_score((((60,), 1), ((64, 67), 2)), tempo=60)
    assert rendered.shape == (3000,)
    assert rendered.dtype == np.float32
    assert np.max(np.abs(rendered)) > 0
    assert np.all(rendered[900:1000] == 0)
    with pytest.raises(ValueError):
        synth.render_score((((60,), 1),), tempo=0)


def test_home_enters_course_and_completion_moves_to_the_next_lesson(win, app):
    win.home.continue_beginner.click()
    app.processEvents()
    page = win.beginner
    assert win.pages.currentWidget() is page
    assert page.lesson.id == "find_c"
    page.start_button.click()
    win.controller.demo_note(72, True)  # Correct name, wrong octave; correctable.
    assert page.follower.index == 0
    win.controller.demo_note(72, False)
    for step in page.lesson.steps:
        for note in step.notes:
            win.controller.demo_note(note, True)
        for note in step.notes:
            win.controller.demo_note(note, False)
    assert page.follower.finished
    assert page.next_button.isEnabled()
    rows = win.database.connection.execute("SELECT * FROM attempts").fetchall()
    assert len(rows) == 1 and rows[0]["trainer_type"] == "beginner_course"
    assert rows[0]["correct"] == 0  # Completion still counts after correcting mistakes.
    assert completed_lessons(win.database) == {"find_c"}
    assert next_lesson_index(win.database) == 1
    page._save_completion()
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 1
    page.next_button.click()
    assert page.lesson.id == "right_five"


def test_inactive_course_never_consumes_notes_and_can_restart(win, app):
    win._open_beginner()
    win.beginner.start_practice()
    win.navigation.setCurrentRow(0)
    win.controller.demo_note(60, True)
    win.controller.demo_note(60, False)
    assert win.beginner.follower.index == 0
    assert not win.beginner._running
    win._open_beginner()
    app.processEvents()
    win.beginner.start_practice()
    assert win.beginner._running


def test_all_courses_and_pieces_accept_midi_events_and_preserve_sustain_semantics(win, app):
    import mido

    win._open_beginner()
    page = win.beginner
    for collection, items in enumerate((LESSONS, PIECES)):
        page.collection.setCurrentIndex(collection)
        for index, lesson in enumerate(items):
            page.lesson_picker.setCurrentIndex(index)
            page.start_practice()
            for step in lesson.steps:
                for note in sorted(step.notes):
                    win.controller._receive(mido.Message("note_on", note=note, velocity=70))
                assert page.follower.matched
                win.controller._receive(mido.Message("control_change", control=64, value=127))
                for note in sorted(step.notes):
                    win.controller._receive(mido.Message("note_on", note=note, velocity=0))
                win.controller._receive(mido.Message("control_change", control=64, value=0))
            assert page.follower.finished
    assert completed_lessons(win.database) == {lesson.id for lesson in LESSONS + PIECES}
    rows = win.database.connection.execute("SELECT correct FROM attempts").fetchall()
    assert len(rows) == 36 and all(row[0] for row in rows)
    page.resume_next()
    assert page.collection.currentIndex() == 0 and page.lesson is LESSONS[-1]


def test_chord_target_precedes_input_and_corrected_chord_is_confirmed_automatically(win, app):
    win.navigation.setCurrentRow(1)
    app.processEvents()
    page = win.trainer
    page.trainer.current_chord = parse_chord("C")
    page._show_question()
    assert page.chord.text() == "C" and page.expected.text() == "C E G"
    assert page.keyboard.expected_pitch_classes == frozenset({0, 4, 7})
    assert not hasattr(page, "check_button")
    win.controller.demo_note(60, True)
    QTest.qWait(360)
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
    win.controller.demo_note(63, True)
    win.controller.demo_note(67, True)
    QTest.qWait(360)
    assert page.trainer.last_evaluation is None  # Wait, don't grade an unfinished/wrong chord.
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
    win.controller.demo_note(63, False)
    win.controller.demo_note(64, True)
    QTest.qWait(360)
    assert page.trainer.last_evaluation.correct is True
    rows = win.database.connection.execute("SELECT * FROM attempts").fetchall()
    assert len(rows) == 1 and not rows[0]["correct"]  # Correction isn't perfect fluency.
    assert page.trainer.wrong_count == 1
    chord = page.trainer.current_chord
    QTest.qWait(600)
    assert page.trainer.current_chord is chord  # Held keys never become the next answer.
    for note in tuple(win.controller.pressed_notes):
        win.controller.demo_note(note, False)
    QTest.qWait(600)
    assert page.trainer.current_chord is not chord
    assert page.expected.text() != "—"
    assert len(win.database.connection.execute("SELECT * FROM attempts").fetchall()) == 1


def test_chord_stability_timer_cancels_on_release_and_hidden_pages(win, app):
    win.navigation.setCurrentRow(1)
    app.processEvents()
    page = win.trainer
    page.trainer.current_chord = parse_chord("C")
    page._show_question()
    for note in (60, 64, 67):
        win.controller.demo_note(note, True)
    win.controller.demo_note(67, False)
    QTest.qWait(360)
    assert page.trainer.last_evaluation is None
    win.controller.demo_note(67, True)
    win.navigation.setCurrentRow(0)
    QTest.qWait(360)
    assert page.trainer.last_evaluation is None
    win.navigation.setCurrentRow(1)
    app.processEvents()
    QTest.qWait(360)
    assert page.trainer.last_evaluation is None  # Old held notes aren't a new answer.
    for note in (60, 64, 67):
        win.controller.demo_note(note, False)
    for note in (60, 64, 67):
        win.controller.demo_note(note, True)
    QTest.qWait(360)
    assert page.trainer.last_evaluation.correct


def test_long_scores_page_with_current_note_without_squeezing_the_whole_piece(win, app):
    win._open_beginner()
    page = win.beginner
    page.collection.setCurrentIndex(1)
    page.lesson_picker.setCurrentIndex(0)
    assert page.lesson.id == "song_twinkle"
    assert page.score.page_count == 3
    x = page.score.step_x(0)
    page.next_line.click()
    assert page.score.page == 1
    page.start_practice()
    assert page.score.page == 0
    for step in page.lesson.steps[:14]:
        for note in step.notes:
            win.controller.demo_note(note, True)
        for note in step.notes:
            win.controller.demo_note(note, False)
    assert page.score.page == 1
    assert page.score.step_x(14) == x
    page.lesson_picker.setCurrentIndex(2)
    assert page.score.bars_per_page == 2  # Eighth notes get more horizontal space.
    page.score.grab()  # Exercise flags, dots and page painting.


def test_course_progress_and_slow_mastery_survive_reopening(tmp_path):
    path = tmp_path / "course.db"
    db = Database(path)
    session_id = db.start_session()
    for _ in range(10):
        db.record_attempt(session_id=session_id, trainer_type="beginner_course", skill="score_playing",
                          question="find_c", expected="", played="", correct=True, response_time_ms=90_000)
    # Simulate a derived label made under the old speed-sensitive rules.
    db.connection.execute("UPDATE mastery SET status='Learning'")
    db.connection.commit()
    db.close()
    db = Database(path)
    assert next_lesson_index(db) == 1
    assert db.connection.execute("SELECT status FROM mastery").fetchone()[0] == "Mastered"
    assert db.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 10
    db.close()
