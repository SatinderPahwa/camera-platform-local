#!/bin/bash
#
# Start All Livestreaming Services
#
# This script starts:
# 1. Kurento Media Server (Podman)
# 2. Livestreaming API and Signaling servers
# 3. Dashboard server (optional)
#

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "========================================================================"
echo "🚀 Starting Camera Livestreaming System"
echo "========================================================================"
echo ""

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if a port is in use
port_in_use() {
    lsof -i ":$1" >/dev/null 2>&1
}

# Function to wait for service to be ready
wait_for_service() {
    local url=$1
    local name=$2
    local max_wait=30
    local count=0

    echo -n "Waiting for $name to be ready"
    while [ $count -lt $max_wait ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            echo ""
            echo -e "${GREEN}✅ $name is ready${NC}"
            return 0
        fi
        echo -n "."
        sleep 1
        count=$((count + 1))
    done
    echo ""
    echo -e "${RED}❌ $name failed to start within ${max_wait}s${NC}"
    return 1
}

# Check prerequisites
echo "📋 Checking prerequisites..."
echo ""

# Check Python
if ! command_exists python3; then
    echo -e "${RED}❌ Python 3 not found${NC}"
    echo "   Install: brew install python3"
    exit 1
fi
echo -e "${GREEN}✅ Python 3: $(python3 --version)${NC}"

# Check Container Runtime (Podman or Docker)
if command_exists podman; then
    CONTAINER_CMD="podman"
    echo -e "${GREEN}✅ Podman: $(podman --version)${NC}"
elif command_exists docker; then
    CONTAINER_CMD="docker"
    echo -e "${GREEN}✅ Docker: $(docker --version)${NC}"
else
    echo -e "${RED}❌ No container runtime found${NC}"
    echo "   Install: brew install podman OR brew install --cask docker"
    exit 1
fi

# Check if Podman machine is running (macOS only)
if [[ "$OSTYPE" == "darwin"* ]] && [[ "$CONTAINER_CMD" == "podman" ]]; then
    echo "Checking Podman machine status..."
    if ! podman ps >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Podman machine not running, starting it...${NC}"

        # Try to start the machine
        if podman machine start 2>&1 | grep -q "already running"; then
            echo -e "${GREEN}✅ Podman machine already running${NC}"
        else
            echo -e "${GREEN}✅ Podman machine started${NC}"
            sleep 3  # Give it a moment to initialize
        fi

        # Verify it's now working
        if ! podman ps >/dev/null 2>&1; then
            echo -e "${RED}❌ Failed to start Podman machine${NC}"
            echo "   Try manually: podman machine start"
            exit 1
        fi
    fi
fi

# Check EMQX Broker
echo "Checking EMQX Broker..."
if command -v emqx >/dev/null 2>&1; then
    if sudo emqx ctl status >/dev/null 2>&1; then
        echo -e "${GREEN}✅ EMQX Broker is running${NC}"
    else
        echo -e "${RED}❌ EMQX Broker is not running${NC}"
        echo "   Start: sudo systemctl start emqx"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠️  EMQX not found in path (assuming running)${NC}"
fi

# Check Python dependencies
echo ""
echo "📦 Checking Python dependencies..."

# Use project venv if available
PYTHON_CMD="python3"
PIP_CMD="pip3"
if [ -f "$PROJECT_DIR/venv/bin/python3" ]; then
    PYTHON_CMD="$PROJECT_DIR/venv/bin/python3"
    PIP_CMD="$PROJECT_DIR/venv/bin/pip3"
    echo -e "${GREEN}✅ Using project virtual environment${NC}"
fi

if ! $PYTHON_CMD -c "import aiohttp" 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Missing Python dependencies${NC}"
    echo "   Installing dependencies..."
    $PIP_CMD install -r "$SCRIPT_DIR/requirements.txt"
fi
echo -e "${GREEN}✅ Python dependencies OK${NC}"

# Check external IP configuration
echo ""
echo "🌐 Checking configuration..."
if [ -z "$EXTERNAL_IP" ]; then
    # Try to get external IP
    EXTERNAL_IP=$(curl -s ifconfig.me 2>/dev/null || echo "")
    if [ -n "$EXTERNAL_IP" ]; then
        echo -e "${YELLOW}⚠️  EXTERNAL_IP not set, detected: $EXTERNAL_IP${NC}"
        export EXTERNAL_IP
        echo "   Set manually: export EXTERNAL_IP=\"your-ip-here\""
    else
        echo -e "${RED}❌ EXTERNAL_IP not configured${NC}"
        echo "   Please set: export EXTERNAL_IP=\"your-external-ip\""
        exit 1
    fi
else
    echo -e "${GREEN}✅ EXTERNAL_IP: $EXTERNAL_IP${NC}"
fi

echo ""
echo "========================================================================"
echo "Starting Services"
echo "========================================================================"
echo ""

# Step 1: Start Kurento Media Server
echo "1️⃣  Starting Kurento Media Server..."
echo ""

if $CONTAINER_CMD ps --format "{{.Names}}" | grep -q "^kms-production$"; then
    echo -e "${GREEN}✅ Kurento already running${NC}"
else
    "$SCRIPT_DIR/scripts/start_kurento.sh"
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ Failed to start Kurento${NC}"
        exit 1
    fi
fi

# Wait for Kurento to be ready
sleep 2
if ! wait_for_service "http://localhost:8888" "Kurento"; then
    echo -e "${RED}❌ Kurento did not start properly${NC}"
    echo "   Check logs: $CONTAINER_CMD logs kms-production"
    exit 1
fi

echo ""
echo "2️⃣  Starting Livestreaming API and Signaling servers..."
echo ""

# Check if already running
if port_in_use 8080; then
    echo -e "${YELLOW}⚠️  Port 8080 already in use${NC}"
    echo "   Stop existing service or change port"
    read -p "Kill existing process and continue? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        lsof -ti :8080 | xargs kill -9 2>/dev/null || true
        sleep 2
    else
        exit 1
    fi
fi

# Create logs directory
mkdir -p "$SCRIPT_DIR/logs"

# Start livestreaming service in background (use venv python if available)
cd "$SCRIPT_DIR"
nohup $PYTHON_CMD main.py > logs/main.out 2>&1 &
LIVESTREAM_PID=$!
echo $LIVESTREAM_PID > logs/livestream.pid

echo -e "${BLUE}Started livestreaming service (PID: $LIVESTREAM_PID)${NC}"

# Wait for API to be ready
if ! wait_for_service "http://localhost:8080/health" "Livestreaming API"; then
    echo -e "${RED}❌ Livestreaming service failed to start${NC}"
    echo "   Check logs: tail -f $SCRIPT_DIR/logs/livestreaming.log"
    echo "              tail -f $SCRIPT_DIR/logs/main.out"
    kill $LIVESTREAM_PID 2>/dev/null || true
    exit 1
fi

# Check health
echo ""
echo "🏥 Health check:"
curl -s http://localhost:8080/health | python3 -m json.tool

echo ""
echo "3️⃣  Dashboard server..."
echo ""

# Dashboard server is managed by main project's managed_start.sh
if port_in_use 5000; then
    echo -e "${GREEN}✅ Dashboard already running on port 5000${NC}"
    echo -e "${BLUE}ℹ️  Dashboard is managed by main project's managed_start.sh${NC}"
else
    echo -e "${YELLOW}⚠️  Dashboard not running on port 5000${NC}"
    echo -e "${BLUE}ℹ️  Start dashboard with: ./managed_start.sh start${NC}"
fi

echo ""
echo "========================================================================"
echo "✅ All Services Started Successfully!"
echo "========================================================================"
echo ""
echo "📡 Service URLs:"
echo "   API Server:       http://localhost:8080"
echo "   Signaling Server: ws://localhost:8765"
echo "   Kurento:          ws://localhost:8888/kurento"
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "   Dashboard:        http://localhost:5000"
fi
echo ""
echo "📊 Status:"
echo "   Health check:  curl http://localhost:8080/health | python3 -m json.tool"
echo "   List streams:  curl http://localhost:8080/streams | python3 -m json.tool"
echo "   Kurento logs:  $CONTAINER_CMD logs -f kms-production"
echo "   Service logs:  tail -f $SCRIPT_DIR/logs/livestreaming.log"
echo ""
echo "🧪 Test with Camera 4:"
echo "   Start stream:"
echo "     curl -X POST http://localhost:8080/streams/56C1CADCF1FA4C6CAEBA3E2FD85EFEBF/start"
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "   View in browser:"
    echo "     http://localhost:5000/livestream/viewer?camera=56C1CADCF1FA4C6CAEBA3E2FD85EFEBF"
fi
echo ""
echo "🛑 Stop all services:"
echo "   $SCRIPT_DIR/stop_all.sh"
echo ""
echo "========================================================================"

# Save configuration
cat > "$SCRIPT_DIR/logs/services.env" <<EOF
# Service PIDs and configuration
LIVESTREAM_PID=$LIVESTREAM_PID
DASHBOARD_PID=${DASHBOARD_PID:-}
EXTERNAL_IP=$EXTERNAL_IP
STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EOF

echo "Service info saved to: $SCRIPT_DIR/logs/services.env"
echo ""
