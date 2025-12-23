# Livestreaming Service Startup

## Integrated with Main Management System

The livestreaming service is integrated into the main server management system.

## How to Start/Stop Livestreaming

**Primary method** - Use the main management scripts in the project root:

```bash
# Start all services (including livestreaming)
./managed_start.sh start

# Stop all services
./managed_start.sh stop

# Restart all services
./managed_start.sh restart

# Check status
./managed_status.sh
```

## Standalone Control (Advanced)

The livestreaming folder contains its own startup scripts that manage:
- Kurento Media Server (Podman container)
- Livestreaming API server
- Signaling WebSocket server

```bash
cd livestreaming

# Start everything (Kurento + Python services)
./start_all.sh

# Stop everything
./stop_all.sh

# Check status
./status.sh
```

**Note:** The main `managed_start.sh` calls these scripts automatically.

## Testing

- `status.sh` - Check Kurento and livestreaming status
- `test_stream.sh` - Test streaming with a camera
