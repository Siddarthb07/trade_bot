# Trade Bot — Strategies Inventory

Last updated: 2026-08-27  
See also: [ML_TRAINING.md](./ML_TRAINING.md), [REAL_CAPITAL.md](./runbooks/REAL_CAPITAL.md), [README.md](../README.md).

**Not investment advice.**

---

## Currently used (live path)

| Strategy | Role |
|----------|------|
| Investor history rules | Tier from win rate / cluster / deal size |
| Interim probability | Fallback when ML not trained |
| LightGBM + Platt (`bulk_ml`) | Bulk BUY win probability |
| Macro / theme picks | Demand themes + FRED context |
| **`adaptive_edge`** | Expanding-window peer gate + per-ticker TP/SL + **regime match** |
| **Paper / live auto-exec** | Confidence sizing under ₹1000 / $10; Alpaca + Kite adapters |
| **Session flatten** | IN ~15:16 IST, US ~01:15 IST day book + re-kill |
| **WSB mention heat** | Filter / veto only (`sent_filter`) |
| **Live UI** | `/exec` tape (5s) + session day-sim + paper health |

Off-shelf TA (`mom_cross`, `mean_rev_bb`, `trend_follow`, `mean_rev_chop`) is audited and may appear in playbooks; **not** default live unless ambition-pass / registry-enabled.

## Registry (`/exec/strategies`)

| ID | Default live | Notes |
|----|--------------|-------|
| `bulk_ml` | yes | LightGBM bulk |
| `adaptive_edge` | yes | Peer calibrator; ticker must be ambition-eligible + regime match |
| `mom_cross` | no | Dual MA **cross events only** (no ma_state spam) |
| `mean_rev_bb` | no | Bollinger — until walk-forward gate |
| `trend_follow` | no | Mom cross in trend regime |
| `mean_rev_chop` | no | BB in chop only |
| `intraday_orb` | no | **Requires same-session 5m bars** (refuses daily misuse) |
| `macro_theme` | no | Context |
| `sent_filter` | no | Veto only |

## Verify gate (Stage B)

Walk-forward / expanding holdout via `walk_forward_backtest`, `scripts/run_strategy_benchmark.py`, `scripts/run_adaptive_edge_search.py`.

- **Soft pass:** expectancy > 0 after costs, max DD ≤ 35%, **n ≥ 30** trades → paper / study.
- **Ambition pass (live):** soft pass **and** OOS hit rate ≥ **85%** **and** n ≥ **30**. Fail closed otherwise.
- Validate freeze: `python scripts/validate_adaptive_profiles.py` (add `--require-eligible` before publishing).
- Playbooks: `scripts/paper_5y_backtest.py` → `models/ticker_playbooks.json` · `GET /exec/playbooks`
- Adaptive hybrid: `scripts/run_adaptive_edge_search.py` → `models/ticker_adaptive_profiles.json` · `GET /exec/adaptive-profiles`
- Anti-memorization: expanding window only; holdout not used to pick TP/SL; peer memory capped
- Online learn: peers / `effective_target` only — **never** retunes TP/SL from live labels

## Day sim (Stage A)

`POST /exec/day-sim?asof=2024-08-23&capital=10000&market=IN&path_mode=session`

| Param | Default | Meaning |
|-------|---------|---------|
| `path_mode` | `session` | 5m intraday + cost model |
| `path_mode=daily` | — | Legacy EOD research path |
| `allow_demo_fallback` | `false` | If true, DEMO badge; **excluded from edge hit rate** |

## Paper health / freeze (Stage C)

- `GET /exec/paper-metrics` — rolling 30/90d expectancy, n, hit (only when n>0)
- Sunday job `paper_weekly_freeze` — kill + revoke eligibility if expectancy collapses
- `POST /exec/weekly-freeze` — manual trigger

## Micro-live / ladder (Stage D–E)

- Dual ACK: `EXEC_LIVE_ACK_*=true` **and** `EXEC_LIVE_CONFIRM_PHRASE=I_ACCEPT_MICRO_LIVE_RISK`
- Caps stay ₹1000 / $10 until `/exec/cap-ladder/step-up` with positive rolling expectancy
- Weekly portfolio loss limit enforced in `broker.risk.authorize`

## Ops (Stage F)

- Decision receipts: `models/decision_receipts.jsonl` · `GET /exec/receipts`
- Model pin: `POST /exec/model-pin` → `models/model_pin.json`
- Runbook: [docs/runbooks/REAL_CAPITAL.md](./runbooks/REAL_CAPITAL.md)

## Scripts

| Script | Output |
|--------|--------|
| `scripts/paper_5y_backtest.py` | `models/paper_5y_backtest.json`, playbooks |
| `scripts/run_adaptive_edge_search.py` | `models/adaptive_edge_backtest.json`, profiles, state |
| `scripts/run_stage_b_search.py` | Stage B search + peer-gate ablation → `models/stage_b_search_report.json` |
| `scripts/run_strategy_benchmark.py` | `models/benchmark_results.json` |
| `scripts/validate_adaptive_profiles.py` | exit 0/1 freeze audit |
