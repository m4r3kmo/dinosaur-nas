import argparse
import json
import os
import sqlite3

from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import sleep

from .cache import DiscoverCache
from .catalog import PLATFORMS
from .tmdb import TMDBClient


REGION = "SK"
MAX_PAGES = 500
REQUEST_DELAY = 0.25
RETENTION_DAYS = 90
RETRY_DELAY = 15

CATALOG_SORTS = {
    "movie": (
        "original_title.asc",
        "primary_release_date.asc",
    ),
    "tv": (
        "original_name.asc",
        "first_air_date.asc",
    ),
}


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

    def cleanup(self):

        cutoff = (
            datetime.now(timezone.utc)
            - timedelta(days=RETENTION_DAYS)
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


def fetch_catalog(
    client, provider_id, media_type, sort_by=None
):

    if sort_by is None:
        sort_by = CATALOG_SORTS[media_type][0]

    ids = set()
    seen_pages = {}
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
            sort_by=sort_by,
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

            tmdb_id = item.get("id")

            if type(tmdb_id) is not int or tmdb_id < 1:
                raise IncompleteCatalog(
                    f"Invalid TMDB ID {tmdb_id!r} "
                    f"on page {page}"
                )

            if tmdb_id in ids:
                raise IncompleteCatalog(
                    f"Duplicate TMDB ID {tmdb_id} "
                    f"on page {page}; "
                    f"first seen on page {seen_pages[tmdb_id]}"
                )

            ids.add(tmdb_id)
            seen_pages[tmdb_id] = page

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


def fetch_catalog_with_retry(client, provider_id, media_type):

    sorts = CATALOG_SORTS[media_type]

    for attempt, sort_by in enumerate(sorts, start=1):

        print(json.dumps({
            "provider": PLATFORMS[provider_id],
            "media_type": media_type,
            "attempt": attempt,
            "sort_by": sort_by,
            "status": "scanning",
        }), flush=True)

        try:
            return fetch_catalog(
                client,
                provider_id,
                media_type,
                sort_by=sort_by,
            )

        except IncompleteCatalog as exc:

            print(json.dumps({
                "provider": PLATFORMS[provider_id],
                "media_type": media_type,
                "attempt": attempt,
                "sort_by": sort_by,
                "status": "incomplete",
                "reason": str(exc),
            }), flush=True)

            if attempt == len(sorts):
                raise

            sleep(RETRY_DELAY)


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

    DiscoverCache().cleanup()
    print("METADATA CACHE CLEANUP: OK", flush=True)

    store = CatalogStore()
    store.cleanup()
    print("CATALOG RETENTION CLEANUP: OK", flush=True)

    client = TMDBClient()

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

                ids = fetch_catalog_with_retry(
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
