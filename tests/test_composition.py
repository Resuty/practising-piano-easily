from practising_piano_easily.composition import Progression, ProgressionChord, analyze_composition, build_midi, make_voicing
from practising_piano_easily.core import parse_key


def test_voicing_inversion_and_slash_bass():
    assert make_voicing(ProgressionChord("C", inversion=0, octave=3)) == (48, 52, 55)
    assert make_voicing(ProgressionChord("C", inversion=1, octave=3)) == (52, 55, 60)
    slash = make_voicing(ProgressionChord("C/E", octave=3))
    assert slash[0] % 12 == 4
    assert set(note % 12 for note in slash) == {0, 4, 7}


def test_progression_edit_analysis_and_objective_metrics():
    progression = Progression([ProgressionChord("Cmaj7"), ProgressionChord("A7"), ProgressionChord("Dm7"), ProgressionChord("G7")])
    progression.move(0, 1)
    progression.move(1, -1)
    report = analyze_composition(progression, parse_key("C major"))
    assert tuple(item.roman for item in report.harmony) == ("Imaj7", "V7/ii", "ii7", "V7")
    assert len(report.voice_leading) == 3
    assert all(item.total_movement >= 0 for item in report.voice_leading)


def test_built_midi_has_tempo_duration_velocity_and_notes():
    progression = Progression([
        ProgressionChord("C", duration_beats=2, octave=3, velocity=70),
        ProgressionChord("F", duration_beats=2, octave=3, velocity=85),
    ])
    midi = build_midi(progression, 100)
    messages = [message for message in midi.tracks[0] if not message.is_meta]
    assert sum(message.type == "note_on" for message in messages) == 6
    assert {message.velocity for message in messages if message.type == "note_on"} == {70, 85}
    assert sum(message.time for message in messages) == 1920
