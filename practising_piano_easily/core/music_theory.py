"""Spelling-aware notes, intervals, chords, and chord-symbol parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


LETTERS = "CDEFGAB"
NATURAL_PITCH_CLASSES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


@dataclass(frozen=True, order=True)
class Note:
    letter: str
    accidental: int = 0

    def __post_init__(self) -> None:
        if self.letter not in LETTERS or not -3 <= self.accidental <= 3:
            raise ValueError(f"Invalid note spelling: {self.letter!r}, accidental={self.accidental}")

    @property
    def pitch_class(self) -> int:
        return (NATURAL_PITCH_CLASSES[self.letter] + self.accidental) % 12

    def __str__(self) -> str:
        return self.letter + ("#" * self.accidental if self.accidental > 0 else "b" * -self.accidental)


def parse_note(value: str) -> Note:
    value = value.strip().replace("♯", "#").replace("♭", "b")
    if not value or value[0].upper() not in LETTERS:
        raise ValueError(f"Invalid note: {value!r}")
    suffix = value[1:]
    if any(character not in "#b" for character in suffix) or ("#" in suffix and "b" in suffix):
        raise ValueError(f"Invalid accidental: {value!r}")
    return Note(value[0].upper(), suffix.count("#") - suffix.count("b"))


@dataclass(frozen=True)
class Interval:
    name: str
    semitones: int
    letter_steps: int


INTERVALS = {
    "P1": Interval("P1", 0, 0), "m2": Interval("m2", 1, 1),
    "M2": Interval("M2", 2, 1), "m3": Interval("m3", 3, 2),
    "M3": Interval("M3", 4, 2), "P4": Interval("P4", 5, 3),
    "A4": Interval("A4", 6, 3), "d5": Interval("d5", 6, 4),
    "P5": Interval("P5", 7, 4), "m6": Interval("m6", 8, 5),
    "M6": Interval("M6", 9, 5), "m7": Interval("m7", 10, 6),
    "M7": Interval("M7", 11, 6), "P8": Interval("P8", 12, 7),
    "9": Interval("9", 14, 8), "11": Interval("11", 17, 10),
    "13": Interval("13", 21, 12),
}


def transpose(note: Note | str, interval: Interval | str) -> Note:
    note = parse_note(note) if isinstance(note, str) else note
    interval = INTERVALS[interval] if isinstance(interval, str) else interval
    target_letter = LETTERS[(LETTERS.index(note.letter) + interval.letter_steps) % 7]
    target_pc = (note.pitch_class + interval.semitones) % 12
    accidental = target_pc - NATURAL_PITCH_CLASSES[target_letter]
    accidental += -12 if accidental > 6 else 12 if accidental < -6 else 0
    return Note(target_letter, accidental)


def interval_between(first: Note | str, second: Note | str) -> str:
    first = parse_note(first) if isinstance(first, str) else first
    second = parse_note(second) if isinstance(second, str) else second
    steps = (LETTERS.index(second.letter) - LETTERS.index(first.letter)) % 7
    number = steps + 1
    difference = (second.pitch_class - first.pitch_class) % 12 - (0, 2, 4, 5, 7, 9, 11)[steps]
    if difference > 6:
        difference -= 12
    quality = (
        {0: "P", 1: "A", -1: "d"}.get(difference)
        if number in {1, 4, 5}
        else {0: "M", -1: "m", 1: "A", -2: "d"}.get(difference)
    )
    if quality is None:
        raise ValueError(f"Unsupported interval spelling: {first} to {second}")
    return f"{quality}{number}"


DEGREE_INTERVALS = {
    "1": Interval("P1", 0, 0), "b2": Interval("m2", 1, 1), "2": Interval("M2", 2, 1),
    "b3": Interval("m3", 3, 2), "3": Interval("M3", 4, 2), "4": Interval("P4", 5, 3),
    "#4": Interval("A4", 6, 3), "b5": Interval("d5", 6, 4), "5": Interval("P5", 7, 4),
    "#5": Interval("A5", 8, 4), "b6": Interval("m6", 8, 5), "6": Interval("M6", 9, 5),
    "bb7": Interval("d7", 9, 6), "b7": Interval("m7", 10, 6), "7": Interval("M7", 11, 6),
    "b9": Interval("m9", 13, 8), "9": Interval("M9", 14, 8), "#9": Interval("A9", 15, 8),
    "11": Interval("P11", 17, 10), "#11": Interval("A11", 18, 10),
    "b13": Interval("m13", 20, 12), "13": Interval("M13", 21, 12),
}


@dataclass(frozen=True)
class Chord:
    root: Note
    quality: str = "major"
    seventh: str | None = None
    extension: int | None = None
    alterations: tuple[str, ...] = ()
    added_tones: tuple[int, ...] = ()
    suspension: int | None = None
    sixth: bool = False
    bass: Note | None = None
    canonical_suffix: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if self.quality not in {"major", "minor", "diminished", "augmented"}:
            raise ValueError(f"Unsupported chord quality: {self.quality}")
        if self.seventh not in {None, "major", "minor", "diminished"}:
            raise ValueError(f"Unsupported seventh: {self.seventh}")
        if self.suspension not in {None, 2, 4}:
            raise ValueError(f"Unsupported suspension: {self.suspension}")
        if any(alteration not in {"b5", "#5", "b9", "#9", "#11", "b13"} for alteration in self.alterations):
            raise ValueError(f"Unsupported alteration: {self.alterations}")

    @property
    def symbol(self) -> str:
        suffix = self.canonical_suffix
        if suffix is None:
            suffix = {"major": "", "minor": "m", "diminished": "dim", "augmented": "aug"}[self.quality]
        return f"{self.root}{suffix}" + (f"/{self.bass}" if self.bass else "")

    @property
    def formula(self) -> tuple[str, ...]:
        tones = ["1", {"major": "3", "minor": "b3", "diminished": "b3", "augmented": "3"}[self.quality],
                 {"major": "5", "minor": "5", "diminished": "b5", "augmented": "#5"}[self.quality]]
        if self.suspension:
            tones[1] = str(self.suspension)
        if self.sixth:
            tones.append("6")
        if self.seventh:
            tones.append({"major": "7", "minor": "b7", "diminished": "bb7"}[self.seventh])
        if self.extension:
            tones.extend(tone for degree, tone in ((9, "9"), (11, "11"), (13, "13")) if self.extension >= degree)
        tones.extend(str(tone) for tone in self.added_tones)
        for alteration in self.alterations:
            degree = alteration.lstrip("b#")
            tones = [tone for tone in tones if tone.lstrip("b#") != degree]
            tones.append(alteration)
        order = {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "9": 9, "11": 11, "13": 13}
        return tuple(sorted(dict.fromkeys(tones), key=lambda tone: order[tone.lstrip("b#")]))

    @property
    def notes(self) -> tuple[Note, ...]:
        return tuple(transpose(self.root, DEGREE_INTERVALS[tone]) for tone in self.formula)

    @property
    def pitch_classes(self) -> frozenset[int]:
        return frozenset(note.pitch_class for note in self.notes)

    @property
    def required_pitch_classes(self) -> frozenset[int]:
        if not self.extension:
            return self.pitch_classes
        required_degrees = {"1", "2" if self.suspension == 2 else "4" if self.suspension == 4 else
                            "b3" if self.quality in {"minor", "diminished"} else "3",
                            {"major": "7", "minor": "b7", "diminished": "bb7"}[self.seventh],
                            str(self.extension)}
        required_degrees.update(self.alterations)
        return frozenset(transpose(self.root, DEGREE_INTERVALS[tone]).pitch_class for tone in required_degrees)


BASE_SPECS = {
    "": {}, "m": {"quality": "minor"}, "dim": {"quality": "diminished"},
    "aug": {"quality": "augmented"}, "maj7": {"seventh": "major"},
    "7": {"seventh": "minor"}, "m7": {"quality": "minor", "seventh": "minor"},
    "mMaj7": {"quality": "minor", "seventh": "major"},
    "m7b5": {"quality": "diminished", "seventh": "minor"},
    "dim7": {"quality": "diminished", "seventh": "diminished"},
    "sus2": {"suspension": 2}, "sus4": {"suspension": 4},
    "add9": {"added_tones": (9,)}, "add11": {"added_tones": (11,)},
    "6": {"sixth": True}, "m6": {"quality": "minor", "sixth": True},
    "6/9": {"sixth": True, "added_tones": (9,)},
    "9": {"seventh": "minor", "extension": 9},
    "maj9": {"seventh": "major", "extension": 9},
    "m9": {"quality": "minor", "seventh": "minor", "extension": 9},
    "11": {"seventh": "minor", "extension": 11},
    "m11": {"quality": "minor", "seventh": "minor", "extension": 11},
    "13": {"seventh": "minor", "extension": 13},
    "maj13": {"seventh": "major", "extension": 13},
    "m13": {"quality": "minor", "seventh": "minor", "extension": 13},
}
ALIASES = {"maj": "", "min": "m", "M7": "maj7", "Δ7": "maj7", "°": "dim", "+": "aug",
           "°7": "dim7", "ø": "m7b5", "ø7": "m7b5"}
ALTERATION_PATTERN = re.compile(r"(?:b5|#5|b9|#9|#11|b13)")


def parse_chord(symbol: str) -> Chord:
    source = symbol.strip().replace("♯", "#").replace("♭", "b")
    bass = None
    slash = re.search(r"/([A-Ga-g](?:#{1,2}|b{1,2})?)$", source)
    if slash:
        bass = parse_note(slash.group(1))
        source = source[:slash.start()]
    root_match = re.match(r"^([A-Ga-g](?:#{1,2}|b{1,2})?)(.*)$", source)
    if not root_match:
        raise ValueError(f"Invalid chord symbol: {symbol!r}")
    root = parse_note(root_match.group(1))
    suffix = root_match.group(2)
    suffix = ALIASES.get(suffix, suffix)
    if suffix.startswith("min"):
        suffix = "m" + suffix[3:]
    exact = BASE_SPECS.get(suffix)
    alterations: tuple[str, ...] = ()
    base = suffix
    if exact is None:
        for candidate in sorted(BASE_SPECS, key=len, reverse=True):
            if not candidate or not suffix.startswith(candidate):
                continue
            remainder = suffix[len(candidate):]
            tokens = tuple(ALTERATION_PATTERN.findall(remainder))
            if "".join(tokens) == remainder:
                base, exact, alterations = candidate, BASE_SPECS[candidate], tokens
                break
    if exact is None:
        raise ValueError(f"Invalid or unsupported chord symbol: {symbol!r}")
    canonical = base + "".join(alterations)
    return Chord(root=root, bass=bass, alterations=alterations, canonical_suffix=canonical, **exact)

