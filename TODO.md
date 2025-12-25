# TODO - Future Improvements

## High Priority

### 1. Fix REMB Loopback Trap

**Current Issue:**
- The camera starts streaming but times out after ~10 seconds because it doesn't receive RTCP feedback packets from the Kurento Media Server.
- `tcpdump` shows Kurento is sending the RTCP packets to its own loopback interface (`lo`) instead of to the camera's IP address over the physical network interface (`wlp2s0`).

**Problem Analysis:**
- This is a known issue with Kurento's `RtpEndpoint` when dealing with clients on the same subnet. It incorrectly identifies the camera as a "local" service.
- The `WebRtcEndpoint.conf.ini` (`externalIPv4`, `networkInterfaces`) and `ufw` settings appear correct. The issue lies in how the `RtpEndpoint`'s SDP is negotiated.

**Proposed Solution (based on Kurento documentation):**
- Modify `livestreaming/core/stream_manager.py` and `livestreaming/core/sdp_processor.py`.
- The initial SDP offer sent to Kurento must contain the server's real LAN IP, not `0.0.0.0`.
- The `build_custom_sdp_offer` function in `sdp_processor.py` should be modified to accept an IP address and use it in the `o=` and `c=` lines of the SDP.
- The `start_stream` method in `stream_manager.py` should be updated to pass the correct IP to this function.

**Status:** Not started. This is the next critical fix.

### 2. ✅ COMPLETED - Address SSL Private Key Permissions (Security Vulnerability)

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

### 4. Re-enable and Configure Firewall

**Current Issue:**
- The `ufw` firewall on the server was disabled as a temporary measure to diagnose the RTP/RTCP issue.
- Running without a host firewall is a security risk.

**Recommended Solution:**
- Once all services are confirmed to be working correctly, re-enable `ufw`.
- Methodically add back the `allow` rules one by one, testing the stream at each step to identify the specific rule or default policy that was interfering with RTCP traffic.
- The goal is to have a minimal but fully functional set of firewall rules.

**Status:** Not started. To be addressed after the REMB issue is fixed.

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