import json
import sqlite3

import pytest

from engine.logger import ActivityEvent, ActivityLogger


@pytest.fixture
def tmp_db(tmp_path):
    return str(tmp_path / "test_presence.db")


def test_logger_creates_table_on_init(tmp_db):
    ActivityLogger(db_path=tmp_db, stdout=False)
    with sqlite3.connect(tmp_db) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='activity_log'"
        ).fetchone()
    assert row is not None


def test_log_activity_inserts_row(tmp_db):
    logger = ActivityLogger(db_path=tmp_db, stdout=False)
    event = ActivityEvent(
        activity="typing",
        persona="focused_writer",
        duration_s=42.5,
        metadata={"content_type": "email", "wpm": 70},
    )
    logger.log_activity(event)

    with sqlite3.connect(tmp_db) as conn:
        rows = conn.execute("SELECT activity, persona, duration_s, metadata FROM activity_log").fetchall()

    assert len(rows) == 1
    assert rows[0][0] == "typing"
    assert rows[0][1] == "focused_writer"
    assert rows[0][2] == 42.5
    assert json.loads(rows[0][3])["content_type"] == "email"


def test_log_activity_multiple_rows(tmp_db):
    logger = ActivityLogger(db_path=tmp_db, stdout=False)
    for activity in ["typing", "idle", "mouse", "dead_stop"]:
        logger.log_activity(ActivityEvent(
            activity=activity, persona="power_user", duration_s=10.0, metadata={}
        ))

    with sqlite3.connect(tmp_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
    assert count == 4


def test_log_activity_ts_is_iso8601(tmp_db):
    from datetime import datetime
    logger = ActivityLogger(db_path=tmp_db, stdout=False)
    logger.log_activity(ActivityEvent(
        activity="idle", persona="steady", duration_s=5.0, metadata={}
    ))
    with sqlite3.connect(tmp_db) as conn:
        ts = conn.execute("SELECT ts FROM activity_log").fetchone()[0]
    datetime.fromisoformat(ts)


def test_activity_event_defaults():
    event = ActivityEvent(activity="idle", persona="focused_writer", duration_s=5.0)
    assert event.metadata == {}


def test_logger_handles_sqlite_error_gracefully(tmp_db):
    ActivityLogger(db_path=tmp_db, stdout=False)
    broken_logger = ActivityLogger(db_path="/dev/null/impossible.db", stdout=False)
    # Should not raise
    broken_logger.log_activity(ActivityEvent(
        activity="idle", persona="focused_writer", duration_s=1.0, metadata={}
    ))
