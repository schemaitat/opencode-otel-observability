#!/usr/bin/env bash
set -euo pipefail

plugin=""
for f in ".opencode/opencode.json" "opencode.json" "$HOME/.config/opencode/opencode.json"; do
    [[ -f "$f" ]] || continue
    entry=$(python3 - "$f" <<'EOF'
import json, sys
cfg = json.load(open(sys.argv[1]))
hits = [p for p in cfg.get("plugin", []) if "opencode-plugin-otel" in p]
print(hits[0] if hits else "", end="")
EOF
)
    [[ -n "$entry" ]] && plugin="$entry" && echo "plugin : $entry" && echo "source : $f" && break
done

[[ -n "$plugin" ]] || { echo "FAIL: opencode-plugin-otel not found in any config"; exit 1; }

if [[ "$plugin" == *"file:"* ]]; then
    path="${plugin##*file:}"
    [[ -f "$path/dist/index.js" ]] \
        && echo "dist   : OK ($path/dist/index.js)" \
        || { echo "FAIL: dist/index.js missing — cd $path && bun run build"; exit 1; }
else
    echo "dist   : OK (npm — opencode installs on startup)"
fi

[[ "${OPENCODE_ENABLE_TELEMETRY:-}" == "1" ]] \
    && echo "env    : OPENCODE_ENABLE_TELEMETRY=1" \
    || echo "WARN   : OPENCODE_ENABLE_TELEMETRY not set"
[[ -n "${OPENCODE_OTLP_ENDPOINT:-}" ]] \
    && echo "env    : OPENCODE_OTLP_ENDPOINT=${OPENCODE_OTLP_ENDPOINT}" \
    || echo "WARN   : OPENCODE_OTLP_ENDPOINT not set"
