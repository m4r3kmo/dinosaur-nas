import argparse
import json
import os
import sqlite3

from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import sleep

from .catalog import PLATFORMS
from .tmdb import TMDBClient


REGION = "SK"
MAX_PAGES = 500
REQUEST_DELAY = 0.25
RETENTION_DAYS = 90


class IncompleteCatalog(RuntimeError):
    pass


class CatalogStore:

    def __init__(self, path=None):

        self.path = Path(
            path or Path(
                os.getenv("DOWNLOADER_STATE_DIR", "/state")
            ) / "streaming_catalog.db"
        )

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with closing(self.connect()) as db, db:

            db.executescript("""
                CREATE TABLE IF NOT EXISTS catalogs (
                    provider_id INTEGER NOT NULL,
                    media_type TEXT NOT NULL,
                    confirmed TEXT NOT NULL,
                    observed TEXT NOT NULL,
                    scanned_at TEXT NOT NULL,
                    PRIMARY KEY (provider_id, media_type)
                );

                CREATE TABLE IF NOT EXISTS catalog_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_id INTEGER NOT NULL,
                    media_type TEXT NOT NULL,
                    tmdb_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    detected_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS catalog_events_date
                ON catalog_events(detected_at);
            """)

    def connect(self):

        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row

        return db

    def observe(self, provider_id, media_type, ids):

        current = set(ids)

        now = datetime.now(timezone.utc)
        timestamp = now.isoformat()

        cutoff = (
            now - timedelta(days=RETENTION_DAYS)
        ).isoformat()

        with closing(self.connect()) as db, db:

            db.execute("BEGIN IMMEDIATE")

            db.execute(
                "DELETE FROM catalog_events WHERE detected_at < ?",
                (cutoff,),
            )

            db.execute(
                "DELETE FROM catalogs WHERE scanned_at < ?",
                (cutoff,),
            )

            row = db.execute("""
                SELECT confirmed, observed
                FROM catalogs
                WHERE provider_id = ? AND media_type = ?
            """, (provider_id, media_type)).fetchone()

            baseline = row is None

            if baseline:

                confirmed = current.copy()
                added = set()
                removed = set()

            else:

                confirmed = set(json.loads(row["confirmed"]))
                previous = set(json.loads(row["observed"]))

                # Require two successful observations.
                added = (current - confirmed) & previous
                removed = (confirmed - current) - previous

                confirmed = (confirmed | added) - removed

                for event_type, changes in (
                    ("added", added),
                    ("removed", removed),
                ):

                    db.executemany("""
                        INSERT INTO catalog_events (
                            provider_id,
                            media_type,
                            tmdb_id,
                            event_type,
                            detected_at
                        )
                        VALUES (?, ?, ?, ?, ?)
                    """, [
                        (
                            provider_id,
                            media_type,
                            tmdb_id,
                            event_type,
                            timestamp,
                        )
                        for tmdb_id in sorted(changes)
                    ])

            db.execute("""
                INSERT INTO catalogs (
                    provider_id,
                    media_type,
                    confirmed,
                    observed,
                    scanned_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(provider_id, media_type)
                DO UPDATE SET
                    confirmed = excluded.confirmed,
                    observed = excluded.observed,
                    scanned_at = excluded.scanned_at
            """, (
                provider_id,
                media_type,
                json.dumps(sorted(confirmed)),
                json.dumps(sorted(current)),
                timestamp,
            ))

        return {
            "provider": PLATFORMS[provider_id],
            "media_type": media_type,
            "baseline": baseline,
            "titles": len(current),
            "added": len(added),
            "removed": len(removed),
            "pending_added": len(current - confirmed),
            "pending_removed": len(confirmed - current),
        }


def fetch_catalog(client, provider_id, media_type):

    ids = set()
    page = 1
    expected_pages = None
    expected_total = None

    while True:

        sleep(REQUEST_DELAY)

        data = client.get(
            f"discover/{media_type}",
            page=page,
            watch_region=REGION,
            with_watch_providers=str(provider_id),
            with_watch_monetization_types="flatrate",
            include_adult="false",
            sort_by="popularity.desc",
        )

        if expected_pages is None:

            expected_pages = int(data["total_pages"])
            expected_total = int(data["total_results"])

            if not 1 <= expected_pages <= MAX_PAGES:
                raise IncompleteCatalog(
                    "Invalid or unsupported page count"
                )

            if expected_total < 1:
                raise IncompleteCatalog(
                    "Unexpected empty catalog"
                )

        if (
            int(data["page"]) != page
            or int(data["total_pages"]) != expected_pages
            or int(data["total_results"]) != expected_total
        ):
            raise IncompleteCatalog(
                "Catalog changed during scan"
            )

        for item in data["results"]:

            tmdb_id = int(item["id"])

            if tmdb_id < 1 or tmdb_id in ids:
                raise IncompleteCatalog(
                    "Invalid or duplicate TMDB ID"
                )

            ids.add(tmdb_id)

        if page == expected_pages:
            break

        if page % 25 == 0:
            print(
                f"Progress: {PLATFORMS[provider_id]} "
                f"{media_type} {page}/{expected_pages}",
                flush=True,
            )

        page += 1

    if len(ids) != expected_total:
        raise IncompleteCatalog(
            f"Expected {expected_total}, got {len(ids)}"
        )

    return ids


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--provider",
        type=int,
        choices=PLATFORMS,
    )

    parser.add_argument(
        "--media-type",
        choices=("movie", "tv"),
    )

    args = parser.parse_args()

    client = TMDBClient()
    store = CatalogStore()

    providers = (
        [args.provider]
        if args.provider
        else PLATFORMS.keys()
    )

    media_types = (
        [args.media_type]
        if args.media_type
        else ("movie", "tv")
    )

    failed = 0

    for provider_id in providers:

        for media_type in media_types:

            try:

                ids = fetch_catalog(
                    client,
                    provider_id,
                    media_type,
                )

                result = store.observe(
                    provider_id,
                    media_type,
                    ids,
                )

                print(json.dumps(result), flush=True)

            except IncompleteCatalog as exc:

                failed += 1

                print(json.dumps({
                    "provider": PLATFORMS[provider_id],
                    "media_type": media_type,
                    "status": "incomplete",
                    "reason": str(exc),
                }), flush=True)

                continue

            except Exception as exc:

                print(json.dumps({
                    "provider": PLATFORMS[provider_id],
                    "media_type": media_type,
                    "status": "failed",
                    "error": type(exc).__name__,
                }), flush=True)

                # Stop on incomplete data or API failure.
                return 1

    if failed:
        print(f"CATALOG SCAN INCOMPLETE: {failed}", flush=True)
        return 1

    print("CATALOG SCAN COMPLETE", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
