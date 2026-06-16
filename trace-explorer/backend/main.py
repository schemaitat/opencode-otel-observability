"""FastAPI application entry point for the Trace Explorer backend."""

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

# How often (seconds) the SSE stream polls Tempo for span changes.
STREAM_POLL_SECONDS: float = float(os.environ.get("STREAM_POLL_SECONDS", "0.5"))

# Time-range options for the session list, in seconds. "all" means no limit.
RANGE_SECONDS: dict[str, int | None] = {
    "1h": 3600,
    "6h": 6 * 3600,
    "24h": 24 * 3600,
    "all": None,
}

# Reusable annotation for the `range` query parameter so it only needs to be
# declared once despite appearing on multiple routes.
_TimeRange = Annotated[str, Query(alias="range", enum=list(RANGE_SECONDS))]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage the lifetime of the shared HTTP client.

    Creates a single ``httpx.AsyncClient`` at startup and closes it on
    shutdown. Reusing the client across requests allows httpx to keep the TCP
    connection to Tempo alive, which significantly reduces per-request latency
    when the frontend polls frequently.

    Args:
        app: The FastAPI application instance. The client is stored as
            ``app.state.http_client`` for use in route handlers.

    Yields:
        Nothing; control is yielded to FastAPI while the server is running.
    """
    app.state.http_client = httpx.AsyncClient(
        limits=httpx.Limits(keepalive_expiry=30),
    )
    try:
        yield
    finally:
        await app.state.http_client.aclose()


app = FastAPI(title="Trace Explorer", lifespan=lifespan)

# Allow all origins. This service is intended for local development use only
# and is not designed to be exposed publicly without an authenticating reverse
# proxy. If you deploy it behind one, restrict this to your actual origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    """Return a static 200 response used by load balancers and readiness probes.

    Returns:
        A dict with a single ``status`` key set to ``"ok"``.
    """
    return {"status": "ok"}


@app.get("/api/sessions")
async def get_sessions(request: Request, time_range: _TimeRange = "24h") -> list[SessionSummary]:
    """Return per-session summaries filtered to the requested time range.

    Args:
        request: FastAPI request; used to access the shared HTTP client via
            ``request.app.state.http_client``.
        time_range: One of ``"1h"``, ``"6h"``, ``"24h"``, or ``"all"``,
            supplied as the ``range`` query parameter.

    Returns:
        A list of session summaries sorted by start time descending.
    """
    return await tempo.list_sessions(
        request.app.state.http_client,
        range_seconds=RANGE_SECONDS[time_range],
    )


@app.get("/api/overview")
async def get_overview(request: Request, time_range: _TimeRange = "24h") -> Overview:
    """Return aggregated cost, token, model, agent, and tool usage.

    Args:
        request: FastAPI request; used to access the shared HTTP client via
            ``request.app.state.http_client``.
        time_range: One of ``"1h"``, ``"6h"``, ``"24h"``, or ``"all"``,
            supplied as the ``range`` query parameter.

    Returns:
        An overview with totals, per-model/agent/tool breakdowns, recent
        call lists, and time-series data.
    """
    return await tempo.get_overview(
        request.app.state.http_client,
        range_seconds=RANGE_SECONDS[time_range],
    )


@app.get("/api/sessions/{session_id}/spans")
async def get_session_spans(request: Request, session_id: str) -> list[Span]:
    """Return all spans for a session in depth-first waterfall order.

    Args:
        request: FastAPI request; used to access the shared HTTP client via
            ``request.app.state.http_client``.
        session_id: The session ID whose spans should be fetched.

    Returns:
        An ordered list of spans in depth-first waterfall order.
    """
    return await tempo.get_session_spans(request.app.state.http_client, session_id)


@app.get("/api/sessions/{session_id}/spans/stream")
async def stream_session_spans(request: Request, session_id: str) -> StreamingResponse:
    """Stream span updates for a session as Server-Sent Events.

    Polls Tempo every ``STREAM_POLL_SECONDS`` (default 0.5 s) and pushes a
    ``spans`` event whenever the span set changes.  Change detection uses a
    ``(span_id, duration_ms)`` fingerprint rather than span IDs alone, so an
    update is also emitted when the synthetic open-session placeholder is
    replaced by the real root span (same ID, updated duration).  A
    ``heartbeat`` event is emitted each cycle when nothing has changed, which
    keeps the connection alive through proxies that close idle streams.  A
    ``done`` event is emitted once the session closes (its root span appears
    in Tempo, so the synthesised placeholder with ``session.is_open`` is no
    longer needed), after which the generator exits.

    SSE event types emitted:

    - ``spans``     – data is a JSON array of :class:`~models.Span` objects in
                      depth-first waterfall order.  Replace the client's full
                      span state with this payload.
    - ``heartbeat`` – data is ``{}``.  No state change needed.
    - ``done``      – data is ``{}``.  The session is closed; no further events
                      will arrive.  The client should close its ``EventSource``.

    Args:
        request: FastAPI request; used to access the shared HTTP client and to
            detect client disconnection via ``request.is_disconnected()``.
        session_id: The session whose span tree should be streamed.

    Returns:
        A ``StreamingResponse`` with ``Content-Type: text/event-stream``.
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        client: httpx.AsyncClient = request.app.state.http_client
        last_fingerprint: frozenset[tuple[str, float]] = frozenset()
        # Track consecutive fetch errors so we can back off without silently
        # spinning in a tight loop.
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

            # Include duration_ms in the fingerprint so that when the session
            # closes and the synthetic placeholder is replaced by the real root
            # span (same span ID, updated duration), we still emit a spans event.
            current_fingerprint = frozenset((s.span_id, s.duration_ms) for s in spans)

            if current_fingerprint != last_fingerprint:
                last_fingerprint = current_fingerprint
                payload = json.dumps([s.model_dump() for s in spans])
                yield f"event: spans\ndata: {payload}\n\n"
            else:
                yield "event: heartbeat\ndata: {}\n\n"

            # A session is open as long as its root span has not yet been
            # exported to Tempo.  The backend synthesises a placeholder root
            # span and marks it with session.is_open = True.  Once the real
            # root arrives the placeholder is dropped, is_open disappears, and
            # we can stop streaming.
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
            # Prevent nginx and other reverse proxies from buffering the
            # stream, which would delay events from reaching the browser.
            "X-Accel-Buffering": "no",
        },
    )


STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
