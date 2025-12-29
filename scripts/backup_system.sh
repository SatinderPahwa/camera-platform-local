#!/bin/bash
#
# FULL SYSTEM BACKUP SCRIPT
# Backs up critical system directories to external SSD (excluding recordings)
#
# Usage: sudo ./backup_system.sh /mnt/backup
#
# This script performs a complete backup of the server excluding the recordings
# partition, using rsync with hard links for space-efficient incremental backups.
#

set -e

# Check if running as root
if [ "$(id -u)" -ne 0 ]; then
    echo "❌ Error: This script must be run as root (use sudo)"
    exit 1
fi

# Check backup destination argument
if [ -z "$1" ]; then
    echo "Usage: sudo $0 /mnt/backup"
    echo "Error: Backup destination not specified"
    exit 1
fi

BACKUP_ROOT="$1"
BACKUP_DATE=$(date +%Y-%m-%d_%H-%M-%S)
BACKUP_DIR="$BACKUP_ROOT/system/$BACKUP_DATE"
LATEST_LINK="$BACKUP_ROOT/system/latest"
LOG_FILE="$BACKUP_ROOT/system/backup_$BACKUP_DATE.log"

# Create backup directory structure first (before logging)
mkdir -p "$BACKUP_DIR"
mkdir -p "$BACKUP_ROOT/metadata"
mkdir -p "$BACKUP_ROOT/application"

echo "======================================================================" | tee -a "$LOG_FILE"
echo "CAMERA PLATFORM SERVER BACKUP" | tee -a "$LOG_FILE"
echo "======================================================================" | tee -a "$LOG_FILE"
echo "Started: $(date)" | tee -a "$LOG_FILE"
echo "Destination: $BACKUP_DIR" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Rsync options explained:
# -a (archive) = preserve permissions, times, symlinks, etc.
# -H = preserve hard links
# -A = preserve ACLs
# -X = preserve extended attributes
# -v = verbose
# --delete = delete files in backup that no longer exist in source
# --link-dest = use hard links from previous backup for unchanged files
# --exclude = skip specified patterns

# Find previous backup for hard linking
PREVIOUS_BACKUP=""
if [ -L "$LATEST_LINK" ] && [ -d "$LATEST_LINK" ]; then
    PREVIOUS_BACKUP="--link-dest=$LATEST_LINK"
    echo "📦 Using incremental backup (hard links from: $(readlink $LATEST_LINK))" | tee -a "$LOG_FILE"
else
    echo "📦 Performing full backup (no previous backup found)" | tee -a "$LOG_FILE"
fi

# Backup function
backup_directory() {
    local SOURCE="$1"
    local DEST="$2"
    local DESCRIPTION="$3"

    echo "" | tee -a "$LOG_FILE"
    echo "Backing up: $DESCRIPTION" | tee -a "$LOG_FILE"
    echo "  From: $SOURCE" | tee -a "$LOG_FILE"
    echo "  To: $DEST" | tee -a "$LOG_FILE"

    rsync -aHAXv $PREVIOUS_BACKUP \
        "$SOURCE/" "$DEST/" \
        2>&1 | tee -a "$LOG_FILE" | grep -E "^(sending|sent|total)"

    if [ ${PIPESTATUS[0]} -eq 0 ]; then
        echo "  ✅ Success" | tee -a "$LOG_FILE"
    else
        echo "  ❌ Failed" | tee -a "$LOG_FILE"
        return 1
    fi
}

# BACKUP CRITICAL DIRECTORIES

# 1. Home directory (application code, databases, scripts)
backup_directory \
    "/home/satinder" \
    "$BACKUP_DIR/home" \
    "Home directory (application code & data)"

# 2. System configuration
backup_directory \
    "/etc" \
    "$BACKUP_DIR/etc" \
    "System configuration (/etc)"

# 3. Locally installed software
if [ -d "/usr/local" ]; then
    # Exclude cache and temporary files
    rsync -aHAXv $PREVIOUS_BACKUP \
        --exclude='cache/' \
        --exclude='tmp/' \
        "/usr/local/" "$BACKUP_DIR/usr-local/" \
        2>&1 | tee -a "$LOG_FILE" | grep -E "^(sending|sent|total)"
    echo "  ✅ Backed up /usr/local" | tee -a "$LOG_FILE"
fi

# 4. Optional software packages
if [ -d "/opt" ] && [ "$(du -s /opt 2>/dev/null | awk '{print $1}')" -gt 100 ]; then
    backup_directory \
        "/opt" \
        "$BACKUP_DIR/opt" \
        "Optional software (/opt)"
fi

# 5. EMQX data (if exists)
if [ -d "/var/lib/emqx" ]; then
    backup_directory \
        "/var/lib/emqx" \
        "$BACKUP_DIR/var-lib-emqx" \
        "EMQX data"
fi

# 6. CoTURN data (if exists)
if [ -d "/var/lib/coturn" ]; then
    backup_directory \
        "/var/lib/coturn" \
        "$BACKUP_DIR/var-lib-coturn" \
        "CoTURN data"
fi

# 7. Boot partition
backup_directory \
    "/boot" \
    "$BACKUP_DIR/boot" \
    "Boot partition"

# 8. EFI partition (if exists)
if [ -d "/boot/efi" ]; then
    backup_directory \
        "/boot/efi" \
        "$BACKUP_DIR/boot-efi" \
        "EFI boot partition"
fi

# CREATE BACKUP MANIFEST
echo "" | tee -a "$LOG_FILE"
echo "Creating backup manifest..." | tee -a "$LOG_FILE"

cat > "$BACKUP_DIR/manifest.txt" <<EOF
CAMERA PLATFORM SERVER BACKUP
==============================
Backup Date: $BACKUP_DATE
Hostname: $(hostname)
Kernel: $(uname -r)
OS: $(cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2)

DISK LAYOUT
-----------
$(lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE)

BACKUP CONTENTS
---------------
$(du -sh $BACKUP_DIR/* 2>/dev/null)

TOTAL BACKUP SIZE
-----------------
$(du -sh $BACKUP_DIR)

PACKAGE COUNT
-------------
Installed packages: $(dpkg -l | grep -c ^ii)

DOCKER IMAGES
-------------
$(docker images --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}" 2>/dev/null || echo "Docker not available")

SYSTEMD SERVICES (Active)
--------------------------
$(systemctl list-units --type=service --state=running --no-pager | head -20)
EOF

echo "✅ Manifest created: $BACKUP_DIR/manifest.txt" | tee -a "$LOG_FILE"

# EXPORT PACKAGE LIST (for system recreation)
echo "" | tee -a "$LOG_FILE"
echo "Exporting package list..." | tee -a "$LOG_FILE"
dpkg --get-selections > "$BACKUP_DIR/packages.list"
echo "✅ Package list saved: $BACKUP_DIR/packages.list" | tee -a "$LOG_FILE"

# UPDATE LATEST SYMLINK
echo "" | tee -a "$LOG_FILE"
echo "Updating 'latest' symlink..." | tee -a "$LOG_FILE"
rm -f "$LATEST_LINK"
ln -s "$BACKUP_DIR" "$LATEST_LINK"
echo "✅ Latest backup: $(readlink $LATEST_LINK)" | tee -a "$LOG_FILE"

# CALCULATE CHECKSUMS (for verification)
echo "" | tee -a "$LOG_FILE"
echo "Calculating checksums (this may take a while)..." | tee -a "$LOG_FILE"
find "$BACKUP_DIR" -type f -exec sha256sum {} \; > "$BACKUP_DIR/checksums.sha256" 2>&1 | tee -a "$LOG_FILE"
echo "✅ Checksums saved: $BACKUP_DIR/checksums.sha256" | tee -a "$LOG_FILE"

# BACKUP SUMMARY
echo "" | tee -a "$LOG_FILE"
echo "======================================================================" | tee -a "$LOG_FILE"
echo "BACKUP COMPLETE" | tee -a "$LOG_FILE"
echo "======================================================================" | tee -a "$LOG_FILE"
echo "Backup location: $BACKUP_DIR" | tee -a "$LOG_FILE"
echo "Backup size: $(du -sh $BACKUP_DIR | awk '{print $1}')" | tee -a "$LOG_FILE"
echo "Log file: $LOG_FILE" | tee -a "$LOG_FILE"
echo "Completed: $(date)" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Show disk usage on backup drive
echo "Backup drive usage:" | tee -a "$LOG_FILE"
df -h "$BACKUP_ROOT" | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo "✅ Backup completed successfully!" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "To verify backup integrity, run:" | tee -a "$LOG_FILE"
echo "  cd $BACKUP_DIR && sha256sum -c checksums.sha256" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

exit 0
