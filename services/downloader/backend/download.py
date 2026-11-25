import os
import re
import shutil
import time
import urllib.parse
import urllib.request

from pathlib import Path
from getpass import getpass

from fastshare import FastShareClient


DOWNLOAD_DIR = Path("/mnt/storage/media/downloads")
CHUNK_SIZE = 1024 * 1024


def download_file(client, item, destination):

    if not client.token:
        raise RuntimeError("Authentication required")

    filename = item["filename"]
    expected_size = int(item["data"]["value"])
    url = item["download_url"]

    if (
        filename in ("", ".", "..")
        or "/" in filename
        or "\\" in filename
        or "\x00" in filename
    ):
        raise RuntimeError("Invalid filename")

    parsed = urllib.parse.urlsplit(url)

    if (
        parsed.scheme != "https"
        or not re.fullmatch(
            r"data[0-9]+\.fastshare\.cloud",
            parsed.hostname or "",
        )
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.path != "/download.php"
    ):
        raise RuntimeError("Unexpected download URL")

    if any(c in client.token for c in ';\r\n \t,"\\'):
        raise RuntimeError("Invalid authentication token")

    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)

    target = destination / filename
    partial = destination / f"{filename}.part"

    if target.exists() or partial.exists():
        raise RuntimeError("File already exists")

    if shutil.disk_usage(destination).free < expected_size:
        raise RuntimeError("Not enough free disk space")

    request = urllib.request.Request(
        url,
        headers={
            "Cookie": f"FASTSHARE={client.token}",
            "Accept-Encoding": "identity",
        },
    )

    downloaded = 0
    started = time.monotonic()
    last_update = started

    print(f"Downloading: {filename}")
    print(f"Size: {expected_size / 1024**3:.2f} GiB")

    with client.opener.open(request, timeout=60) as response:

        if response.status != 200:
            raise RuntimeError("Unexpected HTTP status")

        content_type = response.headers.get("Content-Type", "")

        if content_type.lower().startswith(
            ("text/", "application/json")
        ):
            raise RuntimeError("Unexpected response type")

        content_length = response.headers.get("Content-Length")

        if content_length and int(content_length) != expected_size:
            raise RuntimeError("Unexpected file size")

        with partial.open("xb") as output:

            while True:
                chunk = response.read(CHUNK_SIZE)

                if not chunk:
                    break

                if downloaded + len(chunk) > expected_size:
                    raise RuntimeError("File exceeds expected size")

                output.write(chunk)
                downloaded += len(chunk)

                now = time.monotonic()
                elapsed = now - started

                if now - last_update >= 2:
                    speed = downloaded / max(elapsed, 0.001)
                    percent = downloaded / expected_size * 100
                    remaining = (expected_size - downloaded) / speed

                    print(
                        f"\r{percent:6.2f}% | "
                        f"{speed / 1024**2:.2f} MiB/s | "
                        f"ETA: {remaining:.0f}s",
                        end="",
                        flush=True,
                    )

                    last_update = now

            output.flush()
            os.fsync(output.fileno())

    if downloaded != expected_size:
        raise RuntimeError("Incomplete download")

    # Publish completed file without overwriting an existing file.
    os.link(partial, target)
    partial.unlink()

    elapsed = time.monotonic() - started

    print("\nDownload completed successfully")
    print(f"File: {target}")
    print(f"Duration: {elapsed:.1f}s")

    return target


if __name__ == "__main__":

    client = FastShareClient()

    try:
        username = input("FastShare username: ")
        password = getpass("FastShare password: ")

        client.login(username, password)
        del password

        results = client.search("Big Buck Bunny")

        item = next(
            (
                entry for entry in results
                if entry.get("id") == "8066239"
            ),
            None,
        )

        if not item:
            raise RuntimeError("Test file not found")

        download_file(client, item, DOWNLOAD_DIR)

    except KeyboardInterrupt:
        print("\nDownload interrupted")
        raise SystemExit(1)

    except Exception as error:
        print(f"\nDownload failed: {type(error).__name__}")
        raise SystemExit(1)