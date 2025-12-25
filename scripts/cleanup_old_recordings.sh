#!/bin/bash
# Cleanup old recordings and database events (keep last 5 for testing)

set -e

echo "==========================================="
echo "Cleanup Old Recordings (Keep Last 5)"
echo "==========================================="
echo ""

# Get the actual user (not root when using sudo)
ACTUAL_USER="${SUDO_USER:-$USER}"

# Paths
RECORDINGS_DIR="/data/uploads/56C1CADCF1FA4C6CAEBA3E2FD85EFEBF/activity"
DB_PATH="/home/$ACTUAL_USER/camera-platform-local/data/camera_events.db"

# Check if running with sudo (needed for /data access)
if [ "$EUID" -ne 0 ]; then
    echo "❌ This script must be run with sudo"
    echo "Usage: sudo ./scripts/cleanup_old_recordings.sh"
    exit 1
fi

# 1. Clean up recording files (keep last 5)
echo "1️⃣  Cleaning up recording files..."
cd "$RECORDINGS_DIR"
TOTAL_COUNT=$(ls -t | wc -l)
echo "   Found $TOTAL_COUNT recording directories"

if [ "$TOTAL_COUNT" -gt 5 ]; then
    DELETE_COUNT=$((TOTAL_COUNT - 5))
    echo "   Deleting $DELETE_COUNT old recordings (keeping last 5)..."
    ls -t | tail -n +6 | xargs -I {} rm -rf "{}"
    echo "   ✅ Deleted $DELETE_COUNT recordings"
else
    echo "   ✅ Only $TOTAL_COUNT recordings - nothing to delete"
fi
echo ""

# 2. Get the 5 most recent event IDs from directories
echo "2️⃣  Identifying events to keep..."
KEEP_IDS=$(ls -t | head -5 | tr '\n' ',' | sed 's/,$//')
echo "   Keeping events: $KEEP_IDS"
echo ""

# 3. Clean up database (keep last 5 events)
echo "3️⃣  Cleaning up database..."

# Count before cleanup
BEFORE_COUNT=$(sudo -u "$ACTUAL_USER" sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM activity_events;")
echo "   Events before cleanup: $BEFORE_COUNT"

# Delete old events (keep last 5 by timestamp)
sudo -u "$ACTUAL_USER" sqlite3 "$DB_PATH" "DELETE FROM activity_events WHERE event_id NOT IN (SELECT event_id FROM activity_events ORDER BY start_timestamp DESC LIMIT 5);"

AFTER_COUNT=$(sudo -u "$ACTUAL_USER" sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM activity_events;")
DELETE_COUNT=$((BEFORE_COUNT - AFTER_COUNT))
echo "   ✅ Deleted $DELETE_COUNT events (kept $AFTER_COUNT)"
echo ""

# 4. Show remaining events
echo "4️⃣  Remaining events:"
sudo -u "$ACTUAL_USER" sqlite3 "$DB_PATH" "SELECT event_id, camera_name, activity_type, datetime(start_timestamp, 'unixepoch', 'localtime'), recording_path IS NOT NULL as has_recording FROM activity_events ORDER BY start_timestamp DESC;"
echo ""

echo "==========================================="
echo "✅ Cleanup Complete"
echo "==========================================="
echo ""
echo "Summary:"
echo "  - Recording files: Kept last 5"
echo "  - Database events: Kept last 5"
echo ""
echo "Next: Restart services to apply database fix"
echo "  sudo systemctl start emqx"
echo "  cd ~/camera-platform-local && ./scripts/managed_start.sh restart"
