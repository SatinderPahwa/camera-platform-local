#!/bin/bash
#
# Log Cleanup Script
# Removes log files older than 15 days to prevent disk space issues
#

# Detect project directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
LIVESTREAM_LOG_DIR="$PROJECT_DIR/livestreaming/logs"
RETENTION_DAYS=15

# Function to log cleanup actions
log_cleanup() {
    echo "[$(date "+%Y-%m-%d %H:%M:%S")] $1"
}

log_cleanup "=== Log Cleanup Started ==="
log_cleanup "Retention period: $RETENTION_DAYS days"

# Count and size before cleanup
TOTAL_FILES_BEFORE=$(find "$LOG_DIR" "$LIVESTREAM_LOG_DIR" -name "*.log" -type f 2>/dev/null | wc -l)
TOTAL_SIZE_BEFORE=$(du -sh "$LOG_DIR" 2>/dev/null | cut -f1)

log_cleanup "Files before cleanup: $TOTAL_FILES_BEFORE"
log_cleanup "Total size before: $TOTAL_SIZE_BEFORE"

# Cleanup main logs directory
if [ -d "$LOG_DIR" ]; then
    log_cleanup "Cleaning $LOG_DIR..."

    # Find and remove log files older than RETENTION_DAYS
    DELETED_COUNT=0
    while IFS= read -r -d '' file; do
        log_cleanup "Removing: $file"
        rm -f "$file"
        DELETED_COUNT=$((DELETED_COUNT + 1))
    done < <(find "$LOG_DIR" -name "*.log" -type f -mtime +$RETENTION_DAYS -print0 2>/dev/null)

    log_cleanup "Deleted $DELETED_COUNT files from main logs"
fi

# Cleanup livestreaming logs directory
if [ -d "$LIVESTREAM_LOG_DIR" ]; then
    log_cleanup "Cleaning $LIVESTREAM_LOG_DIR..."

    # Find and remove log files older than RETENTION_DAYS
    DELETED_COUNT=0
    while IFS= read -r -d '' file; do
        log_cleanup "Removing: $file"
        rm -f "$file"
        DELETED_COUNT=$((DELETED_COUNT + 1))
    done < <(find "$LIVESTREAM_LOG_DIR" -name "*.log" -type f -mtime +$RETENTION_DAYS -print0 2>/dev/null)

    log_cleanup "Deleted $DELETED_COUNT files from livestreaming logs"
fi

# Optional: Rotate current log files if they're too large (>100MB)
log_cleanup "Checking for large log files..."
while IFS= read -r -d '' file; do
    SIZE_MB=$(du -m "$file" | cut -f1)
    if [ "$SIZE_MB" -gt 100 ]; then
        log_cleanup "Rotating large file: $file ($SIZE_MB MB)"
        # Rotate: file.log -> file.log.old
        mv "$file" "${file}.old"
        touch "$file"
        chmod 644 "$file"

        # Remove old rotation if it exists
        if [ -f "${file}.old.old" ]; then
            rm -f "${file}.old.old"
        fi

        # Rename previous old file
        if [ -f "${file}.old" ]; then
            mv "${file}.old" "${file}.old.old" 2>/dev/null || true
        fi
    fi
done < <(find "$LOG_DIR" "$LIVESTREAM_LOG_DIR" -name "*.log" -type f -print0 2>/dev/null)

# Count and size after cleanup
TOTAL_FILES_AFTER=$(find "$LOG_DIR" "$LIVESTREAM_LOG_DIR" -name "*.log" -type f 2>/dev/null | wc -l)
TOTAL_SIZE_AFTER=$(du -sh "$LOG_DIR" 2>/dev/null | cut -f1)

log_cleanup "Files after cleanup: $TOTAL_FILES_AFTER"
log_cleanup "Total size after: $TOTAL_SIZE_AFTER"
log_cleanup "=== Log Cleanup Complete ==="
