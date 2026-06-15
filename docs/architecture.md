# Architecture

```
OpenCode (@devtheops/opencode-plugin-otel)
        │ OTLP (metrics, logs, traces)
        ▼
OpenTelemetry Collector
        │
        ├──────────────────┬──────────────────┐
        ▼                  ▼                  ▼
  Prometheus           Loki               Tempo
(opencode_* metrics) (structured logs) (LLM + tool traces)
        │                  │                  │
        └──────────────────┴──────────────────┘
                           │
                           ▼
           Grafana (dashboards) + Trace Explorer (waterfall UI)
```

| Service | Purpose | Port | UI |
|---------|---------|------|----|
| **OTel Collector** | Metrics/logs/traces ingestion | 4317 (gRPC), 4318 (HTTP) | — |
| **Prometheus** | Metrics storage | 9090 | http://localhost:9090 |
| **Loki** | Log aggregation | 3100 | — |
| **Tempo** | Trace storage | 3200 | http://localhost:3200 |
| **Trace Explorer** | React/FastAPI waterfall SPA | 8060 | http://localhost:8060 |
| **Grafana** | Dashboards | 3000 | http://localhost:3000 |
