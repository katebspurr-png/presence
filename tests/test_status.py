import threading
from engine.status import ConfigStore, EngineControl, StatusStore


def test_status_store_update_and_snapshot():
    store = StatusStore()
    assert store.snapshot() is None
    store.update({"activity": "typing", "persona": "focused_writer"})
    snap = store.snapshot()
    assert snap["activity"] == "typing"
    assert snap["persona"] == "focused_writer"


def test_status_store_snapshot_is_copy():
    store = StatusStore()
    store.update({"activity": "idle"})
    snap = store.snapshot()
    snap["activity"] = "mutated"
    assert store.snapshot()["activity"] == "idle"


def test_config_store_get_and_set():
    store = ConfigStore({"persona": "focused_writer"})
    assert store.get()["persona"] == "focused_writer"
    store.set({"persona": "power_user"})
    assert store.get()["persona"] == "power_user"


def test_config_store_get_is_copy():
    store = ConfigStore({"persona": "focused_writer"})
    cfg = store.get()
    cfg["persona"] = "mutated"
    assert store.get()["persona"] == "focused_writer"


def test_engine_control_events_default_unset():
    ctrl = EngineControl()
    assert not ctrl.running.is_set()
    assert not ctrl.paused.is_set()
    assert not ctrl.stopped.is_set()
    assert not ctrl.reload.is_set()


def test_engine_control_set_and_clear():
    ctrl = EngineControl()
    ctrl.running.set()
    assert ctrl.running.is_set()
    ctrl.running.clear()
    assert not ctrl.running.is_set()


def test_status_store_thread_safety():
    store = StatusStore()
    errors = []

    def writer():
        for i in range(100):
            store.update({"activity": f"typing_{i}"})

    def reader():
        for _ in range(100):
            try:
                store.snapshot()
            except Exception as e:
                errors.append(e)

    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


def test_config_store_deep_copy_isolates_nested_structures():
    nested_config = {"dead_zones": [{"start": "09:00", "days": ["mon"]}]}
    store = ConfigStore(nested_config)
    cfg = store.get()
    cfg["dead_zones"][0]["start"] = "MUTATED"
    assert store.get()["dead_zones"][0]["start"] == "09:00"
