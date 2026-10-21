"""Question generation for block and Stage 1 mixed ear training."""

from __future__ import annotations

import random
from dataclasses import dataclass


INTERVALS = {"m2": 1, "M2": 2, "m3": 3, "M3": 4, "P4": 5, "A4 / d5": 6,
             "P5": 7, "m6": 8, "M6": 9, "m7": 10, "M7": 11, "P8": 12}
TRIADS = {"major": (0, 4, 7), "minor": (0, 3, 7), "diminished": (0, 3, 6), "augmented": (0, 4, 8)}
SEVENTHS = {"maj7": (0, 4, 7, 11), "7": (0, 4, 7, 10), "m7": (0, 3, 7, 10),
            "m7b5": (0, 3, 6, 10), "dim7": (0, 3, 6, 9)}
PITCH_NAMES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")


@dataclass(frozen=True)
class EarQuestion:
    kind: str
    prompt: str
    options: tuple[str, ...]
    answer: str
    groups: tuple[tuple[int, ...], ...]


class EarTrainer:
    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    def question(self, kind: str, stage: int = 1) -> EarQuestion:
        if kind == "Mixed (Stage 1)":
            kind = self.rng.choice(("Interval", "Major vs minor"))
        if kind == "Interval":
            answer = self.rng.choice(tuple(INTERVALS))
            root = self.rng.randint(48, 60)
            return EarQuestion(kind, "Identify the ascending interval", tuple(INTERVALS), answer,
                               ((root,), (root + INTERVALS[answer],)))
        if kind == "Major vs minor":
            return self._quality_question("Major vs minor", {name: TRIADS[name] for name in ("major", "minor")})
        if kind == "Triad quality":
            return self._quality_question(kind, TRIADS)
        if kind == "Seventh quality":
            return self._quality_question(kind, SEVENTHS)
        if kind == "Inversion":
            inversion = self.rng.randrange(3)
            root = self.rng.randint(48, 55)
            base = [root + interval for interval in TRIADS["major"]]
            notes = tuple(base[inversion:] + [note + 12 for note in base[:inversion]])
            answers = ("Root position", "First inversion", "Second inversion")
            return EarQuestion(kind, "Identify the major-triad inversion", answers, answers[inversion], (notes,))
        if kind == "Bass note":
            root = self.rng.randint(48, 59)
            inversion = self.rng.randrange(3)
            base = [root + interval for interval in TRIADS[self.rng.choice(("major", "minor"))]]
            notes = tuple(base[inversion:] + [note + 12 for note in base[:inversion]])
            answer = PITCH_NAMES[notes[0] % 12]
            return EarQuestion(kind, "Identify the lowest pitch class", PITCH_NAMES, answer, (notes,))
        if kind == "Root movement":
            movements = {name: semitones for name, semitones in INTERVALS.items() if name != "P8"}
            answer = self.rng.choice(tuple(movements))
            root = self.rng.randint(48, 60)
            return EarQuestion(kind, "Identify the ascending root movement", tuple(movements), answer,
                               ((root,), (root + movements[answer],)))
        if kind == "Cadence":
            tonic = self.rng.randint(48, 53)
            cadence = self.rng.choice(("V → I", "ii → V → I"))
            tonic_chord = tuple(tonic + interval for interval in TRIADS["major"])
            dominant = tuple(tonic + 7 + interval for interval in TRIADS["major"])
            supertonic = tuple(tonic + 2 + interval for interval in TRIADS["minor"])
            groups = (dominant, tonic_chord) if cadence == "V → I" else (supertonic, dominant, tonic_chord)
            return EarQuestion(kind, "Identify the cadence", ("V → I", "ii → V → I"), cadence, groups)
        raise ValueError(f"Unsupported ear-training kind: {kind}")

    def _quality_question(self, kind: str, vocabulary: dict[str, tuple[int, ...]]) -> EarQuestion:
        answer = self.rng.choice(tuple(vocabulary))
        root = self.rng.randint(48, 59)
        notes = tuple(root + interval for interval in vocabulary[answer])
        return EarQuestion(kind, "Identify the chord quality", tuple(vocabulary), answer, (notes,))
