"""Bluetooth HID connection manager.

Listens on L2CAP PSMs 0x11 (control) and 0x13 (interrupt) for an incoming
HIDP connection from a paired host. Exposes the interrupt socket for sending
HID input reports.

The Pi must be configured as a BT HID peripheral before this module is useful
(see setup/enable-bluetooth-hid.sh).  call start() once at engine startup;
after that, get_interrupt_socket() returns the active socket or None.

Combined HID descriptor (Report ID 1 = keyboard, Report ID 2 = mouse) is
embedded here for reference — it must match the SDP record registered by
enable-bluetooth-hid.sh.

HIDP report format on the interrupt channel (PSM 0x13):
  byte 0 : 0xA1  (HIDP DATA | INPUT)
  byte 1 : report ID  (0x01 keyboard, 0x02 mouse)
  bytes 2+: report payload

Keyboard report payload (8 bytes):
  [modifier, reserved, keycode, 0, 0, 0, 0, 0]

Mouse report payload (4 bytes):
  [buttons, dx_signed, dy_signed, wheel_signed]
"""

import logging
import socket
import threading
import time

logger = logging.getLogger(__name__)

_BT_CONTROL_PSM  = 0x11
_BT_INTERRUPT_PSM = 0x13

# -----------------------------------------------------------------------
# Combined keyboard+mouse HID report descriptor (Report ID 1 + 2).
# Kept here for documentation purposes; actual SDP registration is done
# by setup/enable-bluetooth-hid.sh which embeds the same bytes.
# -----------------------------------------------------------------------
HID_DESCRIPTOR = bytes([
    # --- Keyboard (Report ID 1) ---
    0x05, 0x01,        # Usage Page (Generic Desktop)
    0x09, 0x06,        # Usage (Keyboard)
    0xA1, 0x01,        # Collection (Application)
    0x85, 0x01,        #   Report ID (1)
    0x05, 0x07,        #   Usage Page (Keyboard/Keypad)
    0x19, 0xE0,        #   Usage Min (Left Control)
    0x29, 0xE7,        #   Usage Max (Right GUI)
    0x15, 0x00,        #   Logical Min (0)
    0x25, 0x01,        #   Logical Max (1)
    0x75, 0x01,        #   Report Size (1 bit)
    0x95, 0x08,        #   Report Count (8)
    0x81, 0x02,        #   Input (Data, Var, Abs)  — modifier byte
    0x95, 0x01,        #   Report Count (1)
    0x75, 0x08,        #   Report Size (8 bits)
    0x81, 0x01,        #   Input (Const)            — reserved byte
    0x95, 0x06,        #   Report Count (6)
    0x75, 0x08,        #   Report Size (8 bits)
    0x15, 0x00,        #   Logical Min (0)
    0x25, 0x65,        #   Logical Max (101)
    0x05, 0x07,        #   Usage Page (Keyboard/Keypad)
    0x19, 0x00,        #   Usage Min (0)
    0x29, 0x65,        #   Usage Max (101)
    0x81, 0x00,        #   Input (Data, Array)      — 6 key slots
    0x05, 0x08,        #   Usage Page (LEDs)
    0x19, 0x01,        #   Usage Min (Num Lock)
    0x29, 0x05,        #   Usage Max (Kana)
    0x95, 0x05,        #   Report Count (5)
    0x75, 0x01,        #   Report Size (1 bit)
    0x91, 0x02,        #   Output (Data, Var, Abs)  — 5 LED bits
    0x95, 0x01,        #   Report Count (1)
    0x75, 0x03,        #   Report Size (3 bits)
    0x91, 0x01,        #   Output (Const)            — LED padding
    0xC0,              # End Collection
    # --- Mouse (Report ID 2) ---
    0x05, 0x01,        # Usage Page (Generic Desktop)
    0x09, 0x02,        # Usage (Mouse)
    0xA1, 0x01,        # Collection (Application)
    0x85, 0x02,        #   Report ID (2)
    0x09, 0x01,        #   Usage (Pointer)
    0xA1, 0x00,        #   Collection (Physical)
    0x05, 0x09,        #     Usage Page (Buttons)
    0x19, 0x01,        #     Usage Min (Button 1)
    0x29, 0x03,        #     Usage Max (Button 3)
    0x15, 0x00,        #     Logical Min (0)
    0x25, 0x01,        #     Logical Max (1)
    0x95, 0x03,        #     Report Count (3)
    0x75, 0x01,        #     Report Size (1 bit)
    0x81, 0x02,        #     Input (Data, Var, Abs)  — 3 buttons
    0x95, 0x01,        #     Report Count (1)
    0x75, 0x05,        #     Report Size (5 bits)
    0x81, 0x01,        #     Input (Const)            — button padding
    0x05, 0x01,        #     Usage Page (Generic Desktop)
    0x09, 0x30,        #     Usage (X)
    0x09, 0x31,        #     Usage (Y)
    0x09, 0x38,        #     Usage (Wheel)
    0x15, 0x80,        #     Logical Min (-128)
    0x25, 0x7F,        #     Logical Max (127)
    0x75, 0x08,        #     Report Size (8 bits)
    0x95, 0x03,        #     Report Count (3)
    0x81, 0x06,        #     Input (Data, Var, Rel)  — X, Y, Wheel
    0xC0,              #   End Collection (Physical)
    0xC0,              # End Collection (Application)
])

# -----------------------------------------------------------------------
# Module-level connection state
# -----------------------------------------------------------------------
_interrupt_socket: "socket.socket | None" = None
_socket_lock = threading.Lock()
_started = False
_start_lock = threading.Lock()


def get_interrupt_socket() -> "socket.socket | None":
    """Return the active BT HID interrupt socket, or None if not connected."""
    with _socket_lock:
        return _interrupt_socket


def _set_socket(sock: "socket.socket | None") -> None:
    global _interrupt_socket
    with _socket_lock:
        _interrupt_socket = sock


def start() -> None:
    """Start the BT HID listener thread (idempotent, safe to call multiple times)."""
    global _started
    with _start_lock:
        if _started:
            return
        _started = True
    t = threading.Thread(target=_connection_loop, daemon=True, name="bt-hid-listener")
    t.start()
    logger.info("bt_hid_listener_started")


def _connection_loop() -> None:
    """Background thread: continuously accept L2CAP connections from a paired host."""
    while True:
        try:
            _accept_once()
        except OSError as e:
            logger.warning(f"bt_accept_error={e!r}")
        except Exception as e:
            logger.error(f"bt_connection_loop_error={e!r}", exc_info=True)
        finally:
            _set_socket(None)
        time.sleep(5.0)


def _make_l2cap_server(psm: int) -> "socket.socket":
    s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("", psm))
    s.listen(1)
    return s


def _accept_once() -> None:
    """Open L2CAP servers on PSM 0x11 and 0x13, accept one connection pair, hold until disconnect."""
    ctrl_server = _make_l2cap_server(_BT_CONTROL_PSM)
    intr_server = _make_l2cap_server(_BT_INTERRUPT_PSM)
    logger.info("bt_hid_listening psm_ctrl=0x11 psm_intr=0x13")

    try:
        ctrl_conn, ctrl_addr = ctrl_server.accept()
        logger.info(f"bt_hid_ctrl_connected addr={ctrl_addr}")
        intr_conn, intr_addr = intr_server.accept()
        logger.info(f"bt_hid_intr_connected addr={intr_addr}")
    finally:
        ctrl_server.close()
        intr_server.close()

    _set_socket(intr_conn)
    logger.info("bt_hid_ready")

    # Keep control connection alive; drain any incoming data (LED state reports etc.)
    try:
        while True:
            try:
                data = ctrl_conn.recv(64)
                if not data:
                    break  # host closed control channel
            except BlockingIOError:
                time.sleep(0.05)
            except OSError:
                break
    finally:
        try:
            ctrl_conn.close()
        except OSError:
            pass
        try:
            intr_conn.close()
        except OSError:
            pass
        logger.info("bt_hid_disconnected")
