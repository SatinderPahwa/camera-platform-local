# Camera Livestreaming Module

Production-grade WebRTC livestreaming for Hive cameras using Kurento Media Server.

## Overview

This module provides BCGH (WebRTC) livestreaming capabilities for cameras, solving the 30-second REMB timeout issue through Kurento Media Server integration. It supports multiple concurrent viewers per camera stream with automatic session management.

## Architecture

```
Browser Dashboard
     ↓ POST /api/stream/start/{camera_id}
Livestreaming API
     ↓ Local EMQX MQTT (SDP offer)
Camera (BCGH mode)
     ↓ RTP Stream (video/audio)
Kurento Media Server 6.16.0
     ↓ WebRTC + Trickle ICE
WebSocket Signaling Server
     ↓ SDP/ICE Exchange
Browser Viewer (WebRTC)
```

## Directory Structure

```
livestreaming/
├── core/                   # Core streaming logic
│   ├── kurento_client.py  # KMS WebSocket client
│   ├── stream_manager.py  # Camera stream session management
│   ├── sdp_processor.py   # SDP offer/answer generation
│   └── keepalive.py       # Camera keepalive sender
├── server/                 # Server components
│   ├── api_server.py      # REST API for stream control
│   └── signaling_server.py # WebSocket server for viewer signaling
├── config/                 # Configuration
│   ├── settings.py        # Livestreaming settings
│   └── kurento.conf.json  # KMS configuration
├── static/                 # Static files
│   └── js/
│       └── webrtc_viewer.js  # Browser WebRTC client
├── templates/              # HTML templates
│   └── viewer.html        # Viewer page template
├── logs/                   # Log files
├── tests/                  # Unit tests
└── README.md              # This file
```

## Key Features

- **Multiple Viewers**: Multiple browsers can view same camera stream
- **Automatic REMB**: Kurento handles REMB feedback to prevent camera timeout
- **Session Management**: Tracks active streams and viewers
- **Error Recovery**: Automatic cleanup and restart capabilities
- **Production Ready**: Comprehensive logging, error handling
- **Future-Proof**: Authentication hooks for external access

## Quick Start

### Prerequisites

1. Kurento Media Server 6.16.0 running (via Podman/Docker)
2. Local EMQX Broker running on port 8883 (TLS)
3. Python dependencies: `aiohttp`, `paho-mqtt`, `websockets`

### Start Streaming

1. **Start Platform**:
```bash
./scripts/managed_start.sh start
```
This will automatically start Kurento and all livestreaming services.

2. **From Dashboard**: Click "Start Stream" on any camera

3. **View Stream**: Navigate to `/stream/view/{camera_id}`

## API Endpoints

### Stream Control

- `POST /api/stream/start/{camera_id}` - Start camera stream
- `POST /api/stream/stop/{camera_id}` - Stop camera stream
- `GET /api/stream/status/{camera_id}` - Get stream status
- `GET /api/stream/active` - List all active streams

### Viewer

- `GET /stream/view/{camera_id}` - View camera stream
- `WS ws://localhost:8765/webrtc` - WebSocket signaling

## Configuration

### Kurento Settings (`config/settings.py`)

```python
KURENTO_WS_URL = "ws://localhost:8888/kurento"
KURENTO_STUN_SERVER = "stun.l.google.com:19302"
EXTERNAL_IP = "192.168.199.173"  # Your external IP
```

### Camera Settings

```python
CAMERA_RTP_AUDIO_PORT = 5008
CAMERA_RTP_VIDEO_PORT = 5006
CAMERA_RTCP_PORT = 5007
```

### Bandwidth Settings

```python
MAX_VIDEO_BANDWIDTH = 5000  # Kbps
MIN_VIDEO_BANDWIDTH = 500   # Kbps
```

## Database Schema

### `stream_sessions` Table

```sql
CREATE TABLE stream_sessions (
    session_id TEXT PRIMARY KEY,
    camera_id TEXT NOT NULL,
    pipeline_id TEXT,
    rtp_endpoint_id TEXT,
    webrtc_endpoint_id TEXT,
    stream_id TEXT,
    status TEXT,  -- 'starting', 'active', 'stopping', 'stopped'
    created_at INTEGER,
    updated_at INTEGER,
    ended_at INTEGER,
    error_message TEXT
);
```

### `viewer_sessions` Table

```sql
CREATE TABLE viewer_sessions (
    viewer_id TEXT PRIMARY KEY,
    stream_session_id TEXT,
    webrtc_endpoint_id TEXT,
    user_agent TEXT,
    ip_address TEXT,
    connected_at INTEGER,
    disconnected_at INTEGER,
    FOREIGN KEY (stream_session_id) REFERENCES stream_sessions(session_id)
);
```

## Troubleshooting

### Stream doesn't start

1. Check Kurento is running: `podman ps | grep kms-poc2`
2. Check API server logs: `tail -f logs/api_server.log`
3. Verify camera is online in dashboard
4. Check AWS IoT connectivity

### Viewer connection fails

1. **Firefox users**: Disable mDNS obfuscation (see POC2 docs)
   - `about:config` → `media.peerconnection.ice.obfuscate_host_addresses` → `false`
2. Check signaling server: `tail -f logs/signaling_server.log`
3. Verify STUN configuration
4. Check browser console for ICE candidates

### Camera disconnects after 30 seconds

- This should NOT happen if Kurento is properly configured
- Check `setMaxVideoRecvBandwidth` is being called
- Verify REMB packets in Kurento logs

## Testing

```bash
# Run unit tests
cd /Users/satinder/Documents/_camera_firmware/camera_project/livestreaming
python3 -m pytest tests/

# Test Kurento connectivity
python3 tests/test_kurento_connection.py

# Test stream lifecycle
python3 tests/test_stream_lifecycle.py
```

## Monitoring

### Check Active Streams
```bash
curl http://localhost:8080/api/stream/active | python3 -m json.tool
```

### View Stream Status
```bash
curl http://localhost:8080/api/stream/status/56C1CADCF1FA4C6CAEBA3E2FD85EFEBF
```

### Monitor Logs
```bash
tail -f logs/api_server.log
tail -f logs/signaling_server.log
tail -f logs/stream_manager.log
```

## Security Considerations

### Current (Local Network Only)

- No authentication required
- All communication over HTTP/WS (not HTTPS/WSS)
- Suitable for home network use

### Future (External Access)

The architecture includes hooks for:
- JWT authentication tokens
- HTTPS/WSS with TLS certificates
- Rate limiting per user/IP
- Session encryption

See `server/api_server.py` authentication middleware for implementation.

## Performance

### Expected Metrics

- Stream start time: <5 seconds
- Viewer connection time: <10 seconds
- Max concurrent viewers per stream: 10-20 (depends on bandwidth)
- CPU usage: ~5-10% per active stream (on modern hardware)

### Resource Usage

- Kurento: ~200MB RAM per stream
- API Server: ~50MB RAM
- Signaling Server: ~30MB RAM
- Bandwidth: ~1-2 Mbps per viewer

## References

- [POC2 Implementation Guide](/Users/satinder/camera_broker_project/poc2_bcgh_streaming/POC2_IMPLEMENTATION_GUIDE.md)
- [Kurento 6.16.0 Documentation](https://doc-kurento.readthedocs.io/en/6.16.0/)
- [WebRTC Standards](https://webrtc.org/)

## Support

For issues or questions:
1. Check POC2 documentation for detailed technical background
2. Review troubleshooting section above
3. Check server logs for error messages
4. Verify Kurento Media Server status

---

**Version**: 1.0.0
**Last Updated**: October 12, 2025
**Status**: Production Ready
