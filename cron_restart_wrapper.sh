#!/bin/bash
# Wrapper script for cron restarts - EMQX Edition
# Simpler than AWS IoT version - no Podman environment needed (using Docker instead)

# Detect project directory (script is in project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Enable lingering for user (allows user processes without active session)
loginctl enable-linger $(whoami) 2>/dev/null || true

# Change to project directory and run restart
cd "$SCRIPT_DIR"
exec /bin/bash ./scripts/managed_start.sh restart
