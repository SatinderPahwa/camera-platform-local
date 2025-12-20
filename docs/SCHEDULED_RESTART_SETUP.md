# Scheduled Restart and Health Monitoring Setup - EMQX Edition

## Overview
Automatic health monitoring and scheduled restarts configured to prevent connection leaks and ensure system reliability.

**Adapted from AWS IoT production server for EMQX MQTT broker.**

## Health Monitoring

### Health Check System
Proactive monitoring that checks all critical services every 12 minutes and restarts only when issues detected.

**Script:** `/home/satinder/camera-platform-local/tools/health_check_and_restart.sh`

**Schedule:** Every 12 minutes via cron
```bash
*/12 * * * * /home/satinder/camera-platform-local/tools/health_check_and_restart.sh
```

### What is Monitored:

1. **Config Server (Port 8443)** - 5-second timeout check
   - Tests: `https://192.168.199.218:8443/health`
   - Restarts ALL services if not responding

2. **Dashboard Server (Port 5000)** - 5-second timeout check
   - Tests: `http://localhost:5000`
   - Restarts ALL services if not responding

3. **CoTURN Server Ports** - Port listening check
   - Tests ports 3478 and 5349
   - Restarts ALL services if either port down

4. **Kurento Media Server** - Docker container + WebSocket check
   - Checks if `kms-production` Docker container running
   - Checks if WebSocket responding on port 8888 (426 status expected)
   - Restarts ALL services if either check fails

5. **EMQX Broker** - Port listening + status check
   - Tests port 8883 (MQTT over TLS)
   - Runs `sudo emqx ctl status` to verify broker is actually running
   - Restarts ALL services if not listening or not running

6. **CLOSE-WAIT Connection Leak** - Threshold: 5 connections
   - Monitors dashboard port 5000: `ss -tn | grep ":5000" | grep CLOSE-WAIT`
   - Monitors config server port 8443: `ss -tn | grep ":8443" | grep CLOSE-WAIT`
   - Restarts ALL services if leak detected on either port

### Log Location:
```bash
/home/satinder/camera-platform-local/logs/health_check.log
```

### View Health Check Logs:
```bash
tail -f /home/satinder/camera-platform-local/logs/health_check.log
```

## Scheduled Restarts

### Schedule
Servers restart automatically every 8 hours as backup to health checks:
- **8:00 AM** (08:00)
- **4:00 PM** (16:00)
- **12:00 AM** (00:00 / Midnight)

### Crontab Configuration
```bash
# Camera Platform - EMQX Edition - Automatic Server Restart Schedule
# Restarts every 8 hours: 8:00 AM, 4:00 PM, 12:00 AM

# At 8:00 AM
0 8 * * * /home/satinder/camera-platform-local/cron_restart_wrapper.sh >> /home/satinder/camera-platform-local/logs/cron_restart.log 2>&1

# At 4:00 PM (16:00)
0 16 * * * /home/satinder/camera-platform-local/cron_restart_wrapper.sh >> /home/satinder/camera-platform-local/logs/cron_restart.log 2>&1

# At 12:00 AM (midnight)
0 0 * * * /home/satinder/camera-platform-local/cron_restart_wrapper.sh >> /home/satinder/camera-platform-local/logs/cron_restart.log 2>&1

# Health check every 12 minutes
*/12 * * * * /home/satinder/camera-platform-local/tools/health_check_and_restart.sh
```

### Wrapper Script
The `cron_restart_wrapper.sh` script handles environment setup:

```bash
#!/bin/bash
# Enable lingering for user (allows user processes without active session)
loginctl enable-linger satinder 2>/dev/null || true

# Change to project directory and run restart
cd /home/satinder/camera-platform-local
exec /bin/bash ./scripts/managed_start.sh restart
```

**Note:** Simpler than AWS IoT version - no Podman environment variables needed since we use Docker.

### User Lingering
User lingering ensures services can run even when no user sessions are active:

```bash
loginctl enable-linger satinder
```

Verify lingering is enabled:
```bash
loginctl show-user satinder | grep Linger
# Should show: Linger=yes
```

## Automatic Startup on Boot

### Systemd User Service
A systemd user service ensures all camera services start automatically when the server boots.

**Service file:** `~/.config/systemd/user/camera-platform.service`

```ini
[Unit]
Description=Camera Platform Services - EMQX Edition (Dashboard, MQTT Processor, Config Server)
After=network.target emqx.service docker.service
Wants=emqx.service docker.service

[Service]
Type=forking
WorkingDirectory=/home/satinder/camera-platform-local
ExecStart=/bin/bash /home/satinder/camera-platform-local/scripts/managed_start.sh start
ExecStop=/bin/bash /home/satinder/camera-platform-local/scripts/managed_start.sh stop
RemainAfterExit=yes
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

**Key differences from AWS IoT version:**
- Depends on `emqx.service` and `docker.service` (instead of custom MQTT bridge and Podman)
- No Podman environment variables needed
- Simpler service definition

### Enable the Service:
```bash
# Create config directory
mkdir -p ~/.config/systemd/user

# Copy service file
cp /home/satinder/camera-platform-local/camera-platform.service \
   ~/.config/systemd/user/camera-platform.service

# Reload systemd
systemctl --user daemon-reload

# Enable service (auto-start on boot)
systemctl --user enable camera-platform.service

# Start service now
systemctl --user start camera-platform.service
```

### Check Service Status:
```bash
systemctl --user status camera-platform.service
```

**IMPORTANT:** User lingering must be enabled for the service to start on boot without an active user session.

## Sudo Configuration

Create `/etc/sudoers.d/camera-platform` to allow passwordless sudo for health checks and restarts:

```bash
# Allow satinder to manage camera platform without password
satinder ALL=(ALL) NOPASSWD: /bin/kill
satinder ALL=(ALL) NOPASSWD: /bin/sh -c *
satinder ALL=(ALL) NOPASSWD: /usr/bin/setsid
satinder ALL=(ALL) NOPASSWD: /usr/bin/emqx
satinder ALL=(ALL) NOPASSWD: /home/satinder/camera-platform-local/venv/bin/python3 /home/satinder/camera-platform-local/servers/enhanced_config_server.py
```

**To create this file:**
```bash
sudo visudo -f /etc/sudoers.d/camera-platform
# Paste the above content, save and exit
```

## Log Locations

**Scheduled Restart Log:**
```bash
/home/satinder/camera-platform-local/logs/cron_restart.log
```

**Health Check Log:**
```bash
/home/satinder/camera-platform-local/logs/health_check.log
```

**Service Logs:**
```bash
/home/satinder/camera-platform-local/logs/config_server.log
/home/satinder/camera-platform-local/logs/mqtt_processor.log
/home/satinder/camera-platform-local/logs/dashboard_server.log
```

## Manual Operations

### View Crontab
```bash
crontab -l
```

### Edit Schedule
```bash
crontab -e
```

### View Restart Logs
```bash
# Scheduled restarts
tail -f /home/satinder/camera-platform-local/logs/cron_restart.log

# Health checks
tail -f /home/satinder/camera-platform-local/logs/health_check.log
```

### Manual Restart (Same as Cron)
```bash
cd /home/satinder/camera-platform-local
./scripts/managed_start.sh restart
```

### Manual Health Check
```bash
cd /home/satinder/camera-platform-local
./tools/health_check_and_restart.sh
```

## Installation Instructions

Run these commands on your production server to set up health monitoring and auto-restart:

```bash
# 1. Enable user lingering
loginctl enable-linger satinder

# 2. Make scripts executable
chmod +x ~/camera-platform-local/tools/health_check_and_restart.sh
chmod +x ~/camera-platform-local/cron_restart_wrapper.sh

# 3. Set up systemd service
mkdir -p ~/.config/systemd/user
cp ~/camera-platform-local/camera-platform.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable camera-platform.service
systemctl --user start camera-platform.service

# 4. Configure sudo permissions
sudo visudo -f /etc/sudoers.d/camera-platform
# Add the sudo configuration from above

# 5. Set up cron jobs
crontab -e
# Add the cron entries from above

# 6. Test health check manually
./tools/health_check_and_restart.sh
tail -20 logs/health_check.log

# 7. Verify systemd service
systemctl --user status camera-platform.service

# 8. Verify cron jobs
crontab -l
```

## Why This Was Needed

### Root Cause: Connection Leak
Flask development server accumulates connections in CLOSE-WAIT state:
- Each connection holds resources (file descriptors, memory)
- Main server thread becomes blocked
- Server can't accept new connections

### Benefits of Health Monitoring:
- **Only restarts when needed** - Less disruption
- **Faster detection** - Issues caught within 12 minutes
- **Comprehensive coverage** - Monitors all critical services
- **Self-healing** - Automatically resolves issues
- **Complete restart** - Uses `managed_start.sh restart`

### Long-term Improvements Recommended:
1. Replace Flask dev server with production WSGI server (gunicorn/uWSGI)
2. Already using Nginx reverse proxy ✓
3. Add rate limiting and firewall rules
4. Implement connection timeouts and proper cleanup

## Verification

### Check if Cron Jobs are Active
```bash
# View crontab
crontab -l

# Check cron service status
systemctl status cron
```

### Check Last Restart Time
```bash
# Check restart log
tail -20 /home/satinder/camera-platform-local/logs/cron_restart.log

# Check process start time
ps -p $(cat /home/satinder/camera-platform-local/pids/dashboard_server.pid) -o lstart
```

### Check for Stuck Connections
```bash
# Count CLOSE-WAIT connections on dashboard port
ss -tn | grep ':5000' | grep -c 'CLOSE-WAIT'

# Count CLOSE-WAIT on config server port
ss -tn | grep ':8443' | grep -c 'CLOSE-WAIT'

# Should return 0 or very low number after restart
```

## Monitoring

To monitor server health between checks:
```bash
# Check connection states (dashboard)
watch -n 60 'ss -tn | grep ":5000" | grep CLOSE-WAIT | wc -l'

# Check connection states (config server)
watch -n 60 'ss -tn | grep ":8443" | grep CLOSE-WAIT | wc -l'

# Check server status
./scripts/managed_status.sh

# Check EMQX status
sudo emqx ctl status
sudo emqx ctl listeners

# Check ports
sudo ss -tlnp | grep -E ':(5000|8443|8883|3478|5349|8888)'
```

## Troubleshooting

### If Cron Restart Fails
1. Check cron log: `tail -50 logs/cron_restart.log`
2. Verify sudo permissions: `sudo -n emqx ctl status && echo "OK" || echo "FAIL"`
3. Test manual restart: `./scripts/managed_start.sh restart`
4. Check system logs: `journalctl -u cron --since "1 hour ago"`

### If Health Check Doesn't Restart Services
1. Check health check log: `tail -50 logs/health_check.log`
2. Run health check manually: `./tools/health_check_and_restart.sh`
3. Verify script permissions: `ls -l tools/health_check_and_restart.sh`
4. Check cron is running: `systemctl status cron`

### If Service Doesn't Start on Boot
1. Check lingering: `loginctl show-user satinder | grep Linger`
2. Check service status: `systemctl --user status camera-platform.service`
3. Check service logs: `journalctl --user -u camera-platform.service`
4. Verify EMQX started: `sudo systemctl status emqx`

## Differences from AWS IoT Version

| Feature | AWS IoT Version | EMQX Version |
|---------|----------------|--------------|
| **MQTT Broker** | Custom bridge to AWS IoT Core | EMQX on port 8883 |
| **Config Server Port** | 80 | 8443 |
| **Livestreaming** | Kurento via Podman | Kurento via Docker |
| **Podman Environment** | Required XDG_RUNTIME_DIR | Not needed (Docker) |
| **Systemd Dependencies** | network.target only | emqx.service + docker.service |
| **Health Checks** | MQTT port 1883 | EMQX port 8883 + status command |
| **Cron Wrapper** | Complex (Podman env) | Simple (no special env) |

## Setup Date
- **Documentation Created:** December 20, 2025
- **Server:** cameras.pahwa.net (satinder@camera1)
- **Adapted From:** camera-server production setup (December 2025)
