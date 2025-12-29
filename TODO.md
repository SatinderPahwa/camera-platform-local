# TODO - Future Improvements

## High Priority

### 1. ✅ COMPLETED - Fix Recording Deletion in Admin Dashboard (Feature Bug)

**Issue:**
- The delete old recordings functionality in the admin dashboard did not work
- Missing backend script: `tools/cleanup_old_recordings.py`

**Solution Implemented:**
- ✅ Copied proven working script from reference project
- ✅ Handles recordings and thumbnails
- ✅ Scans for orphaned files (not in database)
- ✅ Handles both files and directories
- ✅ Runs VACUUM to optimize database after deletion
- ✅ Proper statistics for dashboard parsing

**Status:** ✅ **COMPLETE** - Admin dashboard recording deletion now functional

### 2. ⚠️ PAUSED - Fix REMB Loopback Trap (RTCP Not Flowing)

**Current Issue:**
- Camera streams but doesn't receive RTCP/REMB feedback packets from Kurento Media Server
- `tcpdump` shows **zero** packets from Kurento to camera (all traffic is one-way: camera → server)
- Without REMB feedback, adaptive bitrate doesn't work (critical for external/cellular viewers)
- **System WAS working in October 2025** (camera logs showed bitrate updates every 5 seconds)
- Issue existed BEFORE Dec 26, 2025 - all fixes below were attempts to resolve pre-existing problem

**Current Branch:** `fix-rtcp-remb-config` (created Dec 29, 2025)
**Previous Branch:** `fix-rtcp-direction-sendrecv` (Dec 26, 2025 - all attempts failed)

**All Attempts Made (Dec 26, 2025 on fix-rtcp-direction-sendrecv) - None Resolved Issue:**

1. **Commit cef1cd1:** Changed direction from `recvonly` to `sendrecv` for RTCP flow
   - Result: ❌ No change

2. **Commit a0fa972:** Added explicit `a=rtcp:{port+1}` attributes in offer to Kurento
   - Result: ❌ No change

3. **Commit 74f5161:** Added bidirectional endpoint connection for REMB propagation
   - Result: ❌ No change

4. **Commit 0066f77:** Changed offer direction from `sendonly` to `sendrecv`
   - Result: ❌ No change

5. **Commit 7d478cf:** Added SDP offer/answer logging to diagnose RTCP issue
   - Result: ❌ Diagnostic only, no fix

6. **Commit 724cc96:** Matched original Hive SDP - keep `recvonly` and add `direction:passive`
   - Result: ❌ No change

7. **Commit bf89c89:** Corrected offer directions - audio `sendrecv`, video `sendonly`
   - Enhanced answer adds `a=direction:passive` for video
   - Result: ❌ No change

8. **Commit d9bd15f:** Changed SDP offer o= and c= lines from `EXTERNAL_IP` to `0.0.0.0`
   - Matches reference Hive AWS implementation (deharo-kcs-develop SessionDescription.java)
   - Result: ❌ No change

9. **Commit 90ab03c:** Documentation update confirming 0.0.0.0 fix didn't work

**Current SDP Configuration (after all attempts):**
```python
# Offer to Kurento:
o=- {random} {random} IN IP4 0.0.0.0
c=IN IP4 0.0.0.0
m=audio {port} RTP/AVPF 96 0
a=rtcp:{port+1}
a=sendrecv
m=video {port} RTP/AVPF 103
a=rtcp:{port+1}
a=sendonly
```

**Verification (Dec 26, 2025 19:35):**
```bash
# tcpdump showed 30 packets, ALL camera → server (192.168.199.124 → 192.168.199.218)
# ZERO packets from server → camera
# Expected: Bidirectional RTCP flow including REMB packets
```

**New Attempts (Dec 29, 2025 on fix-rtcp-remb-config) - Testing in Progress:**

10. **Branch `fix-rtcp-remb-config` created** - New approach targeting Kurento config instead of SDP
    - Created `BaseRtpEndpoint.conf.ini` with explicit REMB configuration
    - `rembLocalActivation=true` - Enable REMB packets to camera
    - `rembOnConnect=5000000` - 5 Mbps initial bitrate
    - `rembMinBitrate=500000` - 500 Kbps minimum
    - Updated `start_kurento.sh` to mount config file into Kurento container
    - **Issue:** Kurento entrypoint modifies config causing "Device or resource busy" on restart
    - **Workaround:** Clean `minPort`/`maxPort` from config before each restart
    - **Test Result (first test):** ❌ tcpdump showed only one-way traffic (camera → server), no RTCP back to camera
    - Created `rollback_remb_fix.sh` for quick rollback if needed

11. **Commit 7318bf6:** Added STUN/TURN configuration to BaseRtpEndpoint for RTCP routing
    - `networkInterfaces=all` - Explicit network interface configuration
    - `externalIPv4=192.168.199.173` - External IP for RTCP routing
    - `stunServerAddress=stun.l.google.com` - STUN server for NAT traversal
    - `stunServerPort=19302`
    - Matches WebRtcEndpoint STUN/TURN settings for consistency
    - **Status:** ⏳ Ready to test - services restarted, need to capture packets

**Environment Details:**
- **Server:** camera1 (192.168.199.173) - Mac
- **Camera:** 192.168.199.124 (corrected from 192.168.199.167)
- **Kurento:** 6.16.0 in Docker with `--network host`
- **Kurento Ports:** 5000-5050 (via `KMS_MIN_PORT`/`KMS_MAX_PORT` env vars)
- **Network:** Both on same subnet (192.168.199.x)
- **BaseRtpEndpoint.conf.ini:** NOW MOUNTED with REMB + STUN/TURN configuration

**Configuration Comparison:**
| Aspect | October 2025 (Working) | Dec 26 2025 (After Fixes) |
|--------|------------------------|---------------------------|
| SDP o=/c= | `IN IP4 {external_ip}` | `IN IP4 0.0.0.0` |
| Audio direction | `a=sendonly` | `a=sendrecv` |
| Video direction | `a=sendonly` | `a=sendonly` |
| Explicit a=rtcp: | Not present | Added for audio/video |
| Kurento ports | 5000-5050 | 5000-5050 (unchanged) |

**Open Questions:**
1. What changed between October 2025 (working) and when it stopped working?
2. Is the issue related to network topology (same subnet)?
3. Does Kurento RtpEndpoint have specific requirements for RTCP routing?
4. Could the issue be in Kurento/GStreamer configuration rather than SDP?

**Files Modified:**
- `livestreaming/core/sdp_processor.py` - Multiple SDP changes (see commits above)
- `livestreaming/core/stream_manager.py` - Bidirectional endpoint connections

**Status:** ⚠️ **PAUSED** - Multiple fix attempts based on reference implementation did not resolve issue. Need fresh approach to identify root cause. Issue pre-dates all Dec 26 changes.

### 3. ✅ COMPLETED - Address SSL Private Key Permissions (Security Vulnerability)

**Solution Implemented:** Group ownership with automated management

**What was done:**
- ✅ Created `scripts/setup_ssl_certificates.sh` automation script
- ✅ Created `ssl-certs` group with secure permissions
- ✅ Added user and turnserver to ssl-certs group
- ✅ Set directory permissions to 750, private key to 640
- ✅ Automated Certbot renewal hook preserves permissions
- ✅ Updated .env with SSL configuration
- ✅ No world-readable keys (secure by default)

**Affects:**
- Dashboard server (port 5000, HTTPS) - via Gunicorn
- WebSocket signaling server (port 8765, WSS) - via ssl-certs group

**Status:** ✅ **COMPLETE** - Fully automated, secure, repeatable

### 3. ✅ COMPLETED - Replace Flask Development Server with Production WSGI Server

**Solution Implemented:** Gunicorn with gevent workers and SSL support

**What was done:**
- ✅ Created `servers/wsgi.py` entry point
- ✅ Created `config/gunicorn_config.py` with production settings:
  - 9 workers: (2 × CPU cores) + 1, capped at 9
  - Gevent worker class for async I/O (streaming)
  - 120s timeout for large downloads
  - SSL via ssl-certs group ownership
  - Graceful shutdown (SIGTERM with 30s timeout)
  - Worker recycling (1000 requests per worker)
  - PID file tracking: `pids/gunicorn.pid`
- ✅ Updated `scripts/managed_start.sh` with `start_server_gunicorn()` function
- ✅ Updated stop logic for graceful Gunicorn shutdown
- ✅ Dashboard server updated with dev mode warnings

**Status:** ✅ **COMPLETE** - Running in production on camera1

### 5. ✅ COMPLETED - Re-enable and Configure Firewall

**Solution Implemented:** Automated firewall configuration script

**What was done:**
- ✅ Created `scripts/configure_firewall.sh` automation script
- ✅ Auto-detects local network for local-only rules
- ✅ Configures all 17 required firewall rules
- ✅ Public ports: SSH, dashboard, livestream API, WebSocket, MQTT, TURN, Kurento media
- ✅ Local-only ports: Config server (80), EMQX dashboard (8083/8084)
- ✅ Updated DEPLOYMENT_GUIDE.md with correct port list
- ✅ Fixed missing ports in documentation (8080 livestream API, 8765 WebSocket)

**Ports configured:**
- From anywhere: 22, 5000, 8080, 8765, 8883, 3478, 5349, 5000-5050/udp, 49152-65535/udp
- From local network only: 80, 8083, 8084

**Status:** ✅ **COMPLETE** - Firewall active and tested from local + external networks

### 6. ✅ COMPLETED - Fix Gunicorn MQTT Client ID Conflict

**Issue:**
- Dashboard MQTT commands failed with "MQTT client not connected"
- All 9 Gunicorn workers used same MQTT client ID "camera_dashboard"
- EMQX only allows ONE connection per client ID
- Only 1 worker had working MQTT connection (11% success rate)

**Solution Implemented:**
- ✅ Changed MQTT client ID to include worker PID: `camera_dashboard_worker_{PID}`
- ✅ Each of 9 workers now has unique MQTT connection
- ✅ Camera commands (reboot, mode change) work consistently
- ✅ Added Gunicorn post_worker_init hook for diagnostics

**Status:** ✅ **COMPLETE** - All workers connected, commands work from local + external

---

## Medium Priority

- **Add Rate Limiting:** Implement rate limiting (e.g., with Flask-Limiter) on API endpoints to prevent abuse.
- **Add Prometheus Metrics:** Add `prometheus_flask_exporter` to expose performance metrics for monitoring with Grafana.

---

## Low Priority

- **Add Automated Tests:** Create a test suite for API endpoints and core logic.
- ✅ **~~Implement Logging Rotation:~~** **COMPLETE** - `tools/cleanup_old_logs.sh` removes logs >15 days old, rotates large files, runs daily at 3 AM via cron
- **Improve Documentation:** Add a developer guide and more detailed API documentation.

---

## Recently Completed (Infrastructure Improvements)

### Production Hardening & Self-Healing
- ✅ Created `scripts/setup_production_hardening.sh` - Full automation
- ✅ Systemd service for auto-start on boot
- ✅ Health monitoring every 12 minutes with auto-restart
- ✅ Enhanced health checks now restart CoTURN, Kurento, EMQX, platform services
- ✅ Scheduled restarts every 8 hours (8 AM, 4 PM, Midnight)
- ✅ Automated log cleanup (daily at 3 AM, >15 days retention)
- ✅ Sudo rules for passwordless service management
- ✅ Complete self-healing for all infrastructure services

### Documentation
- ✅ Created `docs/AUTOMATED_DEPLOYMENT.md` - Comprehensive automation guide
- ✅ Updated `docs/DEPLOYMENT_GUIDE.md` - Replaced manual steps with automation