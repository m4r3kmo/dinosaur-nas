import json
import os
import sqlite3

from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .catalog import PLATFORMS


def get_streaming_metrics(db_path=None):

    path = Path(
        db_path or Path(
            os.getenv("DOWNLOADER_STATE_DIR", "/state")
        ) / "streaming_catalog.db"
    )

    snapshots = {}
    additions = {}

    database_present = path.is_file()

    if database_present:

        uri = path.resolve().as_uri() + "?mode=ro"

        with closing(sqlite3.connect(
            uri, uri=True, timeout=5
        )) as db:

            db.row_factory = sqlite3.Row
            db.execute("BEGIN")

            for row in db.execute("SELECT * FROM catalogs"):

                snapshots[
                    (row["provider_id"], row["media_type"])
                ] = row

            cutoff = (
                datetime.now(timezone.utc)
                - timedelta(days=30)
            ).isoformat()

            for row in db.execute("""
                SELECT provider_id, media_type, COUNT(*) AS total
                FROM catalog_events
                WHERE event_type = 'added'
                  AND detected_at >= ?
                GROUP BY provider_id, media_type
            """, (cutoff,)):

                additions[
                    (row["provider_id"], row["media_type"])
                ] = row["total"]

    definitions = {
        "titles": "Confirmed streaming catalog entries",
        "initialized": "Catalog baseline initialized",
        "last_success_timestamp_seconds": "Last successful catalog scan",
        "pending_added": "Unconfirmed catalog additions",
        "pending_removed": "Unconfirmed catalog removals",
        "additions_30d": "Confirmed addition events in the last 30 days",
    }

    metrics = {
        name: [] for name in definitions
    }

    for provider_id, provider in PLATFORMS.items():

        for media_type in ("movie", "tv"):

            key = (provider_id, media_type)
            row = snapshots.get(key)

            confirmed = (
                set(json.loads(row["confirmed"]))
                if row else set()
            )

            observed = (
                set(json.loads(row["observed"]))
                if row else set()
            )

            timestamp = (
                int(datetime.fromisoformat(
                    row["scanned_at"]
                ).timestamp())
                if row else 0
            )

            labels = (
                f'provider="{provider}",'
                f'provider_id="{provider_id}",'
                f'media_type="{media_type}"'
            )

            values = {
                "titles": len(confirmed),
                "initialized": int(row is not None),
                "last_success_timestamp_seconds": timestamp,
                "pending_added": len(observed - confirmed),
                "pending_removed": len(confirmed - observed),
                "additions_30d": additions.get(key, 0),
            }

            for name, value in values.items():

                metrics[name].append(
                    f'dinosaur_streaming_catalog_{name}'
                    f'{{{labels}}} {value}'
                )

    lines = [
        "# HELP dinosaur_streaming_catalog_database_present "
        "Streaming catalog database exists",
        "# TYPE dinosaur_streaming_catalog_database_present gauge",
        f"dinosaur_streaming_catalog_database_present "
        f"{int(database_present)}",
    ]

    for name, description in definitions.items():

        full_name = f"dinosaur_streaming_catalog_{name}"

        lines.extend([
            f"# HELP {full_name} {description}",
            f"# TYPE {full_name} gauge",
            *metrics[name],
        ])

    return "\n".join(lines) + "\n"
