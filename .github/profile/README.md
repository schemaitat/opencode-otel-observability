# OpenCode Observability Stack

Self-contained observability stack for [OpenCode](https://opencode.ai), built on the [`@devtheops/opencode-plugin-otel`](https://www.npmjs.com/package/@devtheops/opencode-plugin-otel) plugin.

Ships a **Grafana dashboard** with cost/token analytics, TraceQL-based explainability, and a standalone **Trace Explorer** session timeline (waterfall) explorer.

## Quick Links

- **[Full Documentation](https://schemaitat.github.io/opencode-otel-observability/)** — Architecture, quick start, configuration, and API reference
- **[Quick Start Guide](https://schemaitat.github.io/opencode-otel-observability/quick-start/)** — Get the stack running in 5 minutes
- **[Architecture](https://schemaitat.github.io/opencode-otel-observability/architecture/)** — How the services fit together
- **[Trace Explorer](https://schemaitat.github.io/opencode-otel-observability/trace-explorer/)** — Waterfall UI and cross-session analytics

## Key Features

- **Cost & token analytics** — usage by model, agent, and session; breakdown by token type
- **Tool usage** — call counts, average duration, and success rate per tool
- **Productivity metrics** — lines added/removed, message counts per session
- **TraceQL tables** — LLM calls (prompt → model → outcome) and tool calls (tool → params → result)
- **Trace → Logs linking** — click a span in Grafana to jump to matching Loki logs
- **Trace Explorer** — React/FastAPI SPA with waterfall timelines, subagent linking, and cross-session dashboard

## Try It Now

```bash
docker compose up -d
# or: just up
```

Then open:
- **Grafana** — http://localhost:3000 (admin/admin)
- **Trace Explorer** — http://localhost:8060
- **Prometheus** — http://localhost:9090
- **Tempo** — http://localhost:3200

See the [Quick Start guide](https://schemaitat.github.io/opencode-otel-observability/quick-start/) for the full walkthrough.

## License

[MIT](../LICENSE)
