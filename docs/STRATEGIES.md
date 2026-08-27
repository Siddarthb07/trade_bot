# Trade Bot — Strategies Inventory

Last updated: 2026-08-27  
See also: [ML_TRAINING.md](./ML_TRAINING.md), [README.md](../README.md).

**Not investment advice.**

---

## Currently used (live path)

| Strategy | Role |
|----------|------|
| Investor history rules | Tier from win rate / cluster / deal size |
| Interim probability | Fallback when ML not trained |
| LightGBM + Platt (`bulk_ml`) | Bulk BUY win probability |
| Macro / theme picks | Demand themes + FRED context |
| **`adaptive_edge`** | Expanding-window peer gate + per-ticker TP/SL profiles |
| **Paper / live auto-exec** | Confidence sizing under ₹1000 / $10; Alpaca + Kite adapters |
| **Session flatten** | IN ~15:16 IST, US ~01:15 IST day book |
| **WSB mention heat** | Filter / veto only (`sent_filter`) |
| **Live UI** | `/exec` tape (5s) + day-sim ledger |

Off-shelf TA (`mom_cross`, `mean_rev_bb`, `trend_follow`, `mean_rev_chop`) is audited and may appear in playbooks; **not** default live unless ambition-pass / registry-enabled.

## Registry (`/exec/strategies`)

| ID | Default live | Notes |
|----|--------------|-------|
| `bulk_ml` | yes | LightGBM bulk |
| `adaptive_edge` | yes | Peer calibrator; ticker must be ambition-eligible for fire |
| `mom_cross` | no | Dual MA **cross events only** (no ma_state spam) |
| `mean_rev_bb` | no | Bollinger — until walk-forward gate |
| `trend_follow` | no | Mom cross in trend regime |
| `mean_rev_chop` | no | BB in chop only |
| `intraday_orb` | no | Needs same-session bars (refuses daily misuse) |
| `macro_theme` | no | Context |
| `sent_filter` | no | Veto only |

## Verify gate

Walk-forward / expanding holdout via `walk_forward_backtest`, `scripts/run_strategy_benchmark.py`, `scripts/run_adaptive_edge_search.py`.

- **Soft pass:** expectancy > 0, max DD ≤ 35%, enough trades → paper / study.
- **Ambition pass (live):** soft pass **and** OOS hit rate ≥ **85%**. Fail closed otherwise.
- Playbooks: `scripts/paper_5y_backtest.py` → `models/ticker_playbooks.json` · `GET /exec/playbooks`
- Adaptive hybrid: `scripts/run_adaptive_edge_search.py` → `models/ticker_adaptive_profiles.json` · `GET /exec/adaptive-profiles`
- Anti-memorization: expanding window only; holdout not used to pick TP/SL; peer memory capped

## Day sim (paper ledger)

`POST /exec/day-sim?asof=2024-08-23&capital=10000&market=IN` or the **Live** page button.

- Allocates up to 3 names from adaptive / setup fallback  
- Full cash ledger + PnL statement (money put / returned / exit reason)  
- Daily-bar path exits — not live tick fills  

## Scripts

| Script | Output |
|--------|--------|
| `scripts/paper_5y_backtest.py` | `models/paper_5y_backtest.json`, playbooks |
| `scripts/run_adaptive_edge_search.py` | `models/adaptive_edge_backtest.json`, profiles, state |
| `scripts/run_strategy_benchmark.py` | `models/benchmark_results.json` |
