"""USB HID mouse report encoder for /dev/hidg1.

Generates human-like cursor movement using cubic bezier curves written as
4-byte HID mouse reports. Click bits are always zero — movement and scroll
wheel only.

Report format (4 bytes):
  [buttons, dx, dy, wheel]
  - buttons: always 0x00
  - dx, dy: signed relative displacement, two's-complement, clamped [-127, 127]
  - wheel:  signed scroll delta; negative = down, positive = up

Bezier control points are constrained so their perpendicular distance from the
start→end line is at most 30% of the segment length, keeping curves natural.
"""

import logging
import math
import random
import time

logger = logging.getLogger(__name__)

_REPORT_HZ = 60
_REPORT_INTERVAL_S = 1.0 / _REPORT_HZ


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def _ease_in_out_sine(t: float) -> float:
    """Sine ease-in-out: slow at both ends, fast in the middle. t ∈ [0, 1]."""
    return (1.0 - math.cos(math.pi * t)) / 2.0


def _cubic_bezier(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    """Evaluate cubic bezier curve at parameter t ∈ [0, 1]."""
    u = 1.0 - t
    x = u**3 * p0[0] + 3*u**2*t * p1[0] + 3*u*t**2 * p2[0] + t**3 * p3[0]
    y = u**3 * p0[1] + 3*u**2*t * p1[1] + 3*u*t**2 * p2[1] + t**3 * p3[1]
    return (x, y)


def _constrain_control_point(
    start: tuple[float, float],
    end: tuple[float, float],
    cp: tuple[float, float],
    max_ratio: float = 0.3,
) -> tuple[float, float]:
    """Clamp cp so its perpendicular distance from line start→end ≤ max_ratio * |start→end|."""
    ax, ay = start
    bx, by = end
    dx, dy = bx - ax, by - ay
    dist = math.hypot(dx, dy)
    if dist == 0.0:
        return start

    max_perp = dist * max_ratio

    # Project cp onto the line and measure perpendicular offset
    cx, cy = cp
    t = ((cx - ax) * dx + (cy - ay) * dy) / (dist * dist)
    proj_x = ax + t * dx
    proj_y = ay + t * dy

    perp_x = cx - proj_x
    perp_y = cy - proj_y
    perp_dist = math.hypot(perp_x, perp_y)

    if perp_dist > max_perp and perp_dist > 0.0:
        scale = max_perp / perp_dist
        return (proj_x + perp_x * scale, proj_y + perp_y * scale)
    return cp


def _make_control_points(
    start: tuple[float, float],
    end: tuple[float, float],
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Generate two random bezier control points constrained to ≤30% perpendicular offset."""
    ax, ay = start
    bx, by = end
    dist = math.hypot(bx - ax, by - ay)
    max_offset = dist * 0.3

    # Perpendicular unit vector (rotate direction 90°)
    if dist > 0.0:
        perp_x = -(by - ay) / dist
        perp_y = (bx - ax) / dist
    else:
        perp_x, perp_y = 1.0, 0.0

    # Place control points along the path at t≈0.3 and t≈0.7 with bounded lateral offset
    t1 = random.uniform(0.2, 0.45)
    t2 = random.uniform(0.55, 0.8)
    off1 = random.uniform(-max_offset, max_offset)
    off2 = random.uniform(-max_offset, max_offset)

    cp1_raw = (ax + t1 * (bx - ax) + off1 * perp_x, ay + t1 * (by - ay) + off1 * perp_y)
    cp2_raw = (ax + t2 * (bx - ax) + off2 * perp_x, ay + t2 * (by - ay) + off2 * perp_y)

    return (
        _constrain_control_point(start, end, cp1_raw),
        _constrain_control_point(start, end, cp2_raw),
    )


def _to_signed_byte(v: int) -> int:
    """Convert integer to unsigned byte value for two's-complement signed HID delta."""
    return max(-127, min(127, v)) & 0xFF


# ---------------------------------------------------------------------------
# Internal I/O helpers
# ---------------------------------------------------------------------------

def _write_report(hid_file, dx: int, dy: int, wheel: int) -> bool:
    """Write one 4-byte mouse report. Returns False and logs on OSError."""
    try:
        hid_file.write(bytes([
            0x00,
            _to_signed_byte(dx),
            _to_signed_byte(dy),
            _to_signed_byte(wheel),
        ]))
        hid_file.flush()
        return True
    except OSError as e:
        logger.warning(f"hid_mouse_write_error={e!r}")
        return False


def _micro_pause(duration_s: float, control) -> None:
    """Short pause with 50ms control-check granularity."""
    end = time.monotonic() + duration_s
    while time.monotonic() < end:
        if control.stopped.is_set() or control.paused.is_set():
            break
        time.sleep(min(0.05, end - time.monotonic()))


def _scroll_burst(hid_file, control) -> None:
    """Emit 3–8 scroll wheel reports. 70% scroll down, 30% scroll up."""
    for _ in range(random.randint(3, 8)):
        if control.stopped.is_set() or control.paused.is_set():
            return
        direction = -1 if random.random() < 0.70 else 1
        wheel = direction * random.randint(1, 2)
        if hid_file is not None:
            _write_report(hid_file, 0, 0, wheel)
        time.sleep(0.05)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_movement_session(
    duration_s: float,
    screen_w: int,
    screen_h: int,
    control,
    hid_path: str | None = None,
) -> None:
    """Run a mouse movement session for approximately duration_s seconds.

    Moves the virtual cursor along cubic bezier curves between random positions
    within the screen bounds. Interleaves micro-pauses (~20% probability after
    each move) and scroll bursts (~15% probability after each move).

    Args:
        duration_s: How long to run the session.
        screen_w: Screen width in pixels — constrains target x coordinates.
        screen_h: Screen height in pixels — constrains target y coordinates.
        control: EngineControl instance — checked between every report write.
            Exits cleanly on stop or pause without raising.
        hid_path: Path to the HID mouse gadget device (e.g. /dev/hidg1), or
            None for a dry run. OSError on open is logged and silently skipped.
    """
    hid_file = None
    if hid_path is not None:
        try:
            hid_file = open(hid_path, "wb")
        except OSError as e:
            logger.warning(f"hid_mouse_unavailable path={hid_path} error={e!r}")

    try:
        end_time = time.monotonic() + duration_s
        cx, cy = float(screen_w) / 2.0, float(screen_h) / 2.0

        while time.monotonic() < end_time:
            if control.stopped.is_set() or control.paused.is_set():
                break

            tx = random.uniform(0.0, float(screen_w))
            ty = random.uniform(0.0, float(screen_h))
            cp1, cp2 = _make_control_points((cx, cy), (tx, ty))

            dist = math.hypot(tx - cx, ty - cy)
            n_steps = max(10, int(dist / 4.0))

            prev_x, prev_y = cx, cy

            for i in range(1, n_steps + 1):
                if control.stopped.is_set() or control.paused.is_set():
                    return
                if time.monotonic() >= end_time:
                    break

                t_eased = _ease_in_out_sine(i / n_steps)
                px, py = _cubic_bezier((cx, cy), cp1, cp2, (tx, ty), t_eased)

                dx = int(round(px - prev_x))
                dy = int(round(py - prev_y))
                prev_x, prev_y = px, py

                if hid_file is not None:
                    if not _write_report(hid_file, dx, dy, 0):
                        hid_file = None  # stop writing after failure

                time.sleep(_REPORT_INTERVAL_S)

            cx, cy = tx, ty

            if random.random() < 0.20:
                _micro_pause(random.uniform(0.2, 1.5), control)
                if control.stopped.is_set() or control.paused.is_set():
                    break

            if random.random() < 0.15:
                _scroll_burst(hid_file, control)
                if control.stopped.is_set() or control.paused.is_set():
                    break

    finally:
        if hid_file is not None:
            hid_file.close()
