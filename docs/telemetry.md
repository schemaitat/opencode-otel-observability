# Metrics, Logs & Traces

## Metrics (Prometheus, `opencode_*`)

Cumulative per-session counters exported via the `otel-collector` job:

| Metric | Labels |
|--------|--------|
| `opencode_session_count_total` | `session_id`, `is_subagent` |
| `opencode_cost_usage_USD_total` | `session_id`, `model`, `agent` |
| `opencode_token_usage_tokens_total` | `session_id`, `model`, `agent`, `type` (`input`/`output`/`cache_read`/`cache_creation`/`reasoning`) |
| `opencode_model_usage_total` | `session_id`, `model`, `agent`, `provider` |
| `opencode_message_count_total` | `session_id`, `model`, `agent` |
| `opencode_tool_duration_milliseconds_{count,sum,bucket}` | `session_id`, `tool_name`, `success` |
| `opencode_lines_of_code_total` | `session_id`, `type` (`added`/`removed`) |
| `opencode_cache_count_total` | `session_id`, `model`, `type` |

## Logs (Loki, `{service_name="opencode"}`)

Key `event_name` values:

| Event | Key attributes |
|-------|----------------|
| `api_request` | `model`, `duration_ms`, token counts, `cost_usd`, `provider`, `session_id` |
| `tool_result` | `tool_name`, `success`, `duration_ms`, `tool_result_size_bytes`, `session_id` |
| `session.idle` / `session.created` / `session.error` | `total_tokens`, `total_cost_usd`, `total_messages`, `session_id` |
| `user_prompt` | `prompt_length`, `model`, `session_id` |

## Traces (Tempo, `{resource.service.name="opencode"}`)

- `opencode.llm` — one per LLM call; attributes: `llm.model_name`, `llm.token_count.*`, `cost_usd`, `llm.finish_reason`, `input.value`, `output.value`
- `opencode.tool.<name>` — one per tool call; attributes: `tool.name`, `tool.parameters`, `tool.success`, `output.value`
- `session.id` is a **span attribute** (not resource), so TraceQL filters use `.session.id`

!!! note
    Traces are retained for **24 hours** by default (see `tempo.yaml`).
