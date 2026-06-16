# Trace Explorer

[`trace-explorer/`](https://github.com/schemaitat/opencode-otel-observability/tree/main/trace-explorer)
is a React SPA backed by FastAPI (`trace-explorer` service, port `8060`).
It has two views, switchable from the header:

## Sessions

- Left sidebar with session list, sortable and searchable, with time-range filter (`1h`, `6h`, `24h`, `all`)
- Stat cards: LLM calls, tool calls, total cost, total tokens, duration
- Nested waterfall with depth-first span tree (Jaeger-style indentation)
- Subagent linking — `task` tool spans link to child session IDs via `parent_session_id`
- Right panel with per-span detail: collapsible JSON tree for attributes, formatted cost/token/duration values
- Live updates for in-progress sessions via SSE (`GET /api/sessions/{session_id}/spans/stream`):
    - `spans` — full span list; replace client state with this payload. Emitted when any
      `(span_id, duration_ms)` pair changes — covers both new spans arriving and the
      synthetic placeholder being replaced by the real root span on session close.
    - `heartbeat` — emitted each poll cycle when nothing has changed (keeps the connection alive through proxies)
    - `done` — emitted once the session closes; client should close the `EventSource`
    - `error` — emitted on a Tempo fetch failure; includes a `detail` field

### Open-session placeholder

OpenCode flushes the `opencode.session` root span to Tempo only when the session ends.
While the session is running, child spans (LLM calls, tool calls, agent spans) reference
the root span ID as their parent, but that parent is not yet in Tempo.

The backend detects these orphaned children and synthesises a placeholder root span so the
waterfall renders a properly nested tree instead of disconnected top-level entries:

| Placeholder field | Value |
|---|---|
| `span_id` | The actual `parentSpanId` referenced by the orphaned children — identical to the real root span's ID |
| `start_ns` | Earliest start time among orphaned children |
| `duration_ms` | From `start_ns` to the latest child end time; grows as new child spans arrive |
| `session.is_open` | `true` — signals the session is still running |

Because the placeholder and the real root share the same span ID, the placeholder is
**transparently replaced** when the real root arrives: it is no longer an orphan (its
parent ID is now in Tempo), so synthesis produces nothing and the real span takes its place.
The SSE fingerprints `(span_id, duration_ms)` — not just span IDs — so this replacement
always triggers a `spans` event and the client receives the correct final duration before
the `done` event fires.

The frontend renders open placeholders with a pulsing bar animation and a **Live** badge.

![Trace Explorer Sessions view](images/trace-explorer-sessions.png)

## Overview

A dashboard-style view aggregating cost, token, model, agent, and tool usage across all sessions
for the selected time range (`1h`, `6h`, `24h`, `all`) — computed directly from Tempo span
attributes:

- Summary cards: sessions, total cost, total tokens, LLM calls, tool calls
- Time series charts: cost by model, token usage by model, tool calls by tool
- Model usage table and cost-by-model bar chart
- Agent activity table and token-usage-by-agent bar chart
- Tool usage table and tool success-rate bar chart
- LLM calls table (prompt -> model -> outcome) and tool calls table (tool -> parameters -> result),
  each linking back to the originating session in the Sessions view

![Trace Explorer Overview view](images/trace-explorer-overview.png)

Connects to Tempo (`TEMPO_URL`, default `http://tempo:3200`).

## Configuration

| Variable | Default | Description |
|----------|---------|--------------|
| `TEMPO_URL` | `http://tempo:3200` | Backend: base URL of the Tempo HTTP API. |
| `CACHE_TTL_SECONDS` | `20` (set to `2` in `docker-compose.yml`) | Backend: how long fetched trace data is cached before re-querying Tempo. Lower values make the UI feel more "live" at the cost of more frequent Tempo queries. |
| `STREAM_POLL_SECONDS` | `0.5` | Backend: how often (seconds) the SSE stream polls Tempo for span changes. |
| `VITE_SESSIONS_POLL_MS` | `5000` (set to `2000`) | Frontend: poll interval for the session list. |
| `VITE_OVERVIEW_POLL_MS` | `10000` (set to `3000`) | Frontend: poll interval for the overview dashboard. |

The `VITE_*` variables are read at build time. They're set in `frontend/.env` for local dev/build and as Docker build args in `docker-compose.yml` for the containerized build.
