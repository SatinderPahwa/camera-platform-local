#!/bin/bash
#
# Generate Kurento WebRtcEndpoint Configuration from .env
#
# This script reads LOCAL_IP and port settings from .env and generates
# the WebRtcEndpoint.conf.ini file for Kurento Media Server.
#
# This ensures configuration is consistent across deployments.
#

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/../.." && pwd )"
CONFIG_DIR="$SCRIPT_DIR/../config/kurento"
CONFIG_FILE="$CONFIG_DIR/WebRtcEndpoint.conf.ini"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "======================================================================"
echo "Generating Kurento WebRtcEndpoint Configuration"
echo "======================================================================"
echo ""

# Load .env file
ENV_FILE="$PROJECT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}❌ Error: .env file not found at $ENV_FILE${NC}"
    echo "   Please create .env file first (see SETUP_GUIDE.md)"
    exit 1
fi

# Source .env file
echo "Loading configuration from .env..."
set -a  # Automatically export all variables
source "$ENV_FILE"
set +a

# Validate required variables
if [ -z "$LOCAL_IP" ]; then
    echo -e "${RED}❌ Error: LOCAL_IP not set in .env${NC}"
    exit 1
fi

if [ -z "$KMS_MIN_PORT" ]; then
    echo -e "${YELLOW}⚠️  Warning: KMS_MIN_PORT not set, using default 5000${NC}"
    KMS_MIN_PORT=5000
fi

if [ -z "$KMS_MAX_PORT" ]; then
    echo -e "${YELLOW}⚠️  Warning: KMS_MAX_PORT not set, using default 5050${NC}"
    KMS_MAX_PORT=5050
fi

echo "Configuration:"
echo "  LOCAL_IP: $LOCAL_IP"
echo "  KMS_MIN_PORT: $KMS_MIN_PORT"
echo "  KMS_MAX_PORT: $KMS_MAX_PORT"

# Determine network interface for Kurento
if [ -n "$NETWORK_INTERFACE" ]; then
    # User specified a network interface in .env
    echo "  Network interface (from .env): $NETWORK_INTERFACE"
else
    # Auto-detect network interface based on OS_TYPE and LOCAL_IP
    DETECTED_INTERFACE=""

    if [ "$OS_TYPE" = "linux" ]; then
        # Linux: use ip command
        if command -v ip &> /dev/null; then
            DETECTED_INTERFACE=$(ip -o addr show | grep "inet $LOCAL_IP" | awk '{print $2}' | head -1)
        fi
    elif [ "$OS_TYPE" = "macos" ]; then
        # macOS: use ifconfig
        if command -v ifconfig &> /dev/null; then
            DETECTED_INTERFACE=$(ifconfig | grep -B 6 "inet $LOCAL_IP" | head -1 | awk '{print $1}' | tr -d ':')
        fi
    fi

    if [ -n "$DETECTED_INTERFACE" ]; then
        NETWORK_INTERFACE="$DETECTED_INTERFACE"
        echo "  Network interface (auto-detected): $NETWORK_INTERFACE"
    else
        NETWORK_INTERFACE="all"
        echo -e "${YELLOW}  Network interface: all (could not auto-detect - may cause ICE issues)${NC}"
    fi
fi

echo ""

# Create config directory if it doesn't exist
mkdir -p "$CONFIG_DIR"

# Backup existing config if it exists
if [ -f "$CONFIG_FILE" ]; then
    BACKUP_FILE="${CONFIG_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    echo "Backing up existing configuration to:"
    echo "  $BACKUP_FILE"
    cp "$CONFIG_FILE" "$BACKUP_FILE"
fi

# Generate new configuration
echo "Generating new configuration..."
cat > "$CONFIG_FILE" << EOF
# Kurento WebRTC Endpoint Configuration
# This file is AUTO-GENERATED from .env by generate_kurento_config.sh
# DO NOT edit manually - changes will be overwritten
#
# Generated: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
# Source: $ENV_FILE

# STUN server configuration
stunServerAddress=stun.l.google.com
stunServerPort=19302

# External IP configuration
# This is the server's LOCAL_IP from .env
# Kurento will advertise this IP in ICE candidates
externalIPv4=$LOCAL_IP

# Network interfaces
# Auto-detected based on OS_TYPE and LOCAL_IP
# Specify a single interface to avoid ICE gathering issues on systems with multiple interfaces
networkInterfaces=$NETWORK_INTERFACE

# ICE candidate gathering timeout (in seconds)
iceCandidateGatheringTimeout=10

# Port range for WebRTC (from .env: KMS_MIN_PORT - KMS_MAX_PORT)
minPort=$KMS_MIN_PORT
maxPort=$KMS_MAX_PORT

# TURN server (optional - uncomment if needed for restrictive NATs)
# turnURL=username:password@turn.example.com:3478?transport=udp
EOF

# Add TURN server configuration if available in .env
if [ -n "$TURN_SERVER_URL" ] && [ -n "$TURN_SERVER_USERNAME" ] && [ -n "$TURN_SERVER_PASSWORD" ]; then
    # Extract port from TURN URL (e.g., turn:hostname:3478 -> 3478)
    TURN_PORT=$(echo "$TURN_SERVER_URL" | sed 's/turn:[^:]*://')

    # Use LOCAL_IP because coturn runs on same server as Kurento
    echo "" >> "$CONFIG_FILE"
    echo "# TURN server configuration (for NAT traversal)" >> "$CONFIG_FILE"
    echo "# Configured from .env - using LOCAL_IP because TURN server is on same host" >> "$CONFIG_FILE"
    echo "turnURL=${TURN_SERVER_USERNAME}:${TURN_SERVER_PASSWORD}@${LOCAL_IP}:${TURN_PORT}?transport=udp" >> "$CONFIG_FILE"

    TURN_CONFIGURED="yes"
else
    TURN_CONFIGURED="no"
fi

echo ""
echo -e "${GREEN}✅ Configuration generated successfully${NC}"
echo ""
echo "Generated file:"
echo "  $CONFIG_FILE"
echo ""
echo "Configuration summary:"
echo "  - External IP (ICE candidates): $LOCAL_IP"
echo "  - Network interface: $NETWORK_INTERFACE"
echo "  - WebRTC port range: $KMS_MIN_PORT-$KMS_MAX_PORT"
echo "  - STUN server: stun.l.google.com:19302"
if [ "$TURN_CONFIGURED" = "yes" ]; then
    echo "  - TURN server: ${LOCAL_IP}:${TURN_PORT} (for browser NAT traversal)"
fi
echo ""
echo "======================================================================"
