# Refactor opencode-dashboard.json: model/token/tool usage, traces, drill-down

## Context

The opencode dashboard (`opencode-dashboard.json`) currently has 5 sections (Overview,
Cost & Token Usage, Tool Performance, Traces, Event Logs) with 12 panels. The metric
queries were already fixed (rate/increase -> raw sums) and the Loki `line_format`
quoting bug was fixed (single quotes -> backticks). Now we want to reorganize/extend
the dashboard so a user can:

- See model usage (which models/providers are used, cost & tokens per model)
- See token usage broken down by type and model
- See tool usage (calls, duration, success rate per tool)
- Browse traces and drill into a single call (LLM request or tool call) with full span detail
- Filter the whole dashboard down to one session (and optionally one model) to inspect
  a single run end-to-end (metrics -> traces -> logs)

## Data available (verified against running stack)

Prometheus metrics (job="otel-collector"), all cumulative per-session counters:
- `opencode_session_count_total{session_id, is_subagent}`
- `opencode_cost_usage_USD_total{session_id, model, agent}`
- `opencode_token_usage_tokens_total{session_id, model, agent, type}` (type = input/output/cache_read/cache_creation/reasoning)
- `opencode_model_usage_total{session_id, model, agent, provider}`
- `opencode_message_count_total{session_id, model, agent}`
- `opencode_tool_duration_milliseconds_{count,sum,bucket}{session_id, tool_name, success}`
- `opencode_lines_of_code_total` / `_count_total{session_id, type=added|removed}`
- `opencode_cache_count_total{session_id, model, type=cacheRead|...}`

Loki (`{service_name="opencode"}`), key `event_name` values:
- `api_request` (model, duration_ms, input_tokens, output_tokens, cache_read_tokens, cost_usd, provider, session_id)
- `tool_result` (tool_name, success, duration_ms, tool_result_size_bytes, session_id)
- `session.idle` / `session.created` / `session.error` (total_tokens, total_cost_usd, total_messages, session_id)
- `user_prompt` (prompt_length, model, session_id)

Tempo traces (`{resource.service.name="opencode"}`):
- Root spans: `opencode.llm` (one per LLM call) and `opencode.tool.<name>` (one per tool call)
- Span attributes include `session.id`, `llm.model_name`, `llm.token_count.*`, `cost_usd`, `duration_ms`, etc.
- `session.id` is a **span attribute**, not a resource attribute -> TraceQL filter is `.session.id`, not `resource.session.id`.

## Plan

### 1. Add template variables (dashboard `templating.list`)

- `session_id`: query-type Prometheus variable,
  `query: label_values(opencode_model_usage_total{job="otel-collector"}, session_id)`,
  `multi: true`, `includeAll: true`, `allValue: ".*"`, sort by recent-ish (alphabetical is fine,
  session ids aren't time-sortable, so default sort).
- `model`: query-type Prometheus variable, chained on session_id:
  `query: label_values(opencode_model_usage_total{job="otel-collector", session_id=~"$session_id"}, model)`,
  `multi: true`, `includeAll: true`, `allValue: ".*"`.

These two vars will be used to filter Prometheus, Loki, and Tempo queries throughout.

### 2. Reorganize sections/panels

**Overview** (stat row, keep similar but extend):
- Active Sessions: `count(count by (session_id) (opencode_session_count_total{job="otel-collector", session_id=~"$session_id"}))`
- Total Cost: `sum(opencode_cost_usage_USD_total{job="otel-collector", session_id=~"$session_id", model=~"$model"})`
- Total Tokens: `sum(opencode_token_usage_tokens_total{job="otel-collector", session_id=~"$session_id", model=~"$model"})`
- Tool Calls: `sum(opencode_tool_duration_milliseconds_count{job="otel-collector", session_id=~"$session_id"})`
- New: Messages: `sum(opencode_message_count_total{job="otel-collector", session_id=~"$session_id", model=~"$model"})`
- New: Lines Changed (+/-): two stats or one stat with two series from `opencode_lines_of_code_total{...,type=~"added|removed"}`

**Model Usage** (new section, replaces part of "Cost & Token Usage"):
- Cost by Model (existing, add `session_id=~"$session_id"` filter) - timeseries
- Token Usage by Model: `sum by (model) (opencode_token_usage_tokens_total{job="otel-collector", session_id=~"$session_id", type=~"input|output"})` - timeseries
- Requests by Model/Provider: table panel from `sum by (model, provider) (opencode_model_usage_total{job="otel-collector", session_id=~"$session_id"})`
- Token Usage by Type (existing, add filters) - timeseries

**Tool Usage** (rename "Tool Performance", add filters + success rate):
- Tool Calls by Tool (existing + `session_id=~"$session_id"` filter)
- Avg Tool Duration by Tool (existing + filter)
- New: Tool Success Rate by Tool: `sum by (tool_name) (opencode_tool_duration_milliseconds_count{success="true",...}) / sum by (tool_name) (opencode_tool_duration_milliseconds_count{...})` as a bar gauge/table (percent unit)

**Traces & Drill-down** (rename "Traces"):
- Recent Traces (Tempo, traceql) - update query to
  `{resource.service.name="opencode" && .session.id=~"$session_id"}` so it respects the session filter.
  This panel already supports click-through to full trace/span view (Tempo's built-in trace viewer),
  satisfying "inspect single calls".
- Configure trace-to-logs linking via the Tempo datasource (`grafana-datasources.yml`,
  `jsonData.tracesToLogsV2`): point at the `loki` datasource, map span attribute
  `session.id` -> Loki label `session_id`, with a filter query of
  `{service_name="opencode"} | session_id="${__span.tags["session.id"]}"`. This lets a user
  click a span and jump to the matching Loki logs for that session.

**Event Logs** (existing, add session filter):
- API Requests / Tool Results / Session Lifecycle: prepend `session_id=~"$session_id"` to the
  Loki stream selector, e.g. `{service_name="opencode", session_id=~"$session_id"} | event_name="api_request" | line_format ...`

### 3. Files to change

- `opencode-dashboard.json`: add `templating.list` entries; update/add panel queries and
  gridPos layout for the reorganized sections (Overview, Model Usage, Tool Usage,
  Traces & Drill-down, Event Logs); add ~4 new panels (Messages, Lines Changed,
  Token Usage by Model, Requests by Model table, Tool Success Rate).
- `grafana-datasources.yml`: add `jsonData.tracesToLogsV2` config to the `tempo` datasource
  for trace->log drill-down linking.

### 4. Verification

- Validate JSON with `python3 -c "import json; json.load(open('opencode-dashboard.json'))"`.
- Restart grafana (`docker compose restart grafana`) since dashboard hot-reload was
  unreliable last time and datasource changes need a restart anyway.
- Re-run the same `curl -u admin:admin http://localhost:3000/api/ds/query` checks used
  earlier for: Prometheus panels (with `session_id=~".*"`/`model=~".*"` substituted),
  Loki panels (with `session_id=~".*"`), and the Tempo TraceQL query with `.session.id`.
- Confirm template variables resolve via
  `curl -u admin:admin 'http://localhost:3000/api/datasources/proxy/uid/prometheus/api/v1/label/session_id/values'`
  (or the Grafana variable query API).
- Spot check one trace -> click span -> verify the "Logs for this span" link produces a
  valid Loki query filtered by that session_id.

## Status: implemented

All of the above is done:
- `templating.list` has `session_id`, `model`, and `agent` (chained: model and agent
  both filter on `session_id`).
- Sections/panels reorganized as planned: Overview (6 stats incl. Messages and Lines
  Changed +/-), Model Usage (Cost/Token by Model, Requests by Model/Provider table,
  Token Usage by Type), Tool Usage (Calls/Avg Duration by Tool, Tool Success Rate
  bargauge), Traces & Drill-down (session-filtered TraceQL), Event Logs
  (session-filtered Loki streams).
- `grafana-datasources.yml`: tempo datasource has `tracesToLogsV2` pointing at loki,
  matching `session.id` span attribute -> `session_id` Loki label. Note: had to
  escape `${__span.tags[...]}` as `$${__span.tags[...]}` in the YAML, otherwise
  Grafana's provisioning env-var interpolation strips it to an empty string.

### Extra: explainability of tool calls / model & agent usage

Added a new **"Agent & Model Activity"** section (Cost by Agent, Token Usage by
Agent, Requests by Agent/Model/Provider table) using the `agent` label that was
already present on `opencode_cost_usage_USD_total`, `opencode_token_usage_tokens_total`,
and `opencode_model_usage_total`.

Added a new **"Explainability: Calls & Reasoning"** section using Tempo TraceQL
`select()` to surface span attributes directly in table panels (no need to open each
trace individually):
- "LLM Calls (prompt -> model -> outcome)": `.agent.name`, `.llm.model_name`,
  `.input.value` (the prompt that triggered the call), `.llm.finish_reason`,
  `.cost_usd`, `.duration_ms`.
- "Tool Calls (tool -> parameters -> result)": `.tool.name`, `.tool.parameters`
  (actual args passed), `.tool.success`, `.output.value` (truncated tool output),
  `.duration_ms`.

Both respect `$session_id` (and the LLM table also `$agent`). Verified via
`/api/ds/query` against the running stack - both return populated tables with the
selected attributes as columns.
