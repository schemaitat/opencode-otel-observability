"""Tempo HTTP client and span-aggregation logic for the Trace Explorer backend."""

import asyncio
import base64
import logging
import os
import re
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_TASK_ID_RE = re.compile(r'<task id="(ses_\w+)"')

TEMPO_URL: str = os.environ.get("TEMPO_URL", "http://tempo:3200")

_TRACE_FETCH_CONCURRENCY: int = 10
_HTTP_TIMEOUT_SECONDS: int = 30
_PREVIEW_LEN: int = 200
_NUM_BUCKETS: int = 60

# TraceQL queries used across multiple functions.
_QUERY_ALL_SESSIONS: str = '{resource.service.name="opencode"} | select(.session.id)'
_QUERY_CLOSED_SESSIONS: str = (
    '{resource.service.name="opencode" && name="opencode.session"} | select(.session.id)'
)


# ── Attribute helpers ─────────────────────────────────────────────────────────


def _attr_value(value: dict[str, Any]) -> str | int | float | bool | None:
    """Extract a typed Python value from an OTLP attribute value dict.

    OTLP encodes attribute values as ``{"stringValue": "..."}`` etc. This
    returns the first matching key coerced to its native Python type.

    Args:
        value: A single OTLP attribute value object, e.g.
            ``{"stringValue": "hello"}`` or ``{"intValue": "42"}``.

    Returns:
        The extracted value as ``str``, ``int``, ``float``, or ``bool``,
        or ``None`` if none of the known type keys are present.
    """
    for key in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if key in value:
            v = value[key]
            if key == "intValue":
                return int(v)
            if key == "doubleValue":
                return float(v)
            return v  # type: ignore[return-value]
    return None


def _span_attrs(span: dict[str, Any]) -> dict[str, Any]:
    """Return a flat key/value dict for all attributes on an OTLP span.

    Args:
        span: A single OTLP span object containing an ``attributes`` list of
            ``{"key": ..., "value": ...}`` dicts.

    Returns:
        A dict mapping each attribute key to its decoded Python value.
    """
    return {a["key"]: _attr_value(a["value"]) for a in span.get("attributes", [])}


def _to_hex(span_id: str | None) -> str | None:
    """Convert an OTLP JSON span/parent-span ID (base64) to hex.

    The hex representation matches what Grafana's Tempo UI displays.
    Both ``None`` and empty-string inputs return ``None`` so callers can use a
    plain ``if parent_span_id`` check to detect root spans.

    Args:
        span_id: A base64-encoded span ID as it appears in OTLP JSON export,
            or ``None`` / ``""`` for absent parent span IDs.

    Returns:
        The lowercase hex string, or ``None`` if the input was absent or could
        not be decoded.
    """
    if span_id is None or span_id == "":
        return None
    try:
        return base64.b64decode(span_id).hex()
    except Exception:
        return span_id


def _truncate(value: object, length: int = _PREVIEW_LEN) -> str | None:
    """Convert a value to a string and truncate it to a maximum length.

    Args:
        value: Any value to stringify, or ``None`` to pass through as-is.
        length: Maximum number of characters to keep. Defaults to
            ``_PREVIEW_LEN``. Truncated strings are suffixed with ``"..."``.

    Returns:
        The (possibly truncated) string representation of ``value``, or
        ``None`` if ``value`` is ``None``.
    """
    if value is None:
        return None
    s = str(value)
    return s if len(s) <= length else s[:length] + "..."


# ── HTTP helpers ──────────────────────────────────────────────────────────────


async def _search(
    client: httpx.AsyncClient,
    query: str,
    limit: int = 1000,
    range_seconds: int | None = None,
) -> list[dict[str, Any]]:
    """Execute a TraceQL search against Tempo and return the matching trace stubs.

    ``spss`` (spans per span set) is set high so the search results include
    enough spans for the closed-session detection pass in ``list_sessions``.

    Args:
        client: Shared async HTTP client.
        query: TraceQL query string.
        limit: Maximum number of traces to return. Defaults to ``1000``.
        range_seconds: When set, constrains the search to traces whose start
            time falls within the last ``range_seconds`` seconds.

    Returns:
        A list of trace stub dicts as returned by ``GET /api/search``.

    Raises:
        httpx.HTTPStatusError: If Tempo returns a non-2xx response.
    """
    params: dict[str, int | str] = {"q": query, "limit": limit, "spss": 1000}
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


async def _get_trace(client: httpx.AsyncClient, trace_id: str) -> list[dict[str, Any]]:
    """Fetch a single trace by ID, retrying up to 5 times on HTTP 429.

    Args:
        client: Shared async HTTP client.
        trace_id: Hex trace ID to fetch.

    Returns:
        A list of OTLP batch dicts as returned by ``GET /api/traces/{id}``.

    Raises:
        httpx.HTTPStatusError: If Tempo returns a non-2xx response other than
            429, or if all 5 retry attempts are exhausted due to rate limiting.
    """
    url = f"{TEMPO_URL}/api/traces/{trace_id}"
    for attempt in range(1, 6):
        resp = await client.get(url, timeout=_HTTP_TIMEOUT_SECONDS)
        if resp.status_code != 429:
            resp.raise_for_status()
            return resp.json().get("batches", [])  # type: ignore[no-any-return]
        log.warning("Tempo rate-limited (attempt %d/5) for trace %s", attempt, trace_id)
        await asyncio.sleep(0.2 * attempt)
    # All 5 attempts returned 429 — raise a proper HTTP error.
    raise httpx.HTTPStatusError(
        f"Rate-limited after 5 retries for trace {trace_id}",
        request=resp.request,  # type: ignore[possibly-unbound]
        response=resp,  # type: ignore[possibly-unbound]
    )


async def _fetch_traces_by_ids(
    client: httpx.AsyncClient,
    trace_ids: list[str],
) -> list[list[dict[str, Any]]]:
    """Fetch each trace in full with bounded concurrency.

    Args:
        client: Shared async HTTP client.
        trace_ids: Ordered list of hex trace IDs to fetch.

    Returns:
        A list of batch lists in the same order as ``trace_ids``. Each
        element is the ``batches`` array from ``GET /api/traces/{id}``.
    """
    semaphore = asyncio.Semaphore(_TRACE_FETCH_CONCURRENCY)

    async def fetch(tid: str) -> list[dict[str, Any]]:
        async with semaphore:
            return await _get_trace(client, tid)

    return list(await asyncio.gather(*(fetch(tid) for tid in trace_ids)))


async def _fetch_all_traces(
    client: httpx.AsyncClient,
    query: str,
    limit: int,
    range_seconds: int | None,
) -> list[list[dict[str, Any]]]:
    """Search for traces matching a query and fetch each one in full.

    Args:
        client: Shared async HTTP client.
        query: TraceQL query string passed to ``_search``.
        limit: Maximum number of traces to search for.
        range_seconds: Optional time-range constraint forwarded to ``_search``.

    Returns:
        A list of batch lists, one per matching trace.
    """
    traces = await _search(client, query, limit=limit, range_seconds=range_seconds)
    trace_ids = sorted({t["traceID"] for t in traces})
    return await _fetch_traces_by_ids(client, trace_ids)


# ── Session list helpers ──────────────────────────────────────────────────────


def _extract_closed_session_ids(closed_traces: list[dict[str, Any]]) -> set[str]:
    """Extract session IDs whose root ``opencode.session`` span has been exported.

    A session is considered closed once its root span has been flushed to
    Tempo (which only happens when the session ends).

    Args:
        closed_traces: Trace stubs returned by searching for
            ``name="opencode.session"`` spans.

    Returns:
        The set of session IDs that are confirmed closed.
    """
    closed: set[str] = set()
    for trace in closed_traces:
        span_set = trace.get("spanSet") or (trace.get("spanSets") or [{}])[0]
        for span in span_set.get("spans", []):
            session_id = _span_attrs(span).get("session.id")
            if session_id:
                closed.add(str(session_id))
    return closed


def _aggregate_session_spans(
    full_traces: list[list[dict[str, Any]]],
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Aggregate per-session stats from a collection of full traces.

    Args:
        full_traces: List of batch lists as returned by ``_fetch_traces_by_ids``.

    Returns:
        A two-tuple ``(sessions, parent_by_child)`` where ``sessions`` maps
        session ID to an aggregated stats dict, and ``parent_by_child`` maps a
        subagent session ID to the parent session ID that launched it via the
        ``task`` tool.
    """
    sessions: dict[str, dict[str, Any]] = {}
    parent_by_child: dict[str, str] = {}

    for batches in full_traces:
        for batch in batches:
            for scope_span in batch.get("scopeSpans", []):
                for span in scope_span.get("spans", []):
                    attrs = _span_attrs(span)
                    session_id = attrs.get("session.id")
                    if not session_id:
                        continue

                    start_ns = int(span["startTimeUnixNano"])
                    end_ns = int(span["endTimeUnixNano"])

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

                    # A `task` tool call spawns a subagent in its own session; the
                    # spawned session's ID is embedded in the result text (e.g.
                    # `<task id="ses_..." state="completed">`), letting us link
                    # the subagent session back to the session that launched it.
                    if attrs.get("tool.name") == "task":
                        match = _TASK_ID_RE.search(attrs.get("output.value") or "")
                        if match:
                            parent_by_child[match.group(1)] = str(session_id)

    return sessions, parent_by_child


async def list_sessions(
    client: httpx.AsyncClient,
    range_seconds: int | None = None,
) -> list[dict[str, Any]]:
    """Return per-session summaries including cost, tokens, call counts, and time range.

    Spans are classified by which attributes they carry rather than the
    trace's root span name, since a session's LLM/tool spans may be nested
    under an ``opencode.session`` agent span instead of being trace roots.

    Args:
        client: Shared async HTTP client.
        range_seconds: When set, limits the search to traces active within the
            last ``range_seconds`` seconds. Pass ``None`` to fetch all history.

    Returns:
        A list of session summary dicts sorted by ``start_ns`` descending.
        Each dict includes ``session_id``, ``start_ns``, ``end_ns``,
        ``duration_ms``, ``is_open``, ``llm_calls``, ``tool_calls``,
        ``total_cost_usd``, ``total_tokens``, ``models``, ``agents``, and
        ``parent_session_id``.
    """
    traces, closed_traces = await asyncio.gather(
        _search(client, _QUERY_ALL_SESSIONS, limit=4000, range_seconds=range_seconds),
        _search(client, _QUERY_CLOSED_SESSIONS, limit=4000, range_seconds=range_seconds),
    )

    closed_session_ids = _extract_closed_session_ids(closed_traces)

    # The search API truncates each trace's spanSet to a handful of spans
    # (controlled by `spss`), which isn't enough to get accurate per-session
    # call counts. Fetch each matching trace in full instead and aggregate
    # from every span, the same way `get_session_spans` does.
    trace_ids = sorted({t["traceID"] for t in traces})
    full_traces = await _fetch_traces_by_ids(client, trace_ids)

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
        result.append(s)

    result.sort(key=lambda s: s["start_ns"], reverse=True)
    return result


# ── Overview helpers ──────────────────────────────────────────────────────────


def _compute_time_range(
    records: list[tuple[int, int, dict[str, Any]]],
    range_seconds: int | None,
    now_ns: int,
) -> tuple[int, int]:
    """Compute the nanosecond time range used for time-series bucketing.

    When ``range_seconds`` is ``None`` (the "all" option), the range is derived
    from the actual span timestamps so the buckets cover the full data set.
    Uses span ``end_ns`` (not ``start_ns``) as the upper bound to avoid
    truncating long-running spans at the tail of the range.

    Args:
        records: Flattened list of ``(start_ns, end_ns, attrs)`` tuples.
        range_seconds: Fixed window size in seconds, or ``None`` for "all".
        now_ns: Current time in nanoseconds used as the range ceiling.

    Returns:
        A ``(range_start_ns, range_end_ns)`` tuple in nanoseconds. Falls back
        to a 1-hour window ending at ``now_ns`` when ``records`` is empty and
        ``range_seconds`` is ``None``.
    """
    if range_seconds is not None:
        return now_ns - range_seconds * 10**9, now_ns
    if records:
        return (
            min(r[0] for r in records),
            max(now_ns, max(r[1] for r in records)),  # r[1] is end_ns
        )
    return now_ns - 3600 * 10**9, now_ns


async def get_overview(
    client: httpx.AsyncClient,
    range_seconds: int | None = None,
) -> dict[str, Any]:
    """Aggregate cost, token, model, agent, and tool usage across all sessions.

    Mirrors the "Model Usage", "Agent & Model Activity", "Tool Usage", and
    "Explainability" sections of the Grafana dashboard, computed directly from
    Tempo span attributes instead of Prometheus counters.

    Args:
        client: Shared async HTTP client.
        range_seconds: When set, limits the search to the last
            ``range_seconds`` seconds. Pass ``None`` to aggregate all history.

    Returns:
        A dict containing ``total_sessions``, ``total_cost_usd``,
        ``total_tokens``, ``total_llm_calls``, ``total_tool_calls``,
        ``by_model``, ``by_agent``, ``by_tool``, ``llm_calls`` (up to 100,
        newest first), ``tool_calls`` (up to 100, newest first), and
        ``timeseries`` with per-bucket cost, token, and tool-call counts.
    """
    full_traces = await _fetch_all_traces(
        client, _QUERY_ALL_SESSIONS, limit=4000, range_seconds=range_seconds
    )

    # Flatten into (start_ns, end_ns, attrs) tuples so we know the overall time
    # range before bucketing (required when range_seconds is None / "all").
    records: list[tuple[int, int, dict[str, Any]]] = []
    for batches in full_traces:
        for batch in batches:
            for scope_span in batch.get("scopeSpans", []):
                for span in scope_span.get("spans", []):
                    attrs = _span_attrs(span)
                    if not attrs.get("session.id"):
                        continue
                    records.append(
                        (int(span["startTimeUnixNano"]), int(span["endTimeUnixNano"]), attrs)
                    )

    now_ns = time.time_ns()
    range_start_ns, range_end_ns = _compute_time_range(records, range_seconds, now_ns)

    bucket_width_ns = max(1, (range_end_ns - range_start_ns) // _NUM_BUCKETS)
    bucket_starts_ns = [range_start_ns + i * bucket_width_ns for i in range(_NUM_BUCKETS)]

    def bucket_index(start_ns: int) -> int:
        """Map a span start time to its time-series bucket index (0-based, clamped)."""
        idx = (start_ns - range_start_ns) // bucket_width_ns
        return min(max(int(idx), 0), _NUM_BUCKETS - 1)

    # ── Aggregation pass ─────────────────────────────────────────────────────
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
            # ``tool.success`` may arrive as a native bool or as the string
            # "true"/"false" depending on the SDK version that emitted the span.
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

    return {
        "total_sessions": len(session_ids),
        "total_cost_usd": sum(m["cost"] for m in by_model.values()),
        "total_tokens": sum(m["total_tokens"] for m in by_model.values()),
        "total_llm_calls": len(llm_calls),
        "total_tool_calls": len(tool_calls),
        "by_model": sorted(by_model.values(), key=lambda m: m["cost"], reverse=True),
        "by_agent": sorted(by_agent.values(), key=lambda a: a["cost"], reverse=True),
        "by_tool": sorted(by_tool.values(), key=lambda t: t["calls"], reverse=True),
        "llm_calls": llm_calls[:100],
        "tool_calls": tool_calls[:100],
        "timeseries": {
            "bucket_starts_ns": bucket_starts_ns,
            "cost_by_model": cost_by_model_ts,
            "tokens_by_model": tokens_by_model_ts,
            "tool_calls_by_tool": tool_calls_ts,
        },
    }


# ── Session spans helpers ─────────────────────────────────────────────────────


def _synthesize_open_session_placeholders(
    spans_by_id: dict[str, dict[str, Any]],
    session_id: str,
) -> None:
    """Add placeholder root spans for sessions whose root span is still open.

    While a session is running its ``opencode.session`` root span is not yet
    exported to Tempo, but its child spans already reference its span ID as
    ``parentSpanId``. Without a placeholder the waterfall would render those
    children as disconnected top-level entries rather than nested under a
    single root.

    Args:
        spans_by_id: Mutable mapping of span ID to span dict. Placeholder
            entries are inserted directly into this dict.
        session_id: ID of the session being rendered, used to populate the
            placeholder's ``session.id`` attribute.
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
    """Return spans in depth-first order with a ``depth`` field for waterfall rendering.

    Spans whose parent is not present in ``spans_by_id`` are treated as roots.
    Siblings are sorted by ``start_ns`` at each level.

    Args:
        spans_by_id: Mapping of span ID to span dict for a single session.

    Returns:
        An ordered list of span dicts, each augmented with a ``depth`` integer
        (0 for roots, incrementing for each nesting level).
    """
    # Group children by parent; spans whose parent isn't in this session's set
    # are treated as roots (key=None).
    children: dict[str | None, list[dict[str, Any]]] = {}
    for span in spans_by_id.values():
        parent_id = span["parent_span_id"]
        key: str | None = parent_id if parent_id in spans_by_id else None
        children.setdefault(key, []).append(span)

    for group in children.values():
        group.sort(key=lambda s: s["start_ns"])

    ordered: list[dict[str, Any]] = []

    def visit(span: dict[str, Any], depth: int) -> None:
        """Append span and all descendants in DFS order."""
        ordered.append({**span, "depth": depth})
        for child in children.get(span["span_id"], []):
            visit(child, depth + 1)

    for root in children.get(None, []):
        visit(root, 0)

    return ordered


async def get_session_spans(
    client: httpx.AsyncClient,
    session_id: str,
) -> list[dict[str, Any]]:
    """Fetch the full span tree for a session in depth-first waterfall order.

    A session's spans may be spread across multiple Tempo traces (flat,
    single-span traces) or nested under a single ``opencode.session`` trace.
    Every trace containing a span for this session is fetched in full; only
    spans belonging to this session are kept, then returned in depth-first
    order with ``depth`` and ``parent_span_id`` fields for waterfall rendering.

    Args:
        client: Shared async HTTP client.
        session_id: The session whose spans should be fetched.

    Returns:
        An ordered list of span dicts, each containing ``trace_id``,
        ``span_id``, ``parent_span_id``, ``span_name``, ``start_ns``,
        ``duration_ms``, ``depth``, and ``attributes``.
    """
    query = (
        f'{{resource.service.name="opencode" && .session.id="{session_id}"}} | select(.session.id)'
    )
    traces = await _search(client, query, limit=2000)
    trace_ids = sorted({t["traceID"] for t in traces})
    full_traces = await _fetch_traces_by_ids(client, trace_ids)

    spans_by_id: dict[str, dict[str, Any]] = {}

    for trace_id, batches in zip(trace_ids, full_traces, strict=True):
        for batch in batches:
            for scope_span in batch.get("scopeSpans", []):
                for span in scope_span.get("spans", []):
                    attrs = _span_attrs(span)
                    if attrs.get("session.id") != session_id:
                        continue

                    # A `task` tool call spawns a subagent in its own session; the
                    # spawned session's ID is embedded in the result text (e.g.
                    # `<task id="ses_..." state="completed">`), so pull it out
                    # and expose it as an attribute the frontend can link to.
                    if attrs.get("tool.name") == "task":
                        match = _TASK_ID_RE.search(attrs.get("output.value") or "")
                        if match:
                            attrs["subagent.session_id"] = match.group(1)

                    span_id = _to_hex(span["spanId"])
                    parent_id = _to_hex(span.get("parentSpanId"))
                    start_ns = int(span["startTimeUnixNano"])
                    end_ns = int(span["endTimeUnixNano"])
                    if span_id is None:
                        continue
                    spans_by_id[span_id] = {
                        "trace_id": trace_id,
                        "span_id": span_id,
                        "parent_span_id": parent_id,
                        "span_name": span["name"],
                        "start_ns": start_ns,
                        "duration_ms": (end_ns - start_ns) / 1e6,
                        "attributes": attrs,
                    }

    _synthesize_open_session_placeholders(spans_by_id, session_id)
    return _build_ordered_spans(spans_by_id)
