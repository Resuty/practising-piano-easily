import pytest

from practising_piano_easily.core import (
    Key, analyze_progression, diatonic_chords, minor_functional_dominant,
    parse_key, roman_to_chord, scale_notes,
)
from practising_piano_easily.trainers.progression import ProgressionTrainer


def names(notes):
    return tuple(map(str, notes))


@pytest.mark.parametrize(
    ("tonic", "scale_type", "expected"),
    [
        ("F", "major", ("F", "G", "A", "Bb", "C", "D", "E")),
        ("A", "natural_minor", ("A", "B", "C", "D", "E", "F", "G")),
        ("A", "harmonic_minor", ("A", "B", "C", "D", "E", "F", "G#")),
        ("A", "melodic_minor_ascending", ("A", "B", "C", "D", "E", "F#", "G#")),
    ],
)
def test_scales_preserve_spelling(tonic, scale_type, expected):
    assert names(scale_notes(tonic, scale_type)) == expected


def test_f_major_diatonic_sevenths_fixture():
    chords = diatonic_chords(parse_key("F major"), sevenths=True)
    assert tuple(item.roman for item in chords) == ("Imaj7", "ii7", "iii7", "IVmaj7", "V7", "vi7", "viiø7")
    assert tuple(item.chord.symbol for item in chords) == ("Fmaj7", "Gm7", "Am7", "Bbmaj7", "C7", "Dm7", "Em7b5")


def test_minor_natural_harmony_and_functional_dominant_are_distinct():
    key = parse_key("A minor")
    assert tuple(item.chord.symbol for item in diatonic_chords(key)) == ("Am", "Bdim", "C", "Dm", "Em", "F", "G")
    assert minor_functional_dominant(key).symbol == "E7"
    assert names(minor_functional_dominant(key).notes) == ("E", "G#", "B", "D")


def test_roman_numerals_and_secondary_dominants():
    key = Key(scale_notes("C")[0], "major")
    assert roman_to_chord(key, "vi").symbol == "Am"
    assert roman_to_chord(key, "V/V").symbol == "D"
    assert roman_to_chord(key, "V7/ii").symbol == "A7"


def test_progression_analysis_separates_fact_and_interpretation():
    findings = analyze_progression(["Cmaj7", "A7", "Dm7", "G7"], parse_key("C major"))
    assert tuple(item.roman for item in findings) == ("Imaj7", "V7/ii", "ii7", "V7")
    assert findings[1].chromatic
    assert findings[1].possible_interpretations == ("secondary dominant of ii",)
    assert not findings[0].chromatic


def test_progression_trainer_checks_and_advances_in_order():
    trainer = ProgressionTrainer(parse_key("D major"), ["I", "V", "vi", "IV"])
    assert tuple(chord.symbol for chord in trainer.chords) == ("D", "A", "Bm", "G")
    assert trainer.check({50, 54, 57}).correct
    assert not trainer.advance()
    assert trainer.current_roman == "V"
    trainer.advance()
    trainer.advance()
    assert trainer.advance()
    assert trainer.current_roman == "I"


@pytest.mark.parametrize(
    ("symbol", "roman", "interpretation"),
    [
        ("Fm", "iv", "borrowed from C minor"),
        ("Ab", "bVI", "borrowed from C minor"),
        ("Bb", "bVII", "borrowed from C minor"),
        ("Eb", "bIII", "borrowed from C minor"),
        ("Db7", "bII7", "possible tritone substitution for V7"),
        ("Bb7", "bVII7", "possible backdoor dominant"),
        ("Cdim7", "CT°7", "possible common-tone diminished chord"),
        ("C#dim7", "vii°7/ii", "secondary leading-tone chord of ii"),
    ],
)
def test_common_chromatic_harmony(symbol, roman, interpretation):
    finding = analyze_progression([symbol], parse_key("C major"))[0]
    assert finding.chromatic
    assert finding.roman == roman
    assert interpretation in finding.possible_interpretations


def test_context_can_add_another_possible_interpretation():
    finding = analyze_progression(["C", "C#dim7", "Dm"], parse_key("C major"))[1]
    assert finding.roman == "vii°7/ii"
    assert "secondary leading-tone chord of ii" in finding.possible_interpretations
    assert "possible chromatic passing diminished chord" in finding.possible_interpretations
