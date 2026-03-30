# Family Hub PWA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Flask PWA ("Family Hub") that provides a mobile-first control interface for the Presence behavioral engine, including status dashboard, engine controls, persona selector, activity feed, and a dead zone editor.

**Architecture:** Flask runs as a separate process (`run_pwa.py`) proxying control commands to the command server on port 7777 and reading/writing `config.json` directly. A single-page `index.html` (vanilla JS, no build step) polls `/api/status` every 3s and `/api/activity_log` every 10s, and re-fetches immediately on tab visibility restored. The `engine_state` field is computed in `command_server.py` from `EngineControl` events and included in every `/status` response.

**Tech Stack:** Python 3, Flask ≥ 3.0, SQLite (stdlib), urllib (stdlib), Jinja2, vanilla HTML/CSS/JS, SVG timeline, PWA manifest

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `engine/personas.py` | Rename `slow_and_steady` → `steady` |
| Modify | `config.json` | Rename `slow_and_steady` key → `steady` |
| Modify | `tests/test_personas.py` | Update test name and assertion |
| Modify | `docs/README.md` | Update persona table and config docs |
| Modify | `engine/command_server.py` | Add `engine_state` to `/status` response |
| Modify | `tests/test_command_server.py` | Assert `engine_state` in all three states |
| Modify | `requirements.txt` | Add `flask>=3.0.0` |
| Create | `pwa/__init__.py` | Package marker |
| Create | `pwa/app.py` | Flask app factory — all routes |
| Create | `run_pwa.py` | Entrypoint: binds 0.0.0.0:5000 |
| Create | `presence-pwa.service` | systemd unit for PWA process |
| Create | `pwa/static/manifest.json` | PWA manifest |
| Create | `pwa/static/icon.svg` | House outline icon, terracotta |
| Create | `pwa/templates/index.html` | Full single-page app |
| Create | `tests/test_pwa.py` | Flask test client tests |

---

## Task 1: Rename `slow_and_steady` → `steady`

**Files:**
- Modify: `engine/personas.py`
- Modify: `config.json`
- Modify: `tests/test_personas.py`
- Modify: `docs/README.md`

- [ ] **Step 1: Rename the key and `name` field in `engine/personas.py`**

In `_BUILTIN_PERSONAS`, change the key `"slow_and_steady"` to `"steady"` and the `name` field to `"steady"`:

```python
    "steady": PersonaParams(
        name="steady",
        typing_mean_s=120,
        typing_stddev_s=10,
        mouse_lambda=0.1,
        idle_lambda=0.3,
        wpm=35,
        typo_rate=0.005,
        thinking_pause_p=0.03,
        thinking_pause_mean_s=2.5,
    ),
```

- [ ] **Step 2: Rename the key in `config.json`**

Change the `"slow_and_steady"` key inside `"personas"` to `"steady"`. The values stay the same:

```json
    "steady":                 { "typing_mean_s": 120, "typing_stddev_s": 10, "mouse_lambda": 0.1,  "idle_lambda": 0.3,  "wpm": 35, "typo_rate": 0.005, "thinking_pause_p": 0.03, "thinking_pause_mean_s": 2.5 },
```

- [ ] **Step 3: Update `tests/test_personas.py`**

Rename the test function and update the `get_persona` call:

```python
def test_get_persona_steady():
    p = get_persona("steady", SAMPLE_CONFIG)
    assert p.typing_stddev_s == 10
    assert p.wpm == 35
```

- [ ] **Step 4: Update persona table in `docs/README.md`**

In the Configuration table, change:
```
| `persona` | `focused_writer` \| `distracted_multitasker` \| `slow_and_steady` \| `power_user` \| `custom` |
```
to:
```
| `persona` | `focused_writer` \| `distracted_multitasker` \| `steady` \| `power_user` \| `custom` |
```

In the Personas table, change:
```
| `slow_and_steady` | 35 | 0.5% | Very rare (3%), medium (2.5s) | Stretched durations, low variance |
```
to:
```
| `steady` | 35 | 0.5% | Very rare (3%), medium (2.5s) | Stretched durations, low variance |
```

- [ ] **Step 5: Run tests to verify nothing else broke**

```bash
python3 -m pytest tests/test_personas.py -v
```

Expected: All tests pass. The renamed test should show as `test_get_persona_steady`.

- [ ] **Step 6: Commit**

```bash
git add engine/personas.py config.json tests/test_personas.py docs/README.md
git commit -m "refactor: rename slow_and_steady persona to steady"
```

---

## Task 2: Add `engine_state` to command server `/status`

**Files:**
- Modify: `engine/command_server.py`
- Modify: `tests/test_command_server.py`

- [ ] **Step 1: Write three failing tests in `tests/test_command_server.py`**

Add after the existing `test_get_status_returns_snapshot` test:

```python
def test_status_engine_state_running(server):
    srv, ctrl, store = server
    ctrl.running.set()
    ctrl.stopped.clear()
    ctrl.paused.clear()
    data = _get("/status")
    assert data["engine_state"] == "running"


def test_status_engine_state_paused(server):
    srv, ctrl, store = server
    ctrl.running.set()
    ctrl.paused.set()
    data = _get("/status")
    assert data["engine_state"] == "paused"


def test_status_engine_state_stopped(server):
    srv, ctrl, store = server
    ctrl.running.clear()
    ctrl.stopped.set()
    data = _get("/status")
    assert data["engine_state"] == "stopped"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_command_server.py::test_status_engine_state_running tests/test_command_server.py::test_status_engine_state_paused tests/test_command_server.py::test_status_engine_state_stopped -v
```

Expected: FAIL — `engine_state` key not in response.

- [ ] **Step 3: Modify `do_GET` in `engine/command_server.py`**

Replace the existing `do_GET` method inside `_make_handler`:

```python
        def do_GET(self):
            if self.path == "/status":
                snapshot = dict(status_store.snapshot() or {})
                if control.stopped.is_set() or not control.running.is_set():
                    snapshot["engine_state"] = "stopped"
                elif control.paused.is_set():
                    snapshot["engine_state"] = "paused"
                else:
                    snapshot["engine_state"] = "running"
                self._send_json(200, snapshot)
            else:
                self._send_json(404, {"error": "not found"})
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_command_server.py -v
```

Expected: All 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add engine/command_server.py tests/test_command_server.py
git commit -m "feat: add engine_state to command server /status response"
```

---

## Task 3: Flask backend scaffold (ping endpoint)

**Files:**
- Modify: `requirements.txt`
- Create: `pwa/__init__.py`
- Create: `pwa/app.py`
- Create: `run_pwa.py`
- Create: `tests/test_pwa.py`

- [ ] **Step 1: Add Flask to `requirements.txt`**

```
anthropic>=0.30.0
flask>=3.0.0
pytest>=8.0.0
```

- [ ] **Step 2: Install Flask**

```bash
pip install flask>=3.0.0
```

- [ ] **Step 3: Create `pwa/__init__.py`**

```python
```
(empty file — package marker only)

- [ ] **Step 4: Write the ping test in `tests/test_pwa.py`**

```python
import json
import sqlite3
import unittest.mock as mock
from urllib.error import URLError

import pytest

from pwa.app import create_app


def _mock_response(body, status=200):
    """Build a mock urllib response context manager."""
    m = mock.MagicMock()
    m.read.return_value = json.dumps(body).encode()
    m.status = status
    m.__enter__ = lambda s: s
    m.__exit__ = mock.MagicMock(return_value=False)
    return m


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "presence.db"
    cfg = {
        "persona": "focused_writer",
        "dead_zones": [{"start": "09:00", "end": "09:30", "days": ["mon"]}],
        "logging": {"db_path": str(db_path)},
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(cfg))
    app = create_app(config_path=str(config_path))
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c, config_path, db_path


def test_ping_returns_ok(client):
    c, _, _ = client
    resp = c.get("/api/ping")
    assert resp.status_code == 200
    assert json.loads(resp.data) == {"ok": True}
```

- [ ] **Step 5: Run test to verify it fails**

```bash
python3 -m pytest tests/test_pwa.py::test_ping_returns_ok -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'pwa'` or `ImportError`.

- [ ] **Step 6: Create `pwa/app.py` with factory and ping endpoint**

```python
import json
import os
import sqlite3
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from flask import Flask, jsonify, render_template, request

VALID_PERSONAS = frozenset({
    "focused_writer", "distracted_multitasker", "steady", "power_user", "custom"
})


def create_app(config_path=None, command_url=None):
    if config_path is None:
        config_path = os.environ.get("PRESENCE_CONFIG", "config.json")
    config_path = Path(config_path)
    if command_url is None:
        command_url = os.environ.get("PRESENCE_COMMAND_URL", "http://127.0.0.1:7777")

    app = Flask(__name__)

    def _read_config():
        with open(config_path) as f:
            return json.load(f)

    def _write_config(cfg):
        tmp = config_path.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(cfg, f, indent=2)
        os.replace(tmp, config_path)

    def _proxy(path, method="GET"):
        try:
            if method == "GET":
                with urlopen(f"{command_url}{path}", timeout=5) as r:
                    return json.loads(r.read()), r.status
            else:
                req = Request(f"{command_url}{path}", data=b"", method=method)
                with urlopen(req, timeout=5) as r:
                    return json.loads(r.read()), r.status
        except URLError:
            return None, None

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/ping")
    def ping():
        return jsonify({"ok": True})

    return app
```

- [ ] **Step 7: Run test to verify it passes**

```bash
python3 -m pytest tests/test_pwa.py::test_ping_returns_ok -v
```

Expected: PASS.

- [ ] **Step 8: Create `run_pwa.py`**

```python
from pwa.app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
```

- [ ] **Step 9: Commit**

```bash
git add requirements.txt pwa/__init__.py pwa/app.py run_pwa.py tests/test_pwa.py
git commit -m "feat: add Flask PWA scaffold with /api/ping"
```

---

## Task 4: Status proxy and engine control endpoints

**Files:**
- Modify: `pwa/app.py` (add status + start/stop/pause routes)
- Modify: `tests/test_pwa.py` (add 7 tests)

- [ ] **Step 1: Write failing tests — add to `tests/test_pwa.py`**

```python
def test_status_proxies_engine(client):
    c, _, _ = client
    body = {"activity": "typing", "persona": "focused_writer", "engine_state": "running"}
    with mock.patch("pwa.app.urlopen", return_value=_mock_response(body)):
        resp = c.get("/api/status")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["engine_state"] == "running"
    assert data["activity"] == "typing"


def test_status_engine_offline(client):
    c, _, _ = client
    with mock.patch("pwa.app.urlopen", side_effect=URLError("refused")):
        resp = c.get("/api/status")
    assert resp.status_code == 503
    assert json.loads(resp.data)["error"] == "engine offline"


def test_post_start_proxies(client):
    c, _, _ = client
    with mock.patch("pwa.app.urlopen", return_value=_mock_response({"status": "started"})) as m:
        resp = c.post("/api/start")
    assert resp.status_code == 200
    assert m.call_args[0][0].full_url.endswith("/start")


def test_post_stop_proxies(client):
    c, _, _ = client
    with mock.patch("pwa.app.urlopen", return_value=_mock_response({"status": "stopped"})) as m:
        resp = c.post("/api/stop")
    assert resp.status_code == 200
    assert m.call_args[0][0].full_url.endswith("/stop")


def test_post_pause_proxies(client):
    c, _, _ = client
    with mock.patch("pwa.app.urlopen", return_value=_mock_response({"status": "paused"})) as m:
        resp = c.post("/api/pause")
    assert resp.status_code == 200
    assert m.call_args[0][0].full_url.endswith("/pause")


def test_control_engine_offline(client):
    c, _, _ = client
    with mock.patch("pwa.app.urlopen", side_effect=URLError("refused")):
        resp = c.post("/api/start")
    assert resp.status_code == 503
    assert json.loads(resp.data)["error"] == "engine offline"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_pwa.py::test_status_proxies_engine tests/test_pwa.py::test_status_engine_offline tests/test_pwa.py::test_post_start_proxies -v
```

Expected: FAIL — 404 (routes not yet registered).

- [ ] **Step 3: Add status and control routes to `pwa/app.py`**

Inside `create_app()`, after the `ping` route and before `return app`:

```python
    @app.route("/api/status")
    def status():
        data, code = _proxy("/status")
        if data is None:
            return jsonify({"error": "engine offline"}), 503
        return jsonify(data), code

    @app.route("/api/start", methods=["POST"])
    def start():
        data, code = _proxy("/start", method="POST")
        if data is None:
            return jsonify({"error": "engine offline"}), 503
        return jsonify(data), code

    @app.route("/api/stop", methods=["POST"])
    def stop():
        data, code = _proxy("/stop", method="POST")
        if data is None:
            return jsonify({"error": "engine offline"}), 503
        return jsonify(data), code

    @app.route("/api/pause", methods=["POST"])
    def pause():
        data, code = _proxy("/pause", method="POST")
        if data is None:
            return jsonify({"error": "engine offline"}), 503
        return jsonify(data), code
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_pwa.py -v
```

Expected: All 7 tests pass (ping + 6 new).

- [ ] **Step 5: Commit**

```bash
git add pwa/app.py tests/test_pwa.py
git commit -m "feat: add /api/status and engine control proxy endpoints"
```

---

## Task 5: Persona and activity log endpoints

**Files:**
- Modify: `pwa/app.py` (add persona + activity_log routes)
- Modify: `tests/test_pwa.py` (add 4 tests)

- [ ] **Step 1: Write failing tests — add to `tests/test_pwa.py`**

```python
def test_set_persona_valid(client):
    c, config_path, _ = client
    resp = c.post("/api/persona", json={"persona": "steady"})
    assert resp.status_code == 200
    assert json.loads(resp.data) == {"persona": "steady"}
    saved = json.loads(config_path.read_text())
    assert saved["persona"] == "steady"


def test_set_persona_unknown(client):
    c, _, _ = client
    resp = c.post("/api/persona", json={"persona": "ghost"})
    assert resp.status_code == 400
    assert json.loads(resp.data)["error"] == "unknown persona"


def test_activity_log_returns_entries(client):
    c, _, db_path = client
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "CREATE TABLE activity_log "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, activity TEXT, "
            "persona TEXT, duration_s REAL, metadata TEXT)"
        )
        for i in range(10):
            conn.execute(
                "INSERT INTO activity_log VALUES (NULL, ?, 'typing', 'focused_writer', 60.0, '{}')",
                (f"2026-03-30T10:{i:02d}:00Z",),
            )
        conn.commit()
    resp = c.get("/api/activity_log")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert len(data) == 8
    assert data[0]["activity"] == "typing"
    assert "ts" in data[0]
    assert "duration_s" in data[0]


def test_activity_log_missing_db_returns_empty(client):
    c, _, _ = client
    # db_path does not contain the table — sqlite3.connect creates empty file,
    # SELECT fails, exception is caught, returns []
    resp = c.get("/api/activity_log")
    assert resp.status_code == 200
    assert json.loads(resp.data) == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_pwa.py::test_set_persona_valid tests/test_pwa.py::test_activity_log_returns_entries -v
```

Expected: FAIL — 404.

- [ ] **Step 3: Add persona and activity_log routes to `pwa/app.py`**

Inside `create_app()`, before `return app`:

```python
    @app.route("/api/persona", methods=["POST"])
    def set_persona():
        body = request.get_json(force=True, silent=True) or {}
        name = body.get("persona", "")
        if name not in VALID_PERSONAS:
            return jsonify({"error": "unknown persona"}), 400
        try:
            cfg = _read_config()
            cfg["persona"] = name
            _write_config(cfg)
        except Exception:
            return jsonify({"error": "config error"}), 500
        return jsonify({"persona": name})

    @app.route("/api/activity_log")
    def activity_log():
        try:
            cfg = _read_config()
            db_path = cfg.get("logging", {}).get("db_path", "")
            with sqlite3.connect(db_path) as conn:
                rows = conn.execute(
                    "SELECT ts, activity, persona, duration_s FROM activity_log "
                    "ORDER BY id DESC LIMIT 8"
                ).fetchall()
            return jsonify([
                {"ts": r[0], "activity": r[1], "persona": r[2], "duration_s": r[3]}
                for r in rows
            ])
        except Exception:
            return jsonify([])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_pwa.py -v
```

Expected: All 11 tests pass.

- [ ] **Step 5: Commit**

```bash
git add pwa/app.py tests/test_pwa.py
git commit -m "feat: add /api/persona and /api/activity_log endpoints"
```

---

## Task 6: Dead zone CRUD endpoints

**Files:**
- Modify: `pwa/app.py` (add dead_zones routes)
- Modify: `tests/test_pwa.py` (add 5 tests)

- [ ] **Step 1: Write failing tests — add to `tests/test_pwa.py`**

```python
def test_add_dead_zone(client):
    c, config_path, _ = client
    body = {"start": "14:00", "end": "15:00", "days": ["mon", "wed"]}
    resp = c.post("/api/dead_zones", json=body)
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert len(data["dead_zones"]) == 2
    assert data["dead_zones"][-1]["start"] == "14:00"
    saved = json.loads(config_path.read_text())
    assert len(saved["dead_zones"]) == 2


def test_update_dead_zone(client):
    c, config_path, _ = client
    body = {"start": "10:00", "end": "11:00", "days": ["tue"]}
    resp = c.put("/api/dead_zones/0", json=body)
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["dead_zones"][0]["start"] == "10:00"
    assert data["dead_zones"][0]["days"] == ["tue"]


def test_delete_dead_zone(client):
    c, config_path, _ = client
    resp = c.delete("/api/dead_zones/0")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["dead_zones"] == []
    saved = json.loads(config_path.read_text())
    assert saved["dead_zones"] == []


def test_update_dead_zone_out_of_range(client):
    c, _, _ = client
    body = {"start": "10:00", "end": "11:00", "days": ["mon"]}
    resp = c.put("/api/dead_zones/99", json=body)
    assert resp.status_code == 404
    assert json.loads(resp.data)["error"] == "index out of range"


def test_delete_dead_zone_out_of_range(client):
    c, _, _ = client
    resp = c.delete("/api/dead_zones/99")
    assert resp.status_code == 404
    assert json.loads(resp.data)["error"] == "index out of range"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_pwa.py::test_add_dead_zone tests/test_pwa.py::test_delete_dead_zone_out_of_range -v
```

Expected: FAIL — 404 or 405.

- [ ] **Step 3: Add dead zone routes to `pwa/app.py`**

Inside `create_app()`, before `return app`:

```python
    @app.route("/api/dead_zones", methods=["POST"])
    def add_dead_zone():
        body = request.get_json(force=True, silent=True) or {}
        try:
            cfg = _read_config()
            cfg.setdefault("dead_zones", []).append({
                "start": body["start"],
                "end": body["end"],
                "days": body["days"],
            })
            _write_config(cfg)
        except Exception:
            return jsonify({"error": "config error"}), 500
        return jsonify({"dead_zones": cfg["dead_zones"]})

    @app.route("/api/dead_zones/<int:index>", methods=["PUT"])
    def update_dead_zone(index):
        body = request.get_json(force=True, silent=True) or {}
        try:
            cfg = _read_config()
            zones = cfg.get("dead_zones", [])
            if index >= len(zones):
                return jsonify({"error": "index out of range"}), 404
            zones[index] = {
                "start": body["start"],
                "end": body["end"],
                "days": body["days"],
            }
            _write_config(cfg)
        except Exception:
            return jsonify({"error": "config error"}), 500
        return jsonify({"dead_zones": zones})

    @app.route("/api/dead_zones/<int:index>", methods=["DELETE"])
    def delete_dead_zone(index):
        try:
            cfg = _read_config()
            zones = cfg.get("dead_zones", [])
            if index >= len(zones):
                return jsonify({"error": "index out of range"}), 404
            zones.pop(index)
            _write_config(cfg)
        except Exception:
            return jsonify({"error": "config error"}), 500
        return jsonify({"dead_zones": zones})
```

- [ ] **Step 4: Run the full test suite to verify everything passes**

```bash
python3 -m pytest tests/test_pwa.py -v
```

Expected: All 16 tests pass.

- [ ] **Step 5: Commit**

```bash
git add pwa/app.py tests/test_pwa.py
git commit -m "feat: add dead zone CRUD endpoints (POST/PUT/DELETE /api/dead_zones)"
```

---

## Task 7: PWA static files and systemd unit

**Files:**
- Create: `pwa/static/manifest.json`
- Create: `pwa/static/icon.svg`
- Create: `presence-pwa.service`

- [ ] **Step 1: Create `pwa/static/manifest.json`**

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

- [ ] **Step 2: Create `pwa/static/icon.svg`**

Simple house outline in terracotta on transparent background — pentagon body with centered door:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" fill="none">
  <polygon points="50,12 90,46 90,90 10,90 10,46"
           stroke="#C4785A" stroke-width="5" stroke-linejoin="round"/>
  <rect x="37" y="62" width="26" height="28" rx="3"
        stroke="#C4785A" stroke-width="4"/>
</svg>
```

- [ ] **Step 3: Create `presence-pwa.service`**

```ini
[Unit]
Description=Family Hub PWA
After=network.target presence.service

[Service]
User=pi
WorkingDirectory=/home/pi/presence
EnvironmentFile=-/home/pi/presence/.env
ExecStart=/home/pi/presence/venv/bin/python run_pwa.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 4: Commit**

```bash
git add pwa/static/manifest.json pwa/static/icon.svg presence-pwa.service
git commit -m "feat: add PWA manifest, house icon, and systemd unit"
```

---

## Task 8: Frontend — status, controls, persona, activity feed

**Files:**
- Create: `pwa/templates/index.html`

This task creates the full `index.html`. All layout sections except the dead zone editor are included here; the dead zone editor section is added in Task 9 to keep each task focused.

- [ ] **Step 1: Create `pwa/templates/` directory and `index.html`**

```bash
mkdir -p pwa/templates
```

- [ ] **Step 2: Write `pwa/templates/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#C4785A">
<link rel="manifest" href="/static/manifest.json">
<title>Family Hub</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: #FAFAF8;
  color: #2C2C2A;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  min-height: 100vh;
  padding-bottom: 48px;
  max-width: 420px;
  margin: 0 auto;
}

header { padding: 28px 24px 8px; }
.wordmark {
  font-size: 13px; font-weight: 600;
  letter-spacing: .12em; text-transform: uppercase; color: #9A9087;
}

.offline-badge {
  margin: 4px 16px; padding: 6px 12px;
  background: #F7E0D9; color: #C4785A;
  border-radius: 8px; font-size: 12px; font-weight: 600; text-align: center;
}

.card {
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 2px 12px rgba(44,44,42,.07);
  margin: 12px 16px;
  padding: 20px;
}

/* ── Status card ── */
.status-label {
  font-size: 11px; font-weight: 600; letter-spacing: .1em;
  text-transform: uppercase; color: #9A9087;
  margin-bottom: 14px; display: flex; align-items: center; gap: 6px;
}
.dot { width: 7px; height: 7px; border-radius: 50%; background: #C4785A; flex-shrink: 0; }
.dot.pulse { animation: pulse 2s infinite; }
.dot.dim   { opacity: .3; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }

.status-row {
  display: flex; align-items: baseline;
  justify-content: space-between; margin-bottom: 6px;
}
.status-activity { font-size: 26px; font-weight: 600; letter-spacing: -.01em; }
.status-badge {
  background: #F0EAE5; color: #C4785A;
  font-size: 12px; font-weight: 600;
  padding: 4px 10px; border-radius: 20px;
  white-space: nowrap; margin-left: 8px;
}
.status-meta { font-size: 13px; color: #9A9087; margin-top: 4px; }
.status-dz  {
  font-size: 13px; color: #9A9087;
  margin-top: 10px; padding-top: 10px;
  border-top: 1px solid #F0EDE9;
}

/* ── Controls card ── */
.btn-primary {
  display: block; width: 100%; padding: 18px;
  border: none; border-radius: 12px;
  font-size: 16px; font-weight: 600;
  background: #C4785A; color: #fff;
  margin-bottom: 10px; cursor: pointer;
  letter-spacing: .01em; transition: opacity .15s;
}
.btn-primary:active { opacity: .85; }
.btn-secondary {
  display: block; width: 100%; padding: 14px;
  border: 2px solid #E8E2DC; border-radius: 12px;
  font-size: 15px; font-weight: 600;
  background: transparent; color: #7A6E66;
  cursor: pointer; transition: border-color .15s, color .15s;
}
.btn-secondary:active { border-color: #C4785A; color: #C4785A; }
.btn-ghost {
  display: block; width: 100%; padding: 14px;
  border: 2px solid #F0EDE9; border-radius: 12px;
  font-size: 15px; font-weight: 600;
  background: transparent; color: #C0B8B0; cursor: default;
}

/* ── Persona pills ── */
.section-label {
  font-size: 11px; font-weight: 600; letter-spacing: .1em;
  text-transform: uppercase; color: #9A9087; margin-bottom: 12px;
}
.persona-pills { display: flex; gap: 8px; flex-wrap: wrap; }
.pill {
  padding: 8px 14px; border-radius: 20px;
  font-size: 13px; font-weight: 500;
  border: 1.5px solid #E8E2DC;
  background: transparent; color: #7A6E66;
  cursor: pointer; transition: all .15s;
}
.pill.active { background: #C4785A; color: #fff; border-color: #C4785A; }

/* ── Activity feed ── */
.feed-item {
  display: flex; align-items: center;
  justify-content: space-between;
  padding: 10px 0; border-bottom: 1px solid #F0EDE9;
}
.feed-item:last-child { border-bottom: none; }
.feed-left { display: flex; align-items: center; gap: 10px; }
.feed-icon {
  width: 26px; height: 26px; border-radius: 8px;
  background: #F0EAE5; display: flex; align-items: center;
  justify-content: center; font-size: 13px; flex-shrink: 0;
}
.feed-name  { font-size: 14px; font-weight: 500; }
.feed-right { text-align: right; }
.feed-dur   { font-size: 13px; color: #9A9087; }
.feed-time  { font-size: 11px; color: #C0B8B0; margin-top: 2px; }

/* ── Dead zone editor ── */
.dz-card { padding: 0; }
.dz-card > summary {
  padding: 16px 20px; font-size: 13px; font-weight: 600;
  color: #9A9087; cursor: pointer; list-style: none;
  display: flex; align-items: center; justify-content: space-between;
}
.dz-card > summary::-webkit-details-marker { display: none; }
.dz-card > summary::after {
  content: '›'; font-size: 20px; color: #C0B8B0; transition: transform .2s;
}
.dz-card[open] > summary::after { transform: rotate(90deg); }
.dz-inner { padding: 0 20px 20px; }
.dz-timeline-wrap {
  border-radius: 8px; background: #F7F5F3;
  margin-bottom: 16px; overflow: hidden;
}
.dz-timeline { display: block; width: 100%; }
.dz-form     { display: flex; flex-direction: column; gap: 12px; }
.dz-row      { display: flex; gap: 10px; }
.dz-field    { flex: 1; }
.dz-field-label { font-size: 12px; font-weight: 500; color: #9A9087; margin-bottom: 4px; }
.dz-input {
  width: 100%; padding: 10px 12px;
  border: 1.5px solid #E8E2DC; border-radius: 10px;
  font-size: 14px; color: #2C2C2A; background: #fff; outline: none;
}
.dz-input:focus { border-color: #C4785A; }
.dz-toggle {
  display: flex; align-items: center; gap: 8px;
  font-size: 13px; color: #7A6E66; cursor: pointer; user-select: none;
}
.dz-toggle input[type=checkbox] {
  width: 16px; height: 16px; accent-color: #C4785A; cursor: pointer; flex-shrink: 0;
}
.day-pills  { display: flex; gap: 6px; }
.day-pill {
  width: 34px; height: 34px; border-radius: 50%;
  font-size: 12px; font-weight: 600;
  border: 1.5px solid #E8E2DC; background: transparent; color: #9A9087;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all .15s;
}
.day-pill.active { background: #C4785A; color: #fff; border-color: #C4785A; }
.dz-actions { display: flex; gap: 8px; }
.dz-btn-primary {
  flex: 1; padding: 12px; border: none; border-radius: 10px;
  background: #C4785A; color: #fff; font-size: 14px; font-weight: 600;
  cursor: pointer; transition: opacity .15s;
}
.dz-btn-primary:active { opacity: .85; }
.dz-btn-secondary {
  flex: 1; padding: 12px; border: 1.5px solid #E8E2DC; border-radius: 10px;
  background: transparent; color: #7A6E66; font-size: 14px; font-weight: 600;
  cursor: pointer; transition: border-color .15s;
}
.dz-btn-secondary:active { border-color: #C4785A; }
.dz-btn-danger {
  flex: 1; padding: 12px; border: 1.5px solid #E2C4BC; border-radius: 10px;
  background: transparent; color: #C4785A; font-size: 14px; font-weight: 600; cursor: pointer;
}
</style>
</head>
<body>

<header><span class="wordmark">Family Hub</span></header>

<div id="offline-badge" class="offline-badge" hidden>Offline</div>

<!-- Status card -->
<div class="card">
  <div class="status-label">
    <span class="dot dim" id="status-dot"></span>Live Status
  </div>
  <div class="status-row">
    <div class="status-activity" id="status-activity">—</div>
    <span class="status-badge" id="status-persona"></span>
  </div>
  <div class="status-meta" id="status-next"></div>
  <div class="status-dz" id="status-dz" hidden></div>
</div>

<!-- Controls card -->
<div class="card">
  <button class="btn-primary" id="btn-primary">—</button>
  <button class="btn-secondary" id="btn-secondary">—</button>
</div>

<!-- Persona card -->
<div class="card">
  <div class="section-label">Persona</div>
  <div class="persona-pills">
    <button class="pill" data-api="focused_writer">Focused</button>
    <button class="pill" data-api="distracted_multitasker">Multitasker</button>
    <button class="pill" data-api="steady">Steady</button>
    <button class="pill" data-api="power_user">Power User</button>
  </div>
</div>

<!-- Activity feed -->
<div class="card">
  <div class="section-label">Recent Activity</div>
  <div id="feed-list"></div>
</div>

<!-- Dead zone editor -->
<details class="card dz-card" id="dz-details">
  <summary id="dz-summary">No dead zones set.</summary>
  <div class="dz-inner">
    <div class="dz-timeline-wrap">
      <svg id="dz-timeline" class="dz-timeline" viewBox="0 0 600 52" height="52"></svg>
    </div>
    <div class="dz-form">
      <div class="dz-row">
        <div class="dz-field">
          <div class="dz-field-label">Start</div>
          <input type="time" class="dz-input" id="dz-start">
        </div>
        <div class="dz-field">
          <div class="dz-field-label">End</div>
          <input type="time" class="dz-input" id="dz-end">
        </div>
      </div>
      <label class="dz-toggle">
        <input type="checkbox" id="dz-repeat" onchange="toggleRepeat()">
        Repeat on selected days
      </label>
      <div id="dz-days" hidden>
        <div class="day-pills">
          <button class="day-pill active" data-day="mon">M</button>
          <button class="day-pill active" data-day="tue">T</button>
          <button class="day-pill active" data-day="wed">W</button>
          <button class="day-pill active" data-day="thu">T</button>
          <button class="day-pill active" data-day="fri">F</button>
        </div>
      </div>
      <div class="dz-actions" id="dz-actions">
        <button class="dz-btn-primary" onclick="saveDeadZone()">Add</button>
      </div>
    </div>
  </div>
</details>

<script>
const ACTIVITY_LABELS = {typing:'Typing', mouse:'Mouse', idle:'Idle', dead_stop:'Meeting'};
const ACTIVITY_ICONS  = {typing:'⌨', mouse:'🖱', idle:'⏸', dead_stop:'📅'};
const TODAY = ['sun','mon','tue','wed','thu','fri','sat'][new Date().getDay()];

// Timeline: 8am–6pm = 600 min, viewBox width 600 → 1px per minute
const TL_START = 8 * 60;   // 480 min since midnight
const TL_RANGE = 10 * 60;  // 600 min span
const TL_W = 600;

let _lastDeadZones = [];
let _selectedZoneIdx = null;

// ── Polling ───────────────────────────────────────────────────────────────────

async function fetchStatus() {
  try {
    const r = await fetch('/api/status');
    if (!r.ok) throw new Error();
    renderStatus(await r.json());
    document.getElementById('offline-badge').hidden = true;
  } catch {
    document.getElementById('offline-badge').hidden = false;
  }
}

async function fetchLog() {
  try {
    const r = await fetch('/api/activity_log');
    if (!r.ok) throw new Error();
    renderLog(await r.json());
  } catch {}
}

setInterval(fetchStatus, 3000);
setInterval(fetchLog, 10000);

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') {
    fetchStatus();
    fetchLog();
  }
});

fetchStatus();
fetchLog();

// ── Status rendering ──────────────────────────────────────────────────────────

function renderStatus(data) {
  const state = data.engine_state || 'stopped';
  const dot = document.getElementById('status-dot');
  dot.className = state === 'running' ? 'dot pulse' : 'dot dim';

  document.getElementById('status-activity').textContent =
    ACTIVITY_LABELS[data.activity] ?? data.activity ?? '—';
  document.getElementById('status-persona').textContent =
    (data.persona || '').replace(/_/g, ' ');

  const nextEl = document.getElementById('status-next');
  nextEl.textContent = data.next_change_at
    ? 'Next change ' + data.next_change_at.slice(0, 5)
    : '';

  const dzEl = document.getElementById('status-dz');
  if (data.time_until_dead_zone_s != null) {
    const s = Math.round(data.time_until_dead_zone_s);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    dzEl.textContent = h > 0 ? `Dead zone in ${h}h ${m}m` : `Dead zone in ${m}m`;
    dzEl.hidden = false;
  } else {
    dzEl.hidden = true;
  }

  renderControls(state);
  renderPersonaPills(data.persona);

  if (Array.isArray(data.dead_zones)) {
    _lastDeadZones = data.dead_zones;
    renderDeadZoneSection(_lastDeadZones);
  }
}

// ── Controls ──────────────────────────────────────────────────────────────────

function renderControls(state) {
  const primary   = document.getElementById('btn-primary');
  const secondary = document.getElementById('btn-secondary');

  secondary.disabled = false;

  if (state === 'running') {
    primary.textContent   = 'Stop';
    primary.onclick       = () => doAction('/api/stop');
    secondary.textContent = 'Pause';
    secondary.className   = 'btn-secondary';
    secondary.onclick     = () => doAction('/api/pause');
  } else if (state === 'paused') {
    primary.textContent   = 'Resume';
    primary.onclick       = () => doAction('/api/pause');
    secondary.textContent = 'Stop';
    secondary.className   = 'btn-secondary';
    secondary.onclick     = () => doAction('/api/stop');
  } else {
    primary.textContent   = 'Start';
    primary.onclick       = () => doAction('/api/start');
    secondary.textContent = 'Pause';
    secondary.className   = 'btn-ghost';
    secondary.onclick     = null;
    secondary.disabled    = true;
  }
}

async function doAction(path) {
  await fetch(path, { method: 'POST' });
  fetchStatus();
}

// ── Persona pills ─────────────────────────────────────────────────────────────

function renderPersonaPills(activePersona) {
  document.querySelectorAll('.pill').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.api === activePersona);
    btn.onclick = () => selectPersona(btn.dataset.api);
  });
}

async function selectPersona(apiName) {
  await fetch('/api/persona', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ persona: apiName }),
  });
  fetchStatus();
}

// ── Activity feed ─────────────────────────────────────────────────────────────

function fmtDur(s) {
  s = Math.round(s);
  return s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${s}s`;
}

function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function renderLog(entries) {
  const el = document.getElementById('feed-list');
  if (!entries.length) { el.innerHTML = ''; return; }
  el.innerHTML = entries.map(e => `
    <div class="feed-item">
      <div class="feed-left">
        <div class="feed-icon">${ACTIVITY_ICONS[e.activity] ?? '•'}</div>
        <div class="feed-name">${ACTIVITY_LABELS[e.activity] ?? e.activity}</div>
      </div>
      <div class="feed-right">
        <div class="feed-dur">${fmtDur(e.duration_s)}</div>
        <div class="feed-time">${fmtTime(e.ts)}</div>
      </div>
    </div>
  `).join('');
}

// ── Dead zone editor ──────────────────────────────────────────────────────────

function _timeToMin(hhmm) {
  const [h, m] = hhmm.split(':').map(Number);
  return h * 60 + m;
}

function renderDeadZoneSection(zones) {
  const todayZones = zones.filter(z => z.days.includes(TODAY));
  const summary = document.getElementById('dz-summary');
  summary.textContent = todayZones.length
    ? `${todayZones.length} dead zone${todayZones.length !== 1 ? 's' : ''} today`
    : 'No dead zones set.';
  renderTimeline(zones);
}

function renderTimeline(zones) {
  const svg = document.getElementById('dz-timeline');
  const todayZones = zones
    .map((z, i) => ({ ...z, idx: i }))
    .filter(z => z.days.includes(TODAY));

  const rects = todayZones.map(z => {
    const x = Math.max(0, (_timeToMin(z.start) - TL_START) / TL_RANGE * TL_W);
    const w = Math.min(TL_W - x, (_timeToMin(z.end) - _timeToMin(z.start)) / TL_RANGE * TL_W);
    const sel = z.idx === _selectedZoneIdx;
    return `<rect x="${x.toFixed(1)}" y="4" width="${Math.max(2, w).toFixed(1)}" height="30"
      rx="4" fill="${sel ? '#A85E44' : '#C4785A'}" opacity="${sel ? '1' : '0.75'}"
      data-idx="${z.idx}" style="cursor:pointer"/>`;
  }).join('');

  const ticks = [0, 120, 240, 360, 480, 600].map(offset => {
    const x = (offset / TL_RANGE * TL_W).toFixed(1);
    const h = 8 + offset / 60;
    const label = h < 12 ? `${h}am` : h === 12 ? '12pm' : `${h - 12}pm`;
    return `<line x1="${x}" y1="34" x2="${x}" y2="40" stroke="#E8E2DC" stroke-width="1"/>
      <text x="${x}" y="50" text-anchor="middle" font-size="8" fill="#C0B8B0"
            font-family="-apple-system,sans-serif">${label}</text>`;
  }).join('');

  svg.innerHTML = ticks + rects;

  svg.querySelectorAll('rect[data-idx]').forEach(rect => {
    rect.addEventListener('click', e => {
      e.stopPropagation();
      selectZone(parseInt(rect.dataset.idx));
    });
  });
}

function selectZone(idx) {
  _selectedZoneIdx = idx;
  const z = _lastDeadZones[idx];
  document.getElementById('dz-start').value = z.start;
  document.getElementById('dz-end').value   = z.end;
  const repeat = z.days.length > 1;
  document.getElementById('dz-repeat').checked   = repeat;
  document.getElementById('dz-days').hidden = !repeat;
  if (repeat) {
    document.querySelectorAll('.day-pill').forEach(p => {
      p.classList.toggle('active', z.days.includes(p.dataset.day));
    });
  }
  document.getElementById('dz-actions').innerHTML = `
    <button class="dz-btn-primary"   onclick="saveDeadZone()">Update</button>
    <button class="dz-btn-danger"    onclick="deleteDeadZone()">Delete</button>
    <button class="dz-btn-secondary" onclick="cancelDeadZone()">Cancel</button>
  `;
  renderTimeline(_lastDeadZones);
}

function cancelDeadZone() {
  _selectedZoneIdx = null;
  document.getElementById('dz-start').value       = '';
  document.getElementById('dz-end').value         = '';
  document.getElementById('dz-repeat').checked    = false;
  document.getElementById('dz-days').hidden       = true;
  document.querySelectorAll('.day-pill').forEach(p => p.classList.add('active'));
  document.getElementById('dz-actions').innerHTML =
    `<button class="dz-btn-primary" onclick="saveDeadZone()">Add</button>`;
  renderTimeline(_lastDeadZones);
}

function toggleRepeat() {
  document.getElementById('dz-days').hidden =
    !document.getElementById('dz-repeat').checked;
}

document.querySelectorAll('.day-pill').forEach(p => {
  p.addEventListener('click', () => p.classList.toggle('active'));
});

function _formData() {
  const start  = document.getElementById('dz-start').value;
  const end    = document.getElementById('dz-end').value;
  const repeat = document.getElementById('dz-repeat').checked;
  const days   = repeat
    ? [...document.querySelectorAll('.day-pill.active')].map(p => p.dataset.day)
    : [TODAY];
  return { start, end, days: days.length ? days : [TODAY] };
}

async function saveDeadZone() {
  const body   = _formData();
  const method = _selectedZoneIdx !== null ? 'PUT'  : 'POST';
  const url    = _selectedZoneIdx !== null
    ? `/api/dead_zones/${_selectedZoneIdx}`
    : '/api/dead_zones';
  const r = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (r.ok) {
    _lastDeadZones = (await r.json()).dead_zones;
    cancelDeadZone();
    renderDeadZoneSection(_lastDeadZones);
  }
}

async function deleteDeadZone() {
  if (_selectedZoneIdx === null) return;
  const r = await fetch(`/api/dead_zones/${_selectedZoneIdx}`, { method: 'DELETE' });
  if (r.ok) {
    _lastDeadZones = (await r.json()).dead_zones;
    cancelDeadZone();
    renderDeadZoneSection(_lastDeadZones);
  }
}

// Click on empty timeline area → deselect
document.getElementById('dz-timeline').addEventListener('click', e => {
  if (!e.target.hasAttribute('data-idx')) cancelDeadZone();
});
</script>
</body>
</html>
```

- [ ] **Step 3: Smoke test — verify the app renders without errors**

```bash
python3 -c "
from pwa.app import create_app
app = create_app(config_path='config.json')
with app.test_client() as c:
    r = c.get('/')
    assert r.status_code == 200, f'Got {r.status_code}'
    assert b'Family Hub' in r.data
    print('OK — index.html renders')
"
```

Expected output: `OK — index.html renders`

- [ ] **Step 4: Run full test suite**

```bash
python3 -m pytest tests/ -v
```

Expected: All tests pass (existing 115 + 16 new PWA tests = 131).

- [ ] **Step 5: Commit**

```bash
git add pwa/templates/index.html
git commit -m "feat: add Family Hub PWA frontend (status, controls, persona, feed, dead zones)"
```

---

## Task 9: Update README

**Files:**
- Modify: `docs/README.md`

- [ ] **Step 1: Add `pwa/` to the project structure block**

In the `Project Structure` code block, add after `presence.service`:

```
├── pwa/
│   ├── __init__.py
│   ├── app.py              # Flask app factory + all routes
│   ├── templates/
│   │   └── index.html      # Single-page PWA
│   └── static/
│       ├── manifest.json   # PWA manifest
│       └── icon.svg        # House outline icon
├── run_pwa.py              # PWA entrypoint (0.0.0.0:5000)
└── presence-pwa.service    # systemd unit for PWA process
```

- [ ] **Step 2: Add PWA section after the "HTTP Control API" section**

```markdown
## Family Hub PWA

Mobile-first control interface served at `http://<device-ip>:5000`. Install to home screen via the browser's "Add to Home Screen" prompt — it will appear as **Family Hub** with a neutral house icon.

**Start manually:**
```bash
python3 run_pwa.py
```

**Deploy with systemd:**
```bash
sudo cp presence-pwa.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable presence-pwa
sudo systemctl start presence-pwa
```

**Environment variables:**

| Variable | Default | Purpose |
|---|---|---|
| `PRESENCE_CONFIG` | `config.json` | Path to shared config file |
| `PRESENCE_COMMAND_URL` | `http://127.0.0.1:7777` | Command server base URL |

> **Security note:** No authentication is required. Access should be restricted to a trusted local network via router/firewall configuration. Do not expose port 5000 to the internet.
```

- [ ] **Step 3: Update the test count**

Change `115 tests` → `131 tests` in the Running Tests section.

- [ ] **Step 4: Run full test suite to confirm count**

```bash
python3 -m pytest tests/ -v --tb=short 2>&1 | tail -5
```

Expected: `131 passed` (or similar — exact count may vary if smoke tests are collected).

- [ ] **Step 5: Commit**

```bash
git add docs/README.md
git commit -m "docs: add PWA section and update project structure in README"
```

---

## Self-Review

Spec requirements checked against tasks:

| Requirement | Task |
|---|---|
| Flask separate process, port 5000 | Task 3 (`run_pwa.py`) |
| `pwa/` package structure | Task 3 |
| `GET /api/ping` | Task 3 |
| Proxy `/status`, `/start`, `/stop`, `/pause` | Task 4 |
| `engine_state` in status response | Task 2 |
| `POST /api/persona` validates + writes config | Task 5 |
| `GET /api/activity_log` reads SQLite, limit 8 | Task 5 |
| SQLite unavailable → `[]` (graceful) | Task 5 |
| Atomic config writes (write-then-replace) | Task 3 (`_write_config`) |
| `POST /api/dead_zones` append | Task 6 |
| `PUT /api/dead_zones/<idx>` update | Task 6 |
| `DELETE /api/dead_zones/<idx>` delete | Task 6 |
| 404 on out-of-range index | Task 6 |
| 503 `engine offline` on `URLError` | Task 4 |
| `persona rename slow_and_steady → steady` | Task 1 |
| PWA manifest + house icon | Task 7 |
| systemd unit | Task 7 |
| Status card with pulsing dot (running only) | Task 8 |
| Three-state controls (running/paused/stopped) | Task 8 |
| Persona pills (Focused, Multitasker, Steady, Power User) | Task 8 |
| Activity feed, icons, duration format, Meeting label | Task 8 |
| Dead zone editor (`<details>`, collapsed) | Task 8 |
| SVG timeline 8am–6pm, tap to select zone | Task 8 |
| Form: time pickers, repeat toggle, day pills | Task 8 |
| Add/Update/Delete/Cancel actions | Task 8 |
| Re-render timeline + summary on save | Task 8 |
| Poll status every 3s, log every 10s | Task 8 |
| `visibilitychange` re-fetches immediately | Task 8 |
| Offline badge on fetch error | Task 8 |
| README PWA section + trusted network warning | Task 9 |
| `tests/test_pwa.py` (16 tests) | Tasks 3–6 |
| `tests/test_command_server.py` engine_state tests | Task 2 |
