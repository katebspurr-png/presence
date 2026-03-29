import logging

from engine.activities.base import ActivityBase, ActivityResult, interruptible_sleep

logger = logging.getLogger(__name__)


class MouseActivity(ActivityBase):
    """Stub mouse activity.

    Mouse movement algorithm (bezier curves, HID report encoding) is out of scope
    for this phase. A real implementation would write 6-byte mouse HID reports to
    self.hid_path at intervals over duration_s.
    """

    def __init__(self, hid_path: str = "/dev/hidg1") -> None:
        self.hid_path = hid_path

    def run(self, duration_s: float, control) -> ActivityResult:
        # Stub: no HID writes until mouse movement algorithm is implemented.
        interruptible_sleep(duration_s, control)
        return ActivityResult(activity="mouse", duration_s=duration_s)
