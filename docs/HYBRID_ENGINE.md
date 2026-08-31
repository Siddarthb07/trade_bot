# Hybrid Engine

North star: **most profits** — compound growth of keepable equity (paper → live micro).

## Lanes

| Lane | Meaning |
|------|---------|
| `product` | Risk-capped (guards). Default for paper/live path. |
| `stretch` | Higher risk budget; may chase ceiling with SL still on. |
| `research` | Raw OR-width heroes. **Not live-eligible.** Celebrated with a research badge only. |

## Aspiration ceiling vs primary score

- **Ceiling:** frozen raw `in_tr10_orwidth_chase5_75x` compounds on July/Aug/benchmark windows (`models/benchmarks/orwidth_ceiling_floor.json`).
- **Floor:** guarded configs on the same windows.
- **Primary score:** `compound + 2.5 * min(0, worst+6) - 0.35 * DD` — optimizes keepable profit.

## Stack

- `packages/processor/hybrid/` — chooser, ticker ranks, engine, ledger, wins
- `packages/processor/benchmarks.py` — fixtures + compare
- API: `/exec/hybrid-sim`, `/exec/hybrid/benchmarks|learning|wins|trades|strategies`, `/market/intraday-history`
- Dash: **Hybrid Lab** at `/hybrid` (Session Desk / Trade Book / Strategies)

## Recognition stack (deferred)

**Rejected for this cycle:** a full L0–L4 “recognition cathedral” (HMM / agreement / Kelly / microstructure stubs) on yfinance 5m. Aug MTD product was still **−23.6%** under guards — the binding constraint is *when to sit out / whether a proposed ORB bet should fire*, not detector density. 8–10%/day session-close remains oracle-unreachable (see `DAY_SIM_METHODS_LOG.md`).

**Deferred thin slice (only after Lab makes skips/fills legible):** one pre-registered ablation — baseline product vs **cash expert** and/or **meta-label veto** (no HMM, no agreement τ, no Kelly) on `july_chop` + `benchmark_15d`. Win = `primary_score` up **and** worst-day not worse than floor by a locked X. Fail → recognition stays docs-only. Do **not** scaffold `packages/processor/hybrid/recognition/` until that gate is written and run.

## Run

```bash
# unit tests (no network)
python -m pytest tests/test_hybrid_engine.py tests/test_session_guard.py -q

# one hybrid day (needs market data / cache)
python -c "from processor.hybrid import simulate_hybrid_day; import json; print(json.dumps(simulate_hybrid_day(asof='2026-08-26', lane='product'), indent=2)[:800])"
```

## Wins

Milestones append to `models/hybrid_wins.jsonl` with lane disclaimers. Research spikes never auto-promote into product language.
