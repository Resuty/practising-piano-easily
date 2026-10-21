"""Objective voice-leading measurements; no aesthetic good/bad labels."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, permutations


@dataclass(frozen=True)
class VoiceLeadingMetrics:
    total_movement: int
    largest_leap: int
    common_tones_retained: int
    movements: tuple[int, ...]


def measure_voice_leading(first: tuple[int, ...] | list[int],
                          second: tuple[int, ...] | list[int]) -> VoiceLeadingMetrics:
    if not first or not second:
        raise ValueError("Two non-empty voicings are required")
    source = tuple(sorted(first))
    target = tuple(sorted(second))
    pairings = []
    if len(source) <= len(target):
        for chosen in combinations(target, len(source)):
            pairings.extend(tuple(zip(source, order)) for order in permutations(chosen))
    else:
        for chosen in combinations(source, len(target)):
            pairings.extend(tuple(zip(order, target)) for order in permutations(chosen))
    best = min(
        pairings,
        key=lambda pairs: (
            sum(abs(a - b) for a, b in pairs),
            max(abs(a - b) for a, b in pairs),
        ),
    )
    movements = tuple(abs(a - b) for a, b in best)
    return VoiceLeadingMetrics(
        total_movement=sum(movements),
        largest_leap=max(movements),
        common_tones_retained=sum(a % 12 == b % 12 for a, b in best),
        movements=movements,
    )


def measure_progression(voicings: list[tuple[int, ...]]) -> tuple[VoiceLeadingMetrics, ...]:
    if len(voicings) < 2:
        return ()
    return tuple(measure_voice_leading(first, second) for first, second in zip(voicings, voicings[1:]))
