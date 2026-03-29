import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class ActivityEvent:
    activity: str
    persona: str
    duration_s: float
    metadata: dict = field(default_factory=dict)


class ActivityLogger:
    def __init__(self, db_path: str, stdout: bool = True) -> None:
        self.db_path = db_path
        self.stdout = stdout
        self._init_db()

    def _init_db(self) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS activity_log (
                        id         INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts         TEXT NOT NULL,
                        activity   TEXT NOT NULL,
                        persona    TEXT NOT NULL,
                        duration_s REAL NOT NULL,
                        metadata   TEXT
                    )
                """)
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"sqlite_init_error={e!r} db_path={self.db_path}")

    def log_activity(self, event: ActivityEvent) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        metadata_json = json.dumps(event.metadata)

        if self.stdout:
            logger.info(
                f"ts={ts} activity={event.activity} persona={event.persona} "
                f"duration_s={event.duration_s:.1f} metadata={metadata_json}"
            )

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO activity_log (ts, activity, persona, duration_s, metadata) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (ts, event.activity, event.persona, event.duration_s, metadata_json),
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"sqlite_write_error={e!r} activity={event.activity}")
