#!/bin/bash
#
# APPLICATION-ONLY BACKUP SCRIPT
# Quick backup of camera platform application for fast recovery
#
# Usage: ./backup_application.sh /mnt/backup
#
# This script creates a compressed tarball of the application directory,
# databases, SSL certificates, and configuration files for quick restoration.
#

set -e

# Check backup destination argument
if [ -z "$1" ]; then
    echo "Usage: $0 /mnt/backup"
    echo "Error: Backup destination not specified"
    exit 1
fi

BACKUP_ROOT="$1"
APPLICATION_DIR="$BACKUP_ROOT/application"
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
BACKUP_FILE="$APPLICATION_DIR/camera-platform-$TIMESTAMP.tar.gz"

echo "======================================================================"
echo "CAMERA PLATFORM APPLICATION BACKUP"
echo "======================================================================"
echo "Started: $(date)"
echo "Destination: $BACKUP_FILE"
echo ""

# Create application backup directory
mkdir -p "$APPLICATION_DIR"

# Application source directory
APP_SOURCE="/home/satinder/camera-platform-local"

if [ ! -d "$APP_SOURCE" ]; then
    echo "❌ Error: Application directory not found: $APP_SOURCE"
    exit 1
fi

echo "📦 Creating application tarball..."
echo "  Source: $APP_SOURCE"
echo "  Destination: $BACKUP_FILE"
echo ""

# Create temporary directory for staging
TEMP_DIR=$(mktemp -d)
STAGE_DIR="$TEMP_DIR/camera-platform-local"

echo "Step 1: Copying application files to staging area..."
cp -r "$APP_SOURCE" "$TEMP_DIR/"

# Remove unnecessary files from staging
echo "Step 2: Cleaning staging area (removing cache, logs, pycache)..."
find "$STAGE_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$STAGE_DIR" -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
find "$STAGE_DIR" -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
find "$STAGE_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
find "$STAGE_DIR" -type f -name "*.pyo" -delete 2>/dev/null || true
find "$STAGE_DIR" -name ".DS_Store" -delete 2>/dev/null || true

# Remove virtual environment (can be recreated)
if [ -d "$STAGE_DIR/venv" ]; then
    echo "  Removing venv (can be recreated from requirements.txt)..."
    rm -rf "$STAGE_DIR/venv"
fi

# Remove large log files (keep recent 10 files)
if [ -d "$STAGE_DIR/logs" ]; then
    echo "  Pruning old log files..."
    find "$STAGE_DIR/logs" -type f -name "*.log" | sort -r | tail -n +11 | xargs rm -f 2>/dev/null || true
    find "$STAGE_DIR/livestreaming/logs" -type f | sort -r | tail -n +11 | xargs rm -f 2>/dev/null || true
fi

# Remove PID files
find "$STAGE_DIR" -name "*.pid" -delete 2>/dev/null || true

echo "✅ Staging complete"
echo ""

# Create manifest file
echo "Step 3: Creating backup manifest..."
cat > "$STAGE_DIR/BACKUP_MANIFEST.txt" <<EOF
CAMERA PLATFORM APPLICATION BACKUP
====================================
Backup Date: $TIMESTAMP
Application Path: $APP_SOURCE
Hostname: $(hostname)
Git Branch: $(cd "$APP_SOURCE" && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
Git Commit: $(cd "$APP_SOURCE" && git rev-parse HEAD 2>/dev/null || echo "unknown")

CONTENTS
--------
- Full application source code
- Configuration files (.env, *.ini, *.conf)
- Database files (*.db)
- SSL certificates (if present)
- Scripts and tools
- Recent log files (latest 10)

EXCLUDED
--------
- Virtual environment (venv/) - recreate with: python3 -m venv venv && venv/bin/pip install -r requirements.txt
- Python cache files (__pycache__, *.pyc)
- Old log files (kept latest 10)
- PID files

DATABASE FILES
--------------
$(find "$STAGE_DIR" -name "*.db" -exec ls -lh {} \; | awk '{print $9 " - " $5}')

TOTAL SIZE
----------
$(du -sh "$STAGE_DIR" | awk '{print $1}')

RESTORATION INSTRUCTIONS
-------------------------
1. Extract tarball:
   tar -xzf camera-platform-$TIMESTAMP.tar.gz -C /home/satinder/

2. Recreate virtual environment:
   cd /home/satinder/camera-platform-local
   python3 -m venv venv
   venv/bin/pip install -r requirements.txt

3. Restore SSL certificates (if not included):
   See full system backup for /etc/letsencrypt/

4. Restart services:
   ./scripts/managed_start.sh restart

5. Verify:
   curl http://localhost:8080/health
   curl https://localhost:5000/
EOF

echo "✅ Manifest created"
echo ""

# Create compressed tarball
echo "Step 4: Compressing tarball (this may take a minute)..."
cd "$TEMP_DIR"
tar -czf "$BACKUP_FILE" camera-platform-local/

if [ $? -eq 0 ]; then
    echo "✅ Tarball created successfully"
else
    echo "❌ Failed to create tarball"
    rm -rf "$TEMP_DIR"
    exit 1
fi

# Cleanup staging area
rm -rf "$TEMP_DIR"

# Update latest symlink
echo ""
echo "Step 5: Updating 'latest' symlink..."
rm -f "$APPLICATION_DIR/latest.tar.gz"
ln -s "$BACKUP_FILE" "$APPLICATION_DIR/latest.tar.gz"
echo "✅ Latest application backup: $(readlink $APPLICATION_DIR/latest.tar.gz)"

echo ""
echo "======================================================================"
echo "APPLICATION BACKUP COMPLETE"
echo "======================================================================"
echo "Backup file: $BACKUP_FILE"
echo "Backup size: $(du -sh $BACKUP_FILE | awk '{print $1}')"
echo "Completed: $(date)"
echo ""
echo "To restore this backup:"
echo "  tar -xzf $BACKUP_FILE -C /home/satinder/"
echo "  cd /home/satinder/camera-platform-local"
echo "  python3 -m venv venv"
echo "  venv/bin/pip install -r requirements.txt"
echo "  ./scripts/managed_start.sh restart"
echo ""

# List all application backups
echo "All application backups:"
ls -lh "$APPLICATION_DIR"/*.tar.gz 2>/dev/null | awk '{printf "  %-50s %s\n", $9, $5}' || echo "  (none)"
echo ""

exit 0
