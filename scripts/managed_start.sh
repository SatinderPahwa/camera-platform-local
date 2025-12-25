#!/bin/bash

# Managed Server Startup Script - EMQX Edition
# Prevents duplicate processes and tracks PIDs properly

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_DIR="$PROJECT_DIR/pids"
LOG_DIR="$PROJECT_DIR/logs"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Create necessary directories
mkdir -p "$PID_DIR"
mkdir -p "$LOG_DIR"
mkdir -p "$PROJECT_DIR/data"
mkdir -p "$PROJECT_DIR/data/uploads"

# Load environment variables from .env file
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a  # Export all variables
    source "$PROJECT_DIR/.env"
    set +a  # Stop exporting
    echo "✓ Loaded environment from .env"
else
    echo "⚠️  Warning: .env file not found at $PROJECT_DIR/.env"
fi

# Convert relative paths to absolute (in case .env uses relative paths)
# This ensures LOG_DIR and PID_DIR work correctly even after cd commands
if [[ ! "$PID_DIR" = /* ]]; then
    PID_DIR="$PROJECT_DIR/$PID_DIR"
fi
if [[ ! "$LOG_DIR" = /* ]]; then
    LOG_DIR="$PROJECT_DIR/$LOG_DIR"
fi

echo "======================================"
echo "VBC01 Camera Platform - EMQX Edition"
echo "======================================"

# Function to check if process is already running
check_process() {
    local name=$1
    local pid_file="$PID_DIR/${name}.pid"

    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0  # Running
        else
            rm "$pid_file"  # Clean up stale PID
            return 1
        fi
    fi
    return 1
}

# Function to start a server
start_server() {
    local name=$1
    local script=$2
    local use_sudo=${3:-false}
    local log_file="$LOG_DIR/${name}.log"
    local pid_file="$PID_DIR/${name}.pid"

    # Check if already running
    if check_process "$name"; then
        local pid=$(cat "$pid_file")
        echo -e "${YELLOW}⚠️  ${name} already running (PID: $pid)${NC}"
        return 0
    fi

    # Start the server
    echo -n "Starting $name..."
    cd "$PROJECT_DIR/servers"

    # Use venv python if available
    local python_cmd="python3"
    if [ -f "$PROJECT_DIR/venv/bin/python3" ]; then
        python_cmd="$PROJECT_DIR/venv/bin/python3"
    fi

    # Set DATABASE_PATH to absolute path
    export DATABASE_PATH="$PROJECT_DIR/data/camera_events.db"

    if [ "$use_sudo" = true ]; then
        # Config server needs sudo for port 80
        sudo sh -c "DATABASE_PATH='$DATABASE_PATH' setsid '$python_cmd' '$script' > '$log_file' 2>&1 &"
        sleep 2
        local pid=$(pgrep -f "$script" | tail -1)

        if [ -z "$pid" ]; then
            echo -e "${RED} ✗ Failed to start${NC}"
            return 1
        fi
    else
        $python_cmd "$script" > "$log_file" 2>&1 &
        local pid=$!
    fi

    # Save PID
    echo $pid > "$pid_file"
    sleep 2

    if ps -p "$pid" > /dev/null 2>&1; then
        echo -e "${GREEN} ✓ Started (PID: $pid)${NC}"
        return 0
    else
        echo -e "${RED} ✗ Failed to start${NC}"
        rm "$pid_file"
        return 1
    fi
}

# Function to start a server with Gunicorn
start_server_gunicorn() {
    local name=$1
    local app_module=$2
    local use_sudo=${3:-false}
    local log_file="$LOG_DIR/${name}.log"
    # Gunicorn creates its own PID file at pids/gunicorn.pid (set in gunicorn_config.py)
    local gunicorn_pid_file="$PID_DIR/gunicorn.pid"
    # Also maintain dashboard_server.pid for compatibility with managed_status.sh
    local pid_file="$PID_DIR/${name}.pid"

    # Check if already running by checking gunicorn.pid
    if [ -f "$gunicorn_pid_file" ]; then
        local pid=$(cat "$gunicorn_pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo -e "${YELLOW}⚠️  ${name} already running (PID: $pid)${NC}"
            return 0
        else
            # Stale PID file, remove it
            rm "$gunicorn_pid_file" 2>/dev/null
            rm "$pid_file" 2>/dev/null
        fi
    fi

    # Start Gunicorn
    echo -n "Starting $name (Gunicorn)..."
    cd "$PROJECT_DIR"

    # Use venv python if available
    local python_cmd="python3"
    local gunicorn_cmd="gunicorn"
    if [ -f "$PROJECT_DIR/venv/bin/python3" ]; then
        python_cmd="$PROJECT_DIR/venv/bin/python3"
        gunicorn_cmd="$PROJECT_DIR/venv/bin/gunicorn"
    fi

    # Set DATABASE_PATH to absolute path
    export DATABASE_PATH="$PROJECT_DIR/data/camera_events.db"

    if [ "$use_sudo" = true ]; then
        # Dashboard with sudo (if needed for port 443)
        sudo sh -c "DATABASE_PATH='$DATABASE_PATH' '$gunicorn_cmd' --config config/gunicorn_config.py --daemon '$app_module' 2>&1 | tee -a '$log_file'"
        sleep 2
    else
        # Normal startup without sudo
        $gunicorn_cmd --config config/gunicorn_config.py --daemon "$app_module" >> "$log_file" 2>&1
        sleep 2
    fi

    # Wait for Gunicorn to create its PID file
    local waited=0
    while [ ! -f "$gunicorn_pid_file" ] && [ $waited -lt 5 ]; do
        sleep 1
        waited=$((waited + 1))
    done

    # Read PID from Gunicorn's PID file
    if [ -f "$gunicorn_pid_file" ]; then
        local pid=$(cat "$gunicorn_pid_file")
        # Also copy to dashboard_server.pid for compatibility
        echo $pid > "$pid_file"
    else
        echo -e "${RED} ✗ Failed to start (PID file not created)${NC}"
        return 1
    fi

    # Verify process is running
    if ps -p "$pid" > /dev/null 2>&1; then
        echo -e "${GREEN} ✓ Started (PID: $pid)${NC}"
        return 0
    else
        echo -e "${RED} ✗ Failed to start${NC}"
        rm "$pid_file" 2>/dev/null
        rm "$gunicorn_pid_file" 2>/dev/null
        return 1
    fi
}

# Function to stop a server
stop_server() {
    local name=$1
    local pid_file="$PID_DIR/${name}.pid"

    # For dashboard_server, also check gunicorn.pid
    local gunicorn_pid_file="$PID_DIR/gunicorn.pid"
    if [ "$name" = "dashboard_server" ] && [ -f "$gunicorn_pid_file" ]; then
        pid_file="$gunicorn_pid_file"
    fi

    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            # Check if this is a Gunicorn master process
            if ps -p "$pid" -o command= | grep -q gunicorn; then
                echo -n "Stopping $name (Gunicorn - graceful shutdown)..."

                # Send TERM signal for graceful shutdown
                if kill -TERM "$pid" 2>/dev/null; then
                    # Wait up to 30 seconds for graceful shutdown
                    local waited=0
                    while ps -p "$pid" > /dev/null 2>&1 && [ $waited -lt 30 ]; do
                        sleep 1
                        waited=$((waited + 1))
                    done

                    if ps -p "$pid" > /dev/null 2>&1; then
                        echo " timeout, force killing..."
                        sudo kill -9 "$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null
                    else
                        echo " done"
                    fi
                else
                    # Might need sudo
                    sudo kill -TERM "$pid" 2>/dev/null
                    sleep 2
                    if ps -p "$pid" > /dev/null 2>&1; then
                        sudo kill -9 "$pid" 2>/dev/null
                    fi
                    echo " done [required sudo]"
                fi
            else
                # Regular process (not Gunicorn)
                if kill "$pid" 2>/dev/null; then
                    echo "Stopped $name (PID: $pid)"
                else
                    # Process might be owned by root, try with sudo and force kill
                    sudo kill -9 "$pid" 2>/dev/null && echo "Stopped $name (PID: $pid) [required sudo]" || echo "Failed to stop $name"
                fi
            fi
            rm "$pid_file"
            # Also remove both PID files for dashboard_server
            if [ "$name" = "dashboard_server" ]; then
                rm "$PID_DIR/dashboard_server.pid" 2>/dev/null
                rm "$PID_DIR/gunicorn.pid" 2>/dev/null
            fi
        else
            rm "$pid_file"
        fi
    fi
}

# Function to check EMQX status
check_emqx() {
    echo ""
    echo -e "${BLUE}Checking EMQX broker...${NC}"

    if command -v emqx &> /dev/null; then
        if sudo emqx ctl status &> /dev/null; then
            echo -e "${GREEN}✓ EMQX broker is running${NC}"
            return 0
        else
            echo -e "${RED}✗ EMQX broker is not running${NC}"
            echo -e "${YELLOW}  Start EMQX: sudo systemctl start emqx${NC}"
            return 1
        fi
    else
        echo -e "${RED}✗ EMQX not installed${NC}"
        echo -e "${YELLOW}  Install: brew install emqx (macOS) or see https://www.emqx.io/docs/en/latest/deploy/install.html${NC}"
        return 1
    fi
}

# Parse command line arguments
ACTION="${1:-start}"

case "$ACTION" in
    start)
        echo "Starting all servers..."
        echo ""

        # Check EMQX first
        if ! check_emqx; then
            echo ""
            echo -e "${RED}Cannot start platform without EMQX broker${NC}"
            exit 1
        fi

        echo ""
        echo "Starting platform services..."

        # Start servers in order
        start_server "config_server" "enhanced_config_server.py" true
        start_server "mqtt_processor" "local_mqtt_processor.py"
        # Dashboard runs on Gunicorn (production WSGI server) - port 5000, reads SSL certs via ssl-certs group
        start_server_gunicorn "dashboard_server" "servers.wsgi:application" false

        # Start livestreaming system
        echo ""
        echo "Starting livestreaming system..."
        cd "$PROJECT_DIR/livestreaming"
        ./start_all.sh
        cd "$PROJECT_DIR"

        echo ""
        echo "======================================"
        echo "Startup Complete"
        echo "======================================"
        echo ""
        echo -e "${GREEN}Dashboard: http://localhost:${DASHBOARD_SERVER_PORT:-5000}${NC}"
        echo ""

        # Show status
        "$SCRIPT_DIR/managed_status.sh"
        ;;

    stop)
        echo "Stopping all servers..."
        echo ""

        # Stop livestreaming system first
        echo "Stopping livestreaming system..."
        cd "$PROJECT_DIR/livestreaming"
        ./stop_all.sh
        cd "$PROJECT_DIR"

        stop_server "dashboard_server"
        stop_server "mqtt_processor"
        stop_server "config_server"

        echo ""
        echo "All servers stopped"
        echo -e "${YELLOW}Note: EMQX broker not stopped (managed separately)${NC}"
        ;;

    restart)
        "$0" stop
        echo ""
        sleep 2
        "$0" start
        ;;

    status)
        "$SCRIPT_DIR/managed_status.sh"
        ;;

    *)
        echo "Usage: $0 {start|stop|restart|status}"
        echo ""
        echo "  start   - Start all servers (skip if already running)"
        echo "  stop    - Stop all servers"
        echo "  restart - Stop and start all servers"
        echo "  status  - Show server status"
        exit 1
        ;;
esac
