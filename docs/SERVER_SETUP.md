# Server Setup Guide

Complete Ubuntu server setup for VBC01 Camera Platform with livestreaming support.

## Table of Contents

- [Overview](#overview)
- [Server Requirements](#server-requirements)
- [Initial Server Setup](#initial-server-setup)
- [Install EMQX Broker](#install-emqx-broker)
- [Install Kurento Media Server](#install-kurento-media-server)
- [Install TURN Server (coturn)](#install-turn-server-coturn)
- [Install Nginx](#install-nginx)
- [SSL Certificates](#ssl-certificates)
- [Firewall Configuration](#firewall-configuration)
- [System Services](#system-services)
- [Verification](#verification)

## Overview

This guide covers setting up a **production-ready Ubuntu server** for the camera platform with:

- ✅ **EMQX 5.8.8** - MQTT broker for camera connections
- ✅ **Kurento Media Server 7.0.1** - WebRTC media server for livestreaming
- ✅ **coturn** - TURN/STUN server for NAT traversal (REQUIRED for remote access)
- ✅ **Nginx** - Reverse proxy and static file serving
- ✅ **SSL/TLS** - Secure connections with Let's Encrypt

**Important:** TURN server is **REQUIRED**, not optional. Without it, livestreaming only works on local network.

## Server Requirements

### Hardware
- **CPU:** 4 cores minimum (8 cores recommended for multiple cameras)
- **RAM:** 4GB minimum (8GB recommended)
- **Disk:** 50GB minimum (SSD recommended)
- **Network:** 100Mbps minimum, 1Gbps recommended

### Operating System
- **Ubuntu Server 22.04 LTS** (recommended)
- **Ubuntu Server 24.04 LTS** (also supported)

### Network
- **Static IP address**
- **Domain name** pointing to server
- **Open ports:** 80, 443, 5000, 8883, 18083, 3478, 5349, 8888, 50000-60000

## Initial Server Setup

### 1. Update System

```bash
# Update package lists
sudo apt update

# Upgrade all packages
sudo apt upgrade -y

# Install essential tools
sudo apt install -y curl wget git vim build-essential software-properties-common
```

### 2. Create User and Configure SSH

```bash
# Create deployment user (if not already done)
sudo adduser deploy
sudo usermod -aG sudo deploy

# Configure SSH key authentication (recommended)
# On your local machine:
ssh-copy-id deploy@your-server-ip

# On server, disable password authentication (optional but recommended)
sudo nano /etc/ssh/sshd_config
# Set: PasswordAuthentication no
sudo systemctl restart sshd
```

### 3. Set Hostname and Timezone

```bash
# Set hostname
sudo hostnamectl set-hostname camera-server

# Set timezone
sudo timedatectl set-timezone America/New_York  # Adjust to your timezone
```

## Install EMQX Broker

### Version: EMQX 5.8.8 (Open Source)

```bash
# Add EMQX repository
curl -s https://assets.emqx.com/scripts/install-emqx-deb.sh | sudo bash

# Install EMQX
sudo apt install -y emqx=5.8.8

# Hold version to prevent automatic updates
sudo apt-mark hold emqx

# Enable and start EMQX
sudo systemctl enable emqx
sudo systemctl start emqx

# Verify installation
emqx --version
# Should show: 5.8.8

# Check status
sudo systemctl status emqx
emqx ctl status
```

### Configure EMQX

```bash
# Edit EMQX configuration
sudo nano /etc/emqx/emqx.conf

# Key settings to configure:
# listeners.ssl.default {
#   bind = "0.0.0.0:8883"
#   max_connections = 512000
#   ssl_options {
#     cacertfile = "/path/to/certificates/ca.crt"
#     certfile = "/path/to/certificates/broker.crt"
#     keyfile = "/path/to/certificates/broker.key"
#     verify = verify_peer
#     fail_if_no_peer_cert = true
#   }
# }

# The setup_platform.py wizard will generate the correct config
# Copy it to EMQX:
sudo cp deployment/emqx.conf /etc/emqx/emqx.conf

# Restart EMQX
sudo systemctl restart emqx
```

### Secure EMQX Dashboard

```bash
# Change default password (admin/public)
emqx ctl admins passwd admin <new_strong_password>

# Edit dashboard config for HTTPS (optional)
sudo nano /etc/emqx/emqx.conf

# dashboard {
#   listeners.https {
#     bind = 18084
#     ssl_options {
#       certfile = "/etc/ssl/certs/server.crt"
#       keyfile = "/etc/ssl/private/server.key"
#     }
#   }
# }
```

## Install Kurento Media Server

### Version: Kurento 7.0.1 (Latest stable)

**Important:** Kurento is required for WebRTC livestreaming from cameras.

```bash
# Install dependencies
sudo apt install -y gnupg

# Add Kurento repository key
sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 5AFA7A83

# Add Kurento repository
sudo tee /etc/apt/sources.list.d/kurento.list <<EOF
# Kurento Media Server - Release packages
deb [arch=amd64] http://ubuntu.openvidu.io/7.0.1 jammy kms7
EOF

# Update and install
sudo apt update
sudo apt install -y kurento-media-server=7.0.1

# Hold version
sudo apt-mark hold kurento-media-server

# Enable and start Kurento
sudo systemctl enable kurento-media-server
sudo systemctl start kurento-media-server

# Verify installation
dpkg -l | grep kurento
# Should show version 7.0.1
```

### Configure Kurento

```bash
# Configure Kurento for TURN/STUN
sudo nano /etc/kurento/modules/kurento/WebRtcEndpoint.conf.ini

# Add TURN server configuration:
# stunServerAddress=<your-domain>
# stunServerPort=3478
# turnURL=<username>:<password>@<your-domain>:3478

# Configure logging (optional)
sudo nano /etc/kurento/kurento.conf.json

# Restart Kurento
sudo systemctl restart kurento-media-server

# Check logs
sudo journalctl -u kurento-media-server -f
```

## Install TURN Server (coturn)

### Version: coturn (latest from Ubuntu repo)

**CRITICAL:** TURN server is REQUIRED for livestreaming from outside your home network.

```bash
# Install coturn
sudo apt install -y coturn

# Enable coturn
sudo nano /etc/default/coturn
# Uncomment: TURNSERVER_ENABLED=1

# Configure coturn
sudo nano /etc/turnserver.conf
```

### coturn Configuration

Replace the contents with:

```ini
# TURN server name (your domain)
realm=camera.example.com
server-name=camera.example.com

# Listening interfaces
listening-ip=0.0.0.0
listening-port=3478
tls-listening-port=5349

# External IP (your public IP)
external-ip=YOUR.PUBLIC.IP.ADDRESS/YOUR.LOCAL.IP.ADDRESS
# Example: external-ip=203.0.113.10/192.168.1.100

# Relay IP (usually same as listening IP)
relay-ip=192.168.1.100

# Port range for relay
min-port=50000
max-port=60000

# Authentication
# Use long-term credentials
lt-cred-mech

# User credentials (generate strong password)
user=turnuser:STRONG_PASSWORD_HERE

# SSL certificates (required for TURNS)
cert=/etc/letsencrypt/live/camera.example.com/fullchain.pem
pkey=/etc/letsencrypt/live/camera.example.com/privkey.pem

# Logging
verbose
log-file=/var/log/turnserver.log

# Security
fingerprint
no-multicast-peers
no-cli

# Performance
max-bps=3000000
bps-capacity=0
```

### Start and Enable coturn

```bash
# Start coturn
sudo systemctl enable coturn
sudo systemctl start coturn

# Check status
sudo systemctl status coturn

# View logs
sudo tail -f /var/log/turnserver.log
```

### Test TURN Server

Use an online TURN/STUN tester:
- https://webrtc.github.io/samples/src/content/peerconnection/trickle-ice/

Enter:
- **STUN URI:** `stun:camera.example.com:3478`
- **TURN URI:** `turn:camera.example.com:3478`
- **Username:** `turnuser`
- **Password:** `STRONG_PASSWORD_HERE`

You should see successful relay candidates.

## Install Nginx

### For Reverse Proxy and Static Files

```bash
# Install Nginx
sudo apt install -y nginx

# Create site configuration
sudo nano /etc/nginx/sites-available/camera-platform
```

### Nginx Configuration

```nginx
# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name camera.example.com;

    # Allow Let's Encrypt challenges
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    # Redirect everything else to HTTPS
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS server
server {
    listen 443 ssl http2;
    server_name camera.example.com;

    # SSL certificates
    ssl_certificate /etc/letsencrypt/live/camera.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/camera.example.com/privkey.pem;

    # SSL settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Dashboard (Flask)
    location / {
        proxy_pass http://localhost:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # EMQX Dashboard (optional)
    location /emqx/ {
        proxy_pass http://localhost:18083/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # WebSocket support for Kurento
    location /kurento {
        proxy_pass http://localhost:8888;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Enable Site

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/camera-platform /etc/nginx/sites-enabled/

# Remove default site
sudo rm /etc/nginx/sites-enabled/default

# Test configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

## SSL Certificates

### Install Certbot (Let's Encrypt)

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d camera.example.com

# Follow prompts:
# - Enter email address
# - Agree to terms
# - Choose redirect HTTP to HTTPS (option 2)

# Verify certificate
sudo certbot certificates

# Test auto-renewal
sudo certbot renew --dry-run
```

### Auto-Renewal

Certbot automatically installs a systemd timer:

```bash
# Check renewal timer
sudo systemctl list-timers | grep certbot

# Manual renewal (if needed)
sudo certbot renew
```

## Firewall Configuration

### Configure UFW (Uncomplicated Firewall)

```bash
# Enable UFW
sudo ufw enable

# Allow SSH (adjust port if changed)
sudo ufw allow 22/tcp

# Allow HTTP and HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Allow Dashboard (if not behind Nginx)
sudo ufw allow 5000/tcp

# Allow EMQX MQTT
sudo ufw allow 8883/tcp

# Allow EMQX Dashboard
sudo ufw allow 18083/tcp

# Allow STUN/TURN
sudo ufw allow 3478/tcp
sudo ufw allow 3478/udp
sudo ufw allow 5349/tcp
sudo ufw allow 5349/udp

# Allow TURN relay port range
sudo ufw allow 50000:60000/udp

# Allow Kurento WebSocket
sudo ufw allow 8888/tcp

# Check status
sudo ufw status verbose
```

### Port Summary

| Port | Protocol | Service | Required |
|------|----------|---------|----------|
| 22 | TCP | SSH | Yes |
| 80 | TCP | HTTP (redirect) | Yes |
| 443 | TCP | HTTPS | Yes |
| 5000 | TCP | Dashboard | Yes (if not proxied) |
| 8883 | TCP | EMQX MQTT/TLS | Yes |
| 18083 | TCP | EMQX Dashboard | Optional |
| 3478 | TCP/UDP | STUN | Yes |
| 5349 | TCP/UDP | TURNS | Yes |
| 8888 | TCP | Kurento WebSocket | Yes |
| 50000-60000 | UDP | TURN Relay | Yes |

## System Services

### Create Platform Service

Create a systemd service for automatic startup:

```bash
# Create service file
sudo nano /etc/systemd/system/camera-platform.service
```

```ini
[Unit]
Description=VBC01 Camera Platform
After=network.target emqx.service kurento-media-server.service
Requires=emqx.service kurento-media-server.service

[Service]
Type=forking
User=deploy
WorkingDirectory=/home/deploy/camera-platform-local
ExecStart=/home/deploy/camera-platform-local/scripts/managed_start.sh start
ExecStop=/home/deploy/camera-platform-local/scripts/managed_start.sh stop
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable camera-platform

# Start service
sudo systemctl start camera-platform

# Check status
sudo systemctl status camera-platform
```

### Service Dependencies

Ensure services start in correct order:

1. **emqx** - MQTT broker (first)
2. **kurento-media-server** - WebRTC server
3. **coturn** - TURN server
4. **nginx** - Reverse proxy
5. **camera-platform** - Platform services (last)

## Verification

### 1. Check All Services

```bash
# EMQX
sudo systemctl status emqx
emqx ctl status

# Kurento
sudo systemctl status kurento-media-server
sudo journalctl -u kurento-media-server -n 50

# coturn
sudo systemctl status coturn
sudo tail -f /var/log/turnserver.log

# Nginx
sudo systemctl status nginx
sudo nginx -t

# Camera Platform
sudo systemctl status camera-platform
./scripts/managed_status.sh
```

### 2. Test Connectivity

```bash
# Test EMQX MQTT
python3 tools/test_emqx.py

# Test STUN/TURN
# Use online tester: https://webrtc.github.io/samples/src/content/peerconnection/trickle-ice/

# Test Dashboard
curl -I https://camera.example.com

# Test Kurento WebSocket
wscat -c ws://localhost:8888/kurento
# Should connect successfully
```

### 3. View Logs

```bash
# Platform logs
tail -f logs/*.log

# EMQX logs
sudo journalctl -u emqx -f

# Kurento logs
sudo journalctl -u kurento-media-server -f

# coturn logs
sudo tail -f /var/log/turnserver.log

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

## Performance Tuning

### System Limits

```bash
# Increase file descriptor limits
sudo nano /etc/security/limits.conf

# Add:
* soft nofile 65536
* hard nofile 65536

# Increase connection tracking
sudo nano /etc/sysctl.conf

# Add:
net.netfilter.nf_conntrack_max = 1000000
net.core.somaxconn = 4096
net.ipv4.tcp_max_syn_backlog = 8192

# Apply changes
sudo sysctl -p
```

### EMQX Tuning

```bash
# Edit EMQX VM args
sudo nano /etc/emqx/vm.args

# Increase process limit
+P 2097152

# Restart EMQX
sudo systemctl restart emqx
```

## Backup and Maintenance

### Automated Backup Script

```bash
#!/bin/bash
# /home/deploy/backup.sh

BACKUP_DIR=/backups/camera-platform
DATE=$(date +%Y%m%d-%H%M%S)

mkdir -p $BACKUP_DIR

# Platform files
tar czf $BACKUP_DIR/platform-$DATE.tar.gz \
    /home/deploy/camera-platform-local \
    --exclude=venv \
    --exclude=logs \
    --exclude=data/uploads

# EMQX config
sudo cp -r /etc/emqx $BACKUP_DIR/emqx-$DATE

# Kurento config
sudo cp -r /etc/kurento $BACKUP_DIR/kurento-$DATE

# coturn config
sudo cp /etc/turnserver.conf $BACKUP_DIR/turnserver-$DATE.conf

# Delete backups older than 30 days
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete

echo "Backup completed: $DATE"
```

### Cron Jobs

```bash
# Edit crontab
crontab -e

# Add backup job (daily at 2 AM)
0 2 * * * /home/deploy/backup.sh

# Restart services weekly (Sunday 3 AM)
0 3 * * 0 sudo systemctl restart camera-platform

# Certificate renewal check (daily)
0 0 * * * sudo certbot renew --quiet
```

## Troubleshooting

### Common Issues

1. **TURN server not working:**
   - Check public IP in `external-ip` setting
   - Verify ports 50000-60000 are open
   - Test with online TURN tester

2. **Kurento not starting:**
   - Check dependencies: `sudo apt install -y gstreamer1.0-plugins-*`
   - View logs: `sudo journalctl -u kurento-media-server -n 100`

3. **EMQX certificate errors:**
   - Verify certificate paths in emqx.conf
   - Check certificate permissions: `sudo chmod 644 /path/to/*.crt`
   - Check key permissions: `sudo chmod 600 /path/to/*.key`

4. **Nginx 502 Bad Gateway:**
   - Check if platform services are running
   - Verify ports in nginx config match service ports
   - Check SELinux if enabled: `sudo setsebool -P httpd_can_network_connect 1`

## Production Checklist

- [ ] All services installed and running
- [ ] SSL certificates configured and auto-renewing
- [ ] Firewall configured with minimal open ports
- [ ] Strong passwords set (EMQX admin, TURN user, dashboard admin)
- [ ] TURN server tested with external tester
- [ ] Automated backups configured
- [ ] Monitoring/alerting set up
- [ ] Log rotation configured
- [ ] System limits increased
- [ ] Documentation updated with server details

## Next Steps

After server setup is complete:

1. **Deploy Platform:** Follow [SETUP_GUIDE.md](SETUP_GUIDE.md)
2. **Add Cameras:** Follow [CAMERA_SETUP.md](CAMERA_SETUP.md)
3. **Test Livestreaming:** Verify WebRTC works from external network
4. **Monitor Performance:** Use EMQX dashboard and system monitoring

---

**Server Setup Version:** 1.0
**Last Updated:** January 2025
**Tested On:** Ubuntu 22.04 LTS
