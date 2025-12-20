#!/bin/bash
# Wrapper script for cron restarts - EMQX Edition
# Simpler than AWS IoT version - no Podman environment needed (using Docker instead)

# Enable lingering for user (allows user processes without active session)
loginctl enable-linger satinder 2>/dev/null || true

# Change to project directory and run restart
cd /home/satinder/camera-platform-local
exec /bin/bash ./scripts/managed_start.sh restart
