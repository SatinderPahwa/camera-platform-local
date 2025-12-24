# Troubleshooting Guide

Common issues and solutions for the VBC01 Camera Platform.

## Table of Contents

- [Platform Services](#platform-services)
- [EMQX Broker](#emqx-broker)
- [Camera Connection](#camera-connection)
- [Notifications](#notifications)
- [Dashboard](#dashboard)
- [Performance](#performance)
- [Logs and Debugging](#logs-and-debugging)

## Platform Services

### Services Won't Start

**Problem:** `./scripts/managed_start.sh start` fails

**Solutions:**

1. **Check Python installation:**
   ```bash
   python3 --version
   which python3
   ```

2. **Activate virtual environment:**
   ```bash
   source venv/bin/activate
   pip list  # Verify dependencies installed
   ```

3. **Check port conflicts:**
   ```bash
   # Config server (port 80)
   sudo lsof -i :80

   # Dashboard (port 5000)
   lsof -i :5000

   # EMQX (port 8883)
   sudo lsof -i :8883
   ```

4. **Check permissions:**
   ```bash
   # Config server needs sudo for port 80
   ls -l servers/enhanced_config_server.py
   chmod +x servers/*.py
   ```

5. **View startup errors:**
   ```bash
   tail -50 logs/config_server.log
   tail -50 logs/mqtt_processor.log
   tail -50 logs/dashboard_server.log
   ```

### Config Server Port 80 Permission Denied

**Problem:** Config server fails to bind to port 80

**Solution:**

```bash
# Option 1: Run with sudo (managed_start.sh does this automatically)
sudo python3 servers/enhanced_config_server.py

# Option 2: Use port 8080 instead (update .env)
CONFIG_SERVER_PORT=8080

# Option 3: Grant port binding capability (Linux)
sudo setcap 'cap_net_bind_service=+ep' /usr/bin/python3
```

**Note:** Cameras expect config server on port 80, so option 1 is recommended.

### Service Keeps Crashing

**Problem:** Service starts but immediately dies

**Diagnostic steps:**

1. **Check logs for Python errors:**
   ```bash
   tail -100 logs/<service_name>.log | grep -i error
   ```

2. **Verify database exists:**
   ```bash
   ls -lh data/camera_events.db
   # If missing, processor will create it on first run
   ```

3. **Test service manually:**
   ```bash
   cd servers/
   python3 enhanced_config_server.py
   # Watch for immediate errors
   ```

4. **Check dependencies:**
   ```bash
   pip install -r requirements.txt --upgrade
   ```

## EMQX Broker

### EMQX Won't Start

**Problem:** `sudo emqx start` fails or `emqx ctl status` shows not running

**Solutions:**

1. **Check if already running:**
   ```bash
   ps aux | grep emqx
   # If running, stop first: sudo emqx stop
   ```

2. **Check port conflicts:**
   ```bash
   sudo lsof -i :8883
   sudo lsof -i :18083
   ```

3. **Check EMQX logs:**
   ```bash
   sudo emqx ctl log tail
   # or
   tail -f /var/log/emqx/emqx.log
   ```

4. **Verify configuration:**
   ```bash
   sudo emqx check-config
   ```

5. **Reset EMQX data (last resort):**
   ```bash
   sudo emqx stop
   sudo rm -rf /var/lib/emqx/data/*
   sudo emqx start
   ```

### Certificate Verification Failed

**Problem:** EMQX logs show TLS handshake errors

**Check certificates:**

```bash
# Verify broker certificate
openssl x509 -in certificates/broker.crt -text -noout

# Check SAN (Subject Alternative Names)
openssl x509 -in certificates/broker.crt -noout -ext subjectAltName

# Should include both domain and IP:
# X509v3 Subject Alternative Name:
#     DNS:camera.example.com, IP Address:192.168.1.100
```

**Regenerate if needed:**

```bash
# Re-run setup wizard
python3 setup_platform.py

# Restart EMQX
sudo emqx stop
sudo emqx start
```

### Too Many Connections

**Problem:** EMQX refuses new connections

**Check connection limits:**

```bash
emqx ctl listeners
# Look for max_conns and current_conn

emqx ctl clients list
# See all connected clients
```

**Increase limits (edit EMQX config):**

```bash
sudo nano /etc/emqx/emqx.conf

# Find and modify:
listeners.ssl.default {
  max_connections = 512000  # Increase if needed
}

# Restart EMQX
sudo emqx restart
```

## Camera Connection

### Camera Not Connecting to Config Server

**Problem:** Camera doesn't request config or certificates

**Solutions:**

1. **Verify camera can reach config server:**
   ```bash
   # On camera (SSH/telnet)
   ping <server_ip>
   curl http://<server_ip>/hivecam/<camera_id>
   ```

2. **Check camera database config:**
   ```bash
   # On camera
   sqlite3 /cali/master_ctrl.db "SELECT * FROM app_info WHERE key='configSrvHost';"

   # Should return your server IP/domain
   # If wrong: UPDATE app_info SET value='<server_ip>' WHERE key='configSrvHost';
   ```

3. **Check config server logs:**
   ```bash
   tail -f logs/config_server.log
   # Should see request when camera boots
   ```

4. **Verify certificates exist:**
   ```bash
   ls -l certificates/
   # Should contain: ca.crt, broker.crt, camera_client.crt, camera_client.key
   ```

### Camera Gets Certificates But Won't Connect to EMQX

**Problem:** Config server logs show successful cert delivery, but no EMQX connection

**Solutions:**

1. **Check camera certificate deployment:**
   ```bash
   # On camera
   ls -l /root/certs/
   md5sum /root/certs/*

   # Compare with camera_files/<camera_id>/checksums.txt
   ```

2. **Verify CA certificate appended:**
   ```bash
   # On camera
   grep -c "BEGIN CERTIFICATE" /etc/ssl/certs/ca-bundle.trust.crt
   # Should be more than the default count

   # Re-append if needed:
   cat /root/certs/mqttCA.crt >> /etc/ssl/certs/ca-bundle.trust.crt
   ```

3. **Check EMQX logs for client connection attempts:**
   ```bash
   emqx ctl log tail | grep <camera_id>

   # Look for TLS errors, certificate verification failures
   ```

4. **Test EMQX TLS endpoint:**
   ```bash
   openssl s_client -connect <server_ip>:8883 -CAfile certificates/ca.crt -cert certificates/camera_client.crt -key certificates/camera_client.key
   ```

5. **Reboot camera:**
   ```bash
   # On camera
   reboot
   ```

### Camera Connects Briefly Then Disconnects

**Problem:** Camera appears in EMQX clients, then immediately disconnects

**Causes:**

1. **Duplicate client ID:** Another camera with same ID
   ```bash
   # Check EMQX clients
   emqx ctl clients list | grep <camera_id>

   # Should only be one instance
   ```

2. **MQTT protocol mismatch:** Check EMQX logs for protocol errors

3. **Keep-alive timeout:** Camera not sending heartbeats
   ```bash
   # Check processor logs for last heartbeat
   grep -i heartbeat logs/mqtt_processor.log
   ```

## Notifications

### No Telegram Notifications

**Problem:** Events detected but no Telegram messages

**Solutions:**

1. **Verify Telegram configuration:**
   ```bash
   cat .env | grep TELEGRAM

   # Check:
   # TELEGRAM_ENABLED=true
   # TELEGRAM_BOT_TOKEN=<valid_token>
   # TELEGRAM_CHAT_ID=<valid_chat_id>
   ```

2. **Test bot token:**
   ```bash
   curl https://api.telegram.org/bot<TOKEN>/getMe

   # Should return bot info:
   # {"ok":true,"result":{"id":...,"is_bot":true,...}}
   ```

3. **Test chat ID:**
   ```bash
   curl -X POST https://api.telegram.org/bot<TOKEN>/sendMessage \
     -d "chat_id=<CHAT_ID>&text=Test message"

   # Should receive message in Telegram
   ```

4. **Check notification settings:**
   ```bash
   # In .env
   TELEGRAM_NOTIFY_MOTION=true   # Enable motion notifications
   TELEGRAM_NOTIFY_PERSON=true   # Enable person detection
   TELEGRAM_NOTIFY_SOUND=false   # Disable sound alerts
   ```

5. **Check processor logs:**
   ```bash
   grep -i telegram logs/mqtt_processor.log

   # Look for errors like:
   # - "Telegram API error"
   # - "Invalid token"
   # - "Chat not found"
   ```

6. **Restart services:**
   ```bash
   ./scripts/managed_start.sh restart
   ```

### Thumbnails Not Appearing in Notifications

**Problem:** Telegram notifications arrive but no thumbnail image

**Solutions:**

1. **Check upload directory:**
   ```bash
   ls -l data/uploads/<camera_id>/
   # Should contain thumbnail ZIP files
   ```

2. **Check processor logs:**
   ```bash
   grep -i thumbnail logs/mqtt_processor.log

   # Look for:
   # "Thumbnail arrived during wait!"
   # or "No thumbnail after 4 seconds"
   ```

3. **Verify camera is uploading:**
   ```bash
   tail -f logs/config_server.log | grep -i thumbnail
   ```

4. **Check thumbnail wait time:**
   - Processor waits 4 seconds for thumbnail before sending notification
   - If network is slow, thumbnail may arrive late
   - Check `local_mqtt_processor.py` line ~249 for wait time

## Dashboard

### Dashboard Not Accessible

**Problem:** Cannot access `http://localhost:5000`

**Solutions:**

1. **Check service status:**
   ```bash
   ./scripts/managed_start.sh status
   # dashboard_server should be "Running"
   ```

2. **Check port binding:**
   ```bash
   lsof -i :5000
   # Should show python3 process
   ```

3. **Check logs:**
   ```bash
   tail -50 logs/dashboard_server.log
   ```

4. **Try different port:**
   ```bash
   # In .env
   DASHBOARD_SERVER_PORT=8080

   # Restart
   ./scripts/managed_start.sh restart
   ```

5. **Check firewall:**
   ```bash
   # Ubuntu/Debian
   sudo ufw status
   sudo ufw allow 5000

   # macOS
   # Check System Preferences → Security & Privacy → Firewall
   ```

### Cannot Login to Dashboard

**Problem:** Login page appears but credentials rejected

**Solutions:**

1. **Check credentials in .env:**
   ```bash
   cat .env | grep ADMIN

   # ADMIN_USERNAME=admin
   # ADMIN_PASSWORD=your_password
   ```

2. **Reset password:**
   ```bash
   # Edit .env
   nano .env

   # Change ADMIN_PASSWORD
   # Restart dashboard
   ./scripts/managed_start.sh restart
   ```

3. **Check Flask secret key:**
   ```bash
   # In .env, should have:
   FLASK_SECRET_KEY=<some_random_hex_string>

   # If missing, generate:
   python3 -c "import os; print(os.urandom(24).hex())"
   ```

### Dashboard Shows No Cameras

**Problem:** Dashboard loads but camera list is empty

**Check database:**

```bash
sqlite3 data/camera_events.db "SELECT * FROM camera_registry;"

# If empty, cameras haven't connected yet
# Check camera connection troubleshooting above
```

## Performance

### High CPU Usage

**Problem:** Services consuming excessive CPU

**Check:**

```bash
top -p $(cat pids/*.pid | tr '\n' ',' | sed 's/,$//')

# Identify which service is using CPU
```

**Solutions:**

1. **Reduce log level:**
   ```bash
   # In .env
   LOG_LEVEL=WARNING  # Instead of DEBUG or INFO
   ```

2. **Check for message loops:**
   ```bash
   # Watch MQTT traffic
   tail -f logs/mqtt_processor.log | head -100
   ```

3. **Reduce event polling:**
   - Check dashboard auto-refresh rate
   - Reduce browser tab count showing dashboard

### High Memory Usage

**Problem:** Services using too much RAM

**Check:**

```bash
ps aux | grep python3 | awk '{print $6, $11}'
# Shows memory (KB) and command
```

**Solutions:**

1. **Limit Flask debug mode:**
   ```bash
   # In .env
   DEBUG=false
   ENVIRONMENT=production
   ```

2. **Rotate logs:**
   ```bash
   # Archive old logs
   mkdir -p logs/archive
   mv logs/*.log.* logs/archive/
   ```

3. **Restart services periodically:**
   ```bash
   # Add to cron
   0 3 * * * cd /path/to/camera-platform-local && ./scripts/managed_start.sh restart
   ```

## Logs and Debugging

### Enable Debug Logging

```bash
# In .env
LOG_LEVEL=DEBUG
DEBUG=true

# Restart services
./scripts/managed_start.sh restart
```

### Monitor All Logs

```bash
# Watch all services
tail -f logs/*.log

# Watch specific service
tail -f logs/mqtt_processor.log

# Filter for errors
tail -f logs/*.log | grep -i error

# Follow camera events
tail -f logs/mqtt_processor.log | grep -i <camera_id>
```

### Clean Up Logs

```bash
# Archive old logs
mkdir -p logs/archive
mv logs/*.log logs/archive/

# Restart to create fresh logs
./scripts/managed_start.sh restart
```

### Test Individual Components

```bash
# Test EMQX connection
python3 tools/test_emqx.py

# Test config server manually
curl http://localhost/hivecam/<camera_id>

# Test dashboard manually
cd servers/
python3 dashboard_server.py
```

## Getting Help

If you've tried these solutions and still have issues:

1. **Collect diagnostic info:**
   ```bash
   # Service status
   ./scripts/managed_start.sh status > debug_info.txt

   # Logs (last 100 lines each)
   for log in logs/*.log; do
     echo "=== $log ===" >> debug_info.txt
     tail -100 "$log" >> debug_info.txt
   done

   # Configuration (redact sensitive info!)
   cat .env | grep -v TOKEN | grep -v PASSWORD >> debug_info.txt

   # EMQX status
   emqx ctl status >> debug_info.txt
   emqx ctl listeners >> debug_info.txt
   ```

2. **Open GitHub issue** with:
   - Platform version
   - Operating system
   - Diagnostic info (debug_info.txt)
   - Steps to reproduce

3. **Community support:**
   - Check existing issues on GitHub
   - Search documentation
   - Review commit history for recent fixes

## Livestreaming Issues

### WebSocket Connection Failed (External Access)

**Problem:** When accessing dashboard via HTTPS (e.g., `https://cameras.pahwa.net:5000`), livestreaming fails with:
```
❌ Error: WebSocket connection failed
❌ WebSocket error - Check port 8765 is accessible
🔌 Connecting to: wss://cameras.pahwa.net:8765
```

**Root Cause:** Browser security policy requires **WSS** (secure WebSocket) when page is loaded over HTTPS. The signaling server must have SSL certificates configured.

**Solution:**

1. **Configure SSL for signaling server:**
   ```bash
   # On production server
   cd ~/camera-platform-local
   ./scripts/configure_ssl_signaling.sh
   ```

2. **Verify .env has SSL configuration:**
   ```bash
   grep DASHBOARD_SSL .env
   # Should show:
   # DASHBOARD_SSL_ENABLED=true
   # DASHBOARD_SSL_CERT_FILE=/etc/letsencrypt/live/YOUR_DOMAIN/fullchain.pem
   # DASHBOARD_SSL_KEY_FILE=/etc/letsencrypt/live/YOUR_DOMAIN/privkey.pem
   ```

3. **Restart services:**
   ```bash
   ./scripts/managed_start.sh restart
   ```

4. **Verify WSS is enabled:**
   ```bash
   tail -f logs/livestreaming.log | grep -i ssl
   # Should show:
   # 🔒 Signaling server SSL enabled with certificate: /etc/letsencrypt/live/...
   # ✅ Signaling server running on wss://0.0.0.0:8765
   ```

**Port Forwarding Check:**

If WSS is enabled but connection still fails, verify port forwarding:
```bash
# From external network, test WebSocket port
nc -zv YOUR_DOMAIN 8765
# Should show: Connection succeeded
```

Add port forwarding rule in router:
- External port: 8765
- Internal IP: Your server IP
- Internal port: 8765
- Protocol: TCP

**Firewall Check:**
```bash
sudo ufw status | grep 8765
# Should show:
# 8765/tcp   ALLOW   Anywhere
```

If not allowed:
```bash
sudo ufw allow 8765/tcp
```

### Livestreaming Works Locally But Not Externally

**Problem:** Stream works on `http://localhost:5000` but fails on `https://cameras.pahwa.net:5000`

**Diagnosis:**
1. **Check browser console** (F12 → Console tab)
   - Look for WebSocket connection errors
   - Check if trying WS or WSS

2. **Verify SSL configuration:**
   ```bash
   # On server
   cat .env | grep -E "SSL|CERT"
   ```

3. **Check signaling server logs:**
   ```bash
   tail -f logs/livestreaming.log | grep -i "signaling\|ssl\|wss"
   ```

**Expected behavior:**
- Local: Uses `ws://localhost:8765` (plain WebSocket)
- External (HTTPS): Uses `wss://YOUR_DOMAIN:8765` (secure WebSocket)

### Certificate Permission Issues

**Problem:** Signaling server fails to start with:
```
Permission denied: '/etc/letsencrypt/live/YOUR_DOMAIN/privkey.pem'
```

**Solution:**

Option A: Run signaling server with elevated permissions (not recommended):
```bash
# Temporary workaround
sudo chmod 644 /etc/letsencrypt/live/YOUR_DOMAIN/privkey.pem
./scripts/managed_start.sh restart
```

Option B: Use Nginx reverse proxy (recommended for production):
```bash
# Nginx handles SSL, forwards to plain WS
# Update soon - see SERVER_REFERENCE.md
```

---

**Still stuck?** Open an issue on GitHub with detailed logs and we'll help troubleshoot!
