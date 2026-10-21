import io
import json

from practising_piano_easily.progress import (
    adaptive_weight, daily_plan, dashboard_report, export_attempts_csv, export_attempts_json,
    mastery_status, session_report,
)
from practising_piano_easily.storage import Database


def test_mastery_thresholds_and_adaptive_weight_are_transparent():
    assert mastery_status(0, 0, 0, 0) == "New"
    assert mastery_status(3, 2, 3000, 2) == "Learning"
    assert mastery_status(5, 4, 3500, 3) == "Familiar"
    assert mastery_status(10, 9, 2000, 5) == "Mastered"
    assert mastery_status(10, 9, 120_000, 5) == "Mastered"
    assert mastery_status(5, 4, 120_000, 3) == "Familiar"
    assert adaptive_weight(0.8, 6000) > adaptive_weight(0.1, 1500)


def test_session_report_and_daily_plans_use_actual_attempts():
    database = Database(":memory:")
    session_id = database.start_session(15)
    for question, correct in (("C", True), ("Dm", False)):
        database.record_attempt(
            session_id=session_id, trainer_type="chord_construction", skill="chord_level_1",
            question=question, expected="", played="", correct=correct, response_time_ms=2000,
        )
    report = session_report(database, session_id)
    assert report["attempts"] == 2
    assert report["accuracy"] == 50
    assert report["new_mistakes"] == ["Dm"]
    assert daily_plan(15, 1)[0] == ("Read and listen to the current lesson", 5)
    assert daily_plan(30, 1) != daily_plan(30, 10)
    assert sum(minutes for _, minutes in daily_plan(45, 1)) == 45
    csv_output = io.StringIO()
    json_output = io.StringIO()
    export_attempts_csv(database, csv_output)
    export_attempts_json(database, json_output)
    assert "chord_level_1" in csv_output.getvalue()
    assert len(json.loads(json_output.getvalue())) == 2
    database.close()


def test_database_updates_mastery_recent_error_and_dashboard_confusions():
    database = Database(":memory:")
    session_id = database.start_session()
    for index in range(10):
        database.record_attempt(
            session_id=session_id, trainer_type="chord_construction", skill="chord_level_1",
            question="C", expected="C E G", played="60 64 67", correct=True,
            response_time_ms=2000, metadata={"confusion": None},
        )
    database.record_attempt(
        session_id=session_id, trainer_type="chord_construction", skill="chord_level_1",
        question="Dm", expected="D F A", played="62 66 69", correct=False,
        response_time_ms=5000, metadata={"confusion": "minor → major"},
    )
    rows = database.connection.execute("SELECT status, recent_error_rate FROM mastery ORDER BY item_id").fetchall()
    assert rows[0]["status"] == "Mastered"
    assert rows[1]["recent_error_rate"] == 0.3
    report = dashboard_report(database)
    assert report["confusions"] == [("minor → major", 1)]
    assert report["root_accuracy"]["C"] == 100
    database.close()
