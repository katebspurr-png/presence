import json
import time

from engine.config_watcher import ConfigWatcher
from engine.status import ConfigStore, EngineControl


def _write_config(path: str, config: dict) -> None:
    with open(path, "w") as f:
        json.dump(config, f)


def test_config_watcher_fires_reload_on_change(tmp_path):
    config_file = str(tmp_path / "config.json")
    initial = {"persona": "focused_writer"}
    updated = {"persona": "power_user"}
    _write_config(config_file, initial)

    ctrl = EngineControl()
    store = ConfigStore(initial)
    watcher = ConfigWatcher(config_path=config_file, config_store=store, control=ctrl)
    watcher.start()

    time.sleep(0.1)  # let watcher read initial mtime
    _write_config(config_file, updated)
    time.sleep(3)  # watcher polls every 2s

    ctrl.stopped.set()
    watcher.join(timeout=2)

    assert ctrl.reload.is_set()
    assert store.get()["persona"] == "power_user"


def test_config_watcher_bad_json_keeps_old_config(tmp_path):
    config_file = str(tmp_path / "config.json")
    initial = {"persona": "focused_writer"}
    _write_config(config_file, initial)

    ctrl = EngineControl()
    store = ConfigStore(initial)
    watcher = ConfigWatcher(config_path=config_file, config_store=store, control=ctrl)
    watcher.start()

    time.sleep(0.1)
    with open(config_file, "w") as f:
        f.write("{not valid json}")
    time.sleep(3)

    ctrl.stopped.set()
    watcher.join(timeout=2)

    assert store.get()["persona"] == "focused_writer"
    assert not ctrl.reload.is_set()


def test_config_watcher_is_daemon_thread(tmp_path):
    config_file = str(tmp_path / "config.json")
    _write_config(config_file, {"persona": "focused_writer"})
    ctrl = EngineControl()
    store = ConfigStore({})
    watcher = ConfigWatcher(config_path=config_file, config_store=store, control=ctrl)
    assert watcher.daemon is True


def test_config_watcher_bad_json_does_not_retry_indefinitely(tmp_path):
    """After a bad JSON write, watcher should log once per file change, not per poll."""
    config_file = str(tmp_path / "config.json")
    _write_config(config_file, {"persona": "focused_writer"})

    ctrl = EngineControl()
    store = ConfigStore({"persona": "focused_writer"})
    watcher = ConfigWatcher(config_path=config_file, config_store=store, control=ctrl)
    watcher.start()

    time.sleep(0.1)
    with open(config_file, "w") as f:
        f.write("{bad json}")
    time.sleep(3)  # let two polls happen

    # Write a valid config after the bad one
    _write_config(config_file, {"persona": "power_user"})
    time.sleep(3)

    ctrl.stopped.set()
    watcher.join(timeout=2)

    # Should have recovered and loaded the valid config
    assert store.get()["persona"] == "power_user"
    assert ctrl.reload.is_set()
