# Bluetooth HID Plan

**Goal:** Add Bluetooth HID as an alternative to USB, letting the Pi pair wirelessly with the work computer. USB remains the default; `"hid_mode": "bluetooth"` in `config.json` switches to BT. Both modes use the same engine — only the HID backend changes.

**Hardware:** Pi Zero 2W BCM43438 (BT 4.1). No additional hardware needed.

**End-user flow:**
1. Pi boots, reads `hid_mode` from config
2. If `bluetooth`: starts BT HID backend, enters discoverable mode on first boot (no saved pairing)
3. User opens Family Hub PWA → taps "Pair Bluetooth"
4. User pairs from work computer BT settings
5. Pi saves pairing, reconnects automatically on every subsequent boot
6. Engine runs normally — typing and mouse output goes over BT instead of USB

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `setup/enable-bluetooth-hid.sh` | Configure bluetoothd as HID device, register SDP records |
| Create | `engine/hid/bluetooth_keyboard.py` | BT HID keyboard backend |
| Create | `engine/hid/bluetooth_mouse.py` | BT HID mouse backend |
| Create | `engine/hid/factory.py` | Returns USB or BT backend based on config `hid_mode` |
| Modify | `engine/hid/keyboard.py` | Extract interface/base class |
| Modify | `engine/hid/mouse.py` | Extract interface/base class |
| Modify | `engine/scheduler.py` | Use `hid/factory.py` to get HID backend |
| Modify | `config.json` | Add `"hid_mode": "usb"` (default) |
| Modify | `pwa/app.py` | Add `/api/bluetooth/pair` and `/api/bluetooth/status` endpoints |
| Modify | `pwa/templates/index.html` | Add pairing UI to PWA |
| Modify | `presence.service` | Add `bluetooth.target` dependency when hid_mode=bluetooth |
| Create | `tests/test_hid_factory.py` | Unit tests for HID backend selection |

---

## Phase 1: BT HID system configuration

### Task 1: Install and configure bluez

```bash
sudo apt install -y bluez bluez-tools python3-dbus
```

The key packages:
- `bluez` — Bluetooth stack (likely already installed)
- `bluez-tools` — `bt-agent`, `bt-adapter` CLI tools
- `python3-dbus` — needed to communicate with bluetoothd from Python

### Task 2: Create `setup/enable-bluetooth-hid.sh`

This script:
1. Enables the bluez HID plugin
2. Registers SDP records for keyboard + mouse
3. Sets the Pi's BT device name to `Presence`
4. Puts adapter into pairable mode

```bash
#!/bin/bash
# Configure bluetoothd to act as a Bluetooth HID device (keyboard + mouse)
set -e

# Ensure bluetoothd runs with HID plugin enabled
if ! grep -q "ExecStart.*--plugin=input" /lib/systemd/system/bluetooth.service; then
    sudo sed -i 's|ExecStart=/usr/libexec/bluetooth/bluetoothd|ExecStart=/usr/libexec/bluetooth/bluetoothd --plugin=input|' \
        /lib/systemd/system/bluetooth.service
    sudo systemctl daemon-reload
    sudo systemctl restart bluetooth
fi

# Set device name
sudo bluetoothctl system-alias "Presence"

# Enable adapter
sudo bluetoothctl power on
sudo bluetoothctl agent NoInputNoOutput
sudo bluetoothctl default-agent

echo "Bluetooth HID configured. Use bluetoothctl to pair."
```

### Task 3: Register HID SDP records

Bluez needs SDP (Service Discovery Protocol) records so the host computer recognizes the Pi as a keyboard+mouse. Create `/etc/bluetooth/hid_sdp.xml`:

```xml
<?xml version="1.0" encoding="UTF-8" ?>
<record>
  <attribute id="0x0001">
    <sequence>
      <uuid value="0x1124"/>
    </sequence>
  </attribute>
  <attribute id="0x0004">
    <sequence>
      <sequence>
        <uuid value="0x0100"/>
        <uint16 value="0x0011"/>
      </sequence>
      <sequence>
        <uuid value="0x0011"/>
      </sequence>
    </sequence>
  </attribute>
  <attribute id="0x0005">
    <sequence>
      <uuid value="0x1002"/>
    </sequence>
  </attribute>
  <attribute id="0x0006">
    <sequence>
      <uint16 value="0x656e"/>
      <uint16 value="0x006a"/>
      <uint16 value="0x0100"/>
    </sequence>
  </attribute>
  <attribute id="0x0009">
    <sequence>
      <sequence>
        <uuid value="0x1124"/>
        <uint16 value="0x0100"/>
      </sequence>
    </sequence>
  </attribute>
  <attribute id="0x000d">
    <sequence>
      <sequence>
        <sequence>
          <uuid value="0x0100"/>
          <uint16 value="0x0013"/>
        </sequence>
        <sequence>
          <uuid value="0x0011"/>
        </sequence>
      </sequence>
    </sequence>
  </attribute>
  <attribute id="0x0100">
    <text value="Presence HID"/>
  </attribute>
  <attribute id="0x0101">
    <text value="Infinite Saturdays"/>
  </attribute>
  <attribute id="0x0102">
    <text value="1.0"/>
  </attribute>
  <attribute id="0x0200">
    <uint16 value="0x0100"/>
  </attribute>
  <attribute id="0x0201">
    <uint8 value="0x22"/>
  </attribute>
  <!-- HID descriptor: keyboard + mouse combo -->
  <attribute id="0x0202">
    <sequence>
      <sequence>
        <uint8 value="0x22"/>
        <text encoding="hex" value="05010906a101850105079508750195017501810295017508810305ff0903a101851109300931093815817f750895038106c0c0050109020901a10185020901a10005091901290315002501950375018102950175058103050109300931150081269f7f750895038106c0c0"/>
      </sequence>
    </sequence>
  </attribute>
  <attribute id="0x0203">
    <uint8 value="0x40"/>
  </attribute>
  <attribute id="0x0204">
    <boolean value="false"/>
  </attribute>
  <attribute id="0x0205">
    <boolean value="false"/>
  </attribute>
  <attribute id="0x0206">
    <boolean value="false"/>
  </attribute>
  <attribute id="0x0207">
    <boolean value="false"/>
  </attribute>
  <attribute id="0x0208">
    <boolean value="false"/>
  </attribute>
  <attribute id="0x0209">
    <boolean value="false"/>
  </attribute>
  <attribute id="0x020a">
    <boolean value="true"/>
  </attribute>
  <attribute id="0x020b">
    <uint16 value="0x0100"/>
  </attribute>
  <attribute id="0x020c">
    <uint16 value="0x0c80"/>
  </attribute>
  <attribute id="0x020d">
    <boolean value="false"/>
  </attribute>
  <attribute id="0x020e">
    <boolean value="false"/>
  </attribute>
  <attribute id="0x020f">
    <uint16 value="0x0640"/>
  </attribute>
  <attribute id="0x0210">
    <uint16 value="0x0320"/>
  </attribute>
</record>
```

---

## Phase 2: Python BT HID backends

### Task 4: Create HID interface base classes

Refactor existing USB HID modules to share a common interface so the engine can swap backends.

- [ ] **Step 1: Create `engine/hid/base.py`**

```python
from abc import ABC, abstractmethod


class HIDKeyboard(ABC):
    @abstractmethod
    def type_string(self, text: str, wpm: int, typo_rate: float,
                    thinking_pause_p: float, thinking_pause_mean_s: float) -> None:
        ...

    @abstractmethod
    def close(self) -> None:
        ...


class HIDMouse(ABC):
    @abstractmethod
    def move(self, width: int, height: int) -> None:
        ...

    @abstractmethod
    def close(self) -> None:
        ...
```

- [ ] **Step 2: Update `engine/hid/keyboard.py` and `engine/hid/mouse.py`** to inherit from `HIDKeyboard` and `HIDMouse`

- [ ] **Step 3: Run tests to verify nothing broke**
  ```bash
  python3 -m pytest tests/test_hid_keyboard.py tests/test_hid_mouse.py -v
  ```

### Task 5: Create Bluetooth keyboard backend

- [ ] **Step 1: Write failing test in `tests/test_hid_bluetooth.py`**

```python
from unittest.mock import MagicMock, patch
from engine.hid.bluetooth_keyboard import BluetoothKeyboard

def test_bluetooth_keyboard_instantiates():
    with patch("engine.hid.bluetooth_keyboard.dbus"):
        kb = BluetoothKeyboard()
        assert kb is not None

def test_bluetooth_keyboard_closes_cleanly():
    with patch("engine.hid.bluetooth_keyboard.dbus"):
        kb = BluetoothKeyboard()
        kb.close()  # should not raise
```

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Create `engine/hid/bluetooth_keyboard.py`**

```python
import dbus
import time
from engine.hid.base import HIDKeyboard
from engine.hid import keyboard as _usb_kb  # reuse scan code tables


class BluetoothKeyboard(HIDKeyboard):
    """Sends keystrokes over Bluetooth HID using bluez D-Bus interface."""

    def __init__(self) -> None:
        self._bus = dbus.SystemBus()
        self._profile = self._get_hid_profile()

    def _get_hid_profile(self):
        manager = dbus.Interface(
            self._bus.get_object("org.bluez", "/org/bluez"),
            "org.bluez.ProfileManager1",
        )
        return manager

    def type_string(self, text: str, wpm: int, typo_rate: float,
                    thinking_pause_p: float, thinking_pause_mean_s: float) -> None:
        # Reuse the same character-by-character logic as USB keyboard
        # but send via BT HID socket instead of /dev/hidg0
        _usb_kb.type_string_via_socket(
            text, wpm, typo_rate, thinking_pause_p, thinking_pause_mean_s,
            send_fn=self._send_report
        )

    def _send_report(self, report: bytes) -> None:
        # Send HID report via bluez D-Bus
        # Report format matches the HID descriptor in hid_sdp.xml
        try:
            self._profile.SendData(dbus.Array(report, signature="y"))
        except dbus.DBusException:
            pass  # connection dropped, engine will retry next activity

    def close(self) -> None:
        pass
```

- [ ] **Step 4: Run test to verify it passes**

- [ ] **Step 5: Create `engine/hid/bluetooth_mouse.py`** (same pattern)

- [ ] **Step 6: Commit**

### Task 6: Create HID factory

- [ ] **Step 1: Write test**

```python
from engine.hid.factory import get_hid_backends

def test_factory_returns_usb_by_default():
    config = {"hid_mode": "usb", "hid": {"keyboard": "/dev/hidg0", "mouse": "/dev/hidg1"}}
    kb, mouse = get_hid_backends(config)
    from engine.hid.keyboard import USBKeyboard
    assert isinstance(kb, USBKeyboard)

def test_factory_returns_bluetooth():
    config = {"hid_mode": "bluetooth"}
    with patch("engine.hid.factory.BluetoothKeyboard") as mock_kb, \
         patch("engine.hid.factory.BluetoothMouse") as mock_mouse:
        kb, mouse = get_hid_backends(config)
        mock_kb.assert_called_once()
        mock_mouse.assert_called_once()
```

- [ ] **Step 2: Create `engine/hid/factory.py`**

```python
from engine.hid.base import HIDKeyboard, HIDMouse


def get_hid_backends(config: dict) -> tuple[HIDKeyboard, HIDMouse]:
    mode = config.get("hid_mode", "usb")
    if mode == "bluetooth":
        from engine.hid.bluetooth_keyboard import BluetoothKeyboard
        from engine.hid.bluetooth_mouse import BluetoothMouse
        return BluetoothKeyboard(), BluetoothMouse()
    else:
        from engine.hid.keyboard import USBKeyboard
        from engine.hid.mouse import USBMouse
        hid_cfg = config.get("hid", {})
        return (
            USBKeyboard(hid_cfg.get("keyboard", "/dev/hidg0")),
            USBMouse(hid_cfg.get("mouse", "/dev/hidg1")),
        )
```

- [ ] **Step 3: Run tests**

- [ ] **Step 4: Commit**

---

## Phase 3: PWA pairing UI

### Task 7: Add pairing endpoints to `pwa/app.py`

- [ ] **Step 1: Write failing tests**

```python
def test_bluetooth_status_endpoint(client):
    resp = client.get("/api/bluetooth/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "paired" in data
    assert "discoverable" in data

def test_bluetooth_pair_endpoint(client):
    resp = client.post("/api/bluetooth/pair")
    assert resp.status_code in (200, 503)  # 503 if BT not available
```

- [ ] **Step 2: Add routes to `pwa/app.py`**

```python
@app.route("/api/bluetooth/status", methods=["GET"])
def bluetooth_status():
    import subprocess
    result = subprocess.run(
        ["bluetoothctl", "show"],
        capture_output=True, text=True
    )
    paired = "Paired: yes" in result.stdout
    discoverable = "Discoverable: yes" in result.stdout
    return jsonify({"paired": paired, "discoverable": discoverable})

@app.route("/api/bluetooth/pair", methods=["POST"])
def bluetooth_pair():
    import subprocess
    subprocess.Popen(["sudo", "bluetoothctl", "discoverable", "on"])
    subprocess.Popen(["sudo", "bluetoothctl", "pairable", "on"])
    return jsonify({"status": "discoverable", "message": "Pair from your computer's Bluetooth settings. Device name: Presence"})
```

- [ ] **Step 3: Add pairing UI to `index.html`**

Add a BT section to the PWA (only shown when `hid_mode` is `bluetooth`):
- Status indicator: paired / unpaired
- "Start Pairing" button → calls `/api/bluetooth/pair` → shows instructions
- "Forget Device" button → unpairs

- [ ] **Step 4: Run tests and commit**

---

## Phase 4: Config and scheduler wiring

### Task 8: Add `hid_mode` to config and wire up factory

- [ ] **Step 1: Add to `config.json`**
```json
"hid_mode": "usb"
```

- [ ] **Step 2: Update `engine/scheduler.py`** to use `hid/factory.py` instead of importing USB backends directly

- [ ] **Step 3: Run full test suite**
```bash
python3 -m pytest tests/ -v
```

- [ ] **Step 4: Commit everything**
```bash
git add engine/hid/ pwa/app.py pwa/templates/index.html config.json
git add setup/enable-bluetooth-hid.sh etc/bluetooth/hid_sdp.xml
git commit -m "feat: Bluetooth HID backend with PWA pairing UI"
```

---

## Verification

1. `config.json` `hid_mode: usb` → engine uses `/dev/hidg0`, `/dev/hidg1` (existing behavior unchanged)
2. `config.json` `hid_mode: bluetooth` → engine uses BT HID backend
3. `/api/bluetooth/status` returns `{"paired": false, "discoverable": false}` initially
4. POST `/api/bluetooth/pair` → Pi becomes discoverable → work computer can pair
5. After pairing: engine sends typing/mouse activity over BT
6. After reboot: Pi reconnects to paired device automatically
7. All 135+ tests pass

---

## Notes

- **bluez version:** Trixie ships bluez 5.7x — the D-Bus API is stable at this version
- **Reconnection:** bluez handles automatic reconnection to paired devices; no extra code needed
- **Security:** BT HID uses "Just Works" pairing (no PIN) — acceptable for this use case since the Pi is physically controlled by the user
- **Dual mode:** USB and BT can theoretically run simultaneously, but that's out of scope — pick one per deployment
- **Testing BT without hardware:** Mock the `dbus` module in unit tests; integration test requires physical Pi + BT-capable computer
