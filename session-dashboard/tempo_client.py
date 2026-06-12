import os
import requests

TEMPO_URL = os.environ.get("TEMPO_URL", "http://tempo:3200")
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")

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


def list_sessions() -> list[str]:
    """Return session ids known to Prometheus, most recently active first isn't
    available (no timestamp label), so just return sorted ids."""
    resp = requests.get(
        f"{PROMETHEUS_URL}/api/v1/label/session_id/values",
        params={"match[]": 'opencode_model_usage_total{job="otel-collector"}'},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json().get("data", [])
    return sorted(data, reverse=True)


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
