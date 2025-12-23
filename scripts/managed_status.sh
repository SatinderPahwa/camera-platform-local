#!/bin/bash

# Server Status Script - EMQX Edition

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_DIR="$PROJECT_DIR/pids"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "======================================"
echo "Server Status"
echo "======================================"

# Function to check process status
check_status() {
    local name=$1
    local pid_file="$PID_DIR/${name}.pid"

    printf "%-20s" "$name:"

    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo -e "${GREEN}Running (PID: $pid)${NC}"
            return 0
        else
            echo -e "${RED}Dead (stale PID file)${NC}"
            return 1
        fi
    else
        echo -e "${RED}Not running${NC}"
        return 1
    fi
}

# Check EMQX
printf "%-20s" "EMQX broker:"
if command -v emqx &> /dev/null; then
    if sudo emqx ctl status &> /dev/null; then
        echo -e "${GREEN}Running${NC}"
    else
        echo -e "${RED}Not running${NC}"
    fi
else
    echo -e "${RED}Not installed${NC}"
fi

# Check platform services
check_status "config_server"
check_status "mqtt_processor"
check_status "dashboard_server"

# Check livestreaming status
echo ""
echo "--------------------------------------"
echo "Livestreaming Status"
echo "--------------------------------------"
cd "$PROJECT_DIR/livestreaming"
./status.sh
cd "$PROJECT_DIR"


echo ""
echo "======================================"
echo "Quick Actions:"
echo "======================================"
echo "Start all:     ./scripts/managed_start.sh start"
echo "Stop all:      ./scripts/managed_start.sh stop"
echo "Restart all:   ./scripts/managed_start.sh restart"
echo ""
echo "View logs:"
echo "  tail -f logs/config_server.log"
echo "  tail -f logs/mqtt_processor.log"
echo "  tail -f logs/dashboard_server.log"
echo ""
echo "EMQX management:"
echo "  sudo systemctl start emqx"
echo "  sudo systemctl stop emqx"
echo "  sudo emqx ctl status"
echo "  Dashboard: http://localhost:18083 (admin/public)"
echo ""
