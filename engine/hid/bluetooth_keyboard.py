"""Bluetooth HID keyboard backend.

Sends keystrokes over Bluetooth HID via the L2CAP interrupt channel (PSM 0x13).
The Pi must be configured as a BT HID peripheral (setup/enable-bluetooth-hid.sh)
and paired with the host before this module is used.

Drop-in replacement for the USB write_string function — same signature,
same behaviour from the caller's perspective.

HIDP report format used here (interrupt channel, PSM 0x13):
  [0xA1, 0x01, modifier, 0x00, keycode, 0x00, 0x00, 0x00, 0x00, 0x00]
   ^     ^     ^modifier ^rsv  ^key1    ^key2–key6 (zeroed)
   |     Report ID (keyboard = 1)
   HIDP DATA | INPUT header
"""

import logging

from engine.hid.keyboard import SCAN_CODES, ADJACENT_KEYS, _jittered_delay, _interruptible_pause

logger = logging.getLogger(__name__)

# HIDP transaction header for INPUT reports sent by the device.
_HIDP_DATA_INPUT: int = 0xA1
_REPORT_ID_KEYBOARD: int = 0x01

# Key-up: all-zero payload with HIDP header and report ID.
_KEY_UP_REPORT = bytes([_HIDP_DATA_INPUT, _REPORT_ID_KEYBOARD, 0, 0, 0, 0, 0, 0, 0, 0])


def _get_bt_socket():
    """Return the active BT HID interrupt socket, or None if not connected."""
    from engine.hid import bluetooth_connection
    bluetooth_connection.start()
    return bluetooth_connection.get_interrupt_socket()


def write_string(
    text: str,
    wpm: int,
    typo_rate: float,
    thinking_pause_p: float,
    thinking_pause_mean_s: float,
    control,
) -> None:
    """Type text over Bluetooth HID.

    Same behaviour as engine.hid.keyboard.write_string but outputs over BT
    instead of writing to /dev/hidg0.

    If the BT socket is unavailable (not yet implemented or connection dropped),
    timing runs normally but no keystrokes are sent — identical to the USB
    dry-run mode (hid_path=None).
    """
    import random
    import time

    bt_socket = _get_bt_socket()

    base_delay_s = 60.0 / (max(1, wpm) * 5)

    for char in text:
        if control.stopped.is_set() or control.paused.is_set():
            break

        if char not in SCAN_CODES:
            continue

        if typo_rate > 0 and random.random() < typo_rate:
            candidates = [c for c in ADJACENT_KEYS.get(char, []) if c in SCAN_CODES]
            if candidates:
                _send_key(bt_socket, random.choice(candidates))
                time.sleep(_jittered_delay(base_delay_s))
                _send_key(bt_socket, "\x08")
                time.sleep(_jittered_delay(base_delay_s))

        _send_key(bt_socket, char)

        if char in (" ", "\n") and thinking_pause_p > 0 and random.random() < thinking_pause_p:
            pause_s = max(0.3, random.gauss(thinking_pause_mean_s, thinking_pause_mean_s * 0.3))
            _interruptible_pause(pause_s, control)
        else:
            time.sleep(_jittered_delay(base_delay_s))


def _send_key(bt_socket, char: str) -> None:
    """Send one key-down + key-up HIDP report pair over the interrupt socket.

    No-op if bt_socket is None (dry-run mode when BT is not connected).

    HIDP keyboard report (10 bytes):
      [0xA1, 0x01, modifier, 0x00, keycode, 0x00, 0x00, 0x00, 0x00, 0x00]
    """
    if bt_socket is None or char not in SCAN_CODES:
        return
    modifier, keycode = SCAN_CODES[char]
    key_down = bytes([_HIDP_DATA_INPUT, _REPORT_ID_KEYBOARD,
                      modifier, 0x00, keycode, 0x00, 0x00, 0x00, 0x00, 0x00])
    try:
        bt_socket.send(key_down)
        bt_socket.send(_KEY_UP_REPORT)
    except OSError as e:
        logger.warning(f"bt_key_send_error={e!r}")
