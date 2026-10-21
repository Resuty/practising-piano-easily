"""Bounded-buffer, polyphonic demonstration using the existing additive timbre."""

from collections import deque

import numpy as np

from .synthesizer import midi_frequency


class ScoreRenderer:
    def __init__(self, score, position, speed=1.0, volume=0.25, sample_rate=44_100):
        self.score, self.position, self.speed = score, position, speed
        self.volume, self.sample_rate = min(1, max(0, volume)), sample_rate
        self.frames = 0
        # Prepare the score's search indexes outside the audio callback.
        _ = score.starts, score.longest_note

    def render(self, frames, speed=None):
        speed = self.speed if speed is None else speed
        offsets = np.arange(frames) / self.sample_rate
        positions = self.position + offsets * speed
        phase_time = (self.frames + np.arange(frames)) / self.sample_rate
        signal = np.zeros(frames)
        voices = np.zeros(frames)
        for note in self.score.visible_notes(self.position, frames / self.sample_rate * speed):
            active = (positions >= note.start) & (positions < note.end)
            if not active.any():
                continue
            age = np.maximum(0, (positions - note.start) / speed)
            remaining = np.maximum(0, (note.end - positions) / speed)
            envelope = np.minimum(1, age / 0.02) * np.minimum(1, remaining / 0.05)
            envelope *= 0.72 + 0.28 * np.exp(-age / 0.08)
            phase = 2 * np.pi * midi_frequency(note.pitch) * phase_time
            signal += (np.sin(phase) + 0.32 * np.sin(2 * phase) + 0.12 * np.sin(3 * phase)) * envelope * active
            voices += active
        signal /= np.maximum(1, voices) * 1.44
        self.position += frames / self.sample_rate * speed
        self.frames += frames
        return (signal * self.volume).astype(np.float32)


class ScoreDemoPlayer:
    def __init__(self):
        self.stream = None
        self.renderer = None
        self.error = None
        self._blocks = deque(maxlen=64)
        self._start_position = 0.0

    def start(self, score, position, speed, volume, device):
        import sounddevice

        self.stop()
        self.error = None
        self._blocks.clear()
        self._start_position = position
        self.renderer = ScoreRenderer(score, position, speed, volume)
        try:
            # Stop the app's one-shot tutorial/ear-training sounds before demonstrating.
            sounddevice.stop()
            self.stream = sounddevice.OutputStream(samplerate=self.renderer.sample_rate, channels=1,
                dtype="float32", blocksize=1024, latency="low", device=device, callback=self._callback)
            self.stream.start()
        except Exception:
            self.stop()
            raise

    def _callback(self, outdata, frames, timing, status):
        import sounddevice

        position, speed = self.renderer.position, self.renderer.speed
        try:
            outdata[:, 0] = self.renderer.render(frames, speed)
            self._blocks.append((timing.outputBufferDacTime, position, speed, frames / self.renderer.sample_rate))
        except Exception as exc:
            outdata.fill(0)
            self.error = str(exc)
            raise sounddevice.CallbackAbort from exc

    @property
    def position(self):
        if self.error:
            raise RuntimeError(self.error)
        if not self.stream.active:
            raise RuntimeError("Audio stream stopped")
        now = self.stream.time
        # The score follows the samples reaching the speakers, not the queued buffer end.
        for timestamp, position, speed, duration in reversed(tuple(self._blocks)):
            if timestamp <= now:
                return position + min(duration, now - timestamp) * speed
        return self._start_position

    def stop(self):
        stream, self.stream = self.stream, None
        if stream is not None:
            try:
                stream.abort()
            finally:
                stream.close()
