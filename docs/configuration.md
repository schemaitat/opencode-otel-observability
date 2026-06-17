# Advanced Configuration

## Collector ([`collector-config.yaml`](https://github.com/schemaitat/opencode-otel-observability/blob/main/collector-config.yaml))

Single OTLP receiver (gRPC `4317` / HTTP `4318`) feeding three pipelines:

- **metrics** → Prometheus exporter (`:8889`)
- **logs** → Loki via `otlphttp`
- **traces** → Tempo via `otlp/tempo` (gRPC)

A `resource` processor tags all telemetry with `environment=production`. Change the value in `collector-config.yaml` to match your environment.

## Tempo ([`tempo.yaml`](https://github.com/schemaitat/opencode-otel-observability/blob/main/tempo.yaml))

Local block storage with a 24h retention window. Increase
`compactor.compaction.block_retention` for longer retention.

## Trace → Logs Linking ([`grafana-datasources.yml`](https://github.com/schemaitat/opencode-otel-observability/blob/main/grafana-datasources.yml))

Maps the `session.id` span attribute to the Loki `session_id` label so clicking a span
jumps to the matching session logs:

```yaml
jsonData:
  tracesToLogsV2:
    datasourceUid: loki
    customQuery: true
    query: '{service_name="opencode"} | session_id="$${__span.tags["session.id"]}"'
```

!!! note
    `$$` in `$${__span.tags[...]}` is how Grafana provisioning escapes a literal `$` to
    prevent environment-variable interpolation. At runtime Grafana evaluates it as
    `${__span.tags["session.id"]}`.
