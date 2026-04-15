"""Bluetooth HID mouse backend.

Sends mouse movement reports over the L2CAP interrupt channel (PSM 0x13).
The Pi must be configured as a BT HID peripheral (setup/enable-bluetooth-hid.sh)
and paired with the host before this module is used.

Drop-in replacement for the USB run_movement_session function — same signature,
same behaviour from the caller's perspective.

HIDP report format used here (interrupt channel, PSM 0x13):
  [0xA1, 0x02, buttons, dx_signed, dy_signed, wheel_signed]
   ^     ^     ^0x00   (no buttons pressed for movement)
   |     Report ID (mouse = 2)
   HIDP DATA | INPUT header
"""

import logging
import random
import time

from engine.hid.mouse import (
    _ease_in_out_sine,
    _cubic_bezier,
    _make_control_points,
    _to_signed_byte,
    _micro_pause,
    _scroll_burst,
)

logger = logging.getLogger(__name__)

_REPORT_HZ = 60
_REPORT_INTERVAL_S = 1.0 / _REPORT_HZ

# HIDP transaction header for INPUT reports sent by the device.
_HIDP_DATA_INPUT: int = 0xA1
_REPORT_ID_MOUSE: int = 0x02


def _get_bt_socket():
    """Return the active BT HID interrupt socket, or None if not connected."""
    from engine.hid import bluetooth_connection
    bluetooth_connection.start()
    return bluetooth_connection.get_interrupt_socket()


def run_movement_session(
    duration_s: float,
    screen_w: int,
    screen_h: int,
    control,
) -> None:
    """Run a mouse movement session over Bluetooth HID.

    Same behaviour as engine.hid.mouse.run_movement_session but outputs over BT
    instead of writing to /dev/hidg1.

    If the BT socket is unavailable, timing runs normally but no reports are
    sent — identical to USB dry-run mode.
    """
    import math

    bt_socket = _get_bt_socket()

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

            _send_report(bt_socket, dx, dy, 0)
            time.sleep(_REPORT_INTERVAL_S)

        cx, cy = tx, ty

        if random.random() < 0.20:
            _micro_pause(random.uniform(0.2, 1.5), control)
            if control.stopped.is_set() or control.paused.is_set():
                break

        if random.random() < 0.15:
            _send_scroll_burst(bt_socket, control)
            if control.stopped.is_set() or control.paused.is_set():
                break


def _send_report(bt_socket, dx: int, dy: int, wheel: int) -> None:
    """Send one HIDP mouse report over the interrupt socket. No-op if socket is None.

    HIDP mouse report (6 bytes):
      [0xA1, 0x02, buttons, dx_signed, dy_signed, wheel_signed]
    """
    if bt_socket is None:
        return
    report = bytes([
        _HIDP_DATA_INPUT, _REPORT_ID_MOUSE,
        0x00,  # buttons (none pressed for movement)
        _to_signed_byte(dx),
        _to_signed_byte(dy),
        _to_signed_byte(wheel),
    ])
    try:
        bt_socket.send(report)
    except OSError as e:
        logger.warning(f"bt_mouse_send_error={e!r}")


def _send_scroll_burst(bt_socket, control) -> None:
    """Emit 3–8 scroll wheel reports over BT."""
    for _ in range(random.randint(3, 8)):
        if control.stopped.is_set() or control.paused.is_set():
            return
        direction = -1 if random.random() < 0.70 else 1
        wheel = direction * random.randint(1, 2)
        _send_report(bt_socket, 0, 0, wheel)
        time.sleep(0.05)
