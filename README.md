# OpenCode Observability Stack

[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue?logo=docker)](docker-compose.yml)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://schemaitat.github.io/opencode-otel-observability/)

A self-contained observability stack for [OpenCode](https://opencode.ai), built on the
[`@devtheops/opencode-plugin-otel`](https://www.npmjs.com/package/@devtheops/opencode-plugin-otel)
plugin. Ships a Grafana dashboard with cost/token analytics, TraceQL-based explainability, and
a standalone session timeline (waterfall) explorer.

## Screenshots

| Grafana dashboard | Trace Explorer — Overview |
|---|---|
| ![Grafana OpenCode Observability dashboard](docs/images/grafana-overview.png) | ![Trace Explorer Overview view](docs/images/trace-explorer-overview.png) |

| Trace Explorer — Sessions |
|---|
| ![Trace Explorer Sessions view](docs/images/trace-explorer-sessions.png) |

## Quick Start

```bash
docker compose up -d
# or: just up
```

Add the plugin to `~/.config/opencode/opencode.json` (or a project-level `opencode.json`):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["@devtheops/opencode-plugin-otel"]
}
```

Export telemetry environment variables before running `opencode` (or use `just run-opencode`):

```bash
export OPENCODE_ENABLE_TELEMETRY=1
export OPENCODE_OTLP_ENDPOINT=http://localhost:4317
export OPENCODE_OTLP_PROTOCOL=grpc
```

Then open:

| URL | Service |
|-----|---------|
| http://localhost:3000 | Grafana — "OpenCode Observability" (admin/admin) |
| http://localhost:8060 | Trace Explorer |
| http://localhost:9090 | Prometheus |
| http://localhost:3200 | Tempo |

See the [Quick Start guide](https://schemaitat.github.io/opencode-otel-observability/quick-start/)
for the full walkthrough.

## Features

- **Cost & token analytics** — usage by model, agent, and session; breakdown by token type
- **Tool usage** — call counts, average duration, and success rate per tool
- **Productivity** — lines added/removed, message counts per session
- **TraceQL tables** — LLM calls (prompt → model → outcome) and tool calls (tool → params → result)
- **Trace → Logs linking** — click a span in Grafana to jump to matching Loki logs
- **Trace Explorer** — React/FastAPI waterfall SPA with session timelines, subagent linking, and a
  cross-session usage dashboard
- **Dashboard filters** — `session_id`, `model`, and `agent` template variables apply to every panel

## Documentation

Full documentation is published at
**[schemaitat.github.io/opencode-otel-observability](https://schemaitat.github.io/opencode-otel-observability/)**,
or browse it directly in [`docs/`](docs/):

- [Architecture](docs/architecture.md) — how the services fit together
- [Quick Start](docs/quick-start.md) — start the stack and connect OpenCode
- [Metrics, Logs & Traces](docs/telemetry.md) — what's exported and how to query it
- [Dashboard](docs/dashboard.md) — the Grafana "OpenCode Observability" dashboard
- [Trace Explorer](docs/trace-explorer.md) — the standalone waterfall + usage dashboard UI
- [Configuration](docs/configuration.md) — collector, Tempo, and Grafana datasource details
- [Development](docs/development.md) — `just` targets and local dev workflow

## License

[MIT](LICENSE)
