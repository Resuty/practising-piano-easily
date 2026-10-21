"""Tempo-based falling-note practice; no UI, audio device or wall-clock dependency."""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from functools import cached_property
import math

from .midi_score import MidiScoreFollower
from .score_timeline import ScoreTimeline


@dataclass(frozen=True)
class FallingNote:
    pitch: int
    start: float
    end: float
    voice: str = "right"

    def __post_init__(self):
        if (not isinstance(self.pitch, int) or not 0 <= self.pitch <= 127 or not math.isfinite(self.start) or not math.isfinite(self.end)
                or self.start < 0 or self.end < self.start):
            raise ValueError("Invalid falling-note pitch or duration")


@dataclass(frozen=True)
class TimedGroup:
    time: float
    notes: frozenset[int]


@dataclass(frozen=True)
class FallingScore:
    notes: tuple[FallingNote, ...]
    timeline: ScoreTimeline | None = None
    span: float | None = None

    def __post_init__(self):
        if (not self.notes and self.span is None) or len(self.notes) > 100_000:
            raise ValueError("A falling score needs 1 to 100000 pitched notes")
        if self.span is not None and (not math.isfinite(self.span) or self.span <= 0
                                     or any(note.end > self.span + 1e-8 for note in self.notes)):
            raise ValueError("Invalid passage duration")
        if any(a.start > b.start for a, b in zip(self.notes, self.notes[1:])):
            raise ValueError("Falling notes must be sorted by onset")

    @cached_property
    def groups(self):
        groups = {}
        for note in self.notes:
            groups.setdefault(note.start, set()).add(note.pitch)
        return tuple(TimedGroup(time, frozenset(notes)) for time, notes in groups.items())

    @cached_property
    def starts(self):
        return tuple(note.start for note in self.notes)

    @cached_property
    def group_times(self):
        return tuple(group.time for group in self.groups)

    @cached_property
    def duration(self):
        return self.span if self.span is not None else max(0.1, max(note.end for note in self.notes))

    @cached_property
    def longest_note(self):
        return max((note.end - note.start for note in self.notes), default=0)

    def visible_notes(self, position, lookahead):
        first = bisect_left(self.starts, position - self.longest_note - 0.1)
        last = bisect_right(self.starts, position + lookahead)
        return tuple(note for note in self.notes[first:last] if note.end >= position)

    def practice_part(self, hand="both", split_note=60, track=-1):
        if hand not in {"both", "right", "left"} or not isinstance(split_note, int) or not 21 <= split_note <= 108:
            raise ValueError("Choose both, right or left hand and a split key from A0 to C8")
        if hand == "both" and track == -1:
            return self
        notes = tuple(note for note in self.notes
                      if (track == -1 or note.voice == f"track:{track}") and
                      (hand == "both" or (note.voice == hand if note.voice in {"right", "left"} else
                       track != -1 or (note.pitch >= split_note) == (hand == "right"))))
        # Keep the original duration and bar coordinates even when this hand has long rests or no notes.
        return FallingScore(notes, self.timeline, span=self.duration)

    def section(self, first, last):
        if not 1 <= first <= last <= len(self.groups):
            raise ValueError("Choose a valid first and last note group")
        start, end = self.groups[first - 1].time, self.groups[last - 1].time
        notes = tuple(FallingNote(note.pitch, max(0, note.start - start), max(0, note.end - start), note.voice)
                      for note in self.notes if start <= note.start <= end)
        return FallingScore(notes), start

    def measure_section(self, first, last):
        if self.timeline is None or not 1 <= first <= last <= len(self.timeline.measures):
            raise ValueError("Choose a valid first and last bar")
        start = self.timeline.seconds_at(self.timeline.measures[first - 1].start_beat)
        end = self.timeline.seconds_at(min(self.timeline.measures[last - 1].end_beat, self.timeline.end_beat))
        # Include tied-in notes as fresh attacks at the boundary; never extend beyond the chosen bars.
        notes = tuple(FallingNote(note.pitch, max(0, note.start - start), min(end, note.end) - start, note.voice)
                      for note in self.notes if note.start < end - 1e-8
                      and (note.end > start + 1e-8 or note.start >= start))
        return FallingScore(notes, span=end - start), start


def score_from_lesson(lesson, tempo=80):
    if not 20 <= tempo <= 300:
        raise ValueError("Tempo must be between 20 and 300")
    seconds = 60 / tempo
    beat, notes = 0, []
    for step in lesson.steps:
        for voice, pitches in (("right", step.right), ("left", step.left)):
            notes.extend(FallingNote(pitch, beat * seconds, (beat + step.beats) * seconds, voice) for pitch in pitches)
        beat += step.beats
    timeline = ScoreTimeline(((0, 0, seconds),), ((0, 4, 4),), beat)
    return FallingScore(tuple(notes), timeline)


class FallingSession:
    def __init__(self, score: FallingScore, *, preview=False, lead_in=3.0):
        self.score = score
        self.preview = preview
        self.position = -lead_in
        self.speed = 1.0
        self.running = False
        self.elapsed = 0.0
        self.follower = MidiScoreFollower(score.groups, allow_empty=not score.notes)

    @property
    def finished(self):
        return self.position >= self.score.duration and (self.preview or self.follower.finished)

    @property
    def waiting(self):
        return (not self.preview and not self.follower.finished
                and self.position >= self.score.groups[self.follower.index].time)

    def advance(self, elapsed):
        if not math.isfinite(elapsed) or elapsed < 0 or not 0.25 <= self.speed <= 2:
            raise ValueError("Invalid playback time or speed")
        if not self.running:
            return "paused"
        self.elapsed += elapsed
        target = self.position + elapsed * self.speed
        if not self.preview and not self.follower.finished:
            target = min(target, self.score.groups[self.follower.index].time)
        self.position = min(self.score.duration, target)
        if self.finished:
            self.running = False
            return "finished"
        return "waiting" if self.waiting else "playing"

    def event(self, event):
        if event.note is None:
            return "ignored"
        released = event.event_type == "note_off" or (event.event_type == "note_on" and event.velocity == 0)
        if released:
            return self.follower.event(event)
        if not self.running or self.preview or self.follower.finished:
            return "ignored"
        if self.position < self.score.groups[self.follower.index].time - 0.12:
            if event.event_type == "note_on":
                self.follower.held.add(event.note)
                return "early"
            return "ignored"
        return self.follower.event(event)
