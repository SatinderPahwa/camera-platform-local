# Server Reference Guide

**Advanced server configuration, performance tuning, and production hardening**

> **Note:** For basic server setup, see [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) first.

This guide covers advanced topics for production deployments.

---

## Table of Contents

- [Performance Tuning](#performance-tuning)
- [Monitoring and Alerting](#monitoring-and-alerting)
- [Backup Strategies](#backup-strategies)
- [High Availability](#high-availability)
- [Security Hardening](#security-hardening)
- [Scaling Considerations](#scaling-considerations)
- [Advanced Configuration](#advanced-configuration)

---

## Performance Tuning

### System Limits

Increase file descriptors and connection limits for high-traffic deployments:

```bash
# Edit limits
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
net.ipv4.ip_local_port_range = 1024 65535

# Apply changes
sudo sysctl -p

# Reboot to ensure limits take effect
sudo reboot
```

### EMQX Performance Tuning

```bash
# Edit EMQX VM args
sudo nano /etc/emqx/vm.args

# Increase process limit (default: 2097152)
+P 4194304

# Increase scheduler threads (match CPU cores)
+S 8:8

# Enable async threads
+A 64

# Restart EMQX
sudo systemctl restart emqx
```

**EMQX Configuration Tuning:**

```bash
sudo nano /etc/emqx/emqx.conf

# Increase connection limits
listeners.ssl.default {
  max_connections = 1024000

  # Connection rate limiting
  max_conn_rate = 1000
}

# Tune session settings
mqtt {
  max_packet_size = 10MB
  max_clientid_len = 256
  max_topic_levels = 128

  # Keep-alive multiplier
  keepalive_backoff = 0.75
}
```

### Kurento Performance

```bash
# Edit Kurento config
sudo nano /etc/kurento/kurento.conf.json

# Increase worker threads
{
  "mediaServer": {
    "resources": {
      "garbageCollectorPeriod": 240,
      "disableRequestCache": false
    },
    "net": {
      "websocket": {
        "port": 8888,
        "path": "kurento",
        "threads": 10
      }
    }
  }
}

# Restart Kurento
sudo systemctl restart kurento-media-server
```

### Nginx Optimization

```bash
sudo nano /etc/nginx/nginx.conf

# Worker processes (match CPU cores)
worker_processes 8;
worker_connections 4096;

# Enable gzip
gzip on;
gzip_vary on;
gzip_proxied any;
gzip_types text/plain text/css text/xml text/javascript
           application/json application/javascript application/xml+rss;

# Connection tuning
keepalive_timeout 65;
keepalive_requests 100;

# Client body limits
client_max_body_size 100M;
client_body_buffer_size 128k;

# Restart Nginx
sudo systemctl restart nginx
```

---

## Monitoring and Alerting

### System Monitoring

**Install monitoring tools:**

```bash
# Install monitoring utilities
sudo apt install -y htop iotop nethogs sysstat

# Enable sysstat
sudo systemctl enable sysstat
sudo systemctl start sysstat
```

**Monitor services:**

```bash
# Real-time monitoring
htop                           # CPU/Memory
iotop                          # Disk I/O
nethogs                        # Network per process
sar -u 1 10                    # CPU usage
sar -r 1 10                    # Memory usage
sar -n DEV 1 10                # Network usage
```

### EMQX Monitoring

```bash
# Client statistics
emqx ctl clients list
emqx ctl clients show <client_id>

# Topic subscriptions
emqx ctl subscriptions list
emqx ctl subscriptions show <client_id>

# Node statistics
emqx ctl broker stats

# Metrics
emqx ctl metrics

# Alarms
emqx ctl alarms
```

**EMQX Dashboard Metrics:**
- Open: `http://server-ip:18083`
- Navigate to: **Dashboard** → **Metrics**
- Monitor: Connections, Messages/sec, Subscriptions

### Log Monitoring

**Centralized logging:**

```bash
# Install logrotate
sudo apt install -y logrotate

# Configure platform logs rotation
sudo nano /etc/logrotate.d/camera-platform

# Add:
/home/deploy/camera-platform-local/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    create 0644 deploy deploy
    sharedscripts
    postrotate
        /home/deploy/camera-platform-local/scripts/managed_start.sh restart > /dev/null
    endscript
}
```

**Real-time monitoring:**

```bash
# Monitor all platform logs
tail -f ~/camera-platform-local/logs/*.log

# Monitor EMQX
sudo journalctl -u emqx -f

# Monitor Kurento
sudo journalctl -u kurento-media-server -f

# Monitor coturn
sudo tail -f /var/log/turnserver.log

# Search for errors across all logs
sudo journalctl --since "1 hour ago" | grep -i error
```

### Alerting Setup

**Email alerts on service failure:**

```bash
# Install mail utilities
sudo apt install -y mailutils

# Create alert script
sudo nano /usr/local/bin/service-alert.sh
```

```bash
#!/bin/bash
SERVICE=$1
STATUS=$(systemctl is-active $SERVICE)

if [ "$STATUS" != "active" ]; then
    echo "$SERVICE is $STATUS on $(hostname)" | \
    mail -s "ALERT: $SERVICE DOWN" admin@example.com
fi
```

```bash
# Make executable
sudo chmod +x /usr/local/bin/service-alert.sh

# Add to cron (check every 5 minutes)
crontab -e

# Add:
*/5 * * * * /usr/local/bin/service-alert.sh emqx
*/5 * * * * /usr/local/bin/service-alert.sh kurento-media-server
*/5 * * * * /usr/local/bin/service-alert.sh coturn
```

---

## Backup Strategies

### Automated Backup Script

```bash
# Create backup script
nano ~/backup-camera-platform.sh
```

```bash
#!/bin/bash
# Camera Platform Backup Script

BACKUP_DIR=/backups/camera-platform
DATE=$(date +%Y%m%d-%H%M%S)
RETENTION_DAYS=30

mkdir -p $BACKUP_DIR

echo "Starting backup at $(date)"

# Platform files
tar czf $BACKUP_DIR/platform-$DATE.tar.gz \
    ~/camera-platform-local \
    --exclude=venv \
    --exclude=logs \
    --exclude='*.pyc' \
    --exclude=__pycache__

# Database
cp ~/camera-platform-local/data/camera_events.db \
   $BACKUP_DIR/database-$DATE.db

# EMQX configuration
sudo tar czf $BACKUP_DIR/emqx-config-$DATE.tar.gz /etc/emqx

# Kurento configuration
sudo tar czf $BACKUP_DIR/kurento-config-$DATE.tar.gz /etc/kurento

# coturn configuration
sudo cp /etc/turnserver.conf $BACKUP_DIR/turnserver-$DATE.conf

# Nginx configuration
sudo tar czf $BACKUP_DIR/nginx-config-$DATE.tar.gz /etc/nginx

# SSL certificates
sudo tar czf $BACKUP_DIR/ssl-certs-$DATE.tar.gz /etc/letsencrypt

# Delete old backups
find $BACKUP_DIR -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete
find $BACKUP_DIR -name "*.db" -mtime +$RETENTION_DAYS -delete
find $BACKUP_DIR -name "*.conf" -mtime +$RETENTION_DAYS -delete

echo "Backup completed at $(date)"
echo "Backup size: $(du -sh $BACKUP_DIR | cut -f1)"
```

```bash
# Make executable
chmod +x ~/backup-camera-platform.sh

# Test backup
./backup-camera-platform.sh

# Schedule daily backup (3 AM)
crontab -e

# Add:
0 3 * * * /home/deploy/backup-camera-platform.sh >> /var/log/camera-backup.log 2>&1
```

### Offsite Backup

**Sync to remote server:**

```bash
# Install rclone for cloud backup
curl https://rclone.org/install.sh | sudo bash

# Configure rclone (supports S3, Google Drive, etc.)
rclone config

# Add to backup script:
rclone sync /backups/camera-platform remote:camera-backups
```

---

## High Availability

### EMQX Cluster

For critical deployments, run EMQX in cluster mode:

```bash
# On each node
sudo nano /etc/emqx/emqx.conf

# Configure cluster
cluster {
  name = camera_cluster
  discovery_strategy = static

  static {
    seeds = [
      "emqx1@192.168.1.101",
      "emqx2@192.168.1.102",
      "emqx3@192.168.1.103"
    ]
  }
}

# Join cluster
emqx ctl cluster join emqx@192.168.1.101
```

### Database Replication

**Migrate to PostgreSQL for HA:**

```python
# Update config/settings.py
DATABASE_TYPE = 'postgresql'
DATABASE_HOST = 'postgres-server'
DATABASE_PORT = 5432
DATABASE_NAME = 'camera_platform'
```

### Load Balancing

**Nginx upstream for dashboard:**

```nginx
upstream dashboard_backend {
    least_conn;
    server 192.168.1.101:5000;
    server 192.168.1.102:5000;
    server 192.168.1.103:5000;
}

server {
    location / {
        proxy_pass http://dashboard_backend;
    }
}
```

---

## Security Hardening

### SSH Hardening

```bash
sudo nano /etc/ssh/sshd_config

# Disable root login
PermitRootLogin no

# Disable password authentication
PasswordAuthentication no

# Use SSH keys only
PubkeyAuthentication yes

# Change port (optional)
Port 2222

# Restart SSH
sudo systemctl restart sshd
```

### Firewall Rules - Production

```bash
# Default deny
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH (adjust port if changed)
sudo ufw allow 2222/tcp

# Allow HTTPS only (no HTTP)
sudo ufw allow 443/tcp

# EMQX - restrict to local network
sudo ufw allow from 192.168.0.0/16 to any port 8883 proto tcp

# TURN - public access required
sudo ufw allow 3478/tcp
sudo ufw allow 3478/udp
sudo ufw allow 5349/tcp
sudo ufw allow 5349/udp
sudo ufw allow 50000:60000/udp

# Enable
sudo ufw enable
```

### Fail2ban Protection

```bash
# Install fail2ban
sudo apt install -y fail2ban

# Configure
sudo nano /etc/fail2ban/jail.local
```

```ini
[sshd]
enabled = true
port = 2222
maxretry = 3
bantime = 3600

[nginx-http-auth]
enabled = true
maxretry = 3
bantime = 3600
```

```bash
# Start fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### EMQX Security

```bash
# Change admin password
emqx ctl admins passwd admin <strong-password>

# Enable TLS client verification
sudo nano /etc/emqx/emqx.conf

listeners.ssl.default {
  ssl_options {
    verify = verify_peer
    fail_if_no_peer_cert = true
  }
}
```

---

## Scaling Considerations

### Camera Capacity

**Single server capacity:**
- **10 cameras:** No optimization needed
- **50 cameras:** Tune system limits
- **100+ cameras:** Consider EMQX cluster

**Bottlenecks:**
1. **EMQX:** CPU (message processing)
2. **Kurento:** CPU + Bandwidth (video streams)
3. **Storage:** Disk I/O (recordings)

### Storage Scaling

```bash
# Monitor disk usage
df -h
du -sh ~/camera-platform-local/data/uploads

# Automated cleanup of old recordings (>30 days)
find ~/camera-platform-local/data/uploads \
  -name "*.zip" -mtime +30 -delete

# Add to cron (weekly)
0 2 * * 0 find /home/deploy/camera-platform-local/data/uploads -name "*.zip" -mtime +30 -delete
```

### Database Optimization

```bash
# Vacuum SQLite database monthly
sqlite3 ~/camera-platform-local/data/camera_events.db "VACUUM;"

# Archive old events (>90 days)
sqlite3 ~/camera-platform-local/data/camera_events.db <<EOF
DELETE FROM activity_events WHERE start_timestamp < $(date -d '90 days ago' +%s);
DELETE FROM status_events WHERE timestamp < $(date -d '90 days ago' +%s);
VACUUM;
EOF
```

---

## Advanced Configuration

### EMQX Authentication Database

Use external database for authentication:

```bash
sudo nano /etc/emqx/emqx.conf

authentication = [
  {
    mechanism = password_based
    backend = built_in_database
    user_id_type = clientid
  }
]
```

### Custom Kurento Modules

```bash
# Install development tools
sudo apt install -y kurento-media-server-dev

# Build custom modules
# See: https://doc-kurento.readthedocs.io/
```

### Nginx Rate Limiting

```nginx
# Limit requests to dashboard
limit_req_zone $binary_remote_addr zone=dashboard:10m rate=10r/s;

server {
    location / {
        limit_req zone=dashboard burst=20;
        proxy_pass http://localhost:5000;
    }
}
```

---

## Production Checklist

Before going live:

- [ ] System limits increased
- [ ] Firewall configured (minimal ports)
- [ ] Fail2ban enabled
- [ ] SSH hardened (keys only, non-standard port)
- [ ] Strong passwords everywhere (EMQX, dashboard, TURN)
- [ ] Automated backups configured and tested
- [ ] Monitoring/alerting set up
- [ ] Log rotation configured
- [ ] SSL certificates auto-renewing
- [ ] TURN server tested from external network
- [ ] Performance tuning applied
- [ ] Documentation updated with server details
- [ ] Disaster recovery plan documented

---

## Further Reading

- **EMQX Documentation:** https://www.emqx.io/docs/
- **Kurento Documentation:** https://doc-kurento.readthedocs.io/
- **coturn Wiki:** https://github.com/coturn/coturn/wiki
- **Nginx Optimization:** https://www.nginx.com/blog/tuning-nginx/

---

**Questions?** Open an issue on GitHub with your configuration details.
