# OpenCode Observability Stack

A self-contained observability stack for [OpenCode](https://opencode.ai), built on the
[`@devtheops/opencode-plugin-otel`](https://www.npmjs.com/package/@devtheops/opencode-plugin-otel)
plugin. Ships a Grafana dashboard with cost/token analytics, TraceQL-based explainability, and
a standalone session timeline (waterfall) explorer.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Docker Compose v2+
- [`just`](https://github.com/casey/just) (optional)
- [OpenCode](https://opencode.ai) with the [`@devtheops/opencode-plugin-otel`](https://www.npmjs.com/package/@devtheops/opencode-plugin-otel) plugin
- For local Trace Explorer development only (`just dev-trace-explorer`): [`uv`](https://docs.astral.sh/uv/) and [Node.js](https://nodejs.org/) 22+

## Features

- **Cost & token analytics** — usage by model, agent, and session; breakdown by token type
- **Tool usage** — call counts, average duration, and success rate per tool
- **Productivity** — lines added/removed, message counts per session
- **TraceQL tables** — LLM calls (prompt → model → outcome) and tool calls (tool → params → result)
- **Trace → Logs linking** — click a span in Grafana to jump to matching Loki logs
- **Trace Explorer** — React/FastAPI waterfall SPA with session timelines, subagent linking, and a
  cross-session usage dashboard
- **Dashboard filters** — `session_id`, `model`, and `agent` template variables apply to every panel

## Where to go next

- [Architecture](architecture.md) — how the services fit together
- [Quick Start](quick-start.md) — start the stack and connect OpenCode
- [Metrics, Logs & Traces](telemetry.md) — what's exported and how to query it
- [Dashboard](dashboard.md) — the Grafana "OpenCode Observability" dashboard
- [Trace Explorer](trace-explorer.md) — the standalone waterfall UI
- [Configuration](configuration.md) — collector, Tempo, and Grafana datasource details
- [Development](development.md) — `just` targets and local dev workflow

## License

[MIT](https://github.com/schemaitat/opencode-otel-observability/blob/main/LICENSE)
