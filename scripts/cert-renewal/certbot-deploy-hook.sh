#!/bin/bash
#
# certbot-deploy-hook.sh - runs ONLY after a certificate is successfully
# renewed (certbot --deploy-hook / renewal-hooks/deploy). Picks up the new cert
# in the services that serve it and confirms over Telegram.
#
# IMPORTANT: the platform runs under systemd as root, so restarts must go
# through systemctl (NOT scripts/managed_start.sh, which cannot restart
# root-owned processes and leaves the dashboard dead). CoTURN is a separate
# systemd service and must be restarted on its own or it keeps serving the old
# (expired) cert on :5349.
#
# certbot provides RENEWED_LINEAGE (path to the live dir) and RENEWED_DOMAINS.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEND="$HERE/telegram-send.sh"

# Only act for our cert (deploy hooks in renewal-hooks/deploy run for every
# renewed lineage; guard so unrelated certs don't restart the camera stack).
case "${RENEWED_LINEAGE:-}" in
  *cameras.pahwa.net*) : ;;
  *) exit 0 ;;
esac

# Make the new key readable by the ssl-certs group (same as the manual runbook).
if [ -x /etc/letsencrypt/renewal-hooks/post/fix-permissions.sh ]; then
  /etc/letsencrypt/renewal-hooks/post/fix-permissions.sh || true
fi

systemctl restart camera-platform || echo "deploy-hook: camera-platform restart failed" >&2
systemctl restart coturn         || echo "deploy-hook: coturn restart failed" >&2

END="$(openssl x509 -enddate -noout -in "${RENEWED_LINEAGE}/fullchain.pem" 2>/dev/null | cut -d= -f2)"

"$SEND" "✅ <b>Certificate renewed</b> for cameras.pahwa.net
Valid until: <code>${END:-unknown}</code>
Dashboard (:5000) and CoTURN (:5349) restarted." \
  || echo "deploy-hook: telegram send failed (continuing)" >&2
