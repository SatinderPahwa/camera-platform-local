#!/bin/bash
# Configure SSL for WebSocket Signaling Server
# This script updates the .env file to enable WSS (secure WebSocket)

set -e  # Exit on error

echo "============================================"
echo "SSL Signaling Server Configuration"
echo "============================================"
echo ""

# Get project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"

# Check if .env exists
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Error: .env file not found at $ENV_FILE"
    echo "💡 Run setup_platform.py first to generate .env file"
    exit 1
fi

# Detect domain from existing .env
DOMAIN=$(grep -E "^EMQX_BROKER_ENDPOINT=" "$ENV_FILE" | cut -d'=' -f2 | tr -d ' "')
if [ -z "$DOMAIN" ]; then
    echo "⚠️  Could not detect domain from .env"
    read -p "Enter your domain name (e.g., cameras.pahwa.net): " DOMAIN
fi

echo "📋 Configuration:"
echo "   Domain: $DOMAIN"
echo "   Cert: /etc/letsencrypt/live/$DOMAIN/fullchain.pem"
echo "   Key:  /etc/letsencrypt/live/$DOMAIN/privkey.pem"
echo ""

# Check if certificates exist
CERT_FILE="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
KEY_FILE="/etc/letsencrypt/live/$DOMAIN/privkey.pem"

if [ ! -f "$CERT_FILE" ]; then
    echo "❌ Error: Certificate not found at $CERT_FILE"
    echo "💡 Run certbot to get Let's Encrypt certificates first:"
    echo "   sudo certbot certonly --manual --preferred-challenges dns -d $DOMAIN"
    exit 1
fi

if [ ! -f "$KEY_FILE" ]; then
    echo "❌ Error: Private key not found at $KEY_FILE"
    exit 1
fi

echo "✅ Certificates found!"
echo ""

# Backup .env
cp "$ENV_FILE" "$ENV_FILE.backup.$(date +%Y%m%d_%H%M%S)"
echo "✅ Backed up .env file"

# Update or add SSL configuration
echo "📝 Updating .env file..."

# Function to update or add env variable
update_env_var() {
    local var_name="$1"
    local var_value="$2"

    if grep -q "^${var_name}=" "$ENV_FILE"; then
        # Update existing
        sed -i.tmp "s|^${var_name}=.*|${var_name}=${var_value}|" "$ENV_FILE"
    else
        # Add new
        echo "${var_name}=${var_value}" >> "$ENV_FILE"
    fi
}

# Update SSL configuration
update_env_var "DASHBOARD_SSL_ENABLED" "true"
update_env_var "DASHBOARD_SSL_CERT_FILE" "$CERT_FILE"
update_env_var "DASHBOARD_SSL_KEY_FILE" "$KEY_FILE"

# Clean up temp files
rm -f "$ENV_FILE.tmp"

echo "✅ SSL configuration updated in .env"
echo ""

# Show what was configured
echo "📋 SSL Configuration:"
grep -E "^DASHBOARD_SSL" "$ENV_FILE" || true
echo ""

echo "✅ Configuration complete!"
echo ""
echo "📌 Next steps:"
echo "   1. Restart services: ./scripts/managed_start.sh restart"
echo "   2. Check logs: tail -f logs/livestreaming.log"
echo "   3. Test external access: https://$DOMAIN:5000/livestream/viewer?camera=YOUR_CAMERA_ID"
echo ""
echo "🔍 Verify WSS is enabled in logs - look for:"
echo "   '🔒 Signaling server SSL enabled with certificate'"
echo ""
