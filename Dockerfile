# GaitScan API. Build: docker build -t gaitscan-api .
# Run:   docker run -p 8000:8000 --env-file .env gaitscan-api
FROM python:3.11-slim

# mediapipe 0.10.9 pulls the non-headless opencv-contrib-python, which needs libGL/glib.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.11 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    MPLBACKEND=Agg \
    PYTHONUNBUFFERED=1

WORKDIR /app
# Dependencies first so code changes don't invalidate this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY alembic ./alembic
COPY gaitcore ./gaitcore
COPY app ./app

RUN useradd --create-home --uid 10001 app && mkdir -p data outputs && chown app:app data outputs
USER app

EXPOSE 8000
# Migrate before serving; a failed migration stops the deploy instead of serving a stale schema.
# --no-proxy-headers: uvicorn would trust the client-written leftmost X-Forwarded-For entry;
# app/core/ratelimit.py derives the client address itself (TRUSTED_PROXY_HOPS).
# One worker: in-process rate limits and the synchronous pipeline assume it (F13/F14, Phase 3).
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --no-proxy-headers"]
