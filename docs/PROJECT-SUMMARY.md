# Presence — Project Summary

## What It Is

A behavioral HID engine running on a Raspberry Pi Zero 2W that simulates realistic human computer activity (typing, mouse movement, idle pauses) via USB or Bluetooth. Plugged into a work computer, it keeps the machine awake and shows activity to employer monitoring tools.

**Core value:** Set it and forget it. The Pi handles everything — no interaction needed during normal operation.

---

## Hardware

| Component | Detail |
|-----------|--------|
| Device | Raspberry Pi Zero 2W |
| Chip | BCM2837B0, BT 4.1 |
| USB data port | Connects to work computer (HID output) |
| USB power port | Power only — no data |
| HID devices | `/dev/hidg0` (keyboard), `/dev/hidg1` (mouse) |

---

## Software Stack

| Layer | Technology |
|-------|------------|
| OS | Raspberry Pi OS Lite 64-bit (Trixie / Debian) |
| Engine | Python 3, stdlib + `anthropic` SDK |
| Web UI | Flask 3.x (Family Hub PWA) |
| Logging | SQLite |
| Config | JSON, live-reloaded (no restart needed) |
| HID | USB gadget via ConfigFS (`libcomposite`, `dwc2`) |
| Content | Claude API (falls back to 55-string bank if unavailable) |

---

## Architecture

```
Work Computer
    ↑ USB HID (keyboard + mouse)
Pi Zero 2W
    ├── engine/          Behavioral engine (scheduler, activities, HID)
    ├── pwa/             Family Hub Flask web app (port 5000)
    ├── portal/          WiFi setup captive portal (port 80, AP mode only)
    └── setup/           Install scripts, gadget config, AP mode config
```

---

## Key Files

| File | Purpose |
|------|---------|
| `config.json` | Runtime config — persona, dead zones, time profiles, HID mode |
| `run.py` | Engine entrypoint |
| `run_pwa.py` | Family Hub PWA entrypoint |
| `run_portal.py` | WiFi setup portal entrypoint |
| `setup/install.sh` | One-shot install script (run after git clone) |
| `setup/enable-gadget.sh` | Configures USB HID gadget via ConfigFS |
| `setup/firstboot.sh` | Boot-time WiFi check; starts AP mode if not connected |
| `presence.service` | systemd unit for engine |
| `presence-pwa.service` | systemd unit for PWA |
| `presence-gadget.service` | systemd unit for USB HID gadget setup |
| `presence-firstboot.service` | systemd unit for firstboot WiFi check |

---

## Personas

| Persona | WPM | Character |
|---------|-----|-----------|
| `focused_writer` | 70 | Long typing bursts, rare mouse |
| `distracted_multitasker` | 55 | Short bursts, frequent switching |
| `steady` | 35 | Slow, low variance |
| `power_user` | 90 | Fast, dense, high typo rate |
| `custom` | configurable | All params from `config.json` |

---

## Activity Types

| Type | Description |
|------|-------------|
| `typing` | Claude-generated content typed via HID with QWERTY typo injection |
| `mouse` | Bezier curve movement with easing and scroll events |
| `idle` | Micro-pause, no HID output |
| `dead_stop` | Complete silence (meeting blocks) |

---

## Configuration Reference

| Key | Description |
|-----|-------------|
| `persona` | Active persona name |
| `testing_mode` | `true` = flat peak weights at all hours (testing only) |
| `hid_mode` | `"usb"` or `"bluetooth"` |
| `dead_zones` | List of `{start, end, days}` meeting blocks |
| `time_profiles` | 24-element hourly weight arrays per activity type |
| `screen.width/height` | Must match work computer's display resolution |
| `claude.model` | Claude model for content generation |
| `command_server.port` | Engine HTTP control port (default 7777) |

---

## Deployment

**Pi location:** `192.168.4.146` (JoshuaTree WiFi)
**SSH:** `pi@192.168.4.146` / password: `kate`
**Repo:** `github.com/katebspurr-png/presence`
**Family Hub PWA:** `http://192.168.4.146:5000`

**Fresh install (after flashing SD card):**
```bash
ssh pi@<ip>
git clone https://github.com/katebspurr-png/presence.git
cd presence
bash setup/install.sh
sudo reboot
```

---

## Services

| Service | Purpose | Auto-start |
|---------|---------|------------|
| `presence-gadget` | USB HID gadget setup | Yes |
| `presence-firstboot` | WiFi check / AP mode | Yes |
| `presence` | Behavioral engine | Yes |
| `presence-pwa` | Family Hub web UI | Yes |

---

## Current Status (2026-04-14)

- [x] Behavioral engine — fully implemented, 135 tests
- [x] Family Hub PWA — fully implemented
- [x] USB HID gadget mode — working on Pi
- [x] Pi deployed and running
- [x] Claude API connected (typing with real content)
- [ ] WiFi captive portal — code written, not yet tested
- [ ] Bluetooth HID — planned, not yet implemented
- [ ] Screen resolution config in PWA — not yet implemented
- [ ] Customer packaging / documentation — not yet started

---

## Roadmap

### Next (immediate)
1. Test WiFi captive portal (delete saved WiFi, reboot, verify `Presence-Setup` hotspot)
2. Fix `testing_mode` sync between Pi and repo
3. Bake udev rule into `install.sh`

### Near term
4. Bluetooth HID — plan written at `docs/superpowers/plans/2026-04-14-bluetooth-hid.md`
5. Screen resolution config in PWA
6. README updates for end-to-end deployment

### Longer term
7. Customer packaging — clean install experience for non-technical users
8. Dual-mode HID (USB + BT simultaneously) — out of scope for now
