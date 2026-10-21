"""Shared questions for interval, scale, diatonic, Roman, and inversion practice."""

from __future__ import annotations

import random
from dataclasses import dataclass

from practising_piano_easily.core import Chord, Key, diatonic_chords, parse_chord, parse_key, scale_notes, transpose


ROOTS = ("C", "D", "E", "F", "G", "A", "B")
INTERVAL_NAMES = {"m2": "Minor 2nd", "M2": "Major 2nd", "m3": "Minor 3rd", "M3": "Major 3rd",
                  "P4": "Perfect 4th", "A4": "Tritone", "P5": "Perfect 5th", "m6": "Minor 6th",
                  "M6": "Major 6th", "m7": "Minor 7th", "M7": "Major 7th", "P8": "Octave"}
SCALE_LABELS = {"major": "Major", "natural_minor": "Natural minor", "harmonic_minor": "Harmonic minor"}


@dataclass(frozen=True)
class TheoryQuestion:
    kind: str
    prompt: str
    answer_text: str
    expected_pitch_classes: frozenset[int] = frozenset()
    expected_sequence: tuple[int, ...] = ()
    bass_pitch_class: int | None = None
    options: tuple[str, ...] = ()
    answer: str | None = None


class TheoryPracticeGenerator:
    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    def question(self, kind: str) -> TheoryQuestion:
        if kind == "Interval construction":
            root = self.rng.choice(ROOTS)
            interval = self.rng.choice(tuple(INTERVAL_NAMES))
            target = transpose(root, interval)
            root_pitch_class = parse_chord(root).root.pitch_class
            pitch_classes = frozenset((root_pitch_class, target.pitch_class))
            return TheoryQuestion(
                kind, f"{INTERVAL_NAMES[interval]} above {root}", f"{root} {target}", pitch_classes,
                expected_sequence=(root_pitch_class, target.pitch_class), bass_pitch_class=root_pitch_class,
            )
        if kind == "Scale":
            root = self.rng.choice(ROOTS)
            scale_type = self.rng.choice(tuple(SCALE_LABELS))
            notes = scale_notes(root, scale_type)
            sequence = tuple(note.pitch_class for note in notes) + (notes[0].pitch_class,)
            return TheoryQuestion(kind, f"{root} {SCALE_LABELS[scale_type]}",
                                  " ".join(map(str, notes + (notes[0],))), expected_sequence=sequence)
        if kind in {"Diatonic chord", "Roman: symbol → chord", "Roman: chord → function"}:
            key = parse_key(f"{self.rng.choice(ROOTS)} major")
            item = self.rng.choice(diatonic_chords(key, sevenths=self.rng.choice((False, True))))
            if kind == "Roman: chord → function":
                options = tuple(entry.roman for entry in diatonic_chords(key, "7" in item.roman or "maj7" in item.roman or "ø" in item.roman))
                return TheoryQuestion(kind, f"{key.name}: {item.chord.symbol}", item.roman,
                                      options=options, answer=item.roman)
            return TheoryQuestion(kind, f"{key.name}: {item.roman}",
                                  f"{item.chord.symbol} = {' '.join(map(str, item.chord.notes))}",
                                  expected_pitch_classes=item.chord.pitch_classes)
        if kind == "Inversion":
            chord = parse_chord(self.rng.choice(ROOTS) + self.rng.choice(("", "m", "7", "maj7", "m7")))
            inversion = self.rng.randrange(len(chord.notes))
            names = ("Root position", "First inversion", "Second inversion", "Third inversion")
            ordered_notes = chord.notes[inversion:] + chord.notes[:inversion]
            return TheoryQuestion(kind, f"{chord.symbol} — {names[inversion]}",
                                  " ".join(map(str, ordered_notes)), chord.pitch_classes,
                                  bass_pitch_class=chord.notes[inversion].pitch_class)
        raise ValueError(f"Unsupported theory exercise: {kind}")


def check_notes(question: TheoryQuestion, midi_notes: tuple[int, ...] | list[int] | set[int]) -> bool:
    notes = tuple(midi_notes)
    if question.expected_sequence:
        return (tuple(note % 12 for note in notes) == question.expected_sequence
                and all(first < second for first, second in zip(notes, notes[1:])))
    if not notes:
        return False
    pitch_classes = frozenset(note % 12 for note in notes)
    bass_ok = question.bass_pitch_class is None or min(notes) % 12 == question.bass_pitch_class
    return pitch_classes == question.expected_pitch_classes and bass_ok


def check_answer(question: TheoryQuestion, answer: str) -> bool:
    if question.answer is None:
        raise ValueError("This question expects MIDI notes")
    return answer == question.answer
