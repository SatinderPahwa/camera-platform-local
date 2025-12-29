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

# Detect container runtime
if command -v podman &> /dev/null; then
    CONTAINER_CMD="podman"
    echo "✅ Using Podman"
elif command -v docker &> /dev/null; then
    CONTAINER_CMD="docker"
    echo "✅ Using Docker"
else
    echo "❌ No container runtime found (podman or docker)"
    exit 1
fi

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

# Check if Podman machine is running (only for Podman on macOS)
if [[ "${CONTAINER_CMD}" == "podman" ]]; then
    echo "Step 2: Checking Podman machine status..."
    if ! ${CONTAINER_CMD} ps >/dev/null 2>&1; then
        echo "⚠️  Podman machine not running, starting it..."

        # Try to start the machine
        if ${CONTAINER_CMD} machine start 2>&1 | grep -q "already running"; then
            echo "✅ Podman machine already running"
        else
            echo "✅ Podman machine started"
            sleep 3  # Give it a moment to initialize
        fi

        # Verify it's now working
        if ! ${CONTAINER_CMD} ps >/dev/null 2>&1; then
            echo "❌ Failed to start Podman machine"
            echo "   Try manually: podman machine start"
            exit 1
        fi
    fi
    echo "✅ Podman machine is running"
else
    echo "Step 2: Container runtime check passed (${CONTAINER_CMD})"
fi
echo ""

# Check if container already exists
echo "Step 3: Starting Kurento container..."
if ${CONTAINER_CMD} ps -a --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    echo "Container '${CONTAINER_NAME}' already exists."

    # Check if it's running
    if ${CONTAINER_CMD} ps --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
        echo "✅ Container is already running"
        echo ""
        echo "To view logs:"
        echo "  ${CONTAINER_CMD} logs -f ${CONTAINER_NAME}"
        echo ""
        echo "To restart:"
        echo "  ${CONTAINER_CMD} restart ${CONTAINER_NAME}"
        echo ""
        echo "To stop:"
        echo "  ${CONTAINER_CMD} stop ${CONTAINER_NAME}"
        exit 0
    fi

    # Container exists but not running - start it
    echo "Starting existing container..."
    ${CONTAINER_CMD} start ${CONTAINER_NAME}
    echo "✅ Container started"
else
    # Create and start new container
    echo "Creating new container..."

    # Detect OS for network configuration
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS: use port mapping (--network host doesn't work properly)
        echo "Detected macOS: using port mapping"
        echo "Mounting custom Kurento configuration..."
        ${CONTAINER_CMD} run -d \
            --name ${CONTAINER_NAME} \
            -p ${WS_PORT}:${WS_PORT} \
            -p ${WS_PORT}:${WS_PORT}/udp \
            -p 5000-5050:5000-5050/udp \
            -v "${CONFIG_DIR}/WebRtcEndpoint.conf.ini:/etc/kurento/modules/kurento/WebRtcEndpoint.conf.ini:Z" \
            -v "${CONFIG_DIR}/BaseRtpEndpoint.conf.ini:/etc/kurento/modules/kurento/BaseRtpEndpoint.conf.ini:Z" \
            -e KMS_MIN_PORT=5000 \
            -e KMS_MAX_PORT=5050 \
            -e GST_DEBUG=3,Kurento*:4 \
            ${IMAGE}
        # REMB_FIX: Added BaseRtpEndpoint.conf.ini mount above to enable REMB feedback
        # ROLLBACK: Remove the BaseRtpEndpoint mount line to revert
    else
        # Linux: use host network for better performance
        echo "Detected Linux: using host network"
        echo "Mounting custom Kurento configuration..."
        ${CONTAINER_CMD} run -d \
            --name ${CONTAINER_NAME} \
            --network host \
            -v "${CONFIG_DIR}/WebRtcEndpoint.conf.ini:/etc/kurento/modules/kurento/WebRtcEndpoint.conf.ini:Z" \
            -v "${CONFIG_DIR}/BaseRtpEndpoint.conf.ini:/etc/kurento/modules/kurento/BaseRtpEndpoint.conf.ini:Z" \
            -e KMS_MIN_PORT=5000 \
            -e KMS_MAX_PORT=5050 \
            -e GST_DEBUG=3,Kurento*:4 \
            ${IMAGE}
        # REMB_FIX: Added BaseRtpEndpoint.conf.ini mount above to enable REMB feedback
        # ROLLBACK: Remove the BaseRtpEndpoint mount line to revert
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
if ${CONTAINER_CMD} ps --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    echo "Status: Running ✅"
    echo "WebSocket URL: ws://localhost:${WS_PORT}/kurento"
    echo ""
    echo "Container ID: $(${CONTAINER_CMD} ps -q --filter name=${CONTAINER_NAME})"
    echo ""
    echo "Useful commands:"
    echo "  View logs:    ${CONTAINER_CMD} logs -f ${CONTAINER_NAME}"
    echo "  Stop:         ${CONTAINER_CMD} stop ${CONTAINER_NAME}"
    echo "  Restart:      ${CONTAINER_CMD} restart ${CONTAINER_NAME}"
    echo "  Remove:       ${CONTAINER_CMD} stop ${CONTAINER_NAME} && ${CONTAINER_CMD} rm ${CONTAINER_NAME}"
    echo ""
    echo "Health check:"
    echo "  curl -s http://localhost:${WS_PORT} | head -5"
    echo ""
else
    echo "❌ Error: Container failed to start"
    echo ""
    echo "Check logs:"
    echo "  ${CONTAINER_CMD} logs ${CONTAINER_NAME}"
    exit 1
fi

echo "======================================================================"
