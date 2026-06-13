FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml .
RUN uv sync

COPY app.py tempo_client.py narrative.py ./
COPY assets ./assets

EXPOSE 8050

CMD ["uv", "run", "python", "app.py"]
