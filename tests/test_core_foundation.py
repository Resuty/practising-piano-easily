import ast
from pathlib import Path

import pytest

from practising_piano_easily.core import Chord, interval_between, parse_note, transpose


def test_note_spelling_and_enharmonic_equivalence():
    assert parse_note("F#").pitch_class == parse_note("Gb").pitch_class
    assert str(transpose("F#", "M3")) == "A#"
    assert str(transpose("Bb", "M3")) == "D"
    assert str(transpose("C", "13")) == "A"


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [("C", "E", "M3"), ("C", "Eb", "m3"), ("F#", "B#", "A4"), ("C", "Gb", "d5")],
)
def test_interval_between_spellings(first, second, expected):
    assert interval_between(first, second) == expected


@pytest.mark.parametrize(
    ("root", "quality", "expected"),
    [
        ("C", "major", ("C", "E", "G")),
        ("C", "minor", ("C", "Eb", "G")),
        ("F#", "major", ("F#", "A#", "C#")),
        ("Bb", "major", ("Bb", "D", "F")),
    ],
)
def test_foundation_chords(root, quality, expected):
    chord = Chord(parse_note(root), quality)
    assert tuple(map(str, chord.notes)) == expected


def test_core_has_no_ui_midi_or_audio_imports():
    forbidden = {"PySide6", "mido", "sounddevice"}
    core = Path(__file__).parents[1] / "practising_piano_easily" / "core"
    imports = set()
    for path in core.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
    assert imports.isdisjoint(forbidden)


def test_invalid_note_and_quality_are_friendly():
    with pytest.raises(ValueError, match="Invalid note"):
        parse_note("H")
    with pytest.raises(ValueError, match="Unsupported chord quality"):
        Chord(parse_note("C"), "dominant")
