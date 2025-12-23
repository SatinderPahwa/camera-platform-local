#!/bin/bash
#
# Stop All Livestreaming Services
#

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================================================"
echo "🛑 Stopping Camera Livestreaming System"
echo "========================================================================"
echo ""

# Load service info if available
if [ -f "$SCRIPT_DIR/logs/services.env" ]; then
    source "$SCRIPT_DIR/logs/services.env"
fi

# Stop livestreaming service
echo "1️⃣  Stopping livestreaming service..."
if [ -f "$SCRIPT_DIR/logs/livestream.pid" ]; then
    PID=$(cat "$SCRIPT_DIR/logs/livestream.pid")
    if ps -p $PID > /dev/null 2>&1; then
        echo "Killing process $PID..."
        kill $PID 2>/dev/null || true
        sleep 2
        # Force kill if still running
        if ps -p $PID > /dev/null 2>&1; then
            kill -9 $PID 2>/dev/null || true
        fi
        echo -e "${GREEN}✅ Livestreaming service stopped${NC}"
    else
        echo -e "${YELLOW}Process $PID not running${NC}"
    fi
    rm -f "$SCRIPT_DIR/logs/livestream.pid"
else
    # Try to find and kill by port
    if lsof -ti :8080 > /dev/null 2>&1; then
        echo "Found process on port 8080, killing..."
        lsof -ti :8080 | xargs kill -9 2>/dev/null || true
        echo -e "${GREEN}✅ Stopped service on port 8080${NC}"
    else
        echo -e "${YELLOW}No livestreaming service found${NC}"
    fi
fi

# Stop dashboard
echo ""
echo "2️⃣  Stopping dashboard server..."
if [ -f "$SCRIPT_DIR/logs/dashboard.pid" ]; then
    PID=$(cat "$SCRIPT_DIR/logs/dashboard.pid")
    if ps -p $PID > /dev/null 2>&1; then
        echo "Killing process $PID..."
        kill $PID 2>/dev/null || true
        sleep 2
        if ps -p $PID > /dev/null 2>&1; then
            kill -9 $PID 2>/dev/null || true
        fi
        echo -e "${GREEN}✅ Dashboard stopped${NC}"
    else
        echo -e "${YELLOW}Process $PID not running${NC}"
    fi
    rm -f "$SCRIPT_DIR/logs/dashboard.pid"
else
    # Dashboard server is managed by main project's managed_start.sh
    # Not stopping dashboard here to avoid killing main dashboard server
    echo -e "${BLUE}ℹ️  Dashboard server (port 5000) is managed separately by managed_start.sh${NC}"
    echo -e "${BLUE}   Use './managed_start.sh stop' to stop the main dashboard${NC}"
fi

# Check if Podman machine is running (macOS) before checking Kurento
echo ""
echo "3️⃣  Kurento Media Server..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    if ! podman ps >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Podman machine not running${NC}"
        echo "Kurento cannot be checked/stopped without Podman machine"
        echo "Start machine with: podman machine start"
        echo -e "${YELLOW}Skipping Kurento...${NC}"
    else
        # Machine is running, check for Kurento
        if podman ps --format "{{.Names}}" | grep -q "^kms-production$"; then
            read -p "Stop Kurento Media Server? (y/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                echo "Stopping Kurento container..."
                podman stop kms-production
                echo -e "${GREEN}✅ Kurento stopped${NC}"

                read -p "Remove Kurento container? (y/n) " -n 1 -r
                echo
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    podman rm kms-production
                    echo -e "${GREEN}✅ Kurento container removed${NC}"
                fi
            else
                echo -e "${YELLOW}Kurento still running${NC}"
            fi
        else
            echo -e "${YELLOW}Kurento not running${NC}"
        fi
    fi
else
    # Linux - no machine needed
    if podman ps --format "{{.Names}}" | grep -q "^kms-production$"; then
        read -p "Stop Kurento Media Server? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "Stopping Kurento container..."
            podman stop kms-production
            echo -e "${GREEN}✅ Kurento stopped${NC}"

            read -p "Remove Kurento container? (y/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                podman rm kms-production
                echo -e "${GREEN}✅ Kurento container removed${NC}"
            fi
        else
            echo -e "${YELLOW}Kurento still running${NC}"
        fi
    else
        echo -e "${YELLOW}Kurento not running${NC}"
    fi
fi

# Clean up
rm -f "$SCRIPT_DIR/logs/services.env"

echo ""
echo "========================================================================"
echo "✅ Services Stopped"
echo "========================================================================"
echo ""
echo "To start again: $SCRIPT_DIR/start_all.sh"
echo ""
