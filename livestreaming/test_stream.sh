#!/bin/bash
#
# Quick Test Script for Camera 4 Livestream
#

CAMERA_ID="56C1CADCF1FA4C6CAEBA3E2FD85EFEBF"
API_URL="http://localhost:8080"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "========================================================================"
echo "🧪 Testing Camera 4 Livestream"
echo "========================================================================"
echo ""
echo "Camera ID: $CAMERA_ID"
echo ""

# Check if services are running
echo "Checking services..."
if ! curl -s $API_URL/health > /dev/null 2>&1; then
    echo -e "${RED}❌ Livestreaming service not running${NC}"
    echo "   Start with: ./start_all.sh"
    exit 1
fi
echo -e "${GREEN}✅ Services are running${NC}"
echo ""

# Start stream
echo "Starting stream..."
START_RESPONSE=$(curl -s -X POST $API_URL/streams/$CAMERA_ID/start -H "Content-Type: application/json")

if echo $START_RESPONSE | grep -q "error"; then
    echo -e "${RED}❌ Failed to start stream${NC}"
    echo $START_RESPONSE | python3 -m json.tool
    exit 1
fi

echo -e "${GREEN}✅ Stream started${NC}"
SESSION_ID=$(echo $START_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['session_id'])" 2>/dev/null)
STREAM_ID=$(echo $START_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['stream_id'])" 2>/dev/null)

echo "   Session ID: $SESSION_ID"
echo "   Stream ID: ${STREAM_ID:0:8}..."
echo ""

# Monitor for 30 seconds
echo "Monitoring stream for 30 seconds (watching for timeout)..."
echo -e "${YELLOW}⏱  This is the critical test - stream should NOT timeout after 30s${NC}"
echo ""

for i in {1..30}; do
    # Get stream status
    STATUS=$(curl -s $API_URL/streams/$CAMERA_ID 2>/dev/null)

    if [ $? -ne 0 ] || [ -z "$STATUS" ]; then
        echo -e "${RED}❌ Failed to get stream status${NC}"
        break
    fi

    STATE=$(echo $STATUS | python3 -c "import sys, json; print(json.load(sys.stdin)['stream']['state'])" 2>/dev/null)
    DURATION=$(echo $STATUS | python3 -c "import sys, json; print(int(json.load(sys.stdin)['stream']['duration_seconds']))" 2>/dev/null)
    KEEPALIVES=$(echo $STATUS | python3 -c "import sys, json; print(json.load(sys.stdin)['stream']['keepalive_stats']['keepalive_count'])" 2>/dev/null)
    ERRORS=$(echo $STATUS | python3 -c "import sys, json; print(json.load(sys.stdin)['stream']['keepalive_stats']['error_count'])" 2>/dev/null)
    VIEWERS=$(echo $STATUS | python3 -c "import sys, json; print(json.load(sys.stdin)['viewer_count'])" 2>/dev/null)

    # Check if stream failed
    if [ "$STATE" != "active" ]; then
        echo -e "${RED}❌ Stream is not active (state: $STATE)${NC}"
        break
    fi

    # Print status
    printf "\r[%2d/30s] Duration: %3ds | Keepalives: %2d | Errors: %d | Viewers: %d | State: %s   " \
           $i $DURATION $KEEPALIVES $ERRORS $VIEWERS $STATE

    # Special check at 30 seconds
    if [ $i -eq 30 ]; then
        echo ""
        echo ""
        if [ "$STATE" == "active" ] && [ "$ERRORS" == "0" ]; then
            echo -e "${GREEN}🎉 SUCCESS! Stream survived 30+ seconds without timeout!${NC}"
            echo -e "${GREEN}   REMB packets are working correctly!${NC}"
        else
            echo -e "${RED}❌ Stream may have issues${NC}"
        fi
    fi

    sleep 1
done

echo ""
echo ""
echo "========================================================================"
echo "📊 Final Stream Statistics"
echo "========================================================================"
echo ""

# Get final stats
FINAL_STATUS=$(curl -s $API_URL/streams/$CAMERA_ID)
echo $FINAL_STATUS | python3 -m json.tool

echo ""
echo "========================================================================"
echo ""

# Ask if user wants to view in browser
read -p "Open viewer in browser? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    URL="http://localhost:5000/livestream/viewer?camera=$CAMERA_ID"
    echo "Opening: $URL"

    # Try to open browser (macOS)
    if command -v open > /dev/null 2>&1; then
        open "$URL"
    else
        echo "Please open manually: $URL"
    fi
fi

echo ""
read -p "Stop stream? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "Stopping stream..."
    STOP_RESPONSE=$(curl -s -X POST $API_URL/streams/$CAMERA_ID/stop)

    echo ""
    echo "Stream stopped. Final statistics:"
    echo $STOP_RESPONSE | python3 -m json.tool

    echo ""
    echo -e "${GREEN}✅ Test complete!${NC}"
else
    echo ""
    echo "Stream still running. Stop manually:"
    echo "  curl -X POST $API_URL/streams/$CAMERA_ID/stop"
fi

echo ""
