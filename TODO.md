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

### 2. ⚠️ IN PROGRESS - Fix REMB Loopback Trap (RTCP Not Flowing)

**Current Issue:**
- Camera streams but doesn't receive RTCP/REMB feedback packets from Kurento Media Server
- `tcpdump` shows **zero** packets from Kurento to camera (all traffic is one-way: camera → server)
- Without REMB feedback, adaptive bitrate doesn't work (critical for external/cellular viewers)

**Attempts Made:**

1. ✅ **SDP Direction Fix (commit bf89c89):**
   - Changed video offer to `a=sendonly` (was `a=sendrecv`)
   - Audio kept as `a=sendrecv` (bidirectional)
   - Enhanced answer adds `a=direction:passive` for video
   - Result: SDP now matches original working Hive implementation

2. ✅ **IP Address Fix (commit d9bd15f):**
   - Changed SDP offer o= and c= lines from `EXTERNAL_IP` to `0.0.0.0`
   - Matches reference Hive AWS implementation (deharo-kcs-develop SessionDescription.java)
   - Deployed to camera1 server via git pull on `fix-rtcp-direction-sendrecv` branch
   - Result: **No change** - Kurento still doesn't send RTCP packets

**Verification (Dec 26, 2025 19:35):**
```bash
# tcpdump showed 30 packets, ALL camera → server (192.168.199.124 → 192.168.199.218)
# ZERO packets from server → camera
# Expected: Bidirectional RTCP flow including REMB packets
```

**Root Cause Analysis:**
- SDP configuration is now **perfect** (matches working reference)
- Bandwidth settings configured correctly (5000 Kbps max, 500 Kbps min)
- Bidirectional endpoint connections in place
- **Problem persists despite matching reference implementation**

**Hypothesis:**
Network topology difference may be critical:
- **Reference (AWS):** Camera and server on different networks → Kurento sends RTCP over internet
- **Our setup:** Both on same subnet (192.168.199.x) → Kurento/GStreamer may handle routing differently
- Possible GStreamer-level same-subnet routing issue in RtpEndpoint

**Next Steps:**
1. Test with camera on different subnet (separate VLAN or external network)
2. Check Kurento RtpEndpoint documentation for same-subnet scenarios
3. Consider alternative: Use WebRTC end-to-end instead of RTP → WebRTC conversion
4. Investigate GStreamer RTP pipeline configuration for RTCP transmission

**Files Modified:**
- `livestreaming/core/sdp_processor.py:84,86` - Use 0.0.0.0 in SDP offer
- `livestreaming/core/sdp_processor.py:88,99` - Correct media directions
- `livestreaming/core/sdp_processor.py:174-198` - Add a=direction:passive

**Status:** ⚠️ **BLOCKED** - Attempted fix from reference implementation didn't resolve issue. Requires deeper investigation into network topology or Kurento/GStreamer behavior with same-subnet RTP.

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