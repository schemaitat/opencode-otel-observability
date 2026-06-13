import asyncio
import base64
import os
import time

import httpx

TEMPO_URL = os.environ.get("TEMPO_URL", "http://tempo:3200")

SUMMARY_ATTRS = [
    ".session.id",
    ".cost_usd",
    ".llm.token_count.total",
    ".llm.model_name",
    ".agent.name",
    ".tool.name",
]


def _attr_value(value: dict):
    for key in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if key in value:
            v = value[key]
            if key == "intValue":
                return int(v)
            if key == "doubleValue":
                return float(v)
            return v
    return None


def _span_attrs(span: dict) -> dict:
    return {a["key"]: _attr_value(a["value"]) for a in span.get("attributes", [])}


def _to_hex(span_id: str | None) -> str | None:
    """Convert an OTLP JSON span/parent-span ID (base64) to hex, matching Grafana's Tempo UI."""
    if not span_id:
        return span_id
    try:
        return base64.b64decode(span_id).hex()
    except Exception:
        return span_id


async def _search(
    client: httpx.AsyncClient,
    query: str,
    limit: int = 1000,
    range_seconds: int | None = None,
) -> list[dict]:
    params: dict[str, int | str] = {"q": query, "limit": limit}
    if range_seconds is not None:
        now = int(time.time())
        params["start"] = now - range_seconds
        params["end"] = now
    resp = await client.get(
        f"{TEMPO_URL}/api/search",
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("traces", [])


async def list_sessions(range_seconds: int | None = None) -> list[dict]:
    """Return per-session summaries (cost, tokens, call counts, time range).

    Spans are classified by which attributes they carry rather than the
    trace's root span name, since a session's LLM/tool spans may be nested
    under an `opencode.session` agent span instead of being trace roots.

    `range_seconds`, if given, limits the search to traces active within the
    last `range_seconds`, so large Tempo deployments don't require pulling
    the full history on every poll.
    """
    select_clause = ", ".join(SUMMARY_ATTRS)
    query = f'{{resource.service.name="opencode"}} | select({select_clause})'
    closed_query = '{resource.service.name="opencode" && name="opencode.session"} | select(.session.id)'

    async with httpx.AsyncClient() as client:
        traces, closed_traces = await asyncio.gather(
            _search(client, query, limit=4000, range_seconds=range_seconds),
            _search(client, closed_query, limit=4000, range_seconds=range_seconds),
        )

    closed_session_ids: set[str] = set()
    for trace in closed_traces:
        span_set = trace.get("spanSet") or (trace.get("spanSets") or [{}])[0]
        for span in span_set.get("spans", []):
            session_id = _span_attrs(span).get("session.id")
            if session_id:
                closed_session_ids.add(session_id)

    sessions: dict[str, dict] = {}

    for trace in traces:
        span_set = trace.get("spanSet") or (trace.get("spanSets") or [{}])[0]
        for span in span_set.get("spans", []):
            attrs = _span_attrs(span)
            session_id = attrs.get("session.id")
            if not session_id:
                continue

            start_ns = int(span["startTimeUnixNano"])
            duration_ns = int(span["durationNanos"])
            end_ns = start_ns + duration_ns

            s = sessions.setdefault(
                session_id,
                {
                    "session_id": session_id,
                    "start_ns": start_ns,
                    "end_ns": end_ns,
                    "llm_calls": 0,
                    "tool_calls": 0,
                    "total_cost_usd": 0.0,
                    "total_tokens": 0,
                    "models": set(),
                    "agents": set(),
                },
            )

            s["start_ns"] = min(s["start_ns"], start_ns)
            s["end_ns"] = max(s["end_ns"], end_ns)

            if attrs.get("llm.model_name") is not None:
                s["llm_calls"] += 1
                s["total_cost_usd"] += attrs.get("cost_usd") or 0
                s["total_tokens"] += attrs.get("llm.token_count.total") or 0
                s["models"].add(attrs["llm.model_name"])
            elif attrs.get("tool.name") is not None:
                s["tool_calls"] += 1

            if attrs.get("agent.name"):
                s["agents"].add(attrs["agent.name"])

    now_ns = time.time_ns()
    result = []
    for s in sessions.values():
        s["models"] = sorted(s["models"])
        s["agents"] = sorted(s["agents"])
        s["is_open"] = s["session_id"] not in closed_session_ids
        if s["is_open"]:
            s["end_ns"] = max(s["end_ns"], now_ns)
        s["duration_ms"] = (s["end_ns"] - s["start_ns"]) / 1e6
        result.append(s)

    result.sort(key=lambda s: s["start_ns"], reverse=True)
    return result


async def get_session_spans(session_id: str) -> list[dict]:
    """Fetch the full span tree for a session.

    A session's spans may be spread across multiple Tempo traces (flat,
    single-span traces) or nested under a single `opencode.session` trace.
    We find every trace that contains a span for this session, fetch each
    trace in full, keep only spans belonging to this session, and return
    them in depth-first order with a `depth` and `parent_span_id` so the
    frontend can render a nested (Jaeger-style) waterfall.
    """
    query = f'{{resource.service.name="opencode" && .session.id="{session_id}"}} | select(.session.id)'

    async with httpx.AsyncClient() as client:
        traces = await _search(client, query, limit=2000)
        trace_ids = sorted({t["traceID"] for t in traces})

        semaphore = asyncio.Semaphore(10)

        async def fetch(tid: str) -> list[dict]:
            async with semaphore:
                return await _get_trace(client, tid)

        full_traces = await asyncio.gather(*(fetch(tid) for tid in trace_ids))

    spans_by_id: dict[str, dict] = {}

    for trace_id, batches in zip(trace_ids, full_traces):
        for batch in batches:
            for scope_span in batch.get("scopeSpans", []):
                for span in scope_span.get("spans", []):
                    attrs = _span_attrs(span)
                    if attrs.get("session.id") != session_id:
                        continue

                    span_id = _to_hex(span["spanId"])
                    parent_id = _to_hex(span.get("parentSpanId"))
                    start_ns = int(span["startTimeUnixNano"])
                    end_ns = int(span["endTimeUnixNano"])
                    spans_by_id[span_id] = {
                        "trace_id": trace_id,
                        "span_id": span_id,
                        "parent_span_id": parent_id,
                        "span_name": span["name"],
                        "start_ns": start_ns,
                        "duration_ms": (end_ns - start_ns) / 1e6,
                        "attributes": attrs,
                    }

    # The root `opencode.session` span stays open for the lifetime of the session (so later
    # turns nest under it) and is only exported to Tempo once the session ends. While it's
    # open, its children reference a parent span ID that isn't in `spans_by_id` yet.
    # Synthesize a placeholder row for that still-open span so the waterfall still shows it
    # as the root instead of flattening its children into separate top-level spans.
    missing_parent_ids = {
        span["parent_span_id"]
        for span in spans_by_id.values()
        if span["parent_span_id"] and span["parent_span_id"] not in spans_by_id
    }
    for parent_id in missing_parent_ids:
        orphans = [s for s in spans_by_id.values() if s["parent_span_id"] == parent_id]
        start_ns = min(s["start_ns"] for s in orphans)
        end_ns = max(s["start_ns"] + s["duration_ms"] * 1e6 for s in orphans)
        agent_name = next((s["attributes"].get("agent.name") for s in orphans if s["attributes"].get("agent.name")), None)
        spans_by_id[parent_id] = {
            "trace_id": orphans[0]["trace_id"],
            "span_id": parent_id,
            "parent_span_id": None,
            "span_name": "opencode.session",
            "start_ns": start_ns,
            "duration_ms": (end_ns - start_ns) / 1e6,
            "attributes": {"session.id": session_id, "agent.name": agent_name, "session.is_open": True},
        }

    # Children grouped by parent, sorted by start time; spans whose parent
    # isn't part of this session's span set are treated as roots.
    children: dict[str | None, list[dict]] = {}
    for span in spans_by_id.values():
        parent_id = span["parent_span_id"]
        key = parent_id if parent_id in spans_by_id else None
        children.setdefault(key, []).append(span)

    for group in children.values():
        group.sort(key=lambda s: s["start_ns"])

    ordered: list[dict] = []

    def visit(span: dict, depth: int):
        ordered.append({**span, "depth": depth})
        for child in children.get(span["span_id"], []):
            visit(child, depth + 1)

    for root in children.get(None, []):
        visit(root, 0)

    return ordered


async def _get_trace(client: httpx.AsyncClient, trace_id: str) -> list[dict]:
    for attempt in range(5):
        resp = await client.get(f"{TEMPO_URL}/api/traces/{trace_id}", timeout=30)
        if resp.status_code == 429:
            await asyncio.sleep(0.2 * (attempt + 1))
            continue
        resp.raise_for_status()
        return resp.json().get("batches", [])
    resp.raise_for_status()
    return []
