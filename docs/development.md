# Development

## Just Targets

```bash
just up                    # Start the stack
just down                  # Stop the stack
just restart               # Restart the stack
just status                # Show status and service URLs
just logs                  # Tail logs from all services
just logs-collector        # Tail otel-collector logs
just logs-prometheus       # Tail prometheus logs
just logs-tempo            # Tail tempo logs
just logs-grafana          # Tail grafana logs
just logs-trace-explorer   # Tail trace-explorer logs
just dev-trace-explorer    # Run trace-explorer backend + frontend locally (port 8060)
just docs                  # Serve the documentation site locally
just validate-config       # Validate docker-compose and collector configs
just setup-opencode        # Show OpenCode telemetry setup instructions
just run-opencode          # Run opencode with telemetry env vars exported
just clean                 # Stop and remove volumes
```

## Resources

- [OpenCode](https://opencode.ai)
- [`@devtheops/opencode-plugin-otel`](https://www.npmjs.com/package/@devtheops/opencode-plugin-otel)
- [OTel Collector docs](https://opentelemetry.io/docs/collector/)
- [Prometheus docs](https://prometheus.io/docs/)
- [Grafana docs](https://grafana.com/docs/)
- [Loki docs](https://grafana.com/docs/loki/)
- [Tempo docs](https://grafana.com/docs/tempo/)

## Building the Docs Locally

```bash
just docs
```

Then open http://127.0.0.1:8000.
