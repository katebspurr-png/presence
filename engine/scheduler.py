import logging
import time
from datetime import datetime, timedelta

from engine.activities.dead_stop import DeadStopActivity
from engine.activities.idle import IdleActivity
from engine.activities.mouse import MouseActivity
from engine.activities.typing import TypingActivity
from engine.activity_selector import ActivitySelector
from engine.logger import ActivityEvent, ActivityLogger
from engine.personas import get_persona
from engine.status import ConfigStore, EngineControl, StatusStore

logger = logging.getLogger(__name__)


def run_engine(
    control: EngineControl,
    config_store: ConfigStore,
    status_store: StatusStore,
    activity_logger: ActivityLogger,
    claude_client=None,
) -> None:
    """Main engine loop. Runs on the calling thread until control.stopped is set."""
    config = config_store.get()
    selector = ActivitySelector(config)
    logger.info("engine_loop_start")

    while True:
        if control.stopped.is_set():
            logger.info("engine_loop_stop")
            break

        if control.reload.is_set():
            config = config_store.get()
            selector.update_config(config)
            control.reload.clear()
            logger.info("engine_config_reloaded")

        if control.paused.is_set():
            time.sleep(1)
            continue

        try:
            activity_type, duration_s = selector.select()
        except Exception as e:
            logger.error(f"selector_error={e!r}", exc_info=True)
            time.sleep(1)
            continue

        persona_name = selector.current_persona_name
        next_change_at = (datetime.now() + timedelta(seconds=duration_s)).strftime("%H:%M:%S")

        status_store.update({
            "activity": activity_type,
            "persona": persona_name,
            "next_change_at": next_change_at,
            "time_until_dead_zone_s": selector.time_until_dead_zone_s(),
        })

        persona = get_persona(persona_name, config)
        hid_keyboard = config["hid"]["keyboard"]
        hid_mouse = config["hid"]["mouse"]

        if activity_type == "typing":
            activity = TypingActivity(
                config=config,
                wpm=persona.wpm,
                hid_path=hid_keyboard,
                claude_client=claude_client,
            )
        elif activity_type == "mouse":
            activity = MouseActivity(hid_path=hid_mouse)
        elif activity_type == "idle":
            activity = IdleActivity()
        else:
            activity = DeadStopActivity()

        logger.info(
            f"activity_start type={activity_type} persona={persona_name} "
            f"duration_s={duration_s:.1f}"
        )

        start = time.monotonic()
        try:
            result = activity.run(duration_s, control)
        except Exception as e:
            logger.error(f"activity_error type={activity_type} error={e!r}", exc_info=True)
            continue

        actual_duration = time.monotonic() - start

        activity_logger.log_activity(ActivityEvent(
            activity=activity_type,
            persona=persona_name,
            duration_s=actual_duration,
            metadata=result.metadata,
        ))
