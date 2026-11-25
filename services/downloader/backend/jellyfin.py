import os
import urllib.request

from getpass import getpass

from fastshare import NoRedirect


JELLYFIN_URL = os.getenv(
    "JELLYFIN_URL",
    "http://127.0.0.1:18096",
).rstrip("/")


def refresh_library(api_key=None):

    api_key = api_key or os.getenv("JELLYFIN_API_KEY")

    if not api_key:
        raise RuntimeError("Jellyfin API key missing")

    request = urllib.request.Request(
        f"{JELLYFIN_URL}/Library/Refresh",
        method="POST",
        headers={
            "Authorization": (
                f'MediaBrowser Token="{api_key}"'
            ),
        },
    )

    opener = urllib.request.build_opener(NoRedirect())

    with opener.open(request, timeout=30) as response:
        return response.status


if __name__ == "__main__":

    api_key = getpass("Jellyfin API key: ")

    try:
        status = refresh_library(api_key)

        print(f"HTTP status: {status}")
        print("Jellyfin library scan requested")

    except urllib.error.HTTPError as error:
        print(f"Jellyfin API error: HTTP {error.code}")

    except Exception as error:
        print(f"Operation failed: {type(error).__name__}")