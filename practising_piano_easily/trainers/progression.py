"""Sequential Roman-numeral progression practice."""

from __future__ import annotations

from practising_piano_easily.core import Key, roman_to_chord

from .chord_construction import Evaluation, match_chord


class ProgressionTrainer:
    def __init__(self, key: Key, romans: list[str]) -> None:
        if not romans:
            raise ValueError("A progression needs at least one Roman numeral")
        self.key = key
        self.romans = romans
        self.chords = [roman_to_chord(key, roman) for roman in romans]
        self.index = 0

    @property
    def current_roman(self) -> str:
        return self.romans[self.index]

    @property
    def current_chord(self):
        return self.chords[self.index]

    def check(self, notes: set[int] | frozenset[int], free_voicing: bool = True) -> Evaluation:
        return match_chord(self.current_chord, notes, free_voicing)

    def advance(self) -> bool:
        self.index += 1
        if self.index == len(self.chords):
            self.index = 0
            return True
        return False

