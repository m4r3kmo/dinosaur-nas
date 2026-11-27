from datetime import datetime, date
from zoneinfo import ZoneInfo

from .catalog import DiscoverCatalog
from .library import get_owned_episodes


def compare_series(catalog, tmdb_id, library):

    if not library["matched"]:
        return {
            "matched": False,
            "seasons": [],
        }

    today = datetime.now(
        ZoneInfo("Europe/Bratislava")
    ).date()

    detail = catalog.details("tv", tmdb_id)

    seasons = []

    for season in detail.get("seasons", []):

        number = season["number"]

        data = catalog.cached(
            f"episodes:tv:{tmdb_id}:{number}",
            lambda: catalog.client.get(
                f"tv/{tmdb_id}/season/{number}",
                language="en-US",
            ),
        )

        owned = set(
            library["owned"].get(str(number), [])
        )

        aired = set()
        upcoming = set()
        unknown = set()

        for episode in data.get("episodes", []):

            ep_number = episode.get("episode_number")
            air_date = episode.get("air_date")

            if not isinstance(ep_number, int):
                continue

            if ep_number < 1:
                continue

            try:
                released = date.fromisoformat(
                    air_date or ""
                )
            except (ValueError, TypeError):
                unknown.add(ep_number)
                continue

            if released <= today:
                aired.add(ep_number)
            else:
                upcoming.add(ep_number)

        available = aired & owned
        missing = aired - owned

        seasons.append({
            "number": number,
            "name": season["name"],
            "aired": len(aired),
            "available": sorted(available),
            "missing": sorted(missing),
            "upcoming": sorted(upcoming),
            "unknown": sorted(unknown),
            "complete": (
                bool(aired)
                and not missing
                and not unknown
            ),
        })

    return {
        "matched": True,
        "tmdb_id": tmdb_id,
        "title": detail["title"],
        "seasons": sorted(
            seasons,
            key=lambda item: item["number"],
        ),
    }


def get_series_status(tmdb_id):

    library = get_owned_episodes(tmdb_id)

    return compare_series(
        DiscoverCatalog(),
        tmdb_id,
        library,
    )
