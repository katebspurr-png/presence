"""Tests for engine/hid/mouse.py — bezier math, report format, and session behavior."""

import math
from unittest.mock import patch

import pytest

from engine.hid.mouse import (
    _constrain_control_point,
    _cubic_bezier,
    _ease_in_out_sine,
    _scroll_burst,
    _to_signed_byte,
    run_movement_session,
)
from engine.status import EngineControl


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctrl(stopped=False, paused=False):
    c = EngineControl()
    if stopped:
        c.stopped.set()
    if paused:
        c.paused.set()
    return c


class _FileCapture:
    def __init__(self):
        self.reports = []

    def write(self, b):
        self.reports.append(bytes(b))

    def flush(self):
        pass

    def close(self):
        pass


# ---------------------------------------------------------------------------
# Easing
# ---------------------------------------------------------------------------

def test_ease_in_out_at_zero():
    assert _ease_in_out_sine(0.0) == pytest.approx(0.0)


def test_ease_in_out_at_one():
    assert _ease_in_out_sine(1.0) == pytest.approx(1.0)


def test_ease_in_out_at_half():
    assert _ease_in_out_sine(0.5) == pytest.approx(0.5)


def test_ease_in_out_symmetry():
    for t in [0.1, 0.2, 0.3, 0.4]:
        assert _ease_in_out_sine(t) == pytest.approx(1.0 - _ease_in_out_sine(1.0 - t))


# ---------------------------------------------------------------------------
# Cubic bezier
# ---------------------------------------------------------------------------

def test_cubic_bezier_at_zero_returns_start():
    p0, p1, p2, p3 = (0.0, 0.0), (10.0, 5.0), (20.0, 5.0), (30.0, 0.0)
    result = _cubic_bezier(p0, p1, p2, p3, 0.0)
    assert result == pytest.approx((0.0, 0.0))


def test_cubic_bezier_at_one_returns_end():
    p0, p1, p2, p3 = (0.0, 0.0), (10.0, 5.0), (20.0, 5.0), (30.0, 0.0)
    result = _cubic_bezier(p0, p1, p2, p3, 1.0)
    assert result == pytest.approx((30.0, 0.0))


# ---------------------------------------------------------------------------
# Bezier control point constraint
# ---------------------------------------------------------------------------

def test_constrain_control_point_clamps_perpendicular_offset():
    """A point 500px off the line should be clamped to 30% of line length."""
    start = (0.0, 0.0)
    end = (100.0, 0.0)
    raw_cp = (50.0, 500.0)  # far above horizontal line
    constrained = _constrain_control_point(start, end, raw_cp)

    # Perpendicular distance from the horizontal line = |y|
    perp_dist = abs(constrained[1])
    assert perp_dist <= 100.0 * 0.3 + 1e-9


def test_constrain_control_point_does_not_move_inbound_point():
    """A point already within 30% should not be moved."""
    start = (0.0, 0.0)
    end = (100.0, 0.0)
    cp = (50.0, 10.0)  # 10% perpendicular — within the 30% limit
    result = _constrain_control_point(start, end, cp)
    assert result == pytest.approx(cp)


def test_constrain_control_point_diagonal_line():
    """Constraint works correctly on non-axis-aligned lines."""
    start = (0.0, 0.0)
    end = (100.0, 100.0)
    dist = math.hypot(100.0, 100.0)
    max_perp = dist * 0.3

    raw_cp = (50.0 + 200.0, 50.0)  # way off perpendicular
    constrained = _constrain_control_point(start, end, raw_cp)

    # Recompute perpendicular distance
    dx, dy = 100.0, 100.0
    cx, cy = constrained
    t = (cx * dx + cy * dy) / (dist * dist)
    proj_x = t * dx
    proj_y = t * dy
    perp_dist = math.hypot(cx - proj_x, cy - proj_y)
    assert perp_dist <= max_perp + 1e-9


# ---------------------------------------------------------------------------
# Signed byte encoding
# ---------------------------------------------------------------------------

def test_to_signed_byte_positive_value():
    assert _to_signed_byte(10) == 10


def test_to_signed_byte_negative_one():
    assert _to_signed_byte(-1) == 255  # two's-complement 0xFF


def test_to_signed_byte_clamps_above_127():
    assert _to_signed_byte(200) == 127


def test_to_signed_byte_clamps_below_neg_127():
    # -200 clamped to -127, two's-complement = 0x81 = 129
    assert _to_signed_byte(-200) == 129


def test_to_signed_byte_zero():
    assert _to_signed_byte(0) == 0


# ---------------------------------------------------------------------------
# Session behavior
# ---------------------------------------------------------------------------

@patch("engine.hid.mouse.time.sleep")
def test_session_with_hid_path_none_does_not_crash(mock_sleep):
    ctrl = _ctrl(stopped=True)
    run_movement_session(1.0, 1920, 1080, ctrl, hid_path=None)


@patch("engine.hid.mouse.time.sleep")
def test_session_hid_oserror_does_not_crash(mock_sleep):
    ctrl = _ctrl(stopped=True)
    with patch("builtins.open", side_effect=OSError("no device")):
        run_movement_session(1.0, 1920, 1080, ctrl, hid_path="/dev/hidg1")


@patch("engine.hid.mouse.time.sleep")
def test_control_stop_exits_cleanly(mock_sleep):
    ctrl = EngineControl()
    call_count = [0]

    def side_effect(t):
        call_count[0] += 1
        if call_count[0] >= 5:
            ctrl.stopped.set()

    mock_sleep.side_effect = side_effect
    run_movement_session(9999.0, 1920, 1080, ctrl, hid_path=None)
    # Exits without hanging


# ---------------------------------------------------------------------------
# Report format
# ---------------------------------------------------------------------------

@patch("engine.hid.mouse.time.sleep")
def test_mouse_reports_are_4_bytes(mock_sleep):
    """Every HID report written must be exactly 4 bytes."""
    ctrl = EngineControl()
    cap = _FileCapture()
    # Stop after collecting a handful of reports
    write_count = [0]
    original_write = cap.write

    def counting_write(b):
        original_write(b)
        write_count[0] += 1
        if write_count[0] >= 20:
            ctrl.stopped.set()

    cap.write = counting_write

    with patch("builtins.open", return_value=cap):
        run_movement_session(9999.0, 100, 100, ctrl, hid_path="/dev/hidg1")

    for i, report in enumerate(cap.reports):
        assert len(report) == 4, f"Report {i} is {len(report)} bytes, expected 4"


@patch("engine.hid.mouse.time.sleep")
def test_mouse_button_byte_always_zero(mock_sleep):
    """Buttons byte (report[0]) must always be 0x00 — no click events."""
    ctrl = EngineControl()
    cap = _FileCapture()
    write_count = [0]
    original_write = cap.write

    def counting_write(b):
        original_write(b)
        write_count[0] += 1
        if write_count[0] >= 20:
            ctrl.stopped.set()

    cap.write = counting_write

    with patch("builtins.open", return_value=cap):
        run_movement_session(9999.0, 100, 100, ctrl, hid_path="/dev/hidg1")

    for report in cap.reports:
        assert report[0] == 0x00, f"Button byte should be 0x00, got 0x{report[0]:02X}"


@patch("engine.hid.mouse.time.sleep")
def test_mouse_deltas_clamped_to_signed_byte_range(mock_sleep):
    """dx and dy deltas must be representable as signed bytes [-127, 127]."""
    ctrl = EngineControl()
    cap = _FileCapture()
    write_count = [0]
    original_write = cap.write

    def counting_write(b):
        original_write(b)
        write_count[0] += 1
        if write_count[0] >= 50:
            ctrl.stopped.set()

    cap.write = counting_write

    with patch("builtins.open", return_value=cap):
        run_movement_session(9999.0, 1920, 1080, ctrl, hid_path="/dev/hidg1")

    for report in cap.reports:
        dx_byte = report[1]
        dy_byte = report[2]
        # Two's-complement decode
        dx = dx_byte if dx_byte < 128 else dx_byte - 256
        dy = dy_byte if dy_byte < 128 else dy_byte - 256
        assert -127 <= dx <= 127, f"dx={dx} out of signed byte range"
        assert -127 <= dy <= 127, f"dy={dy} out of signed byte range"


# ---------------------------------------------------------------------------
# Scroll bias
# ---------------------------------------------------------------------------

@patch("engine.hid.mouse.time.sleep")
def test_scroll_burst_bias_70_percent_down(mock_sleep):
    """Over many scroll events, ~70% should be scroll-down (negative wheel delta)."""
    cap = _FileCapture()
    ctrl = _ctrl()

    for _ in range(200):
        _scroll_burst(cap, ctrl)

    scroll_reports = [r for r in cap.reports if len(r) == 4 and r[3] != 0]
    assert len(scroll_reports) > 0, "Expected scroll reports"

    down_count = sum(
        1 for r in scroll_reports
        if (r[3] if r[3] < 128 else r[3] - 256) < 0  # two's-complement decode
    )
    down_pct = down_count / len(scroll_reports)
    assert 0.60 <= down_pct <= 0.80, (
        f"Expected ~70% scroll-down, got {down_pct:.1%} over {len(scroll_reports)} events"
    )
