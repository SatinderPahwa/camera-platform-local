# VBC01 Camera Platform - Local MQTT Edition

**Fully offline-capable home security camera platform with WebRTC livestreaming**

No cloud dependencies. No AWS account. No internet required. Complete privacy.

---

## 🎯 What is This?

A self-hosted camera management platform for VBC01 (Hive) cameras that runs entirely on your local network using EMQX MQTT broker instead of AWS IoT Core.

**Key Features:**
- 📹 Live streaming (WebRTC) from anywhere
- 🔔 Instant notifications with thumbnails (Telegram)
- 💾 Encrypted recording storage and playback
- 🌐 Web dashboard for camera control
- 🔒 Complete privacy - all data stays on your server
- ⚡ One-command automated setup

---

## 📖 Start Here - User Journey

### **Scenario 1: I'm Starting Fresh**
*I have a new Ubuntu server and want to set up everything from scratch*

→ **Go to: [Complete Deployment Guide](docs/DEPLOYMENT_GUIDE.md)**

This guide walks you through:
1. Installing all infrastructure (EMQX, Kurento, TURN server)
2. Setting up the platform
3. Adding your first camera
4. Testing everything works

**Time required:** 2-3 hours

---

### **Scenario 2: I Already Have Infrastructure**
*I have EMQX/Kurento installed, just need the platform*

→ **Quick Setup:**

```bash
# 1. Clone repository
git clone https://github.com/SatinderPahwa/camera-platform-local.git
cd camera-platform-local

# 2. Install Python dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Run automated setup wizard
python3 setup_platform.py

# 4. Start services
./scripts/managed_start.sh start

# 5. Add cameras
python3 tools/add_camera.py <CAMERA_ID>
```

**Need details?** See [Platform Setup Only](docs/DEPLOYMENT_GUIDE.md#platform-setup)

---

### **Scenario 3: I Need to Add More Cameras**
*Platform is running, I want to add another camera*

→ **Go to: [Camera Setup Guide](docs/CAMERA_SETUP.md)**

Quick steps:
```bash
python3 tools/add_camera.py <CAMERA_ID>
# Follow prompts to FTP certificates to camera
```

---

### **Scenario 4: Something's Not Working**
*I have issues with cameras, streaming, or notifications*

→ **Go to: [Troubleshooting Guide](docs/TROUBLESHOOTING.md)**

Common issues:
- Camera won't connect → Check EMQX and certificates
- No livestream → TURN server configuration
- No notifications → Telegram token/chat ID

---

## 🏗️ System Architecture

```
┌─────────────────┐
│  VBC01 Cameras  │  (Your home security cameras)
└────────┬────────┘
         │ MQTT/TLS (port 8883)
         ↓
┌─────────────────┐
│  EMQX Broker    │  (Local MQTT server)
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│ MQTT Processor  │  (Event processing + notifications)
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│    Database     │  (SQLite - events, recordings)
└─────────────────┘

┌─────────────────┐
│ Web Dashboard   │  (https://your-domain.com)
└─────────────────┘

┌─────────────────┐
│ Kurento + TURN  │  (Livestreaming from anywhere)
└─────────────────┘
```

**No AWS. No Cloud. All Local.**

---

## 📋 Requirements

### **What You Need:**

1. **Ubuntu Server** (22.04 LTS recommended)
   - 4GB RAM minimum, 8GB recommended
   - 50GB disk space (SSD recommended)
   - Static IP address

2. **Domain Name** (REQUIRED)
   - Must point to your server
   - Example: `camera.yourdomain.com`
   - Needed for SSL and camera connections

3. **Telegram Bot** (for notifications)
   - Create bot with @BotFather
   - Get your chat ID from @userinfobot

4. **Port Forwarding** (if accessing remotely)
   - See [DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md#firewall-configuration)

### **What Gets Installed:**

- **EMQX 5.8.8** - MQTT broker
- **Kurento 7.0.1** - WebRTC media server
- **coturn** - TURN/STUN server (REQUIRED for remote streaming)
- **Nginx** - Reverse proxy
- **Python 3.8+** - Platform runtime
- **SSL Certificates** - Let's Encrypt (free)

---

## 🚀 Quick Start (If You Can't Wait)

```bash
# On Ubuntu server
git clone https://github.com/SatinderPahwa/camera-platform-local.git
cd camera-platform-local

# Run the setup wizard - it handles everything
python3 setup_platform.py

# Start platform
./scripts/managed_start.sh start

# Add camera
python3 tools/add_camera.py YOUR_CAMERA_ID
```

**Note:** This assumes EMQX, Kurento, and TURN server are already installed. If not, start with [DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md).

---

## 📚 Documentation

Choose your path:

| Document | When to Use |
|----------|-------------|
| **[DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md)** | **Start here for complete setup** |
| [CAMERA_SETUP.md](docs/CAMERA_SETUP.md) | Adding cameras after platform is running |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Fixing issues |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Understanding how it works |

---

## 🎥 Supported Cameras

- **Model:** VBC01 (Hive Camera)
- **Firmware:** FW117 and compatible versions
- **Connection:** MQTT over TLS (mutual authentication)
- **Features:** Motion detection, person detection, encrypted recordings

**Have different cameras?** This platform is designed specifically for VBC01 cameras with AWS IoT SDK v2.1.1.

---

## 💡 Key Differences from AWS IoT Version

| Feature | AWS IoT Version | This Version |
|---------|----------------|--------------|
| **MQTT Broker** | AWS IoT Core (cloud) | EMQX (your server) |
| **Internet** | Required | Optional |
| **Setup Time** | Hours (AWS setup) | Minutes (automated) |
| **Monthly Cost** | AWS charges | $0 (self-hosted) |
| **Data Privacy** | Stored in AWS | Stays on your server |
| **Remote Access** | Always works | Requires TURN server |

---

## 🛠️ Getting Help

1. **Check the guides:**
   - [Deployment Guide](docs/DEPLOYMENT_GUIDE.md)
   - [Troubleshooting](docs/TROUBLESHOOTING.md)

2. **Check service status:**
   ```bash
   ./scripts/managed_status.sh
   ```

3. **View logs:**
   ```bash
   tail -f logs/*.log
   ```

4. **Open an issue:**
   - GitHub Issues: https://github.com/SatinderPahwa/camera-platform-local/issues

---

## 🤝 Contributing

This is a personal project, but contributions are welcome! If you've improved something or fixed a bug, pull requests are appreciated.

---

## 📄 License

MIT License - See [LICENSE](LICENSE) file

---

## 🙏 Credits

- Built for VBC01 Hive Cameras
- Powered by [EMQX](https://www.emqx.io/)
- Livestreaming via [Kurento](https://www.kurento.org/)
- Notifications via [Telegram](https://telegram.org/)

---

**Built with ❤️ for privacy-focused, offline-capable home security**

**Questions?** Start with the [Deployment Guide](docs/DEPLOYMENT_GUIDE.md) → It has everything you need.
