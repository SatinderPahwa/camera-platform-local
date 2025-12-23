#!/bin/bash
#
# Start Kurento Media Server in Podman container
#
# Based on proven POC2 implementation
# Kurento 6.16.0 is used (not 7.0.0 due to libnice ICE bugs)
#

set -e

CONTAINER_NAME="kms-production"
IMAGE="docker.io/kurento/kurento-media-server:6.16.0"
WS_PORT=8888

# Get absolute path to config directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CONFIG_DIR="${SCRIPT_DIR}/../config/kurento"

echo "======================================================================"
echo "Starting Kurento Media Server for Production Livestreaming"
echo "======================================================================"
echo ""

# Generate Kurento configuration from .env
echo "Step 1: Generating Kurento configuration from .env..."
"${SCRIPT_DIR}/generate_kurento_config.sh"
if [ $? -ne 0 ]; then
    echo "❌ Failed to generate Kurento configuration"
    exit 1
fi
echo ""

# Check if Podman machine is running
echo "Step 2: Checking Podman machine status..."
if ! podman ps >/dev/null 2>&1; then
    echo "⚠️  Podman machine not running, starting it..."

    # Try to start the machine
    if podman machine start 2>&1 | grep -q "already running"; then
        echo "✅ Podman machine already running"
    else
        echo "✅ Podman machine started"
        sleep 3  # Give it a moment to initialize
    fi

    # Verify it's now working
    if ! podman ps >/dev/null 2>&1; then
        echo "❌ Failed to start Podman machine"
        echo "   Try manually: podman machine start"
        exit 1
    fi
fi

echo "✅ Podman machine is running"
echo ""

# Check if container already exists
echo "Step 3: Starting Kurento container..."
if podman ps -a --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    echo "Container '${CONTAINER_NAME}' already exists."

    # Check if it's running
    if podman ps --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
        echo "✅ Container is already running"
        echo ""
        echo "To view logs:"
        echo "  podman logs -f ${CONTAINER_NAME}"
        echo ""
        echo "To restart:"
        echo "  podman restart ${CONTAINER_NAME}"
        echo ""
        echo "To stop:"
        echo "  podman stop ${CONTAINER_NAME}"
        exit 0
    fi

    # Container exists but not running - start it
    echo "Starting existing container..."
    podman start ${CONTAINER_NAME}
    echo "✅ Container started"
else
    # Create and start new container
    echo "Creating new container..."

    # Detect OS for network configuration
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS: use port mapping (--network host doesn't work properly)
        echo "Detected macOS: using port mapping"
        echo "Mounting custom Kurento configuration..."
        podman run -d \
            --name ${CONTAINER_NAME} \
            -p ${WS_PORT}:${WS_PORT} \
            -p ${WS_PORT}:${WS_PORT}/udp \
            -p 5000-5050:5000-5050/udp \
            -v "${CONFIG_DIR}/WebRtcEndpoint.conf.ini:/etc/kurento/modules/kurento/WebRtcEndpoint.conf.ini:Z" \
            -e KMS_MIN_PORT=5000 \
            -e KMS_MAX_PORT=5050 \
            -e GST_DEBUG=3,Kurento*:4 \
            ${IMAGE}
    else
        # Linux: use host network for better performance
        echo "Detected Linux: using host network"
        echo "Mounting custom Kurento configuration..."
        podman run -d \
            --name ${CONTAINER_NAME} \
            --network host \
            -v "${CONFIG_DIR}/WebRtcEndpoint.conf.ini:/etc/kurento/modules/kurento/WebRtcEndpoint.conf.ini:Z" \
            -e KMS_MIN_PORT=5000 \
            -e KMS_MAX_PORT=5050 \
            -e GST_DEBUG=3,Kurento*:4 \
            ${IMAGE}
    fi

    echo "✅ Container created and started"
fi

echo ""
echo "======================================================================"
echo "Kurento Media Server Status"
echo "======================================================================"

# Wait a moment for container to initialize
sleep 2

# Check if container is running
if podman ps --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    echo "Status: Running ✅"
    echo "WebSocket URL: ws://localhost:${WS_PORT}/kurento"
    echo ""
    echo "Container ID: $(podman ps -q --filter name=${CONTAINER_NAME})"
    echo ""
    echo "Useful commands:"
    echo "  View logs:    podman logs -f ${CONTAINER_NAME}"
    echo "  Stop:         podman stop ${CONTAINER_NAME}"
    echo "  Restart:      podman restart ${CONTAINER_NAME}"
    echo "  Remove:       podman stop ${CONTAINER_NAME} && podman rm ${CONTAINER_NAME}"
    echo ""
    echo "Health check:"
    echo "  curl -s http://localhost:${WS_PORT} | head -5"
    echo ""
else
    echo "❌ Error: Container failed to start"
    echo ""
    echo "Check logs:"
    echo "  podman logs ${CONTAINER_NAME}"
    exit 1
fi

echo "======================================================================"
