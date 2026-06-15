"""Pydantic models for Trace Explorer API responses."""

from typing import Any

from pydantic import BaseModel, Field


class OtlpAttributeValue(BaseModel):
    """A single OTLP attribute value, e.g. ``{"stringValue": "hello"}``."""

    stringValue: str | None = None
    intValue: int | None = None
    doubleValue: float | None = None
    boolValue: bool | None = None

    @property
    def value(self) -> str | int | float | bool | None:
        """Return the first populated typed value, or ``None`` if all are unset."""
        for v in (self.stringValue, self.intValue, self.doubleValue, self.boolValue):
            if v is not None:
                return v
        return None


class OtlpAttribute(BaseModel):
    """A single OTLP ``{"key": ..., "value": ...}`` attribute entry."""

    key: str
    value: OtlpAttributeValue


class OtlpSpan(BaseModel):
    """A single OTLP span as returned by ``GET /api/traces/{id}``."""

    spanId: str
    parentSpanId: str | None = None
    name: str
    startTimeUnixNano: int
    endTimeUnixNano: int
    attributes: list[OtlpAttribute] = Field(default_factory=list)

    def attrs(self) -> dict[str, Any]:
        """Return a flat key/value dict for all attributes on this span."""
        return {a.key: a.value.value for a in self.attributes}


class OtlpScopeSpan(BaseModel):
    """An OTLP ``scopeSpans`` entry containing a list of spans."""

    spans: list[OtlpSpan] = Field(default_factory=list)


class OtlpBatch(BaseModel):
    """An OTLP ``batches`` entry containing a list of scope spans."""

    scopeSpans: list[OtlpScopeSpan] = Field(default_factory=list)


class TraceResponse(BaseModel):
    """The response body of ``GET /api/traces/{id}``."""

    batches: list[OtlpBatch] = Field(default_factory=list)


class SessionSummary(BaseModel):
    """Per-session summary including cost, tokens, call counts, and time range."""

    session_id: str
    start_ns: int
    end_ns: int
    duration_ms: float
    is_open: bool
    llm_calls: int
    tool_calls: int
    total_cost_usd: float
    total_tokens: int
    models: list[str]
    agents: list[str]
    parent_session_id: str | None


class ModelUsage(BaseModel):
    """Aggregated cost and token usage for a single LLM model."""

    model: str
    calls: int
    cost: float
    prompt_tokens: int
    completion_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    reasoning_tokens: int
    total_tokens: int
    providers: list[str]


class AgentUsage(BaseModel):
    """Aggregated cost and token usage for a single agent."""

    agent: str
    calls: int
    cost: float
    total_tokens: int


class ToolUsage(BaseModel):
    """Aggregated call counts and durations for a single tool."""

    tool: str
    calls: int
    total_duration_ms: float
    succeeded: int
    failed: int


class LlmCallRecord(BaseModel):
    """A single LLM call, truncated for display in a recent-calls list."""

    start_ns: int
    session_id: str
    agent: str
    model: str
    input: str | None
    finish_reason: str | None
    cost_usd: float
    duration_ms: float


class ToolCallRecord(BaseModel):
    """A single tool call, truncated for display in a recent-calls list."""

    start_ns: int
    session_id: str
    tool: str
    parameters: str | None
    success: bool | str | None
    output: str | None
    duration_ms: float


class TimeSeries(BaseModel):
    """Per-bucket cost, token, and tool-call counts for the overview charts."""

    bucket_starts_ns: list[int]
    cost_by_model: dict[str, list[float]]
    tokens_by_model: dict[str, list[int]]
    tool_calls_by_tool: dict[str, list[int]]


class Overview(BaseModel):
    """Aggregated cost, token, model, agent, and tool usage across all sessions."""

    total_sessions: int
    total_cost_usd: float
    total_tokens: int
    total_llm_calls: int
    total_tool_calls: int
    by_model: list[ModelUsage]
    by_agent: list[AgentUsage]
    by_tool: list[ToolUsage]
    llm_calls: list[LlmCallRecord]
    tool_calls: list[ToolCallRecord]
    timeseries: TimeSeries


class Span(BaseModel):
    """A single span in a session's waterfall, with depth for tree rendering."""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    span_name: str
    start_ns: int
    duration_ms: float
    depth: int
    attributes: dict[str, Any]
