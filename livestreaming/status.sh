#!/bin/bash
#
# Check Status of Livestreaming Services
#

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "========================================================================"
echo "📊 Livestreaming System Status"
echo "========================================================================"
echo ""

# Check Kurento
echo "1️⃣  Kurento Media Server"
if podman ps --format "{{.Names}}" | grep -q "^kms-production$"; then
    echo -e "   Status: ${GREEN}✅ Running${NC}"
    CONTAINER_ID=$(podman ps -q --filter name=kms-production)
    echo "   Container: $CONTAINER_ID"
    echo "   URL: ws://localhost:8888/kurento"

    # Test connection
    if curl -s http://localhost:8888 > /dev/null 2>&1; then
        echo -e "   Connection: ${GREEN}✅ OK${NC}"
    else
        echo -e "   Connection: ${RED}❌ Failed${NC}"
    fi
else
    echo -e "   Status: ${RED}❌ Not running${NC}"
fi

echo ""
echo "2️⃣  Livestreaming API Server"
if lsof -i :8080 > /dev/null 2>&1; then
    PID=$(lsof -ti :8080)
    echo -e "   Status: ${GREEN}✅ Running${NC} (PID: $PID)"
    echo "   URL: http://localhost:8080"

    # Check health
    if curl -s http://localhost:8080/health > /dev/null 2>&1; then
        echo -e "   Health: ${GREEN}✅ Healthy${NC}"

        # Get detailed status
        HEALTH=$(curl -s http://localhost:8080/health)
        ACTIVE_STREAMS=$(echo $HEALTH | python3 -c "import sys, json; print(json.load(sys.stdin).get('active_streams', 0))" 2>/dev/null || echo "0")
        TOTAL_VIEWERS=$(echo $HEALTH | python3 -c "import sys, json; print(json.load(sys.stdin).get('total_viewers', 0))" 2>/dev/null || echo "0")

        echo "   Active streams: $ACTIVE_STREAMS"
        echo "   Total viewers: $TOTAL_VIEWERS"
    else
        echo -e "   Health: ${RED}❌ Unhealthy${NC}"
    fi
else
    echo -e "   Status: ${RED}❌ Not running${NC}"
fi

echo ""
echo "3️⃣  Signaling Server"
if lsof -i :8765 > /dev/null 2>&1; then
    PID=$(lsof -ti :8765)
    echo -e "   Status: ${GREEN}✅ Running${NC} (PID: $PID)"
    echo "   URL: ws://localhost:8765"
else
    echo -e "   Status: ${RED}❌ Not running${NC}"
fi

echo ""
echo "4️⃣  Dashboard Server"
if lsof -i :5000 > /dev/null 2>&1; then
    PID=$(lsof -ti :5000)
    echo -e "   Status: ${GREEN}✅ Running${NC} (PID: $PID)"
    echo "   URL: http://localhost:5000"
else
    echo -e "   Status: ${YELLOW}⚠️  Not running${NC} (optional)"
fi

echo ""
echo "5️⃣  Configuration"
if [ -n "$EXTERNAL_IP" ]; then
    echo -e "   EXTERNAL_IP: ${GREEN}$EXTERNAL_IP${NC}"
else
    echo -e "   EXTERNAL_IP: ${YELLOW}⚠️  Not set${NC}"
fi

echo ""
echo "========================================================================"

# Check if services.env exists
if [ -f "$SCRIPT_DIR/logs/services.env" ]; then
    source "$SCRIPT_DIR/logs/services.env"
    echo ""
    echo "System started at: $STARTED_AT"
    UPTIME=$(python3 -c "from datetime import datetime; started = datetime.fromisoformat('${STARTED_AT}'.replace('Z', '+00:00')); now = datetime.now(started.tzinfo); print(str(now - started).split('.')[0])" 2>/dev/null || echo "unknown")
    echo "Uptime: $UPTIME"
fi

echo ""
echo "📋 Quick Commands:"
echo "   View API health:   curl http://localhost:8080/health | python3 -m json.tool"
echo "   List streams:      curl http://localhost:8080/streams | python3 -m json.tool"
echo "   Kurento logs:      podman logs -f kms-production"
echo "   Service logs:      tail -f $SCRIPT_DIR/logs/livestreaming.log"
echo "   Stop all:          $SCRIPT_DIR/stop_all.sh"
echo ""
