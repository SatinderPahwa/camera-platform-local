# External Streaming Fix - WebSocket SSL Configuration

**Date:** December 24, 2025
**Branch:** gemini-livestream-fixes-2
**Issue:** External streaming fails with WebSocket connection error when accessing via HTTPS

## Problem Summary

When accessing the dashboard via HTTPS (e.g., `https://cameras.pahwa.net:5000`), livestreaming fails with:

```
❌ Error: WebSocket connection failed
❌ WebSocket error - Check port 8765 is accessible
🔌 Connecting to: wss://cameras.pahwa.net:8765
```

### Root Cause

**Browser Security Policy:** Browsers require secure WebSocket (WSS) when a page is loaded over HTTPS. The signaling server was only configured for plain WebSocket (WS), causing connection failure.

## Changes Made

### 1. Added SSL Configuration to `config/settings.py`

Added environment variables for SSL certificate configuration:

```python
# SSL/TLS Configuration (for HTTPS Dashboard and WSS Signaling)
DASHBOARD_SSL_ENABLED = get_env('DASHBOARD_SSL_ENABLED', False, bool)
DASHBOARD_SSL_CERT_FILE = get_env('DASHBOARD_SSL_CERT_FILE', '')
DASHBOARD_SSL_KEY_FILE = get_env('DASHBOARD_SSL_KEY_FILE', '')
```

### 2. Created Deployment Script

**File:** `scripts/configure_ssl_signaling.sh`

Automated script that:
- Detects domain from existing .env
- Verifies Let's Encrypt certificates exist
- Updates .env with SSL configuration
- Provides deployment instructions

### 3. Updated Documentation

**File:** `docs/TROUBLESHOOTING.md`

Added comprehensive section on "Livestreaming Issues" covering:
- WebSocket connection failures
- SSL/WSS configuration
- Port forwarding requirements
- Certificate permission issues
- Diagnostic procedures

### 4. Updated TODO.md

Documented security issue:
- SSL private key permissions (affects both dashboard and signaling server)
- Port 80 constraint (config server needs it, can't use Nginx reverse proxy)
- Recommended solutions with group ownership approach

## How It Works

The existing code already has SSL support:

1. **Signaling Server** (`livestreaming/server/signaling_server.py:143-155`):
   - Checks for `DASHBOARD_SSL_CERT_FILE` and `DASHBOARD_SSL_KEY_FILE` env vars
   - If found and files exist → enables WSS with SSL context
   - If not found → runs plain WS

2. **Viewer JavaScript** (`templates/livestream_viewer.html:209-211`):
   - Auto-detects if page loaded via HTTPS
   - If HTTPS → uses WSS (`wss://`)
   - If HTTP → uses WS (`ws://`)

The fix simply provides the missing SSL certificate configuration.

## Deployment Instructions

### On Production Server (camera1)

1. **SSH to server:**
   ```bash
   ssh satinder@camera1
   cd ~/camera-platform-local
   ```

2. **Pull latest changes:**
   ```bash
   git fetch origin
   git checkout gemini-livestream-fixes-2
   git pull origin gemini-livestream-fixes-2
   ```

3. **Run SSL setup script (RECOMMENDED - implements secure group ownership):**
   ```bash
   sudo ./scripts/setup_ssl_certificates.sh
   ```

   This script implements the secure solution from TODO.md #2:
   - Creates `ssl-certs` group
   - Adds your user to the group
   - Sets secure permissions (640 for private keys, 644 for certs)
   - Creates Certbot renewal hook to maintain permissions
   - Updates .env with SSL configuration

4. **Activate group membership:**
   ```bash
   # Log out and back in (recommended)
   exit
   ssh satinder@camera1

   # OR use newgrp (temporary for current shell)
   newgrp ssl-certs
   ```

5. **Verify configuration:**
   ```bash
   # Check group membership
   groups
   # Should include: ssl-certs

   # Check .env
   grep DASHBOARD_SSL .env
   # Should show:
   # DASHBOARD_SSL_ENABLED=true
   # DASHBOARD_SSL_CERT_FILE=/etc/letsencrypt/live/cameras.pahwa.net/fullchain.pem
   # DASHBOARD_SSL_KEY_FILE=/etc/letsencrypt/live/cameras.pahwa.net/privkey.pem
   ```

6. **Restart services:**
   ```bash
   cd ~/camera-platform-local
   ./scripts/managed_start.sh restart
   ```

6. **Verify WSS is enabled:**
   ```bash
   tail -f logs/livestreaming.log | grep -i ssl
   ```

   Expected output:
   ```
   🔒 Signaling server SSL enabled with certificate: /etc/letsencrypt/live/cameras.pahwa.net/fullchain.pem
   ✅ Signaling server running on wss://0.0.0.0:8765
   ```

### Port Forwarding (If Not Already Done)

Add to your router:
- External port: **8765** (TCP)
- Internal IP: Your server IP
- Internal port: **8765**

### Firewall Rule

```bash
sudo ufw allow 8765/tcp
sudo ufw status | grep 8765
```

## Testing

1. **From external network**, open browser:
   ```
   https://cameras.pahwa.net:5000
   ```

2. **Navigate to livestream viewer:**
   - Click on camera
   - Click "View Live Stream" or go to `/livestream/viewer?camera=CAMERA_ID`

3. **Open browser console (F12):**
   - Check Debug section for connection status
   - Should show: `🔌 Connecting to: wss://cameras.pahwa.net:8765`
   - Stream should connect within 5-10 seconds

4. **Check logs on server:**
   ```bash
   tail -f logs/livestreaming.log
   ```

   Should show successful WebSocket connections.

## Troubleshooting

If connection still fails:

1. **Check signaling server is running with SSL:**
   ```bash
   ps aux | grep signaling
   grep "SSL enabled" logs/livestreaming.log
   ```

2. **Test port 8765 is accessible:**
   ```bash
   # From external network
   nc -zv cameras.pahwa.net 8765
   ```

3. **Check certificate permissions:**
   ```bash
   ls -l /etc/letsencrypt/live/cameras.pahwa.net/
   ```

4. **See full troubleshooting guide:**
   `docs/TROUBLESHOOTING.md` → "Livestreaming Issues" section

## Security Considerations

### Current Temporary Workaround

SSL private key may be set to world-readable (`chmod 644`) to allow non-root services to read it. This is a **security risk**.

### Long-Term Solution (Recommended)

Implement group-based permissions:

```bash
# Create ssl-certs group
sudo groupadd ssl-certs

# Add user to group
sudo usermod -a -G ssl-certs satinder

# Change ownership
sudo chown -R root:ssl-certs /etc/letsencrypt/live/
sudo chown -R root:ssl-certs /etc/letsencrypt/archive/

# Set permissions
sudo chmod 750 /etc/letsencrypt/live/
sudo chmod 750 /etc/letsencrypt/archive/
sudo chmod 640 /etc/letsencrypt/archive/*/privkey*.pem

# Handle Certbot renewals
sudo nano /etc/letsencrypt/renewal-hooks/post/fix-permissions.sh
```

Add this to post-renewal hook:
```bash
#!/bin/bash
chown -R root:ssl-certs /etc/letsencrypt/live/
chown -R root:ssl-certs /etc/letsencrypt/archive/
chmod 750 /etc/letsencrypt/live/
chmod 750 /etc/letsencrypt/archive/
chmod 640 /etc/letsencrypt/archive/*/privkey*.pem
```

See `TODO.md` item #2 for full details.

## Files Changed

- `config/settings.py` - Added SSL configuration variables
- `scripts/configure_ssl_signaling.sh` - New deployment script (executable)
- `docs/TROUBLESHOOTING.md` - Added livestreaming SSL/WSS troubleshooting section
- `TODO.md` - Documented security issue with port 80 constraint
- `EXTERNAL_STREAMING_FIX.md` - This document

## Comparison with Reference Implementation

The reference project (`/home/spahwa/camera-project` on camera-server) uses:
- `TLS_ENABLED`, `TLS_CERT_PATH`, `TLS_KEY_PATH` (different variable names)
- Same underlying SSL support in signaling server
- **Same security issue** with certificate permissions

Both projects need the group ownership solution for production security.

## Next Steps

1. Deploy fix to production server following instructions above
2. Test external streaming
3. Implement group-based certificate permissions (see TODO.md #2)
4. Merge branch to main after successful testing
5. Update reference implementation with same fix if needed

## Related Issues

- Browser security policy requires WSS for HTTPS pages
- Port 80 constraint prevents Nginx reverse proxy solution
- SSL private key permissions security issue (tracked in TODO.md)

---

**Branch:** gemini-livestream-fixes-2
**Status:** Ready for deployment testing
**Author:** Claude Code
**Date:** 2025-12-24
