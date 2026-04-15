"""HID backend factory.

Returns write callables for keyboard and mouse based on config["hid_mode"].

Callers receive simple functions with stable signatures — they don't need to
know whether output goes to a USB gadget file or a Bluetooth socket.

Keyboard callable signature:
    write_string(text, wpm, typo_rate, thinking_pause_p,
                 thinking_pause_mean_s, control) -> None

Mouse callable signature:
    run_movement_session(duration_s, screen_w, screen_h, control) -> None
"""


def get_keyboard_writer(config: dict):
    """Return the keyboard write callable for the configured HID mode."""
    mode = config.get("hid_mode", "usb")
    if mode == "bluetooth":
        from engine.hid.bluetooth_keyboard import write_string
        return write_string

    from engine.hid.keyboard import write_string as _usb_write
    path = config.get("hid", {}).get("keyboard", "/dev/hidg0")

    def _write(text, wpm, typo_rate, thinking_pause_p, thinking_pause_mean_s, control):
        _usb_write(text, wpm, typo_rate, thinking_pause_p, thinking_pause_mean_s,
                   control, hid_path=path)

    return _write


def get_mouse_runner(config: dict):
    """Return the mouse movement callable for the configured HID mode."""
    mode = config.get("hid_mode", "usb")
    if mode == "bluetooth":
        from engine.hid.bluetooth_mouse import run_movement_session
        return run_movement_session

    from engine.hid.mouse import run_movement_session as _usb_run
    path = config.get("hid", {}).get("mouse", "/dev/hidg1")

    def _run(duration_s, screen_w, screen_h, control):
        _usb_run(duration_s, screen_w, screen_h, control, hid_path=path)

    return _run
