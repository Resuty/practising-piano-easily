import sqlite3

from practising_piano_easily.storage import Database
from practising_piano_easily.trainers.beginner_course import LESSONS
from practising_piano_easily.ui.i18n import language
from test_falling_piano import app, win, downloaded_fixture, make_midi


def test_each_workspace_restores_its_own_notation_settings_after_database_reopen(win, tmp_path):
    path = tmp_path / "notation.db"
    first = type(win)(Database(path))
    first._skip_summary = True
    falling, reading = first.falling.notation_controls, first.online_library.practice.notation_controls
    falling.zoom.setValue(140)
    falling.bars.setCurrentIndex(2)
    reading.zoom.setValue(80)
    reading.bars.setCurrentIndex(6)
    first.online_library.practice.loop_current.setChecked(True)
    first.close()
    second = type(win)(Database(path))
    second._skip_summary = True
    try:
        assert second.falling.notation_controls.values() == (140, 2)
        assert second.online_library.practice.notation_controls.values() == (80, 6)
        assert second.online_library.practice.loop_current.isChecked()
        assert second.falling.midi_staff.zoom_percent == 140
        assert second.online_library.practice.midi_staff.full_score
        assert not second.falling.session.running and not second.online_library.practice._running
        language.set_language("en")
        assert second.falling.notation_controls.bars.itemText(0) == "Automatic"
        language.set_language("zh_CN")
        assert second.falling.notation_controls.bars.itemText(0) == "自动"
    finally:
        second.close()


def test_bad_saved_notation_settings_use_safe_defaults_without_rewriting_them(win, tmp_path):
    path = tmp_path / "invalid-notation.db"
    database = Database(path)
    database.set_settings({"falling_notation_zoom": "0", "falling_notation_bars": "999",
                           "reading_notation_zoom": "not-a-number", "reading_notation_bars": "-2"})
    window = type(win)(database)
    window._skip_summary = True
    try:
        assert window.falling.notation_controls.values() == (100, 0)
        assert window.online_library.practice.notation_controls.values() == (100, 0)
        assert database.get_setting("falling_notation_zoom") == "0"
    finally:
        window.close()


def test_failed_notation_save_keeps_choices_and_retries_when_leaving(win, monkeypatch):
    controls = win.falling.notation_controls
    save = win.database.set_settings
    monkeypatch.setattr(win.database, "set_settings", lambda *_: (_ for _ in ()).throw(sqlite3.OperationalError("locked")))
    controls.zoom.setValue(150)
    controls.bars.setCurrentIndex(3)
    assert controls.values() == (150, 3) and controls.notation.zoom_percent == 150
    assert controls._saved_options == (100, 0) and "未能保存" in controls.warning.text()
    monkeypatch.setattr(win.database, "set_settings", save)
    win.navigation.setCurrentRow(14)
    win.navigation.setCurrentRow(0)
    assert win.database.get_setting("falling_notation_zoom") == "150"
    assert win.database.get_setting("falling_notation_bars") == "3"
    assert controls._saved_options == (150, 3)


def test_layout_controls_do_not_pause_reset_or_grade_an_active_falling_passage(win):
    win._open_falling_lesson(LESSONS[5])
    page = win.falling
    page.start()
    page.timer.stop()
    page.session.position = 0
    win.controller.demo_note(60, True)
    engine, position, hits = page.session, page.session.position, set(page.session.follower.hits)
    page.notation_controls.zoom.setValue(130)
    page.notation_controls.bars.setCurrentIndex(2)
    assert page.session is engine and page.session.running and page.session.position == position
    assert page.session.follower.hits == hits == {60}
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
    win.controller.demo_note(60, False)


def test_full_reading_view_can_switch_pdf_and_change_layout_without_losing_follow_progress(win, tmp_path):
    source = downloaded_fixture(tmp_path, "complete-score")
    make_midi(tmp_path / "score.mid")
    page = win.online_library.practice
    page.open_score(source, tmp_path)
    assert page.score_views.currentWidget() is page.pdf and not page.notation_controls.isEnabled()
    page.score_mode.setCurrentIndex(0)
    assert page.score_views.currentWidget() is page.midi_staff and page.midi_staff.full_score
    assert page.notation_controls.isEnabled()
    win._open_score_practice()
    page.start_practice()
    follower = page.follower
    page.notation_controls.zoom.setValue(150)
    page.notation_controls.bars.setCurrentIndex(1)
    page.score_mode.setCurrentIndex(1)
    page.score_mode.setCurrentIndex(0)
    assert page.follower is follower and page._running and page.follower.index == 0
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
    page.open_score(source, tmp_path)  # Opening a new score must not reuse the old follower while changing views.
    assert page.follower is None and not page._running
