# Trade Bot

Personal research and alerting system for Indian (NSE) and US (SEC) institutional activity. Runs entirely on your Windows PC via Docker.

**Not investment advice.** Uses public disclosures only. Historical win rates are not calibrated probabilities until the Platt scorer ships (Phase 5).

## Prerequisites

- Docker Desktop (WSL2 backend)
- 8+ GB RAM free
- Phone on same Wi‑Fi for dashboard links from WhatsApp

## Quick Start

```powershell
cd C:\Users\siddu\projects\trade_bot
copy .env.example .env
# Edit .env: set DASHBOARD_PUBLIC_URL to your PC LAN IP, WHATSAPP_TO, SEC_IDENTITY, passwords

docker compose up -d --build
```

Services:

| URL | Service |
|---|---|
| http://localhost:3000 | Dashboard |
| http://localhost:8000/health | API health |
| http://localhost:3001 | WAHA (WhatsApp QR) |
| http://localhost:8080 | ntfy (fallback push) |

Default login: `admin` / `changeme` (change in `.env`).

## WAHA WhatsApp Setup

1. Open http://localhost:3001
2. Create/start session `default`
3. Scan QR code with WhatsApp on your phone
4. **Wait 2 minutes** before restarting containers (auth flush)
5. Set `WHATSAPP_TO=91XXXXXXXXXX` in `.env`

Brief alerts go to WhatsApp; full detail is on the dashboard.

## LAN IP for Phone Links

WhatsApp messages include dashboard links. `localhost` does not work on your phone.

```powershell
ipconfig
# Find IPv4 e.g. 192.168.1.42
```

Set in `.env`:

```
DASHBOARD_PUBLIC_URL=http://192.168.1.42:3000
```

Allow Windows Firewall inbound on port 3000 from your LAN.

## Backfill Before Alerts

Alerts are disabled until enough history exists (`ALERTS_ENABLED=false` by default).

```powershell
docker compose exec worker python scripts/backfill_nse.py 2000
docker compose exec worker python scripts/backfill_sec.py 100
```

Gate requirements:
- ≥500 IN signals
- ≥20 entities with ≥10 trades each

When ready:

```
ALERTS_ENABLED=true
```

Then `docker compose up -d`.

## Host NSE Fallback

If Docker NSE ingest fails (check **System** page), run host-side `nsepython`:

```powershell
pip install nsepython
.\scripts\host_ingest_nse.ps1
```

Schedule via Task Scheduler daily at 18:15 IST if needed.

## Schedules (IST)

| Job | Time |
|---|---|
| NSE block intraday | 10:35 |
| NSE EOD bulk/block | 18:15 |
| SEC Form 4 | every 6h |
| SEC 13F | 07:00 |
| US 13F digest (WhatsApp) | 09:00 |

## Backup

```powershell
.\scripts\backup_db.ps1
```

Backups go to `%USERPROFILE%\smartmoney-backups\`.

## Development

```powershell
pip install -r requirements.txt
$env:PYTHONPATH="packages"
pytest
```

Dashboard dev server:

```powershell
cd apps/dashboard
npm install
npm run dev
```

## Architecture

- `worker` — APScheduler scrapers (NSE, SEC)
- `processor` — RQ worker: forward returns, investor stats, tiers, alerts
- `api` — FastAPI REST
- `dashboard` — Vite/React SPA
- `waha` — WhatsApp delivery
- `ntfy` — fallback if WAHA is down

## Compliance

- Personal use only
- No MNPI, no trade-call scraping, no LLM confidence scores
- Outbound WhatsApp is a delivery channel, not a signal source

## Troubleshooting

| Issue | Fix |
|---|---|
| WAHA session lost | Re-scan QR at :3001; check `/system` |
| No NSE data | Run host fallback; check `ingestion_runs` |
| Phone link 404 | Fix `DASHBOARD_PUBLIC_URL` to LAN IP |
| Alerts not firing | Confirm backfill gate + `ALERTS_ENABLED=true` |
