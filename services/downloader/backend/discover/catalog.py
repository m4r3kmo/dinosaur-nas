import json

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .cache import DiscoverCache
from .tmdb import TMDBClient, TMDBError


REGION = "SK"
CACHE_TTL = 21600
DEFAULT_PAGES = 2
MAX_PAGES = 10

PLATFORMS = {
    8: "Netflix",
    119: "Prime Video",
    337: "Disney+",
    350: "Apple TV",
    1899: "HBO Max",
    1773: "SkyShowtime",
}


class DiscoverCatalog:

    def __init__(self):
        self.client = TMDBClient()
        self.cache = DiscoverCache()

    def cached(self, key, loader):

        cached = self.cache.get(key, CACHE_TTL)

        if cached is not None:
            return cached

        result = loader()
        self.cache.set(key, result)

        return result

    def providers(self, media_type):

        if media_type not in ("movie", "tv"):
            raise ValueError("Invalid media type")

        def load():

            providers = self.client.providers(
                media_type,
                REGION,
            )

            available = {
                item["provider_id"]: item
                for item in providers
            }

            return [
                {
                    "id": provider_id,
                    "name": name,
                    "logo": self.client.poster_url(
                        available[provider_id].get(
                            "logo_path"
                        ),
                        "w92",
                    ),
                }
                for provider_id, name in PLATFORMS.items()
                if provider_id in available
            ]

        return self.cached(
            f"providers:{REGION}:{media_type}",
            load,
        )

    def normalize(self, item, media_type, provider):

        is_movie = media_type == "movie"

        release_date = (
            item.get("release_date")
            if is_movie
            else item.get("first_air_date")
        ) or ""

        title = (
            item.get("title")
            if is_movie
            else item.get("name")
        ) or ""

        original_title = (
            item.get("original_title")
            if is_movie
            else item.get("original_name")
        ) or title

        votes = item.get("vote_count") or 0

        rating = (
            round(item.get("vote_average", 0) * 10, 1)
            if votes else None
        )

        return {
            "id": item["id"],
            "key": f'{media_type}:{item["id"]}',
            "media_type": media_type,
            "title": title,
            "original_title": original_title,
            "year": release_date[:4],
            "release_date": release_date,
            "overview": item.get("overview") or "",
            "poster": self.client.poster_url(
                item.get("poster_path")
            ),
            "backdrop": self.client.poster_url(
                item.get("backdrop_path"),
                "w780",
            ),
            "genre_ids": item.get("genre_ids", []),
            "tmdb_rating": rating,
            "tmdb_votes": votes,
            "csfd_rating": None,
            "popularity": item.get("popularity") or 0,
            "providers": [provider],
        }

    def fetch_provider(
        self,
        media_type,
        provider,
        days,
        min_rating,
        min_votes,
        sort,
        page_limit=DEFAULT_PAGES,
        genre_ids=(),
    ):

        today = datetime.now(
            ZoneInfo("Europe/Bratislava")
        ).date()

        start = today - timedelta(days=days)

        date_field = (
            "primary_release_date"
            if media_type == "movie"
            else "air_date"
        )

        sorts = {
            "newest": (
                "primary_release_date.desc"
                if media_type == "movie"
                else "popularity.desc"
            ),
            "rating": "vote_average.desc",
            "popular": "popularity.desc",
        }

        params = {
            "with_watch_providers": provider["id"],
            f"{date_field}.gte": start.isoformat(),
            f"{date_field}.lte": today.isoformat(),
            "vote_average.gte": min_rating / 10,
            "vote_count.gte": min_votes,
            "sort_by": sorts[sort],
        }

        if genre_ids:
            params["with_genres"] = "|".join(
                map(str, genre_ids)
            )

        results = []
        total_pages = 1

        for page in range(1, page_limit + 1):

            if page > total_pages:
                break

            cache_key = json.dumps(
                [
                    "release-page-v2",
                    REGION,
                    media_type,
                    params,
                    page,
                ],
                sort_keys=True,
            )

            payload = self.cached(
                cache_key,
                lambda page=page: self.client.discover(
                    media_type,
                    page=page,
                    **params,
                ),
            )

            total_pages = payload.get(
                "total_pages", 1
            )

            results.extend(
                self.normalize(
                    item, media_type, provider
                )
                for item in payload.get(
                    "results", []
                )
            )

        return {
            "items": results,
            "truncated": total_pages > page_limit,
        }

    def recent_tv_season(self, item, days):

        today = datetime.now(
            ZoneInfo("Europe/Bratislava")
        ).date()

        start = today - timedelta(days=days)

        detail = self.details("tv", item["id"])

        recent = []

        for season in detail.get("seasons", []):

            air_date = season.get("air_date")

            if not air_date:
                continue

            if start.isoformat() <= air_date <= today.isoformat():
                recent.append(season)

        if not recent:
            return None

        latest = max(
            recent,
            key=lambda season: (
                season["air_date"],
                season["number"],
            ),
        )

        return {
            **item,
            "first_air_date": item["release_date"],
            "release_date": latest["air_date"],
            "season_number": latest["number"],
            "release_kind": (
                "new_series"
                if latest["number"] == 1
                else "new_season"
            ),
        }

    def releases(
        self,
        media_type="all",
        provider_id=0,
        days=90,
        min_rating=50,
        min_votes=5,
        sort="newest",
        page_limit=DEFAULT_PAGES,
        genres=(),
    ):
        from .genres import genre_ids_for

        if not DEFAULT_PAGES <= page_limit <= MAX_PAGES:
            raise ValueError("Invalid page limit")

        if media_type not in ("all", "movie", "tv"):
            raise ValueError("Invalid media type")

        if sort not in ("newest", "rating", "popular"):
            raise ValueError("Invalid sort")

        if provider_id and provider_id not in PLATFORMS:
            raise ValueError("Invalid provider")

        self.cache.cleanup()

        media_types = (
            ("movie", "tv")
            if media_type == "all"
            else (media_type,)
        )

        jobs = []

        for kind in media_types:

            if genres and not genre_ids_for(kind, genres):
                continue

            for provider in self.providers(kind):

                if provider_id and provider["id"] != provider_id:
                    continue

                jobs.append((kind, provider))

        merged = {}
        errors = []
        truncated = False
        successful = 0

        with ThreadPoolExecutor(max_workers=6) as executor:

            futures = [
                (
                    kind,
                    provider,
                    executor.submit(
                        self.fetch_provider,
                        kind,
                        provider,
                        days,
                        min_rating,
                        min_votes,
                        sort,
                        page_limit,
                        genre_ids_for(kind, genres),
                    ),
                )
                for kind, provider in jobs
            ]

            for kind, provider, future in futures:

                try:
                    result = future.result()

                    successful += 1
                    truncated |= result["truncated"]

                except TMDBError as exc:
                    errors.append({
                        "provider": provider["name"],
                        "media_type": kind,
                        "error": str(exc),
                    })
                    continue

                for item in result["items"]:

                    key = item["key"]

                    if key not in merged:
                        merged[key] = item
                        continue

                    existing = merged[key]

                    known_ids = {
                        p["id"]
                        for p in existing["providers"]
                    }

                    for p in item["providers"]:
                        if p["id"] not in known_ids:
                            existing["providers"].append(p)
                            known_ids.add(p["id"])

        if jobs and not successful:
            raise TMDBError("All catalog queries failed")

        items = [
            item for item in merged.values()
            if (
                min_rating == 0 or (
                    item["tmdb_rating"] is not None
                    and item["tmdb_rating"] >= min_rating
                )
            )
            and item["tmdb_votes"] >= min_votes
        ]

        movies = [
            {
                **item,
                "release_kind": "new_movie",
                "season_number": None,
            }
            for item in items
            if item["media_type"] == "movie"
        ]

        series = [
            item for item in items
            if item["media_type"] == "tv"
        ]

        recent_series = []

        with ThreadPoolExecutor(max_workers=6) as executor:

            futures = [
                (
                    item,
                    executor.submit(
                        self.recent_tv_season,
                        item,
                        days,
                    ),
                )
                for item in series
            ]

            for item, future in futures:

                try:
                    result = future.result()

                    if result is not None:
                        recent_series.append(result)

                except TMDBError as exc:
                    errors.append({
                        "provider": "TMDB",
                        "media_type": "tv",
                        "error": str(exc),
                    })

        items = movies + recent_series

        sort_keys = {
            "newest": lambda x: x["release_date"],
            "rating": lambda x: x["tmdb_rating"] or 0,
            "popular": lambda x: x["popularity"],
        }

        items.sort(
            key=sort_keys[sort],
            reverse=True,
        )

        return {
            "region": REGION,
            "count": len(items),
            "source": "TMDB",
            "availability_source": "JustWatch",
            "date_type": "premiere",
            "truncated": truncated,
            "page_limit": page_limit,
            "max_pages": MAX_PAGES,
            "has_more": truncated and page_limit < MAX_PAGES,
            "errors": errors,
            "items": items,
        }

    def details(self, media_type, tmdb_id):

        def load():

            data = self.client.details(
                media_type, tmdb_id
            )

            availability = data.get(
                "watch/providers", {}
            ).get("results", {}).get(REGION, {})

            providers = [
                {
                    "id": p["provider_id"],
                    "name": PLATFORMS[p["provider_id"]],
                    "logo": self.client.poster_url(
                        p.get("logo_path"), "w92"
                    ),
                }
                for p in availability.get("flatrate", [])
                if p["provider_id"] in PLATFORMS
            ]

            return {
                "id": tmdb_id,
                "key": f"{media_type}:{tmdb_id}",
                "media_type": media_type,
                "release_date": (
                    data.get("release_date")
                    or data.get("first_air_date")
                    or ""
                ),
                "year": (
                    data.get("release_date")
                    or data.get("first_air_date")
                    or ""
                )[:4],
                "first_air_date": data.get(
                    "first_air_date"
                ),
                "backdrop": self.client.poster_url(
                    data.get("backdrop_path"), "w780"
                ),
                "genre_ids": [
                    genre["id"]
                    for genre in data.get("genres", [])
                ],
                "tmdb_votes": data.get("vote_count", 0),
                "popularity": data.get("popularity", 0),
                "title": data.get("title") or data.get("name"),
                "original_title": (
                    data.get("original_title")
                    or data.get("original_name")
                ),
                "overview": data.get("overview"),
                "poster": self.client.poster_url(
                    data.get("poster_path"), "w500"
                ),
                "imdb_id": data.get(
                    "external_ids", {}
                ).get("imdb_id"),
                "runtime": data.get("runtime"),
                "number_of_seasons": data.get(
                    "number_of_seasons"
                ),
                "number_of_episodes": data.get(
                    "number_of_episodes"
                ),
                "seasons": [
                    {
                        "number": s["season_number"],
                        "name": s["name"],
                        "episodes": s["episode_count"],
                        "air_date": s.get("air_date"),
                    }
                    for s in data.get("seasons", [])
                    if s["season_number"] > 0
                ],
                "providers": providers,
                "watch_url": availability.get("link"),
                "tmdb_rating": (
                    round(data["vote_average"] * 10, 1)
                    if data.get("vote_count")
                    else None
                ),
                "csfd_rating": None,
            }

        return self.cached(
            f"detail-v3:{REGION}:{media_type}:{tmdb_id}",
            load,
        )
