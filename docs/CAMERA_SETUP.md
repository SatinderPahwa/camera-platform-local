# Camera Setup Guide

How to add VBC01 cameras to your EMQX platform.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Finding Camera ID](#finding-camera-id)
- [Generate Certificates](#generate-certificates)
- [Deploy to Camera](#deploy-to-camera)
- [Configure Camera Database](#configure-camera-database)
- [Verification](#verification)
- [Troubleshooting](#troubleshooting)

## Prerequisites

- ✅ Platform is running (`./scripts/managed_start.sh status`)
- ✅ EMQX broker is running (`emqx ctl status`)
- ✅ Camera is accessible on network (can ping camera IP)
- ✅ You have camera root password

## Finding Camera ID

Each VBC01 camera has a unique 32-character hexadecimal ID.

### Method 1: From Camera Database

If you have access to the camera's file system:

```bash
# SSH/Telnet to camera
telnet <camera_ip>  # or ssh root@<camera_ip>
# Login: root / <password>

# Read camera ID from database
sqlite3 /cali/master_ctrl.db "SELECT * FROM app_info WHERE key='uuid';"
```

The camera ID will be displayed (e.g., `67E48798E70345179A86980A7CAAAE73`).

### Method 2: From AWS IoT Console

If the camera was previously connected to AWS IoT:

1. Go to AWS IoT Console
2. Navigate to "Things"
3. Find your camera thing name: `vbc01-camera-<CAMERA_ID>`
4. The camera ID is the 32-character suffix

### Method 3: From EMQX Logs

If the camera tries to connect with wrong certificates:

```bash
# Check EMQX logs for connection attempts
emqx ctl log tail

# Look for client_id in connection attempts
```

## Generate Certificates

Use the `add_camera.py` tool to prepare certificates:

```bash
python3 tools/add_camera.py <CAMERA_ID>

# Example:
python3 tools/add_camera.py 67E48798E70345179A86980A7CAAAE73
```

This creates:

```
camera_files/<CAMERA_ID>/
├── mqttCA.crt        # CA certificate
├── mqtt.pem          # Client certificate + key (combined)
├── mqtt.key          # Client private key
└── checksums.txt     # MD5 checksums for verification
```

## Deploy to Camera

You need to copy certificates to the camera's `/root/certs/` directory.

### Method 1: FTP (Recommended)

```bash
# Navigate to camera certificate directory
cd camera_files/<CAMERA_ID>/

# Connect via FTP
ftp <camera_ip>
# Login: root / <password>

# Upload certificates
cd /root/certs
put mqttCA.crt
put mqtt.pem
put mqtt.key
quit

# Verify upload (via SSH/Telnet)
ssh root@<camera_ip>
ls -lh /root/certs/
md5sum /root/certs/*
```

Compare MD5 checksums with `checksums.txt` to ensure successful transfer.

### Method 2: SCP

```bash
cd camera_files/<CAMERA_ID>/

scp mqttCA.crt root@<camera_ip>:/root/certs/
scp mqtt.pem root@<camera_ip>:/root/certs/
scp mqtt.key root@<camera_ip>:/root/certs/
```

### Important Notes

- **Certificate location must be `/root/certs/`** - camera firmware expects this path
- **File names must match exactly:** `mqttCA.crt`, `mqtt.pem`, `mqtt.key`
- **Permissions:** Files should be readable by root (chmod 600)
- **Backup existing certificates** before replacing (if any)

## Configure Camera Database

The camera needs to know your config server address.

### Update Database

```bash
# SSH/Telnet to camera
ssh root@<camera_ip>

# Backup database
cp /cali/master_ctrl.db /cali/master_ctrl.db.backup

# Update config server URL
sqlite3 /cali/master_ctrl.db "UPDATE app_info SET value='<YOUR_SERVER_IP_OR_DOMAIN>' WHERE key='configSrvHost';"

# Verify change
sqlite3 /cali/master_ctrl.db "SELECT * FROM app_info WHERE key='configSrvHost';"
```

**Example:**
```sql
UPDATE app_info SET value='192.168.1.100' WHERE key='configSrvHost';
-- or
UPDATE app_info SET value='camera.example.com' WHERE key='configSrvHost';
```

### Append CA Certificate (One-time)

The camera needs to trust your self-signed CA certificate:

```bash
# On camera, append your CA cert to trusted bundle
cat /root/certs/mqttCA.crt >> /etc/ssl/certs/ca-bundle.trust.crt

# Verify it was appended
tail -20 /etc/ssl/certs/ca-bundle.trust.crt
```

## Reboot Camera

After deploying certificates and updating database:

```bash
# Reboot camera
reboot
```

Or use the dashboard reboot function once the camera is connected.

## Verification

### 1. Check Config Server Logs

The camera should request configuration from your config server:

```bash
tail -f logs/config_server.log
```

Expected:
```
Camera 67E48798E70345179A86980A7CAAAE73 requested config
Sending config response with EMQX broker: camera.example.com
Camera 67E48798E70345179A86980A7CAAAE73 requested certificates
Sending certificates...
```

### 2. Check EMQX Dashboard

Open EMQX dashboard: `http://localhost:18083`

- Navigate to "Clients"
- Look for client with ID matching your camera ID
- Status should be "Connected"

### 3. Check MQTT Processor Logs

The processor should receive connection events:

```bash
tail -f logs/mqtt_processor.log
```

Expected:
```
Connection event: Camera 67E48798 - connected
Firmware version: V0_0_00_117RC_svn1356
```

### 4. Check Platform Dashboard

Open dashboard: `http://localhost:5000`

- Camera should appear in camera list
- Status: "Online" or "Connected"
- Last seen: Recent timestamp

### 5. Test Camera Commands

From the dashboard:

1. Click on camera name
2. Try changing mode: ARMED → LIVESTREAMONLY → PRIVACY
3. Check processor logs for command delivery

## Camera Configuration

### Setting Camera Name

In the dashboard:

1. Click on camera
2. Edit name field
3. Save

Or via database:

```bash
sqlite3 data/camera_events.db "UPDATE camera_registry SET camera_name='Front Door Camera' WHERE camera_id='<CAMERA_ID>';"
```

### Camera Modes

- **ARMED:** Motion detection enabled, recordings enabled
- **LIVESTREAMONLY:** Only livestreaming, no motion detection
- **PRIVACY:** Camera disabled, no streaming or recording

### Telegram Notifications

Notifications are configured in `.env`:

```bash
TELEGRAM_NOTIFY_MOTION=true     # General motion detection
TELEGRAM_NOTIFY_PERSON=true     # Person detection (AI)
TELEGRAM_NOTIFY_SOUND=false     # Sound detection
```

Restart services after changing: `./scripts/managed_start.sh restart`

### RTSP Streaming

VBC01 cameras support RTSP streaming:

```
rtsp://<camera_ip>/stream0
```

View in VLC or any RTSP-compatible player:

```bash
vlc rtsp://192.168.1.101/stream0
```

## Troubleshooting

### Camera Not Connecting

**Check 1: Domain Resolution**
```bash
# On camera
ping <YOUR_DOMAIN>

# Should resolve to your server IP
```

**Check 2: Config Server Accessibility**
```bash
# On camera
curl http://<YOUR_SERVER_IP>/hivecam/<CAMERA_ID>

# Should return JSON config
```

**Check 3: Certificate Validity**
```bash
# On camera
ls -l /root/certs/
md5sum /root/certs/*

# Compare with checksums.txt
```

**Check 4: EMQX Logs**
```bash
emqx ctl log tail | grep <CAMERA_ID>

# Look for TLS handshake errors
```

### Camera Connects But No Events

**Check 1: Mode Setting**
- Ensure camera is in ARMED mode (not PRIVACY)

**Check 2: Motion Detection**
- Check camera settings in dashboard
- Verify motion zones configured

**Check 3: Processor Logs**
```bash
tail -f logs/mqtt_processor.log

# Should see activity events
```

### No Telegram Notifications

**Check 1: Token and Chat ID**
```bash
# Verify in .env
cat .env | grep TELEGRAM

# Test token
curl https://api.telegram.org/bot<TOKEN>/getMe
```

**Check 2: Processor Logs**
```bash
grep -i telegram logs/mqtt_processor.log

# Look for send errors
```

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for more solutions.

## Multiple Cameras

To add more cameras, repeat the process for each:

```bash
# Camera 1
python3 tools/add_camera.py <CAMERA_ID_1>
# Deploy, configure, reboot

# Camera 2
python3 tools/add_camera.py <CAMERA_ID_2>
# Deploy, configure, reboot

# Camera 3...
```

**Important:** All cameras use the **same certificates** (shared certificate model).

## Next Steps

- 📹 [Configure recording storage](TROUBLESHOOTING.md#storage)
- 🔔 [Customize notifications](TROUBLESHOOTING.md#notifications)
- 🌐 [Set up remote access](DEPLOYMENT.md#remote-access)
- 🛡️ [Security hardening](DEPLOYMENT.md#security)

---

**Need help?** Open an issue on GitHub with your logs and setup details.
