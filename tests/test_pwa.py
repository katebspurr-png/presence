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


# ---------------------------------------------------------------------------
# Bluetooth
# ---------------------------------------------------------------------------

def test_bluetooth_get_default(client):
    c, _, _ = client
    resp = c.get("/api/bluetooth")
    assert resp.status_code == 200
    assert json.loads(resp.data)["hid_mode"] == "usb"


def test_bluetooth_get_explicit(client):
    c, config_path, _ = client
    cfg = json.loads(config_path.read_text())
    cfg["hid_mode"] = "bluetooth"
    config_path.write_text(json.dumps(cfg))
    resp = c.get("/api/bluetooth")
    assert json.loads(resp.data)["hid_mode"] == "bluetooth"


def test_bluetooth_set_valid(client):
    c, config_path, _ = client
    with mock.patch("urllib.request.urlopen"):
        resp = c.post("/api/bluetooth",
                      data=json.dumps({"hid_mode": "bluetooth"}),
                      content_type="application/json")
    assert resp.status_code == 200
    assert json.loads(resp.data)["hid_mode"] == "bluetooth"
    assert json.loads(config_path.read_text())["hid_mode"] == "bluetooth"


def test_bluetooth_set_invalid_mode(client):
    c, _, _ = client
    resp = c.post("/api/bluetooth",
                  data=json.dumps({"hid_mode": "wifi"}),
                  content_type="application/json")
    assert resp.status_code == 400


def test_bluetooth_discover_no_bluetoothctl(client):
    c, _, _ = client
    with mock.patch("subprocess.run", side_effect=FileNotFoundError):
        resp = c.post("/api/bluetooth/discover")
    assert resp.status_code == 500
    assert "bluetoothctl not found" in json.loads(resp.data)["error"]


def test_bluetooth_discover_success(client):
    c, _, _ = client
    mock_result = mock.MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Changing discoverable on succeeded"
    with mock.patch("subprocess.run", return_value=mock_result):
        resp = c.post("/api/bluetooth/discover")
    assert resp.status_code == 200
    assert json.loads(resp.data)["ok"] is True


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def test_settings_get_default(client):
    c, _, _ = client
    resp = c.get("/api/settings")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["screen"]["width"] == 1920
    assert data["screen"]["height"] == 1080


def test_settings_set_screen(client):
    c, config_path, _ = client
    with mock.patch("urllib.request.urlopen"):
        resp = c.post("/api/settings",
                      data=json.dumps({"screen": {"width": 2560, "height": 1440}}),
                      content_type="application/json")
    assert resp.status_code == 200
    saved = json.loads(config_path.read_text())
    assert saved["screen"]["width"] == 2560
    assert saved["screen"]["height"] == 1440


def test_settings_set_invalid_dimensions(client):
    c, _, _ = client
    resp = c.post("/api/settings",
                  data=json.dumps({"screen": {"width": 50, "height": 1080}}),
                  content_type="application/json")
    assert resp.status_code == 400
