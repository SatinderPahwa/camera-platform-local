# Architecture Documentation

System design and technical architecture of the VBC01 Camera Platform (EMQX Edition).

## Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Components](#components)
- [Data Flow](#data-flow)
- [Livestreaming Architecture](#livestreaming-architecture)
- [Certificate Model](#certificate-model)
- [MQTT Topics](#mqtt-topics)
- [Database Schema](#database-schema)
- [Security](#security)

## Overview

The VBC01 Camera Platform is a **fully offline-capable** camera management system that uses a local EMQX MQTT broker instead of AWS IoT Core. This design eliminates cloud dependencies while maintaining compatibility with VBC01 camera firmware (AWS IoT SDK v2.1.1).

### Key Design Principles

1. **Offline First:** Operates without internet connectivity
2. **No Cloud Dependencies:** No AWS account or cloud services required
3. **Shared Certificates:** Single set of certificates for all cameras (simplified management)
4. **Direct MQTT:** Cameras connect directly to local EMQX broker
5. **Local Processing:** All event processing and storage on local server

### Differences from AWS IoT Version

| Feature | AWS IoT Version | EMQX Version |
|---------|----------------|--------------|
| **MQTT Broker** | AWS IoT Core (cloud) | EMQX (local) |
| **Certificates** | Per-camera (AWS IoT Things) | Shared (all cameras use same cert) |
| **Topics** | AWS IoT topics + bridge | Direct EMQX topics |
| **Internet** | Required | Optional |
| **Setup** | AWS account + CLI | Domain + IP only |
| **Notifications** | Slack + Telegram | Telegram only |

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         VBC01 Cameras                            │
│  (AWS IoT SDK v2.1.1 - Compatible with EMQX 5.8.8)             │
└────────────┬────────────────────────────────────────────────────┘
             │
             │ HTTPS (Port 80)                  MQTT/TLS (Port 8883)
             │ Certificate + Config             Telemetry + Commands
             ↓                                           ↓
┌────────────────────────┐              ┌─────────────────────────┐
│   Config Server        │              │    EMQX Broker          │
│  (enhanced_config_     │              │   (Local MQTT)          │
│   server.py)           │              │   - TLS Listener        │
│  - Serves certs        │              │   - Client Auth         │
│  - Camera config       │              │   - Message Routing     │
│  - File uploads        │              └────────┬────────────────┘
└────────────────────────┘                       │
                                                 │ Subscribe
                                                 ↓
                                    ┌────────────────────────────┐
                                    │  MQTT Processor            │
                                    │  (local_mqtt_processor.py) │
                                    │  - Process events          │
                                    │  - Update database         │
                                    │  - Send notifications      │
                                    └────────┬───────────────────┘
                                             │
                                             ↓
                        ┌────────────────────────────────────────┐
                        │  SQLite Database                       │
                        │  - Camera registry                     │
                        │  - Activity events                     │
                        │  - Status history                      │
                        └────────┬───────────────────────────────┘
                                 │
                                 ↓
                    ┌────────────────────────────────────────────┐
                    │  Dashboard Server                          │
                    │  (dashboard_server.py)                     │
                    │  - Web UI (Flask)                          │
                    │  - Camera control                          │
                    │  - Event history                           │
                    │  - Recording playback                      │
                    └────────────────────────────────────────────┘
                                 ↑
                                 │ HTTPS (Port 5000)
                                 │
                         ┌───────────────┐
                         │  Web Browser  │
                         └───────────────┘
```

## Components

### 1. Config Server (`enhanced_config_server.py`)

**Purpose:** Provides certificates and configuration to cameras

**Functions:**
- Serves EMQX broker endpoint and port
- Delivers shared certificates (CA, client cert, client key)
- Receives file uploads (thumbnails, recordings)
- Extracts and stores uploaded ZIP files

**Endpoints:**
- `GET /hivecam/{camera_id}` - Returns MQTT broker config
- `GET /hivecam/cert/{camera_id}` - Returns PEM-encoded certificates
- `POST /hivecam/upload` - Receives file uploads from cameras

**Port:** 80 (requires sudo/root privileges)

**Certificate Format:**
```json
{
  "caCert": "-----BEGIN CERTIFICATE-----\n...",
  "clientCert": "-----BEGIN CERTIFICATE-----\n...",
  "clientKey": "-----BEGIN PRIVATE KEY-----\n..."
}
```

### 2. EMQX Broker

**Purpose:** Local MQTT message broker (replaces AWS IoT Core)

**Configuration:**
- **Listener:** `mqtts:ssl:default` on port 8883
- **TLS Version:** TLS 1.2+ (required by camera firmware)
- **Client Auth:** Mutual TLS (certificate-based)
- **Max Connections:** 512,000 (default)

**Compatibility:**
- EMQX 5.8.8+ is compatible with AWS IoT SDK v2.1.1
- Camera firmware connects without code changes
- Supports all AWS IoT SDK features used by cameras

**Management:**
```bash
sudo emqx start          # Start broker
emqx ctl status          # Check status
emqx ctl clients list    # List connected clients
emqx ctl listeners       # Show listeners
```

**Dashboard:** `http://localhost:18083` (admin/public)

### 3. MQTT Processor (`local_mqtt_processor.py`)

**Purpose:** Processes MQTT messages into database and triggers notifications

**Functions:**
- Subscribes to camera topics (activity, status, connection)
- Parses event messages (motion, person, sound)
- Updates SQLite database
- Sends Telegram notifications
- Restores camera state on reconnection

**Topics Subscribed:**
```python
'prod/device/message/hive-cam/+/activity/+'
'prod/device/connection/hive-cam/+'
'prod/device/status/hive-cam/+'
'prod/device/message/hive-cam/+/camera/state'
```

**Event Processing:**
1. **Activity Events:** Motion detection, person detection, sound alerts
2. **Connection Events:** Camera online/offline status
3. **Status Events:** Heartbeats, battery level, signal strength
4. **Disconnect Events:** Last will messages

**Notification Flow:**
- Activity start → Wait 4 seconds for thumbnail → Send Telegram notification
- Thumbnail arrives → Update notification with image
- Connection change → Send online/offline alert

### 4. Dashboard Server (`dashboard_server.py`)

**Purpose:** Web interface for camera management

**Functions:**
- Display camera status and events
- Control camera modes (ARMED/LIVESTREAMONLY/PRIVACY)
- View event history with thumbnails
- Playback encrypted recordings (HLS)
- Manage camera settings

**Authentication:**
- Flask-Login based authentication
- Bcrypt password hashing
- Optional Google OAuth

**API Endpoints:**
- `GET /api/cameras` - Camera status list
- `GET /api/events` - Recent activity events
- `POST /api/control/mode/{camera_id}/{mode}` - Change camera mode
- `POST /api/control/reboot/{camera_id}` - Reboot camera
- `GET /api/media/thumbnail/{event_id}` - Serve thumbnail image
- `GET /api/media/playlist/{event_id}.m3u8` - HLS playlist for recording

**MQTT Publishing:**
- Dashboard publishes commands directly to EMQX
- Topics: `prod/honeycomb/{camera_id}/system/setmode`, etc.

### 5. Database Manager (`database_manager.py`)

**Purpose:** SQLite database abstraction layer

**Functions:**
- Camera registry management
- Activity event storage
- Status event logging
- File upload tracking
- State management

**Tables:**
- `camera_registry` - Camera metadata and status
- `activity_events` - Motion/person detection events
- `status_events` - Heartbeats and connection events
- `file_uploads` - Thumbnail and recording uploads
- `camera_state` - Stored settings for restoration

### 6. Telegram Notifier (`telegram_notifier.py`)

**Purpose:** Send notifications to Telegram

**Functions:**
- Initial text notifications (motion detected)
- Thumbnail image notifications
- Connection status alerts (online/offline)

**Message Format:**
```
🎥 Motion Detected - Front Door Camera
⏰ 2025-01-15 14:30:45
📍 Event ID: abc123...

[Thumbnail Image]
```

## Data Flow

### Camera Connection Flow

```
1. Camera boots → Reads configSrvHost from database
2. Camera → Config Server: GET /hivecam/{camera_id}
3. Config Server → Camera: Returns EMQX broker endpoint
4. Camera → Config Server: GET /hivecam/cert/{camera_id}
5. Config Server → Camera: Returns certificates (CA, cert, key)
6. Camera → EMQX: TLS handshake with client certificate
7. EMQX → Camera: Connection accepted
8. Camera → EMQX: Publishes connection event
9. MQTT Processor receives event → Updates database
10. Telegram notification: "Camera Online"
```

### Motion Detection Flow

```
1. Camera detects motion → Publishes activity/start event
2. MQTT Processor receives event → Stores in database
3. Processor waits 4 seconds for thumbnail
4. Camera uploads thumbnail ZIP → Config server
5. Config server extracts thumbnail → Updates database
6. Processor sends Telegram notification with thumbnail
7. User receives notification with image
8. Motion stops → Camera publishes activity/stop event
9. Processor updates event duration in database
```

### Command Flow (Dashboard → Camera)

```
1. User clicks "ARMED" mode in dashboard
2. Dashboard → EMQX: Publishes setmode message
3. EMQX → Camera: Forwards message to subscribed topic
4. Camera receives command → Changes mode
5. Camera → EMQX: Publishes state update
6. MQTT Processor receives update → Updates database
7. Dashboard refreshes → Shows new mode
```

## Livestreaming Architecture

### Overview

The livestreaming system enables real-time video streaming from VBC01 cameras through a WebRTC-based architecture using Kurento Media Server. The system handles SDP (Session Description Protocol) negotiation, RTP/RTCP media transport, and adaptive bitrate control via REMB (Receiver Estimated Maximum Bitrate) feedback.

### Components

```
┌─────────────────┐         WebSocket          ┌──────────────────────┐
│  Web Browser    │◄──────────────────────────►│  Signaling Server    │
│  (WebRTC)       │         SDP Offer/Answer   │  (Port 8765 WSS)     │
└─────────────────┘                             └──────────┬───────────┘
        ↑                                                  │
        │ SRTP/SRTCP                                      │ Kurento API
        │ (via TURN)                                       │
        ↓                                                  ↓
┌─────────────────┐                             ┌──────────────────────┐
│  CoTURN Server  │◄────────────────────────────│  Kurento Media       │
│  (STUN/TURN)    │         RTP Relay           │  Server (KMS)        │
│  Port 3478/5349 │                             │  Docker Container    │
└─────────────────┘                             └──────────┬───────────┘
                                                           │
                                                           │ RTP/RTCP
                                                           │ REMB Feedback
                                                           ↓
                                                  ┌──────────────────────┐
                                                  │  VBC01 Camera        │
                                                  │  (192.168.199.x)     │
                                                  │  Ports 5000-5050     │
                                                  └──────────────────────┘
```

### Adaptive Bitrate Control (REMB)

**REMB (Receiver Estimated Maximum Bitrate)** is critical for streaming quality, especially for external/cellular viewers. Without REMB feedback, cameras cannot adjust their bitrate based on network conditions.

#### How REMB Works

1. **Camera** streams video at initial bitrate (e.g., 5 Mbps)
2. **Kurento** receives stream and estimates available bandwidth
3. **Kurento** sends RTCP REMB packets back to camera with recommended bitrate
4. **Camera** adjusts encoding bitrate (visible in camera logs every 5 seconds)
5. Loop continues - camera adapts to changing network conditions

#### REMB Fix (December 2025)

**Problem:** Camera was streaming but not receiving RTCP/REMB feedback from Kurento. `tcpdump` showed zero packets from Kurento → camera (all traffic was one-way: camera → server). Without REMB, adaptive bitrate didn't work.

**Root Cause:** Missing `a=direction:active` attribute in SDP offer to Kurento.

The VBC01 camera firmware (based on AWS implementation) validates that Kurento's answer contains `a=direction:passive`. This attribute pairing is required for REMB feedback:
- **Offer must contain:** `a=direction:active`
- **Answer must contain:** `a=direction:passive`

This handshake signals that both sides support bidirectional RTCP feedback.

**Solution Implemented:**

Modified `livestreaming/core/sdp_processor.py` to add `a=direction:active` to both audio and video media sections in the SDP offer:

```python
# Audio media section (line 94)
"a=sendrecv",           # Audio is bidirectional
"a=direction:active",   # CRITICAL for REMB: offer must be active

# Video media section (line 106)
"a=sendonly",           # Camera only sends video
"a=direction:active",   # CRITICAL for REMB: offer must be active
```

Added validation in `enhance_answer()` to verify Kurento responds correctly:

```python
if "a=direction:passive" not in sdp_answer:
    logger.warning("⚠️ Answer does NOT contain 'a=direction:passive' - REMB may not work!")
else:
    logger.info("✅ Answer contains 'a=direction:passive' - REMB should be supported")
```

**Result:** ✅ Camera now receives RTCP packets and adjusts bitrate dynamically. Verified in camera logs showing bitrate updates every 5 seconds. Adaptive bitrate working perfectly!

**Files Modified:**
- `livestreaming/core/sdp_processor.py` - Added `a=direction:active` to offer (lines 94, 106)
- `livestreaming/core/sdp_processor.py` - Added validation in `enhance_answer()` (lines 147-153)

**Verification:**
```bash
# Capture RTCP packets on server
sudo tcpdump -i any -n "host <camera_ip> and (udp portrange 5000-5050)" -v

# Expected: Bidirectional traffic including RTCP packets from server → camera

# Check camera logs for bitrate adjustments
# Should see: "bitrate updated to X bps" every ~5 seconds
```

### SDP Negotiation Flow

```
1. Browser → Signaling Server: Request stream
2. Signaling Server → Kurento: Create RtpEndpoint
3. Signaling Server → Camera (via MQTT): Start streaming
4. Camera → Signaling Server: WebSocket connection with camera details
5. Signaling Server builds custom SDP offer:
   - Fixed SSRCs for audio/video
   - Explicit RTCP ports (port+1)
   - Direction attributes (a=direction:active)
   - Camera's IP and RTP ports
6. Signaling Server → Kurento: processOffer(sdp)
7. Kurento → Signaling Server: SDP answer with:
   - Server IP and ports
   - Direction attributes (a=direction:passive)
   - REMB support confirmation
8. Signaling Server enhances answer:
   - Replaces Kurento's SSRCs with camera's fixed SSRCs
   - Adds Hive-specific x-skl attributes
   - Validates REMB support
9. Signaling Server → Camera: Enhanced SDP answer
10. Camera starts RTP stream to Kurento
11. Kurento starts RTCP/REMB feedback to camera
12. Media flows: Camera → Kurento → Browser (via TURN)
```

### Critical SDP Attributes

**In Offer (to Kurento):**
```
o=- {random} {random} IN IP4 0.0.0.0
c=IN IP4 0.0.0.0
m=audio {port} RTP/AVPF 96 0
a=rtcp:{port+1}                 # Explicit RTCP port
a=sendrecv                      # Bidirectional audio
a=direction:active              # Enable REMB feedback

m=video {port} RTP/AVPF 103
a=rtcp:{port+1}                 # Explicit RTCP port
a=rtcp-fb:103 goog-remb         # REMB support
a=sendonly                      # Unidirectional video
a=direction:active              # Enable REMB feedback
```

**In Answer (from Kurento):**
```
a=direction:passive             # REMB confirmation
a=recvonly                      # Kurento receives video
a=ssrc:{camera_ssrc}            # Fixed SSRC (replaced by enhance_answer)
```

### Port Configuration

**Camera Ports:** 5000-5050 (configured in camera database)
**Kurento Ports:** 5000-5050 (configured via `KMS_MIN_PORT`/`KMS_MAX_PORT` environment variables)
**TURN Ports:** 3478 (STUN), 5349 (TURNS), 49152-65535 (UDP relay)

### Kurento Media Server

**Version:** 6.16.0
**Network Mode:** `--network host` (Docker)
**Configuration:** BaseRtpEndpoint with REMB + STUN/TURN settings

**Key Settings:**
- `rembLocalActivation=true` - Enable REMB packets
- `rembOnConnect=5000000` - 5 Mbps initial bitrate
- `rembMinBitrate=500000` - 500 Kbps minimum
- `networkInterfaces=all` - All network interfaces
- `externalIPv4=<server_ip>` - External IP for RTCP routing

**Management:**
```bash
# Start Kurento container
./livestreaming/scripts/start_kurento.sh

# Check status
docker ps | grep kms-production

# View logs
docker logs kms-production --tail 100 -f
```

### Troubleshooting REMB Issues

**Symptom:** Camera streams but bitrate doesn't adjust

**Diagnosis:**
```bash
# 1. Capture RTCP packets
sudo tcpdump -i any -n "host <camera_ip> and (udp portrange 5000-5050)" -v

# 2. Check for bidirectional traffic
# Expected: Packets in BOTH directions (camera → server AND server → camera)

# 3. Check Kurento logs for REMB
docker logs kms-production | grep -i remb

# 4. Verify SDP contains direction attributes
# Check signaling server logs for:
# "✅ Answer contains 'a=direction:passive' - REMB should be supported"
```

**Common Issues:**

1. **Missing `a=direction:active` in offer** → No REMB feedback
   - Fix: Ensure sdp_processor.py includes direction attributes

2. **Kurento not configured for REMB** → No RTCP packets sent
   - Fix: Mount BaseRtpEndpoint.conf.ini with REMB settings

3. **Firewall blocking RTCP** → One-way traffic only
   - Fix: Allow UDP ports 5000-5050 in both directions

4. **Wrong Kurento endpoint** → Using WebRtcEndpoint instead of RtpEndpoint
   - Fix: Use RtpEndpoint for camera streams (WebRtcEndpoint is for browsers)

## Certificate Model

### Shared Certificate Architecture

Unlike AWS IoT (unique cert per Thing), this platform uses **shared certificates**:

- **One CA certificate** for all components
- **One broker certificate** for EMQX server
- **One client certificate** shared by all cameras

**Advantages:**
- ✅ Simple deployment (same files for all cameras)
- ✅ Easy certificate rotation (update once, deploy to all)
- ✅ No per-camera certificate generation
- ✅ Less storage required

**Identity:**
- Cameras identified by MQTT client ID (camera UUID)
- Certificate = authentication, client ID = identity

### Certificate Files

```
certificates/
├── ca.crt              # CA certificate (root of trust)
├── ca.key              # CA private key (keep secure!)
├── broker.crt          # EMQX broker certificate
├── broker.key          # EMQX broker private key
├── camera_client.crt   # Shared client certificate (all cameras)
└── camera_client.key   # Shared client private key (all cameras)
```

### Camera Certificate Deployment

Files on camera (`/root/certs/`):
```
mqttCA.crt    # Copy of ca.crt
mqtt.pem      # Combined camera_client.crt + camera_client.key
mqtt.key      # Copy of camera_client.key
```

## MQTT Topics

### Camera → Platform (Published by Cameras)

| Topic Pattern | Purpose | Example |
|--------------|---------|---------|
| `prod/device/connection/hive-cam/{UUID}` | Connection events | Camera online/offline |
| `prod/device/status/hive-cam/{UUID}` | Status heartbeats | Battery, signal, uptime |
| `prod/device/message/hive-cam/{UUID}/activity/start` | Motion detected | Activity event start |
| `prod/device/message/hive-cam/{UUID}/activity/stop` | Motion ended | Activity event end |
| `prod/device/message/hive-cam/{UUID}/camera/state` | State updates | Mode changes |

### Platform → Camera (Published by Dashboard)

| Topic Pattern | Purpose | Example |
|--------------|---------|---------|
| `prod/honeycomb/{UUID}/system/setmode` | Change mode | ARMED/LIVESTREAMONLY/PRIVACY |
| `prod/honeycomb/{UUID}/system/reboot` | Reboot camera | Restart command |
| `prod/honeycomb/{UUID}/settings/update` | Update settings | Detection sensitivity, etc. |

### Message Format

**Activity Event (Motion Detection):**
```json
{
  "eventId": "evt_abc123...",
  "activityType": "MOTION",
  "timestamp": 1705329045,
  "confidence": 0.85,
  "region": {...}
}
```

**Connection Event:**
```json
{
  "status": "connected",
  "timestamp": 1705329045,
  "device": {
    "softwareVersion": "V0_0_00_117RC_svn1356",
    "hardwareVersion": "VBC01",
    "serialNumber": "SN123456"
  },
  "ipAddress": "192.168.1.101"
}
```

**Mode Command:**
```json
{
  "requestId": "req_xyz789...",
  "creationTimestamp": "2025-01-15T14:30:45Z",
  "sourceId": "67E48798E70345179A86980A7CAAAE73",
  "sourceType": "hive-cam",
  "mode": "ARMED"
}
```

## Database Schema

### camera_registry

Tracks all known cameras and their current status.

```sql
CREATE TABLE camera_registry (
    camera_id TEXT PRIMARY KEY,
    camera_name TEXT,
    ip_address TEXT,
    firmware_version TEXT,
    status TEXT,                  -- Camera mode (armed/livestreamonly/privacy)
    connection_status TEXT,       -- Connection state (connected/disconnected)
    last_seen INTEGER,            -- Unix timestamp
    created_at INTEGER,
    updated_at INTEGER
);
```

### activity_events

Records motion detection, person detection, and sound alerts.

```sql
CREATE TABLE activity_events (
    event_id TEXT PRIMARY KEY,
    camera_id TEXT,
    camera_name TEXT,
    activity_type TEXT,           -- MOTION/MOTION_SMART/AUDIO_ALL
    start_timestamp INTEGER,
    end_timestamp INTEGER,
    duration_seconds INTEGER,
    confidence REAL,
    thumbnail_path TEXT,
    recording_path TEXT,
    recording_filename TEXT,
    recording_size INTEGER,
    upload_status TEXT,
    telegram_msg_id INTEGER,
    telegram_notified INTEGER,    -- Boolean (0/1)
    created_at INTEGER
);
```

### status_events

Logs heartbeats, connection events, and camera status updates.

```sql
CREATE TABLE status_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id TEXT,
    event_type TEXT,              -- connection/status/heartbeat/disconnect
    status TEXT,
    timestamp INTEGER,
    camera_name TEXT,
    client_id TEXT,
    ip_address TEXT,
    firmware_version TEXT,
    battery_level INTEGER,
    temperature REAL,
    uptime INTEGER,
    raw_payload TEXT,             -- Full JSON for debugging
    created_at INTEGER
);
```

### camera_state

Stores camera settings for restoration after reconnection.

```sql
CREATE TABLE camera_state (
    camera_id TEXT,
    setting_name TEXT,            -- mode/detection_sensitivity/etc.
    setting_value TEXT,
    last_updated INTEGER,
    PRIMARY KEY (camera_id, setting_name)
);
```

## Security

### TLS/SSL

- **Config Server:** HTTPS with self-signed certificate
- **EMQX Broker:** MQTTS (MQTT over TLS) on port 8883
- **Mutual TLS:** Both server and client authenticate with certificates

### Certificate Security

- **CA private key:** Keep secure! Used to sign all certificates
- **Client certificate:** Shared but acceptable (client ID provides identity)
- **4096-bit RSA keys:** Strong encryption
- **10-year validity:** Balance between security and convenience

### Authentication

- **Dashboard:** Flask-Login with bcrypt password hashing
- **MQTT:** Certificate-based (no username/password)
- **Config Server:** No auth (cameras must know UUID to request config)

### Best Practices

1. **Change default passwords:**
   ```bash
   # Dashboard (in .env)
   ADMIN_PASSWORD=<strong_password>

   # EMQX dashboard
   emqx ctl admins passwd admin <new_password>
   ```

2. **Restrict network access:**
   ```bash
   # Firewall rules
   sudo ufw allow from 192.168.1.0/24 to any port 80
   sudo ufw allow from 192.168.1.0/24 to any port 8883
   ```

3. **Secure CA private key:**
   ```bash
   chmod 600 certificates/ca.key
   # Consider encrypting or moving to secure storage
   ```

4. **Regular certificate rotation:**
   - Regenerate certificates annually
   - Deploy new certs to all cameras
   - Restart EMQX and services

5. **Monitor logs for suspicious activity:**
   ```bash
   # Check for unknown client IDs
   emqx ctl clients list

   # Monitor connection attempts
   tail -f logs/mqtt_processor.log | grep -i connection
   ```

## Scaling and Performance

### Single Server Limits

- **Cameras:** Up to 100 cameras (tested)
- **Events:** Millions of events in SQLite
- **EMQX:** 512,000 concurrent connections (default)
- **Storage:** Limited by disk space

### Optimization Tips

1. **Database maintenance:**
   ```bash
   # Vacuum database monthly
   sqlite3 data/camera_events.db "VACUUM;"

   # Archive old events
   sqlite3 data/camera_events.db "DELETE FROM activity_events WHERE start_timestamp < $(date -d '90 days ago' +%s);"
   ```

2. **Log rotation:**
   ```bash
   # Add to cron
   0 0 * * * find /path/to/logs -name "*.log" -mtime +7 -exec gzip {} \;
   ```

3. **Recording cleanup:**
   ```bash
   # Delete recordings older than 30 days
   find data/uploads -type f -name "*.zip" -mtime +30 -delete
   ```

## Deployment Considerations

### Production Checklist

- [ ] Change all default passwords
- [ ] Configure firewall rules
- [ ] Set up log rotation
- [ ] Enable HTTPS for dashboard (nginx reverse proxy)
- [ ] Configure automatic backups
- [ ] Set up monitoring/alerts
- [ ] Document recovery procedures
- [ ] Test camera failover

### High Availability

For critical deployments:
- Run EMQX in cluster mode
- Use PostgreSQL instead of SQLite
- Deploy multiple processor instances
- Add load balancer for dashboard

### Backup Strategy

```bash
# Daily backup script
#!/bin/bash
BACKUP_DIR=/backups/camera-platform/$(date +%Y%m%d)
mkdir -p $BACKUP_DIR

# Database
cp data/camera_events.db $BACKUP_DIR/

# Certificates
tar czf $BACKUP_DIR/certificates.tar.gz certificates/

# Configuration
cp .env $BACKUP_DIR/

# EMQX config
cp /etc/emqx/emqx.conf $BACKUP_DIR/

# Compress everything
tar czf $BACKUP_DIR.tar.gz $BACKUP_DIR/
rm -rf $BACKUP_DIR
```

---

**Architecture Version:** 1.0 (EMQX Edition)
**Last Updated:** January 2025
