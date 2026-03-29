import sqlite3
import threading
import time

from engine.activity_selector import ActivitySelector
from engine.logger import ActivityLogger
from engine.scheduler import run_engine
from engine.status import ConfigStore, EngineControl, StatusStore

SMOKE_CONFIG = {
    "persona": "focused_writer",
    "dead_zones": [],
    "time_profiles": {
        "typing":    [0.4] * 24,
        "mouse":     [0.2] * 24,
        "idle":      [0.3] * 24,
        "dead_stop": [0.1] * 24,
    },
    "personas": {
        "focused_writer": {
            "typing_mean_s": 2, "typing_stddev_s": 0.5,
            "mouse_lambda": 2.0, "idle_lambda": 2.0, "wpm": 60,
        },
        "custom": {
            "typing_mean_s": 2, "typing_stddev_s": 0.5,
            "mouse_lambda": 2.0, "idle_lambda": 2.0, "wpm": 60,
        },
    },
    "claude": {
        "model": "claude-sonnet-4-20250514",
        "content_types": ["email"],
        "max_tokens": 50,
    },
    "hid": {"keyboard": "/dev/null", "mouse": "/dev/null"},
    "logging": {"db_path": "", "stdout": False},
}


def test_engine_runs_multiple_activities_and_stops(tmp_path):
    db_path = str(tmp_path / "smoke.db")
    ctrl = EngineControl()
    ctrl.running.set()
    config_store = ConfigStore(SMOKE_CONFIG)
    status_store = StatusStore()
    activity_logger = ActivityLogger(db_path=db_path, stdout=False)

    engine_thread = threading.Thread(
        target=run_engine,
        kwargs=dict(
            control=ctrl,
            config_store=config_store,
            status_store=status_store,
            activity_logger=activity_logger,
            claude_client=None,
        ),
    )
    engine_thread.start()

    time.sleep(8)  # let a few short activities complete
    ctrl.stopped.set()
    engine_thread.join(timeout=5)

    assert not engine_thread.is_alive()

    snap = status_store.snapshot()
    assert snap is not None
    assert snap["activity"] in {"typing", "mouse", "idle", "dead_stop"}
    assert snap["persona"] == "focused_writer"
    assert "next_change_at" in snap

    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
    assert count >= 1


def test_engine_respects_pause_and_resume(tmp_path):
    db_path = str(tmp_path / "pause.db")
    ctrl = EngineControl()
    ctrl.running.set()
    config_store = ConfigStore(SMOKE_CONFIG)
    status_store = StatusStore()
    activity_logger = ActivityLogger(db_path=db_path, stdout=False)

    engine_thread = threading.Thread(
        target=run_engine,
        kwargs=dict(
            control=ctrl,
            config_store=config_store,
            status_store=status_store,
            activity_logger=activity_logger,
            claude_client=None,
        ),
    )
    engine_thread.start()
    time.sleep(1)

    ctrl.paused.set()
    time.sleep(0.5)
    snap_while_paused = status_store.snapshot()

    time.sleep(2)
    snap_still_paused = status_store.snapshot()

    assert snap_while_paused == snap_still_paused or snap_while_paused is None

    ctrl.paused.clear()
    time.sleep(3)
    ctrl.stopped.set()
    engine_thread.join(timeout=5)
    assert not engine_thread.is_alive()


def test_engine_handles_activity_exception_and_continues(tmp_path):
    """Engine should not die if an activity raises an exception."""
    from unittest.mock import patch
    db_path = str(tmp_path / "exc.db")
    ctrl = EngineControl()
    ctrl.running.set()
    config_store = ConfigStore(SMOKE_CONFIG)
    status_store = StatusStore()
    activity_logger = ActivityLogger(db_path=db_path, stdout=False)

    call_count = {"n": 0}
    original_select = ActivitySelector.select

    def flaky_select(self):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated selector crash")
        return original_select(self)

    engine_thread = threading.Thread(
        target=run_engine,
        kwargs=dict(
            control=ctrl,
            config_store=config_store,
            status_store=status_store,
            activity_logger=activity_logger,
            claude_client=None,
        ),
    )
    with patch.object(ActivitySelector, "select", flaky_select):
        engine_thread.start()
        time.sleep(6)
        ctrl.stopped.set()
        engine_thread.join(timeout=5)

    assert not engine_thread.is_alive()
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
    assert count >= 1
