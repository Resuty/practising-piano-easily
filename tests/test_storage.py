import json

from practising_piano_easily.storage import Database


def test_schema_session_attempt_and_settings_round_trip():
    database = Database(":memory:")
    session_id = database.start_session(15)
    attempt_id = database.record_attempt(
        session_id=session_id,
        trainer_type="chord_construction",
        skill="major_triad",
        question="C",
        expected="C E G",
        played="60 64 67",
        correct=True,
        response_time_ms=1250,
        metadata={"mode": "root_position"},
    )
    database.set_setting("curriculum_stage", "1")
    database.set_settings({"settling_ms": "350", "question_count": "20"})
    row = database.connection.execute("SELECT * FROM attempts WHERE id = ?", (attempt_id,)).fetchone()
    assert row["correct"] == 1
    assert json.loads(row["metadata_json"]) == {"mode": "root_position"}
    assert database.get_setting("curriculum_stage") == "1"
    assert database.get_setting("settling_ms") == "350"
    assert database.connection.execute("PRAGMA user_version").fetchone()[0] == 2
    mastery = database.connection.execute("SELECT * FROM mastery").fetchone()
    assert mastery["attempts"] == 1
    assert mastery["status"] == "Learning"
    database.end_session(session_id)
    assert database.connection.execute("SELECT ended_at FROM sessions").fetchone()[0]
    database.close()
