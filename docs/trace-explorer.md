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
- Handles in-progress sessions by synthesising a placeholder root span

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
| `VITE_SESSIONS_POLL_MS` | `5000` (set to `2000`) | Frontend: poll interval for the session list. |
| `VITE_OVERVIEW_POLL_MS` | `10000` (set to `3000`) | Frontend: poll interval for the overview dashboard. |
| `VITE_SPANS_POLL_MS` | `4000` (set to `1500`) | Frontend: poll interval for the selected session's span waterfall. |

The `VITE_*` variables are read at build time. They're set in `frontend/.env` for local dev/build and as Docker build args in `docker-compose.yml` for the containerized build.
