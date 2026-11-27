import json
import os

from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p"


class TMDBError(RuntimeError):
    pass


class TMDBClient:

    def __init__(self):
        self.token = os.getenv(
            "TMDB_ACCESS_TOKEN", ""
        ).strip()

        if not self.token:
            raise TMDBError(
                "TMDB_ACCESS_TOKEN is not configured"
            )

    def get(self, path: str, **params) -> dict:

        url = f"{TMDB_BASE_URL}/{path.lstrip('/')}"

        if params:
            url += "?" + urlencode(params)

        request = Request(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "User-Agent": "DinosaurDiscover/0.6.0",
            },
        )

        try:
            with urlopen(request, timeout=15) as response:
                return json.load(response)

        except HTTPError as exc:
            raise TMDBError(
                f"TMDB HTTP error: {exc.code}"
            ) from None

        except (URLError, TimeoutError):
            raise TMDBError(
                "TMDB connection failed"
            ) from None

    def providers(self, media_type: str, region="SK"):

        if media_type not in ("movie", "tv"):
            raise ValueError("Invalid media type")

        return self.get(
            f"watch/providers/{media_type}",
            watch_region=region,
            language="en-US",
        ).get("results", [])

    def discover(self, media_type: str, **filters):

        if media_type not in ("movie", "tv"):
            raise ValueError("Invalid media type")

        params = {
            "language": "en-US",
            "watch_region": "SK",
            "include_adult": "false",
            "with_watch_monetization_types": "flatrate",
            **filters,
        }

        return self.get(
            f"discover/{media_type}",
            **params,
        )

    def details(self, media_type: str, tmdb_id: int):

        if media_type not in ("movie", "tv"):
            raise ValueError("Invalid media type")

        return self.get(
            f"{media_type}/{int(tmdb_id)}",
            language="en-US",
            append_to_response=(
                "external_ids,watch/providers"
            ),
        )

    @staticmethod
    def poster_url(path, size="w342"):

        if not path:
            return None

        return f"{TMDB_IMAGE_URL}/{size}{path}"
