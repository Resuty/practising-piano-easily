from types import SimpleNamespace

import numpy as np
import pytest
import sounddevice

from practising_piano_easily.audio.score_demo import ScoreDemoPlayer, ScoreRenderer
from practising_piano_easily.trainers.falling_notes import FallingNote, FallingScore


def peak_frequency(samples, rate=44_100):
    spectrum = abs(np.fft.rfft(samples))
    return np.fft.rfftfreq(len(samples), 1 / rate)[spectrum.argmax()]


@pytest.mark.parametrize("speed", [0.25, 1, 2])
def test_demo_renders_polyphony_rests_and_durations_without_transposing(speed):
    score = FallingScore((FallingNote(69, 1, 3), FallingNote(60, 1.5, 2)))
    renderer = ScoreRenderer(score, 0, speed, volume=.3)
    silence = renderer.render(round(.9 / speed * 44_100))
    assert np.count_nonzero(silence) == 0
    renderer.position = 1.1
    tone = renderer.render(8820)
    assert tone.dtype == np.float32 and max(abs(tone)) <= .3
    assert peak_frequency(tone) == pytest.approx(440, abs=5)
    renderer.position = 1.6
    chord = renderer.render(4410)
    spectrum = abs(np.fft.rfft(chord))
    freqs = np.fft.rfftfreq(len(chord), 1 / 44_100)
    for frequency in (261.63, 440):
        assert spectrum[abs(freqs - frequency).argmin()] > 10
    renderer.position = 3
    assert np.count_nonzero(renderer.render(1024)) == 0


def test_renderer_changes_tempo_live_and_buffers_only_requested_frames():
    renderer = ScoreRenderer(FallingScore((FallingNote(69, 0, 86_400),)), 1)
    first = renderer.render(1024)
    assert first.shape == (1024,)
    renderer.speed = 2
    second = renderer.render(1024)
    assert second.shape == (1024,)
    assert renderer.position == pytest.approx(1 + 3072 / 44_100)
    assert renderer.frames == 2048


class FakeStream:
    def __init__(self, **kwargs):
        self.callback = kwargs["callback"]
        self.active, self.time, self.closed = False, 0., False
        self.kwargs = kwargs

    def start(self):
        self.active = True

    def abort(self):
        self.active = False

    def close(self):
        self.closed = True


@pytest.fixture
def stream_factory(monkeypatch):
    streams = []
    def create(**kwargs):
        stream = FakeStream(**kwargs)
        streams.append(stream)
        return stream
    monkeypatch.setattr(sounddevice, "OutputStream", create)
    monkeypatch.setattr(sounddevice, "stop", lambda: None)
    return streams


def test_stream_clock_tracks_audible_samples_not_future_queued_buffers(stream_factory):
    player = ScoreDemoPlayer()
    score = FallingScore((FallingNote(69, 0, 5),))
    player.start(score, -3, 1, .25, None)
    stream = stream_factory[-1]
    assert player.position == -3
    output = np.empty((1024, 1), dtype=np.float32)
    stream.callback(output, 1024, SimpleNamespace(outputBufferDacTime=10.), None)
    stream.callback(output, 1024, SimpleNamespace(outputBufferDacTime=10. + 1024 / 44_100), None)
    stream.time = 9.9
    assert player.position == -3
    stream.time = 10.01
    assert player.position == pytest.approx(-2.99)
    player.stop()
    assert player.stream is None and stream.closed and not stream.active
    player.start(score, 1.25, .5, .1, 4)
    assert player.position == 1.25 and player.renderer.speed == .5
    assert stream_factory[-1].kwargs["device"] == 4
    player.stop()


def test_failed_stream_start_and_callback_release_resources(stream_factory, monkeypatch):
    player = ScoreDemoPlayer()
    score = FallingScore((FallingNote(60, 0, 1),))
    monkeypatch.setattr(FakeStream, "start", lambda self: (_ for _ in ()).throw(RuntimeError("device removed")))
    with pytest.raises(RuntimeError, match="device removed"):
        player.start(score, 0, 1, .25, None)
    assert player.stream is None and stream_factory[-1].closed
    monkeypatch.setattr(FakeStream, "start", lambda self: setattr(self, "active", True))
    player.start(score, 0, 1, .25, None)
    monkeypatch.setattr(player.renderer, "render", lambda *args: (_ for _ in ()).throw(RuntimeError("render error")))
    output = np.ones((1024, 1), dtype=np.float32)
    with pytest.raises(sounddevice.CallbackAbort):
        player._callback(output, 1024, SimpleNamespace(outputBufferDacTime=0), None)
    assert not output.any()
    with pytest.raises(RuntimeError, match="render error"):
        _ = player.position
    player.stop()
