"""Scales, diatonic harmony, Roman numerals, and explicit harmonic interpretations."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from .music_theory import Chord, Interval, Note, parse_chord, parse_note, transpose


SCALE_PATTERNS = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "natural_minor": (0, 2, 3, 5, 7, 8, 10),
    "harmonic_minor": (0, 2, 3, 5, 7, 8, 11),
    "melodic_minor_ascending": (0, 2, 3, 5, 7, 9, 11),
}
TRIAD_SUFFIXES = {(4, 7): "", (3, 7): "m", (3, 6): "dim", (4, 8): "aug"}
SEVENTH_SUFFIXES = {
    (4, 7, 11): "maj7", (4, 7, 10): "7", (3, 7, 10): "m7",
    (3, 6, 10): "m7b5", (3, 6, 9): "dim7", (3, 7, 11): "mMaj7",
}
MAJOR_TRIAD_ROMANS = ("I", "ii", "iii", "IV", "V", "vi", "vii°")
MAJOR_SEVENTH_ROMANS = ("Imaj7", "ii7", "iii7", "IVmaj7", "V7", "vi7", "viiø7")
MINOR_TRIAD_ROMANS = ("i", "ii°", "III", "iv", "v", "VI", "VII")
MINOR_SEVENTH_ROMANS = ("i7", "iiø7", "IIImaj7", "iv7", "v7", "VImaj7", "VII7")


@dataclass(frozen=True)
class Key:
    tonic: Note
    mode: str = "major"

    def __post_init__(self) -> None:
        if self.mode not in {"major", "minor"}:
            raise ValueError(f"Unsupported key mode: {self.mode}")

    @property
    def name(self) -> str:
        return f"{self.tonic} {self.mode}"


def parse_key(value: str) -> Key:
    parts = value.strip().split()
    if len(parts) != 2:
        raise ValueError(f"Invalid key: {value!r}")
    return Key(parse_note(parts[0]), parts[1].lower())


def scale_notes(tonic: Note | str, scale_type: str = "major") -> tuple[Note, ...]:
    tonic = parse_note(tonic) if isinstance(tonic, str) else tonic
    if scale_type not in SCALE_PATTERNS:
        raise ValueError(f"Unsupported scale: {scale_type}")
    return tuple(
        transpose(tonic, Interval(str(index + 1), semitones, index))
        for index, semitones in enumerate(SCALE_PATTERNS[scale_type])
    )


@dataclass(frozen=True)
class DiatonicChord:
    roman: str
    chord: Chord


def diatonic_chords(key: Key, sevenths: bool = False) -> tuple[DiatonicChord, ...]:
    scale_type = "major" if key.mode == "major" else "natural_minor"
    scale = scale_notes(key.tonic, scale_type)
    romans = (
        MAJOR_SEVENTH_ROMANS if key.mode == "major" and sevenths else
        MAJOR_TRIAD_ROMANS if key.mode == "major" else
        MINOR_SEVENTH_ROMANS if sevenths else MINOR_TRIAD_ROMANS
    )
    result = []
    for degree, root in enumerate(scale):
        indices = (degree, degree + 2, degree + 4, degree + 6) if sevenths else (degree, degree + 2, degree + 4)
        tones = [scale[index % 7] for index in indices]
        intervals = tuple((tone.pitch_class - root.pitch_class) % 12 for tone in tones[1:])
        suffix = (SEVENTH_SUFFIXES if sevenths else TRIAD_SUFFIXES).get(intervals)
        if suffix is None:
            raise ValueError(f"No chord spelling for scale degree {degree + 1} in {key.name}")
        result.append(DiatonicChord(romans[degree], parse_chord(str(root) + suffix)))
    return tuple(result)


def minor_functional_dominant(key: Key) -> Chord:
    if key.mode != "minor":
        raise ValueError("Functional minor dominant requires a minor key")
    fifth = scale_notes(key.tonic, "natural_minor")[4]
    return parse_chord(str(fifth) + "7")


def roman_to_chord(key: Key, roman: str) -> Chord:
    roman = roman.strip()
    secondary = re.fullmatch(r"V(7)?/(I|ii|iii|IV|V|vi)", roman)
    if secondary:
        target_roman = secondary.group(2)
        target = next(item.chord for item in diatonic_chords(Key(key.tonic, "major")) if item.roman == target_roman)
        dominant_root = transpose(target.root, "P5")
        return parse_chord(str(dominant_root) + ("7" if secondary.group(1) else ""))
    for sevenths in (False, True):
        for item in diatonic_chords(key, sevenths):
            if item.roman == roman:
                return item.chord
    raise ValueError(f"Unsupported Roman numeral {roman!r} in {key.name}")


@dataclass(frozen=True)
class HarmonyFinding:
    chord_symbol: str
    roman: str | None
    chromatic: bool
    possible_interpretations: tuple[str, ...] = ()


def analyze_chord_in_key(chord: Chord, key: Key) -> HarmonyFinding:
    for sevenths in (True, False):
        for item in diatonic_chords(key, sevenths):
            if item.chord.formula == chord.formula and item.chord.root == chord.root:
                return HarmonyFinding(chord.symbol, item.roman, False)
    if key.mode == "major":
        for target in ("ii", "iii", "IV", "V", "vi"):
            for dominant in (f"V7/{target}", f"V/{target}"):
                candidate = roman_to_chord(key, dominant)
                if candidate.formula == chord.formula and candidate.root == chord.root:
                    return HarmonyFinding(
                        chord.symbol, dominant, True, (f"secondary dominant of {target}",)
                    )
        borrowed = {
            "iv": parse_chord(str(scale_notes(key.tonic, "major")[3]) + "m"),
            "bIII": parse_chord(str(transpose(key.tonic, Interval("m3", 3, 2)))),
            "bVI": parse_chord(str(transpose(key.tonic, Interval("m6", 8, 5)))),
            "bVII": parse_chord(str(transpose(key.tonic, Interval("m7", 10, 6)))),
        }
        for roman, candidate in borrowed.items():
            if candidate.root == chord.root and candidate.formula == chord.formula:
                return HarmonyFinding(chord.symbol, roman, True, (f"borrowed from {key.tonic} minor",))
        for target in ("ii", "iii", "IV", "V", "vi"):
            target_chord = roman_to_chord(key, target)
            leading_root = transpose(target_chord.root, Interval("chromatic below", -1, -1))
            for suffix, label in (("dim7", f"vii°7/{target}"), ("dim", f"vii°/{target}")):
                candidate = parse_chord(str(leading_root) + suffix)
                if candidate.root == chord.root and candidate.formula == chord.formula:
                    return HarmonyFinding(chord.symbol, label, True, (f"secondary leading-tone chord of {target}",))
        tritone_sub = parse_chord(str(transpose(key.tonic, Interval("m2", 1, 1))) + "7")
        if tritone_sub.root == chord.root and tritone_sub.formula == chord.formula:
            return HarmonyFinding(chord.symbol, "bII7", True, ("possible tritone substitution for V7",))
        backdoor = parse_chord(str(transpose(key.tonic, Interval("m7", 10, 6))) + "7")
        if backdoor.root == chord.root and backdoor.formula == chord.formula:
            return HarmonyFinding(chord.symbol, "bVII7", True, ("possible backdoor dominant",))
        common_tone = parse_chord(str(key.tonic) + "dim7")
        if common_tone.root == chord.root and common_tone.formula == chord.formula:
            return HarmonyFinding(chord.symbol, "CT°7", True, ("possible common-tone diminished chord",))
    return HarmonyFinding(chord.symbol, None, True, ("No single interpretation assigned",))


def analyze_progression(symbols: list[str] | tuple[str, ...], key: Key) -> tuple[HarmonyFinding, ...]:
    chords = [parse_chord(symbol) for symbol in symbols]
    findings = [analyze_chord_in_key(chord, key) for chord in chords]
    for index in range(1, len(chords) - 1):
        chord = chords[index]
        if chord.quality != "diminished":
            continue
        previous_pc = chords[index - 1].root.pitch_class
        current_pc = chord.root.pitch_class
        next_pc = chords[index + 1].root.pitch_class
        if (current_pc - previous_pc) % 12 == 1 and (next_pc - current_pc) % 12 == 1:
            interpretations = tuple(dict.fromkeys(
                findings[index].possible_interpretations + ("possible chromatic passing diminished chord",)
            ))
            findings[index] = replace(findings[index], possible_interpretations=interpretations)
    return tuple(findings)
