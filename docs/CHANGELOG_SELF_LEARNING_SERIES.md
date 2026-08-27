# Change log — self-learning + live exec series

**Range:** `eea5d87` → `1b96e1d` (6 commits on `master`)  
**Author dates:** 2026-08-27 (author-backdated split push)  
**Net:** 49 files, ~+13.8k / −48 lines  

**Not investment advice.**

This log covers the committed stack that added **prediction-event self-learning**, **broker/exec**, **adaptive edge / strategy lab**, **APIs + scripts**, **Live dash**, and **docs/artifacts**. It does **not** include the later uncommitted readiness-gates work (see `docs/CHANGES_SINCE_1b96e1d_READINESS.md`).

---

## Commit map (oldest → newest)

| SHA | Subject |
|-----|---------|
| `4fc2647` | Add prediction-event self-learning loop and exec schema |
| `53d0cd3` | Add paper/Alpaca/Kite broker adapters with risk and sizing |
| `54df7c8` | Add strategy lab, ensemble router, and adaptive edge gate |
| `b25ac7f` | Wire auto-exec APIs, scheduler flatten jobs, and strategy scripts |
| `66e5953` | Add Live trading dash with tape polling and day-sim ledger |
| `1b96e1d` | Document live exec/adaptive edge and check in backtest artifacts |

---

## 1. Self-learning algorithm (`4fc2647`)

**Why:** Close the loop from scored signals → labeled outcomes → gated model/peer updates without memorizing holdout.

### Schema / models
- Migration `migrations/versions/005_prediction_events_and_exec.py`
  - Tables: `prediction_events`, `orders`, `fills`, `trade_risk_state` (and related exec seed caps)
- `packages/core/models.py` — ORM for prediction events + exec entities
- `packages/core/config.py` — online-learn + exec settings (`ml_online_learn_*`, `exec_mode_*`, ACK flags, etc.)

### Core loop
| Module | Role |
|--------|------|
| `packages/processor/prediction_events.py` | Upsert prediction events; label from forward returns; record live PnL events |
| `packages/processor/learn.py` | Champion/challenger retrain on **frozen labeled** `bulk_ml` events; feed adaptive peer bins from labeled outcomes |
| `packages/processor/live_calibrate.py` | Live probability shift only (min trades gate; max shift cap) — not TP/SL retune |
| `packages/processor/forward_backfill.py` | Hook: labels → prediction events |
| `packages/processor/scoring.py` | Emit/update prediction events on score |
| `packages/processor/features.py` | Feature wiring for the learn path |

### Learning rules (as shipped)
- Retrain only on labeled frozen events with feature vectors
- Accuracy-drop gate (`ml_max_accuracy_drop`) before promoting challenger
- Adaptive online path updates **peer hit memory / effective target** from wins — not offline TP/SL search
- Live PnL events stay out of the LightGBM training mix (calibration / adaptive bins)

**Diff size:** 9 files, +753 / −5

---

## 2. Broker execution (`53d0cd3`)

Paper-first auto-exec under per-market caps.

| Path | Role |
|------|------|
| `packages/broker/paper.py` | In-process paper broker + slippage |
| `packages/broker/alpaca.py` | Alpaca paper/live orders |
| `packages/broker/kite.py` | Kite (IN) adapter |
| `packages/broker/risk.py` | Kill switch, arm, notional/daily caps (₹1000 / $10 defaults) |
| `packages/broker/sizing.py` | Confidence-scaled notional |
| `packages/broker/session.py` | IN/US session + flatten windows |
| `packages/broker/executor.py` | Authorize → size → place → persist order/fill |
| `packages/broker/daytrade.py` | Day-book flatten + ORB scan job |
| `packages/broker/base.py` | Shared request/result types |

**Diff size:** 10 files, +1007

---

## 3. Strategy lab + adaptive edge (`54df7c8`)

| Path | Role |
|------|------|
| `packages/processor/strategies.py` | Classic TA + `intraday_orb` (refuses daily misuse) + regime helpers + verify report |
| `packages/processor/strategy_audit.py` | Per-ticker playbook soft/ambition pass |
| `packages/processor/adaptive_edge.py` | Expanding peer gate, path TP/SL labels, 85% ambition target, anti-memorization |
| `packages/processor/ensemble.py` | Live router (bulk_ml / adaptive / playbooks / vetoes) |
| `packages/processor/day_sim.py` | Paper day replay ledger |
| `packages/processor/sentiment.py` | WSB heat as filter/veto |

**Adaptive edge ideas shipped:** expanding window peers, fixed a-priori 85% target, holdout not used to pick TP/SL, capped peer memory, per-ticker profiles.

**Diff size:** 6 files, +1927

---

## 4. APIs, scheduler, scripts, tests (`b25ac7f`)

- `packages/api/main.py` — `/exec/status|orders|arm|kill|strategies|playbooks|adaptive-profiles|day-sim|live`, learn job hooks
- `packages/ingest/scheduler.py` — IN/US flatten jobs; strategy seed
- `packages/processor/jobs.py` — job wiring
- Scripts:
  - `scripts/paper_5y_backtest.py`
  - `scripts/run_adaptive_edge_search.py`
  - `scripts/run_strategy_benchmark.py`
- `tests/test_online_learn.py`
- `.env.example` — exec / broker / learn env knobs

**Diff size:** 8 files, +1123

---

## 5. Live dashboard (`66e5953`)

- `apps/dashboard/src/pages/ExecPage.tsx` — Live tape (5s), arm/kill, day-sim ledger/PnL
- Nav: `App.tsx`, `Layout.tsx` — “Live” `/exec`
- Minor portfolio page link tweak

**Diff size:** 4 files, +486 / −1

---

## 6. Docs + backtest artifacts (`1b96e1d`)

- `README.md`, `docs/ML_TRAINING.md`, **new** `docs/STRATEGIES.md`
- `.gitignore` model/tooling hygiene
- Checked-in artifacts under `models/`:
  - `adaptive_edge_backtest.json`, `adaptive_edge_state.json`
  - `ticker_adaptive_profiles.json`, `ticker_playbooks.json`
  - `paper_5y_backtest.json`, `hit_rate_ladder.json`
  - `benchmark_results.json`, `day_sim_2024-08-23.json`

**Diff size:** 12 files, +8538 / −42

---

## How the self-learning pieces connect

```text
Signal / score
    → prediction_events (upsert)
    → forward labels / live fills
    → learn.py
         ├─ LightGBM challenger (frozen bulk_ml rows only)
         └─ adaptive peer bins (labeled wins)
    → live_calibrate.py (prob shift)
    → ensemble / adaptive_edge decide fire
    → executor (paper|live under risk caps)
    → orders + fills (+ optional live_pnl events)
```

---

## Reproduce / inspect

```powershell
git log --oneline eea5d87..1b96e1d
git show 4fc2647 --stat
git diff --stat eea5d87..1b96e1d
```

Key entrypoints:
- Learn: `packages/processor/learn.py`, `prediction_events.py`, `live_calibrate.py`
- Edge: `packages/processor/adaptive_edge.py`
- Exec: `packages/broker/executor.py`, `risk.py`
- UI: `apps/dashboard/src/pages/ExecPage.tsx`
- Tests: `tests/test_online_learn.py`

---

## Related (not in this commit range)

Uncommitted readiness work after `1b96e1d` (session day-sim, n≥30 ambition, paper health, dual ACK, cap ladder, receipts) is listed separately in:

`docs/CHANGES_SINCE_1b96e1d_READINESS.md`
