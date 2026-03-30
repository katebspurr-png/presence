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
