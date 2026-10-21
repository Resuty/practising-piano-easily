import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from practising_piano_easily.storage import Database
from practising_piano_easily.trainers.beginner_course import LESSONS, PIECES
from practising_piano_easily.tutorial import load_lessons
from practising_piano_easily.ui.en import COURSES, EN
from practising_piano_easily.ui.i18n import language, tr
from practising_piano_easily.ui.main_window import MainWindow
from practising_piano_easily.midi.controller import MidiController


def test_english_covers_all_authored_course_and_quiz_text():
    assert set(COURSES) == {item.id for item in LESSONS + PIECES}
    for lesson in LESSONS + PIECES:
        assert lesson.title in EN and lesson.instructions in EN
    for lesson in load_lessons():
        assert lesson.title in EN
        for quiz in lesson.quizzes:
            assert quiz.question in EN and quiz.explanation in EN
            for option in quiz.options:
                assert not re.search(r"[\u4e00-\u9fff]", EN.get(option, option))
    translated = load_lessons("en")
    assert len(translated) == 10
    assert [lesson.id for lesson in translated] == [lesson.id for lesson in load_lessons()]
    assert all(not re.search(r"[\u4e00-\u9fff]", lesson.markdown) for lesson in translated)
    assert all(not re.search(r"[\u4e00-\u9fff]", value) for value in EN.values())


def test_english_preserves_music_symbols_and_opaque_paths():
    previous = language.code
    try:
        language.set_language("en")
        assert tr("Cmaj7/B") == "Cmaj7/B"
        assert tr("F# minor") == "F# minor"
        assert tr(LESSONS[0].title) == COURSES["find_c"][0]
        path_message = "Saved to:\nC:/Music/" + LESSONS[0].title + ".mid"
        assert tr(path_message) == path_message
    finally:
        language.set_language(previous)


def test_switch_to_english_translates_content_without_resetting_practice(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MidiController, "refresh_devices", lambda self: None)
    import sounddevice
    monkeypatch.setattr(sounddevice, "query_devices", lambda: [])
    database = Database(tmp_path / "english.db")
    win = MainWindow(database)
    win._skip_summary = True
    question = win.trainer.trainer.current_chord
    win.tutorial.choices.setCurrentIndex(win.tutorial.lesson.quizzes[0].answer + 1)
    choice = win.tutorial.choices.currentIndex()
    try:
        win.language_selector.setCurrentIndex(win.language_selector.findData("en"))
        app.processEvents()
        assert win.navigation.item(0).text() == "Home"
        assert win.navigation.item(12).text() == "Beginner lessons / scores"
        assert database.get_setting("language") == "en"
        assert win.settings.language.currentData() == "en"
        assert win.trainer.trainer.current_chord is question
        assert win.tutorial.choices.currentIndex() == choice
        assert "Chords: connect" in win.tutorial.reader.toPlainText()
        assert "middle C" in win.beginner.instructions.text()
        assert COURSES[LESSONS[0].id][0] in win.falling.source_picker.itemText(0)
        assert win.score_practice.practice.title.text() == COURSES[LESSONS[0].id][0]
        for lesson in win.tutorial.lessons:
            win.tutorial.chapter.setCurrentIndex(win.tutorial.lessons.index(lesson))
            for index in range(len(lesson.quizzes)):
                win.tutorial.quiz.setCurrentIndex(index)
                assert not re.search(r"[\u4e00-\u9fff]", win.tutorial.question.text())
                assert all(not re.search(r"[\u4e00-\u9fff]", win.tutorial.choices.itemText(i))
                           for i in range(win.tutorial.choices.count()))
        win.language_selector.setCurrentIndex(win.language_selector.findData("ja"))
        app.processEvents()
        assert win.navigation.item(0).text() == "ホーム"
    finally:
        win.close()
        language.set_language("zh_CN")
