import os
import shutil
import sqlite3
import threading

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from fastshare import FastShareClient

from download_queue import (
    initialize,
    enqueue,
    list_downloads,
    worker,
    STOP_EVENT,
    DOWNLOAD_DIR,
)


@asynccontextmanager
async def lifespan(app):

    if not (
        os.getenv("FASTSHARE_USERNAME")
        and os.getenv("FASTSHARE_PASSWORD")
    ):
        raise RuntimeError("FastShare credentials missing")

    initialize()

    STOP_EVENT.clear()

    thread = threading.Thread(
        target=worker,
        daemon=True,
    )

    thread.start()

    try:
        yield
    finally:
        STOP_EVENT.set()
        thread.join(timeout=5)


app = FastAPI(
    title="Dinosaur Downloader",
    description="Dinosaur NAS Download Manager",
    version="0.2.0",
    lifespan=lifespan,
)


class DownloadRequest(BaseModel):
    query: str = Field(min_length=2, max_length=200)
    file_id: str = Field(min_length=1, max_length=64)


@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "service": "dinosaur-downloader",
        "version": "0.2.0",
    }


@app.get("/api/search")
def search(query: str = Query(min_length=2, max_length=200)):

    try:
        client = FastShareClient()
        results = client.search(query, pagination=100)

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
            detail="FastShare search failed",
        )


@app.post("/api/downloads", status_code=202)
def create_download(request: DownloadRequest):

    try:
        client = FastShareClient()

        results = client.search(
            request.query,
            pagination=100,
        )

    except Exception:
        raise HTTPException(
            status_code=502,
            detail="FastShare search failed",
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
        job_id = enqueue(item)

        return {
            "id": job_id,
            "status": "queued",
        }

    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="File already in download queue",
        )

    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid file information",
        )


@app.get("/api/downloads")
def downloads():
    return list_downloads()


@app.get("/api/storage")
def storage():
    usage = shutil.disk_usage(DOWNLOAD_DIR)

    return {
        "total": usage.total,
        "used": usage.used,
        "free": usage.free,
    }