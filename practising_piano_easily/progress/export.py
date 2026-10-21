"""Portable attempt exports; SQLite remains the source of truth."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import TextIO


def attempt_rows(database) -> list[dict]:
    rows = []
    for row in database.connection.execute("SELECT * FROM attempts ORDER BY id"):
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json"))
        rows.append(item)
    return rows


def export_attempts_csv(database, destination: str | Path | TextIO) -> Path | None:
    rows = attempt_rows(database)
    fieldnames = list(rows[0]) if rows else [
        "id", "timestamp", "session_id", "trainer_type", "skill", "question",
        "expected", "played", "correct", "response_time_ms", "difficulty", "metadata",
    ]
    should_close = not hasattr(destination, "write")
    path = Path(destination) if should_close else None
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("w", newline="", encoding="utf-8-sig")
    else:
        handle = destination
    try:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            row = {**row, "metadata": json.dumps(row["metadata"], ensure_ascii=False, sort_keys=True)}
            writer.writerow(row)
    finally:
        if should_close:
            handle.close()
    return path

def export_attempts_json(database, destination: str | Path | TextIO) -> Path | None:
    should_close = not hasattr(destination, "write")
    path = Path(destination) if should_close else None
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("w", encoding="utf-8")
    else:
        handle = destination
    try:
        json.dump(attempt_rows(database), handle, ensure_ascii=False, indent=2)
    finally:
        if should_close:
            handle.close()
    return path
