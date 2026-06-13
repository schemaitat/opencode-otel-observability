from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import tempo

# Time-range options for the session list, in seconds. "all" means no limit.
RANGE_SECONDS = {
    "1h": 3600,
    "6h": 6 * 3600,
    "24h": 24 * 3600,
    "all": None,
}

app = FastAPI(title="Trace Explorer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/sessions")
async def get_sessions(range: str = Query("24h", enum=list(RANGE_SECONDS))):
    return await tempo.list_sessions(range_seconds=RANGE_SECONDS[range])


@app.get("/api/sessions/{session_id}/spans")
async def get_session_spans(session_id: str):
    return await tempo.get_session_spans(session_id)


STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
