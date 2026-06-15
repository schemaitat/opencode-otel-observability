"""FastAPI application entry point for the Trace Explorer backend."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import tempo

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
    app.state.http_client = httpx.AsyncClient()
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
async def get_sessions(request: Request, time_range: _TimeRange = "24h") -> list[dict[str, Any]]:
    """Return per-session summaries filtered to the requested time range.

    Args:
        request: FastAPI request; used to access the shared HTTP client via
            ``request.app.state.http_client``.
        time_range: One of ``"1h"``, ``"6h"``, ``"24h"``, or ``"all"``,
            supplied as the ``range`` query parameter.

    Returns:
        A list of session summary dicts sorted by start time descending.
        See ``tempo.list_sessions`` for the full shape of each dict.
    """
    return await tempo.list_sessions(
        request.app.state.http_client,
        range_seconds=RANGE_SECONDS[time_range],
    )


@app.get("/api/overview")
async def get_overview(request: Request, time_range: _TimeRange = "24h") -> dict[str, Any]:
    """Return aggregated cost, token, model, agent, and tool usage.

    Args:
        request: FastAPI request; used to access the shared HTTP client via
            ``request.app.state.http_client``.
        time_range: One of ``"1h"``, ``"6h"``, ``"24h"``, or ``"all"``,
            supplied as the ``range`` query parameter.

    Returns:
        An overview dict with totals, per-model/agent/tool breakdowns, recent
        call lists, and time-series data. See ``tempo.get_overview`` for the
        full shape.
    """
    return await tempo.get_overview(
        request.app.state.http_client,
        range_seconds=RANGE_SECONDS[time_range],
    )


@app.get("/api/sessions/{session_id}/spans")
async def get_session_spans(request: Request, session_id: str) -> list[dict[str, Any]]:
    """Return all spans for a session in depth-first waterfall order.

    Args:
        request: FastAPI request; used to access the shared HTTP client via
            ``request.app.state.http_client``.
        session_id: The session ID whose spans should be fetched.

    Returns:
        An ordered list of span dicts, each containing ``trace_id``,
        ``span_id``, ``parent_span_id``, ``span_name``, ``start_ns``,
        ``duration_ms``, ``depth``, and ``attributes``.
    """
    return await tempo.get_session_spans(request.app.state.http_client, session_id)


STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
