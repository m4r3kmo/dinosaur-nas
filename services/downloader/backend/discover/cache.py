import json
import os
import sqlite3
import time

from contextlib import closing
from pathlib import Path


class DiscoverCache:

    def __init__(self):
        state = Path(
            os.getenv("DOWNLOADER_STATE_DIR", "/state")
        )

        state.mkdir(parents=True, exist_ok=True)

        self.path = state / "discover.db"

        with closing(self.connect()) as db, db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                )
            """)

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def get(self, key, ttl=21600):

        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT payload, updated_at "
                "FROM cache WHERE key = ?",
                (key,),
            ).fetchone()

        if not row:
            return None

        payload, updated_at = row

        if time.time() - updated_at >= ttl:
            return None

        return json.loads(payload)

    def set(self, key, payload):

        with closing(self.connect()) as db, db:
            db.execute("""
                INSERT INTO cache (
                    key, payload, updated_at
                )
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
            """, (
                key,
                json.dumps(payload),
                int(time.time()),
            ))

    def cleanup(self, max_age=604800):

        with closing(self.connect()) as db, db:
            db.execute(
                "DELETE FROM cache WHERE updated_at < ?",
                (int(time.time()) - max_age,),
            )
