import json
import logging
import os
import threading
import time

logger = logging.getLogger(__name__)


class ConfigWatcher(threading.Thread):
    """Polls config.json mtime every 2 seconds. On change, parses and swaps ConfigStore.

    Fires control.reload so the engine loop picks up the new config between activities.
    On parse failure, keeps the existing config and does not fire reload.
    """

    def __init__(self, config_path: str, config_store, control) -> None:
        super().__init__(daemon=True, name="config-watcher")
        self.config_path = config_path
        self.config_store = config_store
        self.control = control
        self._last_mtime: float = 0.0

    def run(self) -> None:
        while not self.control.stopped.is_set():
            try:
                mtime = os.path.getmtime(self.config_path)
                if self._last_mtime != 0.0 and mtime != self._last_mtime:
                    with open(self.config_path) as f:
                        new_config = json.load(f)
                    self.config_store.set(new_config)
                    self.control.reload.set()
                    logger.info(f"config_reloaded path={self.config_path}")
                self._last_mtime = mtime
            except json.JSONDecodeError as e:
                logger.error(f"config_parse_error={e!r} keeping_existing_config=True")
            except OSError as e:
                logger.error(f"config_watch_os_error={e!r}")
            time.sleep(2)
