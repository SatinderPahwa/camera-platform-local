#!/bin/bash
#
# Firewall Configuration Script for Camera Platform
#
# Configures UFW (Uncomplicated Firewall) with all required rules for:
# - Camera connections (local network)
# - Dashboard access (external)
# - Livestreaming (WebRTC via Kurento + TURN)
# - MQTT broker (cameras)
# - EMQX dashboard (local network only)
#
# Usage:
#   sudo ./scripts/configure_firewall.sh
#

set -e  # Exit on error

echo "============================================"
echo "Camera Platform - Firewall Configuration"
echo "============================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Error: This script must be run as root (use sudo)"
    exit 1
fi

# Get the actual user (not root when using sudo)
ACTUAL_USER="${SUDO_USER:-$USER}"
if [ "$ACTUAL_USER" = "root" ]; then
    echo "❌ Error: Could not determine non-root user"
    echo "Please run with: sudo ./scripts/configure_firewall.sh"
    exit 1
fi

# Get project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "📋 Configuration:"
echo "   User: $ACTUAL_USER"
echo "   Project: $PROJECT_ROOT"
echo ""

# Detect local network
echo "🔍 Detecting local network..."
LOCAL_IP=$(ip route get 1.1.1.1 | grep -oP 'src \K\S+')
LOCAL_NETWORK=$(ip route | grep "$LOCAL_IP" | grep -v default | awk '{print $1}' | head -1)

if [ -z "$LOCAL_NETWORK" ]; then
    echo "❌ Error: Could not detect local network"
    echo "Please specify manually:"
    read -p "Enter local network (e.g., 192.168.1.0/24): " LOCAL_NETWORK
fi

echo "   Local IP: $LOCAL_IP"
echo "   Local Network: $LOCAL_NETWORK"
echo ""

# Confirmation
echo "⚠️  WARNING: This will configure firewall rules"
echo ""
echo "The following rules will be configured:"
echo ""
echo "📡 ALLOW FROM ANYWHERE:"
echo "   - 22/tcp        SSH access"
echo "   - 5000/tcp      Dashboard (HTTPS)"
echo "   - 8080/tcp      Livestream API"
echo "   - 8765/tcp      WebSocket signaling (WebRTC)"
echo "   - 8883/tcp      EMQX MQTT broker (cameras)"
echo "   - 3478/tcp+udp  TURN/STUN"
echo "   - 5349/tcp+udp  TURN/STUN (TLS)"
echo "   - 5000:5050/udp Kurento WebRTC media (RTP/RTCP)"
echo "   - 49152:65535/udp TURN relay ports"
echo ""
echo "🏠 ALLOW FROM LOCAL NETWORK ONLY ($LOCAL_NETWORK):"
echo "   - 80/tcp        Config server (cameras connect locally)"
echo "   - 8083/tcp      EMQX dashboard (HTTP)"
echo "   - 8084/tcp      EMQX dashboard (HTTPS)"
echo ""

read -p "Proceed with firewall configuration? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ] && [ "$CONFIRM" != "y" ]; then
    echo "❌ Configuration cancelled"
    exit 0
fi
echo ""

# Install UFW if not present
if ! command -v ufw &> /dev/null; then
    echo "📦 Installing UFW..."
    apt update
    apt install -y ufw
    echo "   ✅ UFW installed"
fi

# Disable UFW first (to clear any existing rules)
echo "🔧 Resetting UFW to defaults..."
ufw --force reset
echo "   ✅ UFW reset"
echo ""

# Set default policies
echo "📝 Setting default policies..."
ufw default deny incoming
ufw default allow outgoing
echo "   ✅ Default policies set (deny incoming, allow outgoing)"
echo ""

# Add rules
echo "📝 Configuring firewall rules..."
echo ""

# SSH - CRITICAL (always allow from anywhere)
echo "   [1/13] SSH (22/tcp) - from anywhere"
ufw allow 22/tcp comment 'SSH access'

# Dashboard - HTTPS access
echo "   [2/13] Dashboard (5000/tcp) - from anywhere"
ufw allow 5000/tcp comment 'Dashboard HTTPS'

# Livestream API
echo "   [3/13] Livestream API (8080/tcp) - from anywhere"
ufw allow 8080/tcp comment 'Livestream API'

# WebSocket signaling
echo "   [4/13] WebSocket signaling (8765/tcp) - from anywhere"
ufw allow 8765/tcp comment 'WebRTC signaling'

# EMQX MQTT broker
echo "   [5/13] EMQX MQTT (8883/tcp) - from anywhere"
ufw allow 8883/tcp comment 'EMQX MQTT broker'

# TURN/STUN (TCP + UDP)
echo "   [6/13] TURN/STUN (3478/tcp) - from anywhere"
ufw allow 3478/tcp comment 'TURN/STUN'
echo "   [7/13] TURN/STUN (3478/udp) - from anywhere"
ufw allow 3478/udp comment 'TURN/STUN'

# TURN/STUN TLS (TCP + UDP)
echo "   [8/13] TURN/STUN TLS (5349/tcp) - from anywhere"
ufw allow 5349/tcp comment 'TURN/STUN TLS'
echo "   [9/13] TURN/STUN TLS (5349/udp) - from anywhere"
ufw allow 5349/udp comment 'TURN/STUN TLS'

# Kurento WebRTC media ports (RTP/RTCP)
echo "   [10/13] Kurento media (5000:5050/udp) - from anywhere"
ufw allow 5000:5050/udp comment 'Kurento WebRTC media'

# TURN relay ports (ephemeral range)
echo "   [11/13] TURN relay (49152:65535/udp) - from anywhere"
ufw allow 49152:65535/udp comment 'TURN relay ports'

# Config server - LOCAL NETWORK ONLY
echo "   [12/13] Config server (80/tcp) - from $LOCAL_NETWORK ONLY"
ufw allow from "$LOCAL_NETWORK" to any port 80 proto tcp comment 'Config server (local only)'

# EMQX dashboard - LOCAL NETWORK ONLY
echo "   [13/13] EMQX dashboard (8083,8084/tcp) - from $LOCAL_NETWORK ONLY"
ufw allow from "$LOCAL_NETWORK" to any port 8083 proto tcp comment 'EMQX dashboard HTTP (local only)'
ufw allow from "$LOCAL_NETWORK" to any port 8084 proto tcp comment 'EMQX dashboard HTTPS (local only)'

echo ""
echo "   ✅ All rules configured"
echo ""

# Enable UFW
echo "🔥 Enabling firewall..."
ufw --force enable
echo "   ✅ Firewall enabled"
echo ""

# Show status
echo "============================================"
echo "✅ Firewall Configuration Complete!"
echo "============================================"
echo ""
echo "📊 Current Status:"
ufw status verbose
echo ""

# Verify critical ports
echo "============================================"
echo "🔍 Verification"
echo "============================================"
echo ""
echo "Critical ports that should be accessible:"
echo ""
echo "From anywhere:"
echo "   ✓ SSH (22/tcp)"
echo "   ✓ Dashboard (5000/tcp)"
echo "   ✓ Livestream API (8080/tcp)"
echo "   ✓ WebSocket (8765/tcp)"
echo "   ✓ MQTT (8883/tcp)"
echo "   ✓ TURN/STUN (3478, 5349 tcp+udp)"
echo "   ✓ Kurento media (5000-5050/udp)"
echo ""
echo "From $LOCAL_NETWORK only:"
echo "   ✓ Config server (80/tcp)"
echo "   ✓ EMQX dashboard (8083, 8084/tcp)"
echo ""

# Test hints
echo "============================================"
echo "🧪 Testing Recommendations"
echo "============================================"
echo ""
echo "1. Test SSH access (from external IP):"
echo "   ssh $ACTUAL_USER@YOUR_EXTERNAL_IP"
echo ""
echo "2. Test dashboard access (from browser):"
echo "   https://YOUR_DOMAIN:5000"
echo ""
echo "3. Test camera connection (from local network):"
echo "   - Camera should connect to config server (port 80)"
echo "   - Camera should connect to MQTT broker (port 8883)"
echo ""
echo "4. Test livestreaming:"
echo "   - Open dashboard and view camera stream"
echo "   - Verify WebRTC connection works"
echo ""
echo "5. View firewall logs:"
echo "   sudo tail -f /var/log/ufw.log"
echo ""

echo "✅ Firewall configuration complete!"
echo ""
