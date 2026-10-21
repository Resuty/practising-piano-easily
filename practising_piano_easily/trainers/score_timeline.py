"""Shared beat/second/measure coordinates for notation and falling-note playback."""

from bisect import bisect_right
from dataclasses import dataclass
from functools import cached_property
import math


@dataclass(frozen=True)
class Measure:
    number: int
    start_beat: float
    end_beat: float
    numerator: int
    denominator: int


@dataclass(frozen=True)
class ScoreTimeline:
    # (quarter-note beat, seconds, seconds per quarter note)
    tempos: tuple[tuple[float, float, float], ...]
    signatures: tuple[tuple[float, int, int], ...]
    end_beat: float

    def __post_init__(self):
        if (not self.tempos or self.tempos[0][:2] != (0, 0) or not self.signatures or self.signatures[0][0] != 0
                or not math.isfinite(self.end_beat) or not 0 <= self.end_beat <= 100_000):
            raise ValueError("Invalid or oversized score timeline")
        if any(not all(math.isfinite(value) for value in tempo) or tempo[2] <= 0 for tempo in self.tempos):
            raise ValueError("Invalid score tempo map")
        if any(beat < 0 or not 1 <= numerator <= 255 or denominator not in (1, 2, 4, 8, 16, 32, 64, 128)
               for beat, numerator, denominator in self.signatures):
            raise ValueError("Invalid MIDI time signature")
        if (any(a[0] >= b[0] or a[1] >= b[1] for a, b in zip(self.tempos, self.tempos[1:]))
                or any(a[0] >= b[0] for a, b in zip(self.signatures, self.signatures[1:]))):
            raise ValueError("Score timeline events must be sorted")

    @cached_property
    def tempo_beats(self):
        return tuple(item[0] for item in self.tempos)

    @cached_property
    def tempo_seconds(self):
        return tuple(item[1] for item in self.tempos)

    def seconds_at(self, beat):
        start, seconds, duration = self.tempos[max(0, bisect_right(self.tempo_beats, beat) - 1)]
        return seconds + (beat - start) * duration

    def beat_at(self, seconds):
        start, begin, duration = self.tempos[max(0, bisect_right(self.tempo_seconds, seconds) - 1)]
        return start + (seconds - begin) / duration

    @cached_property
    def measures(self):
        result = []
        beat, signature = 0.0, 0
        while beat < max(0.01, self.end_beat) - 1e-8:
            while signature + 1 < len(self.signatures) and self.signatures[signature + 1][0] <= beat + 1e-8:
                signature += 1
            _, numerator, denominator = self.signatures[signature]
            end = beat + numerator * 4 / denominator
            if signature + 1 < len(self.signatures):
                end = min(end, self.signatures[signature + 1][0])
            result.append(Measure(len(result) + 1, beat, end, numerator, denominator))
            if len(result) > 10_000:
                raise ValueError("Too many measures for the synchronized score")
            beat = end
        return tuple(result)

    @cached_property
    def measure_starts(self):
        return tuple(measure.start_beat for measure in self.measures)

    def measure_index(self, seconds):
        beat = min(max(0, self.beat_at(seconds)), max(0, self.end_beat - 1e-8))
        return max(0, bisect_right(self.measure_starts, beat) - 1)
