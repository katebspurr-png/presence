# Family Hub PWA — Design Spec
**Date:** 2026-03-30
**Project:** Presence (Infinite Saturdays)
**Scope:** Flask PWA — status dashboard, controls, persona selector, activity feed, dead zone editor

---

## Overview

Family Hub is a mobile-first progressive web app that provides a control interface for the Presence behavioral engine. It is served by a Flask process on port 5000 and communicates with the existing command server (port 7777) via HTTP proxy. The cover name "Family Hub" and neutral icon conceal the device's purpose.

No authentication is required. Access is restricted to the local network by network topology. README notes that this assumes a trusted local network.

---

## Project Structure

```
pwa/
├── __init__.py
├── app.py              # Flask app factory + all routes
├── templates/
│   └── index.html      # Single-page app (Jinja2 template)
└── static/
    ├── manifest.json   # PWA manifest
    └── icon.svg        # Neutral home screen icon (house outline, terracotta)

run_pwa.py              # Entrypoint — binds 0.0.0.0:5000
presence-pwa.service    # systemd unit for the PWA process
```

**Modified files:**
- `requirements.txt` — add `flask>=3.0.0`
- `engine/command_server.py` — enrich `/status` response with `engine_state`
- `engine/personas.py` — rename `slow_and_steady` → `steady`
- `config.json` — rename persona key and display label
- `tests/test_command_server.py` — assert `engine_state` in status response
- `tests/test_personas.py` — update fixture and assertions
- `docs/README.md` — add PWA section, screen config note, trusted network warning

---

## Architecture

Flask runs as a **separate process** from the engine. It proxies control commands to the command server on `127.0.0.1:7777` and reads/writes `config.json` directly for persona and dead zone changes. The config watcher detects file mtime changes and reloads the engine automatically — no special signaling required.

```
Phone browser
    │
    │  HTTP  (port 5000, LAN)
    ▼
Flask PWA (run_pwa.py)
    ├── GET  /                     → serve index.html
    ├── GET  /api/ping             → {ok: true}
    ├── GET  /api/status           → proxy → command server :7777/status
    ├── POST /api/start|stop|pause → proxy → command server :7777/*
    ├── POST /api/persona          → write config.json + config watcher picks up
    ├── GET  /api/activity_log     → read SQLite directly
    ├── POST /api/dead_zones       → write config.json
    ├── PUT  /api/dead_zones/<idx> → write config.json
    └── DELETE /api/dead_zones/<idx> → write config.json

Config watcher (engine thread)
    └── polls config.json mtime → fires control.reload on change
```

**Environment variables:**

| Variable | Default | Purpose |
|---|---|---|
| `PRESENCE_CONFIG` | `config.json` | Path to config file (shared with engine) |
| `PRESENCE_COMMAND_URL` | `http://127.0.0.1:7777` | Command server base URL |

---

## Flask Backend (`pwa/app.py`)

### Endpoints

| Route | Method | Description |
|---|---|---|
| `/` | GET | Serve `index.html` |
| `/api/ping` | GET | Returns `{"ok": true}` — PWA connectivity check |
| `/api/status` | GET | Proxy to command server `/status`; `engine_state` field included |
| `/api/start` | POST | Proxy to command server `/start` |
| `/api/stop` | POST | Proxy to command server `/stop` |
| `/api/pause` | POST | Proxy to command server `/pause` (toggles paused/resumed) |
| `/api/persona` | POST | `{"persona": "steady"}` — validates, writes config.json atomically |
| `/api/activity_log` | GET | Query SQLite `ORDER BY id DESC LIMIT 8`, return JSON array |
| `/api/dead_zones` | POST | Append dead zone to config, atomic write |
| `/api/dead_zones/<int:index>` | PUT | Replace dead zone at index |
| `/api/dead_zones/<int:index>` | DELETE | Remove dead zone at index |

### Atomic config writes

All config mutations use write-then-replace:
```python
tmp = CONFIG_PATH.with_suffix(".json.tmp")
with open(tmp, "w") as f:
    json.dump(config, f, indent=2)
os.replace(tmp, CONFIG_PATH)  # atomic on Linux
```

### Error handling

| Failure | Response |
|---|---|
| Command server unreachable (`URLError`) | 503 `{"error": "engine offline"}` |
| Unknown persona name | 400 `{"error": "unknown persona"}` |
| Dead zone index out of range | 404 `{"error": "index out of range"}` |
| SQLite unavailable | 200 with empty array `[]` (graceful) |
| Config parse/write error | 500 `{"error": "config error"}` |

### `engine_state` enrichment (command_server.py change)

The `/status` GET handler appends `engine_state` derived from `EngineControl` events before returning the snapshot:

```python
if control.stopped.is_set() or not control.running.is_set():
    snapshot["engine_state"] = "stopped"
elif control.paused.is_set():
    snapshot["engine_state"] = "paused"
else:
    snapshot["engine_state"] = "running"
```

No changes to `StatusStore` or the scheduler.

---

## Frontend (`pwa/templates/index.html`)

Single Jinja2 template. Vanilla JS, no build step, no external JS dependencies.

### Visual design

| Token | Value |
|---|---|
| Background | `#FAFAF8` |
| Card background | `#FFFFFF` |
| Accent / primary | `#C4785A` (terracotta) |
| Text | `#2C2C2A` |
| Muted text | `#9A9087` |
| Border | `#E8E2DC` |
| Pill active | `#C4785A` fill, white text |
| Border radius (card) | `16px` |
| Border radius (button) | `12px` |
| Shadow | `0 2px 12px rgba(44,44,42,0.07)` |

### Page layout (top to bottom)

1. **Header** — "Family Hub" wordmark, small, uppercase, muted colour
2. **Status card** — live activity name, persona badge, next change time, dead zone countdown. Pulsing dot when `engine_state === "running"`, dim dot otherwise.
3. **Controls card** — three-state primary + secondary button (see below)
4. **Persona card** — horizontal pill selector, 4 options
5. **Activity feed card** — last 8 entries
6. **Dead zone editor** — collapsible `<details>` (see below)

### Controls three-state logic

| `engine_state` | Primary (terracotta) | Secondary (outline) |
|---|---|---|
| `running` | Stop → POST /api/stop | Pause → POST /api/pause |
| `paused` | Resume → POST /api/pause | Stop → POST /api/stop |
| `stopped` | Start → POST /api/start | Pause (ghosted, `disabled`) |

After any control action, immediately re-fetch `/api/status` without waiting for the 3s poll interval.

### Polling

- `/api/status` every **3 seconds** — updates status card + controls + persona active pill
- `/api/activity_log` every **10 seconds** — updates feed
- On fetch error (command server down): show subtle "Offline" badge on status card, retain last known state in UI
- `visibilitychange` event listener: when `document.visibilityState === "visible"` after backgrounding, immediately fetch both `/api/status` and `/api/activity_log` without waiting for the next poll interval

### Persona selector

UI labels → API persona names:

| Pill | API name |
|---|---|
| Focused | `focused_writer` |
| Multitasker | `distracted_multitasker` |
| Steady | `steady` |
| Power User | `power_user` |

On tap: POST `/api/persona`, immediately re-fetch status to reflect change.

### Activity feed

- Activity name mapping: `typing→Typing`, `mouse→Mouse`, `idle→Idle`, `dead_stop→Meeting`
- Duration format: `Xm Ys` if ≥60s, `Xs` if under a minute
- Time shown from `ts` field (ISO8601 UTC → local time via JS `Date`)
- Icon per type: ⌨ typing, 🖱 mouse, ⏸ idle, 📅 meeting

### Dead zone editor

A `<details>` element, collapsed by default. Positioned below the activity feed.

**Summary line:** "X dead zones today" (count of zones where today's lowercase 3-letter day abbreviation is in the zone's `days` array) or "No dead zones set."

**Expanded content:**

1. **Timeline bar** — SVG, 8am–6pm range (600 minutes). Each dead zone in today's schedule renders as a terracotta filled rect. Tap a block to pre-populate the form with that zone's values and show Update/Delete actions. Tapping outside deselects.

2. **Form fields:**
   - Start time: `<input type="time">`
   - End time: `<input type="time">`
   - Repeat toggle: checkbox. Default **off** when creating new (applies to today's day only). Pre-populated zones use their existing `days` array — if it contains more than one day, repeat is shown as on.
   - Day pills: M T W T F — visible only when repeat is on. All selected by default for new zones. Toggle individually.

3. **Actions:**
   - **Add** (new zone): POST `/api/dead_zones` with `{start, end, days}`
   - **Update** (editing existing): PUT `/api/dead_zones/<index>`
   - **Delete** (editing existing): DELETE `/api/dead_zones/<index>`
   - **Cancel**: deselect and reset form

   On any save action: re-fetch `/api/status`, re-render timeline and summary line.

**Repeat off → days:** the current day's 3-letter lowercase abbreviation (e.g. `"mon"`) as a single-element array.

**Repeat on → days:** the selected day pills as a lowercase 3-letter array, e.g. `["mon","tue","wed","thu","fri"]`.

---

## PWA Manifest (`pwa/static/manifest.json`)

```json
{
  "name": "Family Hub",
  "short_name": "Family Hub",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#FAFAF8",
  "theme_color": "#C4785A",
  "icons": [
    { "src": "/static/icon.svg", "sizes": "any", "type": "image/svg+xml" }
  ]
}
```

Icon: simple house outline in terracotta (`#C4785A`) on transparent background, no text, no keyboard or mouse elements. The SVG file must be fully rendered (complete path data, no placeholders).

---

## Persona Rename: `slow_and_steady` → `steady`

All occurrences updated in one commit:
- `engine/personas.py` — `_BUILTIN_PERSONAS` key and `PersonaParams.name`
- `config.json` — persona key in `personas` block
- `tests/test_personas.py` — fixture and test assertions
- `tests/test_activity_selector.py` — any reference in test configs
- `tests/test_scheduler.py` — any reference in test configs
- `docs/README.md` — persona table

---

## Testing (`tests/test_pwa.py`)

Uses Flask test client. Config reads/writes use a temp file (pytest `tmp_path`). Command server calls mocked via `unittest.mock.patch`.

**Tests:**
- `GET /api/ping` → 200 `{"ok": true}`
- `GET /api/status` → proxied response with `engine_state` field
- `POST /api/start|stop|pause` → proxy calls correct command server paths
- Command server unreachable → 503 `{"error": "engine offline"}`
- `POST /api/persona` valid name → writes config, returns `{"persona": name}`
- `POST /api/persona` unknown name → 400
- `GET /api/activity_log` → returns ≤8 entries with correct shape
- `GET /api/activity_log` with missing SQLite → returns `[]`
- `POST /api/dead_zones` → appends zone, returns updated list
- `PUT /api/dead_zones/0` → updates zone, returns updated list
- `DELETE /api/dead_zones/0` → removes zone, returns updated list
- `PUT /api/dead_zones/99` → 404
- `DELETE /api/dead_zones/99` → 404

**Updated existing tests:**
- `tests/test_command_server.py` — assert `engine_state` present in `/status` response for running, paused, and stopped control states
- `tests/test_personas.py` — `steady` replaces `slow_and_steady` in fixture and all assertions

---

## Out of Scope (this spec)

- Authentication / access control
- Dead zone recurrence beyond day-of-week (e.g. date-specific one-off blocks)
- Advanced config editing (time profiles, distribution parameters)
- Push notifications
- Dark mode
