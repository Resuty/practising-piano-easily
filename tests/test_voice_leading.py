import pytest

from practising_piano_easily.core import measure_progression, measure_voice_leading


def test_objective_voice_leading_metrics():
    metrics = measure_voice_leading((50, 53, 57, 60), (50, 53, 55, 59))
    assert metrics.total_movement == 3
    assert metrics.largest_leap == 2
    assert metrics.common_tones_retained == 2
    assert sorted(metrics.movements) == [0, 0, 1, 2]


def test_progression_and_unequal_voice_counts():
    metrics = measure_progression([(50, 53, 57, 60), (50, 53, 55, 59), (48, 52, 55, 59)])
    assert len(metrics) == 2
    assert sum(item.total_movement for item in metrics) == 6
    reduced = measure_voice_leading((48, 52, 55, 60), (50, 55, 59))
    assert len(reduced.movements) == 3


def test_empty_voicing_is_rejected():
    with pytest.raises(ValueError, match="non-empty"):
        measure_voice_leading((), (60,))
