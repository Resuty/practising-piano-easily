"""SQL-backed dashboard/session summaries with suggestions based only on saved attempts."""

from __future__ import annotations

import json
from collections import Counter

from practising_piano_easily.core import parse_chord


def _attempt_rows(database, where: str = "", parameters: tuple = ()):
    return database.connection.execute(f"SELECT * FROM attempts {where} ORDER BY id", parameters).fetchall()


def dashboard_report(database) -> dict:
    attempts = _attempt_rows(database)
    sessions = database.connection.execute("SELECT * FROM sessions").fetchall()
    total = len(attempts)
    correct = sum(row["correct"] for row in attempts)
    roots = Counter()
    qualities = Counter()
    root_correct = Counter()
    quality_correct = Counter()
    skills = Counter()
    skill_correct = Counter()
    confusions = Counter()
    for row in attempts:
        skills[row["skill"]] += 1
        skill_correct[row["skill"]] += row["correct"]
        if row["trainer_type"] == "chord_construction":
            try:
                chord = parse_chord(row["question"])
            except ValueError:
                continue
            root, quality = str(chord.root), chord.quality
            roots[root] += 1
            qualities[quality] += 1
            root_correct[root] += row["correct"]
            quality_correct[quality] += row["correct"]
            metadata = json.loads(row["metadata_json"])
            if not row["correct"] and metadata.get("confusion"):
                confusions[metadata["confusion"]] += 1
    mastery = database.connection.execute("SELECT status, COUNT(*) count FROM mastery GROUP BY status").fetchall()
    return {
        "sessions": len(sessions),
        "practice_seconds": sum(
            max(0, database.connection.execute(
                "SELECT CAST((julianday(?) - julianday(?)) * 86400 AS INTEGER)",
                (row["ended_at"], row["started_at"]),
            ).fetchone()[0] or 0)
            for row in sessions if row["ended_at"]
        ),
        "attempts": total,
        "correct": correct,
        "accuracy": 100 * correct / total if total else 0.0,
        "average_response_ms": sum(row["response_time_ms"] for row in attempts) / total if total else 0.0,
        "last_7_days": database.connection.execute(
            "SELECT COUNT(*) FROM attempts WHERE datetime(timestamp) >= datetime('now', '-7 days')"
        ).fetchone()[0],
        "last_30_days": database.connection.execute(
            "SELECT COUNT(*) FROM attempts WHERE datetime(timestamp) >= datetime('now', '-30 days')"
        ).fetchone()[0],
        "root_accuracy": {root: 100 * root_correct[root] / count for root, count in roots.items()},
        "quality_accuracy": {quality: 100 * quality_correct[quality] / count for quality, count in qualities.items()},
        "skill_accuracy": {skill: 100 * skill_correct[skill] / count for skill, count in skills.items()},
        "confusions": confusions.most_common(5),
        "mastery": {row["status"]: row["count"] for row in mastery},
    }


def session_report(database, session_id: int) -> dict:
    current = _attempt_rows(database, "WHERE session_id = ?", (session_id,))
    total = len(current)
    correct = sum(row["correct"] for row in current)
    by_skill = Counter(row["skill"] for row in current)
    skill_correct = Counter()
    for row in current:
        skill_correct[row["skill"]] += row["correct"]
    accuracies = {skill: skill_correct[skill] / count for skill, count in by_skill.items()}
    wrong_questions = {row["question"] for row in current if not row["correct"]}
    earlier_wrong = {row[0] for row in database.connection.execute(
        "SELECT DISTINCT question FROM attempts WHERE session_id <> ? AND correct = 0", (session_id,)
    )}
    latest = {}
    for row in current:
        latest[row["question"]] = bool(row["correct"])
    earlier_latest = {
        row["question"]: bool(row["correct"]) for row in database.connection.execute(
            "SELECT * FROM attempts WHERE session_id <> ? ORDER BY id", (session_id,)
        )
    }
    weakest = min(accuracies, key=accuracies.get) if accuracies else None
    return {
        "attempts": total, "correct": correct,
        "accuracy": 100 * correct / total if total else 0.0,
        "average_response_ms": sum(row["response_time_ms"] for row in current) / total if total else 0.0,
        "best_skill": max(accuracies, key=accuracies.get) if accuracies else None,
        "weakest_skill": weakest,
        "new_mistakes": sorted(wrong_questions - earlier_wrong),
        "improved_items": sorted(question for question, ok in latest.items() if ok and earlier_latest.get(question) is False),
        "suggested_next_practice": f"Review {weakest}" if weakest else "Complete a short Stage 1 practice block",
    }


def daily_plan(minutes: int, stage: int, weakest_skill: str | None = None) -> tuple[tuple[str, int], ...]:
    if minutes not in {15, 30, 45}:
        raise ValueError("Daily plan must be 15, 30, or 45 minutes")
    if stage <= 2:
        return (("Read and listen to the current lesson", minutes // 3),
                ("Slow score practice", minutes // 3), ("Repeat or continue the course", minutes // 3))
    if minutes == 15:
        return (("Chord construction", 5), ("Ear training", 5), (weakest_skill or "Review", 5))
    base = (("Chord construction", 5), ("Inversion", 5), ("Diatonic harmony", 5),
            ("Progression", 5), ("Ear training", 5), (weakest_skill or "Review", 5))
    return base if minutes == 30 else base + (("Song analysis / composition", 10), ("Review notes", 5))
