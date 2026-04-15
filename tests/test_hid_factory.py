"""Tests for engine/hid/factory.py — HID backend routing by hid_mode."""

from unittest.mock import MagicMock, patch
import pytest

from engine.hid.factory import get_keyboard_writer, get_mouse_runner

USB_CONFIG = {
    "hid_mode": "usb",
    "hid": {"keyboard": "/dev/hidg0", "mouse": "/dev/hidg1"},
}

BT_CONFIG = {
    "hid_mode": "bluetooth",
    "hid": {"keyboard": "/dev/hidg0", "mouse": "/dev/hidg1"},
}

DEFAULT_CONFIG = {
    "hid": {"keyboard": "/dev/hidg0", "mouse": "/dev/hidg1"},
}


# ---------------------------------------------------------------------------
# get_keyboard_writer
# ---------------------------------------------------------------------------

def test_keyboard_writer_usb_returns_callable():
    fn = get_keyboard_writer(USB_CONFIG)
    assert callable(fn)


def test_keyboard_writer_default_is_usb():
    fn = get_keyboard_writer(DEFAULT_CONFIG)
    assert callable(fn)


def test_keyboard_writer_bluetooth_returns_callable():
    fn = get_keyboard_writer(BT_CONFIG)
    assert callable(fn)


def test_keyboard_writer_bluetooth_is_bt_module_function():
    fn = get_keyboard_writer(BT_CONFIG)
    from engine.hid import bluetooth_keyboard
    assert fn is bluetooth_keyboard.write_string


# ---------------------------------------------------------------------------
# get_mouse_runner
# ---------------------------------------------------------------------------

def test_mouse_runner_usb_returns_callable():
    fn = get_mouse_runner(USB_CONFIG)
    assert callable(fn)


def test_mouse_runner_bluetooth_returns_callable():
    fn = get_mouse_runner(BT_CONFIG)
    assert callable(fn)


def test_mouse_runner_bluetooth_is_bt_module():
    fn = get_mouse_runner(BT_CONFIG)
    from engine.hid import bluetooth_mouse
    assert fn is bluetooth_mouse.run_movement_session


def test_mouse_runner_usb_returns_callable():
    fn = get_mouse_runner(USB_CONFIG)
    assert callable(fn)
