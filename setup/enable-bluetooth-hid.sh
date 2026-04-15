#!/usr/bin/env bash
# Configure the Pi Zero 2W as a Bluetooth HID keyboard+mouse peripheral.
#
# Run this script once (as root) after flashing the Pi.
# The presence engine will then use hid_mode=bluetooth in config.json.
#
# What this does:
#   1. Installs bluez if not present
#   2. Configures /etc/bluetooth/main.conf (device name, class, discoverable)
#   3. Disables the bluez input plugin (we're the peripheral, not the host)
#   4. Registers the combined HID SDP record via a Python D-Bus helper
#   5. Reloads bluetoothd
#   6. Makes the device discoverable and pairable so the host can pair
#
# After running this script, pair your work computer with "Presence" via
# Bluetooth settings.  Once paired, set hid_mode=bluetooth in config.json
# and restart the presence service.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Presence BT HID setup ==="

# 1. Install dependencies
echo "[1/5] Checking packages..."
apt-get install -y --no-install-recommends bluez python3-dbus python3-gi 2>/dev/null || true

# 2. Configure bluetoothd
echo "[2/5] Writing /etc/bluetooth/main.conf..."
cat > /etc/bluetooth/main.conf << 'EOF'
[General]
# Device name shown during pairing
Name = Presence

# Device class: 0x002540 = Major 0x05 (Peripheral) + Minor 0x10 (keyboard) + 0x20 (mouse)
# 0x0005 = Major class Peripheral, 0x40 = keyboard, 0x80 = mouse → 0xC0 minor
# Encoded: ((0x05 << 8) | (0xC0 << 2)) = 0x0025C0
# Use 0x002540 (keyboard only) if combo class causes issues on some hosts.
Class = 0x002540

# Always discoverable and pairable so the host can reconnect after a reboot
DiscoverableTimeout = 0
PairableTimeout = 0

[Policy]
AutoEnable = true
EOF

# 3. Disable the bluez input plugin (it manages HID hosts; we're a peripheral)
echo "[3/5] Disabling bluez input plugin..."
mkdir -p /etc/systemd/system/bluetooth.service.d
cat > /etc/systemd/system/bluetooth.service.d/presence-hid.conf << 'EOF'
[Service]
ExecStart=
ExecStart=/usr/lib/bluetooth/bluetoothd --noplugin=input
EOF

# 4. Register HID SDP record
# The SDP record advertises this device as an HID peripheral so the host
# knows which L2CAP PSMs to connect to (0x11 control, 0x13 interrupt).
# The HID descriptor bytes match bluetooth_connection.HID_DESCRIPTOR exactly.
echo "[4/5] Registering HID SDP record..."
python3 - << 'PYEOF'
import sys
import time

try:
    import dbus
    import dbus.mainloop.glib
    from gi.repository import GLib
except ImportError:
    print("WARNING: python3-dbus / python3-gi not available; SDP registration skipped.")
    print("         Install with: sudo apt-get install python3-dbus python3-gi")
    sys.exit(0)

# Combined keyboard+mouse HID descriptor (must match bluetooth_connection.HID_DESCRIPTOR)
HID_DESCRIPTOR = bytes([
    # Keyboard (Report ID 1)
    0x05,0x01,0x09,0x06,0xA1,0x01,0x85,0x01,
    0x05,0x07,0x19,0xE0,0x29,0xE7,0x15,0x00,
    0x25,0x01,0x75,0x01,0x95,0x08,0x81,0x02,
    0x95,0x01,0x75,0x08,0x81,0x01,0x95,0x06,
    0x75,0x08,0x15,0x00,0x25,0x65,0x05,0x07,
    0x19,0x00,0x29,0x65,0x81,0x00,0x05,0x08,
    0x19,0x01,0x29,0x05,0x95,0x05,0x75,0x01,
    0x91,0x02,0x95,0x01,0x75,0x03,0x91,0x01,
    0xC0,
    # Mouse (Report ID 2)
    0x05,0x01,0x09,0x02,0xA1,0x01,0x85,0x02,
    0x09,0x01,0xA1,0x00,0x05,0x09,0x19,0x01,
    0x29,0x03,0x15,0x00,0x25,0x01,0x95,0x03,
    0x75,0x01,0x81,0x02,0x95,0x01,0x75,0x05,
    0x81,0x01,0x05,0x01,0x09,0x30,0x09,0x31,
    0x09,0x38,0x15,0x80,0x25,0x7F,0x75,0x08,
    0x95,0x03,0x81,0x06,0xC0,0xC0,
])

desc_hex = HID_DESCRIPTOR.hex()

SDP_RECORD_XML = f"""<?xml version="1.0" encoding="UTF-8" ?>
<record>
  <attribute id="0x0001">
    <sequence><uuid value="0x1124"/></sequence>
  </attribute>
  <attribute id="0x0004">
    <sequence>
      <sequence>
        <uuid value="0x0100"/>
        <uint16 value="0x0011"/>
      </sequence>
      <sequence><uuid value="0x0011"/></sequence>
    </sequence>
  </attribute>
  <attribute id="0x0005">
    <sequence><uuid value="0x1002"/></sequence>
  </attribute>
  <attribute id="0x000d">
    <sequence>
      <sequence>
        <sequence>
          <uuid value="0x0100"/>
          <uint16 value="0x0013"/>
        </sequence>
        <sequence><uuid value="0x0011"/></sequence>
      </sequence>
    </sequence>
  </attribute>
  <attribute id="0x0100"><text value="Presence HID"/></attribute>
  <attribute id="0x0101"><text value="Presence Keyboard Mouse"/></attribute>
  <attribute id="0x0102"><text value="Presence"/></attribute>
  <attribute id="0x0201"><uint16 value="0x0111"/></attribute>
  <attribute id="0x0202"><uint8 value="0xC0"/></attribute>
  <attribute id="0x0203"><uint8 value="0x00"/></attribute>
  <attribute id="0x0204"><boolean value="false"/></attribute>
  <attribute id="0x0205"><boolean value="false"/></attribute>
  <attribute id="0x0206">
    <sequence>
      <sequence>
        <uint8 value="0x22"/>
        <text encoding="hex" value="{desc_hex}"/>
      </sequence>
    </sequence>
  </attribute>
  <attribute id="0x0207">
    <sequence>
      <sequence>
        <uint16 value="0x0409"/>
        <uint16 value="0x0100"/>
      </sequence>
    </sequence>
  </attribute>
  <attribute id="0x020b"><uint16 value="0x0100"/></attribute>
  <attribute id="0x020c"><uint16 value="0x0c80"/></attribute>
  <attribute id="0x020d"><boolean value="true"/></attribute>
  <attribute id="0x020e"><boolean value="false"/></attribute>
  <attribute id="0x020f"><uint16 value="0x0640"/></attribute>
  <attribute id="0x0210"><uint16 value="0x0320"/></attribute>
</record>"""

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
bus = dbus.SystemBus()

import dbus.service

class _HIDProfile(dbus.service.Object):
    """Minimal Profile1 implementation just to register the SDP record."""
    def __init__(self, bus, path):
        dbus.service.Object.__init__(self, bus, path)

    @dbus.service.method("org.bluez.Profile1", in_signature="oha{sv}", out_signature="")
    def NewConnection(self, path, fd, properties):
        pass

    @dbus.service.method("org.bluez.Profile1", in_signature="o", out_signature="")
    def RequestDisconnection(self, path):
        pass

    @dbus.service.method("org.bluez.Profile1", in_signature="", out_signature="")
    def Release(self):
        pass

PROFILE_PATH = "/presence/hid_sdp_reg"
HID_UUID = "00001124-0000-1000-8000-00805f9b34fb"

profile = _HIDProfile(bus, PROFILE_PATH)
manager = dbus.Interface(
    bus.get_object("org.bluez", "/org/bluez"),
    "org.bluez.ProfileManager1",
)

try:
    manager.RegisterProfile(PROFILE_PATH, HID_UUID, {
        "Role": dbus.String("server"),
        "RequireAuthentication": dbus.Boolean(False),
        "RequireAuthorization": dbus.Boolean(False),
        "ServiceRecord": dbus.String(SDP_RECORD_XML),
    })
    print("SDP record registered successfully.")
    # Keep the profile alive briefly so bluez can process it before we exit
    loop = GLib.MainLoop()
    GLib.timeout_add_seconds(3, loop.quit)
    loop.run()
    manager.UnregisterProfile(PROFILE_PATH)
except dbus.DBusException as e:
    print(f"WARNING: SDP registration failed: {e}")
    print("         The engine will still run but the host may not see the HID service.")
PYEOF

# 5. Reload and restart bluetooth
echo "[5/5] Restarting bluetoothd..."
systemctl daemon-reload
systemctl restart bluetooth
sleep 2

# Make discoverable and pairable
bluetoothctl << 'BTEOF'
power on
discoverable on
pairable on
BTEOF

echo ""
echo "=== BT HID setup complete ==="
echo ""
echo "Next steps:"
echo "  1. On your work computer, open Bluetooth settings"
echo "  2. Pair with 'Presence'"
echo "  3. On the Pi, run: bluetoothctl trust <MAC_ADDRESS>"
echo "  4. In config.json, set: \"hid_mode\": \"bluetooth\""
echo "  5. Restart the presence service: sudo systemctl restart presence"
echo ""
echo "To find the paired MAC after pairing:"
echo "  bluetoothctl devices"
