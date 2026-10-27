# syntax=docker/dockerfile:1
FROM node:24.22.1-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts ./
COPY frontend/src ./src
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.13.5 AS uv
FROM python:3.12.15-slim-bookworm AS dependencies
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12.15-slim-bookworm AS runtime
ARG SOURCE_REVISION=unreleased
ARG SOURCE_FINGERPRINT=unverified
LABEL org.opencontainers.image.source="https://github.com/fpinero/lab-chatbot" \
      org.opencontainers.image.revision=$SOURCE_REVISION \
      com.labchatbot.source-fingerprint=$SOURCE_FINGERPRINT
ENV PATH="/app/backend/.venv/bin:$PATH" \
    PYTHONPATH=/app/backend \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data
WORKDIR /app
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid 10001 --no-create-home app \
    && mkdir /data && chown 10001:10001 /data
COPY --from=dependencies /app/backend/.venv /app/backend/.venv
COPY backend/app /app/backend/app
COPY backend/migrations /app/backend/migrations
COPY --from=frontend /build/dist /app/frontend/dist
COPY scripts/backup-data.py /app/scripts/backup-data.py
USER 10001:10001
EXPOSE 8000
STOPSIGNAL SIGTERM
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers", "--no-access-log", "--log-level", "warning", "--timeout-graceful-shutdown", "30"]
