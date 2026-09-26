# Semi-automated Let's Encrypt renewal (Telegram-assisted DNS-01)

`cameras.pahwa.net` uses the **DNS-01** challenge because Virgin Media blocks
inbound port 80. Squarespace (our DNS host) has **no API**, so the one step that
can't be automated is publishing the `_acme-challenge` TXT record.

These hooks automate everything *around* that manual step: certbot detects the
cert is within 30 days of expiry (via the existing `certbot.timer`), Telegrams
you the exact record to add, polls the authoritative nameservers until it's
live, then completes the renewal and restarts the services — all using the
**same Telegram bot** the platform already uses for motion alerts (creds read
from `.env`).

## Flow

```
certbot.timer (twice daily) -> certbot renew
  └─ within 30 days of expiry:
       auth-hook    -> Telegram: "set TXT _acme-challenge.cameras = <value>"
                    -> poll authoritative NS hourly until it appears (max ~48h)
       [validate + issue]
       cleanup-hook -> Telegram: "you can delete the TXT record now"
       deploy-hook  -> fix perms, restart camera-platform + coturn,
                       Telegram: "renewed until <date>"
```

## Scripts
- `telegram-send.sh` — send a message via the platform's bot (reads `.env`).
- `certbot-auth-hook.sh` — notify + poll nameservers for the TXT value.
- `certbot-cleanup-hook.sh` — remind to delete the record after validation.
- `certbot-deploy-hook.sh` — restart services + confirm on success.

Tunables (env on the auth hook): `POLL_INTERVAL` (default 3600s),
`MAX_ATTEMPTS` (default 48), `REMIND_EVERY` (default 4).

## Activation (NOT done yet — see note)
1. Ensure scripts are executable on the server and on a stable path
   (e.g. `/home/satinder/camera-platform-local/scripts/cert-renewal/`).
2. Install the deploy hook:
   `ln -s .../certbot-deploy-hook.sh /etc/letsencrypt/renewal-hooks/deploy/camera-platform.sh`
3. Wire the manual hooks into `/etc/letsencrypt/renewal/cameras.pahwa.net.conf`
   under `[renewalparams]`:
   ```
   authenticator = manual
   pref_challs = dns-01
   manual_auth_hook = /home/satinder/camera-platform-local/scripts/cert-renewal/certbot-auth-hook.sh
   manual_cleanup_hook = /home/satinder/camera-platform-local/scripts/cert-renewal/certbot-cleanup-hook.sh
   ```
   (This is what lets `certbot renew` run unattended — plain `manual` without
   hooks refuses to renew non-interactively.)

## Testing
- **Telegram path:** `TG_PREFIX="[TEST] " ./telegram-send.sh "hello"`.
- **Auth-hook detection (no live DNS change):** point it at the value already
  in DNS and force a single check:
  ```
  CERTBOT_DOMAIN=cameras.pahwa.net \
  CERTBOT_VALIDATION="<value currently in _acme-challenge.cameras>" \
  MAX_ATTEMPTS=1 POLL_INTERVAL=1 TG_PREFIX="[TEST] " \
  ./certbot-auth-hook.sh
  ```
  It should Telegram the request, immediately detect the value, and exit 0.
- **Full end-to-end:** only via a real renewal (`certbot renew --force-renewal`
  once hooks are wired). Do this consciously — it will message your phone and
  wait for a real TXT update.

> Note: keep this on its feature branch and merge to `main` only after the first
> real renewal proves the flow end-to-end.
