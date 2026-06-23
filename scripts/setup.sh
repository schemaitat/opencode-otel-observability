#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_DIR="$HOME/projects/opencode-plugin-otel"
PLUGIN_REPO="https://github.com/schemaitat/opencode-plugin-otel"
OPENCODE_CONFIG="$HOME/.config/opencode/opencode.json"

# 0. Check prerequisites
for cmd in docker bun; do
    command -v "$cmd" >/dev/null 2>&1 || { echo "Error: '$cmd' is not installed."; exit 1; }
done
docker compose version >/dev/null 2>&1 || { echo "Error: 'docker compose' (v2) is not available."; exit 1; }

# 1. Clone plugin
if [ ! -d "$PLUGIN_DIR" ]; then
    echo ">>> Cloning plugin..."
    git clone "$PLUGIN_REPO" "$PLUGIN_DIR"
else
    echo ">>> Plugin already present at $PLUGIN_DIR"
fi

# 2. Build plugin (subshell keeps CWD unchanged)
echo ">>> Building plugin..."
(cd "$PLUGIN_DIR" && bun install --frozen-lockfile && bun run build)

# 3. Configure opencode.json (idempotent)
PLUGIN_URI="file://$PLUGIN_DIR"
if [ -f "$OPENCODE_CONFIG" ]; then
    python3 - "$OPENCODE_CONFIG" "$PLUGIN_URI" <<'EOF'
import json, sys
path, uri = sys.argv[1], sys.argv[2]
with open(path) as f:
    c = json.load(f)
c.setdefault("plugin", [])
if uri not in c["plugin"]:
    c["plugin"].append(uri)
    with open(path, "w") as f:
        json.dump(c, f, indent=2)
        f.write("\n")
    print(f">>> Added {uri} to opencode.json")
else:
    print(f">>> Plugin already in opencode.json")
EOF
else
    echo ">>> Warning: $OPENCODE_CONFIG not found — skipping opencode.json config"
fi

# 4. Start the stack
echo ">>> Starting observability stack..."
docker compose -f "$SCRIPT_DIR/../docker-compose.yml" up -d

echo ""
echo "Done. Run opencode with telemetry:"
echo "  just run-opencode"
echo ""
echo "Or export env vars and run opencode directly:"
echo "  export OPENCODE_ENABLE_TELEMETRY=1"
echo "  export OPENCODE_OTLP_ENDPOINT=http://localhost:4317"
echo "  export OPENCODE_OTLP_PROTOCOL=grpc"
