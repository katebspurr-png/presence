import logging

from engine.activities.base import ActivityBase, ActivityResult

logger = logging.getLogger(__name__)


class MouseActivity(ActivityBase):
    """Mouse movement activity using bezier curves and USB HID reports."""

    def __init__(self, config: dict, hid_path: str | None = "/dev/hidg1") -> None:
        self.config = config
        self.hid_path = hid_path

    def run(self, duration_s: float, control) -> ActivityResult:
        from engine.hid.mouse import run_movement_session

        screen = self.config.get("screen", {})
        screen_w = int(screen.get("width", 1920))
        screen_h = int(screen.get("height", 1080))

        run_movement_session(
            duration_s=duration_s,
            screen_w=screen_w,
            screen_h=screen_h,
            control=control,
            hid_path=self.hid_path,
        )
        return ActivityResult(activity="mouse", duration_s=duration_s)
