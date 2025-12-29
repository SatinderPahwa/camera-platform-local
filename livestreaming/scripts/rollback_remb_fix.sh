#!/bin/bash
#
# QUICK ROLLBACK SCRIPT for REMB Fix
# Reverts BaseRtpEndpoint configuration changes
#

set -e

echo "======================================================================"
echo "ROLLBACK: Remove REMB Fix (BaseRtpEndpoint config)"
echo "======================================================================"
echo ""
echo "This will:"
echo "  1. Stop and remove Kurento container"
echo "  2. Checkout previous branch (fix-rtcp-direction-sendrecv)"
echo "  3. Restart Kurento with old configuration"
echo ""
read -p "Continue with rollback? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Rollback cancelled"
    exit 1
fi

echo ""
echo "Step 1: Stopping Kurento container..."
docker stop kms-production || true
docker rm kms-production || true
echo "✅ Container removed"

echo ""
echo "Step 2: Switching to previous branch..."
cd ~/camera-platform-local
git checkout fix-rtcp-direction-sendrecv
echo "✅ Switched to fix-rtcp-direction-sendrecv"

echo ""
echo "Step 3: Restarting Kurento..."
~/camera-platform-local/livestreaming/scripts/start_kurento.sh

echo ""
echo "======================================================================"
echo "✅ ROLLBACK COMPLETE"
echo "======================================================================"
echo ""
echo "Kurento is now running without BaseRtpEndpoint config"
echo "To re-apply the fix: git checkout fix-rtcp-remb-config && restart Kurento"
echo ""
