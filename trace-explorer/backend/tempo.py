import asyncio
import base64
import os
import re
import time

import httpx

_TASK_ID_RE = re.compile(r"task_id:\s*(ses_\w+)")

TEMPO_URL = os.environ.get("TEMPO_URL", "http://tempo:3200")


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
    params: dict[str, int | str] = {"q": query, "limit": limit, "spss": 1000}
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


async def _fetch_all_traces(
    client: httpx.AsyncClient, query: str, limit: int, range_seconds: int | None
) -> list[list[dict]]:
    """Search for traces matching `query` and fetch each one in full (list of batches)."""
    traces = await _search(client, query, limit=limit, range_seconds=range_seconds)
    trace_ids = sorted({t["traceID"] for t in traces})

    semaphore = asyncio.Semaphore(10)

    async def fetch(tid: str) -> list[dict]:
        async with semaphore:
            return await _get_trace(client, tid)

    return await asyncio.gather(*(fetch(tid) for tid in trace_ids))


async def list_sessions(range_seconds: int | None = None) -> list[dict]:
    """Return per-session summaries (cost, tokens, call counts, time range).

    Spans are classified by which attributes they carry rather than the
    trace's root span name, since a session's LLM/tool spans may be nested
    under an `opencode.session` agent span instead of being trace roots.

    `range_seconds`, if given, limits the search to traces active within the
    last `range_seconds`, so large Tempo deployments don't require pulling
    the full history on every poll.
    """
    query = '{resource.service.name="opencode"} | select(.session.id)'
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

        # The search API truncates each trace's spanSet to a handful of spans
        # (controlled by `spss`), which isn't enough to get accurate per-session
        # call counts. Fetch each matching trace in full instead and aggregate
        # from every span, the same way `get_session_spans` does.
        trace_ids = sorted({t["traceID"] for t in traces})

        semaphore = asyncio.Semaphore(10)

        async def fetch(tid: str) -> list[dict]:
            async with semaphore:
                return await _get_trace(client, tid)

        full_traces = await asyncio.gather(*(fetch(tid) for tid in trace_ids))

    sessions: dict[str, dict] = {}
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
                    # "task_id: ses_... (for resuming...)"), letting us link the
                    # subagent session back to the session that launched it.
                    if attrs.get("tool.name") == "task":
                        match = _TASK_ID_RE.search(attrs.get("output.value") or "")
                        if match:
                            parent_by_child[match.group(1)] = session_id

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


_PREVIEW_LEN = 200


def _truncate(value, length: int = _PREVIEW_LEN):
    if value is None:
        return None
    s = str(value)
    return s if len(s) <= length else s[:length] + "..."


_NUM_BUCKETS = 60


async def get_overview(range_seconds: int | None = None) -> dict:
    """Aggregate cost, token, model, agent, and tool usage across all sessions.

    Mirrors the "Model Usage", "Agent & Model Activity", "Tool Usage", and
    "Explainability" sections of the Grafana dashboard, computed directly from
    Tempo span attributes instead of Prometheus counters.
    """
    query = '{resource.service.name="opencode"} | select(.session.id)'

    async with httpx.AsyncClient() as client:
        full_traces = await _fetch_all_traces(client, query, limit=4000, range_seconds=range_seconds)

    # Flatten into (start_ns, end_ns, attrs) tuples first so we know the
    # overall time range before bucketing (needed for range="all").
    records: list[tuple[int, int, dict]] = []
    for batches in full_traces:
        for batch in batches:
            for scope_span in batch.get("scopeSpans", []):
                for span in scope_span.get("spans", []):
                    attrs = _span_attrs(span)
                    if not attrs.get("session.id"):
                        continue
                    records.append((int(span["startTimeUnixNano"]), int(span["endTimeUnixNano"]), attrs))

    now_ns = time.time_ns()
    if range_seconds is not None:
        range_start_ns = now_ns - range_seconds * 10**9
        range_end_ns = now_ns
    elif records:
        range_start_ns = min(r[0] for r in records)
        range_end_ns = max(now_ns, max(r[0] for r in records))
    else:
        range_start_ns = now_ns - 3600 * 10**9
        range_end_ns = now_ns

    bucket_width_ns = max(1, (range_end_ns - range_start_ns) // _NUM_BUCKETS)
    bucket_starts_ns = [range_start_ns + i * bucket_width_ns for i in range(_NUM_BUCKETS)]

    def bucket_index(start_ns: int) -> int:
        idx = (start_ns - range_start_ns) // bucket_width_ns
        return min(max(idx, 0), _NUM_BUCKETS - 1)

    session_ids: set[str] = set()
    by_model: dict[str, dict] = {}
    by_agent: dict[str, dict] = {}
    by_tool: dict[str, dict] = {}
    llm_calls: list[dict] = []
    tool_calls: list[dict] = []
    cost_by_model_ts: dict[str, list[float]] = {}
    tokens_by_model_ts: dict[str, list[int]] = {}
    tool_calls_ts: dict[str, list[int]] = {}

    for start_ns, end_ns, attrs in records:
        session_id = attrs["session.id"]
        session_ids.add(session_id)

        duration_ms = (end_ns - start_ns) / 1e6
        agent = attrs.get("agent.name") or "unknown"
        bucket = bucket_index(start_ns)

        if attrs.get("llm.model_name") is not None:
            model = attrs["llm.model_name"]
            cost = attrs.get("cost_usd") or 0
            total_tokens = attrs.get("llm.token_count.total") or 0

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

            a = by_agent.setdefault(agent, {"agent": agent, "calls": 0, "cost": 0.0, "total_tokens": 0})
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
            tool = attrs["tool.name"]
            success = attrs.get("tool.success")
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

                    # A `task` tool call spawns a subagent in its own session; the
                    # spawned session's ID is embedded in the result text (e.g.
                    # "task_id: ses_... (for resuming...)"), so pull it out and
                    # expose it as an attribute the frontend can link to.
                    if attrs.get("tool.name") == "task":
                        match = _TASK_ID_RE.search(attrs.get("output.value") or "")
                        if match:
                            attrs["subagent.session_id"] = match.group(1)

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
