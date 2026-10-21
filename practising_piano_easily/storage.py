"""SQLite persistence and the deliberately simple initial schema."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
 id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, ended_at TEXT, preset_minutes INTEGER
);
CREATE TABLE IF NOT EXISTS skills (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS items (
 id INTEGER PRIMARY KEY, skill_id INTEGER NOT NULL REFERENCES skills(id),
 item_key TEXT NOT NULL, difficulty INTEGER NOT NULL DEFAULT 1, UNIQUE(skill_id, item_key)
);
CREATE TABLE IF NOT EXISTS attempts (
 id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, session_id INTEGER REFERENCES sessions(id),
 trainer_type TEXT NOT NULL, skill TEXT NOT NULL, question TEXT NOT NULL,
 expected TEXT NOT NULL, played TEXT NOT NULL,
 correct INTEGER NOT NULL CHECK(correct IN (0, 1)),
 response_time_ms INTEGER NOT NULL CHECK(response_time_ms >= 0),
 difficulty INTEGER NOT NULL DEFAULT 1, metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS mastery (
 item_id INTEGER PRIMARY KEY REFERENCES items(id), attempts INTEGER NOT NULL DEFAULT 0,
 correct INTEGER NOT NULL DEFAULT 0, average_response_ms REAL NOT NULL DEFAULT 0,
 streak INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'New', last_practiced TEXT
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
PRAGMA user_version = 1;
"""


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA busy_timeout = 3000")
        if path != ":memory:":
            self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.executescript(SCHEMA)
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(mastery)")}
        if "recent_error_rate" not in columns:
            self.connection.execute("ALTER TABLE mastery ADD COLUMN recent_error_rate REAL NOT NULL DEFAULT 0")
        self.connection.execute("PRAGMA user_version = 2")
        # Refresh derived labels under the current rules, preserving all practice history.
        from practising_piano_easily.progress.mastery import mastery_status

        for row in self.connection.execute("SELECT * FROM mastery").fetchall():
            status = mastery_status(row["attempts"], row["correct"], row["average_response_ms"], row["streak"])
            if status != row["status"]:
                self.connection.execute("UPDATE mastery SET status=? WHERE item_id=?", (status, row["item_id"]))
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def start_session(self, preset_minutes: int | None = None) -> int:
        cursor = self.connection.execute(
            "INSERT INTO sessions(started_at, preset_minutes) VALUES (?, ?)", (now_iso(), preset_minutes)
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def end_session(self, session_id: int) -> None:
        self.connection.execute("UPDATE sessions SET ended_at = ? WHERE id = ?", (now_iso(), session_id))
        self.connection.commit()

    def record_attempt(self, *, session_id: int, trainer_type: str, skill: str, question: str,
                       expected: str, played: str, correct: bool, response_time_ms: int,
                       difficulty: int = 1, metadata: dict[str, Any] | None = None) -> int:
        from practising_piano_easily.progress.mastery import mastery_status

        with self.connection:
            cursor = self.connection.execute(
                """INSERT INTO attempts(timestamp, session_id, trainer_type, skill, question,
                   expected, played, correct, response_time_ms, difficulty, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (now_iso(), session_id, trainer_type, skill, question, expected, played,
                 int(correct), response_time_ms, difficulty,
                 json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)),
            )
            self.connection.execute("INSERT OR IGNORE INTO skills(name) VALUES (?)", (skill,))
            skill_id = self.connection.execute("SELECT id FROM skills WHERE name = ?", (skill,)).fetchone()[0]
            self.connection.execute(
                "INSERT OR IGNORE INTO items(skill_id, item_key, difficulty) VALUES (?, ?, ?)",
                (skill_id, question, difficulty),
            )
            item_id = self.connection.execute(
                "SELECT id FROM items WHERE skill_id = ? AND item_key = ?", (skill_id, question)
            ).fetchone()[0]
            old = self.connection.execute("SELECT * FROM mastery WHERE item_id = ?", (item_id,)).fetchone()
            attempts = (old["attempts"] if old else 0) + 1
            correct_count = (old["correct"] if old else 0) + int(correct)
            average = (((old["average_response_ms"] if old else 0) * (attempts - 1)) + response_time_ms) / attempts
            streak = (old["streak"] + 1 if old and correct else 1 if correct else 0)
            error_rate = (old["recent_error_rate"] * 0.7 if old else 0) + (0 if correct else 0.3)
            status = mastery_status(attempts, correct_count, average, streak)
            self.connection.execute(
                """INSERT INTO mastery(item_id, attempts, correct, average_response_ms, streak, status,
                   last_practiced, recent_error_rate) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(item_id) DO UPDATE SET attempts=excluded.attempts, correct=excluded.correct,
                   average_response_ms=excluded.average_response_ms, streak=excluded.streak,
                   status=excluded.status, last_practiced=excluded.last_practiced,
                   recent_error_rate=excluded.recent_error_rate""",
                (item_id, attempts, correct_count, average, streak, status, now_iso(), error_rate),
            )
        return int(cursor.lastrowid)

    def set_session_preset(self, session_id: int, minutes: int) -> None:
        self.connection.execute("UPDATE sessions SET preset_minutes = ? WHERE id = ?", (minutes, session_id))
        self.connection.commit()

    def mastery_for_skill(self, skill: str) -> dict[str, tuple[float, float]]:
        rows = self.connection.execute(
            """SELECT i.item_key, m.recent_error_rate, m.average_response_ms
               FROM items i JOIN skills s ON s.id=i.skill_id JOIN mastery m ON m.item_id=i.id
               WHERE s.name=?""", (skill,)
        )
        return {row["item_key"]: (row["recent_error_rate"], row["average_response_ms"]) for row in rows}

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return str(row[0]) if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.connection.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.connection.commit()

    def set_settings(self, values: dict[str, str]) -> None:
        with self.connection:
            self.connection.executemany(
                "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                values.items(),
            )
