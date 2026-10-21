"""MIDI-to-falling-note conversion with the full global tempo map, not just the first BPM."""

from bisect import bisect_right
from pathlib import Path

import mido

from .midi_file import load_midi
from .online_scores import MAX_BYTES
from practising_piano_easily.trainers.falling_notes import FallingNote, FallingScore
from practising_piano_easily.trainers.score_timeline import ScoreTimeline


def load_falling_midi(path: Path, track=None):
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("MIDI is too large for falling-note practice")
    try:
        midi = mido.MidiFile(path)
    except Exception as exc:
        raise ValueError(f"Malformed or unreadable MIDI file: {exc}") from exc
    if midi.type == 2 or midi.ticks_per_beat <= 0:
        raise ValueError("Falling notes require a synchronous, beat-based type 0 or type 1 MIDI")
    tempos = {0: 500_000}
    signatures = {0: (4, 4)}
    for midi_track in midi.tracks:
        tick = 0
        for event in midi_track:
            tick += event.time
            if event.type == "set_tempo":
                if event.tempo <= 0:
                    raise ValueError("MIDI tempo must be positive")
                tempos[tick] = event.tempo
            elif event.type == "time_signature":
                signatures[tick] = (event.numerator, event.denominator)
    summary = load_midi(midi)
    if len(summary.notes) > 100_000:
        raise ValueError("MIDI is too large for falling-note practice")
    ticks = sorted(tempos)
    times = [0.0]
    for previous, current in zip(ticks, ticks[1:]):
        times.append(times[-1] + (current - previous) * tempos[previous] / (1_000_000 * midi.ticks_per_beat))

    def seconds(tick):
        index = bisect_right(ticks, tick) - 1
        return times[index] + (tick - ticks[index]) * tempos[ticks[index]] / (1_000_000 * midi.ticks_per_beat)

    notes = tuple(FallingNote(note.note, seconds(note.start_tick), seconds(note.end_tick), f"track:{note.track}")
                  for note in summary.notes if note.channel != 9 and (track is None or note.track == track))
    end_tick = max((note.end_tick for note in summary.notes if note.channel != 9), default=0)
    timeline = ScoreTimeline(tuple((tick / midi.ticks_per_beat, time, tempos[tick] / 1_000_000) for tick, time in zip(ticks, times)),
                             tuple((tick / midi.ticks_per_beat, *signature) for tick, signature in sorted(signatures.items())),
                             end_tick / midi.ticks_per_beat)
    _ = timeline.measures  # Bound pathological tick ranges before building any GUI layout.
    return FallingScore(notes, timeline), summary
