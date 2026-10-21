"""Central, transparent mastery thresholds and adaptive weighting."""

from __future__ import annotations


MASTERY_THRESHOLDS = {
    "Familiar": {"attempts": 5, "accuracy": 0.80, "streak": 3},
    "Mastered": {"attempts": 10, "accuracy": 0.90, "streak": 5},
}


def mastery_status(attempts: int, correct: int, average_response_ms: float, streak: int) -> str:
    if attempts == 0:
        return "New"
    accuracy = correct / attempts
    mastered = MASTERY_THRESHOLDS["Mastered"]
    if (attempts >= mastered["attempts"] and accuracy >= mastered["accuracy"]
            and streak >= mastered["streak"]):
        return "Mastered"
    familiar = MASTERY_THRESHOLDS["Familiar"]
    if (attempts >= familiar["attempts"] and accuracy >= familiar["accuracy"]
            and streak >= familiar["streak"]):
        return "Familiar"
    return "Learning"


def adaptive_weight(recent_error_rate: float, average_response_ms: float) -> float:
    """Weak or slow items receive a larger, easy-to-explain sampling weight."""
    return 1.0 + 3.0 * min(max(recent_error_rate, 0.0), 1.0) + min(max(average_response_ms, 0.0) / 5_000, 2.0)
