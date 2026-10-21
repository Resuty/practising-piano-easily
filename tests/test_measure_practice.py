import json
import sqlite3

import mido
import pytest

from practising_piano_easily.trainers.falling_notes import FallingNote, FallingScore, FallingSession
from practising_piano_easily.trainers.midi_score import MidiScoreFollower
from practising_piano_easily.trainers.score_timeline import ScoreTimeline
from practising_piano_easily.ui.i18n import language
from test_falling_piano import app, win, downloaded_fixture, start_follow


def test_measure_sections_preserve_tempo_meter_leading_and_trailing_rests_and_ties():
    timeline = ScoreTimeline(((0, 0, .5), (4, 2, 1)), ((0, 4, 4), (8, 3, 4)), 14)
    score = FallingScore((FallingNote(60, .5, 1), FallingNote(62, 1.5, 3),
                          FallingNote(64, 6, 8), FallingNote(67, 9, 12)), timeline)
    part, offset = score.measure_section(1, 1)
    assert offset == 0 and part.duration == 2
    assert [(n.pitch, n.start, n.end) for n in part.notes] == [(60, .5, 1), (62, 1.5, 2)]
    part, offset = score.measure_section(2, 2)
    assert offset == 2 and part.duration == 4
    assert [(n.pitch, n.start, n.end) for n in part.notes] == [(62, 0, 1)]
    part, offset = score.measure_section(3, 4)
    assert offset == 6 and part.duration == 6
    assert [(n.pitch, n.start, n.end) for n in part.notes] == [(64, 0, 2), (67, 3, 6)]
    for first, last in ((0, 2), (2, 1), (1, 5)):
        with pytest.raises(ValueError, match="bar"):
            score.measure_section(first, last)


def test_silent_measure_section_can_finish_without_fake_notes_or_practice_hits():
    timeline = ScoreTimeline(((0, 0, .5),), ((0, 4, 4),), 12)
    score = FallingScore((FallingNote(60, 0, .5), FallingNote(62, 4, 6)), timeline)
    part, offset = score.measure_section(2, 2)
    assert offset == 2 and part.duration == 2 and not part.notes and not part.visible_notes(0, 4)
    session = FallingSession(part)
    session.running = True
    assert session.follower.finished and session.advance(5) == "finished"
    assert session.follower.mistakes == 0
    with pytest.raises(ValueError):
        MidiScoreFollower(())
    for span in (0, -1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            FallingScore((), span=span)


@pytest.fixture
def bar_page(win, tmp_path, monkeypatch):
    source = downloaded_fixture(tmp_path, "ten-bars")
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack([mido.MetaMessage("set_tempo", tempo=500_000)])
    previous = 0
    for bar in range(10):
        tick = bar * 1920
        track.append(mido.Message("note_on", note=60 + bar % 5, velocity=80, time=tick - previous))
        length = 1920 if bar == 9 else 240
        track.append(mido.Message("note_off", note=60 + bar % 5, time=length))
        previous = tick + length
    midi.tracks.append(track)
    midi.save(tmp_path / "score.mid")
    page = win.falling
    page.add_downloaded((source, tmp_path))
    page.source_picker.setCurrentIndex(page.source_picker.findData("mutopia:ten-bars"))
    page.demo_before.setChecked(True)  # These regression cases explicitly exercise the optional demo workflow.
    win.navigation.setCurrentRow(14)
    clock = [100.]
    monkeypatch.setattr("practising_piano_easily.ui.falling_piano_page.time.monotonic", lambda: clock[0])
    return page, clock


def finish_passage(page, clock):
    start_follow(page)
    page.timer.stop()
    for group in page.session.score.groups:
        clock[0] += max(0, group.time - page.session.position) / page.session.speed
        page._tick()
        for note in sorted(group.notes):
            page.controller.demo_note(note, True)
            page.controller.demo_note(note, False)
    clock[0] += (page.session.score.duration - page.session.position) / page.session.speed + .001
    page._tick()
    page.next_timer.stop()  # Drive idle transitions deterministically through their clock seam.
    assert page.session.finished


def test_default_is_four_bars_and_custom_ranges_remain_valid(bar_page):
    page, _ = bar_page
    assert page.mode.currentIndex() == 0 and page.range_mode.currentIndex() == 0
    assert not page.loop_current.isChecked() and page.loop_current.isEnabled() and page.next_button.isEnabled()
    assert (page.first.value(), page.last.value()) == (1, 4)
    assert page.first.maximum() == page.last.maximum() == 10
    assert page.session.score.duration == 8 and len(page.session.score.groups) == 4
    assert "小节" in page.first_label.text()
    page.first.setValue(5)
    assert (page.first.value(), page.last.value()) == (5, 4)
    assert page.session is None and not page.play_button.isEnabled() and "互不联动" in page.feedback.text()
    page.last.setValue(8)
    assert (page.first.value(), page.last.value()) == (5, 8) and page._offset == 8
    page.last.setValue(6)
    assert page.session.score.duration == 4
    page.first.setValue(9)
    assert page.last.value() == 6 and page.session is None
    page.last.setValue(2)
    assert page.first.value() == 9 and page.session is None
    page.first.setValue(1)
    assert page.last.value() == 2 and page.session is not None
    language.set_language("en")
    assert page.first_label.text() == "From bar:"
    language.set_language("zh_CN")


@pytest.mark.parametrize("speed", [25, 100, 200])
def test_four_bar_chain_uses_two_real_seconds_and_stops_at_song_end(bar_page, win, speed):
    page, clock = bar_page
    page.speed.setValue(speed)
    for first, last in ((1, 4), (5, 8), (9, 10)):
        assert (page.first.value(), page.last.value()) == (first, last)
        finish_passage(page, clock)
        completed, elapsed = page.session, page.session.elapsed
        rows = win.database.connection.execute("SELECT * FROM attempts").fetchall()
        assert len(rows) == {1: 1, 5: 2, 9: 3}[first]
        metadata = json.loads(rows[-1]["metadata_json"])
        assert metadata["first_bar"] == first and metadata["last_bar"] == last and metadata["range_unit"] == "bar"
        assert page.midi_staff.current_measure == last - 1
        assert page._next_deadline == clock[0] + 2
        if last == 10:
            clock[0] = page._next_deadline
            page._next_tick()
            assert page._next_deadline is None and not page.resume_notice.isVisible()
            break
        deadline = page._next_deadline
        clock[0] = deadline - .001
        page._next_tick()
        assert page.session is completed and page.session.elapsed == elapsed
        clock[0] = deadline
        page._next_tick()
        page.timer.stop()
        assert page.session is not completed and page.session.running and page.session.position == 0
        assert page._section_demo and page.session.preview  # Every following block demonstrates before it grades.
        assert page.session.follower.index == 0 and page.session.follower.mistakes == 0
    clock[0] += 100
    page._next_tick()
    assert page.session is completed and page.session.finished


def test_key_input_selects_repeat_and_held_keys_wait_for_release(bar_page):
    page, clock = bar_page
    finish_passage(page, clock)
    completed = page.session
    deadline = page._next_deadline
    clock[0] += 1.5
    page.controller.demo_note(72, True)
    clock[0] += 10
    page._next_tick()
    assert page.session is completed and page._next_deadline == deadline and page._repeat_requested
    page.controller.demo_note(72, False)
    page.timer.stop()
    assert page.first.value() == 1 and page.session.running and page.session.follower.index == 0


@pytest.mark.parametrize("cancel", ["pause", "navigate", "source", "range"])
def test_idle_auto_advance_is_cancelled_by_explicit_changes(bar_page, win, cancel):
    page, clock = bar_page
    finish_passage(page, clock)
    assert page._next_deadline is not None
    if cancel == "pause":
        page.pause_button.click()
    elif cancel == "navigate":
        win.navigation.setCurrentRow(0)
    elif cancel == "source":
        page.source_picker.setCurrentIndex(0)
    else:
        page.first.setValue(2)
    assert page._next_deadline is None and not page.next_timer.isActive()
    assert not page.resume_notice.isVisible()
    session = page.session
    clock[0] += 100
    page._next_tick()
    assert page.session is session and not session.running


def test_demo_returns_to_chosen_bar_practice_after_countdown_and_no_demo_grade(bar_page, win, monkeypatch):
    page, clock = bar_page
    page.first.setValue(5)
    page.last.setValue(7)
    monkeypatch.setattr(page.demo_player, "start", lambda *args: None)
    page.demonstrate()
    page.timer.stop()
    demo = page.session
    clock[0] += demo.score.duration + 3
    page._tick()
    assert demo.finished and page.session is not demo
    assert page.mode.currentIndex() == 0 and page.range_mode.currentIndex() == 0
    assert (page.first.value(), page.last.value()) == (5, 7)
    assert page._section_demo and page.session.running
    page.timer.stop()
    clock[0] += page.session.score.duration
    page._tick()
    assert page.session.position == 0 and page.resume_timer.isActive()
    page.resume_timer.stop()
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
    page.controller.demo_note(64, True)
    clock[0] += 3
    page._resume_tick()
    assert not page.session.running
    page.controller.demo_note(64, False)
    page._resume_tick()
    page.timer.stop()
    assert page.session.running and page.session.follower.index == 0 and page.session.elapsed == 0


def test_failed_grade_save_blocks_advance_until_successful_retry(bar_page, win, monkeypatch):
    from practising_piano_easily.ui.localized_widgets import QMessageBox
    page, clock = bar_page
    record = win.database.record_attempt
    monkeypatch.setattr(win.database, "record_attempt", lambda **kwargs: (_ for _ in ()).throw(sqlite3.OperationalError("locked")))
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: None)
    finish_passage(page, clock)
    assert page.save_button.isVisible() and page._next_deadline is None
    monkeypatch.setattr(win.database, "record_attempt", record)
    page.save_button.click()
    page.next_timer.stop()
    assert page._saved and page._next_deadline == clock[0] + 2
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 1


def test_rest_only_bars_do_not_add_mastery_or_stall_and_preview_does_not_advance(bar_page, win):
    page, clock = bar_page
    original = page._all_score
    page._all_score = FallingScore(tuple(n for n in original.notes if n.start < 8 or n.start >= 16), original.timeline)
    page._track_changed()
    page._set_bar_range(5, 8)
    assert not page.session.score.notes and "休止" in page.feedback.text()
    finish_passage(page, clock)
    assert page._next_deadline is not None
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
    clock[0] += 3
    page._next_tick()
    page.timer.stop()
    assert (page.first.value(), page.last.value()) == (9, 10) and page.session.running
    page.pause()
    page.mode.setCurrentIndex(1)
    page.start()
    page.timer.stop()
    clock[0] += 100
    page._tick()
    assert page.mode.currentIndex() == 1 and page.session.finished and page._next_deadline is None


def test_segment_demo_ignores_input_lights_keys_then_countdown_starts_fresh_follow(bar_page, win):
    page, clock = bar_page
    page.start()
    page.timer.stop()
    assert page._section_demo and page.session.preview and not page._section_demonstrated
    assert "本段演示" in page.feedback.text()
    clock[0] += 3.1
    page._tick()
    assert page.keyboard.pressed == frozenset((60,))
    page.controller.demo_note(61, True)
    page.controller.demo_note(60, True)
    assert page.session.follower.index == 0 and page.session.follower.mistakes == 0
    assert page.keyboard.pressed == frozenset((60,))
    clock[0] += 8
    page._tick()
    page.resume_timer.stop()
    assert not page._section_demo and page._section_demonstrated and not page.session.preview
    assert not page.session.running and page.session.position == 0 and page.session.elapsed == 0
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
    clock[0] += 3
    page._resume_tick()
    assert not page.session.running  # Keys held during demonstration do not become practice answers.
    page.controller.demo_note(61, False)
    page.controller.demo_note(60, False)
    page._resume_tick()
    page.timer.stop()
    assert page.session.running and not page.session.preview and page.session.follower.index == 0
    page.controller.demo_note(60, True)
    page.controller.demo_note(60, False)
    assert page.session.follower.index == 1


def test_pausing_or_tutorial_return_resumes_the_same_demo_and_restarting_replays_it(bar_page, win):
    page, clock = bar_page
    page.start()
    page.timer.stop()
    clock[0] += 3.1
    page._tick()
    demo, position = page.session, page.session.position
    win._open_chord_help("C")
    win._escape()
    page.resume_timer.stop()
    clock[0] += 3
    page._resume_tick()
    page.timer.stop()
    assert page._section_demo and page.session is demo and page.session.position == position
    clock[0] += 1
    page._tick()
    assert page.session.position == pytest.approx(position + 1)
    page.pause()
    page.start()
    page.timer.stop()
    assert page.session is demo and page._section_demo
    page.restart()
    page.timer.stop()
    assert page.session is not demo and page._section_demo and page.session.position == -3


def test_loop_repeats_demo_then_follow_for_same_bars_and_records_each_follow_once(bar_page, win):
    page, clock = bar_page
    page.loop_current.setChecked(True)
    for repetition in range(1, 4):
        finish_passage(page, clock)
        completed = page.session
        assert (page.first.value(), page.last.value()) == (1, 4)
        assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == repetition
        assert "重练本段" in page.feedback.text() and "重复小节" in page.resume_notice.text()
        page._save_result()
        assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == repetition
        clock[0] = page._next_deadline
        page._next_tick()
        page.timer.stop()
        assert page.session is not completed and page._section_demo and page.session.preview
        assert (page.first.value(), page.last.value()) == (1, 4)
        assert page.session.follower.index == 0 and page.session.follower.mistakes == 0
        assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == repetition


def test_manual_next_cancels_loop_wait_and_demonstrates_following_bars(bar_page, win):
    page, clock = bar_page
    page.loop_current.setChecked(True)
    finish_passage(page, clock)
    old_deadline = page._next_deadline
    page.next_button.click()
    page.timer.stop()
    assert (page.first.value(), page.last.value()) == (5, 8)
    assert page.loop_current.isChecked() and page._section_demo and page.session.running
    assert page._next_deadline is None and not page.next_timer.isActive()
    moved = page.session
    clock[0] = old_deadline + 100
    page._next_tick()
    assert page.session is moved and page.first.value() == 5
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 1


def test_manual_next_during_demo_closes_owned_audio_without_marking_completion(bar_page, win, monkeypatch):
    import sounddevice
    from test_score_demo import FakeStream
    page, _ = bar_page
    monkeypatch.setattr(sounddevice, "OutputStream", lambda **kwargs: FakeStream(**kwargs))
    page.loop_current.setChecked(True)
    page.start()
    page.timer.stop()
    audio, demo = page.demo_player.stream, page.session
    assert audio.active
    page.next_button.click()
    page.timer.stop()
    assert audio.closed and not demo.running
    assert page._section_demo and page.session.running and page.first.value() == 5
    assert page.demo_player.stream is not audio and page.demo_player.stream.active
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0


def test_turning_loop_on_or_off_during_wait_retargets_after_two_fresh_seconds(bar_page):
    page, clock = bar_page
    finish_passage(page, clock)
    clock[0] += 1
    page.loop_current.setChecked(True)
    page.next_timer.stop()
    assert page._next_deadline == clock[0] + 2 and "重复小节" in page.resume_notice.text()
    clock[0] += 1
    page.loop_current.setChecked(False)
    page.next_timer.stop()
    assert page._next_deadline == clock[0] + 2 and "5–8" in page.resume_notice.text()
    clock[0] += 2
    page._next_tick()
    page.timer.stop()
    assert page.first.value() == 5 and page._section_demo and not page.loop_current.isChecked()


def test_final_short_passage_can_loop_and_turning_loop_off_stops_at_song_end(bar_page):
    page, clock = bar_page
    page._set_bar_range(9, 10)
    page.loop_current.setChecked(True)
    finish_passage(page, clock)
    assert not page.next_button.isEnabled() and page._next_deadline is not None
    clock[0] += 3
    page._next_tick()
    page.timer.stop()
    assert (page.first.value(), page.last.value()) == (9, 10) and page._section_demo
    finish_passage(page, clock)
    page.loop_current.setChecked(False)
    clock[0] += 2
    page._next_tick()
    assert page._next_deadline is None and not page.next_timer.isActive()
    assert not page.pause_button.isEnabled() and not page.resume_notice.isVisible()
    assert "全曲" in page.feedback.text()


def test_loop_respects_key_input_and_pause_and_toggle_does_not_restart_paused_playback(bar_page):
    page, clock = bar_page
    page.loop_current.setChecked(True)
    finish_passage(page, clock)
    completed = page.session
    deadline = page._next_deadline
    page.controller.demo_note(72, True)
    clock[0] += 10
    page._next_tick()
    assert page.session is completed and page._next_deadline == deadline
    page.pause_button.click()
    page.controller.demo_note(72, False)
    page.loop_current.setChecked(False)
    page.loop_current.setChecked(True)
    clock[0] += 10
    page._next_tick()
    assert page.session is completed and not page.session.running and page._next_deadline is None


def test_loop_controls_do_not_apply_to_preview_or_note_groups(bar_page):
    page, _ = bar_page
    page.loop_current.setChecked(True)
    page.mode.setCurrentIndex(1)
    assert not page.loop_current.isEnabled() and not page.next_button.isEnabled()
    page.mode.setCurrentIndex(0)
    page.range_mode.setCurrentIndex(1)
    assert not page.loop_current.isEnabled() and not page.next_button.isEnabled()
    page.range_mode.setCurrentIndex(0)
    assert page.loop_current.isEnabled() and page.next_button.isEnabled() and page.loop_current.isChecked()
    language.set_language("en")
    assert page.next_button.text() == "Next passage"
    language.set_language("zh_CN")
    assert page.next_button.text() == "进入下一段"


def test_failed_save_prevents_both_loop_replay_and_manual_next_until_retry(bar_page, win, monkeypatch):
    from practising_piano_easily.ui.localized_widgets import QMessageBox
    page, clock = bar_page
    page.loop_current.setChecked(True)
    record = win.database.record_attempt
    monkeypatch.setattr(win.database, "record_attempt", lambda **kwargs: (_ for _ in ()).throw(sqlite3.OperationalError("locked")))
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: None)
    finish_passage(page, clock)
    assert page._next_deadline is None and not page.next_button.isEnabled()
    completed = page.session
    page.next_passage()
    assert page.session is completed
    monkeypatch.setattr(win.database, "record_attempt", record)
    page.save_button.click()
    page.next_timer.stop()
    assert page._saved and page._next_deadline is not None and page.next_button.isEnabled()


def test_passage_demo_defaults_off_and_start_accepts_practice_without_audio(win, monkeypatch):
    from practising_piano_easily.trainers.beginner_course import LESSONS
    win._open_falling_lesson(LESSONS[3])
    page = win.falling
    assert not page.demo_before.isChecked() and page.demo_before.isEnabled()
    monkeypatch.setattr(page.demo_player, "start", lambda *args: pytest.fail("Direct practice must not start demo audio"))
    page.start()
    page.timer.stop()
    assert page.session.running and not page.session.preview and not page._section_demo
    page.session.advance(3)
    page.controller.demo_note(60, True)
    assert page.session.follower.hits == {60}
    page.controller.demo_note(60, False)
    language.set_language("en")
    assert page.demo_before.text() == "Demonstrate before practice"
    language.set_language("zh_CN")
    assert page.demo_before.text() == "练习前先演示本段"


@pytest.mark.parametrize("loop", [False, True])
def test_demo_off_applies_to_auto_progression_loop_replay_and_manual_next(bar_page, loop, monkeypatch):
    page, clock = bar_page
    page.demo_before.setChecked(False)
    page.loop_current.setChecked(loop)
    monkeypatch.setattr(page.demo_player, "start", lambda *args: pytest.fail("No mandatory demonstration"))
    finish_passage(page, clock)
    clock[0] = page._next_deadline
    page._next_tick()
    page.timer.stop()
    assert page.first.value() == (1 if loop else 5)
    assert page.session.running and not page.session.preview and not page._section_demo
    assert page.session.follower.index == 0 and page.session.position == 0
    page.next_button.click()
    page.timer.stop()
    assert page.first.value() == (5 if loop else 9)
    assert page.session.running and not page.session.preview and not page._section_demo


@pytest.mark.parametrize("paused", [False, True])
def test_switching_demo_off_mid_demo_skips_it_and_respects_pause(bar_page, win, monkeypatch, paused):
    import sounddevice
    from test_score_demo import FakeStream
    page, clock = bar_page
    monkeypatch.setattr(sounddevice, "OutputStream", lambda **kwargs: FakeStream(**kwargs))
    page.start()
    page.timer.stop()
    audio, demo = page.demo_player.stream, page.session
    clock[0] += 3.1
    page._tick()
    if paused:
        page.pause()
    page.demo_before.setChecked(False)
    assert audio.closed and page.demo_player.stream is None
    assert page.session is not demo and not page.session.preview and not page._section_demo
    assert not page.session.running and page.session.position == 0
    assert page.resume_timer.isActive() is not paused
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
    if paused:
        page.start()
    else:
        page.resume_timer.stop()
        clock[0] += 3
        page._resume_tick()
    page.timer.stop()
    assert page.session.running and not page.session.preview


def test_enabling_demo_during_follow_applies_next_time_without_erasing_progress(bar_page):
    page, clock = bar_page
    page.demo_before.setChecked(False)
    page.start()
    page.timer.stop()
    clock[0] += 3
    page._tick()
    page.controller.demo_note(60, True)
    page.controller.demo_note(60, False)
    engine, position = page.session, page.session.position
    assert engine.follower.index == 1
    page.demo_before.setChecked(True)
    page.pause()
    page.start()
    page.timer.stop()
    assert page.session is engine and engine.follower.index == 1 and engine.position == position
    assert not page.session.preview and not page._section_demo
    page.next_button.click()
    page.timer.stop()
    assert page._section_demo and page.session.preview and page.first.value() == 5


def test_explicit_whole_song_demo_still_works_with_passage_demo_off(bar_page, win, monkeypatch):
    page, clock = bar_page
    page.demo_before.setChecked(False)
    played = []
    monkeypatch.setattr(page.demo_player, "start", lambda *args: played.append(args))
    page.demo_button.click()
    page.timer.stop()
    assert page.mode.currentIndex() == 2 and page.session.preview and len(played) == 1
    clock[0] += page.session.score.duration + 3
    page._tick()
    page.resume_timer.stop()
    assert page.mode.currentIndex() == 0 and not page.session.preview and not page._section_demo
    assert page._resume_deadline is not None and len(played) == 1
    clock[0] += 3
    page._resume_tick()
    page.timer.stop()
    assert page.session.running and not page.session.preview and len(played) == 1
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0


def test_held_key_blocked_start_does_not_skip_demo_enabled_before_retry(bar_page):
    page, _ = bar_page
    page.demo_before.setChecked(False)
    page.controller.demo_note(60, True)
    page.start()
    assert not page.session.running and not page._section_demonstrated
    page.demo_before.setChecked(True)
    page.controller.demo_note(60, False)
    page.start()
    page.timer.stop()
    assert page._section_demo and page.session.preview


@pytest.mark.parametrize("demo,loop", [(False, False), (True, False), (False, True), (True, True)])
def test_practice_switches_persist_across_window_and_database_reopen(win, tmp_path, demo, loop):
    from practising_piano_easily.storage import Database
    path = tmp_path / "practice-preferences.db"
    first = type(win)(Database(path))
    first._skip_summary = True
    first.falling.demo_before.setChecked(demo)
    first.falling.loop_current.setChecked(loop)
    first.close()
    second = type(win)(Database(path))
    second._skip_summary = True
    assert second.falling.demo_before.isChecked() == demo
    assert second.falling.loop_current.isChecked() == loop
    assert not second.falling.session.running and not second.falling.timer.isActive()
    second.falling.demo_before.setChecked(False)
    second.falling.loop_current.setChecked(False)
    second.close()
    database = Database(path)
    assert database.get_setting("falling_demo_before", "0") == "0"
    assert database.get_setting("falling_loop_current", "0") == "0"
    database.close()


def test_failed_switch_save_keeps_current_choices_and_retries_on_page_exit(win, monkeypatch):
    page = win.falling
    save = win.database.set_settings
    monkeypatch.setattr(win.database, "set_settings", lambda *a: (_ for _ in ()).throw(sqlite3.OperationalError("locked")))
    page.demo_before.setChecked(True)
    page.loop_current.setChecked(True)
    assert page.demo_before.isChecked() and page.loop_current.isChecked()
    assert page._saved_practice_options == (False, False) and "未能保存" in page.feedback.text()
    assert win.database.get_setting("falling_demo_before") is None
    monkeypatch.setattr(win.database, "set_settings", save)
    win.navigation.setCurrentRow(14)
    win.navigation.setCurrentRow(0)
    assert page._saved_practice_options == (True, True)
    assert win.database.get_setting("falling_demo_before") == "1"
    assert win.database.get_setting("falling_loop_current") == "1"
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0


@pytest.mark.parametrize("offset,repeat", [(1.999, True), (2.0, True), (2.001, False)])
def test_repeat_input_window_is_fixed_and_does_not_score_the_repeat_key(bar_page, win, offset, repeat):
    page, clock = bar_page
    page.demo_before.setChecked(False)
    finish_passage(page, clock)
    deadline = page._next_deadline
    clock[0] = deadline - 2 + offset
    page.controller.demo_note(72, True)
    assert page._repeat_requested == repeat and page._next_deadline == deadline
    page.controller.demo_note(72, False)
    if clock[0] < deadline:
        clock[0] = deadline
        page._next_tick()
    page.timer.stop()
    assert page.first.value() == (1 if repeat else 5)
    assert page.session.running and not page.session.preview and page.session.follower.index == 0
    assert page.session.follower.mistakes == 0
    assert win.database.connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 1


def test_final_note_release_and_pedal_do_not_request_repeat(bar_page):
    from practising_piano_easily.midi.state import MidiEvent
    page, clock = bar_page
    page.demo_before.setChecked(False)
    page.last.setValue(1)
    page.start()
    page.timer.stop()
    clock[0] += 3
    page._tick()
    page.controller.demo_note(60, True)
    clock[0] += page.session.score.duration
    page._tick()
    deadline = page._next_deadline
    assert deadline is not None and page.controller.pressed_notes == frozenset((60,))
    clock[0] += .5
    page.controller._process(MidiEvent("control_change", control=64, value=127))
    page.controller._process(MidiEvent("note_on", note=60, velocity=0))
    assert not page._repeat_requested and page._next_deadline == deadline
    clock[0] = deadline
    page._next_tick()
    page.timer.stop()
    assert page.first.value() == 2 and page.session.running and not page.session.preview


def test_repeat_input_also_replays_final_passage_with_loop_off(bar_page):
    page, clock = bar_page
    page._set_bar_range(9, 10)
    finish_passage(page, clock)
    clock[0] += 1
    page.controller.demo_note(72, True)
    page.controller.demo_note(72, False)
    clock[0] = page._next_deadline
    page._next_tick()
    page.timer.stop()
    assert (page.first.value(), page.last.value()) == (9, 10)
    assert page._section_demo and page.session.running and not page.loop_current.isChecked()


def test_repeat_request_survives_loop_switch_changes_within_decision_window(bar_page):
    page, clock = bar_page
    finish_passage(page, clock)
    page.controller.demo_note(72, True)
    page.controller.demo_note(72, False)
    page.loop_current.setChecked(True)
    page.loop_current.setChecked(False)
    assert page._repeat_requested
    clock[0] = page._next_deadline
    page._next_tick()
    page.timer.stop()
    assert page.first.value() == 1 and page._section_demo
