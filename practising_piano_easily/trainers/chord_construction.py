"""Major/minor triad construction trainer."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

from practising_piano_easily.core import Chord, parse_chord
from practising_piano_easily.storage import Database
from practising_piano_easily.progress.mastery import adaptive_weight


NATURAL_ROOTS = "CDEFGAB"
CHROMATIC_ROOTS = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
LEVEL_SUFFIXES = {
    1: ("", "m"),
    2: ("dim", "aug"),
    3: ("maj7", "7", "m7"),
    4: ("m7b5", "dim7", "mMaj7"),
    5: ("sus2", "sus4", "add9", "add11", "6", "m6", "6/9"),
    6: ("9", "maj9", "m9"),
    7: ("11", "m11", "13", "maj13", "m13"),
    8: ("7b5", "7#5", "7b9", "7#9", "7#11", "7b13"),
}
GENERIC_PITCH_NAMES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B")
SHARP_PITCH_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
FLAT_PITCH_NAMES = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")


@dataclass(frozen=True)
class Evaluation:
    correct: bool
    expected_pitch_classes: frozenset[int]
    played_pitch_classes: frozenset[int]
    missing_pitch_classes: frozenset[int]
    extra_pitch_classes: frozenset[int]
    root_position_ok: bool
    bass_ok: bool
    response_time_ms: int
    played_notes: tuple[int, ...]


def match_chord(chord: Chord, midi_notes: set[int] | frozenset[int], any_inversion: bool) -> Evaluation:
    notes = tuple(sorted(midi_notes))
    played = frozenset(note % 12 for note in notes)
    expected = chord.pitch_classes
    missing = chord.required_pitch_classes - played
    extra = played - expected
    root_ok = bool(notes) and notes[0] % 12 == chord.root.pitch_class
    bass_ok = bool(notes) and (chord.bass is None or notes[0] % 12 == chord.bass.pitch_class)
    return Evaluation(
        correct=not missing and not extra and bass_ok and (any_inversion or chord.bass is not None or root_ok),
        expected_pitch_classes=expected,
        played_pitch_classes=played,
        missing_pitch_classes=missing,
        extra_pitch_classes=extra,
        root_position_ok=root_ok,
        bass_ok=bass_ok,
        response_time_ms=0,
        played_notes=notes,
    )


def pitch_name(pitch_class: int, chord: Chord | None = None, preference: str = "Context") -> str:
    if chord:
        for note in chord.notes:
            if note.pitch_class == pitch_class % 12:
                return str(note)
    names = SHARP_PITCH_NAMES if preference == "Prefer sharps" else FLAT_PITCH_NAMES if preference == "Prefer flats" else GENERIC_PITCH_NAMES
    return names[pitch_class % 12]


def midi_note_name(note: int, chord: Chord | None = None, preference: str = "Context") -> str:
    return f"{pitch_name(note % 12, chord, preference)}{note // 12 - 1}"


class ChordConstructionTrainer:
    def __init__(self, database: Database, session_id: int, rng: random.Random | None = None) -> None:
        self.database = database
        self.session_id = session_id
        self.rng = rng or random.Random()
        self.level = 1
        self.training_mode = "Practice"
        self.slow_practice = True
        self.any_inversion = False
        self.active_notes: frozenset[int] = frozenset()
        self.attempt_scored = False
        self.last_evaluation: Evaluation | None = None
        self.correct_count = 0
        self.wrong_count = 0
        self.corrected_notes = 0
        self.response_times: list[int] = []
        self._bag: list[Chord] = []
        self.current_chord = self._pick_chord(None)
        self.question_started = time.monotonic()

    def _pick_chord(self, previous: Chord | None) -> Chord:
        roots = tuple(NATURAL_ROOTS) if self.level == 1 else CHROMATIC_ROOTS
        choices = [parse_chord(root + suffix) for root in roots for suffix in LEVEL_SUFFIXES[self.level]]
        choices = [chord for chord in choices if chord != previous]
        if self.level == 1 and previous:
            choices = [chord for chord in choices if chord.quality != previous.quality]
        saved = self.database.mastery_for_skill(f"chord_level_{self.level}")
        weights = [adaptive_weight(*saved.get(chord.symbol, (0.0, 0.0))) for chord in choices]
        return self.rng.choices(choices, weights=weights, k=1)[0]

    def set_level(self, level: int) -> None:
        if level not in LEVEL_SUFFIXES:
            raise ValueError(f"Unknown training level: {level}")
        self.level = level
        self._bag.clear()
        self.next_question()

    def next_question(self, now: float | None = None) -> None:
        self.current_chord = self._pick_chord(self.current_chord)
        self.active_notes = frozenset()
        self.attempt_scored = False
        self.last_evaluation = None
        self.corrected_notes = 0
        self.question_started = time.monotonic() if now is None else now

    def set_active_notes(self, notes: set[int] | frozenset[int]) -> str:
        new_notes = frozenset(notes)
        changed = new_notes != self.active_notes
        if changed and new_notes and not self.attempt_scored and self.slow_practice and self.training_mode != "Test":
            preview = match_chord(self.current_chord, new_notes, self.any_inversion)
            self.corrected_notes += len({note for note in new_notes - self.active_notes if note % 12 in preview.extra_pitch_classes})
            if not preview.missing_pitch_classes and not preview.extra_pitch_classes and not preview.correct:
                self.corrected_notes += 1
        self.active_notes = new_notes
        if not new_notes:
            if self.last_evaluation and self.last_evaluation.correct:
                return "advance"
            self.attempt_scored = False
            return "released"
        if changed and self.slow_practice and self.last_evaluation and not self.last_evaluation.correct:
            self.attempt_scored = False
        return "settle" if changed and not self.attempt_scored else "unchanged"

    def evaluate(self, now: float | None = None) -> Evaluation | None:
        if not self.active_notes or self.attempt_scored:
            return None
        finished = time.monotonic() if now is None else now
        base = match_chord(self.current_chord, self.active_notes, self.any_inversion)
        result = Evaluation(
            **{**base.__dict__, "response_time_ms": max(0, round((finished - self.question_started) * 1000))}
        )
        clean = result.correct and not (self.slow_practice and self.training_mode != "Test" and self.corrected_notes)
        self.database.record_attempt(
            session_id=self.session_id,
            trainer_type="chord_construction",
            skill=f"chord_level_{self.level}",
            question=self.current_chord.symbol,
            expected=" ".join(map(str, self.current_chord.notes)),
            played=" ".join(map(str, result.played_notes)),
            correct=clean,
            response_time_ms=result.response_time_ms,
            metadata={
                "training_mode": self.training_mode,
                "mode": "any_inversion" if self.any_inversion else "root_position",
                "root": str(self.current_chord.root), "quality": self.current_chord.quality,
                "played_pitch_classes": sorted(result.played_pitch_classes),
                "confusion": self._confusion(result),
                "corrected_notes": self.corrected_notes,
                "completed": result.correct,
                "target_hints": self.training_mode == "Learn",
            },
        )
        self.attempt_scored = True
        self.last_evaluation = result
        self.correct_count += int(clean)
        self.wrong_count += int(not clean)
        self.response_times.append(result.response_time_ms)
        return result

    def _confusion(self, result: Evaluation) -> str | None:
        if result.correct or len(result.played_pitch_classes) < 3:
            return None
        roots = tuple(NATURAL_ROOTS) if self.level == 1 else CHROMATIC_ROOTS
        for root in roots:
            for suffix in LEVEL_SUFFIXES[self.level]:
                candidate = parse_chord(root + suffix)
                if candidate.pitch_classes == result.played_pitch_classes and candidate != self.current_chord:
                    expected = self.current_chord.canonical_suffix or self.current_chord.quality
                    played = candidate.canonical_suffix or candidate.quality
                    return f"{expected} → {played}"
        return None

    @property
    def accuracy(self) -> float:
        total = self.correct_count + self.wrong_count
        return 100 * self.correct_count / total if total else 0.0

    @property
    def average_response_ms(self) -> float:
        return sum(self.response_times) / len(self.response_times) if self.response_times else 0.0
