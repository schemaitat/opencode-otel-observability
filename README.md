# OpenCode Observability Stack

[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue?logo=docker)](docker-compose.yml)

A self-contained observability stack for [OpenCode](https://opencode.ai), built on the
[`@devtheops/opencode-plugin-otel`](https://www.npmjs.com/package/@devtheops/opencode-plugin-otel)
OpenTelemetry plugin. It ships a Grafana dashboard with agent-aware cost/token analytics,
TraceQL-based explainability, and a standalone session timeline (waterfall) explorer
for drilling into a single run end-to-end.

## 🎯 Features

### 📊 Comprehensive Monitoring
- **Cost Analysis**: Track usage cost by model, agent, and session
- **Token Usage**: Breakdown by type (input/output/cache read/cache creation/reasoning) and by model/agent
- **Tool Usage**: Call counts, average duration, and success rate per tool
- **Productivity Insights**: Lines of code added/removed, message counts per session

### 🔍 Explainability & Tracing
- **TraceQL Tables**: LLM calls (prompt → model → outcome) and tool calls (tool → parameters → result), surfaced directly as Grafana table panels
- **Recent Traces**: Browse and drill into individual traces/spans via Tempo
- **Trace → Logs linking**: Click a span and jump to the matching Loki logs for that session
- **Session Timeline**: Standalone Dash app rendering a waterfall of every LLM/tool call in a session, with a generated narrative and per-span detail view

### 🎛️ Filtering
- Dashboard-wide `session_id`, `model`, and `agent` template variables filter every panel (metrics, logs, and traces) so you can isolate a single run

## 🏗️ Architecture

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

### Components

| Service | Purpose | Port | UI |
|---------|---------|------|----|
| **OpenTelemetry Collector** | Metrics/logs/traces ingestion | 4317 (gRPC), 4318 (HTTP) | - |
| **Prometheus** | Metrics storage & querying | 9090 | http://localhost:9090 |
| **Loki** | Log aggregation & storage | 3100 | - |
| **Tempo** | Trace storage & querying | 3200 | http://localhost:3200 |
| **Session Explorer** | Standalone session timeline/waterfall UI | 8050 | http://localhost:8050 |
| **Grafana** | Dashboards & visualization | 3000 | http://localhost:3000 |

## 🚀 Quick Start

### 1. Start the Stack

```bash
docker compose up -d
# or
make up
```

### 2. Configure OpenCode

Add the OTel plugin to `~/.config/opencode/opencode.json` (or a project-level `opencode.json`,
see [`opencode.json`](opencode.json) for an example):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["@devtheops/opencode-plugin-otel"]
}
```

Then set the following environment variables and run `opencode`:

```bash
export OPENCODE_ENABLE_TELEMETRY=1
export OPENCODE_OTLP_ENDPOINT=http://localhost:4317
export OPENCODE_OTLP_PROTOCOL=grpc

# For debugging (faster export intervals)
export OPENCODE_OTLP_METRICS_INTERVAL=10000
export OPENCODE_OTLP_LOGS_INTERVAL=5000
```

Or run `make setup-opencode` for these instructions at any time.

### 3. Access the Dashboards

- **Grafana**: http://localhost:3000 (admin/admin) → "OpenCode Observability" dashboard
- **Prometheus**: http://localhost:9090
- **Tempo**: http://localhost:3200
- **Session Explorer**: http://localhost:8050

## 📊 Metrics, Logs & Traces

### Metrics (Prometheus, `opencode_*`)

All metrics are cumulative per-session counters exported via the `otel-collector` job:

- `opencode_session_count_total{session_id, is_subagent}` - sessions started
- `opencode_cost_usage_USD_total{session_id, model, agent}` - cost by model and agent
- `opencode_token_usage_tokens_total{session_id, model, agent, type}` - token usage by type (`input`/`output`/`cache_read`/`cache_creation`/`reasoning`)
- `opencode_model_usage_total{session_id, model, agent, provider}` - request counts by model/provider/agent
- `opencode_message_count_total{session_id, model, agent}` - message counts
- `opencode_tool_duration_milliseconds_{count,sum,bucket}{session_id, tool_name, success}` - tool call counts/durations
- `opencode_lines_of_code_total` / `_count_total{session_id, type=added|removed}` - lines of code changed
- `opencode_cache_count_total{session_id, model, type=cacheRead|...}` - prompt cache hits

### Logs (Loki, `{service_name="opencode"}`)

Key `event_name` values:

- `api_request` - model, duration_ms, input/output/cache tokens, cost_usd, provider, session_id
- `tool_result` - tool_name, success, duration_ms, tool_result_size_bytes, session_id
- `session.idle` / `session.created` / `session.error` - total_tokens, total_cost_usd, total_messages, session_id
- `user_prompt` - prompt_length, model, session_id

### Traces (Tempo, `{resource.service.name="opencode"}`)

- Root span `opencode.llm` - one per LLM call, with attributes like `llm.model_name`,
  `llm.token_count.*`, `cost_usd`, `llm.finish_reason`, `input.value`/`output.value`
- Root span `opencode.tool.<name>` - one per tool call, with attributes like `tool.name`,
  `tool.parameters`, `tool.success`, `output.value`
- `session.id` is a **span attribute** (not a resource attribute), so TraceQL filters use `.session.id`

## 📋 Dashboard Sections

The "OpenCode Observability" Grafana dashboard ([`opencode-dashboard.json`](opencode-dashboard.json))
is filterable by `$session_id`, `$model`, and `$agent` template variables and is organized as:

### 📊 Overview
Active Sessions, Total Cost (USD), Total Tokens, Tool Calls, Messages, Lines Changed (+/-)

### 📊 Model Usage
Cost by Model, Token Usage by Model, Requests by Model/Provider (table), Token Usage by Type

### 🤖 Agent & Model Activity
Cost by Agent, Token Usage by Agent, Requests by Agent/Model/Provider (table)

### 🔧 Tool Usage
Tool Calls by Tool, Avg Tool Duration by Tool, Tool Success Rate (bar gauge)

### 🔍 Explainability: Calls & Reasoning
- **LLM Calls** table: prompt content, model name, finish reason, cost, duration - via Tempo TraceQL `select()`
- **Tool Calls** table: tool name, parameters, success status, output, duration - via Tempo TraceQL `select()`

### 📊 Traces & Drill-down
- **Session Timeline**: waterfall visualization of all LLM and tool calls within a session (requires the `auxmoney-waterfall-panel` Grafana plugin)
- **Recent Traces**: Tempo TraceQL trace list with drill-down to span detail and linked Loki logs (TracesToLogs)

### 📝 Event Logs (Loki)
API Requests, Tool Results, Session Lifecycle

## 🧭 Session Explorer (standalone waterfall UI)

[`session-dashboard/`](session-dashboard/) is a small Dash app, run as the `session-dashboard`
service, that complements the Grafana dashboard:

- Pick any session from a dropdown (populated from Prometheus `session_id` label values)
- See summary stat cards: LLM calls, tool calls, total cost, total tokens, wall-clock time
- A Plotly timeline (waterfall) of every LLM/tool call, color-coded by type
- A generated step-by-step narrative of the session ("Step 1: LLM call to `claude-...`, ...")
- Click any bar to see full span detail (prompt/output, tool parameters/output, tokens, cost, finish reason)

It talks directly to Tempo (`TEMPO_URL`, default `http://tempo:3200`) and Prometheus
(`PROMETHEUS_URL`, default `http://prometheus:9090`).

## 🔧 Advanced Configuration

### Grafana Plugin Requirements

The OpenCode dashboard's Session Timeline panel uses a custom panel type:

- **auxmoney-waterfall-panel** - installed automatically via `GF_INSTALL_PLUGINS` in
  `docker-compose.yml`, or manually via `grafana-cli plugins install auxmoney-waterfall-panel`

### Collector Configuration

[`collector-config.yaml`](collector-config.yaml) configures the OpenTelemetry Collector with
three pipelines, all fed by a single OTLP receiver (gRPC `4317` / HTTP `4318`):

- **metrics** → Prometheus exporter (`:8889`, scraped by Prometheus)
- **logs** → Loki via `otlphttp`
- **traces** → Tempo via `otlp/tempo` (gRPC)

A `resource` processor tags everything with `environment=production`.

### Tempo Configuration

[`tempo.yaml`](tempo.yaml) runs Tempo with local block storage (`/var/tempo/traces` +
WAL) and a 24h compaction/retention window. Increase `compactor.compaction.block_retention`
for longer trace retention.

### Trace → Logs Linking

The `tempo` datasource in [`grafana-datasources.yml`](grafana-datasources.yml) configures
`tracesToLogsV2` to map the `session.id` span attribute to the Loki `session_id` label, so
clicking a span in Grafana's trace view jumps to the matching session logs:

```yaml
jsonData:
  tracesToLogsV2:
    datasourceUid: loki
    customQuery: true
    query: '{service_name="opencode"} | session_id="${__span.tags["session.id"]}"'
```

> Note: the `$` in `${__span.tags[...]}` is escaped as `$$` in the YAML file to survive
> Grafana's provisioning environment-variable interpolation.

## 📖 Make Targets

```bash
make up              # Start the observability stack
make down            # Stop the observability stack
make restart         # Restart the observability stack
make status          # Show stack status and service URLs
make logs            # Tail logs from all services
make validate-config # Validate docker-compose and collector configs
make setup-opencode  # Show OpenCode telemetry setup instructions
make clean           # Stop the stack and remove volumes
```

## 📚 Additional Resources

- [OpenCode](https://opencode.ai)
- [`@devtheops/opencode-plugin-otel`](https://www.npmjs.com/package/@devtheops/opencode-plugin-otel)
- [OpenTelemetry Collector Documentation](https://opentelemetry.io/docs/collector/)
- [Prometheus Documentation](https://prometheus.io/docs/) - Metrics and alerting
- [Grafana Documentation](https://grafana.com/docs/) - Dashboards and visualization
- [Loki Documentation](https://grafana.com/docs/loki/) - Log aggregation
- [Tempo Documentation](https://grafana.com/docs/tempo/) - Distributed tracing
- [auxmoney-waterfall-panel](https://grafana.com/grafana/plugins/auxmoney-waterfall-panel/) - Grafana waterfall panel plugin (required for Session Timeline)

## License

[MIT](LICENSE)
