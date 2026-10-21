import pytest

from practising_piano_easily.core import parse_chord
from practising_piano_easily.trainers.chord_construction import match_chord


@pytest.mark.parametrize(
    ("symbol", "canonical", "formula", "notes"),
    [
        ("C", "C", ("1", "3", "5"), ("C", "E", "G")),
        ("Cm", "Cm", ("1", "b3", "5"), ("C", "Eb", "G")),
        ("Cdim", "Cdim", ("1", "b3", "b5"), ("C", "Eb", "Gb")),
        ("Caug", "Caug", ("1", "3", "#5"), ("C", "E", "G#")),
        ("Cmaj7", "Cmaj7", ("1", "3", "5", "7"), ("C", "E", "G", "B")),
        ("C7", "C7", ("1", "3", "5", "b7"), ("C", "E", "G", "Bb")),
        ("Cm7", "Cm7", ("1", "b3", "5", "b7"), ("C", "Eb", "G", "Bb")),
        ("Cm7b5", "Cm7b5", ("1", "b3", "b5", "b7"), ("C", "Eb", "Gb", "Bb")),
        ("Cdim7", "Cdim7", ("1", "b3", "b5", "bb7"), ("C", "Eb", "Gb", "Bbb")),
        ("Cadd9", "Cadd9", ("1", "3", "5", "9"), ("C", "E", "G", "D")),
        ("C9", "C9", ("1", "3", "5", "b7", "9"), ("C", "E", "G", "Bb", "D")),
        ("G7b9", "G7b9", ("1", "3", "5", "b7", "b9"), ("G", "B", "D", "F", "Ab")),
        ("G7#9", "G7#9", ("1", "3", "5", "b7", "#9"), ("G", "B", "D", "F", "A#")),
    ],
)
def test_chord_parser_fixtures(symbol, canonical, formula, notes):
    chord = parse_chord(symbol)
    assert chord.symbol == canonical
    assert chord.formula == formula
    assert tuple(map(str, chord.notes)) == notes


@pytest.mark.parametrize(
    ("alias", "canonical"),
    [("CM7", "Cmaj7"), ("CΔ7", "Cmaj7"), ("Cmin", "Cm"), ("C°", "Cdim"),
     ("C+", "Caug"), ("Cø", "Cm7b5"), ("Cø7", "Cm7b5"), ("C°7", "Cdim7")],
)
def test_aliases_are_canonicalized(alias, canonical):
    assert parse_chord(alias).symbol == canonical


def test_slash_bass_is_separate_from_identity_and_is_checked():
    chord = parse_chord("C/E")
    assert chord.symbol == "C/E"
    assert tuple(map(str, chord.notes)) == ("C", "E", "G")
    assert match_chord(chord, {52, 55, 60}, True).correct
    assert not match_chord(chord, {48, 52, 55}, True).correct


def test_extended_chord_distinguishes_theory_from_practical_voicing():
    chord = parse_chord("C13")
    assert tuple(map(str, chord.notes)) == ("C", "E", "G", "Bb", "D", "F", "A")
    assert match_chord(chord, {48, 52, 58, 69}, False).correct  # root, 3rd, b7, 13th
    assert not match_chord(chord, {48, 52, 55, 69}, False).correct  # missing b7


def test_invalid_symbol_reports_value_error():
    with pytest.raises(ValueError, match="Invalid or unsupported chord symbol"):
        parse_chord("Cmaj42")

