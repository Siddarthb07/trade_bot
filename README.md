# Trade Bot

Personal research, alerting, and **paper-first auto-exec** system for Indian (NSE) and US institutional activity. Runs on your Windows PC via Docker.

**Not investment advice.** Uses public disclosures and price data only. Live ML scores use LightGBM + Platt when the model is `trained` — see [docs/ML_TRAINING.md](docs/ML_TRAINING.md). Strategy inventory and verify gates: [docs/STRATEGIES.md](docs/STRATEGIES.md).

## Prerequisites

- Docker Desktop (WSL2 backend)
- 8+ GB RAM free
- Phone on same Wi‑Fi for dashboard links (or Tailscale later)

## Quick Start

```powershell
cd C:\Users\siddu\projects\trade_bot
copy .env.example .env
# Edit .env: DASHBOARD_PUBLIC_URL (LAN IP), WHATSAPP_TO, SEC_IDENTITY, passwords

docker compose up -d --build
```

Services:

| URL | Service |
|---|---|
| http://localhost:3000 | Dashboard |
| http://localhost:3000/exec | **Live** trading tape + day sim |
| http://localhost:8000/health | API health |
| http://localhost:3001 | WAHA (WhatsApp QR) |
| http://localhost:8080 | ntfy (fallback push) |

Default login: `admin` / `changeme` (change in `.env`).

Dev dashboard (if Docker dash port is busy):

```powershell
cd apps/dashboard
$env:VITE_API_URL="http://127.0.0.1:8000"
npm run dev -- --host 0.0.0.0 --port 3000
```

## What’s in the box

1. **Ingest** — NSE bulk/block deals, SEC Form 4 / 13F  
2. **Score** — investor history + LightGBM (`bulk_ml`) + macro themes  
3. **Self-learn** — frozen `prediction_events`, online retrain, live calibration  
4. **Paper / live exec** — confidence sizing under ₹1000 IN / $10 US (configurable); Alpaca + Kite adapters; kill switch + session arm  
5. **Adaptive edge** — expanding-window peer gate; per-ticker ambition pass (≥85% holdout hit + positive expectancy)  
6. **Live UI** — `/exec` blotter (5s poll) + session day-sim + paper health (Stage A–C)  
7. **Readiness runbook** — [docs/runbooks/REAL_CAPITAL.md](docs/runbooks/REAL_CAPITAL.md) (personal capital gates; not third-party advice)

## Live trading (paper first)

1. Open http://localhost:3000/exec (nav: **Live**)  
2. **Arm sessions** (kill switch off)  
3. Watch the **live tape** for orders/fills  
4. Optional: **Day sim** — pick a date (e.g. `2024-08-23`), capital `10000`, market `IN` → full cash ledger + PnL statement  

```powershell
# API day sim (same engine as the dash button)
curl.exe -u admin:changeme -X POST "http://127.0.0.1:8000/exec/day-sim?asof=2024-08-23&capital=10000&market=IN&path_mode=session"
```

Exec APIs: `/exec/status`, `/exec/orders`, `/exec/live`, `/exec/arm`, `/exec/kill`, `/exec/strategies`, `/exec/playbooks`, `/exec/adaptive-profiles`, `/exec/day-sim`, `/exec/paper-metrics`, `/exec/receipts`, `/exec/cap-ladder/step-up`.

**Defaults:** `EXEC_MODE_IN=paper`, `EXEC_MODE_US=paper`, kill switch **on** until you arm. Live brokers need keys + ack flags in `.env` (see `.env.example`).

## Strategy verify / backtests

```powershell
$env:PYTHONPATH="packages"
python scripts/paper_5y_backtest.py          # classic TA + playbooks
python scripts/run_adaptive_edge_search.py   # 85% holdout search → models/ticker_adaptive_profiles.json
python scripts/run_strategy_benchmark.py
pytest tests/test_online_learn.py -q
```

Ambition gate (live enable): OOS hit ≥ **85%**, positive expectancy, enough trades — fail closed otherwise. Details in [docs/STRATEGIES.md](docs/STRATEGIES.md).

## WAHA WhatsApp Setup

1. Open http://localhost:3001  
2. Create/start session `default`  
3. Scan QR with WhatsApp  
4. **Wait 2 minutes** before restarting containers  
5. Set `WHATSAPP_TO=91XXXXXXXXXX` in `.env`  

## LAN IP for Phone Links

```powershell
ipconfig
# Find IPv4 e.g. 192.168.1.42
```

```
DASHBOARD_PUBLIC_URL=http://192.168.1.42:3000
```

Allow Windows Firewall inbound on port 3000 from your LAN. Phone Live page: `http://<LAN-IP>:3000/exec`.

## ML model

| | |
|---|---|
| Status | `trained` (see `models/model_meta.json`) |
| Samples / win rate | 645 labeled BUY deals · ~35% positive (`1mo`) |
| Docs | **[Model stats + retrain guide](docs/ML_TRAINING.md)** |

```powershell
docker compose run --rm worker python scripts/backfill_nse.py historical 180
docker compose run --rm processor python scripts/label_until_ready.py
docker compose run --rm processor python scripts/train_only.py
```

Online learn after labels mature: `POST /system/jobs/learn` (or automatic from forward backfill).

## Backfill Before Alerts

Alerts stay off until history is enough (`ALERTS_ENABLED=false` by default).

```powershell
docker compose exec worker python scripts/backfill_nse.py 2000
docker compose exec worker python scripts/backfill_sec.py 100
```

Gate: ≥500 IN signals, ≥20 entities with ≥10 trades. Then set `ALERTS_ENABLED=true`.

## Schedules (IST)

| Job | Time |
|---|---|
| NSE block intraday | 10:35 |
| NSE EOD bulk/block | 18:15 |
| SEC Form 4 | every 6h |
| SEC 13F | 07:00 |
| US 13F digest (WhatsApp) | 09:00 |
| Sentiment / mention heat | hourly |
| IN day flatten | ~15:16 |
| US day flatten | ~01:15 |

## Development

```powershell
pip install -r requirements.txt
$env:PYTHONPATH="packages"
pytest
```

```powershell
cd apps/dashboard
npm install
npm run dev
```

## Architecture

- `worker` — APScheduler scrapers (NSE, SEC)  
- `processor` — RQ: forward returns, scoring, learn, auto-exec hook  
- `api` — FastAPI REST (incl. `/exec/*`)  
- `dashboard` — Vite/React SPA  
- `broker` — paper / Alpaca / Kite adapters, risk, sizing, sessions  
- `waha` / `ntfy` — delivery  

## Compliance

- Personal use only  
- No MNPI, no trade-call scraping  
- Paper-first; live trading is optional and capped  
- Outbound WhatsApp is delivery only, not a signal source  

## Troubleshooting

| Issue | Fix |
|---|---|
| Dash port 3000 busy | Use Vite `npm run dev` or free the port; Docker dash may fail to bind |
| WAHA session lost | Re-scan QR at :3001; check `/system` |
| No NSE data | **System** page + `ingestion_runs` |
| Phone link 404 | Fix `DASHBOARD_PUBLIC_URL` to LAN IP |
| Alerts not firing | Backfill gate + `ALERTS_ENABLED=true` |
| No auto trades | Arm sessions, kill off, paper mode; check `/exec/live` reject reasons |
| Day sim 0 trades | Gate may reject that day — UI still shows skipped reasons; fallback setups may allocate |
