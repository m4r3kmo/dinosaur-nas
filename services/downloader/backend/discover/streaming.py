import json

from contextlib import closing
from datetime import datetime, timedelta, timezone

from .catalog import DiscoverCatalog, PLATFORMS
from .scan_catalogs import CatalogStore
from .tmdb import TMDBError


def get_streaming_status(store=None):

    store = store or CatalogStore()

    with closing(store.connect()) as db:

        rows = db.execute(
            "SELECT * FROM catalogs"
        ).fetchall()

    indexed = {
        (row["provider_id"], row["media_type"]): row
        for row in rows
    }

    catalogs = []

    for provider_id, provider_name in PLATFORMS.items():

        for media_type in ("movie", "tv"):

            row = indexed.get(
                (provider_id, media_type)
            )

            confirmed = (
                set(json.loads(row["confirmed"]))
                if row else set()
            )

            observed = (
                set(json.loads(row["observed"]))
                if row else set()
            )

            catalogs.append({
                "provider_id": provider_id,
                "provider": provider_name,
                "media_type": media_type,
                "initialized": row is not None,
                "titles": len(confirmed),
                "pending_added": len(
                    observed - confirmed
                ),
                "pending_removed": len(
                    confirmed - observed
                ),
                "scanned_at": (
                    row["scanned_at"] if row else None
                ),
            })

    initialized = sum(
        item["initialized"] for item in catalogs
    )

    return {
        "region": "SK",
        "initialized_catalogs": initialized,
        "total_catalogs": len(catalogs),
        "baseline_complete": (
            initialized == len(catalogs)
        ),
        "tracked_entries": sum(
            item["titles"] for item in catalogs
        ),
        "catalogs": catalogs,
    }


def get_streaming_additions(
    media_type="all",
    provider_id=0,
    days=30,
    limit=24,
    offset=0,
    store=None,
    catalog=None,
):

    store = store or CatalogStore()

    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(days=days)
    ).isoformat()

    with closing(store.connect()) as db:

        db.execute("BEGIN")

        snapshots = db.execute(
            "SELECT * FROM catalogs"
        ).fetchall()

        rows = db.execute("""
            SELECT *
            FROM catalog_events
            WHERE event_type = 'added'
              AND detected_at >= ?
              AND (? = 'all' OR media_type = ?)
              AND (? = 0 OR provider_id = ?)
            ORDER BY detected_at DESC, id DESC
        """, (
            cutoff,
            media_type,
            media_type,
            provider_id,
            provider_id,
        )).fetchall()

    available = {
        (row["provider_id"], row["media_type"]):
            set(json.loads(row["confirmed"]))
            & set(json.loads(row["observed"]))
        for row in snapshots
    }

    grouped = {}

    for row in rows:

        pid = row["provider_id"]
        kind = row["media_type"]
        tmdb_id = row["tmdb_id"]

        if pid not in PLATFORMS:
            continue

        if tmdb_id not in available.get(
            (pid, kind), set()
        ):
            continue

        key = (kind, tmdb_id)

        entry = grouped.setdefault(key, {
            "detected_at": row["detected_at"],
            "additions": {},
        })

        entry["additions"].setdefault(pid, {
            "provider_id": pid,
            "provider": PLATFORMS[pid],
            "detected_at": row["detected_at"],
        })

    candidates = list(grouped.items())
    total = len(candidates)

    selected = candidates[offset:offset + limit]

    items = []
    errors = []

    if selected and catalog is None:
        catalog = DiscoverCatalog()

    for (kind, tmdb_id), entry in selected:

        try:

            detail = dict(
                catalog.details(kind, tmdb_id)
            )

            detail["detected_at"] = entry[
                "detected_at"
            ]

            detail["streaming_additions"] = list(
                entry["additions"].values()
            )

            items.append(detail)

        except TMDBError:

            errors.append({
                "media_type": kind,
                "tmdb_id": tmdb_id,
                "error": "Metadata unavailable",
            })

    return {
        "region": "SK",
        "date_type": "availability_detected_at",
        "total": total,
        "count": len(items),
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < total,
        "items": items,
        "errors": errors,
    }
