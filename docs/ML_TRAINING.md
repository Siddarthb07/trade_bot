# ML model — stats & retraining

LightGBM + Platt calibration (`lgbm-platt-v1`) scores IN bulk/block BUY deals.
Labels are forward returns after `WIN_WINDOW` (default **1mo**). A deal is a win if
`return_pct > WIN_THRESHOLD_PCT` (default `0.0` = any positive return).

## Current model stats

Source of truth at runtime: `models/model_meta.json` (also exposed on
`GET /system/label-stats` as `ml_model`). Snapshot from the 2026-07-21 train:

| Field | Value |
|---|---|
| Status | `trained` |
| Scorer | `lgbm-platt-v1` |
| Samples | 645 |
| Positives (wins) | 224 |
| Negatives | 421 |
| Positive rate | 34.7% |
| Label window | `1mo` |
| Win threshold | `0.0` |
| Markets | IN |
| Sources | `nse_bulk`, `nse_block`, `bse_bulk` |
| Actions trained | BUY / P / A only |
| Split | date holdout 80/20 |
| Train cutoff (last train row) | 2026-02-03 |
| Holdout test accuracy | 89.1% *(optimistic — not live edge)* |
| Hold priors (days) | HIGH 14 / MEDIUM 7 / LOW 42 / default 7 |
| Trained at (UTC) | 2026-07-21T13:18:10Z |

Gates (skip train if unmet): `ML_TRAIN_MIN_SAMPLES` (30) and
`ML_MIN_POSITIVE_RATE` (5%). Fake / immature labels (`price_source` in
`missing` / `immature`) are never used.

## Train with more datapoints

More mature BUY deals → better labels → retrain. Pipeline:

### 1. Pull more NSE history

```powershell
# Recent archive CSV (thin; last ~week)
docker compose run --rm worker python scripts/backfill_nse.py 5000

# Multi-month historicalOR CSV (main source of volume)
docker compose run --rm worker python scripts/backfill_nse.py historical 180
# or with retries if NSE flaps:
docker compose run --rm worker python scripts/backfill_nse.py retry 180 5 30
```

Optional: set `ML_BACKFILL_DAYS=180` (or higher) in `.env`.

### 2. Label matured deals

Only deals older than the window get real forward returns (no clamped zeros).

```powershell
# Loop until enough 1mo BUY labels (default target ~150+)
docker compose run --rm processor python scripts/label_until_ready.py

# Or one large batch:
docker compose run --rm processor python -c "from processor.forward_backfill import backfill_mature_forward_returns; print(backfill_mature_forward_returns(batch_size=200, markets=['IN']))"
```

Check progress:

```powershell
curl.exe -u admin:changeme http://127.0.0.1:8000/system/label-stats
```

Watch `in_bulk_labeled` and `ml_model.positive_rate`.

### 3. Retrain + rescore

```powershell
docker compose run --rm processor python scripts/train_only.py
```

This writes `models/lgbm_calibrated.pkl` + `models/model_meta.json`, then rescores
signals. Full rescore of 10k+ tickers via yfinance is slow; you can Ctrl+C after
`Train metrics: ... status: trained` if you only need the new model file — live
scoring still uses the new pickle on the next process pass.

### Tips for more / better labels

| Goal | What to do |
|---|---|
| More samples sooner | Keep `WIN_WINDOW=1mo` (3mo needs ~90d-old deals) |
| Longer-horizon model | Set `WIN_WINDOW=3mo`, wait for age, relabel, retrain |
| Stricter “win” | Raise `WIN_THRESHOLD_PCT` (e.g. `0.05` = +5%) |
| More history | `historical 365` (NSE caps ~1y chunks; script already chunks) |
| Cleaner labels | Prefer EOD cache coverage; missing Yahoo symbols stay unlabeled |
| Verify gate | Confirm `status` is `trained` and `positive_rate ≥ 0.05` in `model_meta.json` |

### One-shot refresh (copy-paste)

```powershell
docker compose run --rm worker python scripts/backfill_nse.py historical 180
docker compose run --rm processor python scripts/label_until_ready.py
docker compose run --rm processor python scripts/train_only.py
curl.exe -u admin:changeme http://127.0.0.1:8000/system/label-stats
```
