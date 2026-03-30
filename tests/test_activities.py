import time
from engine.activities.base import ActivityResult, interruptible_sleep
from engine.activities.dead_stop import DeadStopActivity
from engine.activities.idle import IdleActivity
from engine.activities.mouse import MouseActivity
from engine.status import EngineControl


def test_activity_result_defaults():
    result = ActivityResult(activity="idle", duration_s=5.0)
    assert result.metadata == {}


def test_interruptible_sleep_completes_full_duration():
    ctrl = EngineControl()
    start = time.monotonic()
    interruptible_sleep(2.0, ctrl)
    elapsed = time.monotonic() - start
    assert elapsed >= 1.9  # allow small timing slop


def test_interruptible_sleep_breaks_on_stop():
    ctrl = EngineControl()
    ctrl.stopped.set()
    start = time.monotonic()
    interruptible_sleep(60.0, ctrl)
    elapsed = time.monotonic() - start
    assert elapsed < 2.0  # should exit almost immediately


def test_interruptible_sleep_breaks_on_pause():
    ctrl = EngineControl()
    ctrl.paused.set()
    start = time.monotonic()
    interruptible_sleep(60.0, ctrl)
    elapsed = time.monotonic() - start
    assert elapsed < 2.0


def test_idle_activity_returns_correct_result():
    ctrl = EngineControl()
    ctrl.stopped.set()  # exit immediately
    activity = IdleActivity()
    result = activity.run(duration_s=60.0, control=ctrl)
    assert result.activity == "idle"
    assert result.duration_s == 60.0


def test_dead_stop_activity_returns_correct_result():
    ctrl = EngineControl()
    ctrl.stopped.set()
    activity = DeadStopActivity()
    result = activity.run(duration_s=30.0, control=ctrl)
    assert result.activity == "dead_stop"
    assert result.duration_s == 30.0


def test_interruptible_sleep_does_not_overshoot_short_duration():
    ctrl = EngineControl()
    start = time.monotonic()
    interruptible_sleep(0.1, ctrl)
    elapsed = time.monotonic() - start
    assert elapsed < 0.5  # should complete in well under 1s


def test_mouse_activity_returns_correct_result():
    ctrl = EngineControl()
    ctrl.stopped.set()
    activity = MouseActivity(config={}, hid_path="/dev/null")
    result = activity.run(duration_s=10.0, control=ctrl)
    assert result.activity == "mouse"
    assert result.duration_s == 10.0


def test_mouse_activity_handles_missing_hid_device():
    ctrl = EngineControl()
    ctrl.stopped.set()
    activity = MouseActivity(config={}, hid_path="/dev/nonexistent_hidg1")
    result = activity.run(duration_s=5.0, control=ctrl)
    assert result.activity == "mouse"
