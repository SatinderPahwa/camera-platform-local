# Complete Deployment Guide

**From blank Ubuntu server to working camera platform in 2-3 hours**

This is THE guide - everything you need in the right order.

---

## 📖 What This Guide Covers

By the end of this guide, you'll have:
- ✅ Ubuntu server ready with all infrastructure installed
- ✅ Camera platform running and accessible
- ✅ Your first camera connected and streaming
- ✅ Notifications working (Telegram)
- ✅ Web dashboard accessible from anywhere

**Time Required:** 2-3 hours (most is waiting for installations)

---

## 🎯 Prerequisites - What You Need

Before starting, have these ready:

### 1. Ubuntu Server
- **Version:** Ubuntu 22.04 LTS (fresh install)
- **Hardware:** 4GB RAM, 50GB disk, 4 CPU cores
- **Access:** SSH access as user with sudo privileges
- **Network:** Static IP address assigned

### 2. Domain Name
- **Required:** Yes (cameras won't connect without it)
- **Example:** `camera.yourdomain.com`
- **DNS:** Already pointing to your server's public IP
- **Why:** Needed for SSL certificates and camera connections

### 3. Telegram Bot
- Open Telegram, search for `@BotFather`
- Send `/newbot` and follow prompts
- **Save the bot token** (looks like: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)
- Get your chat ID from `@userinfobot` (send `/start`)
- **Save your chat ID** (looks like: `123456789`)

### 4. Camera ID
- Find your camera's 32-character ID
- Methods: Check camera database, AWS IoT console, or EMQX logs
- **Example:** `67E48798E70345179A86980A7CAAAE73`

### 5. Router Configuration
If accessing from outside your home:
- Port forward 443 (HTTPS) to your server
- Port forward 3478/5349 (TURN) to your server
- Port forward 50000-60000 (UDP) to your server

---

## Part 1: Server Infrastructure Setup

### Step 1.1: Initial Server Setup

```bash
# SSH into your server
ssh your-user@your-server-ip

# Update system
sudo apt update && sudo apt upgrade -y

# Install essential tools
sudo apt install -y curl wget git vim build-essential software-properties-common

# Set timezone (adjust to yours)
sudo timedatectl set-timezone America/New_York

# Set hostname
sudo hostnamectl set-hostname camera-server
```

### Step 1.2: Install EMQX Broker (5.8.8)

```bash
# Add EMQX repository
curl -s https://assets.emqx.com/scripts/install-emqx-deb.sh | sudo bash

# Install specific version
sudo apt install -y emqx=5.8.8

# Prevent auto-updates
sudo apt-mark hold emqx

# Enable and start
sudo systemctl enable emqx
sudo systemctl start emqx

# Verify
emqx ctl status
# Should show: EMQX 5.8.8 is running
```

### Step 1.3: Install Kurento Media Server (7.0.1)

```bash
# Add repository key
sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 5AFA7A83

# Add Kurento repository
sudo tee /etc/apt/sources.list.d/kurento.list <<EOF
deb [arch=amd64] http://ubuntu.openvidu.io/7.0.1 jammy kms7
EOF

# Install
sudo apt update
sudo apt install -y kurento-media-server=7.0.1

# Hold version
sudo apt-mark hold kurento-media-server

# Enable and start
sudo systemctl enable kurento-media-server
sudo systemctl start kurento-media-server

# Verify
sudo systemctl status kurento-media-server
```

### Step 1.4: Install TURN Server (coturn)

**CRITICAL:** This is REQUIRED for livestreaming from outside your network.

```bash
# Install coturn
sudo apt install -y coturn

# Enable coturn
sudo nano /etc/default/coturn
# Uncomment this line: TURNSERVER_ENABLED=1

# Configure coturn
sudo nano /etc/turnserver.conf
```

**Paste this configuration** (replace YOUR_DOMAIN and IPs):

```ini
realm=YOUR_DOMAIN
server-name=YOUR_DOMAIN

listening-ip=0.0.0.0
listening-port=3478
tls-listening-port=5349

# Replace with your actual IPs
external-ip=YOUR_PUBLIC_IP/YOUR_LOCAL_IP
relay-ip=YOUR_LOCAL_IP

min-port=50000
max-port=60000

lt-cred-mech
user=turnuser:STRONG_PASSWORD_HERE

# We'll add cert paths after Let's Encrypt
# cert=/etc/letsencrypt/live/YOUR_DOMAIN/fullchain.pem
# pkey=/etc/letsencrypt/live/YOUR_DOMAIN/privkey.pem

verbose
log-file=/var/log/turnserver.log
fingerprint
no-multicast-peers
no-cli
```

**Don't start coturn yet** - we need SSL certificates first.

### Step 1.5: Install Nginx

```bash
# Install Nginx
sudo apt install -y nginx

# Stop default server
sudo systemctl stop nginx
```

We'll configure Nginx after getting SSL certificates.

### Step 1.6: Get SSL Certificates (Let's Encrypt)

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Get certificate (replace YOUR_DOMAIN)
sudo certbot certonly --standalone -d YOUR_DOMAIN

# Follow prompts:
# - Enter your email
# - Agree to terms
# - Choose not to share email (N)

# Verify certificate
sudo certbot certificates
```

**Certificates installed at:**
- `/etc/letsencrypt/live/YOUR_DOMAIN/fullchain.pem`
- `/etc/letsencrypt/live/YOUR_DOMAIN/privkey.pem`

### Step 1.7: Configure Nginx Reverse Proxy

```bash
# Create site configuration
sudo nano /etc/nginx/sites-available/camera-platform
```

**Paste this** (replace YOUR_DOMAIN):

```nginx
# HTTP - redirect to HTTPS
server {
    listen 80;
    server_name YOUR_DOMAIN;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS
server {
    listen 443 ssl http2;
    server_name YOUR_DOMAIN;

    ssl_certificate /etc/letsencrypt/live/YOUR_DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/YOUR_DOMAIN/privkey.pem;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Dashboard
    location / {
        proxy_pass http://localhost:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/camera-platform /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default

# Test configuration
sudo nginx -t

# Start Nginx
sudo systemctl enable nginx
sudo systemctl start nginx
```

### Step 1.8: Update coturn with SSL Certificates

```bash
# Edit coturn config
sudo nano /etc/turnserver.conf

# Uncomment and update these lines:
cert=/etc/letsencrypt/live/YOUR_DOMAIN/fullchain.pem
pkey=/etc/letsencrypt/live/YOUR_DOMAIN/privkey.pem

# Start coturn
sudo systemctl start coturn
sudo systemctl enable coturn

# Verify
sudo systemctl status coturn
```

### Step 1.9: Configure Firewall

```bash
# Enable UFW
sudo ufw enable

# SSH (adjust port if changed)
sudo ufw allow 22/tcp

# HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# EMQX MQTT
sudo ufw allow 8883/tcp

# TURN/STUN
sudo ufw allow 3478/tcp
sudo ufw allow 3478/udp
sudo ufw allow 5349/tcp
sudo ufw allow 5349/udp

# TURN relay ports
sudo ufw allow 50000:60000/udp

# Check status
sudo ufw status verbose
```

✅ **Infrastructure complete!** All services are now running.

---

## Part 2: Platform Setup

### Step 2.1: Clone Repository

```bash
# Clone to home directory
cd ~
git clone https://github.com/SatinderPahwa/camera-platform-local.git
cd camera-platform-local
```

### Step 2.2: Install Python Dependencies

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 2.3: Run Setup Wizard

The setup wizard will generate certificates and configuration.

```bash
python3 setup_platform.py
```

**Answer the prompts:**

1. **Domain name:** `YOUR_DOMAIN` (e.g., camera.yourdomain.com)
2. **Server IP:** Your server's IP (e.g., 192.168.1.100)
3. **Telegram bot token:** Your bot token from BotFather
4. **Telegram chat ID:** Your chat ID from userinfobot
5. **TURN server URL:** `turns:YOUR_DOMAIN:5349`
6. **TURN username:** `turnuser`
7. **TURN password:** The password you set in coturn config

**Setup wizard will:**
- Generate CA certificate
- Generate broker certificate
- Generate client certificates
- Create `.env` file
- Create EMQX configuration
- Create camera deployment files
- Generate checksums

### Step 2.4: Configure EMQX with Generated Certificates

```bash
# Copy EMQX config
sudo cp deployment/emqx.conf /etc/emqx/emqx.conf

# Copy certificates to EMQX directory
sudo mkdir -p /etc/emqx/certs
sudo cp certificates/ca.crt /etc/emqx/certs/
sudo cp certificates/broker.crt /etc/emqx/certs/
sudo cp certificates/broker.key /etc/emqx/certs/
sudo cp certificates/camera_client.crt /etc/emqx/certs/
sudo cp certificates/camera_client.key /etc/emqx/certs/

# Set permissions
sudo chown -R emqx:emqx /etc/emqx/certs
sudo chmod 644 /etc/emqx/certs/*.crt
sudo chmod 600 /etc/emqx/certs/*.key

# Restart EMQX
sudo systemctl restart emqx

# Verify EMQX is listening on 8883
emqx ctl listeners
```

### Step 2.5: Start Platform Services

```bash
# Start all services
./scripts/managed_start.sh start

# Check status
./scripts/managed_status.sh
```

**You should see:**
```
EMQX broker:        Running
config_server:      Running (PID: XXXXX)
mqtt_processor:     Running (PID: XXXXX)
dashboard_server:   Running (PID: XXXXX)
```

### Step 2.6: Test Platform Access

```bash
# Test dashboard (from your laptop)
https://YOUR_DOMAIN

# Login with credentials from .env:
# Username: admin
# Password: (check .env file)
```

✅ **Platform is running!** Ready to add cameras.

---

## Part 3: Add Your First Camera

### Step 3.1: Generate Camera Certificates

```bash
# Replace with your camera's actual ID
python3 tools/add_camera.py YOUR_CAMERA_ID

# Example:
python3 tools/add_camera.py 67E48798E70345179A86980A7CAAAE73
```

**This creates:** `camera_files/YOUR_CAMERA_ID/`
- `mqttCA.crt` - CA certificate
- `mqtt.pem` - Client certificate + key
- `mqtt.key` - Private key
- `checksums.txt` - Verify file integrity

### Step 3.2: Deploy Certificates to Camera

**Connect via FTP:**

```bash
# From camera_files directory
cd camera_files/YOUR_CAMERA_ID

# Connect to camera
ftp YOUR_CAMERA_IP
# Login: root / YOUR_CAMERA_PASSWORD

# Upload files
ftp> cd /root/certs
ftp> put mqttCA.crt
ftp> put mqtt.pem
ftp> put mqtt.key
ftp> quit
```

**Verify upload (SSH/telnet to camera):**

```bash
telnet YOUR_CAMERA_IP
# Login: root / YOUR_CAMERA_PASSWORD

# Check files
ls -lh /root/certs/
md5sum /root/certs/*

# Compare checksums with checksums.txt
```

### Step 3.3: Update Camera Configuration

**On camera (via SSH/telnet):**

```bash
# Backup database
cp /cali/master_ctrl.db /cali/master_ctrl.db.backup

# Update config server host
sqlite3 /cali/master_ctrl.db "UPDATE app_info SET value='YOUR_SERVER_IP' WHERE key='configSrvHost';"

# Verify
sqlite3 /cali/master_ctrl.db "SELECT * FROM app_info WHERE key='configSrvHost';"

# Append CA certificate to trusted bundle (one-time)
cat /root/certs/mqttCA.crt >> /etc/ssl/certs/ca-bundle.trust.crt
```

### Step 3.4: Reboot Camera

```bash
# On camera
reboot
```

**Wait 1-2 minutes for camera to boot and connect.**

---

## Part 4: Verification

### Check 1: Config Server Logs

```bash
# Watch config server logs
tail -f logs/config_server.log

# Expected output:
# Camera YOUR_CAMERA_ID requested config
# Sending config response with EMQX broker: YOUR_DOMAIN
# Camera YOUR_CAMERA_ID requested certificates
# Sending certificates...
```

### Check 2: EMQX Connection

```bash
# Check EMQX clients
emqx ctl clients list | grep YOUR_CAMERA_ID

# Should show your camera connected
```

Or open EMQX dashboard:
```
http://YOUR_SERVER_IP:18083
Username: admin
Password: public (change this!)
```

Navigate to **Clients** → You should see your camera ID connected.

### Check 3: MQTT Processor Logs

```bash
tail -f logs/mqtt_processor.log

# Expected output:
# Connection event: Camera YOUR_CAMERA_ID - connected
# Firmware version: V0_0_00_117RC_svn1356
```

### Check 4: Web Dashboard

```bash
# Open in browser
https://YOUR_DOMAIN

# You should see:
# - Camera listed in dashboard
# - Status: Online/Connected
# - Last seen: Recent timestamp
```

### Check 5: Test Notification

**Trigger motion detection:**
- Wave hand in front of camera
- Wait 5-10 seconds

**Check Telegram:**
- You should receive notification with thumbnail
- Message shows camera name, type, and timestamp

### Check 6: Test Livestream

**In dashboard:**
1. Click on camera name
2. Click "View Live Stream"
3. Stream should start within 5-10 seconds

**If stream doesn't work:**
- Check TURN server: `sudo systemctl status coturn`
- Test TURN: https://webrtc.github.io/samples/src/content/peerconnection/trickle-ice/
- Check Kurento: `sudo systemctl status kurento-media-server`

---

## 🎉 Success! What's Next?

Your camera platform is now fully operational!

### Add More Cameras

```bash
python3 tools/add_camera.py ANOTHER_CAMERA_ID
# Repeat FTP and configuration steps
```

### Secure Your Installation

1. **Change EMQX admin password:**
   ```bash
   emqx ctl admins passwd admin NEW_STRONG_PASSWORD
   ```

2. **Change dashboard password:**
   ```bash
   nano .env
   # Update ADMIN_PASSWORD
   ./scripts/managed_start.sh restart
   ```

3. **Set up automated backups:**
   ```bash
   # See docs/SERVER_SETUP.md#backup-and-maintenance
   ```

### Monitor System

```bash
# Check all services
./scripts/managed_status.sh

# View logs
tail -f logs/*.log

# Check EMQX dashboard
http://YOUR_SERVER_IP:18083
```

### Learn More

- **[CAMERA_SETUP.md](CAMERA_SETUP.md)** - Detailed camera setup guide
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Fix common issues
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Understand the system

---

## 🆘 Something Went Wrong?

### Quick Diagnostics

```bash
# Check all services
./scripts/managed_status.sh

# Check EMQX
emqx ctl status
emqx ctl listeners

# Check logs for errors
grep -i error logs/*.log

# Test EMQX connection
python3 tools/test_emqx.py
```

### Common Issues

**Camera not connecting:**
- Check domain resolves: `ping YOUR_DOMAIN`
- Check certificates on camera: `ls -l /root/certs/`
- Check EMQX logs: `sudo journalctl -u emqx -n 50`

**No livestream:**
- Check TURN server: `sudo systemctl status coturn`
- Check Kurento: `sudo systemctl status kurento-media-server`
- Test TURN: https://webrtc.github.io/samples/src/content/peerconnection/trickle-ice/

**No notifications:**
- Check Telegram token: `cat .env | grep TELEGRAM`
- Test token: `curl https://api.telegram.org/botYOUR_TOKEN/getMe`
- Check processor logs: `grep -i telegram logs/mqtt_processor.log`

**Full troubleshooting:** [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

---

## 📞 Get Help

1. Check [Troubleshooting Guide](TROUBLESHOOTING.md)
2. Review logs: `tail -f logs/*.log`
3. Open GitHub issue with logs and setup details

---

**Congratulations on deploying your camera platform!** 🎉

You now have a fully private, self-hosted security camera system with:
- ✅ Livestreaming from anywhere
- ✅ Instant notifications
- ✅ Encrypted recordings
- ✅ Complete data privacy

**Questions?** Check the other guides or open an issue on GitHub.
