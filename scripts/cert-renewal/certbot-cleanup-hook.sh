#!/bin/bash
#
# certbot-cleanup-hook.sh - certbot --manual-cleanup-hook.
#
# Runs after the validation attempt (whether it succeeded or failed). We can't
# remove the TXT record ourselves (no Squarespace API), so we just remind the
# user they may delete it now. Keeping the record around is harmless but tidy
# to remove so the next renewal starts from a clean slate.
#
# certbot provides CERTBOT_DOMAIN (and CERTBOT_AUTH_OUTPUT).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEND="$HERE/telegram-send.sh"

DOMAIN="${CERTBOT_DOMAIN:-cameras.pahwa.net}"
FQDN="_acme-challenge.${DOMAIN}"
BASE="$(echo "$DOMAIN" | awk -F. '{print $(NF-1)"."$NF}')"
HOST="${FQDN%".$BASE"}"

"$SEND" "🧹 Validation finished for <code>${DOMAIN}</code>. You can now delete the TXT record <code>${HOST}</code> in Squarespace (optional, keeps things tidy)." \
  || echo "cleanup-hook: telegram send failed (continuing)" >&2
