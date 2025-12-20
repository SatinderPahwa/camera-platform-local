#!/bin/bash
#
# Comprehensive Health Check and Auto-Restart Script - EMQX Edition
# Monitors all critical services and restarts if any issues detected
#
# Adapted from AWS IoT version for EMQX MQTT broker
#

# Detect project directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_DIR/logs/health_check.log"
TIMEOUT_SECONDS=5
MAX_CLOSE_WAIT=5

# Service endpoints and ports
CONFIG_SERVER_URL="https://localhost:8443/health"
DASHBOARD_SERVER_URL="http://localhost:5000"

# Function to log with timestamp
log() {
    echo "[$(date "+%Y-%m-%d %H:%M:%S")] $1" >> "$LOG_FILE"
}

# Function to restart all services
restart_all_services() {
    log "⚠️  RESTARTING ALL SERVICES - Reason: $1"

    cd "$PROJECT_DIR"

    # Use managed_start.sh to restart everything
    if /bin/bash ./scripts/managed_start.sh restart >> "$LOG_FILE" 2>&1; then
        log "✅ All services restarted successfully"
        return 0
    else
        log "❌ Error during service restart"
        return 1
    fi
}

# Start health check
log "=== Health Check Started ==="

ISSUES_FOUND=false
ISSUE_REASON=""

# Check 1: Config Server (port 8443)
if timeout "$TIMEOUT_SECONDS" curl -k -s "$CONFIG_SERVER_URL" > /dev/null 2>&1; then
    log "✅ Config server responding"
else
    log "❌ Config server not responding"
    ISSUES_FOUND=true
    ISSUE_REASON="Config server not responding"
fi

# Check 2: Dashboard Server (port 5000)
if timeout "$TIMEOUT_SECONDS" curl -s "$DASHBOARD_SERVER_URL" > /dev/null 2>&1; then
    log "✅ Dashboard server responding"
else
    log "❌ Dashboard server not responding"
    ISSUES_FOUND=true
    ISSUE_REASON="${ISSUE_REASON:+$ISSUE_REASON; }Dashboard server not responding"
fi

# Check 3: CoTURN (ports 3478 and 5349)
if ss -tuln 2>/dev/null | grep -q ":3478 "; then
    log "✅ CoTURN port 3478 listening"
else
    log "❌ CoTURN port 3478 not listening"
    ISSUES_FOUND=true
    ISSUE_REASON="${ISSUE_REASON:+$ISSUE_REASON; }CoTURN port 3478 down"
fi

if ss -tuln 2>/dev/null | grep -q ":5349 "; then
    log "✅ CoTURN port 5349 listening"
else
    log "❌ CoTURN port 5349 not listening"
    ISSUES_FOUND=true
    ISSUE_REASON="${ISSUE_REASON:+$ISSUE_REASON; }CoTURN port 5349 down"
fi

# Check 4: Kurento Media Server (Docker container)
KURENTO_OK=true
if ! docker ps --format "{{.Names}}" 2>/dev/null | grep -q "kms-production"; then
    log "❌ Kurento container not running"
    ISSUES_FOUND=true
    ISSUE_REASON="${ISSUE_REASON:+$ISSUE_REASON; }Kurento container down"
    KURENTO_OK=false
elif ! timeout "$TIMEOUT_SECONDS" curl -s -I http://localhost:8888 2>&1 | grep -q "426"; then
    log "❌ Kurento Media Server not responding"
    ISSUES_FOUND=true
    ISSUE_REASON="${ISSUE_REASON:+$ISSUE_REASON; }Kurento not responding"
    KURENTO_OK=false
fi

if [ "$KURENTO_OK" = "true" ]; then
    log "✅ Kurento Media Server healthy"
fi

# Check 5: EMQX Broker (port 8883 - MQTT over TLS)
if ss -tuln 2>/dev/null | grep -q ":8883 "; then
    log "✅ EMQX broker port 8883 listening"
else
    log "❌ EMQX broker port 8883 not listening"
    ISSUES_FOUND=true
    ISSUE_REASON="${ISSUE_REASON:+$ISSUE_REASON; }EMQX broker down"
fi

# Check 6: EMQX is actually running (not just port listening)
if sudo emqx ctl status > /dev/null 2>&1; then
    log "✅ EMQX broker running"
else
    log "❌ EMQX broker not running"
    ISSUES_FOUND=true
    ISSUE_REASON="${ISSUE_REASON:+$ISSUE_REASON; }EMQX not running"
fi

# Check 7: CLOSE-WAIT connection leak on dashboard server (port 5000)
CLOSE_WAIT_COUNT=$(ss -tn 2>/dev/null | grep ":5000" | grep "CLOSE-WAIT" | wc -l)
if [ "$CLOSE_WAIT_COUNT" -ge "$MAX_CLOSE_WAIT" ]; then
    log "❌ CLOSE-WAIT threshold exceeded ($CLOSE_WAIT_COUNT connections)"
    ISSUES_FOUND=true
    ISSUE_REASON="${ISSUE_REASON:+$ISSUE_REASON; }CLOSE-WAIT leak ($CLOSE_WAIT_COUNT)"
else
    log "✅ CLOSE-WAIT connections OK ($CLOSE_WAIT_COUNT)"
fi

# Check 8: CLOSE-WAIT on config server (port 8443)
CONFIG_CLOSE_WAIT=$(ss -tn 2>/dev/null | grep ":8443" | grep "CLOSE-WAIT" | wc -l)
if [ "$CONFIG_CLOSE_WAIT" -ge "$MAX_CLOSE_WAIT" ]; then
    log "❌ Config server CLOSE-WAIT threshold exceeded ($CONFIG_CLOSE_WAIT connections)"
    ISSUES_FOUND=true
    ISSUE_REASON="${ISSUE_REASON:+$ISSUE_REASON; }Config CLOSE-WAIT leak ($CONFIG_CLOSE_WAIT)"
else
    log "✅ Config server CLOSE-WAIT OK ($CONFIG_CLOSE_WAIT)"
fi

# Decide if restart is needed
if [ "$ISSUES_FOUND" = "true" ]; then
    restart_all_services "$ISSUE_REASON"
else
    log "✅ SUCCESS: All services healthy"
fi

log "=== Health Check Complete ==="
