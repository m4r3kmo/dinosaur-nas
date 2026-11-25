# ==========================================
# Stage 1: React frontend build
# ==========================================

FROM docker.io/library/node:22-bookworm-slim AS frontend

WORKDIR /build

COPY frontend/package.json frontend/package-lock.json ./

RUN npm ci

COPY frontend/index.html ./
COPY frontend/tsconfig.json ./
COPY frontend/vite.config.ts ./
COPY frontend/src/ ./src/

RUN npm run build


# ==========================================
# Stage 2: Python production runtime
# ==========================================

FROM docker.io/library/python:3.13-slim-bookworm

LABEL org.opencontainers.image.title="Dinosaur Downloader"
LABEL org.opencontainers.image.version="0.3.0"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Europe/Bratislava \
    DOWNLOADER_STATE_DIR=/state \
    DOWNLOADER_STATIC_DIR=/app/frontend \
    NAS_MOUNT_PATH=/mnt/storage/media

WORKDIR /app/backend

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 downloader \
    && useradd --uid 1000 \
        --gid 1000 \
        --create-home \
        downloader

COPY backend/requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY backend/main.py ./
COPY backend/fastshare.py ./
COPY backend/download.py ./
COPY backend/download_queue.py ./
COPY backend/jellyfin.py ./
COPY backend/media_import.py ./
COPY backend/storage_config.py ./

COPY --from=frontend /build/dist /app/frontend

RUN mkdir -p /state /mnt/storage/media \
    && chown -R 1000:1000 /app /state

USER 1000:1000

EXPOSE 8085

CMD ["python", "-m", "uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8085", \
     "--workers", "1"]