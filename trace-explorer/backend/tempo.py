"""Tempo HTTP client and span-aggregation logic for the Trace Explorer backend."""

import asyncio
import base64
import logging
import os
import random
import re
import time
from collections.abc import Generator
from typing import Any

import httpx

from models import (
    AgentUsage,
    LlmCallRecord,
    ModelUsage,
    OtlpAttribute,
    OtlpBatch,
    OtlpSpan,
    Overview,
    SessionSummary,
    Span,
    TimeSeries,
    ToolCallRecord,
    ToolUsage,
    TraceResponse,
)

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_TASK_ID_RE = re.compile(r'<task id="(ses_\w+)"')

TEMPO_URL: str = os.environ.get("TEMPO_URL", "http://tempo:3200")

_TRACE_FETCH_CONCURRENCY: int = 25
_HTTP_TIMEOUT_SECONDS: int = 30
_PREVIEW_LEN: int = 200
_NUM_BUCKETS: int = 60

CACHE_TTL_SECONDS: float = float(os.environ.get("CACHE_TTL_SECONDS", "20"))

_QUERY_ALL_SESSIONS: str = '{resource.service.name="opencode"} | select(.session.id)'

# ── Module-level concurrency and cache state ──────────────────────────────────

# Single semaphore shared across all callers; prevents simultaneous endpoint
# calls (e.g. /api/sessions + /api/overview on page load) from collectively
# overwhelming Tempo.
_fetch_semaphore: asyncio.Semaphore = asyncio.Semaphore(_TRACE_FETCH_CONCURRENCY)

# TTL cache keyed by (query, limit, range_seconds).
# Values are either an in-flight Future (coalesce) or (expiry, result) tuple.
type _BatchList = list[list[OtlpBatch]]
type _CacheEntry = asyncio.Future[_BatchList] | tuple[float, _BatchList]

_request_cache: dict[tuple[str | int | None, ...], _CacheEntry] = {}


# ── Span iteration helper ─────────────────────────────────────────────────────


def _iter_spans(full_traces: list[list[OtlpBatch]]) -> Generator[OtlpSpan, None, None]:
    """Yield every OtlpSpan across all batches and scope-spans in full_traces."""
    for batches in full_traces:
        for batch in batches:
            for scope_span in batch.scopeSpans:
                yield from scope_span.spans


# ── Attribute helpers ─────────────────────────────────────────────────────────


def _to_hex(span_id: str | None) -> str | None:
    """Convert a base64 OTLP span ID to hex, or return None if absent/invalid."""
    if span_id is None or span_id == "":
        return None
    try:
        return base64.b64decode(span_id).hex()
    except Exception:
        return span_id


def _truncate(value: object, length: int = _PREVIEW_LEN) -> str | None:
    """Stringify value and truncate to length, or pass through None."""
    if value is None:
        return None
    s = str(value)
    return s if len(s) <= length else s[:length] + "..."


def _span_set_attrs(span: dict[str, Any]) -> dict[str, Any]:
    """Return a flat key/value dict for a span from GET /api/search results."""
    return {
        attr.key: attr.value.value
        for attr in (OtlpAttribute.model_validate(a) for a in span.get("attributes", []))
    }


# ── HTTP helpers ──────────────────────────────────────────────────────────────


async def _search(
    client: httpx.AsyncClient,
    query: str,
    limit: int = 1000,
    range_seconds: int | None = None,
) -> list[dict[str, Any]]:
    """Execute a TraceQL search against Tempo; return matching trace stubs."""
    params: dict[str, int | str] = {"q": query, "limit": limit, "spss": 1}
    if range_seconds is not None:
        now = int(time.time())
        params["start"] = now - range_seconds
        params["end"] = now
    resp = await client.get(
        f"{TEMPO_URL}/api/search",
        params=params,
        timeout=_HTTP_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json().get("traces", [])  # type: ignore[no-any-return]


async def _fetch_traces_by_ids(
    client: httpx.AsyncClient,
    trace_ids: list[str],
) -> list[list[OtlpBatch]]:
    """Fetch each trace in full with bounded global concurrency and 429 retry."""

    async def fetch(tid: str) -> list[OtlpBatch]:
        url = f"{TEMPO_URL}/api/traces/{tid}"
        resp: httpx.Response | None = None
        for attempt in range(1, 6):
            async with _fetch_semaphore:
                resp = await client.get(url, timeout=_HTTP_TIMEOUT_SECONDS)
                if resp.status_code != 429:
                    resp.raise_for_status()
                    return TraceResponse.model_validate(resp.json()).batches
                log.warning("Tempo rate-limited (attempt %d/5) for trace %s", attempt, tid)
            # Release semaphore before sleeping so other traces can proceed.
            await asyncio.sleep(random.uniform(0, 0.2 * attempt))
        assert resp is not None
        raise httpx.HTTPStatusError(
            f"Rate-limited after 5 retries for trace {tid}",
            request=resp.request,
            response=resp,
        )

    return list(await asyncio.gather(*(fetch(tid) for tid in trace_ids)))


async def _fetch_all_traces(
    client: httpx.AsyncClient,
    query: str,
    limit: int,
    range_seconds: int | None,
) -> list[list[OtlpBatch]]:
    """Search for traces matching query and fetch each one in full."""
    traces = await _search(client, query, limit=limit, range_seconds=range_seconds)
    trace_ids = sorted({t["traceID"] for t in traces})
    return await _fetch_traces_by_ids(client, trace_ids)


async def _cached_fetch_all_traces(
    client: httpx.AsyncClient,
    query: str,
    limit: int,
    range_seconds: int | None,
) -> list[list[OtlpBatch]]:
    """Fetch all traces with TTL caching and request coalescing.

    Because asyncio is single-threaded the cache read-then-write is atomic —
    no await can interleave, so concurrent callers coalesce onto one Future.
    """
    key: tuple[str | int | None, ...] = (query, limit, range_seconds)
    now = time.monotonic()

    entry = _request_cache.get(key)

    if isinstance(entry, tuple) and entry[0] > now:
        return entry[1]

    if isinstance(entry, asyncio.Future) and not entry.done():
        return await entry

    loop = asyncio.get_running_loop()
    future: asyncio.Future[_BatchList] = loop.create_future()
    _request_cache[key] = future

    try:
        result = await _fetch_all_traces(client, query, limit, range_seconds)
    except Exception as exc:
        future.set_exception(exc)
        _request_cache.pop(key, None)
        raise

    future.set_result(result)
    _request_cache[key] = (now + CACHE_TTL_SECONDS, result)
    return result


# ── Session list helpers ──────────────────────────────────────────────────────


def _extract_closed_session_ids(full_traces: list[list[OtlpBatch]]) -> set[str]:
    """Return session IDs whose root opencode.session span has been exported."""
    closed: set[str] = set()
    for span in _iter_spans(full_traces):
        if span.name == "opencode.session":
            session_id = span.attrs().get("session.id")
            if session_id:
                closed.add(str(session_id))
    return closed


def _aggregate_session_spans(
    full_traces: list[list[OtlpBatch]],
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Aggregate per-session stats; return (sessions dict, parent_by_child dict)."""
    sessions: dict[str, dict[str, Any]] = {}
    parent_by_child: dict[str, str] = {}

    for span in _iter_spans(full_traces):
        attrs = span.attrs()
        session_id = attrs.get("session.id")
        if not session_id:
            continue

        start_ns = span.startTimeUnixNano
        end_ns = span.endTimeUnixNano

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

        if attrs.get("tool.name") == "task":
            match = _TASK_ID_RE.search(attrs.get("output.value") or "")
            if match:
                parent_by_child[match.group(1)] = str(session_id)

    return sessions, parent_by_child


async def list_sessions(
    client: httpx.AsyncClient,
    range_seconds: int | None = None,
) -> list[SessionSummary]:
    """Return per-session summaries sorted by start time descending."""
    full_traces = await _cached_fetch_all_traces(
        client, _QUERY_ALL_SESSIONS, limit=4000, range_seconds=range_seconds
    )

    closed_session_ids = _extract_closed_session_ids(full_traces)
    sessions, parent_by_child = _aggregate_session_spans(full_traces)

    now_ns = time.time_ns()
    result = []
    for s in sessions.values():
        s["models"] = sorted(s["models"])
        s["agents"] = sorted(s["agents"])
        s["is_open"] = s["session_id"] not in closed_session_ids
        s["parent_session_id"] = parent_by_child.get(s["session_id"])
        if s["is_open"]:
            s["end_ns"] = max(s["end_ns"], now_ns)
        s["duration_ms"] = (s["end_ns"] - s["start_ns"]) / 1e6
        result.append(SessionSummary(**s))

    result.sort(key=lambda s: s.start_ns, reverse=True)
    return result


# ── Overview helpers ──────────────────────────────────────────────────────────


def _compute_time_range(
    records: list[tuple[int, int, dict[str, Any]]],
    range_seconds: int | None,
    now_ns: int,
) -> tuple[int, int]:
    """Return (range_start_ns, range_end_ns) for time-series bucketing."""
    if range_seconds is not None:
        return now_ns - range_seconds * 10**9, now_ns
    if records:
        return (
            min(r[0] for r in records),
            max(now_ns, max(r[1] for r in records)),
        )
    return now_ns - 3600 * 10**9, now_ns


async def get_overview(
    client: httpx.AsyncClient,
    range_seconds: int | None = None,
) -> Overview:
    """Aggregate cost, token, model, agent, and tool usage across all sessions."""
    full_traces = await _cached_fetch_all_traces(
        client, _QUERY_ALL_SESSIONS, limit=4000, range_seconds=range_seconds
    )

    records: list[tuple[int, int, dict[str, Any]]] = []
    for span in _iter_spans(full_traces):
        attrs = span.attrs()
        if not attrs.get("session.id"):
            continue
        records.append((span.startTimeUnixNano, span.endTimeUnixNano, attrs))

    now_ns = time.time_ns()
    range_start_ns, range_end_ns = _compute_time_range(records, range_seconds, now_ns)

    bucket_width_ns = max(1, (range_end_ns - range_start_ns) // _NUM_BUCKETS)
    bucket_starts_ns = [range_start_ns + i * bucket_width_ns for i in range(_NUM_BUCKETS)]

    def bucket_index(start_ns: int) -> int:
        idx = (start_ns - range_start_ns) // bucket_width_ns
        return min(max(int(idx), 0), _NUM_BUCKETS - 1)

    session_ids: set[str] = set()
    by_model: dict[str, dict[str, Any]] = {}
    by_agent: dict[str, dict[str, Any]] = {}
    by_tool: dict[str, dict[str, Any]] = {}
    llm_calls: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    cost_by_model_ts: dict[str, list[float]] = {}
    tokens_by_model_ts: dict[str, list[int]] = {}
    tool_calls_ts: dict[str, list[int]] = {}

    for start_ns, end_ns, attrs in records:
        session_id = str(attrs["session.id"])
        session_ids.add(session_id)

        duration_ms = (end_ns - start_ns) / 1e6
        agent = str(attrs.get("agent.name") or "unknown")
        bucket = bucket_index(start_ns)

        if attrs.get("llm.model_name") is not None:
            model = str(attrs["llm.model_name"])
            cost = float(attrs.get("cost_usd") or 0)
            total_tokens = int(attrs.get("llm.token_count.total") or 0)

            m = by_model.setdefault(
                model,
                {
                    "model": model,
                    "calls": 0,
                    "cost": 0.0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                    "reasoning_tokens": 0,
                    "total_tokens": 0,
                    "providers": set(),
                },
            )
            m["calls"] += 1
            m["cost"] += cost
            m["prompt_tokens"] += attrs.get("llm.token_count.prompt") or 0
            m["completion_tokens"] += attrs.get("llm.token_count.completion") or 0
            m["cache_read_tokens"] += attrs.get("llm.token_count.prompt_details.cache_read") or 0
            m["cache_write_tokens"] += attrs.get("llm.token_count.prompt_details.cache_write") or 0
            m["reasoning_tokens"] += attrs.get("llm.token_count.completion_details.reasoning") or 0
            m["total_tokens"] += total_tokens
            if attrs.get("llm.provider"):
                m["providers"].add(attrs["llm.provider"])

            a = by_agent.setdefault(
                agent, {"agent": agent, "calls": 0, "cost": 0.0, "total_tokens": 0}
            )
            a["calls"] += 1
            a["cost"] += cost
            a["total_tokens"] += total_tokens

            cost_by_model_ts.setdefault(model, [0.0] * _NUM_BUCKETS)[bucket] += cost
            tokens_by_model_ts.setdefault(model, [0] * _NUM_BUCKETS)[bucket] += total_tokens

            llm_calls.append(
                {
                    "start_ns": start_ns,
                    "session_id": session_id,
                    "agent": agent,
                    "model": model,
                    "input": _truncate(attrs.get("input.value")),
                    "finish_reason": attrs.get("llm.finish_reason"),
                    "cost_usd": cost,
                    "duration_ms": duration_ms,
                }
            )
        elif attrs.get("tool.name") is not None:
            tool = str(attrs["tool.name"])
            success = attrs.get("tool.success")
            # tool.success may arrive as native bool or string depending on SDK version
            succeeded = success is True or success == "true"
            failed = success is False or success == "false"

            t = by_tool.setdefault(
                tool,
                {"tool": tool, "calls": 0, "total_duration_ms": 0.0, "succeeded": 0, "failed": 0},
            )
            t["calls"] += 1
            t["total_duration_ms"] += duration_ms
            if succeeded:
                t["succeeded"] += 1
            if failed:
                t["failed"] += 1

            tool_calls_ts.setdefault(tool, [0] * _NUM_BUCKETS)[bucket] += 1

            tool_calls.append(
                {
                    "start_ns": start_ns,
                    "session_id": session_id,
                    "tool": tool,
                    "parameters": _truncate(attrs.get("tool.parameters")),
                    "success": success,
                    "output": _truncate(attrs.get("output.value")),
                    "duration_ms": duration_ms,
                }
            )

    for m in by_model.values():
        m["providers"] = sorted(m["providers"])

    llm_calls.sort(key=lambda r: r["start_ns"], reverse=True)
    tool_calls.sort(key=lambda r: r["start_ns"], reverse=True)

    return Overview(
        total_sessions=len(session_ids),
        total_cost_usd=sum(m["cost"] for m in by_model.values()),
        total_tokens=sum(m["total_tokens"] for m in by_model.values()),
        total_llm_calls=len(llm_calls),
        total_tool_calls=len(tool_calls),
        by_model=[
            ModelUsage(**m)
            for m in sorted(by_model.values(), key=lambda m: m["cost"], reverse=True)
        ],
        by_agent=[
            AgentUsage(**a)
            for a in sorted(by_agent.values(), key=lambda a: a["cost"], reverse=True)
        ],
        by_tool=[
            ToolUsage(**t) for t in sorted(by_tool.values(), key=lambda t: t["calls"], reverse=True)
        ],
        llm_calls=[LlmCallRecord(**r) for r in llm_calls[:100]],
        tool_calls=[ToolCallRecord(**r) for r in tool_calls[:100]],
        timeseries=TimeSeries(
            bucket_starts_ns=bucket_starts_ns,
            cost_by_model=cost_by_model_ts,
            tokens_by_model=tokens_by_model_ts,
            tool_calls_by_tool=tool_calls_ts,
        ),
    )


# ── Session spans helpers ─────────────────────────────────────────────────────


def _synthesize_open_session_placeholders(
    spans_by_id: dict[str, dict[str, Any]],
    session_id: str,
) -> None:
    """Insert placeholder root spans for sessions whose root hasn't been flushed yet.

    While a session is running, child spans reference a parentSpanId that isn't
    in Tempo yet. The placeholder uses that same ID so when the real root arrives
    it transparently replaces it. session.is_open=True signals the SSE stream to
    keep polling and the frontend to show a live indicator.
    """
    missing_parent_ids = {
        span["parent_span_id"]
        for span in spans_by_id.values()
        if span["parent_span_id"] and span["parent_span_id"] not in spans_by_id
    }
    for parent_id in missing_parent_ids:
        orphans = [s for s in spans_by_id.values() if s["parent_span_id"] == parent_id]
        start_ns = min(s["start_ns"] for s in orphans)
        end_ns = max(s["start_ns"] + s["duration_ms"] * 1e6 for s in orphans)
        agent_name = next(
            (
                s["attributes"].get("agent.name")
                for s in orphans
                if s["attributes"].get("agent.name")
            ),
            None,
        )
        spans_by_id[parent_id] = {
            "trace_id": orphans[0]["trace_id"],
            "span_id": parent_id,
            "parent_span_id": None,
            "span_name": "opencode.session",
            "start_ns": start_ns,
            "duration_ms": (end_ns - start_ns) / 1e6,
            "attributes": {
                "session.id": session_id,
                "agent.name": agent_name,
                "session.is_open": True,
            },
        }


def _build_ordered_spans(spans_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Return spans in depth-first order with a depth field for waterfall rendering."""
    children: dict[str | None, list[dict[str, Any]]] = {}
    for span in spans_by_id.values():
        parent_id = span["parent_span_id"]
        key: str | None = parent_id if parent_id in spans_by_id else None
        children.setdefault(key, []).append(span)

    for group in children.values():
        group.sort(key=lambda s: s["start_ns"])

    ordered: list[dict[str, Any]] = []

    def visit(span: dict[str, Any], depth: int) -> None:
        ordered.append({**span, "depth": depth})
        for child in children.get(span["span_id"], []):
            visit(child, depth + 1)

    for root in children.get(None, []):
        visit(root, 0)

    return ordered


async def get_session_spans(
    client: httpx.AsyncClient,
    session_id: str,
) -> list[Span]:
    """Fetch the full span tree for a session in depth-first waterfall order."""
    query = (
        f'{{resource.service.name="opencode" && .session.id="{session_id}"}} | select(.session.id)'
    )
    traces = await _search(client, query, limit=2000)
    trace_ids = sorted({t["traceID"] for t in traces})
    full_traces = await _fetch_traces_by_ids(client, trace_ids)

    spans_by_id: dict[str, dict[str, Any]] = {}

    for trace_id, batches in zip(trace_ids, full_traces, strict=True):
        for span in _iter_spans([batches]):
            attrs = span.attrs()
            if attrs.get("session.id") != session_id:
                continue

            if attrs.get("tool.name") == "task":
                match = _TASK_ID_RE.search(attrs.get("output.value") or "")
                if match:
                    attrs["subagent.session_id"] = match.group(1)

            span_id = _to_hex(span.spanId)
            parent_id = _to_hex(span.parentSpanId)
            start_ns = span.startTimeUnixNano
            end_ns = span.endTimeUnixNano
            if span_id is None:
                continue
            spans_by_id[span_id] = {
                "trace_id": trace_id,
                "span_id": span_id,
                "parent_span_id": parent_id,
                "span_name": span.name,
                "start_ns": start_ns,
                "duration_ms": (end_ns - start_ns) / 1e6,
                "attributes": attrs,
            }

    _synthesize_open_session_placeholders(spans_by_id, session_id)
    return [Span(**span) for span in _build_ordered_spans(spans_by_id)]
