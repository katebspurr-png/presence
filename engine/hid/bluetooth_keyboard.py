"""Bluetooth HID keyboard backend.

Sends keystrokes over Bluetooth HID using the bluez D-Bus interface.
The Pi must be configured as a BT HID device (see setup/enable-bluetooth-hid.sh)
and paired with the host computer before this module is used.

Drop-in replacement for the USB write_string function — same signature,
same behaviour from the caller's perspective.

TODO (requires Pi hardware):
  - Obtain the BT HID interrupt socket via bluez ProfileManager1 D-Bus API
  - Send 8-byte keyboard reports over the socket (same format as USB)
  - Handle reconnection when the host drops the BT connection
  - Test pairing flow end-to-end on Pi Zero 2W + macOS/Windows host
"""

import logging

from engine.hid.keyboard import SCAN_CODES, ADJACENT_KEYS, _write_key, _jittered_delay, _interruptible_pause

logger = logging.getLogger(__name__)


def _get_bt_socket():
    """Return an open BT HID interrupt socket, or None if unavailable.

    TODO: implement via bluez D-Bus ProfileManager1.
    Expected socket path: /var/run/bluetooth/hid-interrupt
    """
    # Placeholder — returns None so callers fall back to dry-run mode
    # until the BT socket implementation is complete.
    logger.warning("bluetooth_hid_not_implemented falling_back_to_dry_run=True")
    return None


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
    """Send one key-down + key-up report pair over the BT socket.

    No-op if bt_socket is None (dry run until BT is implemented).
    Report format is identical to USB: 8 bytes per event.
    """
    if bt_socket is None or char not in SCAN_CODES:
        return
    modifier, keycode = SCAN_CODES[char]
    key_down = bytes([modifier, 0x00, keycode, 0x00, 0x00, 0x00, 0x00, 0x00])
    key_up = bytes(8)
    try:
        bt_socket.send(key_down)
        bt_socket.send(key_up)
    except OSError as e:
        logger.warning(f"bt_key_send_error={e!r}")
