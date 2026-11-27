import argparse
import json

from contextlib import closing

from .availability import AvailabilityTracker
from .catalog import DiscoverCatalog


def get_tracked_keys(tracker):

    with closing(tracker.connect()) as db:

        rows = db.execute(
            "SELECT media_key FROM snapshots"
        ).fetchall()

    return {row["media_key"] for row in rows}


def scan_title(catalog, tracker, media_key):

    media_type, tmdb_id = media_key.split(":", 1)

    # Fresh TMDB data, bypassing DiscoverCache.
    data = catalog.client.details(
        media_type,
        int(tmdb_id),
    )

    results = data.get(
        "watch/providers", {}
    ).get("results", {})

    availability = results.get("SK")

    if not isinstance(availability, dict) or not availability:
        return {
            "media_key": media_key,
            "status": "unknown",
            "reason": "No confirmed SK availability data",
        }

    providers = availability.get("flatrate", [])

    if not isinstance(providers, list):
        raise ValueError("Invalid provider response")

    provider_ids = [
        int(provider["provider_id"])
        for provider in providers
    ]

    return tracker.observe(
        media_type,
        int(tmdb_id),
        provider_ids,
    )


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "keys",
        nargs="*",
        help="Media keys, e.g. movie:671",
    )

    parser.add_argument(
        "--seed-releases",
        action="store_true",
    )

    args = parser.parse_args()

    catalog = DiscoverCatalog()
    tracker = AvailabilityTracker()

    keys = get_tracked_keys(tracker)
    keys.update(args.keys)

    if args.seed_releases:

        releases = catalog.releases(
            media_type="all",
            days=30,
            min_rating=0,
            min_votes=0,
            page_limit=2,
        )

        keys.update(
            item["key"]
            for item in releases["items"]
        )

        print(json.dumps({
            "seed_titles": releases["count"],
            "truncated": releases["truncated"],
            "errors": releases["errors"],
        }))

    summary = {
        "tracked": len(keys),
        "checked": 0,
        "baselines": 0,
        "added": 0,
        "removed": 0,
        "unknown": 0,
        "errors": 0,
    }

    for key in sorted(keys):

        try:

            result = scan_title(
                catalog,
                tracker,
                key,
            )

            print(json.dumps(result))

            if result.get("status") == "unknown":
                summary["unknown"] += 1
                continue

            summary["checked"] += 1

            if result["baseline"]:
                summary["baselines"] += 1

            summary["added"] += len(result["added"])
            summary["removed"] += len(result["removed"])

        except Exception as exc:

            summary["errors"] += 1

            print(json.dumps({
                "media_key": key,
                "error": type(exc).__name__,
            }))

    print("SCAN SUMMARY")
    print(json.dumps(summary, indent=2))

    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
