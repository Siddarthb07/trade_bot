# HTTPS Setup — Trade Bot (Phase 5)

WhatsApp links and phone browsers work best with a **stable HTTPS URL**. Options below keep the stack on your LAN or expose it safely.

## Option A — Tailscale (recommended for home lab)

1. Install [Tailscale](https://tailscale.com/) on the PC running Docker and on your phone.
2. Note the machine's Tailscale IP (e.g. `100.x.y.z`).
3. In `.env`:
   ```
   DASHBOARD_PUBLIC_URL=https://100.x.y.z
   ```
4. Enable Tailscale HTTPS (MagicDNS + cert) or use `tailscale serve`:
   ```bash
   tailscale serve --bg --https=443 http://127.0.0.1:80
   ```
5. Restart dashboard/API so WhatsApp templates pick up the new URL:
   ```powershell
   docker compose restart api worker dashboard
   ```

## Option B — Cloudflare Tunnel

1. Install `cloudflared` and authenticate with Cloudflare.
2. Create a tunnel pointing to `http://localhost:80` (dashboard nginx).
3. Set `DASHBOARD_PUBLIC_URL=https://tradebot.yourdomain.com` in `.env`.
4. No port forwarding required; works off WiFi.

## Option C — Local HTTP only (current default)

- Dashboard: `http://192.168.x.x` (port 80)
- API: `http://127.0.0.1:8000` (not exposed externally)
- WhatsApp path links use `DASHBOARD_PUBLIC_URL` — must be reachable from the phone on the same network.

## WhatsApp group (not DM)

Set in `.env`:
```
WHATSAPP_GROUP_ID=120363xxxxxxxx@g.us
ALERTS_ENABLED=true
DAILY_PICKS_ENABLED=true
```

Run `python scripts/setup_whatsapp_group.py` to list group IDs via WAHA.

## ML model persistence

The `models` Docker volume stores `lgbm_calibrated.pkl` and `model_meta.json` across rebuilds. Dev override also bind-mounts `./models` for easy inspection.

---

*Not investment advice.*
