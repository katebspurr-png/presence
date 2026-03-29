import json
import time
import urllib.request
from urllib.error import HTTPError

import pytest

from engine.command_server import CommandServer
from engine.status import EngineControl, StatusStore

TEST_PORT = 17777  # high port to avoid conflicts


@pytest.fixture
def server():
    ctrl = EngineControl()
    ctrl.running.set()
    store = StatusStore()
    store.update({"activity": "typing", "persona": "focused_writer",
                  "next_change_at": "14:00:00", "time_until_dead_zone_s": 3600})
    srv = CommandServer(host="127.0.0.1", port=TEST_PORT, control=ctrl, status_store=store)
    srv.start()
    time.sleep(0.1)  # let server bind
    yield srv, ctrl, store
    srv.shutdown()


def _get(path: str) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{TEST_PORT}{path}") as r:
        return json.loads(r.read())


def _post(path: str) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{TEST_PORT}{path}",
        data=b"",
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def test_get_status_returns_snapshot(server):
    srv, ctrl, store = server
    data = _get("/status")
    assert data["activity"] == "typing"
    assert data["persona"] == "focused_writer"


def test_post_stop_sets_stopped_event(server):
    srv, ctrl, store = server
    data = _post("/stop")
    assert data["status"] == "stopped"
    assert ctrl.stopped.is_set()
    assert not ctrl.running.is_set()


def test_post_start_sets_running_event(server):
    srv, ctrl, store = server
    ctrl.stopped.set()
    ctrl.running.clear()
    data = _post("/start")
    assert data["status"] == "started"
    assert ctrl.running.is_set()
    assert not ctrl.stopped.is_set()


def test_post_pause_toggles_paused(server):
    srv, ctrl, store = server
    assert not ctrl.paused.is_set()
    data = _post("/pause")
    assert data["status"] == "paused"
    assert ctrl.paused.is_set()
    data = _post("/pause")
    assert data["status"] == "resumed"
    assert not ctrl.paused.is_set()


def test_get_unknown_path_returns_404(server):
    srv, ctrl, store = server
    with pytest.raises(HTTPError) as exc_info:
        _get("/unknown")
    assert exc_info.value.code == 404


def test_server_is_daemon_thread(server):
    srv, ctrl, store = server
    assert srv.daemon is True
