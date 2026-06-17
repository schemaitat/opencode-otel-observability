"""FastAPI backend for the Trace Explorer."""

import asyncio
import json
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

import tempo
from models import Overview, SessionSummary, Span

STREAM_POLL_SECONDS: float = float(os.environ.get("STREAM_POLL_SECONDS", "0.5"))

RANGE_SECONDS: dict[str, int | None] = {
    "1h": 3600,
    "6h": 6 * 3600,
    "24h": 24 * 3600,
    "all": None,
}

_TimeRange = Annotated[str, Query(alias="range", enum=list(RANGE_SECONDS))]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Keep a single shared httpx client alive for the server's lifetime."""
    app.state.http_client = httpx.AsyncClient(
        limits=httpx.Limits(keepalive_expiry=30),
    )
    try:
        yield
    finally:
        await app.state.http_client.aclose()


app = FastAPI(title="Trace Explorer", lifespan=lifespan)

# Local dev only — restrict to your origin if deployed behind a proxy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/sessions")
async def get_sessions(request: Request, time_range: _TimeRange = "24h") -> list[SessionSummary]:
    return await tempo.list_sessions(
        request.app.state.http_client,
        range_seconds=RANGE_SECONDS[time_range],
    )


@app.get("/api/overview")
async def get_overview(request: Request, time_range: _TimeRange = "24h") -> Overview:
    return await tempo.get_overview(
        request.app.state.http_client,
        range_seconds=RANGE_SECONDS[time_range],
    )


@app.get("/api/sessions/{session_id}/spans")
async def get_session_spans(request: Request, session_id: str) -> list[Span]:
    return await tempo.get_session_spans(request.app.state.http_client, session_id)


@app.get("/api/sessions/{session_id}/spans/stream")
async def stream_session_spans(request: Request, session_id: str) -> StreamingResponse:
    """Stream span updates as SSE.

    Events: ``spans`` (full span array), ``heartbeat`` (no change), ``done`` (session closed).
    Fingerprint includes duration_ms so the real root replacing the open-session placeholder
    triggers a ``spans`` event even though the span ID is unchanged.
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        client: httpx.AsyncClient = request.app.state.http_client
        last_fingerprint: frozenset[tuple[str, float]] = frozenset()
        error_count = 0

        while True:
            if await request.is_disconnected():
                break

            try:
                spans = await tempo.get_session_spans(client, session_id)
                error_count = 0
            except Exception as exc:  # noqa: BLE001
                error_count += 1
                backoff = min(2**error_count, 30)
                yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"
                await asyncio.sleep(backoff)
                continue

            current_fingerprint = frozenset((s.span_id, s.duration_ms) for s in spans)

            if current_fingerprint != last_fingerprint:
                last_fingerprint = current_fingerprint
                payload = json.dumps([s.model_dump() for s in spans])
                yield f"event: spans\ndata: {payload}\n\n"
            else:
                yield "event: heartbeat\ndata: {}\n\n"

            # session.is_open is set on the synthetic placeholder while the root
            # span hasn't been flushed to Tempo yet; stop streaming once it's gone.
            is_open = any(s.attributes.get("session.is_open") for s in spans)
            if not is_open and spans:
                yield "event: done\ndata: {}\n\n"
                break

            await asyncio.sleep(STREAM_POLL_SECONDS)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # prevent nginx buffering
        },
    )


STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
