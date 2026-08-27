# Changes since last commit (before readiness gates)

**Base commit:** `1b96e1d` — *Document live exec/adaptive edge and check in backtest artifacts.*  
**As of:** 2026-08-27  
**Scope:** Path to real-capital readiness (personal use), Stages A–F  
**Status:** Working tree only — not committed yet  

**Ops run (this file):**
- `python scripts/validate_adaptive_profiles.py` → OK, **0 eligible**, `min_oos=30`
- `pytest tests/test_readiness_gates.py` → **3 passed**
- Profile validate (in-process) → no errors; `eligible_tickers: []`
- IN modeled cost → **30.0 bps** round-trip

**Not investment advice.**

---

## Summary

| Kind | Count |
|------|-------|
| Modified files | 14 |
| New files | 10 |
| Net lines (tracked diffs) | +917 / −150 (approx.) |

---

## New files

| Path | Purpose |
|------|---------|
| `docs/runbooks/REAL_CAPITAL.md` | Stage A–F ops runbook (arm/kill, freeze, micro-live, ladder) |
| `models/ticker_adaptive_profiles.freeze.json` | Freeze stamp for eligible list / min OOS |
| `packages/broker/cap_ladder.py` | Stage E: step-up/down caps only when expectancy holds |
| `packages/processor/costs.py` | IN/US round-trip cost model (spread + fees) |
| `packages/processor/decision_receipts.py` | Append-only decision receipts + model pin |
| `packages/processor/intraday_bars.py` | yfinance 5m same-session bars for ORB / day-sim |
| `packages/processor/paper_metrics.py` | Rolling 30/90d paper metrics + weekly freeze |
| `packages/processor/profile_validate.py` | Ambition gate validator (n≥30, hit≥85%, expectancy>0) |
| `scripts/validate_adaptive_profiles.py` | CLI freeze audit for profiles JSON |
| `tests/test_readiness_gates.py` | Unit tests for costs + profile validation |

---

## Modified files

### Config / docs

| Path | What changed |
|------|----------------|
| `.env.example` | `EXEC_LIVE_CONFIRM_PHRASE`, `EXEC_WEEKLY_FREEZE_ENABLED` |
| `README.md` | Session day-sim curl; new exec APIs; runbook link |
| `docs/STRATEGIES.md` | Stage A–F gates, day-sim params, paper health, dual ACK, ladder |

### Dashboard

| Path | What changed |
|------|----------------|
| `apps/dashboard/src/pages/ExecPage.tsx` | Paper health (30d/90d); session/daily path; demo fallback checkbox; DEMO badge; edge hit rate only when valid |

### Models / artifacts

| Path | What changed |
|------|----------------|
| `models/ticker_adaptive_profiles.json` | `min_oos_trades: 30`; weak ambition revoked → **`eligible_tickers: []`**; regime tags / disclaimer |

### API

| Path | What changed |
|------|----------------|
| `packages/api/main.py` | `/exec/day-sim` `path_mode` + `allow_demo_fallback`; `/exec/paper-metrics`; `/exec/weekly-freeze`; `/exec/enable-live`; `/exec/cap-ladder/step-up|step-down`; `/exec/receipts`; `/exec/model-pin`; live tape includes health + weekly PnL; status disclaimer |

### Broker / risk / exec

| Path | What changed |
|------|----------------|
| `packages/broker/daytrade.py` | ORB uses intraday session bars only; flatten re-kills session |
| `packages/broker/executor.py` | Dual live ACK check; decision receipts + model pin on every sized order |
| `packages/broker/risk.py` | Live phrase ACK; weekly loss limit; `end_session_disarm`; weekly PnL sidecar |
| `packages/core/config.py` | `exec_live_confirm_phrase`, `exec_weekly_freeze_enabled` |
| `packages/ingest/scheduler.py` | Sunday `paper_weekly_freeze` job |

### Strategies / sim / learn

| Path | What changed |
|------|----------------|
| `packages/processor/adaptive_edge.py` | `MIN_OOS_TRADES=30`; regime on profiles; regime mismatch → no fire; freeze sidecar on `save_profiles` |
| `packages/processor/day_sim.py` | Session path + costs; demo fallback banned from edge metrics by default |
| `packages/processor/learn.py` | Hard rule: online learn never retunes TP/SL |

---

## Behavior deltas vs `1b96e1d`

1. **Day-sim default is session bars + costs**, not daily close-to-close.  
2. **`setup_fallback` is not edge** unless explicitly opted in (DEMO badge).  
3. **Live ambition needs n≥30 OOS** (was 5); current eligible set is empty → fail closed.  
4. **Live mode needs env ACK + phrase** `I_ACCEPT_MICRO_LIVE_RISK`.  
5. **Caps still ₹1000 / $10** until ladder step-up after positive rolling expectancy.  
6. **Weekly freeze** can kill + revoke eligibility if paper expectancy collapses.  
7. **Every order** can leave an audit receipt under `models/decision_receipts.jsonl` (created on first trade).

---

## Ops checklist (post-change)

- [x] Validate profiles script  
- [x] Readiness unit tests  
- [ ] Re-run `scripts/run_adaptive_edge_search.py` until ≥3 names clear n≥30 (Stage B pass)  
- [ ] Run session day-sim under market hours / recent session date with real 5m data  
- [ ] Months of paper → Stage C metrics on `/exec/paper-metrics` before any micro-live env flip  

---

## Diff tip

```powershell
git diff 1b96e1d --stat
git status
```
