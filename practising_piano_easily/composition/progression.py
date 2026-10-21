"""Minimal progression model and deterministic MIDI export."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import mido

from practising_piano_easily.core import Key, HarmonyFinding, analyze_progression, measure_progression, parse_chord


@dataclass(frozen=True)
class ProgressionChord:
    symbol: str
    duration_beats: float = 4.0
    inversion: int = 0
    octave: int = 3
    velocity: int = 80

    def __post_init__(self) -> None:
        chord = parse_chord(self.symbol)
        if self.duration_beats <= 0:
            raise ValueError("Chord duration must be positive")
        if not 0 <= self.inversion < len(chord.notes):
            raise ValueError(f"Inversion must be 0–{len(chord.notes) - 1} for {chord.symbol}")
        if not 0 <= self.octave <= 8 or not 1 <= self.velocity <= 127:
            raise ValueError("Octave must be 0–8 and velocity must be 1–127")


@dataclass
class Progression:
    chords: list[ProgressionChord] = field(default_factory=list)

    def add(self, chord: ProgressionChord) -> None:
        self.chords.append(chord)

    def remove(self, index: int) -> None:
        del self.chords[index]

    def move(self, index: int, offset: int) -> None:
        destination = index + offset
        if not 0 <= destination < len(self.chords):
            return
        self.chords[index], self.chords[destination] = self.chords[destination], self.chords[index]


def make_voicing(item: ProgressionChord) -> tuple[int, ...]:
    chord = parse_chord(item.symbol)
    root_midi = (item.octave + 1) * 12 + chord.root.pitch_class
    notes = []
    for formula, note in zip(chord.formula, chord.notes):
        distance = (note.pitch_class - chord.root.pitch_class) % 12
        if int(formula.lstrip("b#")) > 7:
            distance += 12
        notes.append(root_midi + distance)
    for _ in range(item.inversion):
        notes.append(notes.pop(0) + 12)
    if chord.bass:
        bass = (item.octave + 1) * 12 + chord.bass.pitch_class
        while bass >= min(notes):
            bass -= 12
        notes.insert(0, bass)
    if any(note < 0 or note > 127 for note in notes):
        raise ValueError(f"Voicing for {item.symbol} exceeds the MIDI range")
    return tuple(notes)


@dataclass(frozen=True)
class CompositionReport:
    harmony: tuple[HarmonyFinding, ...]
    voicings: tuple[tuple[int, ...], ...]
    voice_leading: tuple


def analyze_composition(progression: Progression, key: Key) -> CompositionReport:
    if not progression.chords:
        raise ValueError("Add at least one chord")
    voicings = tuple(make_voicing(item) for item in progression.chords)
    return CompositionReport(
        harmony=analyze_progression([item.symbol for item in progression.chords], key),
        voicings=voicings,
        voice_leading=measure_progression(list(voicings)),
    )


def build_midi(progression: Progression, tempo_bpm: int = 120) -> mido.MidiFile:
    if not progression.chords:
        raise ValueError("Add at least one chord")
    if not 20 <= tempo_bpm <= 300:
        raise ValueError("Tempo must be between 20 and 300 BPM")
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name="practising piano easily progression", time=0))
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(tempo_bpm), time=0))
    track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    for item in progression.chords:
        notes = make_voicing(item)
        for note in notes:
            track.append(mido.Message("note_on", note=note, velocity=item.velocity, time=0))
        duration = max(1, round(item.duration_beats * midi.ticks_per_beat))
        for index, note in enumerate(notes):
            track.append(mido.Message("note_off", note=note, velocity=0, time=duration if index == 0 else 0))
    return midi


def export_midi(progression: Progression, path: str | Path, tempo_bpm: int = 120) -> Path:
    path = Path(path)
    if path.suffix.lower() not in {".mid", ".midi"}:
        path = path.with_suffix(".mid")
    path.parent.mkdir(parents=True, exist_ok=True)
    build_midi(progression, tempo_bpm).save(path)
    return path
