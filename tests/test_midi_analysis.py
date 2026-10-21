import mido
import pytest

from practising_piano_easily.analysis import chord_candidates, key_candidates, load_midi, note_windows


def sample_midi():
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    for note in (60, 64, 67, 69):
        track.append(mido.Message("note_on", note=note, velocity=90, time=0))
    for index, note in enumerate((60, 64, 67, 69)):
        track.append(mido.Message("note_off", note=note, velocity=0, time=480 if index == 0 else 0))
    return midi


def test_midi_summary_windows_and_velocity_zero():
    midi = sample_midi()
    summary = load_midi(midi)
    assert summary.tracks == 1
    assert summary.ticks_per_beat == 480
    assert summary.tempo_bpm == pytest.approx(120)
    assert summary.time_signature == "4/4"
    assert summary.note_range == (60, 69)
    assert note_windows(summary) == ((60, 64, 67, 69),)


def test_ambiguous_chord_candidates_are_not_forced_to_one_answer():
    candidates = chord_candidates((60, 64, 67, 69))
    symbols = [candidate.symbol for candidate in candidates]
    assert "C6" in symbols
    assert "Am7/C" in symbols
    assert next(candidate.score for candidate in candidates if candidate.symbol == "C6") == 1.0


def test_key_detection_calls_values_scores_not_probabilities():
    candidates = key_candidates({0, 2, 4, 5, 7, 9, 11})
    assert {candidate.key for candidate in candidates[:2]} == {"C major", "A minor"}
    assert candidates[0].score == candidates[1].score
    assert all(hasattr(candidate, "score") for candidate in candidates)


def test_malformed_path_is_friendly():
    with pytest.raises(ValueError, match="Malformed or unreadable MIDI file"):
        load_midi("does-not-exist.mid")
