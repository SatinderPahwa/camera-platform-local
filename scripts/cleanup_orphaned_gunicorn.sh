#!/bin/bash

# Cleanup Orphaned Gunicorn Processes
# Kills old gunicorn masters that are not tracked in PID file

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_FILE="$PROJECT_DIR/pids/gunicorn.pid"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "======================================"
echo "Gunicorn Orphan Cleanup"
echo "======================================"

# Get current PID if exists
CURRENT_PID=""
if [ -f "$PID_FILE" ]; then
    CURRENT_PID=$(cat "$PID_FILE")
    echo -e "${GREEN}Current master PID: $CURRENT_PID${NC}"
else
    echo -e "${YELLOW}No PID file found - will kill all gunicorn processes${NC}"
fi

# Find all gunicorn master processes
# Masters have command line containing '/bin/gunicorn --config'
MASTERS=$(pgrep -f "bin/gunicorn --config config/gunicorn_config.py")

if [ -z "$MASTERS" ]; then
    echo -e "${GREEN}No gunicorn processes found${NC}"
    exit 0
fi

echo ""
echo "Found gunicorn processes:"
ps -f -p $MASTERS 2>/dev/null | head -20

echo ""
echo "Analyzing process tree..."

KILLED_COUNT=0
KEPT_COUNT=0

for pid in $MASTERS; do
    # Check if this is the current master
    if [ "$pid" = "$CURRENT_PID" ]; then
        echo -e "${GREEN}✓ Keeping current master: $pid${NC}"
        KEPT_COUNT=$((KEPT_COUNT + 1))
        continue
    fi

    # This is an orphaned master - kill it
    if ps -p $pid > /dev/null 2>&1; then
        START_TIME=$(ps -p $pid -o lstart= 2>/dev/null)
        echo -e "${YELLOW}✗ Killing orphaned master: $pid (started: $START_TIME)${NC}"

        # Send TERM for graceful shutdown
        if kill -TERM $pid 2>/dev/null; then
            # Wait up to 10 seconds for graceful shutdown
            waited=0
            while ps -p $pid > /dev/null 2>&1 && [ $waited -lt 10 ]; do
                sleep 1
                waited=$((waited + 1))
            done

            # Force kill if still alive
            if ps -p $pid > /dev/null 2>&1; then
                echo "  Timeout - force killing $pid and its workers..."
                pkill -9 -P $pid  # Kill all children
                kill -9 $pid 2>/dev/null
            fi

            KILLED_COUNT=$((KILLED_COUNT + 1))
        else
            echo -e "${RED}  Failed to kill $pid (may need sudo)${NC}"
        fi
    fi
done

echo ""
echo "======================================"
echo -e "${GREEN}Cleanup Complete${NC}"
echo "  Kept: $KEPT_COUNT"
echo "  Killed: $KILLED_COUNT"
echo "======================================"

# Show final count
REMAINING=$(pgrep -f "bin/gunicorn" | wc -l)
echo ""
echo "Remaining gunicorn processes: $REMAINING"

if [ $REMAINING -gt 15 ]; then
    echo -e "${YELLOW}⚠️  Still more than 15 processes - may need manual cleanup${NC}"
fi
