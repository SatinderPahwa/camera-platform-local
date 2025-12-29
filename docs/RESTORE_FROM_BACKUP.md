# Restore From Backup Guide

This guide explains how to restore the camera platform server from backups created by the three-tier backup system.

## Backup Overview

The backup system creates three tiers of backups:

1. **Tier 1: Full System Backup** (`backup_system.sh`)
   - Complete server backup excluding recordings partition
   - Uses rsync with hard links for incremental backups
   - Location: `/mnt/backup/system/YYYY-MM-DD_HH-MM-SS/`
   - Best for: Full system recovery, hardware migration

2. **Tier 2: Metadata Backup** (`backup_metadata.sh`)
   - Package lists, configs, service configurations
   - Location: `/mnt/backup/metadata/YYYY-MM-DD_HH-MM-SS/`
   - Best for: System recreation on new hardware, auditing

3. **Tier 3: Application Backup** (`backup_application.sh`)
   - Compressed tarball of application code and databases
   - Location: `/mnt/backup/application/camera-platform-YYYY-MM-DD_HH-MM-SS.tar.gz`
   - Best for: Quick application recovery

---

## Restoration Scenarios

### Scenario 1: Application Corruption (Quick Recovery)

**Use:** Tier 3 (Application Backup)
**Time:** ~5 minutes
**Prerequisites:** System is intact, only application is corrupted

#### Steps:

1. **Stop all services:**
   ```bash
   cd /home/satinder/camera-platform-local
   ./scripts/managed_start.sh stop
   ```

2. **Backup current corrupted application (optional):**
   ```bash
   sudo mv /home/satinder/camera-platform-local /home/satinder/camera-platform-local.backup
   ```

3. **Mount backup SSD:**
   ```bash
   sudo mount /dev/sda1 /mnt/backup  # Adjust device as needed
   ```

4. **Extract application backup:**
   ```bash
   cd /mnt/backup/application
   sudo tar -xzf latest.tar.gz -C /home/satinder/
   ```

5. **Recreate virtual environment:**
   ```bash
   cd /home/satinder/camera-platform-local
   python3 -m venv venv
   venv/bin/pip install -r requirements.txt
   ```

6. **Fix permissions:**
   ```bash
   sudo chown -R satinder:satinder /home/satinder/camera-platform-local
   ```

7. **Restart services:**
   ```bash
   ./scripts/managed_start.sh start
   ```

8. **Verify:**
   ```bash
   curl http://localhost:8080/health
   curl -k https://localhost:5000/
   ```

---

### Scenario 2: Full System Crash (Same Hardware)

**Use:** Tier 1 (Full System Backup)
**Time:** ~30 minutes + OS installation
**Prerequisites:** Ubuntu Server installed (same version as backup)

#### Steps:

1. **Install Ubuntu Server:**
   - Install same Ubuntu version shown in backup manifest
   - Create user "satinder" during installation
   - Enable SSH

2. **Mount backup SSD:**
   ```bash
   sudo mkdir -p /mnt/backup
   sudo mount /dev/sda1 /mnt/backup  # Adjust device as needed
   ```

3. **Review backup manifest:**
   ```bash
   cat /mnt/backup/system/latest/manifest.txt
   ```

4. **Restore home directory:**
   ```bash
   sudo rsync -aHAXv /mnt/backup/system/latest/home/ /home/
   ```

5. **Restore system configuration:**
   ```bash
   sudo rsync -aHAXv /mnt/backup/system/latest/etc/ /etc/
   ```

6. **Restore boot partition:**
   ```bash
   sudo rsync -aHAXv /mnt/backup/system/latest/boot/ /boot/
   ```

7. **Restore locally installed software:**
   ```bash
   sudo rsync -aHAXv /mnt/backup/system/latest/usr-local/ /usr/local/
   ```

8. **Restore optional software (if exists):**
   ```bash
   if [ -d /mnt/backup/system/latest/opt ]; then
       sudo rsync -aHAXv /mnt/backup/system/latest/opt/ /opt/
   fi
   ```

9. **Restore service data:**
   ```bash
   # EMQX
   if [ -d /mnt/backup/system/latest/var-lib-emqx ]; then
       sudo rsync -aHAXv /mnt/backup/system/latest/var-lib-emqx/ /var/lib/emqx/
   fi

   # CoTURN
   if [ -d /mnt/backup/system/latest/var-lib-coturn ]; then
       sudo rsync -aHAXv /mnt/backup/system/latest/var-lib-coturn/ /var/lib/coturn/
   fi
   ```

10. **Restore package list:**
    ```bash
    sudo dpkg --set-selections < /mnt/backup/system/latest/packages.list
    sudo apt-get update
    sudo apt-get dselect-upgrade -y
    ```

11. **Recreate Python virtual environment:**
    ```bash
    cd /home/satinder/camera-platform-local
    python3 -m venv venv
    venv/bin/pip install -r requirements.txt
    ```

12. **Pull Docker images:**
    ```bash
    docker pull kurento/kurento-media-server:6.16.0
    ```

13. **Reload systemd and enable services:**
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable camera-platform.service
    sudo systemctl enable coturn.service
    sudo systemctl enable emqx.service
    ```

14. **Start services:**
    ```bash
    cd /home/satinder/camera-platform-local
    ./scripts/managed_start.sh start
    ```

15. **Restore cron jobs:**
    ```bash
    crontab /mnt/backup/system/latest/crontab.txt
    ```

16. **Verify firewall rules:**
    ```bash
    sudo ufw status
    # If needed, re-run firewall configuration:
    ./scripts/configure_firewall.sh
    ```

17. **Reboot and verify:**
    ```bash
    sudo reboot

    # After reboot:
    systemctl status camera-platform.service
    systemctl status coturn.service
    systemctl status emqx.service
    curl http://localhost:8080/health
    ```

---

### Scenario 3: New Hardware Migration

**Use:** Tier 2 (Metadata) + Tier 1 (Configs)
**Time:** ~1 hour
**Prerequisites:** New hardware with Ubuntu Server installed

#### Steps:

1. **Install Ubuntu Server:**
   - Install same version as shown in metadata backup
   - Create user "satinder"
   - Enable SSH

2. **Mount backup SSD:**
   ```bash
   sudo mkdir -p /mnt/backup
   sudo mount /dev/sda1 /mnt/backup
   ```

3. **Review system information:**
   ```bash
   cat /mnt/backup/metadata/latest/system-info.txt
   cat /mnt/backup/metadata/latest/README.md
   ```

4. **Restore package selections:**
   ```bash
   sudo dpkg --set-selections < /mnt/backup/metadata/latest/packages.list
   sudo apt-get update
   sudo apt-get dselect-upgrade -y
   ```

5. **Install Docker (if not installed by packages):**
   ```bash
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   sudo usermod -aG docker satinder
   ```

6. **Restore system configurations from Tier 1 backup:**
   ```bash
   sudo rsync -aHAXv /mnt/backup/system/latest/etc/ /etc/
   ```

7. **Restore application from Tier 1 backup:**
   ```bash
   sudo rsync -aHAXv /mnt/backup/system/latest/home/ /home/
   ```

8. **Update network configuration for new hardware:**
   ```bash
   # Edit /etc/netplan/*.yaml if needed for new network interface names
   sudo nano /etc/netplan/00-installer-config.yaml
   sudo netplan apply
   ```

9. **Recreate Python virtual environment:**
   ```bash
   cd /home/satinder/camera-platform-local
   python3 -m venv venv
   venv/bin/pip install -r requirements.txt
   ```

10. **Pull Docker images:**
    ```bash
    # Use list from metadata backup
    cat /mnt/backup/metadata/latest/docker-images.list
    docker pull kurento/kurento-media-server:6.16.0
    ```

11. **Restore cron jobs:**
    ```bash
    crontab /mnt/backup/metadata/latest/crontab.txt
    ```

12. **Configure firewall:**
    ```bash
    cd /home/satinder/camera-platform-local
    ./scripts/configure_firewall.sh
    ```

13. **Setup production hardening:**
    ```bash
    sudo ./scripts/setup_production_hardening.sh
    ```

14. **Verify SSL certificates:**
    ```bash
    ls -lh /etc/letsencrypt/live/
    # If certificates expired, run:
    ./scripts/setup_ssl_certificates.sh
    ```

15. **Start all services:**
    ```bash
    sudo systemctl start camera-platform.service
    sudo systemctl start coturn.service
    sudo systemctl start emqx.service
    ```

16. **Verify functionality:**
    ```bash
    systemctl status camera-platform.service
    curl http://localhost:8080/health
    curl -k https://localhost:5000/
    ```

---

## Verification Checklist

After any restoration, verify these components:

### Application Services
- [ ] Livestreaming API responds: `curl http://localhost:8080/health`
- [ ] Dashboard accessible: `curl -k https://localhost:5000/`
- [ ] WebSocket signaling server running: `ss -tlnp | grep 8765`

### Infrastructure Services
- [ ] CoTURN running: `systemctl status coturn.service`
- [ ] EMQX running: `systemctl status emqx.service`
- [ ] Kurento container: `docker ps | grep kms-production`

### Database
- [ ] Camera events database: `ls -lh /home/satinder/camera-platform-local/data/camera_events.db`
- [ ] Camera control databases: `find /home/satinder/camera-platform-local/camera_files -name master_ctrl.db`

### Automation
- [ ] Cron jobs installed: `crontab -l`
- [ ] Systemd service enabled: `systemctl is-enabled camera-platform.service`
- [ ] Health checks running: Check logs in `/home/satinder/camera-platform-local/logs/health_check.log`

### Network Configuration
- [ ] Firewall active: `sudo ufw status`
- [ ] Ports open: `sudo ufw status numbered`
- [ ] SSL certificates valid: `sudo certbot certificates`

### SSL/TLS
- [ ] SSL certificates present: `ls /etc/letsencrypt/live/`
- [ ] ssl-certs group configured: `groups satinder | grep ssl-certs`
- [ ] Private key permissions: `ls -l /etc/letsencrypt/live/*/privkey.pem`

---

## Troubleshooting

### Issue: Permission Denied Errors

**Symptom:** Services fail to start with permission errors

**Fix:**
```bash
# Fix application directory ownership
sudo chown -R satinder:satinder /home/satinder/camera-platform-local

# Fix SSL certificate group permissions
sudo ./scripts/setup_ssl_certificates.sh
```

### Issue: Python Module Import Errors

**Symptom:** Services fail with "ModuleNotFoundError"

**Fix:**
```bash
cd /home/satinder/camera-platform-local
rm -rf venv
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt
```

### Issue: Docker Container Fails to Start

**Symptom:** Kurento container not running

**Fix:**
```bash
# Check if container exists
docker ps -a | grep kms-production

# Remove old container
docker stop kms-production
docker rm kms-production

# Restart using script
cd /home/satinder/camera-platform-local
./livestreaming/scripts/start_kurento.sh
```

### Issue: Database Locked Errors

**Symptom:** "database is locked" errors in logs

**Fix:**
```bash
# Stop all services
./scripts/managed_start.sh stop

# Wait a few seconds
sleep 5

# Restart services
./scripts/managed_start.sh start
```

### Issue: Firewall Blocking Connections

**Symptom:** Can't connect to services from external network

**Fix:**
```bash
# Check firewall status
sudo ufw status numbered

# Reconfigure firewall
./scripts/configure_firewall.sh

# Or manually allow port
sudo ufw allow 8080/tcp
```

### Issue: Cron Jobs Not Running

**Symptom:** No health checks or scheduled restarts happening

**Fix:**
```bash
# Check if crontab is installed
crontab -l

# If empty, restore from backup
crontab /mnt/backup/metadata/latest/crontab.txt

# Verify
crontab -l
```

### Issue: Systemd Service Won't Start

**Symptom:** `systemctl start camera-platform` fails

**Fix:**
```bash
# Check service status and logs
sudo systemctl status camera-platform.service
sudo journalctl -u camera-platform.service -n 50

# Reload systemd if service file was restored
sudo systemctl daemon-reload

# Verify service file exists
ls -l /etc/systemd/system/camera-platform.service

# Re-run production hardening if needed
sudo ./scripts/setup_production_hardening.sh
```

---

## Backup Integrity Verification

Before relying on a backup for restoration, verify its integrity:

### Verify Tier 1 (Full System Backup)

```bash
cd /mnt/backup/system/latest

# Check manifest
cat manifest.txt

# Verify checksums (this will take several minutes)
sha256sum -c checksums.sha256 2>&1 | tee verify.log

# Check for failures
grep -i "failed" verify.log
```

### Verify Tier 2 (Metadata Backup)

```bash
cd /mnt/backup/metadata/latest

# Review README
cat README.md

# Check package count
wc -l packages.list

# Verify systemd services list
wc -l systemd-services.list
```

### Verify Tier 3 (Application Backup)

```bash
cd /mnt/backup/application

# List available backups
ls -lh *.tar.gz

# Test tarball integrity
tar -tzf latest.tar.gz > /dev/null && echo "OK" || echo "CORRUPTED"

# View contents without extracting
tar -tzf latest.tar.gz | head -20
```

---

## Testing Restoration (Recommended)

Before you need to restore in an emergency, test the restoration process:

### Option 1: Test in Virtual Machine

1. Create Ubuntu Server VM (same version)
2. Attach backup SSD to VM
3. Follow restoration steps for your scenario
4. Verify all services work

### Option 2: Test on Spare Hardware

1. Install Ubuntu on spare computer
2. Connect backup SSD
3. Follow restoration steps
4. Verify system functionality

### Option 3: Partial Test (Non-Destructive)

1. Mount backup SSD
2. Extract application backup to temporary location:
   ```bash
   mkdir /tmp/restore-test
   tar -xzf /mnt/backup/application/latest.tar.gz -C /tmp/restore-test
   ```
3. Verify files are intact:
   ```bash
   ls -lah /tmp/restore-test/camera-platform-local
   cat /tmp/restore-test/camera-platform-local/BACKUP_MANIFEST.txt
   ```
4. Cleanup:
   ```bash
   rm -rf /tmp/restore-test
   ```

---

## Backup Schedule Recommendations

### Automated Backups (via cron)

Add to crontab:

```bash
# Full system backup: Weekly on Sunday 2 AM
0 2 * * 0 /home/satinder/camera-platform-local/scripts/backup_system.sh /mnt/backup

# Metadata backup: Daily at 1 AM
0 1 * * * /home/satinder/camera-platform-local/scripts/backup_metadata.sh /mnt/backup

# Application backup: Daily at 4 AM
0 4 * * * /home/satinder/camera-platform-local/scripts/backup_application.sh /mnt/backup
```

### Manual Backups

Perform manual backups before:
- Major system upgrades
- Configuration changes
- Software updates
- Hardware modifications

---

## Additional Resources

- **Deployment Guide:** `docs/DEPLOYMENT_GUIDE.md`
- **Automated Deployment:** `docs/AUTOMATED_DEPLOYMENT.md`
- **Backup Scripts:** `scripts/backup_*.sh`
- **Production Hardening:** `scripts/setup_production_hardening.sh`
- **SSL Configuration:** `scripts/setup_ssl_certificates.sh`
- **Firewall Setup:** `scripts/configure_firewall.sh`

---

## Support

If restoration fails or you encounter issues not covered in this guide:

1. Check system logs: `sudo journalctl -xe`
2. Check application logs: `tail -f /home/satinder/camera-platform-local/logs/*.log`
3. Review backup manifest files for additional information
4. Ensure backup SSD is properly mounted and accessible

---

**Last Updated:** December 29, 2025
**Backup System Version:** 1.0
