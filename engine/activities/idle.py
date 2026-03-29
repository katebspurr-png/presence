from engine.activities.base import ActivityBase, ActivityResult, interruptible_sleep


class IdleActivity(ActivityBase):
    """Do nothing for duration_s seconds (micro-pause, no HID output)."""

    def run(self, duration_s: float, control) -> ActivityResult:
        interruptible_sleep(duration_s, control)
        return ActivityResult(activity="idle", duration_s=duration_s)
