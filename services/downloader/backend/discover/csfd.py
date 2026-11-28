import json
import os
import re
import sqlite3
import time

from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_URL = "https://api.czdb.cz/search"
CACHE_TTL = 7 * 24 * 60 * 60
DAILY_LIMIT = 90
REQUEST_WINDOW = 24 * 60 * 60
RETRY_DELAY = 300
TIMEOUT = 10

MEDIA_TYPES = {
    "movie": "movie",
    "tv": "series",
}


def _connect(db_path=None):
    path = Path(
        db_path or Path(
            os.getenv("DOWNLOADER_STATE_DIR", "/state")
        ) / "csfd_cache.db"
    )

    path.parent.mkdir(parents=True, exist_ok=True)

    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row

    db.executescript("""
        CREATE TABLE IF NOT EXISTS ratings (
            media_type TEXT NOT NULL,
            tmdb_id INTEGER NOT NULL,
            imdb_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            fetched_at INTEGER NOT NULL,
            PRIMARY KEY (media_type, tmdb_id)
        );

        CREATE TABLE IF NOT EXISTS requests (
            media_type TEXT NOT NULL,
            tmdb_id INTEGER NOT NULL,
            requested_at INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS requests_timestamp
        ON requests(requested_at);

        CREATE TABLE IF NOT EXISTS counters (
            name TEXT PRIMARY KEY,
            value INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value INTEGER NOT NULL
        );
    """)

    return db


def _inc(db, name):
    db.execute(
        '''
        INSERT INTO counters (name, value)
        VALUES (?, 1)
        ON CONFLICT(name) DO UPDATE SET
            value = value + 1
        ''',
        (name,),
    )


def _record_error(db_path):
    with closing(_connect(db_path)) as db, db:
        _inc(db, "api_errors")


def _empty(status):
    return {
        "csfd_rating": None,
        "csfd_id": None,
        "csfd_url": None,
        "status": status,
    }


def _fetch(imdb_id, api_key):
    url = API_URL + "?" + urlencode({"i": imdb_id})

    request = Request(
        url,
        headers={
            "X-API-Key": api_key,
            "Accept": "application/json",
            "User-Agent": "Dinosaur-Discover/0.6.3",
        },
    )

    with urlopen(request, timeout=TIMEOUT) as response:
        return json.load(response)


def _normalize(data, tmdb_id, imdb_id, media_type):
    if not isinstance(data, dict):
        raise ValueError("Invalid CZDB response")

    # CZDB returns this response when no title is found.
    if data == {"response": "False"}:
        return _empty("not_found")

    results = data.get("results")

    if not isinstance(results, list):
        raise ValueError("Invalid CZDB results")

    matches = [
        row for row in results
        if isinstance(row, dict)
        and str(row.get("tmdb_id")) == str(tmdb_id)
        and row.get("imdb_id") == imdb_id
        and row.get("druh") == MEDIA_TYPES.get(media_type)
    ]

    if len(matches) != 1:
        return _empty(
            "ambiguous" if len(matches) > 1
            else "not_found"
        )

    row = matches[0]
    raw_rating = str(row.get("hodnoceni", "")).strip()

    if not re.fullmatch(r"(100|[0-9]{1,2})%", raw_rating):
        return _empty("not_rated")

    return {
        "csfd_rating": int(raw_rating[:-1]),
        "csfd_id": row.get("csfd_id"),
        "csfd_url": row.get("csfd_url"),
        "status": "ok",
    }


def get_rating(
    tmdb_id,
    imdb_id,
    media_type="movie",
    db_path=None,
):
    if media_type not in MEDIA_TYPES:
        return _empty("unsupported")

    if not re.fullmatch(r"tt[0-9]+", imdb_id or ""):
        return _empty("missing_imdb_id")

    now = int(time.time())
    key = (media_type, tmdb_id)
    api_key = os.getenv("CZDB_API_KEY", "").strip()

    with closing(_connect(db_path)) as db, db:
        db.execute("BEGIN IMMEDIATE")

        db.execute(
            "DELETE FROM ratings WHERE fetched_at <= ?",
            (now - CACHE_TTL,),
        )

        db.execute(
            "DELETE FROM requests WHERE requested_at <= ?",
            (now - REQUEST_WINDOW,),
        )

        cached = db.execute("""
            SELECT payload FROM ratings
            WHERE media_type = ?
              AND tmdb_id = ?
              AND imdb_id = ?
        """, (*key, imdb_id)).fetchone()

        if cached:
            _inc(db, "cache_hits")
            return json.loads(cached["payload"])

        _inc(db, "cache_misses")

        if not api_key:
            return _empty("disabled")

        paused = db.execute("""
            SELECT value FROM settings
            WHERE key = 'blocked_until'
        """).fetchone()

        if paused and paused["value"] > now:
            return _empty("rate_limited")

        used = db.execute(
            "SELECT COUNT(*) FROM requests"
        ).fetchone()[0]

        if used >= DAILY_LIMIT:
            return _empty("rate_limited")

        recent = db.execute("""
            SELECT 1 FROM requests
            WHERE media_type = ?
              AND tmdb_id = ?
              AND requested_at > ?
            LIMIT 1
        """, (*key, now - RETRY_DELAY)).fetchone()

        if recent:
            return _empty("retry_later")

        db.execute("""
            INSERT INTO requests
            (media_type, tmdb_id, requested_at)
            VALUES (?, ?, ?)
        """, (*key, now))

        _inc(db, "api_requests")

    try:
        data = _fetch(imdb_id, api_key)

        result = _normalize(
            data, tmdb_id, imdb_id, media_type
        )

    except HTTPError as exc:
        _record_error(db_path)
        if exc.code == 429:
            with closing(_connect(db_path)) as db, db:
                _inc(db, "api_429")
                db.execute("""
                    INSERT INTO settings (key, value)
                    VALUES ('blocked_until', ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value
                """, (int(time.time()) + REQUEST_WINDOW,))

            return _empty("rate_limited")

        if exc.code in (401, 403):
            return _empty("auth_error")

        return _empty("api_error")

    except (URLError, OSError, ValueError):
        _record_error(db_path)
        return _empty("api_error")

    with closing(_connect(db_path)) as db, db:
        if result["status"] in (
            "ok", "not_found", "not_rated", "ambiguous"
        ):
            _inc(db, result["status"])

        db.execute("""
            INSERT INTO ratings
                (media_type, tmdb_id, imdb_id,
                 payload, fetched_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(media_type, tmdb_id)
            DO UPDATE SET
                imdb_id = excluded.imdb_id,
                payload = excluded.payload,
                fetched_at = excluded.fetched_at
        """, (
            *key,
            imdb_id,
            json.dumps(result),
            int(time.time()),
        ))

    return result
