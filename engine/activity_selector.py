import random
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

from engine.distributions import exponential_duration, gaussian_duration

_ACTIVITY_TYPES = ["typing", "mouse", "idle", "dead_stop"]


class ActivitySelector:
    def __init__(self, config: dict) -> None:
        self.config = config

    def update_config(self, config: dict) -> None:
        self.config = config

    @property
    def current_persona_name(self) -> str:
        return self.config["persona"]

    def select(self) -> Tuple[str, float]:
        """Return (activity_type, duration_s) for the next activity."""
        now = datetime.now()

        dead_zone_remaining = self._dead_zone_remaining_s(now)
        if dead_zone_remaining is not None:
            return ("dead_stop", float(dead_zone_remaining))

        hour = now.hour
        weights = [
            self.config["time_profiles"]["typing"][hour],
            self.config["time_profiles"]["mouse"][hour],
            self.config["time_profiles"]["idle"][hour],
            self.config["time_profiles"]["dead_stop"][hour],
        ]

        activity_type = random.choices(_ACTIVITY_TYPES, weights=weights, k=1)[0]
        _, duration_s = self._sample_duration(activity_type)
        return (activity_type, duration_s)

    def _sample_duration(self, activity_type: str) -> Tuple[str, float]:
        """Return (activity_type, duration_s) using per-persona distribution."""
        persona_name = self.current_persona_name
        p = self.config["personas"][persona_name]

        if activity_type == "typing":
            duration = gaussian_duration(float(p["typing_mean_s"]), float(p["typing_stddev_s"]))
        elif activity_type == "mouse":
            duration = exponential_duration(float(p["mouse_lambda"]))
        elif activity_type == "idle":
            duration = exponential_duration(float(p["idle_lambda"]))
        else:
            # dead_stop outside a dead zone: default 30-minute block
            duration = gaussian_duration(1800.0, 300.0)

        return (activity_type, duration)

    def _dead_zone_remaining_s(self, now: datetime) -> Optional[int]:
        """Return seconds remaining in current dead zone, or None if not in one.

        Dead zone times use 24h "HH:MM" strings — zero-padded (e.g. "09:00").
        String comparison is valid for zero-padded HH:MM format.
        """
        day_name = now.strftime("%a").lower()
        current_time_str = now.strftime("%H:%M")

        for zone in self.config.get("dead_zones", []):
            if day_name not in zone.get("days", []):
                continue
            if zone["start"] <= current_time_str <= zone["end"]:
                zone_end = datetime.combine(
                    now.date(),
                    datetime.strptime(zone["end"], "%H:%M").time(),
                )
                remaining = int((zone_end - now).total_seconds())
                return max(60, remaining)

        return None

    def time_until_dead_zone_s(self) -> Optional[int]:
        """Return seconds until the next dead zone starts (scanning 48h ahead), or None."""
        now = datetime.now()
        earliest: Optional[int] = None

        for offset_days in range(3):
            check_date = now.date() + timedelta(days=offset_days)
            day_name = check_date.strftime("%a").lower()

            for zone in self.config.get("dead_zones", []):
                if day_name not in zone.get("days", []):
                    continue
                zone_start = datetime.combine(
                    check_date,
                    datetime.strptime(zone["start"], "%H:%M").time(),
                )
                if zone_start > now:
                    delta = int((zone_start - now).total_seconds())
                    if earliest is None or delta < earliest:
                        earliest = delta

        return earliest
