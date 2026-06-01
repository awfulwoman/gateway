#!/bin/bash
set -euo pipefail

PLIST_LABEL="com.awfulwoman.gateway"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

UV_PATH="$(which uv 2>/dev/null || true)"
if [ -z "$UV_PATH" ]; then
    echo "Error: uv not found on PATH. Install uv first."
    exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${UV_PATH}</string>
        <string>run</string>
        <string>gateway</string>
        <string>--transport</string>
        <string>http</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${REPO_DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${REPO_DIR}/logs/gateway.log</string>
    <key>StandardErrorPath</key>
    <string>${REPO_DIR}/logs/gateway.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>
PLIST

mkdir -p "${REPO_DIR}/logs"

# Grant TCC permissions for Calendar, Reminders, and Contacts.
# Must use the real path to uv (not a symlink) as TCC matches on the versioned path.
UV_REAL="$(python3 -c "import os; print(os.path.realpath('$UV_PATH'))")"
TCC_DB="$HOME/Library/Application Support/com.apple.TCC/TCC.db"

sqlite3 "$TCC_DB" "
INSERT OR REPLACE INTO access
  (service, client, client_type, auth_value, auth_reason, auth_version, csreq, indirect_object_identifier)
VALUES
  ('kTCCServiceCalendar', 'org.python.python', 0, 2, 3, 1, NULL, 'UNUSED');
INSERT OR REPLACE INTO access
  (service, client, client_type, auth_value, auth_reason, auth_version, csreq, indirect_object_identifier)
VALUES
  ('kTCCServiceCalendar', '$UV_REAL', 1, 2, 3, 1, NULL, 'UNUSED');
INSERT OR REPLACE INTO access
  (service, client, client_type, auth_value, auth_reason, auth_version, csreq, indirect_object_identifier)
VALUES
  ('kTCCServiceReminders', 'org.python.python', 0, 2, 3, 1, NULL, 'UNUSED');
INSERT OR REPLACE INTO access
  (service, client, client_type, auth_value, auth_reason, auth_version, csreq, indirect_object_identifier)
VALUES
  ('kTCCServiceReminders', '$UV_REAL', 1, 2, 3, 1, NULL, 'UNUSED');
INSERT OR REPLACE INTO access
  (service, client, client_type, auth_value, auth_reason, auth_version, csreq, indirect_object_identifier)
VALUES
  ('kTCCServiceAddressBook', 'org.python.python', 0, 2, 3, 1, NULL, 'UNUSED');
INSERT OR REPLACE INTO access
  (service, client, client_type, auth_value, auth_reason, auth_version, csreq, indirect_object_identifier)
VALUES
  ('kTCCServiceAddressBook', '$UV_REAL', 1, 2, 3, 1, NULL, 'UNUSED');
" && echo "Calendar, Reminders, and Contacts TCC permissions granted."

launchctl bootstrap gui/$(id -u) "$PLIST_PATH" 2>/dev/null || launchctl load "$PLIST_PATH"
echo "Gateway service installed and started."
echo "MCP server running at http://127.0.0.1:4000/mcp"
echo ""
echo "Register with Claude Code:"
echo '  claude mcp add --transport http gateway --scope user http://127.0.0.1:4000/mcp'
