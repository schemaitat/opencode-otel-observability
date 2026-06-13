import os
import requests

TEMPO_URL = os.environ.get("TEMPO_URL", "http://tempo:3200")

SESSION_SPAN_ATTRS = [
    ".llm.model_name",
    ".tool.name",
    ".agent.name",
    ".cost_usd",
    ".duration_ms",
    ".llm.token_count.total",
    ".llm.token_count.prompt",
    ".llm.token_count.completion",
    ".llm.finish_reason",
    ".tool.success",
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


def list_sessions() -> list[dict]:
    """Return known sessions with their earliest span start time, most recently
    started first."""
    query = '{resource.service.name="opencode"} | select(.session.id)'
    resp = requests.get(
        f"{TEMPO_URL}/api/search",
        params={"q": query, "limit": 1000},
        timeout=30,
    )
    resp.raise_for_status()
    traces = resp.json().get("traces", [])

    start_ns_by_session: dict[str, int] = {}
    for trace in traces:
        span_set = trace.get("spanSet") or (trace.get("spanSets") or [{}])[0]
        for span in span_set.get("spans", []):
            session_id = _span_attrs(span).get("session.id")
            if not session_id:
                continue
            start_ns = int(span["startTimeUnixNano"])
            if session_id not in start_ns_by_session or start_ns < start_ns_by_session[session_id]:
                start_ns_by_session[session_id] = start_ns

    return [
        {"session_id": session_id, "start_ns": start_ns}
        for session_id, start_ns in sorted(
            start_ns_by_session.items(), key=lambda kv: kv[1], reverse=True
        )
    ]


def get_session_spans(session_id: str) -> list[dict]:
    """Fetch a lightweight list of all spans (LLM + tool calls) for a session."""
    select_clause = ", ".join(SESSION_SPAN_ATTRS)
    query = (
        f'{{resource.service.name="opencode" && .session.id="{session_id}"}}'
        f" | select({select_clause})"
    )
    resp = requests.get(
        f"{TEMPO_URL}/api/search",
        params={"q": query, "limit": 500},
        timeout=30,
    )
    resp.raise_for_status()
    traces = resp.json().get("traces", [])

    spans = []
    for trace in traces:
        span_set = trace.get("spanSet") or (trace.get("spanSets") or [{}])[0]
        for span in span_set.get("spans", []):
            attrs = _span_attrs(span)
            start_ns = int(span["startTimeUnixNano"])
            duration_ns = int(span["durationNanos"])
            spans.append(
                {
                    "trace_id": trace["traceID"],
                    "span_id": span["spanID"],
                    "span_name": trace.get("rootTraceName", "unknown"),
                    "start_ns": start_ns,
                    "duration_ms": duration_ns / 1e6,
                    "model": attrs.get("llm.model_name"),
                    "tool_name": attrs.get("tool.name"),
                    "agent_name": attrs.get("agent.name"),
                    "cost_usd": attrs.get("cost_usd") or 0,
                    "tokens_total": attrs.get("llm.token_count.total") or 0,
                    "tokens_prompt": attrs.get("llm.token_count.prompt") or 0,
                    "tokens_completion": attrs.get("llm.token_count.completion") or 0,
                    "finish_reason": attrs.get("llm.finish_reason"),
                    "tool_success": attrs.get("tool.success"),
                }
            )

    spans.sort(key=lambda s: s["start_ns"])
    return spans


def get_trace_detail(trace_id: str) -> dict:
    """Fetch the full trace and return the root span's attributes as a dict."""
    resp = requests.get(f"{TEMPO_URL}/api/traces/{trace_id}", timeout=30)
    resp.raise_for_status()
    data = resp.json()

    for batch in data.get("batches", []):
        for scope_span in batch.get("scopeSpans", []):
            for span in scope_span.get("spans", []):
                if not span.get("parentSpanId"):
                    return _span_attrs(span)
    return {}
