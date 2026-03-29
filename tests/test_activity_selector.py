from datetime import datetime, date, timedelta
from unittest.mock import patch

import pytest

from engine.activity_selector import ActivitySelector

BASE_CONFIG = {
    "persona": "focused_writer",
    "dead_zones": [
        {"start": "09:00", "end": "09:30", "days": ["mon", "tue", "wed", "thu", "fri"]},
    ],
    "time_profiles": {
        "typing":    [0.1] * 24,
        "mouse":     [0.1] * 24,
        "idle":      [0.1] * 24,
        "dead_stop": [0.1] * 24,
    },
    "personas": {
        "focused_writer": {
            "typing_mean_s": 60, "typing_stddev_s": 10,
            "mouse_lambda": 0.1, "idle_lambda": 0.2, "wpm": 70,
        },
        "custom": {
            "typing_mean_s": 60, "typing_stddev_s": 10,
            "mouse_lambda": 0.1, "idle_lambda": 0.2, "wpm": 60,
        },
    },
}

ACTIVITY_TYPES = {"typing", "mouse", "idle", "dead_stop"}


def test_select_returns_valid_activity_and_positive_duration():
    selector = ActivitySelector(BASE_CONFIG)
    activity_type, duration_s = selector.select()
    assert activity_type in ACTIVITY_TYPES
    assert duration_s >= 1.0


def test_select_returns_dead_stop_during_dead_zone():
    selector = ActivitySelector(BASE_CONFIG)
    # Monday at 09:15 is inside the dead zone
    monday_0915 = datetime(2026, 3, 30, 9, 15)  # a Monday
    with patch("engine.activity_selector.datetime") as mock_dt:
        mock_dt.now.return_value = monday_0915
        mock_dt.combine = datetime.combine
        mock_dt.strptime = datetime.strptime
        activity_type, duration_s = selector.select()
    assert activity_type == "dead_stop"
    assert duration_s >= 1.0


def test_select_outside_dead_zone_is_not_forced_dead_stop():
    selector = ActivitySelector(BASE_CONFIG)
    # Monday at 14:00 is outside the dead zone
    monday_1400 = datetime(2026, 3, 30, 14, 0)
    results = set()
    with patch("engine.activity_selector.datetime") as mock_dt:
        mock_dt.now.return_value = monday_1400
        mock_dt.combine = datetime.combine
        mock_dt.strptime = datetime.strptime
        for _ in range(50):
            activity_type, _ = selector.select()
            results.add(activity_type)
    # With uniform weights, all 4 types should appear eventually
    assert len(results) > 1


def test_select_dead_zone_duration_is_remaining_time_in_zone():
    selector = ActivitySelector(BASE_CONFIG)
    # 15 minutes into a 30-minute zone = ~15 minutes remaining
    monday_0915 = datetime(2026, 3, 30, 9, 15)
    with patch("engine.activity_selector.datetime") as mock_dt:
        mock_dt.now.return_value = monday_0915
        mock_dt.combine = datetime.combine
        mock_dt.strptime = datetime.strptime
        activity_type, duration_s = selector.select()
    assert activity_type == "dead_stop"
    assert 800 <= duration_s <= 950  # ~15 minutes = 900s, allow slop


def test_dead_zone_not_active_on_wrong_day():
    selector = ActivitySelector(BASE_CONFIG)
    # Saturday at 09:15 — dead zone only applies mon-fri
    saturday_0915 = datetime(2026, 4, 4, 9, 15)  # a Saturday
    results = set()
    with patch("engine.activity_selector.datetime") as mock_dt:
        mock_dt.now.return_value = saturday_0915
        mock_dt.combine = datetime.combine
        mock_dt.strptime = datetime.strptime
        for _ in range(50):
            activity_type, _ = selector.select()
            results.add(activity_type)
    assert len(results) > 1  # not forced to dead_stop


def test_time_until_dead_zone_s_returns_positive_int():
    selector = ActivitySelector(BASE_CONFIG)
    # Monday at 08:00 — dead zone starts at 09:00 = 3600s ahead
    monday_0800 = datetime(2026, 3, 30, 8, 0)
    with patch("engine.activity_selector.datetime") as mock_dt:
        mock_dt.now.return_value = monday_0800
        mock_dt.combine = datetime.combine
        mock_dt.strptime = datetime.strptime
        mock_dt.date = date
        result = selector.time_until_dead_zone_s()
    assert result is not None
    assert 3500 <= result <= 3700  # ~1 hour = 3600s


def test_time_until_dead_zone_s_returns_none_when_no_zones():
    config = dict(BASE_CONFIG)
    config["dead_zones"] = []
    selector = ActivitySelector(config)
    assert selector.time_until_dead_zone_s() is None


def test_update_config_changes_persona():
    selector = ActivitySelector(BASE_CONFIG)
    assert selector.current_persona_name == "focused_writer"
    new_config = dict(BASE_CONFIG)
    new_config["persona"] = "custom"
    selector.update_config(new_config)
    assert selector.current_persona_name == "custom"


def test_typing_duration_uses_persona_gaussian():
    selector = ActivitySelector(BASE_CONFIG)
    for _ in range(100):
        _, duration = selector._sample_duration("typing")
        assert 1.0 <= duration <= 3600.0


def test_mouse_duration_uses_exponential():
    selector = ActivitySelector(BASE_CONFIG)
    for _ in range(100):
        _, duration = selector._sample_duration("mouse")
        assert 1.0 <= duration <= 600.0


def test_time_until_dead_zone_scans_48h_ahead():
    selector = ActivitySelector(BASE_CONFIG)
    # Monday at 23:59 — dead zone (09:00 next day, i.e. Tuesday) is ~33h ahead
    # With range(2) this might miss it; with range(3) it should find it
    monday_2359 = datetime(2026, 3, 30, 23, 59)
    with patch("engine.activity_selector.datetime") as mock_dt:
        mock_dt.now.return_value = monday_2359
        mock_dt.combine = datetime.combine
        mock_dt.strptime = datetime.strptime
        result = selector.time_until_dead_zone_s()
    # Tuesday 09:00 is about 32460 seconds after Monday 23:59 (9h 1m)
    assert result is not None
    assert 32000 <= result <= 33000
