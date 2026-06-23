# OpenCode Observability Stack

default:
    @just --list

setup: ## Full setup: clone+build plugin, configure opencode.json, start the stack
    bash scripts/setup.sh

up: ## Start the observability stack
    docker compose up -d
    @echo "Grafana:          http://localhost:3000 (admin/admin)"
    @echo "Prometheus:       http://localhost:9090"
    @echo "Loki:             http://localhost:3100"
    @echo "Tempo:            http://localhost:3200"
    @echo "Trace Explorer:   http://localhost:8060"

build: ## Build all images
    docker compose build

down: ## Stop the observability stack
    docker compose down

restart: ## Restart the observability stack
    docker compose restart

logs: ## Show logs from all services
    docker compose logs -f

logs-collector: ## Show OpenTelemetry collector logs
    docker compose logs -f otel-collector

logs-prometheus: ## Show Prometheus logs
    docker compose logs -f prometheus

logs-tempo: ## Show Tempo logs
    docker compose logs -f tempo

logs-grafana: ## Show Grafana logs
    docker compose logs -f grafana

logs-trace-explorer: ## Show Trace Explorer logs
    docker compose logs -f trace-explorer

dev-trace-explorer: ## Run Trace Explorer backend + frontend locally (requires `just up`)
    #!/usr/bin/env bash
    set -euo pipefail
    cd trace-explorer/backend && TEMPO_URL=http://localhost:3200 uv run uvicorn main:app --port 8060 --reload &
    backend_pid=$!
    trap "kill $backend_pid" EXIT
    cd trace-explorer/frontend && npm run dev

docs: ## Serve the documentation site locally
    uvx --with mkdocs-material mkdocs serve

validate-config: ## Validate all configuration files
    #!/usr/bin/env bash
    set -euo pipefail
    docker compose config > /dev/null && echo "docker-compose.yml: valid"
    if command -v otelcol-contrib >/dev/null 2>&1; then
        otelcol-contrib --config-validate --config=collector-config.yaml
    else
        echo "collector-config.yaml: install otelcol-contrib to validate"
    fi

status: ## Show stack status and service URLs
    @docker compose ps
    @echo ""
    @echo "Grafana:          http://localhost:3000"
    @echo "Prometheus:       http://localhost:9090"
    @echo "Loki:             http://localhost:3100"
    @echo "Tempo:            http://localhost:3200"
    @echo "Trace Explorer:   http://localhost:8060"
    @echo "Collector:        http://localhost:4317 (gRPC), http://localhost:4318 (HTTP)"

run-opencode: ## Run opencode with OTLP telemetry pointed at this stack
    OPENCODE_ENABLE_TELEMETRY=1 \
    OPENCODE_OTLP_ENDPOINT=http://localhost:4317 \
    OPENCODE_OTLP_PROTOCOL=grpc \
    OPENCODE_OTLP_METRICS_INTERVAL=2000 \
    OPENCODE_OTLP_LOGS_INTERVAL=2000 \
    opencode

setup-opencode: ## Print opencode telemetry setup instructions
    @printf 'opencode Telemetry Setup\n\n'
    @printf '1. Add the otel plugin to ~/.config/opencode/opencode.json (or project opencode.json):\n\n'
    @printf '   {\n     "$schema": "https://opencode.ai/config.json",\n     "plugin": ["@devtheops/opencode-plugin-otel"]\n   }\n\n'
    @printf '2. Set environment variables:\n\n'
    @printf '   export OPENCODE_ENABLE_TELEMETRY=1\n'
    @printf '   export OPENCODE_OTLP_ENDPOINT=http://localhost:4317\n'
    @printf '   export OPENCODE_OTLP_PROTOCOL=grpc\n\n'
    @printf 'For faster debug intervals also set:\n\n'
    @printf '   export OPENCODE_OTLP_METRICS_INTERVAL=2000\n'
    @printf '   export OPENCODE_OTLP_LOGS_INTERVAL=2000\n\n'
    @printf 'Traces are viewable in Grafana (http://localhost:3000) via Tempo datasource -> Explore.\n'
