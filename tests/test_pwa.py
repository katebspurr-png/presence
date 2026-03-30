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
