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

### 2. Address SSL Private Key Permissions (Security Vulnerability)

**Current Issue:**
- To enable the dashboard server (running as a non-root user) to serve HTTPS, the permissions on the Let's Encrypt private key (`/etc/letsencrypt/live/your.domain/privkey.pem`) were loosened to be world-readable (`644`).
- **NEW:** The same issue applies to the WebSocket signaling server for WSS (secure WebSocket) support needed for external HTTPS access.
- This is a significant security risk, as any user on the server can read the private SSL key.

**Affects:**
- Dashboard server (port 5000, HTTPS)
- WebSocket signaling server (port 8765, WSS) - **ADDED**

**Constraint:**
- Config server runs on port 80 (cameras connect here) - **cannot use Nginx on port 80**
- Dashboard uses port 5000 with direct HTTPS
- Nginx reverse proxy not viable due to port 80 conflict

**Recommended Long-Term Solutions (choose one):**
- **A) Change Group Ownership** (RECOMMENDED given port 80 constraint): Change the group ownership of the `/etc/letsencrypt/archive/` and `/etc/letsencrypt/live/` directories to a specific group (e.g., `ssl-certs`), add the `satinder` user to that group, and set directory permissions to `750` and private key permissions to `640`. This is more secure than world-readable. Add automation to handle Certbot renewals.
- **B) Use Gunicorn with `sudo`**: Implement the Gunicorn WSGI server with sudo start + privilege drop. Gunicorn can be started with `sudo` to read the key, then drop privileges to run worker processes as non-root user.
- **C) Systemd with CapabilityBoundingSet**: Use systemd service files with `AmbientCapabilities=CAP_NET_BIND_SERVICE` and `ReadOnlyPaths=` to grant specific access to certificates without world-readable permissions.

**Status:** A temporary, insecure workaround (`chmod 644`) is in place. Solution A (group ownership) recommended.

**Security Issue Found in Reference Implementation:**
- The reference project (`camera-project`) has the same SSL private key permission issue
- This is a common limitation when running Python services as non-root users
- Both projects should implement solution A (group ownership) for production given the port 80 constraint

### 3. Replace Flask Development Server with a Production WSGI Server

**Current Issue:**
- The platform uses Flask's built-in development server, which is not suitable for production.
- It is single-threaded, inefficient, and can lead to connection leaks, necessitating scheduled restarts.

**Recommended Solution:**
- Replace the Flask development server with **Gunicorn**. (This directly ties into solving the security vulnerability above).

**Implementation Steps:**
1. Install Gunicorn: `pip install gunicorn`
2. Update `scripts/managed_start.sh` to launch the dashboard with Gunicorn:
   ```bash
   gunicorn -w 4 -b 0.0.0.0:5000 --timeout 120 --access-logfile logs/gunicorn_access.log --error-logfile logs/gunicorn_error.log servers.dashboard_server:app
   ```

**Status:** Not started. To be addressed after all streaming functionality is stable.

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
- **Implement Logging Rotation:** Configure `logrotate` for all custom log files to prevent them from growing indefinitely.
- **Improve Documentation:** Add a developer guide and more detailed API documentation.