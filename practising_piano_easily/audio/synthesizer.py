"""Small additive synthesizer: clear pitch without external samples."""

from __future__ import annotations

import numpy as np


def midi_frequency(note: int) -> float:
    return 440.0 * 2 ** ((note - 69) / 12)


class Synthesizer:
    def __init__(self, sample_rate: int = 44_100, device: int | str | None = None) -> None:
        self.sample_rate = sample_rate
        self.device = device

    def render(self, notes: tuple[int, ...] | list[int], duration: float = 0.8, volume: float = 0.25) -> np.ndarray:
        if not notes:
            raise ValueError("At least one note is required")
        frame_count = max(1, round(duration * self.sample_rate))
        time = np.arange(frame_count, dtype=np.float64) / self.sample_rate
        signal = np.zeros(frame_count, dtype=np.float64)
        for note in notes:
            frequency = midi_frequency(note)
            signal += (
                np.sin(2 * np.pi * frequency * time)
                + 0.32 * np.sin(2 * np.pi * frequency * 2 * time)
                + 0.12 * np.sin(2 * np.pi * frequency * 3 * time)
            )
        signal /= len(notes) * 1.44
        signal *= self._envelope(frame_count, duration)
        return (signal * min(max(volume, 0.0), 1.0)).astype(np.float32)

    def render_sequence(self, groups: tuple[tuple[int, ...], ...], duration: float = 0.65,
                        gap: float = 0.12, volume: float = 0.25) -> np.ndarray:
        silence = np.zeros(round(gap * self.sample_rate), dtype=np.float32)
        parts = []
        for index, group in enumerate(groups):
            if index:
                parts.append(silence)
            parts.append(self.render(group, duration, volume))
        return np.concatenate(parts)

    def play(self, groups: tuple[tuple[int, ...], ...], volume: float = 0.25) -> None:
        import sounddevice

        sounddevice.play(self.render_sequence(groups, volume=volume), self.sample_rate, device=self.device)

    def render_score(self, groups, tempo: int = 80, volume: float = 0.25) -> np.ndarray:
        if not 20 <= tempo <= 300 or not groups:
            raise ValueError("A score needs notes and a tempo between 20 and 300")
        parts = []
        for notes, beats in groups:
            if beats <= 0:
                raise ValueError("Note durations must be positive")
            frames = round(beats * 60 / tempo * self.sample_rate)
            sounding = self.render(notes, duration=beats * 60 / tempo * 0.9, volume=volume)
            parts.append(np.pad(sounding, (0, frames - len(sounding))))
        return np.concatenate(parts)

    def play_score(self, groups, tempo: int = 80, volume: float = 0.25) -> None:
        import sounddevice

        sounddevice.play(self.render_score(groups, tempo, volume), self.sample_rate, device=self.device)

    def _envelope(self, frames: int, duration: float) -> np.ndarray:
        attack = min(round(0.02 * self.sample_rate), frames)
        decay = min(round(0.08 * self.sample_rate), max(0, frames - attack))
        release = min(round(0.15 * self.sample_rate), max(0, frames - attack - decay))
        sustain = max(0, frames - attack - decay - release)
        return np.concatenate((
            np.linspace(0, 1, attack, endpoint=False),
            np.linspace(1, 0.72, decay, endpoint=False),
            np.full(sustain, 0.72),
            np.linspace(0.72, 0, release, endpoint=True),
        ))[:frames]
