# Raspberry Pi Deployment — Trade Bot

**Target:** Always-on homelab node for ingest, scoring, and WhatsApp alerts  
**Last updated:** 2026-07-01

---

## Hardware recommendations

| Board | RAM | Verdict |
|-------|-----|---------|
| **Pi 5 (8 GB)** | 8 GB | Best choice — comfortable headroom |
| **Pi 4 (8 GB)** | 8 GB | Viable with SSD boot |
| **Pi 4 (4 GB)** | 4 GB | Tight — WAHA + Postgres + 4 Python services may OOM |
| **Pi 3 / Zero** | ≤1 GB | Not recommended |

**Storage:** Boot from **USB SSD**, not SD card (Postgres + Docker layers wear SD quickly).

**OS:** Raspberry Pi OS **64-bit** (Bookworm or later).

---

## Pre-flight checklist

1. Static LAN IP or DHCP reservation for the Pi
2. Update `.env` → `DASHBOARD_PUBLIC_URL=http://<pi-ip>` or sslip.io hostname
3. Rotate default passwords (`admin/changeme`, WAHA dashboard, Postgres)
4. Phone on same WiFi (or Tailscale) for dashboard links

---

## Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# log out and back in
sudo apt install docker-compose-plugin
```

---

## Deploy Trade Bot

```bash
git clone https://github.com/Siddarthb07/trade_bot.git
cd trade_bot
cp .env.example .env
# edit .env: DASHBOARD_PUBLIC_URL, WHATSAPP_TO, secrets

docker compose up -d --build
```

Open dashboard: `http://<pi-ip>:3000`  
WAHA QR: `http://<pi-ip>:3001` (or SSH tunnel `ssh -L 3001:localhost:3001 pi@<pi-ip>`)

---

## Resource tuning

### Swap (4 GB Pi only)

```bash
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile   # CONF_SWAPSIZE=2048
sudo dphys-swapfile setup && sudo dphys-swapfile swapon
```

### Limit concurrent builds

Build on a faster machine and `docker save/load`, or:

```bash
docker compose build --parallel 1 api worker processor dashboard
```

### WAHA is the heaviest service

If OOM occurs, consider:
- Running WAHA on your phone-connected laptop instead
- Using ntfy-only alerts (`ntfy` container is lightweight)

---

## WhatsApp on Pi

Same flow as laptop:
1. Start WAHA, scan QR once
2. Wait 2 minutes before restarting
3. Session persists in Postgres (`waha_sessions` DB)

Monitor: `docker compose logs -f waha`

---

## Firewall

```bash
sudo ufw allow from 192.168.0.0/16 to any port 3000
sudo ufw allow from 192.168.0.0/16 to any port 80
sudo ufw enable
```

Keep API (`8000`) and WAHA (`3001`) localhost-only unless you know why you're exposing them.

---

## Backups

```bash
docker compose exec postgres pg_dump -U smartmoney smartmoney > backup.sql
```

Copy `backup.sql` and `models/` volume off the Pi weekly.

---

## vs laptop

| | Laptop | Pi |
|--|--------|-----|
| Always-on | No (sleep kills stack) | Yes |
| WAHA QR pairing | Easy (browser local) | SSH tunnel or LAN browser |
| Performance | Faster builds | Slower; SSD helps |
| Power | ~5–15 W continuous | Higher when awake |

---

## Related docs

- [TRADE_BOT_DEEP_DIVE.md](./TRADE_BOT_DEEP_DIVE.md)
- [HTTPS_SETUP.md](./HTTPS_SETUP.md)
- [LLM_COUNCIL_RATING.md](./LLM_COUNCIL_RATING.md)
