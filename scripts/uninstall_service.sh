#!/bin/bash
set -euo pipefail

PLIST_LABEL="com.awfulwoman.gateway"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

if [ -f "$PLIST_PATH" ]; then
    launchctl bootout gui/$(id -u) "$PLIST_PATH" 2>/dev/null || launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm "$PLIST_PATH"
    echo "Gateway service removed."
else
    echo "No service found at $PLIST_PATH"
fi
