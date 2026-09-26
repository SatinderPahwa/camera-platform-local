#!/bin/bash
#
# certbot-auth-hook.sh - certbot --manual-auth-hook for the DNS-01 challenge.
#
# certbot runs this (as root) when a renewal needs the _acme-challenge TXT
# record deployed. Because our DNS provider (Squarespace) has no API, we can't
# write the record ourselves - instead we Telegram the user the exact record to
# add, then poll the authoritative nameservers until it appears, and only then
# return success so certbot proceeds to validation.
#
# certbot provides:
#   CERTBOT_DOMAIN      - the domain being validated (e.g. cameras.pahwa.net)
#   CERTBOT_VALIDATION  - the TXT value that must be published
#
# Tunables (env, with sane defaults):
#   POLL_INTERVAL  seconds between nameserver checks   (default 3600 = 1h)
#   MAX_ATTEMPTS   give up after this many checks       (default 48  = ~48h)
#   REMIND_EVERY   re-send a reminder every N attempts  (default 4)
#   TG_PREFIX      prepend to messages (test marker)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEND="$HERE/telegram-send.sh"

DOMAIN="${CERTBOT_DOMAIN:?CERTBOT_DOMAIN not set (is this being run by certbot?)}"
VALUE="${CERTBOT_VALIDATION:?CERTBOT_VALIDATION not set}"

POLL_INTERVAL="${POLL_INTERVAL:-3600}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-48}"
REMIND_EVERY="${REMIND_EVERY:-4}"

# Challenge FQDN, base zone, and the host label the user types into Squarespace.
FQDN="_acme-challenge.${DOMAIN}"
BASE="$(echo "$DOMAIN" | awk -F. '{print $(NF-1)"."$NF}')"   # pahwa.net
HOST="${FQDN%".$BASE"}"                                       # _acme-challenge.cameras

notify() { "$SEND" "$1" || echo "auth-hook: telegram send failed (continuing)" >&2; }

# Authoritative nameservers for the zone (resolved dynamically so a provider
# change doesn't silently break polling). Fall back to the known Google set.
mapfile -t NSS < <(dig +short NS "$BASE" 2>/dev/null | sed 's/\.$//' | grep -v '^$')
if [ "${#NSS[@]}" -eq 0 ]; then
  NSS=(ns-cloud-a1.googledomains.com ns-cloud-a2.googledomains.com \
       ns-cloud-a3.googledomains.com ns-cloud-a4.googledomains.com)
fi

# True only if EVERY authoritative nameserver already serves the exact value.
dns_ready() {
  local ns
  for ns in "${NSS[@]}"; do
    dig +short TXT "$FQDN" "@$ns" 2>/dev/null | tr -d '"' | grep -qF "$VALUE" || return 1
  done
  return 0
}

notify "🔐 <b>Certificate renewal started</b> for <code>${DOMAIN}</code>

Add/replace this DNS record in Squarespace:
<b>Type:</b> TXT
<b>Host:</b> <code>${HOST}</code>
<b>Value:</b> <code>${VALUE}</code>

I'll check the nameservers every $((POLL_INTERVAL/60)) min and finish the renewal automatically once it's live (up to ${MAX_ATTEMPTS} checks). Delete any older <code>${HOST}</code> record so only this value remains."

attempt=0
while :; do
  if dns_ready; then
    notify "✅ TXT record for <code>${DOMAIN}</code> is live on all nameservers. Completing renewal now…"
    exit 0
  fi
  attempt=$((attempt + 1))
  [ "$attempt" -ge "$MAX_ATTEMPTS" ] && break
  if [ "$REMIND_EVERY" -gt 0 ] && [ $((attempt % REMIND_EVERY)) -eq 0 ]; then
    notify "⏳ Still waiting for the TXT record for <code>${DOMAIN}</code> (checked ${attempt}×).
<b>Host:</b> <code>${HOST}</code>
<b>Value:</b> <code>${VALUE}</code>"
  fi
  sleep "$POLL_INTERVAL"
done

notify "❌ Renewal for <code>${DOMAIN}</code> gave up after ${MAX_ATTEMPTS} checks — the TXT record never appeared. certbot will try again at its next scheduled run (with a new value)."
exit 1
