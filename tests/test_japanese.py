import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from practising_piano_easily.storage import Database
from practising_piano_easily.trainers.beginner_course import LESSONS, PIECES
from practising_piano_easily.tutorial import load_lessons
from practising_piano_easily.ui.i18n import ZH, language, tr
from practising_piano_easily.ui.ja import JA
from practising_piano_easily.ui.ja_lessons import COURSES
from practising_piano_easily.ui.main_window import MainWindow
from practising_piano_easily.midi.controller import MidiController


def test_japanese_covers_ui_and_all_authored_lessons():
    assert not set(ZH) - set(JA)
    assert set(COURSES) == {item.id for item in LESSONS + PIECES}
    for lesson in LESSONS + PIECES:
        assert lesson.title in JA and lesson.instructions in JA
    for lesson in load_lessons():
        for quiz in lesson.quizzes:
            assert quiz.question in JA and quiz.explanation in JA
    assert [item.id for item in load_lessons("ja")] == [item.id for item in load_lessons()]


def test_japanese_keeps_music_spelling_and_opaque_paths():
    previous = language.code
    try:
        language.set_language("ja")
        assert tr("Home") == "ホーム"
        assert tr("C major") == "C 長調"
        assert tr("F# minor") == "F# 短調"
        assert tr("Cmaj7/B") == "Cmaj7/B"
        assert tr("Saved to:\nC:/Music/Progress/major.mid") == "保存先：\nC:/Music/Progress/major.mid"
        assert tr("MIDI unavailable: Driver says 'Major'") == "MIDI を利用できません： Driver says 'Major'"
    finally:
        language.set_language(previous)


def test_switch_to_japanese_preserves_practice_and_tutorial_answers(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MidiController, "refresh_devices", lambda self: None)
    import sounddevice
    monkeypatch.setattr(sounddevice, "query_devices", lambda: [])
    database = Database(tmp_path / "japanese.db")
    win = MainWindow(database)
    win._skip_summary = True
    assert win.windowTitle() == "practising piano easily"
    question = win.trainer.trainer.current_chord
    win.tutorial.choices.setCurrentIndex(win.tutorial.lesson.quizzes[0].answer + 1)
    choice = win.tutorial.choices.currentIndex()
    try:
        win.language_selector.setCurrentIndex(win.language_selector.findData("ja"))
        app.processEvents()
        assert win.navigation.item(0).text() == "ホーム"
        assert database.get_setting("language") == "ja"
        assert win.settings.language.currentData() == "ja"
        assert win.trainer.trainer.current_chord is question
        assert win.tutorial.choices.currentIndex() == choice
        assert "コード" in win.tutorial.reader.toPlainText()
        assert win.beginner.lesson.title in JA
        assert "中央の C" in win.beginner.instructions.text()
        assert JA[LESSONS[0].title] in win.falling.source_picker.itemText(0)
        assert JA[LESSONS[0].title] in win.score_practice.source_picker.itemText(0)
        assert win.score_practice.practice.title.text() == JA[LESSONS[0].title]
        assert "小節：" in win.score_practice.practice.target.text()
    finally:
        win.close()
        language.set_language("zh_CN")
