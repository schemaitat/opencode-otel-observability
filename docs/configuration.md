# Advanced Configuration

## Collector ([`collector-config.yaml`](https://github.com/aschemaitat/opencode-otel-observability/blob/main/collector-config.yaml))

Single OTLP receiver (gRPC `4317` / HTTP `4318`) feeding three pipelines:

- **metrics** → Prometheus exporter (`:8889`)
- **logs** → Loki via `otlphttp`
- **traces** → Tempo via `otlp/tempo` (gRPC)

A `resource` processor tags all telemetry with `environment=production`.

## Tempo ([`tempo.yaml`](https://github.com/aschemaitat/opencode-otel-observability/blob/main/tempo.yaml))

Local block storage with a 24h retention window. Increase
`compactor.compaction.block_retention` for longer retention.

## Trace → Logs Linking ([`grafana-datasources.yml`](https://github.com/aschemaitat/opencode-otel-observability/blob/main/grafana-datasources.yml))

Maps the `session.id` span attribute to the Loki `session_id` label so clicking a span
jumps to the matching session logs:

```yaml
jsonData:
  tracesToLogsV2:
    datasourceUid: loki
    customQuery: true
    query: '{service_name="opencode"} | session_id="${__span.tags["session.id"]}"'
```

!!! note
    `$` in `${__span.tags[...]}` is escaped as `$$` in the YAML to survive Grafana's
    provisioning environment-variable interpolation.
