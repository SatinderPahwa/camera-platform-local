#!/bin/bash
#
# telegram-send.sh - send a Telegram message using the camera platform's
# existing bot credentials (the same bot used for motion/person notifications).
#
# Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from the platform .env so we
# don't store a second copy of the secret. Never commit the .env.
#
# Usage: telegram-send.sh "message text (HTML allowed)"
# Env:   CAMERA_ENV_FILE  override path to .env (default below)
#        TG_PREFIX        optional string prepended to every message (used to
#                         mark test messages, e.g. "[TEST] ")
set -euo pipefail

ENV_FILE="${CAMERA_ENV_FILE:-/home/satinder/camera-platform-local/.env}"
MSG="${1:-}"
[ -z "$MSG" ] && { echo "usage: $0 <message>" >&2; exit 2; }

# Pull a single KEY=value from .env, stripping optional surrounding quotes.
env_get() {
  sed -n "s/^$1=//p" "$ENV_FILE" 2>/dev/null | head -1 \
    | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
}

BOT_TOKEN="$(env_get TELEGRAM_BOT_TOKEN)"
CHAT_ID="$(env_get TELEGRAM_CHAT_ID)"

if [ -z "$BOT_TOKEN" ] || [ -z "$CHAT_ID" ]; then
  echo "telegram-send: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not found in $ENV_FILE" >&2
  exit 1
fi

http_code="$(curl -sS --max-time 20 -o /dev/null -w '%{http_code}' \
  -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
  -d "chat_id=${CHAT_ID}" \
  -d "parse_mode=HTML" \
  -d "disable_web_page_preview=true" \
  --data-urlencode "text=${TG_PREFIX:-}${MSG}")"

if [ "$http_code" != "200" ]; then
  echo "telegram-send: Telegram API returned HTTP $http_code" >&2
  exit 1
fi
