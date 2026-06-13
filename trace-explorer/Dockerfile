FROM node:22-slim AS frontend-build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync

COPY backend/main.py backend/tempo.py ./
COPY --from=frontend-build /app/dist ./static

EXPOSE 8060

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8060"]
