#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/logs/gateway.log"

mapfile -t pids < <(lsof -ti tcp:4000 || true)
if [[ ${#pids[@]} -gt 0 ]]; then
    echo "Stopping gateway (pids ${pids[*]})..."
    kill "${pids[@]}"
    sleep 1
fi

echo "Starting gateway..."
cd "$SCRIPT_DIR"
nohup uv run gateway >> "$LOG_FILE" 2>&1 &
echo "Started (pid $!), logging to $LOG_FILE"
