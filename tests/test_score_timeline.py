import mido
import pytest

from practising_piano_easily.analysis.falling_score import load_falling_midi
from practising_piano_easily.analysis.score_harmony import harmony_at, harmony_names
from practising_piano_easily.trainers.falling_notes import FallingNote, FallingScore
from practising_piano_easily.trainers.score_timeline import ScoreTimeline


def test_tempo_and_signature_changes_keep_exact_note_and_measure_coordinates(tmp_path):
    midi = mido.MidiFile(ticks_per_beat=480)
    midi.tracks.append(mido.MidiTrack([
        mido.MetaMessage("set_tempo", tempo=500_000),
        mido.MetaMessage("time_signature", numerator=7, denominator=8),
        mido.MetaMessage("set_tempo", tempo=1_000_000, time=960),
        mido.MetaMessage("time_signature", numerator=3, denominator=4, time=2400)]))
    midi.tracks.append(mido.MidiTrack([mido.Message("note_on", note=61, velocity=80),
                                     mido.Message("note_off", note=61, time=5760)]))
    path = tmp_path / "meter.mid"
    midi.save(path)
    score, _ = load_falling_midi(path)
    timeline = score.timeline
    assert [(bar.start_beat, bar.end_beat, bar.numerator, bar.denominator) for bar in timeline.measures] == [
        (0, 3.5, 7, 8), (3.5, 7, 7, 8), (7, 10, 3, 4), (10, 13, 3, 4)]
    assert score.duration == 11
    for beat in (0, 1, 2, 3.5, 7, 9, 12):
        assert timeline.beat_at(timeline.seconds_at(beat)) == pytest.approx(beat)
    assert timeline.measure_index(timeline.seconds_at(7)) == 2
    assert timeline.measure_index(timeline.seconds_at(12)) == 3
    assert timeline.measure_index(-10) == 0


def test_partial_signature_change_and_pathological_timeline_limits():
    timeline = ScoreTimeline(((0, 0, .5),), ((0, 4, 4), (5, 3, 4)), 9)
    assert [(bar.start_beat, bar.end_beat) for bar in timeline.measures] == [(0, 4), (4, 5), (5, 8), (8, 11)]
    with pytest.raises(ValueError):
        ScoreTimeline(((0, 0, 0),), ((0, 4, 4),), 4)
    with pytest.raises(ValueError):
        ScoreTimeline(((0, 0, .5),), ((0, 4, 4),), 100_001)
    with pytest.raises(ValueError):
        _ = ScoreTimeline(((0, 0, .5),), ((0, 1, 128),), 1000).measures


def test_harmony_handles_inversions_extensions_and_ambiguity_without_forcing_names():
    assert harmony_names((48, 60, 64, 67)) == ("C",)
    assert harmony_names((52, 60, 64, 67)) == ("C/E",)
    assert "Cadd9" in harmony_names((48, 60, 62, 64, 67))
    assert set(harmony_names((48, 60, 64, 67, 69))) >= {"C6", "Am7/C"}
    assert harmony_names((60, 64)) == ()
    assert harmony_names(tuple(range(60, 72))) == ()


def test_harmony_groups_arpeggios_within_a_beat_but_excludes_future_beats_and_drums():
    timeline = ScoreTimeline(((0, 0, .5),), ((0, 4, 4),), 8)
    score = FallingScore((FallingNote(60, 0, .1), FallingNote(64, .15, .25), FallingNote(67, .3, .4),
                          FallingNote(61, .5, .9)), timeline)
    assert harmony_at(score, .1) == (("C",), (60, 64, 67))
    assert harmony_at(score, .5) == ((), (61,))
    assert harmony_at(score, 2) == ((), ())
