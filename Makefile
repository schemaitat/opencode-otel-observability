# OpenCode Observability Stack
.PHONY: help up down logs restart clean validate-config status setup-opencode

help: ## Show this help message
	@echo "OpenCode Observability Stack"
	@echo "================================"
	@echo ""
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

up: ## Start the observability stack
	@echo "🚀 Starting OpenCode observability stack..."
	docker compose up -d
	@echo "✅ Stack started!"
	@echo "📊 Grafana: http://localhost:3000 (admin/admin)"
	@echo "🔍 Prometheus: http://localhost:9090"
	@echo "📄 Loki: http://localhost:3100"
	@echo "🔭 Tempo: http://localhost:3200"
	@echo "🧭 Session Explorer: http://localhost:8050"

down: ## Stop the observability stack
	@echo "🛑 Stopping OpenCode observability stack..."
	docker compose down
	@echo "✅ Stack stopped!"

restart: ## Restart the observability stack
	@echo "🔄 Restarting OpenCode observability stack..."
	docker compose restart
	@echo "✅ Stack restarted!"

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

logs-session-dashboard: ## Show Session Explorer logs
	docker compose logs -f session-dashboard

clean: ## Clean up containers and volumes
	@echo "🧹 Cleaning up..."
	docker compose down -v
	docker system prune -f
	@echo "✅ Cleanup complete!"

validate-config: ## Validate all configuration files
	@echo "✅ Validating configurations..."
	@echo "📋 Checking docker compose.yml..."
	docker compose config > /dev/null && echo "✅ docker compose.yml is valid"
	@echo "📋 Checking collector-config.yaml..."
	@if command -v otelcol-contrib >/dev/null 2>&1; then \
		otelcol-contrib --config-validate --config=collector-config.yaml; \
	else \
		echo "ℹ️  Install otelcol-contrib to validate collector config"; \
	fi

status: ## Show stack status
	@echo "📊 OpenCode Observability Stack Status"
	@echo "==========================================="
	@docker compose ps
	@echo ""
	@echo "🌐 Service URLs:"
	@echo "  Grafana:           http://localhost:3000"
	@echo "  Prometheus:        http://localhost:9090"
	@echo "  Loki:              http://localhost:3100"
	@echo "  Tempo:             http://localhost:3200"
	@echo "  Session Explorer:  http://localhost:8050"
	@echo "  Collector:         http://localhost:4317 (gRPC), http://localhost:4318 (HTTP)"

setup-opencode: ## Display opencode telemetry setup instructions
	@echo "🤖 opencode Telemetry Setup"
	@echo "==============================="
	@echo ""
	@echo "1. Install the otel plugin in ~/.config/opencode/opencode.json (or project opencode.json):"
	@echo ""
	@echo '{'
	@echo '  "\$$schema": "https://opencode.ai/config.json",'
	@echo '  "plugin": ["@devtheops/opencode-plugin-otel"]'
	@echo '}'
	@echo ""
	@echo "2. Set these environment variables:"
	@echo ""
	@echo "export OPENCODE_ENABLE_TELEMETRY=1"
	@echo "export OPENCODE_OTLP_ENDPOINT=http://localhost:4317"
	@echo "export OPENCODE_OTLP_PROTOCOL=grpc"
	@echo ""
	@echo "For debugging (faster export intervals):"
	@echo "export OPENCODE_OTLP_METRICS_INTERVAL=10000"
	@echo "export OPENCODE_OTLP_LOGS_INTERVAL=5000"
	@echo ""
	@echo "Then run: opencode"
	@echo ""
	@echo "Traces are viewable in Grafana (http://localhost:3000) via the Tempo datasource → Explore."
