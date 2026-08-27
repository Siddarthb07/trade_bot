# Stage B status (honest)

**Generated after:** `scripts/run_stage_b_search.py` (2026-08-27)  
**Gate:** OOS hit ≥ 85%, **n ≥ 30**, expectancy > 0, regime tag  
**Result: FAIL CLOSED — `stage_b_pass: false`, `eligible_tickers: []`**

**Not investment advice.**

## Best pooled holdout (all tickers, gated)

| Metric | Value |
|--------|-------|
| n_trades | 11 |
| hit_rate_pct | 72.73 |
| expectancy | +0.002974 |

Hybrid eligible pool: **empty** (no ticker cleared n≥30 + 85%).

## Closest ticker (still not live-eligible)

| Ticker | n_oos | hit % | expectancy | ambition_pass |
|--------|-------|-------|------------|---------------|
| QQQ | 7 | 85.71 | +0.0095 | **false** (n&lt;30) |

Others: sparse OOS fires (often n=0 gated) or hit ≪ 85%.

## Ablation (peer gate vs ungated)

On most names, **gated OOS n≈0** while ungated fires ~10–14 trades with mixed expectancy. Gate is highly selective; it does **not** currently produce enough OOS samples to claim an 85%@n≥30 live book.

Artifacts:
- `models/stage_b_search_report.json`
- `models/ticker_adaptive_profiles.json` (eligible empty)
- `models/adaptive_edge_backtest.json`

## What this means for later stages

| Stage | Status |
|-------|--------|
| A Session day-sim | Code ready; edge fills only when gate clears (no demo = often 0 trades) |
| B Ambition live | **Blocked** until search finds ≥3 tickers with n≥30 |
| C Live paper on ambition names | **Blocked** on adaptive_edge (no eligible universe) |
| C Plumbing | Paper metrics / weekly freeze / receipts still usable for bulk_ml paper |

## Next engineering (no cheating)

1. Keep fail-closed — do **not** lower n≥30 or 85% for live.  
2. Research track: soft-study profiles (separate flag, never `ambition_pass`) for expectancy > 0 / lower hit.  
3. Re-run `python scripts/run_stage_b_search.py` after setup/score changes that increase gated OOS sample size without peeking holdout.  
4. Until Stage B clears, paper arm only for non-ambition strategies / measurement — caps stay ₹1000/$10.
