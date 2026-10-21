import random

import numpy as np
import pytest

from practising_piano_easily.audio import Synthesizer, midi_frequency
from practising_piano_easily.trainers.ear_training import EarTrainer


def test_synthesizer_pitch_shape_envelope_and_volume():
    synth = Synthesizer(sample_rate=8000)
    audio = synth.render((69,), duration=0.2, volume=0.4)
    assert midi_frequency(69) == 440.0
    assert audio.dtype == np.float32
    assert audio.shape == (1600,)
    assert audio[0] == pytest.approx(0.0)
    assert audio[-1] == pytest.approx(0.0, abs=1e-6)
    assert 0 < np.max(np.abs(audio)) <= 0.4


def test_sequence_contains_gap_and_all_questions_have_valid_answers():
    synth = Synthesizer(sample_rate=1000)
    sequence = synth.render_sequence(((60,), (64,)), duration=0.1, gap=0.05)
    assert sequence.shape == (250,)
    trainer = EarTrainer(random.Random(3))
    for kind in ("Interval", "Major vs minor", "Triad quality", "Seventh quality",
                 "Inversion", "Bass note", "Root movement", "Cadence", "Mixed (Stage 1)"):
        question = trainer.question(kind)
        assert question.answer in question.options
        assert question.groups and all(question.groups)
