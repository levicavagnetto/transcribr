# syntax=docker/dockerfile:1
# Transcribr: one image for the `web` and `worker` services (design D11).
# Targets: `runtime` (the default, last stage) and `test` (adds the test suite and dev tools).

ARG PYTHON_IMAGE=python:3.14-slim-trixie

# --- 1. The web app's static files -------------------------------------------------------
# The UI files and models are the same on every platform, so build them natively.
FROM --platform=$BUILDPLATFORM node:22-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- 2. The speech and speaker models, pinned and checked by SHA-256 ---------------------
# Only models.py feeds this stage, so code changes don't download the models again.
FROM --platform=$BUILDPLATFORM ${PYTHON_IMAGE} AS models
RUN pip install --no-cache-dir --root-user-action=ignore httpx==0.28.1
COPY backend/transcribr/models.py /opt/fetch/models.py
RUN python -c "import sys; from pathlib import Path; sys.path.insert(0, '/opt/fetch'); \
import models; models.fetch_models(Path('/models')); \
problems = models.verify_models(Path('/models')); sys.exit('; '.join(problems) or None)"

# --- 3. The backend's virtual environment ------------------------------------------------
FROM ${PYTHON_IMAGE} AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /src
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/transcribr ./transcribr
RUN uv sync --frozen --no-dev --no-editable

# --- 4. What both runtime and test images share ------------------------------------------
FROM ${PYTHON_IMAGE} AS base
RUN groupadd --gid 10001 transcribr \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent \
       --shell /usr/sbin/nologin transcribr \
    && mkdir /data && chown 10001:10001 /data
COPY --from=build /app/.venv /app/.venv
COPY --from=models /models /models
COPY --from=ui /ui/dist /app/ui
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    HF_HUB_OFFLINE=1 \
    ORT_DISABLE_TELEMETRY=1 \
    TRANSCRIBR_DATA_DIR=/data \
    TRANSCRIBR_MODELS_DIR=/models \
    TRANSCRIBR_UI_DIR=/app/ui
EXPOSE 8000

# --- test: the backend test suite, run inside the image (also serves the stack's fake Ravon)
FROM base AS test
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/transcribr ./transcribr
COPY backend/tests ./tests
RUN uv sync --frozen --no-editable && ln -s /models /app/models
USER 10001:10001
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-m", "not realsite and not slow"]

# --- runtime: the default image ----------------------------------------------------------
FROM base AS runtime
USER 10001:10001
WORKDIR /app
CMD ["transcribr", "web"]
