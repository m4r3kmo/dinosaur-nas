import os
import uuid
import sqlite3
import threading

from pathlib import Path
from contextlib import contextmanager

from fastshare import FastShareClient
from download import download_file


STATE_DIR = Path(__file__).parent / ".state"
DOWNLOAD_DIR = Path("/mnt/storage/media/downloads")
DB_PATH = STATE_DIR / "downloads.db"

STOP_EVENT = threading.Event()


@contextmanager
def database():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize():
    if not os.path.ismount("/mnt/storage"):
        raise RuntimeError("NAS storage is not mounted")

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    with database() as db:
        db.execute("PRAGMA journal_mode=WAL")

        db.execute("""
            CREATE TABLE IF NOT EXISTS downloads (
                id TEXT PRIMARY KEY,
                source_id TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                download_url TEXT NOT NULL,
                size INTEGER NOT NULL,
                status TEXT DEFAULT 'queued',
                error TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        db.execute("""
            UPDATE downloads
            SET status = 'queued'
            WHERE status = 'running'
        """)


def enqueue(item):
    filename = item["filename"]
    size = int(item["data"]["value"])

    if (
        filename in ("", ".", "..")
        or "/" in filename
        or "\\" in filename
        or any(ord(c) < 32 for c in filename)
        or size <= 0
    ):
        raise ValueError("Invalid file information")

    job_id = uuid.uuid4().hex

    with database() as db:
        db.execute("""
            INSERT INTO downloads (
                id, source_id, filename,
                download_url, size
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            job_id,
            str(item["id"]),
            filename,
            item["download_url"],
            size,
        ))

    return job_id


def set_status(job_id, status, error=None):
    with database() as db:
        db.execute("""
            UPDATE downloads
            SET status = ?, error = ?
            WHERE id = ?
        """, (status, error, job_id))


def list_downloads():
    with database() as db:
        rows = db.execute("""
            SELECT id, source_id, filename,
                   size, status, error, created_at
            FROM downloads
            ORDER BY created_at DESC
        """).fetchall()

    results = []

    for row in rows:
        job = dict(row)

        folder = DOWNLOAD_DIR / job["id"]
        target = folder / job["filename"]
        partial = folder / (job["filename"] + ".part")

        downloaded = 0

        for path in (target, partial):
            try:
                downloaded = path.stat().st_size
                break
            except FileNotFoundError:
                continue

        job["downloaded"] = downloaded
        job["progress"] = round(
            downloaded / job["size"] * 100, 2
        )

        results.append(job)

    return results


def worker():
    while not STOP_EVENT.is_set():

        with database() as db:
            db.execute("BEGIN IMMEDIATE")

            row = db.execute("""
                SELECT *
                FROM downloads
                WHERE status = 'queued'
                ORDER BY created_at ASC
                LIMIT 1
            """).fetchone()

            if row:
                job = dict(row)

                db.execute("""
                    UPDATE downloads
                    SET status = 'running'
                    WHERE id = ?
                """, (job["id"],))

        if not row:
            STOP_EVENT.wait(2)
            continue

        try:
            if not os.path.ismount("/mnt/storage"):
                raise RuntimeError("Storage unavailable")

            destination = DOWNLOAD_DIR / job["id"]

            target = destination / job["filename"]
            partial = destination / (job["filename"] + ".part")

            if target.exists():
                if target.stat().st_size == job["size"]:
                    set_status(job["id"], "completed")
                else:
                    set_status(job["id"], "failed",
                               "File size mismatch")
                continue

            if partial.exists():
                set_status(
                    job["id"],
                    "interrupted",
                    "Partial download preserved",
                )
                continue

            client = FastShareClient()

            client.login(
                os.environ["FASTSHARE_USERNAME"],
                os.environ["FASTSHARE_PASSWORD"],
            )

            item = {
                "filename": job["filename"],
                "download_url": job["download_url"],
                "data": {
                    "value": job["size"]
                },
            }

            download_file(client, item, destination)

            set_status(job["id"], "completed")

        except Exception as error:
            set_status(
                job["id"],
                "failed",
                type(error).__name__,
            )