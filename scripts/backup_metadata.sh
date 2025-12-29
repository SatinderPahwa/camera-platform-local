#!/bin/bash
#
# METADATA BACKUP SCRIPT
# Exports system configuration metadata for disaster recovery
#
# Usage: ./backup_metadata.sh /mnt/backup
#
# This lightweight script exports package lists, cron jobs, systemd services,
# and other configuration metadata needed to recreate the system from scratch.
#

set -e

# Check backup destination argument
if [ -z "$1" ]; then
    echo "Usage: $0 /mnt/backup"
    echo "Error: Backup destination not specified"
    exit 1
fi

BACKUP_ROOT="$1"
METADATA_DIR="$BACKUP_ROOT/metadata"
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
OUTPUT_DIR="$METADATA_DIR/$TIMESTAMP"

echo "======================================================================"
echo "SYSTEM METADATA BACKUP"
echo "======================================================================"
echo "Started: $(date)"
echo "Destination: $OUTPUT_DIR"
echo ""

# Create metadata directory
mkdir -p "$OUTPUT_DIR"

# 1. INSTALLED PACKAGES
echo "📦 Exporting installed packages list..."
dpkg --get-selections > "$OUTPUT_DIR/packages.list"
dpkg -l > "$OUTPUT_DIR/packages_detailed.txt"
echo "✅ Packages: $(wc -l < $OUTPUT_DIR/packages.list) packages saved"

# 2. APT SOURCES
echo ""
echo "📦 Exporting APT sources..."
if [ -d "/etc/apt/sources.list.d" ]; then
    mkdir -p "$OUTPUT_DIR/apt-sources"
    cp /etc/apt/sources.list "$OUTPUT_DIR/apt-sources/" 2>/dev/null || true
    cp /etc/apt/sources.list.d/* "$OUTPUT_DIR/apt-sources/" 2>/dev/null || true
    echo "✅ APT sources saved"
fi

# 3. USER CRON JOBS
echo ""
echo "⏰ Exporting cron jobs..."
crontab -l > "$OUTPUT_DIR/crontab.txt" 2>/dev/null || echo "No user crontab" > "$OUTPUT_DIR/crontab.txt"
if [ -d "/etc/cron.d" ]; then
    mkdir -p "$OUTPUT_DIR/cron.d"
    cp /etc/cron.d/* "$OUTPUT_DIR/cron.d/" 2>/dev/null || true
fi
echo "✅ Cron jobs saved"

# 4. SYSTEMD SERVICES
echo ""
echo "🔧 Exporting systemd services..."
systemctl list-unit-files --type=service > "$OUTPUT_DIR/systemd-services.list"
systemctl list-units --type=service --state=running --no-pager > "$OUTPUT_DIR/systemd-services-running.txt"
if [ -d "/etc/systemd/system" ]; then
    mkdir -p "$OUTPUT_DIR/systemd-custom"
    cp -r /etc/systemd/system/*.service "$OUTPUT_DIR/systemd-custom/" 2>/dev/null || true
fi
echo "✅ Systemd services saved"

# 5. NETWORK CONFIGURATION
echo ""
echo "🌐 Exporting network configuration..."
ip addr show > "$OUTPUT_DIR/network-interfaces.txt"
ip route show > "$OUTPUT_DIR/network-routes.txt"
if [ -f "/etc/netplan"/*.yaml ]; then
    mkdir -p "$OUTPUT_DIR/netplan"
    cp /etc/netplan/*.yaml "$OUTPUT_DIR/netplan/" 2>/dev/null || true
fi
if [ -f "/etc/network/interfaces" ]; then
    cp /etc/network/interfaces "$OUTPUT_DIR/network-interfaces" 2>/dev/null || true
fi
echo "✅ Network config saved"

# 6. FIREWALL RULES
echo ""
echo "🔒 Exporting firewall rules..."
if command -v ufw &> /dev/null; then
    ufw status verbose > "$OUTPUT_DIR/firewall-ufw.txt" 2>/dev/null || true
fi
if command -v iptables &> /dev/null; then
    sudo iptables -L -n -v > "$OUTPUT_DIR/firewall-iptables.txt" 2>/dev/null || true
fi
echo "✅ Firewall rules saved"

# 7. DOCKER CONFIGURATION
echo ""
echo "🐳 Exporting Docker configuration..."
if command -v docker &> /dev/null; then
    docker images --format "{{.Repository}}:{{.Tag}}" > "$OUTPUT_DIR/docker-images.list" 2>/dev/null || true
    docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" > "$OUTPUT_DIR/docker-containers.txt" 2>/dev/null || true
    echo "✅ Docker info saved"
else
    echo "⚠️  Docker not installed"
fi

# 8. PYTHON PACKAGES
echo ""
echo "🐍 Exporting Python packages..."
if [ -f "/home/satinder/camera-platform-local/venv/bin/pip" ]; then
    /home/satinder/camera-platform-local/venv/bin/pip freeze > "$OUTPUT_DIR/python-packages.txt" 2>/dev/null || true
    echo "✅ Python packages saved"
fi

# 9. SYSTEM INFORMATION
echo ""
echo "💻 Exporting system information..."
cat > "$OUTPUT_DIR/system-info.txt" <<EOF
SYSTEM INFORMATION
==================
Hostname: $(hostname)
Kernel: $(uname -r)
OS: $(cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2)
Architecture: $(uname -m)
Uptime: $(uptime)

CPU INFO
--------
$(lscpu | grep -E 'Model name|CPU\(s\)|Thread|Core')

MEMORY INFO
-----------
$(free -h)

DISK LAYOUT
-----------
$(lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE)

DISK USAGE
----------
$(df -h)

MOUNTED FILESYSTEMS
-------------------
$(mount | grep -E '^/dev')
EOF
echo "✅ System info saved"

# 10. SSL CERTIFICATES INFO
echo ""
echo "🔐 Exporting SSL certificates info..."
if [ -d "/etc/letsencrypt" ]; then
    find /etc/letsencrypt -name "cert.pem" -exec sh -c 'echo "=== {} ===" && openssl x509 -in {} -noout -dates -subject' \; > "$OUTPUT_DIR/ssl-certificates-info.txt" 2>/dev/null || true
    echo "✅ SSL cert info saved"
fi

# 11. RUNNING PROCESSES
echo ""
echo "🔄 Exporting running processes..."
ps auxf > "$OUTPUT_DIR/processes.txt"
echo "✅ Process list saved"

# 12. INSTALLED KERNEL MODULES
echo ""
echo "🔌 Exporting loaded kernel modules..."
lsmod > "$OUTPUT_DIR/kernel-modules.txt"
echo "✅ Kernel modules saved"

# CREATE README
cat > "$OUTPUT_DIR/README.md" <<EOF
# System Metadata Backup

**Backup Date:** $TIMESTAMP
**Hostname:** $(hostname)
**OS:** $(cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2)

## Contents

This metadata backup contains configuration files and lists needed to recreate
the camera platform server from scratch on new hardware.

### Package Information
- \`packages.list\` - List of installed packages (dpkg format)
- \`packages_detailed.txt\` - Detailed package information
- \`apt-sources/\` - APT repository sources
- \`python-packages.txt\` - Python packages from venv

### System Configuration
- \`crontab.txt\` - User cron jobs
- \`cron.d/\` - System cron jobs
- \`systemd-services.list\` - All systemd services
- \`systemd-services-running.txt\` - Currently running services
- \`systemd-custom/\` - Custom systemd service files

### Network Configuration
- \`network-interfaces.txt\` - Network interfaces
- \`network-routes.txt\` - Network routes
- \`netplan/\` - Netplan configuration (if used)
- \`firewall-*.txt\` - Firewall rules

### Application Configuration
- \`docker-images.list\` - Docker images to pull
- \`docker-containers.txt\` - Container configurations
- \`ssl-certificates-info.txt\` - SSL certificate information

### System Information
- \`system-info.txt\` - Hardware and system details
- \`processes.txt\` - Running processes at backup time
- \`kernel-modules.txt\` - Loaded kernel modules

## Restoration Using This Backup

### Option 1: Quick Application Restore
If the OS is intact but application is corrupted, use the full system backup instead.

### Option 2: Fresh Installation (New Hardware)

1. **Install Ubuntu Server** (same version as backed up)

2. **Restore Package List:**
   \`\`\`bash
   sudo dpkg --set-selections < packages.list
   sudo apt-get dselect-upgrade
   \`\`\`

3. **Restore System Configurations:**
   - Copy files from full system backup \`/etc\` directory
   - Restore custom systemd services
   - Restore firewall rules

4. **Restore Application:**
   - Clone Git repository or restore from full backup
   - Restore databases
   - Restore SSL certificates
   - Set up cron jobs

5. **Verify Services:**
   - Check all systemd services are running
   - Verify Docker containers
   - Test application functionality

## Notes

- This metadata backup should be used in conjunction with the full system backup
- For fastest restore, use the full system backup (rsync)
- This metadata backup is useful for:
  - Setting up on completely new hardware
  - Understanding what was installed/configured
  - Auditing system configuration

## Full System Backup

The complete files are in the \`system/\` directory of the backup drive.
Use \`backup_system.sh\` to perform a full backup.

EOF

echo ""
echo "======================================================================"
echo "METADATA BACKUP COMPLETE"
echo "======================================================================"
echo "Backup location: $OUTPUT_DIR"
echo "Files saved:"
ls -lh "$OUTPUT_DIR" | tail -n +2 | awk '{printf "  %-40s %s\n", $9, $5}'
echo ""
echo "Total size: $(du -sh $OUTPUT_DIR | awk '{print $1}')"
echo "Completed: $(date)"
echo ""

# Update latest symlink
rm -f "$METADATA_DIR/latest"
ln -s "$OUTPUT_DIR" "$METADATA_DIR/latest"
echo "✅ Latest metadata backup: $(readlink $METADATA_DIR/latest)"
echo ""

exit 0
