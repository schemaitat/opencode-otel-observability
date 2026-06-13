# OpenCode Observability Stack

[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue?logo=docker)](docker-compose.yml)

A self-contained observability stack for [OpenCode](https://opencode.ai), built on the
[`@devtheops/opencode-plugin-otel`](https://www.npmjs.com/package/@devtheops/opencode-plugin-otel)
plugin. Ships a Grafana dashboard with cost/token analytics, TraceQL-based explainability, and
a standalone session timeline (waterfall) explorer.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Docker Compose v2+
- [`just`](https://github.com/casey/just) (optional)
- [OpenCode](https://opencode.ai) with the [`@devtheops/opencode-plugin-otel`](https://www.npmjs.com/package/@devtheops/opencode-plugin-otel) plugin

## Features

- **Cost & token analytics** — usage by model, agent, and session; breakdown by token type
- **Tool usage** — call counts, average duration, and success rate per tool
- **Productivity** — lines added/removed, message counts per session
- **TraceQL tables** — LLM calls (prompt → model → outcome) and tool calls (tool → params → result)
- **Trace → Logs linking** — click a span in Grafana to jump to matching Loki logs
- **Session Explorer** — standalone waterfall UI with narrative, stat cards, and per-span detail
- **Dashboard filters** — `session_id`, `model`, and `agent` template variables apply to every panel

## Architecture

```
OpenCode (@devtheops/opencode-plugin-otel)
        │ OTLP (metrics, logs, traces)
        ▼
OpenTelemetry Collector
        │
        ├── Prometheus  (opencode_* metrics)
        ├── Loki        (structured event logs)
        └── Tempo       (LLM + tool call traces)
        │
        ▼
Grafana (dashboards) + Session Explorer (standalone waterfall UI)
```

| Service | Purpose | Port | UI |
|---------|---------|------|----|
| **OTel Collector** | Metrics/logs/traces ingestion | 4317 (gRPC), 4318 (HTTP) | — |
| **Prometheus** | Metrics storage | 9090 | http://localhost:9090 |
| **Loki** | Log aggregation | 3100 | — |
| **Tempo** | Trace storage | 3200 | http://localhost:3200 |
| **Session Explorer** | Session waterfall UI | 8050 | http://localhost:8050 |
| **Grafana** | Dashboards | 3000 | http://localhost:3000 |

## Quick Start

**1. Start the stack**

```bash
docker compose up -d
# or: just up
```

**2. Configure OpenCode**

Add the plugin to `~/.config/opencode/opencode.json` (or a project-level `opencode.json`).
The [`opencode.json`](opencode.json) in this repo is a ready-to-use example:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["@devtheops/opencode-plugin-otel"]
}
```

Export these environment variables before running `opencode`:

```bash
export OPENCODE_ENABLE_TELEMETRY=1
export OPENCODE_OTLP_ENDPOINT=http://localhost:4317
export OPENCODE_OTLP_PROTOCOL=grpc

# Faster export intervals for debugging
export OPENCODE_OTLP_METRICS_INTERVAL=10000
export OPENCODE_OTLP_LOGS_INTERVAL=5000
```

Or use `just run-opencode` to launch `opencode` with these variables already set.

**3. Open the dashboards**

| URL | Service |
|-----|---------|
| http://localhost:3000 | Grafana — "OpenCode Observability" (admin/admin) |
| http://localhost:9090 | Prometheus |
| http://localhost:3200 | Tempo |
| http://localhost:8050 | Session Explorer |

## Metrics, Logs & Traces

### Metrics (Prometheus, `opencode_*`)

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

### Logs (Loki, `{service_name="opencode"}`)

Key `event_name` values:

| Event | Key attributes |
|-------|----------------|
| `api_request` | `model`, `duration_ms`, token counts, `cost_usd`, `provider`, `session_id` |
| `tool_result` | `tool_name`, `success`, `duration_ms`, `tool_result_size_bytes`, `session_id` |
| `session.idle` / `session.created` / `session.error` | `total_tokens`, `total_cost_usd`, `total_messages`, `session_id` |
| `user_prompt` | `prompt_length`, `model`, `session_id` |

### Traces (Tempo, `{resource.service.name="opencode"}`)

- `opencode.llm` — one per LLM call; attributes: `llm.model_name`, `llm.token_count.*`, `cost_usd`, `llm.finish_reason`, `input.value`, `output.value`
- `opencode.tool.<name>` — one per tool call; attributes: `tool.name`, `tool.parameters`, `tool.success`, `output.value`
- `session.id` is a **span attribute** (not resource), so TraceQL filters use `.session.id`

## Dashboard

The "OpenCode Observability" dashboard ([`opencode-dashboard.json`](opencode-dashboard.json))
is filterable by `$session_id`, `$model`, and `$agent`:

- **Overview** — active sessions, total cost, total tokens, tool calls, messages, lines changed
- **Model Usage** — cost/token/request breakdowns by model and provider
- **Agent Activity** — cost/token/request breakdowns by agent
- **Tool Usage** — call counts, avg duration, success rate
- **Explainability** — LLM calls table and tool calls table via Tempo TraceQL `select()`
- **Traces** — recent trace list with drill-down and linked Loki logs
- **Event Logs** — API requests, tool results, session lifecycle (Loki)

## Session Explorer

[`session-dashboard/`](session-dashboard/) is a Dash app (`session-dashboard` service):

- Dropdown to pick any session (populated from Prometheus label values)
- Stat cards: LLM calls, tool calls, total cost, total tokens, wall-clock time
- Plotly waterfall of every LLM/tool call, color-coded by type
- Generated step-by-step narrative of the session
- Click any bar for full span detail (prompt, output, tokens, cost, finish reason)

Connects to Tempo (`TEMPO_URL`, default `http://tempo:3200`) and Prometheus
(`PROMETHEUS_URL`, default `http://prometheus:9090`).

## Advanced Configuration

### Collector ([`collector-config.yaml`](collector-config.yaml))

Single OTLP receiver (gRPC `4317` / HTTP `4318`) feeding three pipelines:

- **metrics** → Prometheus exporter (`:8889`)
- **logs** → Loki via `otlphttp`
- **traces** → Tempo via `otlp/tempo` (gRPC)

A `resource` processor tags all telemetry with `environment=production`.

### Tempo ([`tempo.yaml`](tempo.yaml))

Local block storage with a 24h retention window. Increase
`compactor.compaction.block_retention` for longer retention.

### Trace → Logs Linking ([`grafana-datasources.yml`](grafana-datasources.yml))

Maps the `session.id` span attribute to the Loki `session_id` label so clicking a span
jumps to the matching session logs:

```yaml
jsonData:
  tracesToLogsV2:
    datasourceUid: loki
    customQuery: true
    query: '{service_name="opencode"} | session_id="${__span.tags["session.id"]}"'
```

> Note: `$` in `${__span.tags[...]}` is escaped as `$$` in the YAML to survive Grafana's
> provisioning environment-variable interpolation.

## Just Targets

```bash
just up              # Start the stack
just down            # Stop the stack
just restart         # Restart the stack
just status          # Show status and service URLs
just logs            # Tail logs from all services
just validate-config # Validate docker-compose and collector configs
just setup-opencode  # Show OpenCode telemetry setup instructions
just run-opencode    # Run opencode with telemetry env vars exported
just clean           # Stop and remove volumes
```

## Resources

- [OpenCode](https://opencode.ai)
- [`@devtheops/opencode-plugin-otel`](https://www.npmjs.com/package/@devtheops/opencode-plugin-otel)
- [OTel Collector docs](https://opentelemetry.io/docs/collector/)
- [Prometheus docs](https://prometheus.io/docs/)
- [Grafana docs](https://grafana.com/docs/)
- [Loki docs](https://grafana.com/docs/loki/)
- [Tempo docs](https://grafana.com/docs/tempo/)

## License

[MIT](LICENSE)
