import os
from storage_config import storage_mounted
import re

from pathlib import Path

from jellyfin import refresh_library


VIDEO_EXTENSIONS = {
    ".mkv", ".mp4", ".avi", ".mov",
    ".m4v", ".webm", ".ts", ".m2ts",
    ".mpg", ".mpeg", ".wmv",
}


def validate_title(title):
    if not isinstance(title, str):
        raise ValueError("Media title required")

    title = title.strip()

    if (
        not title
        or title in (".", "..")
        or title.endswith(".")
        or len(title.encode("utf-8")) > 180
        or re.search(r'[<>:"/\\|?*\x00-\x1f]', title)
    ):
        raise ValueError("Invalid media title")

    return title


def normalize_series_title(title):
    title = validate_title(title)

    match = re.search(
        r"(?<![A-Za-z0-9])S\d{1,3}[\s._-]*E\d{1,3}(?!\d)",
        title,
        flags=re.IGNORECASE,
    )

    if match:
        title = title[:match.start()].rstrip(" ._-")

        if "." in title and not re.search(r"\s", title):
            title = title.replace(".", " ")

        title = re.sub(r"\s+", " ", title).strip()

    return validate_title(title)


def normalize_movie_title(title):
    title = validate_title(title)

    release = re.search(
        r"[ ._-]+(?:4320p|2160p|1080p|720p|480p|"
        r"UHD|Blu[ ._-]?Ray|WEB[ ._-]?(?:DL|Rip)|"
        r"HEVC|[hx][ ._-]?26[45])(?=$|[\s._()-])",
        title,
        flags=re.IGNORECASE,
    )

    if release:
        title = title[:release.start()].rstrip(" ._-")

        if "." in title and not re.search(r"\s", title):
            title = title.replace(".", " ")

    title = re.sub(
        r"(\((?:19|20)\d{2}\))\s*"
        r"\((?:CZ[- ._]?EN|CZ[- ._]?SK|CZ|EN|SK|"
        r"CZE|ENG|SVK)\)$",
        r"\1",
        title,
        flags=re.IGNORECASE,
    )

    return validate_title(title)


def series_key(title):
    match = re.search(r"\s*\(((?:19|20)\d{2})\)$", title)
    year = match.group(1) if match else None

    if match:
        title = title[:match.start()]

    key = re.sub(r"[ ._:-]+", " ", title.lower()).strip()

    return key, year


def resolve_series_title(title, series_root):
    if series_root is None:
        return title

    root = Path(series_root)

    if not root.is_dir():
        return title

    names = [
        entry.name
        for entry in root.iterdir()
        if entry.is_dir()
        and not entry.is_symlink()
        and not entry.name.startswith(".")
    ]

    if title in names:
        return title

    key, year = series_key(title)
    matches = []

    for name in names:
        existing_key, existing_year = series_key(name)

        if key != existing_key:
            continue

        if year and existing_year and year != existing_year:
            continue

        matches.append(name)

    if len(matches) > 1:
        raise ValueError(
            "Multiple matching TV shows. Select an existing series."
        )

    return matches[0] if matches else title


def build_destination(
    filename,
    library="downloads",
    title=None,
    season=None,
    episode=None,
    series_root=None,
):
    if library == "downloads":
        return None

    extension = Path(filename).suffix.lower()

    if extension not in VIDEO_EXTENSIONS:
        raise ValueError("Unsupported video extension")

    title = validate_title(title)

    if library == "movies":
        title = normalize_movie_title(title)
        return str(
            Path("movies") / title / f"{title}{extension}"
        )

    if library == "series":
        title = normalize_series_title(title)
        title = validate_title(
            resolve_series_title(title, series_root)
        )

        if (
            season is None
            or episode is None
            or not 0 <= season <= 999
            or not 1 <= episode <= 999
        ):
            raise ValueError("Invalid season or episode")

        return str(
            Path("series")
            / title
            / f"Season {season:02d}"
            / f"{title} S{season:02d}E{episode:02d}{extension}"
        )

    raise ValueError("Unknown library")


def migrate(db):
    columns = {
        row["name"]
        for row in db.execute(
            "PRAGMA table_info(downloads)"
        )
    }

    migrations = {
        "destination": "TEXT",
        "import_status": "TEXT DEFAULT 'not_requested'",
        "import_error": "TEXT",
    }

    for name, definition in migrations.items():
        if name not in columns:
            db.execute(
                f"ALTER TABLE downloads "
                f"ADD COLUMN {name} {definition}"
            )


def set_import_status(
    database, job_id, status, error=None
):
    with database() as db:
        db.execute("""
            UPDATE downloads
            SET import_status = ?, import_error = ?
            WHERE id = ?
        """, (status, error, job_id))


def process_import(database, download_dir):

    with database() as db:
        row = db.execute("""
            SELECT *
            FROM downloads
            WHERE status = 'completed'
              AND import_status IN (
                  'pending', 'scan_pending'
              )
            ORDER BY created_at ASC
            LIMIT 1
        """).fetchone()

    if not row:
        return

    job = dict(row)

    try:
        if not storage_mounted():
            raise RuntimeError("NAS storage unavailable")

        media_root = download_dir.parent.resolve()

        source = (
            download_dir
            / job["id"]
            / job["filename"]
        )

        relative = Path(job["destination"])

        if (
            relative.is_absolute()
            or ".." in relative.parts
            or relative.parts[0] not in ("movies", "series")
        ):
            raise RuntimeError("Invalid destination")

        destination = media_root / relative

        if not destination.resolve().is_relative_to(
            media_root
        ):
            raise RuntimeError("Unsafe destination")

        if job["import_status"] == "pending":

            if source.is_symlink() or not source.is_file():
                raise RuntimeError("Source file unavailable")

            if source.stat().st_size != job["size"]:
                raise RuntimeError("Source size mismatch")

            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            if destination.exists() or destination.is_symlink():
                raise FileExistsError(
                    "Destination already exists"
                )

            # Publish without overwriting existing media.
            os.link(source, destination)

            set_import_status(
                database,
                job["id"],
                "scan_pending",
            )

            # Remove original download after publication.
            try:
                source.unlink()
            except OSError:
                print(
                    "Import cleanup required:",
                    job["id"],
                )

            print("Media imported:", job["id"])

    except Exception as error:

        set_import_status(
            database,
            job["id"],
            "failed",
            type(error).__name__,
        )

        return

    try:
        refresh_library()

        set_import_status(
            database,
            job["id"],
            "imported",
        )

        print("Jellyfin refresh requested:", job["id"])

    except Exception as error:

        set_import_status(
            database,
            job["id"],
            "scan_failed",
            type(error).__name__,
        )