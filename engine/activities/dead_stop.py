from engine.activities.base import ActivityBase, ActivityResult, interruptible_sleep


class DeadStopActivity(ActivityBase):
    """Complete silence for duration_s seconds (meeting block, no HID output)."""

    def run(self, duration_s: float, control) -> ActivityResult:
        interruptible_sleep(duration_s, control)
        return ActivityResult(activity="dead_stop", duration_s=duration_s)
