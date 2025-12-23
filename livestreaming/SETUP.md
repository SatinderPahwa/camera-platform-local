# Camera Livestreaming Setup Guide

Complete setup guide for production camera BCGH livestreaming with REMB packet handling.

## Prerequisites

### Required Software

1. **Python 3.8+**
   ```bash
   python3 --version
   ```

2. **Podman** (for Kurento Media Server)
   ```bash
   podman --version
   ```

3. **Local EMQX Broker** (running on port 8883)
   ```bash
   emqx ctl status
   ```

### Required Python Packages

Install dependencies:
```bash
cd /Users/satinder/Documents/_camera_firmware/camera_project/livestreaming
pip3 install -r requirements.txt
```

Key dependencies:
- `aiohttp` - Async HTTP server
- `websockets` - WebSocket support
- `paho-mqtt` - EMQX Client
- `aiohttp-cors` - CORS support

## Quick Start

### All-in-One Startup (Recommended)

Start all services with a single command:

```bash
cd /Users/satinder/Documents/_camera_firmware/camera_project/livestreaming
./start_all.sh
```

This script will:
- Check prerequisites (Python, Podman, AWS CLI)
- Install Python dependencies if needed
- Configure external IP (auto-detect or prompt)
- Start Kurento Media Server
- Start Livestreaming API and Signaling servers
- Optionally start Dashboard server
- Display status and helpful commands

### Manual Startup (Alternative)

If you prefer to start services individually:

#### 1. Start Kurento Media Server

```bash
cd /Users/satinder/Documents/_camera_firmware/camera_project/livestreaming
./scripts/start_kurento.sh
```

This will:
- Pull Kurento 6.16.0 image if needed
- Start Kurento in Podman container
- Expose WebSocket on `ws://localhost:8888/kurento`

**Verify Kurento is running:**
```bash
podman ps | grep kms-production
podman logs kms-production
curl -s http://localhost:8888 | head -5
```

### 2. Configure External IP

Edit `config/settings.py` and set your external IP:

```python
EXTERNAL_IP = "86.20.156.73"  # Replace with your actual external IP
```

Or set environment variable:
```bash
export EXTERNAL_IP="86.20.156.73"
```

**Find your external IP:**
```bash
curl ifconfig.me
# or
curl ipinfo.io/ip
```

### 3. Start Livestreaming Service

```bash
cd /Users/satinder/Documents/_camera_firmware/camera_project/livestreaming
python3 main.py
```

This starts:
- **API Server** on `http://localhost:8080`
- **Signaling Server** on `ws://localhost:8765`

**Verify service is running:**
```bash
curl http://localhost:8080/health | python3 -m json.tool
```

Expected output:
```json
{
  "status": "healthy",
  "timestamp": "2025-01-12T...",
  "kurento_connected": true,
  "active_streams": 0,
  "total_viewers": 0
}
```

### 4. Start Dashboard Server (Optional)

The dashboard provides a web interface for stream control:

```bash
cd /Users/satinder/Documents/_camera_firmware/camera_project
python3 servers/dashboard_server.py
```

Dashboard available at: `http://localhost:5000`

## Usage

### Start a Camera Stream (API)

```bash
curl -X POST http://localhost:8080/streams/56C1CADCF1FA4C6CAEBA3E2FD85EFEBF/start \
  -H "Content-Type: application/json" \
  | python3 -m json.tool
```

Response:
```json
{
  "session_id": "stream-56C1CADC-8f7a2b1c",
  "stream_id": "8f7a2b1c-...",
  "camera_id": "56C1CADCF1FA4C6CAEBA3E2FD85EFEBF",
  "state": "active",
  "pipeline_id": "...",
  "webrtc_endpoint_id": "...",
  "started_at": "2025-01-12T..."
}
```

### View Stream (Browser)

1. **Standalone Viewer:**
   Open `livestreaming/static/viewer.html` in browser

2. **Via Dashboard:**
   - Navigate to `http://localhost:5000`
   - Click camera
   - Click "Watch Stream" button

3. **Direct Link:**
   ```
   http://localhost:5000/livestream/viewer?camera=56C1CADCF1FA4C6CAEBA3E2FD85EFEBF
   ```

### Stop a Camera Stream

```bash
curl -X POST http://localhost:8080/streams/56C1CADCF1FA4C6CAEBA3E2FD85EFEBF/stop \
  | python3 -m json.tool
```

### Monitor Active Streams

```bash
# List all streams
curl http://localhost:8080/streams | python3 -m json.tool

# Get specific stream
curl http://localhost:8080/streams/56C1CADCF1FA4C6CAEBA3E2FD85EFEBF \
  | python3 -m json.tool

# Get viewers
curl http://localhost:8080/viewers | python3 -m json.tool
```

## Configuration

### Environment Variables

```bash
# Kurento
export KURENTO_WS_URL="ws://localhost:8888/kurento"

# External IP (required!)
export EXTERNAL_IP="86.20.156.73"

# Ports
export API_SERVER_PORT=8080
export SIGNALING_SERVER_PORT=8765

# EMQX Broker
export EMQX_BROKER_HOST="127.0.0.1"
export EMQX_BROKER_PORT=8883
export EMQX_CLIENT_ID="livestream_service"

# Bandwidth (REMB)
export MAX_VIDEO_RECV_BANDWIDTH=5000  # Kbps
export MIN_VIDEO_RECV_BANDWIDTH=500   # Kbps

# Keepalive
export KEEPALIVE_INTERVAL=4  # seconds
```

### Configuration File

Edit `livestreaming/config/settings.py` for permanent configuration changes.

## Architecture Overview

```
┌─────────────┐
│   Browser   │ ◄──── WebRTC video
│   Viewer    │ ◄──── WebSocket signaling
└──────┬──────┘
       │
       │ WebSocket
       ▼
┌─────────────────────┐
│  Signaling Server   │
│   (port 8765)       │
└──────┬──────────────┘
       │
       │ Kurento API
       ▼
┌─────────────────────┐       ┌──────────────┐
│   Kurento Media     │◄──────│   Camera     │
│   Server (KMS)      │  RTP  │   (BCGH)     │
│   (port 8888)       │       └──────▲───────┘
└─────────────────────┘              │
                                     │ MQTT
                              ┌──────┴───────┐
                              │  API Server  │
                              │  (port 8080) │
                              └──────────────┘
```

### Component Responsibilities

1. **Kurento Media Server**
   - Receives RTP stream from camera
   - Generates REMB packets (prevents 30s timeout)
   - Serves WebRTC to browsers
   - Handles ICE/STUN/TURN

2. **API Server** (`server/api_server.py`)
   - REST API for stream control
   - Manages StreamManager instances
   - Coordinates Kurento resources
   - Provides stream statistics

3. **Signaling Server** (`server/signaling_server.py`)
   - WebSocket server for WebRTC signaling
   - SDP offer/answer exchange
   - ICE candidate relay
   - Viewer session management

4. **Stream Manager** (`core/stream_manager.py`)
   - Orchestrates stream lifecycle
   - Creates Kurento pipeline/endpoints
   - Sends SDP to camera via MQTT
   - Manages keepalive messages

5. **Keepalive Sender** (`core/keepalive.py`)
   - Sends periodic keepalives to camera
   - Prevents camera timeout
   - Tracks statistics

## Troubleshooting

### Kurento Won't Start

```bash
# Check Podman is running
podman version

# Check if port 8888 is free
lsof -i :8888

# View logs
podman logs kms-production

# Restart Kurento
podman restart kms-production
```

### Camera Doesn't Connect

1. **Check camera is online:**
   - Verify camera appears in dashboard
   - Check camera status is not "offline"

2. **Check MQTT topic:**
   ```bash
   # Topic format: prod/honeycomb/{CAMERA_ID}/stream/play
   # Verify camera ID is correct
   ```

3. **Check external IP is reachable:**
   - Camera must be able to reach your EXTERNAL_IP
   - Verify firewall allows RTP ports: 5006, 5007, 5008

4. **Check SDP offer:**
   ```bash
   # Look for SDP in logs
   tail -f livestreaming/logs/livestreaming.log | grep -i sdp
   ```

### Stream Times Out After 30 Seconds

This should NOT happen with proper REMB handling:

1. **Check REMB is enabled:**
   ```bash
   # In Kurento logs, look for:
   podman logs kms-production | grep -i remb
   ```

2. **Check bandwidth settings:**
   ```python
   # In config/settings.py
   MAX_VIDEO_RECV_BANDWIDTH = 5000  # Must be set
   MIN_VIDEO_RECV_BANDWIDTH = 500   # Must be set
   ```

3. **Check keepalive messages:**
   ```bash
   # Look for keepalive logs
   tail -f livestreaming/logs/livestreaming.log | grep -i keepalive
   ```

### Browser Can't Connect

1. **Check WebRTC is supported:**
   - Use Chrome, Firefox, or Safari
   - HTTPS may be required for some browsers

2. **Check ICE candidates:**
   - Open browser console
   - Look for ICE candidate messages
   - Firefox may require mDNS configuration (see below)

3. **Firefox mDNS Issue:**
   Firefox may expose `.local` mDNS candidates. Configure:
   ```
   about:config
   media.peerconnection.ice.no_host = false
   media.peerconnection.ice.default_address_only = false
   ```

### No Video in Browser

1. **Check stream is active:**
   ```bash
   curl http://localhost:8080/streams | python3 -m json.tool
   ```

2. **Check WebRTC endpoint:**
   - Should be connected to RTP endpoint
   - Check Kurento logs

3. **Check ICE state:**
   - Should reach "connected"
   - Look for ICE errors in browser console

4. **Check camera is streaming:**
   ```bash
   # Monitor network traffic
   netstat -an | grep 5006  # RTP video port
   ```

## Monitoring

### Service Logs

```bash
# Livestreaming service
tail -f livestreaming/logs/livestreaming.log

# Kurento Media Server
podman logs -f kms-production

# Dashboard server
# Logs to console
```

### Health Checks

```bash
# Livestreaming service
curl http://localhost:8080/health

# Kurento connection
curl http://localhost:8888

# Active streams
curl http://localhost:8080/streams

# Viewers
curl http://localhost:8080/viewers
```

### Performance Metrics

Check stream statistics:
```bash
curl http://localhost:8080/streams/56C1CADCF1FA4C6CAEBA3E2FD85EFEBF \
  | python3 -m json.tool
```

Key metrics:
- `duration_seconds` - Stream uptime
- `keepalive_count` - Keepalives sent
- `error_count` - Errors encountered
- `viewer_count` - Active viewers

Expected values for healthy stream:
- Keepalive every 4 seconds
- Error count should be 0
- Duration should increase steadily
- No disconnections

## Production Deployment

### Security

1. **Enable TLS:**
   - Use HTTPS for dashboard
   - Use WSS for signaling
   - Configure in `config/settings.py`

2. **Authentication:**
   - Implement user authentication
   - Restrict API access
   - Use API keys or JWT

3. **Firewall:**
   ```bash
   # Open required ports
   # 8080 - API
   # 8765 - Signaling
   # 5006-5008 - RTP/RTCP from camera
   ```

4. **EMQX Security:**
   - Use TLS for all connections (port 8883)
   - Secure the dashboard password
   - Use strong unique client IDs

### Scaling

1. **Multiple Cameras:**
   - Each camera gets its own StreamManager
   - Share single Kurento instance (handles multiple pipelines)

2. **Multiple Viewers:**
   - Each viewer gets WebRtcEndpoint connected to camera's RTP
   - Limit via `MAX_VIEWERS_PER_STREAM` (default: 10)

3. **Multiple Kurento Instances:**
   - For load distribution
   - Use load balancer
   - Implement in API server

### Monitoring Production

1. **Log Aggregation:**
   - Send logs to central service (ELK, CloudWatch)
   - Set up alerts for errors

2. **Metrics:**
   - Track stream duration
   - Monitor error rates
   - Alert on keepalive failures

3. **Uptime:**
   - Use health check endpoint
   - Set up monitoring (Datadog, New Relic)

## Testing with Camera 4

Camera 4 ID: `56C1CADCF1FA4C6CAEBA3E2FD85EFEBF`

### Complete Test Procedure

1. **Start services:**
   ```bash
   ./scripts/start_kurento.sh
   python3 main.py
   ```

2. **Start stream:**
   ```bash
   curl -X POST http://localhost:8080/streams/56C1CADCF1FA4C6CAEBA3E2FD85EFEBF/start
   ```

3. **Open viewer:**
   ```
   http://localhost:5000/livestream/viewer?camera=56C1CADCF1FA4C6CAEBA3E2FD85EFEBF
   ```

4. **Verify streaming:**
   - Video should appear within 5-10 seconds
   - Check keepalive count increases every 4 seconds
   - Stream should run for >10 minutes without timeout

5. **Stop stream:**
   ```bash
   curl -X POST http://localhost:8080/streams/56C1CADCF1FA4C6CAEBA3E2FD85EFEBF/stop
   ```

### Expected Results

- ✅ Stream starts successfully
- ✅ Camera receives REMB packets every 2-3 seconds (automatic from Kurento)
- ✅ Keepalives sent every 4 seconds
- ✅ No timeout after 30 seconds
- ✅ Stream runs for 10+ minutes
- ✅ Clean stop with statistics

## Helper Scripts

The livestreaming system includes several helper scripts for easy management:

### Start All Services

```bash
./start_all.sh
```

Starts Kurento, API, Signaling, and optionally Dashboard servers. Checks prerequisites and configuration automatically.

### Stop All Services

```bash
./stop_all.sh
```

Stops all running services. Prompts before stopping Kurento (which may be shared).

### Check Status

```bash
./status.sh
```

Displays status of all services:
- Running/stopped status
- PIDs and ports
- Health checks
- Active streams and viewers
- Uptime

### Test Stream

```bash
./test_stream.sh
```

Complete test script for Camera 4:
- Starts stream
- Monitors for 30 seconds (watches for timeout)
- Shows real-time statistics
- Verifies REMB is working
- Optionally opens browser viewer
- Clean stop with final stats

**Example output:**
```
🧪 Testing Camera 4 Livestream
========================================
✅ Services are running
✅ Stream started
   Session ID: stream-56C1CADC-abc123
   Stream ID: abc123...

Monitoring stream for 30 seconds...
[30/30s] Duration: 30s | Keepalives: 7 | Errors: 0 | Viewers: 0 | State: active

🎉 SUCCESS! Stream survived 30+ seconds without timeout!
   REMB packets are working correctly!
```

## Reference

- **POC2 Project:** `/Users/satinder/camera_broker_project/poc2_bcgh_streaming`
- **CLAUDE.md:** POC2 project documentation
- **Kurento Documentation:** https://doc-kurento.readthedocs.io/
- **WebRTC Specification:** https://webrtc.org/

## Support

For issues or questions:
1. Check status: `./status.sh`
2. Check logs: `tail -f livestreaming/logs/livestreaming.log`
3. Review troubleshooting section above
4. Consult POC2 reference for proven patterns
5. Check Kurento logs: `podman logs kms-production`
