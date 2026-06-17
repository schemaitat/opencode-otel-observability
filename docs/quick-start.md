# Quick Start

## 1. Start the stack

```bash
docker compose up -d
# or: just up
```

## 2. Configure OpenCode

Add the plugin to `~/.config/opencode/opencode.json` (or a project-level `opencode.json`):

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
export OPENCODE_OTLP_METRICS_INTERVAL=2000
export OPENCODE_OTLP_LOGS_INTERVAL=2000
```

Or use `just run-opencode` to launch `opencode` with these variables already set.

## 3. Open the dashboards

| URL | Service |
|-----|---------|
| http://localhost:3000 | Grafana — "OpenCode Observability" (admin/admin) |
| http://localhost:9090 | Prometheus |
| http://localhost:3100 | Loki — no UI; query via Grafana Explore |
| http://localhost:3200 | Tempo |
| http://localhost:8060 | Trace Explorer |
