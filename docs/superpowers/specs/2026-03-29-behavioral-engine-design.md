# Presence Behavioral Engine — Design Spec
**Date:** 2026-03-29
**Project:** Presence (Infinite Saturdays)
**Scope:** Behavioral engine core — scheduler, activity selector, timing distributions

---

## Overview

Presence is a Raspberry Pi Zero 2W device that presents as a Bluetooth/USB HID keyboard and mouse to a host computer. It runs a behavioral engine that simulates realistic human computer activity to avoid detection by workplace monitoring software.

This spec covers the behavioral engine core: the daemon process, state machine, activity selection, timing distributions, config schema, logging, and error handling. It does not cover the Flask PWA, HID gadget setup, or Bluetooth pairing.

---

## Project Structure

```
presence/
├── engine/
│   ├── __init__.py
│   ├── scheduler.py            # main loop + state machine
│   ├── activity_selector.py    # time-of-day weighting, persona-aware selection
│   ├── distributions.py        # Gaussian/Exponential helpers
│   ├── activities/
│   │   ├── __init__.py
│   │   ├── base.py             # ActivityBase with run() interface
│   │   ├── typing.py           # calls Claude API, writes to /dev/hidg0
│   │   ├── mouse.py            # writes to /dev/hidg1
│   │   ├── idle.py             # micro-pauses, no HID output
│   │   └── dead_stop.py        # complete silence
│   ├── personas.py             # 5 persona definitions as dataclasses
│   ├── config_watcher.py       # polls config.json mtime, fires reload event
│   ├── command_server.py       # localhost HTTP on 127.0.0.1:7777
│   ├── status.py               # EngineStatus dataclass + thread-safe StatusStore
│   └── logger.py               # SQLite + stdout dual logging
├── config.json
├── requirements.txt
├── presence.service            # systemd unit file
├── run.py                      # entrypoint
└── docs/
    └── README.md
```

---

## Threading Model

Three threads share two synchronization objects and one status store.

```
MainThread (Engine)
  └── while True state machine
       ├── check EngineControl events (pause/stop/reload)
       ├── pick activity via ActivitySelector
       ├── execute activity.run()
       ├── emit EngineStatus → StatusStore
       └── interruptible_sleep(next_duration, control)

BackgroundThread: ConfigWatcher
  └── polls config.json mtime every 2s
       └── on change: parses JSON, fires reload Event, pushes to ConfigStore

BackgroundThread: CommandServer
  └── minimal HTTP on 127.0.0.1:7777
       ├── POST /start  → sets EngineControl.running
       ├── POST /stop   → sets EngineControl.stopped
       ├── POST /pause  → toggles EngineControl.paused
       └── GET  /status → returns StatusStore.snapshot() as JSON
```

**Shared objects (all thread-safe):**

| Object | Type | Purpose |
|---|---|---|
| `EngineControl` | 4x `threading.Event` | `running`, `paused`, `stopped`, `reload` signals |
| `StatusStore` | `threading.Lock` + dict | current engine status for PWA |
| `ConfigStore` | `threading.Lock` + dict | parsed config, swapped atomically on reload |

**Interruptible sleep** — the engine never blocks longer than ~1 second on control events:

```python
def interruptible_sleep(duration: float, control: EngineControl) -> None:
    end = time.monotonic() + duration
    while time.monotonic() < end:
        if control.stopped.is_set() or control.paused.is_set():
            break
        time.sleep(1)
```

Config reloads happen between activities, never mid-activity.

---

## Activity Selection

### Time-of-Day Profiles

The config defines 24-element weight vectors (one per hour) for each activity type. At each selection, the scheduler reads the current hour, normalizes the four weights for that hour, and samples using `random.choices`.

### Dead Zones

Dead zones are `{start, end, days}` blocks in config. Checked before each activity selection. During a dead zone, `dead_stop` is forced regardless of weights. The status dict always includes `time_until_dead_zone` by scanning the next 24 hours of upcoming blocks.

### Personas

Five personas defined as dataclasses. Each overrides distribution parameters and typing WPM. The `ActivitySelector` merges persona overrides onto base config parameters at selection time — the config dict is never mutated.

| Persona | Character |
|---|---|
| `focused_writer` | Long typing bursts (mean 180s), rare mouse, low idle rate |
| `distracted_multitasker` | Short typing (mean 40s), frequent mouse, high idle rate |
| `slow_and_steady` | All durations stretched, low variance across all types |
| `power_user` | Fast WPM (90), short gaps, high activity density |
| `custom` | Pass-through: all parameters sourced directly from config, no overrides. **Stub only — not yet implemented.** |

---

## Timing Distributions

| Activity | Distribution | Parameters | Rationale |
|---|---|---|---|
| typing | Gaussian(mean, stddev) | per-persona | Writing sessions cluster around a typical length |
| mouse/browse | Exponential(λ) | per-persona | Bursty; most interactions are short |
| idle | Exponential(λ) | per-persona | Memoryless micro-pauses |
| dead_stop | Gaussian(mean, stddev) | per-persona | Meeting blocks have expected lengths |

All durations are floored at 1 second and capped at reasonable maxima to prevent degenerate draws.

---

## Status Dict

Emitted to `StatusStore` after every state transition:

```python
{
    "activity": "typing",           # current activity type
    "persona": "focused_writer",    # active persona
    "next_change_at": "14:32:10",   # estimated time of next activity change
    "time_until_dead_zone_s": 1840  # seconds until next dead zone (None if none today)
}
```

---

## Config Schema (`config.json`)

```json
{
  "persona": "focused_writer",
  "dead_zones": [
    { "start": "09:00", "end": "09:30", "days": ["mon","tue","wed","thu","fri"] }
  ],
  "time_profiles": {
    "typing":    [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.2, 0.4, 0.6, 0.7, 0.7, 0.6,
                  0.5, 0.6, 0.7, 0.6, 0.5, 0.3, 0.2, 0.1, 0.1, 0.1, 0.1, 0.1],
    "mouse":     [0.05,0.05,0.05,0.05,0.05,0.05,0.1, 0.3, 0.5, 0.5, 0.5, 0.4,
                  0.4, 0.5, 0.5, 0.4, 0.3, 0.2, 0.1, 0.05,0.05,0.05,0.05,0.05],
    "idle":      [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.2, 0.2, 0.2, 0.2, 0.3,
                  0.3, 0.2, 0.2, 0.2, 0.3, 0.3, 0.4, 0.4, 0.4, 0.4, 0.3, 0.3],
    "dead_stop": [0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.4, 0.1, 0.05,0.05,0.05,0.1,
                  0.1, 0.05,0.05,0.1, 0.1, 0.2, 0.3, 0.5, 0.6, 0.6, 0.6, 0.6]
  },
  "personas": {
    "focused_writer":         { "typing_mean_s": 180, "typing_stddev_s": 30, "mouse_lambda": 0.05, "idle_lambda": 0.2,  "wpm": 70 },
    "distracted_multitasker": { "typing_mean_s": 40,  "typing_stddev_s": 15, "mouse_lambda": 0.3,  "idle_lambda": 0.8,  "wpm": 55 },
    "slow_and_steady":        { "typing_mean_s": 120, "typing_stddev_s": 10, "mouse_lambda": 0.1,  "idle_lambda": 0.3,  "wpm": 35 },
    "power_user":             { "typing_mean_s": 90,  "typing_stddev_s": 20, "mouse_lambda": 0.15, "idle_lambda": 0.1,  "wpm": 90 },
    "custom":                 { "typing_mean_s": 90,  "typing_stddev_s": 20, "mouse_lambda": 0.15, "idle_lambda": 0.25, "wpm": 60 }
  },
  "claude": {
    "model": "claude-sonnet-4-20250514",
    "content_types": ["email", "notes", "code_comments"],
    "max_tokens": 300
  },
  "command_server": {
    "host": "127.0.0.1",
    "port": 7777
  },
  "hid": {
    "keyboard": "/dev/hidg0",
    "mouse": "/dev/hidg1"
  },
  "logging": {
    "db_path": "/var/log/presence/presence.db",
    "stdout": true
  }
}
```

---

## SQLite Schema

Single append-only table:

```sql
CREATE TABLE activity_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,     -- ISO8601 UTC
    activity    TEXT NOT NULL,     -- typing|mouse|idle|dead_stop
    persona     TEXT NOT NULL,
    duration_s  REAL NOT NULL,
    metadata    TEXT               -- JSON blob: wpm, content_type, claude_model, etc.
);
```

---

## Logging

`logger.py` exposes a single `log_activity(event: ActivityEvent)` call. Writes to both sinks:

- **stdout**: Python `logging` module, key=value format for clean journald parsing
- **SQLite**: synchronous write after each activity completes, never during

---

## Error Handling

| Failure | Behavior |
|---|---|
| Claude API failure | Log + fall back to pre-baked content bank (50+ hardcoded strings in `typing.py`, split across `email`, `notes`, `code_comments` types). A `used_recently` set tracks strings used in the last 2 hours; selection skips any string in that set, falling back to a random pick only if all strings of that type were recently used. |
| HID device unavailable | Log warning, skip write, continue — engine runs on non-Pi hardware |
| Config parse error on reload | Log error, keep last valid config — never swap in a broken config |
| SQLite write failure | Log to stdout only, continue |
| Unhandled exception in `activity.run()` | Catch at scheduler loop, log traceback, skip to next selection |

The engine loop never dies from a single failed activity.

---

## Testing

- **Unit**: `distributions.py` (output range/shape), `activity_selector.py` (mocked time + config, weighted selection), dead zone logic, interruptible sleep
- **Integration smoke test**: run engine for 10 simulated seconds with HID writes mocked, assert status dict populated and SQLite has entries
- HID paths and Claude client are injectable dependencies — no Pi hardware required for any test

---

## Out of Scope (this spec)

- Flask PWA implementation
- HID gadget kernel module setup
- Bluetooth pairing
- `Custom` persona parameter logic (stub only)
- Mouse movement algorithms (bezier curves, etc.)
- Typing keystroke encoding for `/dev/hidg0`
