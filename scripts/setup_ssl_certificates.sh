#!/bin/bash
# Setup SSL Certificates with Group Ownership (Secure & Repeatable)
# This script implements the recommended security solution from TODO.md #2
#
# What it does:
# 1. Creates ssl-certs group
# 2. Adds user to group
# 3. Configures certificate permissions
# 4. Sets up Certbot renewal hook
# 5. Updates .env with SSL configuration

set -e  # Exit on error

echo "============================================"
echo "SSL Certificate Setup - Group Ownership"
echo "============================================"
echo ""
echo "This script implements the secure group-based"
echo "certificate access solution (TODO.md #2)"
echo ""

# Check if running with sudo
if [ "$EUID" -ne 0 ]; then
    echo "❌ This script must be run with sudo"
    echo "Usage: sudo ./scripts/setup_ssl_certificates.sh"
    exit 1
fi

# Get the actual user (not root when using sudo)
ACTUAL_USER="${SUDO_USER:-$USER}"
if [ "$ACTUAL_USER" = "root" ]; then
    echo "❌ Error: Could not determine non-root user"
    echo "Please run with: sudo -u satinder ./scripts/setup_ssl_certificates.sh"
    exit 1
fi

# Get project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"

echo "📋 Configuration:"
echo "   User: $ACTUAL_USER"
echo "   Project: $PROJECT_ROOT"
echo ""

# Detect domain from .env
if [ -f "$ENV_FILE" ]; then
    DOMAIN=$(grep -E "^EMQX_BROKER_ENDPOINT=" "$ENV_FILE" | cut -d'=' -f2 | tr -d ' "' || true)
fi

if [ -z "$DOMAIN" ]; then
    echo "⚠️  Could not detect domain from .env"
    read -p "Enter your domain name (e.g., cameras.pahwa.net): " DOMAIN
fi

CERT_DIR="/etc/letsencrypt/live/$DOMAIN"
ARCHIVE_DIR="/etc/letsencrypt/archive/$DOMAIN"
CERT_FILE="$CERT_DIR/fullchain.pem"
KEY_FILE="$CERT_DIR/privkey.pem"

echo "   Domain: $DOMAIN"
echo "   Cert Directory: $CERT_DIR"
echo ""

# Check if certificates exist
if [ ! -d "$CERT_DIR" ]; then
    echo "❌ Error: Certificate directory not found: $CERT_DIR"
    echo ""
    echo "💡 Run certbot first to get Let's Encrypt certificates:"
    echo "   sudo certbot certonly --manual --preferred-challenges dns -d $DOMAIN"
    echo ""
    exit 1
fi

if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
    echo "❌ Error: Certificate files not found"
    echo "   Looking for: $CERT_FILE"
    echo "   Looking for: $KEY_FILE"
    exit 1
fi

echo "✅ Certificates found"
echo ""

# Step 1: Create ssl-certs group if it doesn't exist
echo "📝 Step 1: Create ssl-certs group"
if getent group ssl-certs > /dev/null 2>&1; then
    echo "   ✅ Group 'ssl-certs' already exists"
else
    groupadd ssl-certs
    echo "   ✅ Created group 'ssl-certs'"
fi
echo ""

# Step 2: Add users to ssl-certs group
echo "📝 Step 2: Add users to ssl-certs group"

# Add actual user
if id -nG "$ACTUAL_USER" | grep -qw ssl-certs; then
    echo "   ✅ User '$ACTUAL_USER' already in group 'ssl-certs'"
else
    usermod -a -G ssl-certs "$ACTUAL_USER"
    echo "   ✅ Added user '$ACTUAL_USER' to group 'ssl-certs'"
    echo "   ⚠️  User needs to log out and back in for group changes to take effect"
    echo "   ⚠️  Or run: newgrp ssl-certs"
fi

# Add turnserver user (for CoTURN TURN server)
if id turnserver >/dev/null 2>&1; then
    if id -nG turnserver | grep -qw ssl-certs; then
        echo "   ✅ User 'turnserver' already in group 'ssl-certs'"
    else
        usermod -a -G ssl-certs turnserver
        echo "   ✅ Added user 'turnserver' to group 'ssl-certs'"
        echo "   📌 CoTURN can now read SSL certificates for TLS support"
    fi
else
    echo "   ⚠️  User 'turnserver' not found - CoTURN may not be installed yet"
    echo "   💡 Run this script again after installing CoTURN"
fi

echo ""

# Step 3: Set ownership and permissions on certificate directories
echo "📝 Step 3: Configure certificate permissions"

# Set ownership on live directory
chown -R root:ssl-certs /etc/letsencrypt/live/
chown -R root:ssl-certs /etc/letsencrypt/archive/
echo "   ✅ Set ownership: root:ssl-certs"

# Set directory permissions
chmod 750 /etc/letsencrypt/live/
chmod 750 /etc/letsencrypt/archive/
if [ -d "$CERT_DIR" ]; then
    chmod 750 "$CERT_DIR"
fi
if [ -d "$ARCHIVE_DIR" ]; then
    chmod 750 "$ARCHIVE_DIR"
fi
echo "   ✅ Set directory permissions: 750"

# Set private key permissions (most restrictive)
find /etc/letsencrypt/archive/ -name 'privkey*.pem' -exec chmod 640 {} \;
echo "   ✅ Set private key permissions: 640"

# Set public cert permissions (can be more permissive)
find /etc/letsencrypt/archive/ -name 'fullchain*.pem' -exec chmod 644 {} \;
find /etc/letsencrypt/archive/ -name 'cert*.pem' -exec chmod 644 {} \;
find /etc/letsencrypt/archive/ -name 'chain*.pem' -exec chmod 644 {} \;
echo "   ✅ Set certificate permissions: 644"

# Verify permissions
echo ""
echo "📋 Current permissions:"
ls -la "$CERT_DIR/" | head -10
echo ""

# Step 4: Set up Certbot renewal hook
echo "📝 Step 4: Configure Certbot renewal hook"
RENEWAL_HOOK_DIR="/etc/letsencrypt/renewal-hooks/post"
RENEWAL_HOOK_FILE="$RENEWAL_HOOK_DIR/fix-permissions.sh"

mkdir -p "$RENEWAL_HOOK_DIR"

cat > "$RENEWAL_HOOK_FILE" << 'EOF'
#!/bin/bash
# Certbot Post-Renewal Hook
# Automatically fix certificate permissions after renewal
# Created by: setup_ssl_certificates.sh

chown -R root:ssl-certs /etc/letsencrypt/live/
chown -R root:ssl-certs /etc/letsencrypt/archive/
chmod 750 /etc/letsencrypt/live/
chmod 750 /etc/letsencrypt/archive/

# Set permissions on all domain directories
find /etc/letsencrypt/live/ -type d -exec chmod 750 {} \;
find /etc/letsencrypt/archive/ -type d -exec chmod 750 {} \;

# Private keys: most restrictive
find /etc/letsencrypt/archive/ -name 'privkey*.pem' -exec chmod 640 {} \;

# Public certificates: readable
find /etc/letsencrypt/archive/ -name 'fullchain*.pem' -exec chmod 644 {} \;
find /etc/letsencrypt/archive/ -name 'cert*.pem' -exec chmod 644 {} \;
find /etc/letsencrypt/archive/ -name 'chain*.pem' -exec chmod 644 {} \;

echo "✅ Certificate permissions fixed after renewal"
EOF

chmod +x "$RENEWAL_HOOK_FILE"
echo "   ✅ Created renewal hook: $RENEWAL_HOOK_FILE"
echo ""

# Step 5: Update .env file
echo "📝 Step 5: Update .env configuration"

if [ ! -f "$ENV_FILE" ]; then
    echo "   ❌ Error: .env file not found at $ENV_FILE"
    echo "   💡 Run setup_platform.py first"
    exit 1
fi

# Backup .env
cp "$ENV_FILE" "$ENV_FILE.backup.$(date +%Y%m%d_%H%M%S)"
echo "   ✅ Backed up .env file"

# Function to update or add env variable
update_env_var() {
    local var_name="$1"
    local var_value="$2"
    local env_file="$3"

    if grep -q "^${var_name}=" "$env_file"; then
        # Update existing
        sed -i "s|^${var_name}=.*|${var_name}=${var_value}|" "$env_file"
    else
        # Add new
        echo "${var_name}=${var_value}" >> "$env_file"
    fi
}

# Update SSL configuration
update_env_var "DASHBOARD_SSL_ENABLED" "true" "$ENV_FILE"
update_env_var "DASHBOARD_SSL_CERT_FILE" "$CERT_FILE" "$ENV_FILE"
update_env_var "DASHBOARD_SSL_KEY_FILE" "$KEY_FILE" "$ENV_FILE"

# Fix ownership on .env (should be owned by actual user, not root)
chown "$ACTUAL_USER:$ACTUAL_USER" "$ENV_FILE"

echo "   ✅ Updated .env with SSL configuration"
echo ""

# Show configuration
echo "📋 SSL Configuration in .env:"
su - "$ACTUAL_USER" -c "grep '^DASHBOARD_SSL' $ENV_FILE" || grep "^DASHBOARD_SSL" "$ENV_FILE"
echo ""

# Step 6: Verify access
echo "📝 Step 6: Verify certificate access"
echo "   Testing as user '$ACTUAL_USER'..."

# Test if user can read certificates (need to use newgrp or sg)
if sg ssl-certs -c "test -r $KEY_FILE" 2>/dev/null; then
    echo "   ✅ User can read private key"
else
    echo "   ⚠️  User cannot read private key yet"
    echo "   💡 User needs to log out and back in, or run: newgrp ssl-certs"
fi
echo ""

# Summary
echo "============================================"
echo "✅ SSL Certificate Setup Complete!"
echo "============================================"
echo ""
echo "📋 What was configured:"
echo "   ✓ Created ssl-certs group"
echo "   ✓ Added $ACTUAL_USER to ssl-certs group"
echo "   ✓ Set secure permissions on certificates"
echo "   ✓ Created Certbot renewal hook"
echo "   ✓ Updated .env with SSL configuration"
echo ""
echo "⚠️  IMPORTANT: User must activate group membership"
echo "   Option A (Recommended): Log out and log back in"
echo "   Option B (Temporary): Run 'newgrp ssl-certs' in current shell"
echo ""
echo "📌 Next steps:"
echo "   1. Activate group membership (log out/in or newgrp)"
echo "   2. Restart services: ./scripts/managed_start.sh restart"
echo "   3. Check logs: tail -f logs/livestreaming.log | grep -i ssl"
echo "   4. Test external access: https://$DOMAIN:5000"
echo ""
echo "🔍 Expected in logs:"
echo "   🔒 Signaling server SSL enabled with certificate: $CERT_FILE"
echo "   ✅ Signaling server running on wss://0.0.0.0:8765"
echo ""
echo "📖 See EXTERNAL_STREAMING_FIX.md for troubleshooting"
echo ""
