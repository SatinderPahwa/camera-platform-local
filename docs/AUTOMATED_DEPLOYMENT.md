# Automated Deployment Scripts

This document describes the fully automated deployment process for the camera platform. All manual steps have been eliminated.

---

## Overview

The platform deployment is now fully automated through a series of scripts that handle everything from infrastructure setup to production hardening. **No manual configuration required.**

---

## Deployment Scripts

### 1. Platform Setup
**Script:** `setup_platform.py`

**What it does:**
- Generates CA and broker certificates
- Creates MQTT client certificates
- Generates `.env` file with all configuration
- Creates EMQX configuration
- Generates camera deployment files

**Usage:**
```bash
python3 setup_platform.py
```

**Interactive prompts:**
- Domain name
- Server IP address
- Telegram bot token and chat ID
- TURN server credentials

**Output:**
- `.env` - Environment configuration
- `config/emqx.conf` - EMQX broker configuration
- `certificates/` - All SSL/TLS certificates
- `camera_files/` - Camera deployment files

---

### 2. SSL Certificate Permissions
**Script:** `scripts/setup_ssl_certificates.sh`

**What it does:**
- Creates `ssl-certs` group for secure certificate access
- Adds user and turnserver to the group
- Sets secure permissions (640 for private keys, 644 for certs)
- Creates Certbot post-renewal hook (preserves permissions)
- Updates `.env` with SSL configuration

**Usage:**
```bash
sudo ./scripts/setup_ssl_certificates.sh
```

**Fully automated:**
- ✅ No manual group activation required
- ✅ Services automatically use group permissions when started
- ✅ Certbot renewals automatically maintain correct permissions

**Output:**
- `/etc/letsencrypt/` - Certificates with ssl-certs group ownership
- `/etc/letsencrypt/renewal-hooks/post/fix-permissions.sh` - Auto-fix hook
- `.env` - Updated with SSL paths

---

### 3. TURN Server Configuration
**Script:** `scripts/configure_turn_server.sh`

**What it does:**
- Reads domain from `.env` automatically
- Auto-detects local and external IP addresses
- Creates `/etc/turnserver.conf` with correct realm/domain
- Configures SSL certificate paths for TLS
- Starts and enables coturn service

**Usage:**
```bash
sudo ./scripts/configure_turn_server.sh
```

**Fully automated:**
- ✅ No manual configuration editing
- ✅ Domain automatically matches platform domain
- ✅ SSL certificates automatically configured
- ✅ Service started and enabled

**Output:**
- `/etc/turnserver.conf` - TURN server configuration
- coturn service running with TLS support

---

### 4. Production Hardening
**Script:** `scripts/setup_production_hardening.sh`

**What it does:**
- Enables user lingering (services persist without login)
- Creates systemd service for auto-start on boot
- Configures sudo rules (passwordless EMQX commands)
- Sets up cron job: Health checks every 12 minutes
- Sets up cron job: Scheduled restarts every 8 hours

**Usage:**
```bash
sudo ./scripts/setup_production_hardening.sh
```

**Fully automated:**
- ✅ No manual systemd file editing
- ✅ No manual crontab editing
- ✅ No manual sudoers editing
- ✅ All services auto-configured

**Output:**
- `~/.config/systemd/user/camera-platform.service` - Systemd service
- `/etc/sudoers.d/camera-platform` - Sudo rules
- Crontab entries for health checks and restarts

---

## Complete Deployment Process

### Prerequisites
- Ubuntu 22.04 LTS server
- Domain name with DNS configured
- Let's Encrypt certificates obtained (DNS-01 challenge)
- EMQX, Docker/Kurento, coturn installed

### Deployment Steps

```bash
# 1. Clone repository
cd ~
git clone https://github.com/SatinderPahwa/camera-platform-local.git
cd camera-platform-local

# 2. Create virtual environment and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 3. Set file permissions
sudo chown -R $(whoami):$(whoami) .
chmod -R u+w data/ logs/ pids/

# 4. Run platform setup (interactive)
python3 setup_platform.py
# Answer prompts: domain, IP, Telegram credentials, TURN credentials

# 5. Configure EMQX with generated certificates
sudo cp config/emqx.conf /etc/emqx/emqx.conf
sudo mkdir -p /etc/emqx/certs
sudo cp certificates/ca.crt /etc/emqx/certs/
sudo cp certificates/broker.crt /etc/emqx/certs/
sudo cp certificates/broker.key /etc/emqx/certs/
sudo cp certificates/camera_client.crt /etc/emqx/certs/
sudo cp certificates/camera_client.key /etc/emqx/certs/
sudo chown -R emqx:emqx /etc/emqx/certs
sudo chmod 644 /etc/emqx/certs/*.crt
sudo chmod 600 /etc/emqx/certs/*.key
sudo systemctl restart emqx

# 6. Configure SSL certificate permissions (automated)
sudo ./scripts/setup_ssl_certificates.sh

# 7. Configure TURN server (automated)
sudo ./scripts/configure_turn_server.sh

# 8. Production hardening (automated)
sudo ./scripts/setup_production_hardening.sh

# 9. Start platform services
./scripts/managed_start.sh start

# 10. Verify deployment
./scripts/managed_status.sh
```

**Total time:** ~10 minutes (excluding EMQX/Docker installation)

---

## Verification

After deployment, verify everything is working:

```bash
# Check all services
./scripts/managed_status.sh

# Check systemd service
systemctl --user status camera-platform.service

# Check cron jobs
crontab -l | grep "Camera Platform"

# Check logs
tail -f logs/gunicorn_error.log
tail -f logs/mqtt_processor.log
tail -f logs/config_server.log

# Test health check
./tools/health_check_and_restart.sh
tail -f logs/health_check.log

# Test HTTPS access
curl -k -I https://localhost:5000/health
```

---

## Zero Manual Steps

The following previously manual steps are now fully automated:

| Task | Previous Method | Automated By |
|------|----------------|--------------|
| SSL group creation | Manual group commands | `setup_ssl_certificates.sh` |
| Certificate permissions | Manual chmod/chown | `setup_ssl_certificates.sh` |
| Certbot renewal hook | Manual script creation | `setup_ssl_certificates.sh` |
| TURN server config | Manual editing of turnserver.conf | `configure_turn_server.sh` |
| Systemd service | Manual file creation and enable | `setup_production_hardening.sh` |
| Sudo rules | Manual visudo editing | `setup_production_hardening.sh` |
| Cron jobs | Manual crontab -e editing | `setup_production_hardening.sh` |
| User lingering | Manual loginctl command | `setup_production_hardening.sh` |

---

## Repeatable Deployment

The deployment is now 100% repeatable on a fresh server:

```bash
# Full deployment in one go
cd ~/camera-platform-local
python3 setup_platform.py                           # Interactive prompts
sudo ./scripts/setup_ssl_certificates.sh            # Automated
sudo ./scripts/configure_turn_server.sh             # Automated
sudo ./scripts/setup_production_hardening.sh        # Automated
./scripts/managed_start.sh start                    # Automated
```

**Result:**
- ✅ All services configured and running
- ✅ Auto-start on boot enabled
- ✅ Health monitoring active
- ✅ Self-healing configured
- ✅ No manual intervention required

---

## Adding Cameras

Camera provisioning is also automated:

```bash
# Generate certificates and configuration
python3 tools/add_camera.py CAMERA_ID

# Deploy to camera via FTP (use generated files)
cd camera_files/CAMERA_ID
# Files ready for FTP upload (no manual editing needed)
```

---

## Maintenance

All maintenance tasks are automated:

**Health Monitoring:**
- Runs every 12 minutes via cron
- Auto-restarts failed services
- Logs to `logs/health_check.log`

**Scheduled Restarts:**
- Every 8 hours (8 AM, 4 PM, Midnight)
- Prevents connection leaks
- Logs to `logs/cron_restart.log`

**Certificate Renewal:**
- Certbot renewal hook auto-fixes permissions
- No manual intervention needed
- Services continue running

---

## Troubleshooting

If deployment fails at any step:

1. **Check script output** - All scripts provide detailed status
2. **Verify prerequisites** - Ensure EMQX, Docker, coturn installed
3. **Check logs** - Scripts log to their respective log files
4. **Re-run script** - All scripts are idempotent (safe to re-run)

**Common issues:**

```bash
# SSL certificates not found
sudo certbot certificates  # Verify Let's Encrypt certs exist

# EMQX not starting
sudo journalctl -u emqx -n 50  # Check EMQX logs

# Services not accessible
sudo ufw status  # Verify firewall rules

# Group permissions
groups  # Should show ssl-certs (after logout/login)
```

---

## Design Principles

The automated deployment follows these principles:

1. **Idempotent:** Scripts can be run multiple times safely
2. **Self-documenting:** Scripts output what they're doing
3. **Verifiable:** Scripts include built-in verification steps
4. **Minimal interaction:** Only essential prompts (domain, credentials)
5. **Secure by default:** Proper permissions, no world-readable keys
6. **Repeatable:** Same process works on any fresh Ubuntu 22.04 server

---

## See Also

- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Complete deployment guide
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Fix common issues
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
