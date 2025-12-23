# Camera Livestream Viewer Setup

## Overview

The livestreaming system provides a browser-based WebRTC viewer for watching camera streams from anywhere. The architecture ensures remote viewing works through NAT/firewalls using ICE/STUN.

## Architecture

```
Camera (Local Network)
    |
    | Plain RTP (no encryption)
    v
Kurento RtpEndpoint (receives camera stream)
    |
    | Kurento internal connection
    v
Kurento WebRtcEndpoint (one per viewer)
    |
    | WebRTC with ICE/STUN (encrypted)
    v
Browser Viewer (anywhere on internet)
```

**Key Points:**
- Camera sends plain RTP to Kurento (local network only)
- Viewers use WebRTC with ICE for NAT traversal
- Each viewer gets their own WebRtcEndpoint
- STUN servers enable remote viewing through firewalls

## Quick Start (Local Network)

### 1. Start the Services

```bash
cd /Users/satinder/Documents/_camera_firmware/camera_project/livestreaming
export EXTERNAL_IP="192.168.199.173"
./start_all.sh
```

### 2. Start a Camera Stream

```bash
# Start stream for Camera 4
curl -X POST http://localhost:8080/streams/56C1CADCF1FA4C6CAEBA3E2FD85EFEBF/start
```

### 3. Open the Viewer in Browser

```
http://localhost:8080/viewer
```

Or specify a different camera:
```
http://localhost:8080/viewer?camera=CAMERA_ID_HERE
```

### 4. Click "Start Stream" in the UI

The viewer will:
1. Verify stream is active via API
2. Connect to signaling server (WebSocket)
3. Establish WebRTC peer connection
4. Display video

## Remote Access Setup

To view streams from outside your home network, you need to:

### 1. Configure Port Forwarding on Your Router

Forward these ports from your public IP to your server (192.168.199.173):

| Service | Port | Protocol | Destination |
|---------|------|----------|-------------|
| API Server | 8080 | TCP | 192.168.199.173:8080 |
| Signaling Server | 8765 | TCP | 192.168.199.173:8765 |
| Kurento WebRTC | 8888 | TCP | 192.168.199.173:8888 |

**Optional but Recommended:** Forward additional UDP ports for RTP media (improves performance):
- UDP ports 5000-5050 → 192.168.199.173:5000-5050

### 2. Access the Viewer Remotely

From any browser on the internet:

```
http://camera.pahwa.net:8080/viewer
```

Or using your public IP:
```
http://86.20.156.73:8080/viewer
```

**Note:** The viewer.js automatically detects the hostname and configures the correct URLs:
- Local: `http://localhost:8080` and `ws://localhost:8765`
- Remote: `http://camera.pahwa.net:8080` and `ws://camera.pahwa.net:8765`

### 3. Verify Remote Access

Test each component:

```bash
# 1. Test API (from remote machine)
curl http://camera.pahwa.net:8080/health

# 2. Test viewer page loads
curl -I http://camera.pahwa.net:8080/viewer

# 3. Open browser and navigate to viewer URL
```

## How WebRTC Remote Viewing Works

### ICE Candidate Discovery

When you open the viewer remotely, WebRTC performs ICE (Interactive Connectivity Establishment):

1. **STUN Phase**: Browser contacts Google STUN servers to discover its public IP
2. **Candidate Gathering**: Browser generates ICE candidates (possible network paths)
3. **Signaling**: Candidates exchanged via WebSocket signaling server
4. **Connection**: Best path selected (usually STUN-mapped UDP hole punch)

### NAT Traversal

```
Remote Browser (NAT)
    |
    | 1. STUN query to stun.l.google.com:19302
    |    Discovers: public IP = 203.0.113.45:54321
    v
[Internet]
    |
    | 2. ICE candidates exchanged via ws://camera.pahwa.net:8765
    |    Browser candidate: 203.0.113.45:54321 (srflx)
    |    Kurento candidate: 86.20.156.73:XXXXX (host)
    v
Kurento WebRtcEndpoint
    |
    | 3. RTP/RTCP media flows directly
    |    UDP: 203.0.113.45:54321 <-> 86.20.156.73:XXXXX
    v
RtpEndpoint <- Camera
```

### Why This Works Without TURN

- **Symmetric NAT Handling**: STUN servers help discover public IPs
- **UDP Hole Punching**: WebRTC establishes direct P2P connection
- **No TURN needed** (usually): Because Kurento has a public IP

## Troubleshooting

### Viewer Can't Connect (Remote)

**Symptom:** Viewer shows "Connection Failed" or ICE state stuck at "checking"

**Solutions:**

1. **Check port forwarding:**
   ```bash
   # From remote machine, test ports
   nc -zv camera.pahwa.net 8080  # API
   nc -zv camera.pahwa.net 8765  # WebSocket
   nc -zv camera.pahwa.net 8888  # Kurento
   ```

2. **Check firewall on server:**
   ```bash
   # On server, allow incoming connections
   sudo ufw allow 8080/tcp
   sudo ufw allow 8765/tcp
   sudo ufw allow 8888/tcp
   sudo ufw allow 5000:5050/udp  # Optional: RTP media
   ```

3. **Check browser console:**
   - Open Developer Tools (F12)
   - Look for WebSocket errors
   - Check ICE connection state changes

### Video Not Playing (ICE Connected)

**Symptom:** ICE shows "connected" but no video appears

**Solutions:**

1. **Verify stream is active:**
   ```bash
   curl http://localhost:8080/streams/CAMERA_ID
   ```

2. **Check Kurento logs:**
   ```bash
   podman logs -f kms-production | grep -i error
   ```

3. **Check camera is sending RTP:**
   - Look at keepalive stats in API response
   - Camera logs should show "start rtp"

### WebSocket Connection Fails

**Symptom:** "Failed to connect to signaling server"

**Solutions:**

1. **Verify signaling server is running:**
   ```bash
   netstat -an | grep 8765
   ```

2. **Check signaling server logs:**
   ```bash
   tail -f logs/livestreaming.log | grep signaling
   ```

3. **Test WebSocket manually:**
   ```bash
   # Install websocat if needed
   brew install websocat

   # Test connection
   websocat ws://localhost:8765
   ```

### Behind Corporate Firewall

If you're viewing from behind a corporate firewall that blocks UDP:

1. **Add TURN server** to viewer.js CONFIG:
   ```javascript
   stunServers: [
       { urls: 'stun:stun.l.google.com:19302' },
       { urls: 'turn:turn.server.com:3478',
         username: 'user',
         credential: 'pass' }
   ]
   ```

2. **Set up TURN server** (like coturn) on your server:
   ```bash
   # Install coturn
   sudo apt install coturn

   # Configure for public access
   # Edit /etc/turnserver.conf
   ```

## Browser Compatibility

**Tested and Working:**
- Chrome/Chromium (recommended)
- Firefox
- Edge (Chromium-based)
- Safari (macOS/iOS)

**Requirements:**
- WebRTC support (all modern browsers)
- JavaScript enabled
- Secure context (https:// or localhost)

**Note:** For production, use HTTPS with a valid SSL certificate. WebRTC features may be limited on http:// from remote hosts.

## API Endpoints

### Start Stream
```bash
POST /streams/{camera_id}/start
```

### Stop Stream
```bash
POST /streams/{camera_id}/stop
```

### Get Stream Info
```bash
GET /streams/{camera_id}
```

### List All Streams
```bash
GET /streams
```

### Health Check
```bash
GET /health
```

## Configuration

### viewer.js Configuration

The viewer auto-detects URLs, but you can override:

```javascript
// In static/viewer.js
const CONFIG = {
    cameraId: '56C1CADCF1FA4C6CAEBA3E2FD85EFEBF',
    apiUrl: 'http://camera.pahwa.net:8080',        // Override
    signalingUrl: 'ws://camera.pahwa.net:8765',    // Override
    stunServers: [
        { urls: 'stun:stun.l.google.com:19302' }
    ]
};
```

### Environment Variables

```bash
# Server configuration
export EXTERNAL_IP="192.168.199.173"     # Internal IP for camera
export API_SERVER_HOST="0.0.0.0"         # Bind to all interfaces
export API_SERVER_PORT="8080"
export SIGNALING_SERVER_PORT="8765"
export KURENTO_WS_URL="ws://localhost:8888/kurento"
```

## Security Considerations

### Current Setup (Development)

- HTTP (unencrypted) for API and viewer
- WebSocket (unencrypted) for signaling
- WebRTC media (DTLS encrypted)
- No authentication

### Production Recommendations

1. **Use HTTPS:**
   ```bash
   # Add SSL certificate
   export API_USE_SSL=true
   export SSL_CERT=/path/to/cert.pem
   export SSL_KEY=/path/to/key.pem
   ```

2. **Use WSS (Secure WebSocket):**
   ```bash
   export SIGNALING_USE_SSL=true
   ```

3. **Add Authentication:**
   - JWT tokens for API
   - WebSocket authentication
   - Camera ID validation

4. **Rate Limiting:**
   - Limit viewer connections per stream
   - Throttle API requests

## Performance Tuning

### Bandwidth Settings

Adjust camera stream bandwidth:

```bash
# Start with custom bandwidth
curl -X POST http://localhost:8080/streams/CAMERA_ID/start \
  -H "Content-Type: application/json" \
  -d '{"max_bandwidth": 3000, "min_bandwidth": 300}'
```

### Concurrent Viewers

Default: 10 viewers per stream

To change:
```python
# In main.py
signaling_server = SignalingServer(
    ...
    max_viewers_per_stream=20  # Increase limit
)
```

### Kurento Resources

Monitor Kurento resource usage:
```bash
podman stats kms-production
```

## Logs and Monitoring

### View Logs

```bash
# Main service logs
tail -f logs/livestreaming.log

# Kurento logs
podman logs -f kms-production

# Startup logs
tail -f logs/main.out
```

### Monitor Active Viewers

```bash
# List all viewers
curl http://localhost:8080/viewers | python3 -m json.tool

# List viewers for specific camera
curl http://localhost:8080/viewers/CAMERA_ID | python3 -m json.tool
```

### Health Monitoring

```bash
# Check system health
curl http://localhost:8080/health | python3 -m json.tool

# Expected output:
{
    "status": "healthy",
    "kurento_connected": true,
    "active_streams": 1,
    "total_viewers": 2
}
```

## Next Steps

1. **Test local viewing:** Verify viewer works on local network
2. **Configure port forwarding:** Enable remote access
3. **Test remote viewing:** Access from mobile/remote browser
4. **Add SSL certificates:** Secure for production
5. **Monitor performance:** Check bandwidth and viewer capacity

## Support

For issues:
1. Check logs: `logs/livestreaming.log`
2. Verify health: `curl http://localhost:8080/health`
3. Test Kurento: `podman logs kms-production`
4. Check browser console for WebRTC errors
