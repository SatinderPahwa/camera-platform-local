#!/bin/bash
# Production Hardening Setup Script
# Automates systemd service, sudo rules, cron jobs, and health monitoring
#
# What it does:
# 1. Enables user lingering (services persist without active session)
# 2. Creates systemd service for auto-start on boot
# 3. Sets up sudo rules for passwordless EMQX commands
# 4. Configures cron jobs for health checks and scheduled restarts
# 5. Verifies all components are working

set -e  # Exit on error

echo "============================================"
echo "Production Hardening Setup"
echo "============================================"
echo ""
echo "This script automates production deployment:"
echo "- Systemd service for auto-start on boot"
echo "- Health monitoring every 12 minutes"
echo "- Scheduled restarts every 8 hours"
echo "- Self-healing on failures"
echo ""

# Get the actual user (not root when using sudo)
ACTUAL_USER="${SUDO_USER:-$USER}"
if [ "$ACTUAL_USER" = "root" ]; then
    echo "❌ Error: Could not determine non-root user"
    echo "Please run with: sudo ./scripts/setup_production_hardening.sh"
    exit 1
fi

# Get project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_HOME=$(eval echo ~$ACTUAL_USER)

echo "📋 Configuration:"
echo "   User: $ACTUAL_USER"
echo "   Home: $USER_HOME"
echo "   Project: $PROJECT_ROOT"
echo ""

# Step 1: Enable user lingering
echo "📝 Step 1: Enable user lingering"
if loginctl show-user "$ACTUAL_USER" 2>/dev/null | grep -q "Linger=yes"; then
    echo "   ✅ User lingering already enabled"
else
    loginctl enable-linger "$ACTUAL_USER"
    echo "   ✅ Enabled user lingering for $ACTUAL_USER"
fi

# Verify
LINGER_STATUS=$(loginctl show-user "$ACTUAL_USER" 2>/dev/null | grep "Linger=" | cut -d'=' -f2)
if [ "$LINGER_STATUS" = "yes" ]; then
    echo "   ✅ Verified: Linger=$LINGER_STATUS"
else
    echo "   ⚠️  Warning: Lingering may not be active yet"
fi
echo ""

# Step 2: Create systemd service for auto-start on boot
echo "📝 Step 2: Create systemd service for auto-start"

SYSTEMD_DIR="$USER_HOME/.config/systemd/user"
SERVICE_FILE="$SYSTEMD_DIR/camera-platform.service"

# Create systemd directory if it doesn't exist
mkdir -p "$SYSTEMD_DIR"
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$USER_HOME/.config"

# Generate service file from template
cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Camera Platform Services - EMQX Edition (Dashboard, MQTT Processor, Config Server)
After=network.target emqx.service docker.service
Wants=emqx.service docker.service

[Service]
Type=forking
WorkingDirectory=$PROJECT_ROOT
ExecStart=/bin/bash $PROJECT_ROOT/scripts/managed_start.sh start
ExecStop=/bin/bash $PROJECT_ROOT/scripts/managed_start.sh stop
RemainAfterExit=yes
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF

chown "$ACTUAL_USER:$ACTUAL_USER" "$SERVICE_FILE"
echo "   ✅ Created service file: $SERVICE_FILE"

# Reload systemd daemon and enable service (as user)
# Need to set XDG_RUNTIME_DIR for systemctl --user to work
export XDG_RUNTIME_DIR="/run/user/$(id -u $ACTUAL_USER)"

if sudo -u "$ACTUAL_USER" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user daemon-reload 2>/dev/null; then
    sudo -u "$ACTUAL_USER" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user enable camera-platform.service 2>/dev/null
    echo "   ✅ Enabled camera-platform.service"

    # Start service if not already running
    if sudo -u "$ACTUAL_USER" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user is-active camera-platform.service >/dev/null 2>&1; then
        echo "   ✅ Service already running"
    else
        echo "   📌 Note: Service not started yet (will auto-start on next boot)"
        echo "      To start now: systemctl --user start camera-platform.service"
    fi
else
    echo "   ⚠️  Could not enable systemd service automatically"
    echo "   📌 Run these commands manually as $ACTUAL_USER (without sudo):"
    echo "      systemctl --user daemon-reload"
    echo "      systemctl --user enable camera-platform.service"
    echo "      systemctl --user start camera-platform.service"
fi
echo ""

# Step 3: Configure sudo for health checks
echo "📝 Step 3: Configure sudo for health checks"

SUDOERS_FILE="/etc/sudoers.d/camera-platform"

# Check if already configured
if [ -f "$SUDOERS_FILE" ] && grep -q "NOPASSWD.*emqx" "$SUDOERS_FILE" 2>/dev/null; then
    echo "   ✅ Sudo rules already configured"
else
    # Create sudoers file
    cat > "$SUDOERS_FILE" << EOF
# Camera Platform - Allow passwordless commands for health checks and auto-restart
# Created by: setup_production_hardening.sh
$ACTUAL_USER ALL=(ALL) NOPASSWD: /usr/bin/emqx
$ACTUAL_USER ALL=(ALL) NOPASSWD: /bin/systemctl restart emqx
$ACTUAL_USER ALL=(ALL) NOPASSWD: /bin/systemctl restart coturn
$ACTUAL_USER ALL=(ALL) NOPASSWD: /usr/bin/docker restart kms-production
EOF

    # Set correct permissions (sudoers files must be 0440)
    chmod 0440 "$SUDOERS_FILE"
    echo "   ✅ Created sudoers file: $SUDOERS_FILE"

    # Validate sudoers file
    if visudo -c -f "$SUDOERS_FILE" >/dev/null 2>&1; then
        echo "   ✅ Sudoers file syntax is valid"
    else
        echo "   ❌ Error: Invalid sudoers syntax, removing file"
        rm "$SUDOERS_FILE"
        exit 1
    fi
fi
echo ""

# Step 4: Set up cron jobs
echo "📝 Step 4: Configure cron jobs"

# Get current crontab
TEMP_CRON=$(mktemp)
sudo -u "$ACTUAL_USER" crontab -l > "$TEMP_CRON" 2>/dev/null || true

# Check if health check cron already exists
if grep -q "health_check_and_restart.sh" "$TEMP_CRON" 2>/dev/null; then
    echo "   ✅ Health check cron job already configured"
else
    echo "# Camera Platform: Health check every 12 minutes" >> "$TEMP_CRON"
    echo "*/12 * * * * $PROJECT_ROOT/tools/health_check_and_restart.sh" >> "$TEMP_CRON"
    echo "   ✅ Added health check cron job (every 12 minutes)"
fi

# Check if scheduled restart cron already exists
if grep -q "cron_restart_wrapper.sh" "$TEMP_CRON" 2>/dev/null; then
    echo "   ✅ Scheduled restart cron job already configured"
else
    echo "" >> "$TEMP_CRON"
    echo "# Camera Platform: Scheduled restarts every 8 hours (8 AM, 4 PM, Midnight)" >> "$TEMP_CRON"
    echo "0 8,16,0 * * * $PROJECT_ROOT/cron_restart_wrapper.sh >> $PROJECT_ROOT/logs/cron_restart.log 2>&1" >> "$TEMP_CRON"
    echo "   ✅ Added scheduled restart cron job (8 AM, 4 PM, Midnight)"
fi

# Check if log cleanup cron already exists
if grep -q "cleanup_old_logs.sh" "$TEMP_CRON" 2>/dev/null; then
    echo "   ✅ Log cleanup cron job already configured"
else
    echo "" >> "$TEMP_CRON"
    echo "# Camera Platform: Cleanup logs older than 15 days (daily at 3 AM)" >> "$TEMP_CRON"
    echo "0 3 * * * $PROJECT_ROOT/tools/cleanup_old_logs.sh >> $PROJECT_ROOT/logs/cleanup.log 2>&1" >> "$TEMP_CRON"
    echo "   ✅ Added log cleanup cron job (daily at 3 AM)"
fi

# Install crontab (make temp file readable by user first)
chmod 644 "$TEMP_CRON"
sudo -u "$ACTUAL_USER" crontab "$TEMP_CRON"
rm "$TEMP_CRON"
echo ""

# Step 5: Verify cron configuration
echo "📝 Step 5: Verify cron configuration"
echo ""
echo "Current crontab for $ACTUAL_USER:"
echo "-----------------------------------"
sudo -u "$ACTUAL_USER" crontab -l | grep -A1 "Camera Platform" || echo "No camera platform cron jobs found"
echo "-----------------------------------"
echo ""

# Step 6: Test health check script
echo "📝 Step 6: Test health check script"
if [ -f "$PROJECT_ROOT/tools/health_check_and_restart.sh" ]; then
    echo "   ✅ Health check script exists"

    # Make sure it's executable
    chmod +x "$PROJECT_ROOT/tools/health_check_and_restart.sh"

    echo "   📌 Testing health check (this may take a few seconds)..."
    if sudo -u "$ACTUAL_USER" "$PROJECT_ROOT/tools/health_check_and_restart.sh" >/dev/null 2>&1; then
        echo "   ✅ Health check script executed successfully"
    else
        echo "   ⚠️  Health check script encountered issues (check logs/health_check.log)"
    fi
else
    echo "   ⚠️  Warning: Health check script not found"
    echo "      Expected: $PROJECT_ROOT/tools/health_check_and_restart.sh"
fi
echo ""

# Step 7: Verify cron_restart_wrapper.sh exists
echo "📝 Step 7: Verify restart wrapper script"
if [ -f "$PROJECT_ROOT/cron_restart_wrapper.sh" ]; then
    echo "   ✅ Restart wrapper script exists"
    chmod +x "$PROJECT_ROOT/cron_restart_wrapper.sh"
else
    echo "   ⚠️  Warning: Restart wrapper script not found"
    echo "      Expected: $PROJECT_ROOT/cron_restart_wrapper.sh"
fi
echo ""

# Summary
echo "============================================"
echo "✅ Production Hardening Complete!"
echo "============================================"
echo ""
echo "📋 What was configured:"
echo "   ✓ User lingering enabled (services persist)"
echo "   ✓ Systemd service created and enabled"
echo "   ✓ Sudo rules configured (passwordless EMQX)"
echo "   ✓ Health check cron job (every 12 minutes)"
echo "   ✓ Scheduled restart cron job (every 8 hours)"
echo ""
echo "📌 Systemd Service Status:"
sudo -u "$ACTUAL_USER" XDG_RUNTIME_DIR="/run/user/$(id -u $ACTUAL_USER)" systemctl --user status camera-platform.service --no-pager 2>/dev/null || echo "   (Run 'systemctl --user status camera-platform.service' to check status)"
echo ""
echo "📌 Next Steps:"
echo "   1. Services will auto-start on next boot"
echo "   2. Health checks run automatically every 12 minutes"
echo "   3. Scheduled restarts occur at 8 AM, 4 PM, and Midnight"
echo "   4. System is now self-healing on failures"
echo ""
echo "🔍 Useful Commands:"
echo "   Check service status:    systemctl --user status camera-platform.service"
echo "   Start service manually:  systemctl --user start camera-platform.service"
echo "   Stop service:            systemctl --user stop camera-platform.service"
echo "   View cron jobs:          crontab -l"
echo "   View health check logs:  tail -f $PROJECT_ROOT/logs/health_check.log"
echo "   View restart logs:       tail -f $PROJECT_ROOT/logs/cron_restart.log"
echo ""
