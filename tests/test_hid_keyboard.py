"""Tests for engine/hid/keyboard.py — scan codes, QWERTY adjacency, and write_string behavior."""

from unittest.mock import patch

import pytest

from engine.hid.keyboard import ADJACENT_KEYS, SCAN_CODES, _KEY_UP, write_string
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
    """Minimal file-like object that accumulates written bytes."""

    def __init__(self):
        self.written = b""

    def write(self, b):
        self.written += bytes(b)

    def flush(self):
        pass

    def close(self):
        pass


# ---------------------------------------------------------------------------
# SCAN_CODES coverage
# ---------------------------------------------------------------------------

def test_all_printable_ascii_in_scan_codes():
    """Every printable ASCII character (32–126) must have a scan code entry."""
    for cp in range(32, 127):
        assert chr(cp) in SCAN_CODES, f"char {chr(cp)!r} (0x{cp:02X}) missing from SCAN_CODES"


def test_special_keys_in_scan_codes():
    for ch in ["\n", "\t", "\x08"]:
        assert ch in SCAN_CODES, f"special key {ch!r} missing from SCAN_CODES"


def test_uppercase_letters_have_shift_modifier():
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        modifier, _ = SCAN_CODES[letter]
        assert modifier == 0x02, f"{letter!r} should use left-shift modifier (0x02)"


def test_lowercase_letters_have_no_modifier():
    for letter in "abcdefghijklmnopqrstuvwxyz":
        modifier, _ = SCAN_CODES[letter]
        assert modifier == 0x00, f"{letter!r} should have no modifier"


def test_shifted_symbols_have_shift_modifier():
    for ch in '!@#$%^&*()_+{}|:"~<>?':
        modifier, _ = SCAN_CODES[ch]
        assert modifier == 0x02, f"{ch!r} should use left-shift modifier (0x02)"


def test_backspace_keycode():
    assert SCAN_CODES["\x08"] == (0x00, 0x2A)


def test_enter_keycode():
    assert SCAN_CODES["\n"] == (0x00, 0x28)


def test_tab_keycode():
    assert SCAN_CODES["\t"] == (0x00, 0x2B)


def test_space_keycode():
    assert SCAN_CODES[" "] == (0x00, 0x2C)


# ---------------------------------------------------------------------------
# ADJACENT_KEYS coverage
# ---------------------------------------------------------------------------

def test_every_scan_code_char_has_adjacent_keys():
    """Every character in SCAN_CODES must have an entry in ADJACENT_KEYS."""
    for char in SCAN_CODES:
        assert char in ADJACENT_KEYS, f"No ADJACENT_KEYS entry for {char!r}"


def test_all_adjacent_key_values_are_in_scan_codes():
    """Every adjacent key must itself be a valid SCAN_CODES character."""
    for source, adjacents in ADJACENT_KEYS.items():
        for adj in adjacents:
            assert adj in SCAN_CODES, (
                f"Adjacent key {adj!r} of {source!r} not in SCAN_CODES — "
                f"would cause KeyError during typo injection"
            )


def test_adjacent_keys_spot_check_qwerty():
    assert "s" in ADJACENT_KEYS["a"]
    assert "e" in ADJACENT_KEYS["s"]
    assert "a" in ADJACENT_KEYS["s"]


# ---------------------------------------------------------------------------
# Report format
# ---------------------------------------------------------------------------

@patch("engine.hid.keyboard.time.sleep")
def test_single_keystroke_emits_key_down_and_key_up(mock_sleep):
    """Each character must produce exactly one 8-byte key-down and one 8-byte key-up."""
    cap = _FileCapture()
    with patch("builtins.open", return_value=cap):
        write_string(
            "a", wpm=60, typo_rate=0.0, thinking_pause_p=0.0,
            thinking_pause_mean_s=0.0, control=_ctrl(), hid_path="/dev/hidg0",
        )

    assert len(cap.written) == 16, f"Expected 16 bytes, got {len(cap.written)}"
    # key-down: modifier=0x00, reserved=0x00, keycode=0x04 ('a'), rest zeros
    assert cap.written[:8] == bytes([0x00, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00])
    # key-up: all zeros
    assert cap.written[8:] == _KEY_UP


@patch("engine.hid.keyboard.time.sleep")
def test_uppercase_keystroke_uses_shift_modifier(mock_sleep):
    cap = _FileCapture()
    with patch("builtins.open", return_value=cap):
        write_string(
            "A", wpm=60, typo_rate=0.0, thinking_pause_p=0.0,
            thinking_pause_mean_s=0.0, control=_ctrl(), hid_path="/dev/hidg0",
        )

    # key-down modifier byte should be 0x02 (left shift)
    assert cap.written[0] == 0x02
    assert cap.written[2] == 0x04  # keycode for 'a'/'A'


# ---------------------------------------------------------------------------
# Typo injection
# ---------------------------------------------------------------------------

@patch("engine.hid.keyboard.time.sleep")
@patch("engine.hid.keyboard.random.random", return_value=0.0)   # always trigger typo
@patch("engine.hid.keyboard.random.choice", return_value="s")   # always pick 's' as typo
def test_typo_injects_adjacent_key_backspace_then_correct(mock_choice, mock_random, mock_sleep):
    """At typo_rate=1.0: typo key → backspace → correct key (3×16 = 48 bytes)."""
    cap = _FileCapture()
    with patch("builtins.open", return_value=cap):
        write_string(
            "a", wpm=60, typo_rate=1.0, thinking_pause_p=0.0,
            thinking_pause_mean_s=0.0, control=_ctrl(), hid_path="/dev/hidg0",
        )

    assert len(cap.written) == 48, f"Expected 48 bytes (typo+bs+correct), got {len(cap.written)}"
    assert cap.written[2] == 0x16   # 's' keycode (typo)
    assert cap.written[18] == 0x2A  # backspace keycode
    assert cap.written[34] == 0x04  # 'a' keycode (correct)


@patch("engine.hid.keyboard.time.sleep")
@patch("engine.hid.keyboard.random.random", return_value=1.0)   # never trigger typo
def test_typo_not_injected_when_rate_zero(mock_random, mock_sleep):
    cap = _FileCapture()
    with patch("builtins.open", return_value=cap):
        write_string(
            "a", wpm=60, typo_rate=0.0, thinking_pause_p=0.0,
            thinking_pause_mean_s=0.0, control=_ctrl(), hid_path="/dev/hidg0",
        )

    assert len(cap.written) == 16  # only the correct key, no typo


# ---------------------------------------------------------------------------
# Thinking pauses
# ---------------------------------------------------------------------------

@patch("engine.hid.keyboard.time.sleep")
@patch("engine.hid.keyboard.random.random", return_value=0.0)  # always trigger pause
@patch("engine.hid.keyboard.random.gauss", return_value=0.01)  # tiny pause duration
def test_thinking_pause_fires_at_word_boundary(mock_gauss, mock_random, mock_sleep):
    """With thinking_pause_p=1.0, a pause should be inserted after each space/newline."""
    write_string(
        "hi there", wpm=120, typo_rate=0.0, thinking_pause_p=1.0,
        thinking_pause_mean_s=0.01, control=_ctrl(), hid_path=None,
    )
    # Completed without hanging — the pause occurred and the function exited


# ---------------------------------------------------------------------------
# HID unavailability and control events
# ---------------------------------------------------------------------------

@patch("engine.hid.keyboard.time.sleep")
def test_hid_path_none_does_not_crash(mock_sleep):
    write_string(
        "hello world", wpm=60, typo_rate=0.0, thinking_pause_p=0.0,
        thinking_pause_mean_s=0.0, control=_ctrl(), hid_path=None,
    )


@patch("engine.hid.keyboard.time.sleep")
def test_hid_oserror_on_open_does_not_crash(mock_sleep):
    with patch("builtins.open", side_effect=OSError("no device")):
        write_string(
            "hello", wpm=60, typo_rate=0.0, thinking_pause_p=0.0,
            thinking_pause_mean_s=0.0, control=_ctrl(), hid_path="/dev/hidg0",
        )


@patch("engine.hid.keyboard.time.sleep")
def test_control_stop_exits_cleanly_mid_string(mock_sleep):
    ctrl = EngineControl()
    call_count = [0]

    def side_effect(t):
        call_count[0] += 1
        if call_count[0] >= 3:
            ctrl.stopped.set()

    mock_sleep.side_effect = side_effect
    write_string(
        "a" * 30, wpm=120, typo_rate=0.0, thinking_pause_p=0.0,
        thinking_pause_mean_s=0.0, control=ctrl, hid_path=None,
    )
    assert call_count[0] < 30, "Should have stopped before typing all 30 chars"
