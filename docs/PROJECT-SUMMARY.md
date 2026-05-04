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
| `setup/enable-bluetooth-hid.sh` | Configures Pi as BT HID peripheral |
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
| `override.active` | `true` = bypass time-of-day weights and dead zones |
| `override.expires_at` | ISO timestamp when override auto-disables (null = indefinite) |
| `forced_activity` | Lock engine to one activity type: `typing`, `mouse`, `idle` |
| `dead_zones` | List of `{start, end, days}` meeting blocks |
| `time_profiles` | 24-element hourly weight arrays per activity type |
| `screen.width/height` | Must match work computer's display resolution |
| `claude.model` | Claude model for content generation |
| `command_server.port` | Engine HTTP control port (default 7777) |

---

## PWA API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Engine state, current activity, persona, override state |
| `/api/start` | POST | Start engine |
| `/api/stop` | POST | Stop engine |
| `/api/pause` | POST | Pause/resume engine |
| `/api/persona` | POST | Set active persona |
| `/api/override` | GET | Get override state |
| `/api/override` | POST | Enable override (`{duration_minutes: N}` or `{}` for indefinite) |
| `/api/override` | DELETE | Disable override |
| `/api/activity` | POST | Force activity type (`{activity: "typing\|mouse\|idle"}`) |
| `/api/activity` | DELETE | Clear forced activity (back to auto) |
| `/api/bluetooth` | GET/POST | Get/set HID mode (`usb` or `bluetooth`) |
| `/api/bluetooth/discover` | POST | Make Pi discoverable for BT pairing |
| `/api/settings` | GET/POST | Get/set screen resolution |
| `/api/activity_log` | GET | Last 8 activity log entries |
| `/api/dead_zones` | POST | Add dead zone |
| `/api/dead_zones/<n>` | PUT/DELETE | Update/delete dead zone |

---

## PWA Keyboard Shortcut

| Shortcut | Action |
|----------|--------|
| `Ctrl+Shift+P` | Pause / resume engine |

---

## Deployment

**Pi SSH:** `pi@raspberrypi.local` (or by IP — check router device list)
**Repo:** `github.com/katebspurr-png/presence`
**Family Hub PWA:** `http://<pi-ip>:5000`

**Fresh install (after flashing SD card):**
```bash
ssh pi@<ip>
git clone https://github.com/katebspurr-png/presence.git
cd presence
bash setup/install.sh
sudo reboot
```

**After reboot — fix HID permissions (until udev rule is baked in):**
```bash
sudo chmod 666 /dev/hidg0 /dev/hidg1
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

## Current Status (2026-05-03)

- [x] Behavioral engine — fully implemented, 156 tests
- [x] Family Hub PWA — fully implemented
- [x] USB HID gadget mode — working on Pi
- [x] Pi deployed and running
- [x] Claude API connected (typing with real content)
- [x] Bluetooth HID architecture — implemented (L2CAP socket layer)
- [x] Override mode — bypass time restrictions with optional timer
- [x] Forced activity mode — lock engine to typing/mouse/idle from PWA
- [x] Keyboard shortcut — Ctrl+Shift+P to pause/resume
- [x] Screen resolution config in PWA
- [x] BT mode switch in PWA
- [ ] Bluetooth HID — needs D-Bus Profile1 socket fix (bluetoothd owns PSMs)
- [ ] WiFi captive portal — code written, not yet tested end-to-end
- [ ] WPM slider + screen size presets in PWA
- [ ] README for end-to-end deployment

---

## Roadmap

### Next (immediate)
1. Bluetooth D-Bus Profile1 fix — let bluetoothd own PSMs, get socket via callback
2. WPM slider in PWA — per-session typing speed override
3. Screen size presets in PWA — MacBook Air, 1080p, 1440p buttons

### Near term
4. Application focus simulation — some trackers log active app; Presence doesn't touch this
5. Screenshot coverage — document that user should leave a realistic window open
6. README for end-to-end deployment and customer setup
7. WiFi captive portal end-to-end test

### Product / longer term
8. Customer packaging — clean install for non-technical users
9. Idle detection gap — some tools flag no specific-app activity
10. Dual-mode HID (USB + BT simultaneously)
