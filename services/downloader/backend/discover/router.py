from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from .catalog import DiscoverCatalog, PLATFORMS, DEFAULT_PAGES, MAX_PAGES
from .tmdb import TMDBError


router = APIRouter(
    prefix="/api/discover",
    tags=["discover"],
)


@router.get("/providers")
def get_providers():

    try:
        catalog = DiscoverCatalog()

        return {
            "region": "SK",
            "movie": catalog.providers("movie"),
            "tv": catalog.providers("tv"),
        }

    except TMDBError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from None


@router.get("/releases")
def get_releases(
    media_type: Literal["all", "movie", "tv"] = "all",
    provider_id: int = Query(default=0, ge=0),
    days: int = Query(default=30, ge=7, le=90),
    min_rating: int = Query(default=70, ge=0, le=100),
    min_votes: int = Query(default=5, ge=0, le=1000),
    sort: Literal["newest", "rating", "popular"] = "newest",
    page_limit: int = Query(
        default=DEFAULT_PAGES,
        ge=DEFAULT_PAGES,
        le=MAX_PAGES,
    ),
):

    if days not in (7, 14, 30, 90):
        raise HTTPException(
            status_code=400,
            detail="Unsupported release period",
        )

    if provider_id and provider_id not in PLATFORMS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported streaming platform",
        )

    try:

        return DiscoverCatalog().releases(
            media_type=media_type,
            provider_id=provider_id,
            days=days,
            min_rating=min_rating,
            min_votes=min_votes,
            sort=sort,
            page_limit=page_limit,
        )

    except TMDBError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from None


@router.get("/details/{media_type}/{tmdb_id}")
def get_details(
    media_type: Literal["movie", "tv"],
    tmdb_id: int,
):

    if tmdb_id < 1:
        raise HTTPException(
            status_code=400,
            detail="Invalid TMDB ID",
        )

    try:
        return DiscoverCatalog().details(
            media_type, tmdb_id
        )

    except TMDBError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from None


@router.get("/library")
def get_library():

    from .library import (
        get_library_index,
        LibraryError,
    )

    try:
        return get_library_index()

    except LibraryError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from None


@router.get("/library/series/{tmdb_id}")
def get_series_library_status(tmdb_id: int):

    from .series import get_series_status
    from .library import LibraryError

    if tmdb_id < 1:
        raise HTTPException(
            status_code=400,
            detail="Invalid TMDB ID",
        )

    try:
        return get_series_status(tmdb_id)

    except (LibraryError, TMDBError) as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from None


@router.get("/streaming/status")
def streaming_status():

    import sqlite3

    from .streaming import get_streaming_status

    try:
        return get_streaming_status()

    except (sqlite3.Error, OSError):
        raise HTTPException(
            status_code=503,
            detail="Streaming database unavailable",
        ) from None


@router.get("/streaming/additions")
def streaming_additions(
    media_type: Literal["all", "movie", "tv"] = "all",
    provider_id: int = Query(default=0, ge=0),
    days: int = Query(default=30, ge=7, le=90),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):

    import sqlite3

    from .streaming import get_streaming_additions

    if provider_id and provider_id not in PLATFORMS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported streaming platform",
        )

    try:

        return get_streaming_additions(
            media_type=media_type,
            provider_id=provider_id,
            days=days,
            limit=limit,
            offset=offset,
        )

    except (sqlite3.Error, OSError, TMDBError):
        raise HTTPException(
            status_code=503,
            detail="Streaming catalog unavailable",
        ) from None


@router.get("/streaming/metrics")
def streaming_metrics():

    import sqlite3

    from fastapi.responses import PlainTextResponse
    from .metrics import get_streaming_metrics

    try:

        return PlainTextResponse(
            content=get_streaming_metrics(),
            media_type="text/plain; version=0.0.4",
        )

    except (sqlite3.Error, OSError, ValueError):
        raise HTTPException(
            status_code=503,
            detail="Streaming metrics unavailable",
        ) from None
