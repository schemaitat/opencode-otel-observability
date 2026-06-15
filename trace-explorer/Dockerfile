FROM node:22.11.0-slim AS frontend-build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./

# Poll intervals are baked in at build time by Vite. Defaults are tuned for a
# "live" feel; override via --build-arg if needed.
ARG VITE_SESSIONS_POLL_MS=2000
ARG VITE_OVERVIEW_POLL_MS=3000
ARG VITE_SPANS_POLL_MS=1500
ENV VITE_SESSIONS_POLL_MS=$VITE_SESSIONS_POLL_MS \
    VITE_OVERVIEW_POLL_MS=$VITE_OVERVIEW_POLL_MS \
    VITE_SPANS_POLL_MS=$VITE_SPANS_POLL_MS

RUN npm run build

FROM python:3.12.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.16 /uv /usr/local/bin/uv

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --no-dev --no-cache

COPY backend/ ./
COPY --from=frontend-build /app/dist ./static

RUN useradd -M -s /sbin/nologin appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8060

CMD [".venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8060"]
