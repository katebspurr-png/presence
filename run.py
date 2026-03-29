#!/usr/bin/env python3
"""Presence behavioral engine entrypoint.

Usage:
    python3 run.py

Environment:
    PRESENCE_CONFIG      Path to config.json (default: config.json)
    ANTHROPIC_API_KEY    Required for Claude API content generation
                         (optional — falls back to bank if unset)
"""
import json
import logging
import os
import signal
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s level=%(levelname)s logger=%(name)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

log = logging.getLogger("presence")

# Engine imports must come after basicConfig so module-level
# logging.getLogger() calls in engine/*.py inherit the configured handler.
from engine.command_server import CommandServer
from engine.config_watcher import ConfigWatcher
from engine.logger import ActivityLogger
from engine.scheduler import run_engine
from engine.status import ConfigStore, EngineControl, StatusStore

CONFIG_PATH = os.environ.get("PRESENCE_CONFIG", "config.json")


def main() -> None:
    log.info(f"presence_start config={CONFIG_PATH}")

    with open(CONFIG_PATH) as f:
        config = json.load(f)

    control = EngineControl()
    control.running.set()

    config_store = ConfigStore(config)
    status_store = StatusStore()

    log_cfg = config.get("logging", {})
    db_path = log_cfg.get("db_path", "presence.db")
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    activity_logger = ActivityLogger(
        db_path=db_path,
        stdout=log_cfg.get("stdout", True),
    )

    server_cfg = config.get("command_server", {})
    command_server = CommandServer(
        host=server_cfg.get("host", "127.0.0.1"),
        port=int(server_cfg.get("port", 7777)),
        control=control,
        status_store=status_store,
    )
    command_server.start()

    config_watcher = ConfigWatcher(
        config_path=CONFIG_PATH,
        config_store=config_store,
        control=control,
    )
    config_watcher.start()

    claude_client = None
    try:
        import anthropic
        claude_client = anthropic.Anthropic()
        log.info("claude_client_initialized")
    except Exception as e:
        log.warning(f"claude_client_unavailable={e!r} using_fallback_bank=True")

    def _handle_signal(sig, frame):
        log.info(f"signal={sig} shutting_down")
        control.stopped.set()
        command_server.shutdown()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    run_engine(
        control=control,
        config_store=config_store,
        status_store=status_store,
        activity_logger=activity_logger,
        claude_client=claude_client,
    )


if __name__ == "__main__":
    main()
