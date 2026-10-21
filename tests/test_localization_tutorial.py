import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from practising_piano_easily.core import parse_chord
from practising_piano_easily.storage import Database
from practising_piano_easily.tutorial import load_lessons
from practising_piano_easily.ui.i18n import language, tr
from practising_piano_easily.ui.main_window import MainWindow
from practising_piano_easily.midi.controller import MidiController


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, monkeypatch, tmp_path):
    monkeypatch.setattr(MidiController, "refresh_devices", lambda self: None)
    import sounddevice
    monkeypatch.setattr(sounddevice, "query_devices", lambda: [])
    win = MainWindow(Database(tmp_path / "practice.db"))
    win._skip_summary = True
    win.show()
    app.processEvents()
    yield win
    win.close()
    app.processEvents()


def test_language_switch_keeps_questions_answers_and_user_edits(window):
    win = window
    chord = win.trainer.trainer.current_chord
    theory = win.theory_practice.question
    ear = win.ear_training.question
    win.voice_leading.input.setPlainText("60 64 67\n59 62 67")
    win.composition.table.item(0, 0).setText("Fmaj7")
    win.harmony.widget(0).key.setCanonicalText("F major")
    win.trainer.feedback.setText("Wrong · Missing: Bb")
    for code in ("en", "zh_CN", "en", "zh_CN"):
        win.language_selector.setCurrentIndex(win.language_selector.findData(code))
        assert win.database.get_setting("language") == code
        assert win.settings.language.currentData() == code
        assert win.trainer.trainer.current_chord is chord
        assert win.theory_practice.question is theory
        assert win.ear_training.question is ear
        assert win.trainer.training_mode.canonicalText() == "Learn"
        assert win.harmony.widget(0).key.canonicalText() == "F major"
        assert win.voice_leading.input.toPlainText() == "60 64 67\n59 62 67"
        assert win.composition.table.item(0, 0).text() == "Fmaj7"
    assert win.navigation.item(0).text() == "首页"
    assert win.trainer.feedback.text() == "错误 · 缺少音： Bb"
    win.harmony.widget(0)._analyze()
    assert "F 大调" in win.harmony.widget(0).output.toPlainText()
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0


def test_chinese_answer_selection_records_canonical_values(window):
    page = window.ear_training
    page.exercise.setCanonicalText("Major vs minor")
    question = page.question
    page.answer.setCanonicalText(question.answer)
    assert page.answer.currentText() != question.answer
    page._submit()
    row = window.database.connection.execute("SELECT * FROM attempts").fetchone()
    assert row["correct"] == 1
    assert row["played"] == question.answer
    assert row["skill"] == "major_vs_minor"


def test_tutorial_quiz_read_status_and_example_handoff(window, app):
    page = window.tutorial
    window.navigation.setCurrentRow(11)
    page.chapter.setCurrentIndex(4)
    app.processEvents()
    assert window.database.get_setting("tutorial_chapter") == "inversions"
    assert page.choices.currentIndex() == -1
    page._submit()
    assert window.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
    quiz = page.lesson.quizzes[0]
    page.choices.setCurrentIndex(quiz.answer)
    page._submit()
    page._submit()
    rows = window.database.connection.execute("SELECT * FROM attempts").fetchall()
    assert len(rows) == 1 and rows[0]["correct"] == 1
    assert rows[0]["question"] == "tutorial:inversions:1"
    assert tr(quiz.explanation) in page.feedback.text()
    page.read.setChecked(True)
    assert window.database.get_setting("tutorial_read_inversions") == "1"
    window._tutorial_practice(page.current_example)
    assert window.pages.currentWidget() is window.trainer
    assert window.trainer.trainer.current_chord.symbol == "C/E"
    assert window.trainer.trainer.training_mode == "Learn"
    assert window.trainer.trainer.current_chord.bass.pitch_class == 4


def test_language_and_reading_resume_after_restart(window, app, monkeypatch):
    path = window.database.path
    window.language_selector.setCurrentIndex(1)
    window.tutorial.chapter.setCurrentIndex(6)
    window.tutorial.read.setChecked(True)
    window.close()
    resumed = MainWindow(Database(path))
    resumed._skip_summary = True
    try:
        assert language.code == "en"
        assert resumed.navigation.item(0).text() == "Home"
        assert resumed.tutorial.lesson.id == "diatonic"
        assert resumed.tutorial.read.isChecked()
    finally:
        resumed.close()


def test_all_tutorial_examples_match_the_core():
    lessons = load_lessons()
    assert len(lessons) == 10
    assert len({lesson.id for lesson in lessons}) == len(lessons)
    assert sum(len(lesson.quizzes) for lesson in lessons) == 19
    for lesson in lessons:
        assert len(lesson.markdown) > 500
        for quiz in lesson.quizzes:
            assert 0 <= quiz.answer < len(quiz.options) and quiz.explanation
        for example in lesson.examples:
            chord = parse_chord(example.symbol)
            assert frozenset(note % 12 for note in example.notes) == chord.pitch_classes
            assert min(example.notes) % 12 == (chord.bass or chord.root).pitch_class


def test_every_chapter_renders_and_audio_uses_the_selected_example(window, monkeypatch):
    import numpy as np
    import sounddevice

    captured = []
    monkeypatch.setattr(sounddevice, "play", lambda samples, rate, device: captured.append((samples, rate)))
    page = window.tutorial
    for index, lesson in enumerate(page.lessons):
        page.chapter.setCurrentIndex(index)
        assert lesson.title in page.reader.toPlainText()
        assert page.example.count() == len(lesson.examples)
        assert page.quiz.count() == len(lesson.quizzes)
    page.example.setCurrentIndex(1)
    page._play()
    expected = page.synth.render_sequence((page.current_example.notes,), volume=0.25)
    assert np.array_equal(captured[0][0], expected)
    assert captured[0][1] == page.synth.sample_rate


def test_switch_language_does_not_erase_quiz_feedback(window):
    page = window.tutorial
    quiz = page.lesson.quizzes[0]
    page.choices.setCurrentIndex((quiz.answer + 1) % len(quiz.options))
    page._submit()
    assert "错误" in page.feedback.text()
    window.language_selector.setCurrentIndex(1)
    assert "Wrong" in page.feedback.text()
    assert tr(quiz.explanation) in page.feedback.text()
    assert not page.submit.isEnabled()
    assert window.database.connection.execute("SELECT correct FROM attempts").fetchone()[0] == 0


def test_musical_symbols_and_paths_are_not_translated():
    language.set_language("zh_CN")
    symbols = "C Cm Cmaj7 C7 Cdim7 G7#9 F# Bb Bbb C/E V7/ii"
    assert tr(symbols) == symbols
    assert tr("Saved to:\nC:/Music/Progress/major.mid") == "已保存到：\nC:/Music/Progress/major.mid"
