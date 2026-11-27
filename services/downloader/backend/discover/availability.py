import json
import os
import sqlite3

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .catalog import PLATFORMS


class AvailabilityTracker:

    def __init__(self, db_path=None):

        state_dir = Path(
            os.getenv("DOWNLOADER_STATE_DIR", "/state")
        )

        self.db_path = Path(
            db_path or state_dir / "availability.db"
        )

        self.db_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with closing(self.connect()) as db, db:

            db.executescript("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    media_key TEXT PRIMARY KEY,
                    providers TEXT NOT NULL,
                    checked_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    media_key TEXT NOT NULL,
                    provider_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    detected_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS events_detected
                ON events(detected_at);
            """)

    def connect(self):

        db = sqlite3.connect(
            self.db_path,
            timeout=30,
        )

        db.row_factory = sqlite3.Row

        return db

    def observe(self, media_type, tmdb_id, providers):

        if media_type not in ("movie", "tv"):
            raise ValueError("Invalid media type")

        if int(tmdb_id) < 1:
            raise ValueError("Invalid TMDB ID")

        media_key = f"{media_type}:{tmdb_id}"

        current = {
            int(provider)
            for provider in providers
            if int(provider) in PLATFORMS
        }

        now = datetime.now(timezone.utc).isoformat()

        with closing(self.connect()) as db, db:

            db.execute("BEGIN IMMEDIATE")

            row = db.execute(
                """
                SELECT providers FROM snapshots
                WHERE media_key = ?
                """,
                (media_key,),
            ).fetchone()

            baseline = row is None

            previous = (
                set(json.loads(row["providers"]))
                if row else set()
            )

            added = current - previous if row else set()
            removed = previous - current if row else set()

            for event_type, changes in (
                ("added", added),
                ("removed", removed),
            ):

                db.executemany(
                    """
                    INSERT INTO events (
                        media_key,
                        provider_id,
                        event_type,
                        detected_at
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (media_key, provider, event_type, now)
                        for provider in sorted(changes)
                    ],
                )

            db.execute(
                """
                INSERT INTO snapshots (
                    media_key, providers, checked_at
                )
                VALUES (?, ?, ?)
                ON CONFLICT(media_key) DO UPDATE SET
                    providers = excluded.providers,
                    checked_at = excluded.checked_at
                """,
                (
                    media_key,
                    json.dumps(sorted(current)),
                    now,
                ),
            )

        return {
            "media_key": media_key,
            "baseline": baseline,
            "current": sorted(current),
            "added": sorted(added),
            "removed": sorted(removed),
        }

    def get_events(self, limit=100):

        with closing(self.connect()) as db:

            rows = db.execute(
                """
                SELECT * FROM events
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(1, min(int(limit), 1000)),),
            ).fetchall()

        return [
            {
                **dict(row),
                "provider": PLATFORMS.get(
                    row["provider_id"]
                ),
            }
            for row in rows
        ]
