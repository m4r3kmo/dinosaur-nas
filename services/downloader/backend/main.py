import os
import shutil
import sqlite3
import threading

from pathlib import Path
from typing import Literal
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from fastshare import FastShareClient
from media_import import build_destination
from storage_config import storage_mounted

from download_queue import (
    initialize,
    enqueue,
    list_downloads,
    worker,
    import_worker,
    database,
    STOP_EVENT,
    DOWNLOAD_DIR,
)


APP_VERSION = "0.5.3"


# ==========================================
# Application lifecycle
# ==========================================

@asynccontextmanager
async def lifespan(app):

    required_env = (
        "FASTSHARE_USERNAME",
        "FASTSHARE_PASSWORD",
        "JELLYFIN_API_KEY",
    )

    for variable in required_env:
        if not os.getenv(variable):
            raise RuntimeError(
                f"Missing environment variable: {variable}"
            )

    initialize()

    STOP_EVENT.clear()

    parallel = int(os.getenv("DOWNLOAD_WORKERS", "1"))

    if not 1 <= parallel <= 8:
        raise RuntimeError("DOWNLOAD_WORKERS must be between 1 and 8")

    workers = [
        threading.Thread(
            target=worker,
            name=f"download-worker-{index + 1}",
            daemon=True,
        )
        for index in range(parallel)
    ]

    workers.append(
        threading.Thread(
            target=import_worker,
            name="media-import-worker",
            daemon=True,
        )
    )

    app.state.workers = workers

    for thread in workers:
        thread.start()

    try:
        yield
    finally:
        STOP_EVENT.set()

        for thread in workers:
            thread.join(timeout=2)


app = FastAPI(
    title="Dinosaur Downloader",
    description="Dinosaur NAS Download Manager",
    version=APP_VERSION,
    lifespan=lifespan,
)


# ==========================================
# Request models
# ==========================================

class ImportRequest(BaseModel):

    library: Literal[
        "movies", "series", "downloads"
    ] = "downloads"

    title: str | None = Field(
        default=None,
        max_length=180,
    )

    season: int | None = Field(
        default=None,
        ge=0,
        le=999,
    )

    episode: int | None = Field(
        default=None,
        ge=1,
        le=999,
    )


class DownloadRequest(ImportRequest):

    query: str = Field(
        min_length=2,
        max_length=200,
    )

    file_id: str = Field(
        min_length=1,
        max_length=64,
    )


# ==========================================
# Health check
# ==========================================

@app.get("/api/health")
def health():

    workers = getattr(app.state, "workers", [])

    if not workers or not all(t.is_alive() for t in workers):
        raise HTTPException(
            status_code=503,
            detail="Downloader worker unavailable",
        )

    return {
        "status": "healthy",
        "service": "dinosaur-downloader",
        "version": APP_VERSION,
    }


# ==========================================
# FastShare search
# ==========================================

@app.get("/api/search")
def search(
    query: str = Query(
        min_length=2,
        max_length=200,
    )
):

    try:
        client = FastShareClient()

        results = client.search(
            query,
            pagination=100,
        )

        return {
            "query": query,
            "total": len(results),
            "results": [
                {
                    "id": str(item.get("id")),
                    "filename": item.get("filename"),
                    "resolution": item.get("resolution"),
                    "size": int(
                        item.get("data", {}).get("value") or 0
                    ),
                    "duration": item.get("duration_f"),
                    "thumbnail": item.get("thumbnail"),
                }
                for item in results
            ],
        }

    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Remote search service unavailable",
        )


# ==========================================
# Download queue
# ==========================================

@app.post("/api/downloads", status_code=202)
def create_download(request: DownloadRequest):

    if not storage_mounted():
        raise HTTPException(
            status_code=503,
            detail="NAS storage unavailable",
        )

    try:
        client = FastShareClient()

        results = client.search(
            request.query,
            pagination=100,
        )

    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Remote search service unavailable",
        )

    item = next(
        (
            entry for entry in results
            if str(entry.get("id")) == request.file_id
        ),
        None,
    )

    if not item:
        raise HTTPException(
            status_code=404,
            detail="File not found",
        )

    try:
        destination = build_destination(
            filename=item["filename"],
            library=request.library,
            title=request.title,
            season=request.season,
            episode=request.episode,
        )

        job_id = enqueue(
            item,
            destination,
        )

        return {
            "id": job_id,
            "status": "queued",
            "destination": destination,
            "import_status": (
                "pending"
                if destination
                else "not_requested"
            ),
        }

    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="File already in download queue",
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@app.get("/api/downloads")
def downloads():

    return list_downloads()


# ==========================================
# Transfer history management
# ==========================================

@app.delete("/api/downloads/history")
def clear_download_history():

    with database() as db:
        db.execute("BEGIN IMMEDIATE")

        result = db.execute("""
            DELETE FROM downloads
            WHERE status IN ('failed', 'interrupted')
               OR (
                   status = 'completed'
                   AND import_status = 'imported'
               )
        """)

        deleted = result.rowcount

    return {"deleted": deleted}


@app.delete("/api/downloads/{job_id}")
def delete_download_history(job_id: str):

    with database() as db:
        db.execute("BEGIN IMMEDIATE")

        job = db.execute("""
            SELECT status, import_status
            FROM downloads
            WHERE id = ?
        """, (job_id,)).fetchone()

        if not job:
            raise HTTPException(
                status_code=404,
                detail="Transfer not found",
            )

        removable = (
            job["status"] in ("failed", "interrupted")
            or (
                job["status"] == "completed"
                and job["import_status"] in (
                    "imported", "not_requested"
                )
            )
        )

        if not removable:
            raise HTTPException(
                status_code=409,
                detail="Transfer or media import is still pending",
            )

        db.execute("""
            DELETE FROM downloads
            WHERE id = ?
        """, (job_id,))

    return {"deleted": 1, "id": job_id}


# ==========================================
# Jellyfin media import
# ==========================================

@app.post(
    "/api/downloads/{job_id}/import",
    status_code=202,
)
def import_download(
    job_id: str,
    request: ImportRequest,
):

    if not storage_mounted():
        raise HTTPException(
            status_code=503,
            detail="NAS storage unavailable",
        )

    with database() as db:

        db.execute("BEGIN IMMEDIATE")

        job = db.execute("""
            SELECT *
            FROM downloads
            WHERE id = ?
        """, (job_id,)).fetchone()

        if not job:
            raise HTTPException(
                status_code=404,
                detail="Download not found",
            )

        if (
            job["status"] != "completed"
            or job["import_status"] != "not_requested"
        ):
            raise HTTPException(
                status_code=409,
                detail="Download is not ready for import",
            )

        try:
            destination = build_destination(
                filename=job["filename"],
                library=request.library,
                title=request.title,
                season=request.season,
                episode=request.episode,
            )

            if not destination:
                raise ValueError(
                    "Select a media library"
                )

        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail=str(error),
            )

        db.execute("""
            UPDATE downloads
            SET destination = ?,
                import_status = 'pending',
                import_error = NULL
            WHERE id = ?
        """, (
            destination,
            job_id,
        ))

    return {
        "id": job_id,
        "destination": destination,
        "import_status": "pending",
    }


# ==========================================
# NAS storage
# ==========================================

@app.get("/api/storage")
def storage():

    if not storage_mounted():
        raise HTTPException(
            status_code=503,
            detail="NAS storage unavailable",
        )

    usage = shutil.disk_usage(DOWNLOAD_DIR)

    return {
        "total": usage.total,
        "used": usage.used,
        "free": usage.free,
    }


# ==========================================
# Production React frontend
# ==========================================

static_dir = os.getenv("DOWNLOADER_STATIC_DIR")

if static_dir:

    frontend_path = Path(static_dir)

    if not frontend_path.is_dir():
        raise RuntimeError(
            f"Frontend directory not found: {frontend_path}"
        )

    if not (frontend_path / "index.html").is_file():
        raise RuntimeError(
            f"Frontend index.html not found: {frontend_path}"
        )

    app.mount(
        "/",
        StaticFiles(
            directory=frontend_path,
            html=True,
        ),
        name="frontend",
    )