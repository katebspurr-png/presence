import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ActivityResult:
    activity: str
    duration_s: float
    metadata: dict = field(default_factory=dict)


class ActivityBase(ABC):
    @abstractmethod
    def run(self, duration_s: float, control) -> ActivityResult:
        """Execute this activity for approximately duration_s seconds.

        Must honor control.stopped and control.paused — check at least every
        1 second and return early if either is set.
        """
        ...


def interruptible_sleep(duration: float, control) -> None:
    """Sleep for up to duration seconds, waking within ~1s if stop or pause is set."""
    end = time.monotonic() + duration
    while time.monotonic() < end:
        if control.stopped.is_set() or control.paused.is_set():
            break
        time.sleep(1)
