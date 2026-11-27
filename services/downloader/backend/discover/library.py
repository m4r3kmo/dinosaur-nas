import json
import os
import urllib.request

from urllib.parse import urlencode

from jellyfin import JELLYFIN_URL
from fastshare import NoRedirect


class LibraryError(RuntimeError):
    pass


def jellyfin_get(path, **params):

    api_key = os.getenv("JELLYFIN_API_KEY")

    if not api_key:
        raise LibraryError("Jellyfin API key missing")

    url = f"{JELLYFIN_URL}/{path.lstrip('/')}"

    if params:
        url += "?" + urlencode(params)

    request = urllib.request.Request(
        url,
        headers={
            "Authorization": (
                f'MediaBrowser Token="{api_key}"'
            ),
            "Accept": "application/json",
        },
    )

    opener = urllib.request.build_opener(NoRedirect())

    try:
        with opener.open(request, timeout=10) as response:
            return json.load(response)

    except urllib.error.HTTPError as exc:
        raise LibraryError(
            f"Jellyfin HTTP error: {exc.code}"
        ) from None

    except (OSError, ValueError):
        raise LibraryError(
            "Jellyfin request failed"
        ) from None


def get_library_index():

    keys = set()

    movies = 0
    series = 0
    missing_ids = 0
    offset = 0
    limit = 500

    while True:

        data = jellyfin_get(
            "Items",
            Recursive="true",
            IncludeItemTypes="Movie,Series",
            Fields="ProviderIds",
            EnableImages="false",
            EnableUserData="false",
            StartIndex=offset,
            Limit=limit,
        )

        items = data.get("Items", [])

        for item in items:

            item_type = item.get("Type")

            if item_type == "Movie":
                kind = "movie"
                movies += 1

            elif item_type == "Series":
                kind = "tv"
                series += 1

            else:
                continue

            provider_ids = {
                key.lower(): value
                for key, value in (
                    item.get("ProviderIds") or {}
                ).items()
            }

            tmdb_id = provider_ids.get("tmdb")

            if not tmdb_id:
                missing_ids += 1
                continue

            keys.add(f"{kind}:{tmdb_id}")

        offset += len(items)

        total = data.get("TotalRecordCount")

        if not items:
            break

        if total is not None and offset >= total:
            break

        if len(items) < limit:
            break

    return {
        "keys": sorted(keys),
        "movies": movies,
        "series": series,
        "missing_tmdb_ids": missing_ids,
    }


def iter_library_items(item_type, **params):

    offset = 0
    limit = 500

    while True:

        data = jellyfin_get(
            "Items",
            Recursive="true",
            IncludeItemTypes=item_type,
            EnableImages="false",
            EnableUserData="false",
            StartIndex=offset,
            Limit=limit,
            **params,
        )

        items = data.get("Items", [])

        yield from items

        offset += len(items)
        total = data.get("TotalRecordCount")

        if not items or len(items) < limit:
            break

        if total is not None and offset >= total:
            break


def get_owned_episodes(tmdb_id):

    series_ids = set()
    owned = {}

    for item in iter_library_items(
        "Series",
        Fields="ProviderIds",
    ):

        provider_ids = {
            key.lower(): value
            for key, value in (
                item.get("ProviderIds") or {}
            ).items()
        }

        if str(provider_ids.get("tmdb")) == str(tmdb_id):
            if item.get("Id"):
                series_ids.add(item["Id"])

    if not series_ids:
        return {
            "matched": False,
            "owned": {},
        }

    for series_id in series_ids:

        for item in iter_library_items(
            "Episode",
            ParentId=series_id,
            IsMissing="false",
            IsPlaceHolder="false",
            ExcludeLocationTypes="Virtual",
        ):

            if item.get("SeriesId") != series_id:
                continue

            season = item.get("ParentIndexNumber")
            episode = item.get("IndexNumber")
            end = item.get("IndexNumberEnd") or episode

            if not isinstance(season, int) or season < 1:
                continue

            if not isinstance(episode, int) or episode < 1:
                continue

            if not isinstance(end, int) or end < episode:
                end = episode

            owned.setdefault(
                str(season), set()
            ).update(range(episode, end + 1))

    return {
        "matched": True,
        "owned": {
            season: sorted(episodes)
            for season, episodes in owned.items()
        },
    }
