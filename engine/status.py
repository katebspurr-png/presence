import copy
import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EngineControl:
    running: threading.Event = field(default_factory=threading.Event)
    paused: threading.Event = field(default_factory=threading.Event)
    stopped: threading.Event = field(default_factory=threading.Event)
    reload: threading.Event = field(default_factory=threading.Event)


class StatusStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status: Optional[dict] = None

    def update(self, status: dict) -> None:
        with self._lock:
            self._status = copy.deepcopy(status)

    def snapshot(self) -> Optional[dict]:
        with self._lock:
            return copy.deepcopy(self._status) if self._status is not None else None


class ConfigStore:
    def __init__(self, config: dict) -> None:
        self._lock = threading.Lock()
        self._config = copy.deepcopy(config)

    def get(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._config)

    def set(self, config: dict) -> None:
        with self._lock:
            self._config = copy.deepcopy(config)
