#!/bin/bash
# Fix turnserver SSL certificate access
# Run this on camera1 production server

set -e

echo "=== Fixing CoTURN TLS Support ==="
echo ""

echo "Step 1: Adding turnserver user to ssl-certs group..."
sudo usermod -a -G ssl-certs turnserver

echo "Step 2: Verifying group membership..."
groups turnserver

echo ""
echo "Step 3: Restarting CoTURN service..."
sudo systemctl restart coturn
sleep 2

echo ""
echo "Step 4: Checking if port 5349 (TLS) is listening..."
sudo ss -tlnp | grep 5349 || echo "⚠️  Port 5349 not listening yet"

echo ""
echo "Step 5: Checking CoTURN logs for TLS listener..."
sudo journalctl -u coturn -n 30 --no-pager | grep -i "tls\|5349\|listener" || echo "No TLS/5349 messages in recent logs"

echo ""
echo "Step 6: Verifying certificate access..."
if sudo -u turnserver test -r /etc/letsencrypt/live/cameras.pahwa.net/privkey.pem; then
    echo "✅ Can read private key"
else
    echo "❌ Cannot read private key"
fi

if sudo -u turnserver test -r /etc/letsencrypt/live/cameras.pahwa.net/fullchain.pem; then
    echo "✅ Can read certificate"
else
    echo "❌ Cannot read certificate"
fi

echo ""
echo "=== Fix Complete ==="
echo "Now test livestreaming from iPhone cellular network"
