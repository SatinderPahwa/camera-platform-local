# Setup Guide - VBC01 Camera Platform (EMQX Edition)

Complete installation and configuration guide for the offline-capable camera management platform.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Detailed Setup](#detailed-setup)
- [Configuration](#configuration)
- [First Camera](#first-camera)
- [Verification](#verification)

## Prerequisites

### Server Infrastructure Setup

**Important:** For production Ubuntu server deployment with livestreaming support, follow [SERVER_SETUP.md](SERVER_SETUP.md) first to install:
- EMQX 5.8.8 (MQTT broker)
- Kurento Media Server 7.0.1 (WebRTC livestreaming)
- coturn (TURN/STUN server - REQUIRED for remote access)
- Nginx (reverse proxy)
- SSL certificates (Let's Encrypt)

This guide assumes you have completed the server infrastructure setup.

### System Requirements

- **Operating System:** Linux (Ubuntu 22.04+ recommended) or macOS
- **RAM:** 4GB minimum, 8GB recommended (for livestreaming)
- **Disk Space:** 50GB minimum (SSD recommended)
- **Network:** Static IP on local network
- **Domain:** Domain name pointing to your server (REQUIRED)

### Software Requirements (if not using SERVER_SETUP.md)

1. **Python 3.8 or higher**
   ```bash
   python3 --version
   ```

2. **EMQX Broker 5.8.8+** (See [SERVER_SETUP.md](SERVER_SETUP.md) for full installation)
   ```bash
   # macOS
   brew install emqx

   # Ubuntu - see SERVER_SETUP.md for production setup
   ```

3. **Git** (for cloning repository)
   ```bash
   sudo apt install git  # Ubuntu/Debian
   brew install git      # macOS
   ```

4. **FFmpeg** - For video processing
   ```bash
   sudo apt install ffmpeg  # Ubuntu/Debian
   brew install ffmpeg      # macOS
   ```

### Network Requirements

1. **Domain name** pointing to your server IP
   - Example: `camera.example.com` → `192.168.1.100`
   - Update your DNS records or `/etc/hosts` file

2. **Firewall rules** (if applicable):
   - Port 80: HTTPS config server (cameras)
   - Port 5000: Dashboard web interface
   - Port 8883: EMQX broker (MQTT over TLS)
   - Port 18083: EMQX dashboard (optional, for admin)

## Quick Start

For experienced users, here's the fast track:

```bash
# 1. Clone repository
git clone <repo-url> camera-platform-local
cd camera-platform-local

# 2. Install Python dependencies
python3 -m venv venv
source venv/bin/activate  # or: venv\Scripts\activate on Windows
pip install -r requirements.txt

# 3. Run setup wizard
python3 setup_platform.py

# 4. Start EMQX broker
sudo emqx start

# 5. Start platform services
./scripts/managed_start.sh start

# 6. Access dashboard
open http://localhost:5000
```

## Detailed Setup

### Step 1: Clone Repository

```bash
git clone <repo-url> camera-platform-local
cd camera-platform-local
```

### Step 2: Create Virtual Environment

Using a virtual environment is recommended to isolate dependencies:

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate     # Windows
```

### Step 3: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This installs:
- Flask (web server)
- paho-mqtt (MQTT client)
- cryptography (certificate generation)
- python-telegram-bot (notifications)
- And other required packages

### Step 4: Run Setup Wizard

The setup wizard automates all configuration:

```bash
python3 setup_platform.py
```

**Interactive mode** will prompt you for:

1. **Domain name** (e.g., `camera.example.com`)
2. **Server IP address** (e.g., `192.168.1.100`)
3. **Telegram bot token** (get from @BotFather)
4. **Telegram chat ID** (get from @userinfobot)
5. **(Optional) TURN server** for remote access

The wizard will:
- ✅ Generate CA certificate (4096-bit, 10-year validity)
- ✅ Generate broker certificate (with domain + IP SAN)
- ✅ Generate shared client certificate (for all cameras)
- ✅ Create EMQX configuration file
- ✅ Generate `.env` file with all settings
- ✅ Create camera_files/ package (ready to deploy)
- ✅ Generate personalized DEPLOYMENT_GUIDE.md

### Step 5: Configure EMQX

Copy the generated EMQX configuration:

```bash
# The setup wizard creates emqx.conf in deployment/
sudo cp deployment/emqx.conf /etc/emqx/emqx.conf

# Or manually configure EMQX:
sudo emqx ctl listeners
```

### Step 6: Start EMQX Broker

```bash
sudo emqx start

# Verify it's running
emqx ctl status

# Check listeners
emqx ctl listeners
```

Expected output:
```
mqtts:ssl:default
  listen_on       : 0.0.0.0:8883
  acceptors       : 16
  max_conns       : 512000
  current_conn    : 0
  shutdown_count  : []
```

### Step 7: Start Platform Services

```bash
# Start all services
./scripts/managed_start.sh start

# Check status
./scripts/managed_start.sh status
```

Services started:
1. **Config Server** (port 80) - Provides certificates to cameras
2. **MQTT Processor** - Processes camera events into database
3. **Dashboard Server** (port 5000) - Web interface

### Step 8: Access Dashboard

Open your browser and navigate to:

```
http://localhost:5000
```

**Default credentials:**
- Username: `admin`
- Password: `change_me` (or what you set in .env)

**Important:** Change the default password immediately in production!

## Configuration

### Environment Variables

All configuration is in the `.env` file (auto-generated by setup wizard).

**Key settings:**

```bash
# EMQX Broker
EMQX_BROKER_ENDPOINT=camera.example.com
EMQX_BROKER_PORT=8883

# Telegram Notifications
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Dashboard
DASHBOARD_SERVER_PORT=5000
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change_me_in_production
```

To modify configuration:
1. Edit `.env` file
2. Restart services: `./scripts/managed_start.sh restart`

### EMQX Dashboard (Optional)

Access EMQX admin dashboard:

```
http://localhost:18083
Username: admin
Password: public
```

**Important:** Change the default EMQX password in production!

## First Camera

Now you're ready to add your first camera!

See [CAMERA_SETUP.md](CAMERA_SETUP.md) for detailed instructions.

Quick overview:

```bash
# 1. Generate camera certificate package
python3 tools/add_camera.py YOUR_CAMERA_ID

# 2. FTP files to camera (/root/certs/)
# 3. Update camera database (configSrvHost)
# 4. Reboot camera
# 5. Verify connection in dashboard
```

## Verification

### Check Service Status

```bash
./scripts/managed_start.sh status
```

Expected output:
```
======================================
Server Status
======================================
EMQX broker:        Running
config_server:      Running (PID: 12345)
mqtt_processor:     Running (PID: 12346)
dashboard_server:   Running (PID: 12347)
```

### View Logs

```bash
# Watch all logs
tail -f logs/*.log

# Individual services
tail -f logs/config_server.log
tail -f logs/mqtt_processor.log
tail -f logs/dashboard_server.log
```

### Test EMQX Connection

```bash
python3 tools/test_emqx.py
```

Expected output:
```
======================================
EMQX Connection Test
======================================
✅ Connected to EMQX broker
✅ Subscribed to test/emqx/connection
✅ Test message published
✅ Test message received successfully
```

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues and solutions.

## Next Steps

1. ✅ Platform is running
2. 📷 [Add cameras](CAMERA_SETUP.md)
3. 🔔 [Configure notifications](CAMERA_SETUP.md#telegram-notifications)
4. 🎥 [Set up livestreaming](CAMERA_SETUP.md#livestreaming)
5. 🚀 [Deploy to production server](DEPLOYMENT.md)

## Support

For issues, questions, or feature requests, please open an issue on GitHub.

---

**Built with ❤️ for privacy-focused, offline-capable home security**
