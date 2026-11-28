import os
import sqlite3
import time

from contextlib import closing
from pathlib import Path

from .csfd import CACHE_TTL, DAILY_LIMIT, REQUEST_WINDOW


def get_csfd_metrics(db_path=None):
    path = Path(
        db_path or Path(
            os.getenv("DOWNLOADER_STATE_DIR", "/state")
        ) / "csfd_cache.db"
    )

    definitions = {
        "ok_total": (
            "counter", "Successfully matched CSFD ratings"
        ),
        "not_found_total": (
            "counter", "Titles not found in CZDB"
        ),
        "not_rated_total": (
            "counter", "Titles without CSFD rating"
        ),
        "ambiguous_total": (
            "counter", "Ambiguous CZDB results"
        ),
        "api_requests_total": (
            "counter", "Reserved CZDB API requests"
        ),
        "cache_hits_total": (
            "counter", "CSFD cache hits"
        ),
        "cache_misses_total": (
            "counter", "CSFD cache misses"
        ),
        "api_errors_total": (
            "counter", "CZDB API errors"
        ),
        "api_429_total": (
            "counter", "CZDB HTTP 429 responses"
        ),
        "requests_last_24h": (
            "gauge", "Requests in rolling 24 hour window"
        ),
        "request_limit": (
            "gauge", "Internal CZDB request limit"
        ),
        "cache_entries": (
            "gauge", "Unexpired CSFD cache records"
        ),
    }

    values = dict.fromkeys(definitions, 0)
    values["request_limit"] = DAILY_LIMIT

    if path.is_file():
        now = int(time.time())

        uri = path.resolve().as_uri() + "?mode=ro"

        try:
            with closing(sqlite3.connect(
                uri, uri=True, timeout=5
            )) as db:

                db.execute("BEGIN")

                tables = {
                    row[0] for row in db.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type = 'table'"
                    )
                }

                if "counters" in tables:
                    for name, value in db.execute(
                        "SELECT name, value FROM counters"
                    ):
                        key = name + "_total"

                        if key in values:
                            values[key] = value

                if "requests" in tables:
                    values["requests_last_24h"] = (
                        db.execute(
                            "SELECT COUNT(*) FROM requests "
                            "WHERE requested_at > ?",
                            (now - REQUEST_WINDOW,),
                        ).fetchone()[0]
                    )

                if "ratings" in tables:
                    values["cache_entries"] = (
                        db.execute(
                            "SELECT COUNT(*) FROM ratings "
                            "WHERE fetched_at > ?",
                            (now - CACHE_TTL,),
                        ).fetchone()[0]
                    )

        except (sqlite3.Error, OSError):
            return (
                "# TYPE dinosaur_csfd_metrics_up gauge\n"
                "dinosaur_csfd_metrics_up 0\n"
            )

    lines = [
        "# TYPE dinosaur_csfd_metrics_up gauge",
        "dinosaur_csfd_metrics_up 1",
    ]

    for name, (kind, description) in definitions.items():
        metric = "dinosaur_csfd_" + name

        lines.extend([
            f"# HELP {metric} {description}",
            f"# TYPE {metric} {kind}",
            f"{metric} {values[name]}",
        ])

    return "\n".join(lines) + "\n"
