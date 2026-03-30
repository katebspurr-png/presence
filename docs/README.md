# Presence

Behavioral engine for Raspberry Pi Zero 2W (Infinite Saturdays). Simulates realistic human computer activity via USB/Bluetooth HID.

## Hardware

- Raspberry Pi Zero 2W
- USB gadget mode: keyboard (`/dev/hidg0`) and mouse (`/dev/hidg1`) to host
- Bluetooth HID pairing for wireless operation

## Project Structure

```
presence/
├── engine/
│   ├── scheduler.py         # Main state machine loop
│   ├── activity_selector.py # Time-of-day weighting + dead zone detection
│   ├── distributions.py     # Gaussian/Exponential duration samplers
│   ├── personas.py          # 5 persona definitions
│   ├── activities/
│   │   ├── typing.py        # Claude API content + 55-string fallback bank
│   │   ├── mouse.py         # Bezier curve mouse movement
│   │   ├── idle.py          # Micro-pause
│   │   └── dead_stop.py     # Meeting block silence
│   ├── hid/
│   │   ├── keyboard.py      # USB HID scan codes, QWERTY typo injection
│   │   └── mouse.py         # Bezier movement, easing, scroll events
│   ├── status.py            # Thread-safe shared state
│   ├── logger.py            # SQLite + stdout logging
│   ├── config_watcher.py    # Live config reload
│   └── command_server.py    # HTTP control endpoint
├── config.json              # Runtime configuration
├── run.py                   # Entrypoint
└── presence.service         # systemd unit
```

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here
python3 run.py
```

## Configuration

Edit `config.json` — changes are picked up live without restart.

Key settings:

| Key | Description |
|---|---|
| `persona` | `focused_writer` \| `distracted_multitasker` \| `slow_and_steady` \| `power_user` \| `custom` |
| `dead_zones` | List of `{start, end, days}` meeting blocks |
| `time_profiles` | 24-element hourly weight arrays per activity type |
| `claude.model` | Claude model (default: `claude-sonnet-4-20250514`) |
| `screen.width` / `screen.height` | **Must match the target computer's actual display resolution.** Incorrect values cause cursor movement to cluster near the screen centre or hit invisible bounds. Default: 1920×1080. |

## systemd Deployment

```bash
sudo cp presence.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable presence
sudo systemctl start presence
sudo journalctl -u presence -f
```

## HTTP Control API

Runs on `127.0.0.1:7777` (configurable in `config.json`).

| Method | Path | Action |
|---|---|---|
| GET | `/status` | Current activity, persona, next change time, time until dead zone |
| POST | `/start` | Start / resume engine |
| POST | `/stop` | Stop engine |
| POST | `/pause` | Toggle pause |

## Running Tests

```bash
python3 -m pytest tests/ -v
```

115 tests. Integration smoke tests take ~40s.

## Activity Types

| Type | Distribution | Description |
|---|---|---|
| `typing` | Gaussian | Generates content via Claude API or fallback bank; types via USB HID with QWERTY typo injection |
| `mouse` | Exponential | Bezier curve movement with easing, micro-pauses, and scroll events via USB HID |
| `idle` | Exponential | Micro-pause, no HID output |
| `dead_stop` | Duration = zone remainder | Complete silence during meeting blocks |

## Personas

| Persona | WPM | Typo rate | Thinking pauses | Character |
|---|---|---|---|---|
| `focused_writer` | 70 | 1% | Rare (5%), long (3s) | Long typing bursts, rare mouse |
| `distracted_multitasker` | 55 | 2.5% | Frequent (20%), short (1.5s) | Short bursts, frequent mouse/idle |
| `slow_and_steady` | 35 | 0.5% | Very rare (3%), medium (2.5s) | Stretched durations, low variance |
| `power_user` | 90 | 3% | Rare (5%), short (1s) | Fast, dense, short gaps |
| `custom` | configurable | configurable | configurable | All params from `config.json` |

74 tests → 115 tests. Run with: `python3 -m pytest tests/ -v`
