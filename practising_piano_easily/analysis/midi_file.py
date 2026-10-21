"""Conservative MIDI parsing and heuristic candidates labelled as scores."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import mido

from practising_piano_easily.core import parse_chord, scale_notes


ROOTS = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
CANDIDATE_SUFFIXES = ("", "m", "dim", "aug", "maj7", "7", "m7", "m7b5", "dim7", "6", "m6")


@dataclass(frozen=True)
class MidiNoteEvent:
    track: int
    start_tick: int
    end_tick: int
    note: int
    velocity: int
    channel: int


@dataclass(frozen=True)
class MidiFileSummary:
    path: str
    tracks: int
    ticks_per_beat: int
    tempo_bpm: float
    time_signature: str
    notes: tuple[MidiNoteEvent, ...]

    @property
    def duration_ticks(self) -> int:
        return max((note.end_tick for note in self.notes), default=0)

    @property
    def note_range(self) -> tuple[int, int] | None:
        return (min(note.note for note in self.notes), max(note.note for note in self.notes)) if self.notes else None


def load_midi(source: str | Path | mido.MidiFile) -> MidiFileSummary:
    try:
        midi = source if isinstance(source, mido.MidiFile) else mido.MidiFile(source)
    except Exception as exc:
        raise ValueError(f"Malformed or unreadable MIDI file: {exc}") from exc
    notes = []
    tempo_bpm = 120.0
    time_signature = "4/4"
    tempo_seen = False
    signature_seen = False
    for track_index, track in enumerate(midi.tracks):
        tick = 0
        active: dict[tuple[int, int], list[tuple[int, int]]] = {}
        for message in track:
            tick += int(message.time)
            if message.type == "set_tempo" and not tempo_seen:
                tempo_bpm = float(mido.tempo2bpm(message.tempo))
                tempo_seen = True
            elif message.type == "time_signature" and not signature_seen:
                time_signature = f"{message.numerator}/{message.denominator}"
                signature_seen = True
            elif message.type == "note_on" and message.velocity > 0:
                active.setdefault((message.channel, message.note), []).append((tick, message.velocity))
            elif message.type in {"note_off", "note_on"}:
                stack = active.get((message.channel, message.note), [])
                if stack:
                    start, velocity = stack.pop(0)
                    notes.append(MidiNoteEvent(track_index, start, tick, message.note, velocity, message.channel))
        for (channel, note), stack in active.items():
            notes.extend(MidiNoteEvent(track_index, start, tick, note, velocity, channel) for start, velocity in stack)
    return MidiFileSummary(
        path=str(getattr(midi, "filename", source if not isinstance(source, mido.MidiFile) else "<memory>")),
        tracks=len(midi.tracks), ticks_per_beat=midi.ticks_per_beat,
        tempo_bpm=tempo_bpm, time_signature=time_signature,
        notes=tuple(sorted(notes, key=lambda item: (item.start_tick, item.track, item.note))),
    )


def note_windows(summary: MidiFileSummary, window_ticks: int | None = None) -> tuple[tuple[int, ...], ...]:
    window_ticks = window_ticks or summary.ticks_per_beat
    if window_ticks <= 0:
        raise ValueError("Window size must be positive")
    count = max(1, (summary.duration_ticks + window_ticks - 1) // window_ticks)
    return tuple(
        tuple(sorted({note.note for note in summary.notes
                      if note.start_tick < (index + 1) * window_ticks and note.end_tick > index * window_ticks}))
        for index in range(count)
    )


@dataclass(frozen=True)
class ChordCandidate:
    symbol: str
    score: float
    missing: tuple[int, ...]
    extra: tuple[int, ...]


def chord_candidates(midi_notes: tuple[int, ...] | list[int] | set[int], limit: int = 6, *, suffixes=CANDIDATE_SUFFIXES) -> tuple[ChordCandidate, ...]:
    if not midi_notes:
        return ()
    played = {note % 12 for note in midi_notes}
    bass = min(midi_notes) % 12
    candidates = []
    for root in ROOTS:
        for suffix in suffixes:
            chord = parse_chord(root + suffix)
            expected = set(chord.pitch_classes)
            matched = len(expected & played)
            coverage = matched / len(expected)
            precision = matched / len(played)
            score = round(0.65 * coverage + 0.35 * precision, 3)
            symbol = chord.symbol
            if bass != chord.root.pitch_class and bass in expected:
                bass_name = next(candidate for candidate in ROOTS if parse_chord(candidate).root.pitch_class == bass)
                symbol += f"/{bass_name}"
            candidates.append(ChordCandidate(symbol, score, tuple(sorted(expected - played)), tuple(sorted(played - expected))))
    candidates.sort(key=lambda item: (-item.score, len(item.missing) + len(item.extra), len(item.symbol), item.symbol))
    unique = {}
    for candidate in candidates:
        unique.setdefault(candidate.symbol, candidate)
    return tuple(list(unique.values())[:limit])


@dataclass(frozen=True)
class KeyCandidate:
    key: str
    score: float


def key_candidates(pitch_classes: set[int] | frozenset[int], limit: int = 5) -> tuple[KeyCandidate, ...]:
    if not pitch_classes:
        return ()
    results = []
    for root in ROOTS:
        for mode, scale_type in (("major", "major"), ("minor", "natural_minor")):
            scale = {note.pitch_class for note in scale_notes(root, scale_type)}
            inside = len(pitch_classes & scale) / len(pitch_classes)
            tonic = parse_chord(root).root.pitch_class
            fifth = (tonic + 7) % 12
            score = inside + (0.10 if tonic in pitch_classes else 0) + (0.05 if fifth in pitch_classes else 0)
            results.append(KeyCandidate(f"{root} {mode}", round(score, 3)))
    return tuple(sorted(results, key=lambda item: (-item.score, item.key))[:limit])

