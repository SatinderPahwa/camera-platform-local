#!/bin/bash
# Wrapper script for cron restarts - EMQX Edition
# Uses systemctl to ensure root-owned processes are properly stopped

# Enable lingering for user (allows user processes without active session)
loginctl enable-linger $(whoami) 2>/dev/null || true

# Restart via systemd (runs as root, can kill all processes cleanly)
sudo systemctl restart camera-platform
