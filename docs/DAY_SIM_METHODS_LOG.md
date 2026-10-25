# Day-Sim Methods Log — 10% Daily Minimum Goal

> Living experiment log for sim-only session replay toward **>=10% return on every benchmark day**.  
> Not live-eligible. Numbers sourced from JSON reports only.

---

## Goal status

| Metric | Value |
|--------|-------|
| Target (ambition) | **>=10.0% return on every session day** |
| Pass floor (IN compound) | **>=8.0% every session day** — pool rolls to next day (`run_in_compound_search.py`) |
| Benchmark window | **2026-08-13 -> 2026-08-28** (12 sessions; IN unless noted) |
| Capital | INR 10,000 (US configs in target-10 search: USD 10,000) |
| Goal met (10% every day) | **NO** |
| Goal met (8% IN compound) | **NO** — 0/16 full sweep + 0/4 OR-width; see [oracle-realistic ceiling](#g-oracle-realistic-session-close--costs) |
| Oracle ceiling (session-close) | **8% every day impossible** even with perfect ticker pick — min day +5.83% best at 8% target sizing; Aug-18 best move 0.11% |
| Goal met (4% every day, oracle) | **NO** — oracle hit@4=0/12; see §I |
| Goal met (5% every day, oracle) | **NO** — oracle hit@5=0/12; see §I |
| Break-even month (bake-off §J) | **PASS** — July copy-pro +5.39%; scaled use60 July **+6.39%**; Aug use60 **+13.42%** after bulk backfill (§K) |
| Live eligibility | **None** — sim research only |

---

## Current best (honest)

No method meets the goal. Best observed results by sweep type:

| Sweep | Best config | Why it ranks first | Still fails goal because |
|-------|-------------|--------------------|--------------------------|
| Filter (1x, no target sizing) | `orb_scalp_15pct` | Highest avg among trading configs (-0.112%) | 0/12 days >=10%; max day +0.001% |
| Leverage (confidence-scaled) | `baseline_1x_top1` | Best score_vs_target (-5.178); least drawdown at 1x | 0/12 days >=10%; avg -0.253% |
| Target-return search | `tr10_us_50x` | Best min-day (-6.87%) and avg (+0.107%) | 12/12 days below 10%; max day 9.249% |
| IN compound (16 configs) | `in_tr8_100x_tight` | Best min-day (-5.52%); 4 zero-trade days from fetch gaps | 0/12 days >=8%; compound -18% |
| IN OR-width chase5 | `in_tr8_orwidth_chase5_75x` | 4/12 days >=8%; avg +7.29%; compound +77% | Min day -20.5%; wrong picks + high lev |
| Oracle-realistic (perfect pick) | session-close + costs @75x | Best possible with hindsight ticker | 0/12 days >=8% at 8% target; min +5.83% |

**Takeaway:** ORB + adaptive gates in the Aug-2026 chop window produce no durable 10%-per-day edge. Leverage and target-return sizing amplify variance without fixing hit rate. **Oracle-realistic sim proves the 8% every-day floor is unreachable on session-close exits** in this window — even picking the best ticker each day, several sessions cap below 8% because ORB→close moves are 0.1–0.7%.

---

## Methods tried

**Status key:** `VALIDATED` = run complete, numbers recorded | `FAILED` = does not meet >=10% every day | `IN_PROGRESS` = not yet run

**Code (all modes):** `packages/processor/day_sim.py` — `simulate_day()` / `_simulate_session_day()`  
**Leverage sizing:** `packages/broker/sizing.py` — `confidence_leverage()`, `leverage_for_target()`  
**Target-return universe:** `packages/processor/strategies.py` — vol-momentum ORB selection

---

### A. Filter-mode sweep (1x leverage, no target_return)

Report: `models/day_sim_experiment_report.json` (generated 2026-08-28T15:35:58+05:30)  
Script: `python scripts/run_day_sim_experiments.py --grid filter`

#### A1. strict_baseline

| Field | Value |
|-------|-------|
| **Method** | Strict adaptive gate — peer + confidence filters |
| **Config** | `filter_mode=strict`, conf_floor=0.70, max_positions=3, leverage=1x |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | 0.00% / 0.00% / 0.00% |
| **Hit rate** | n/a (0 trades) |
| **Trades/day** | 0.0 |
| **Days >=10%** | 0/12 |
| **Verdict** | Peer gate blocks all entries in this window. Capital preserved, zero edge, goal impossible without trades. |

#### A2. relaxed_default

| Field | Value |
|-------|-------|
| **Method** | Relaxed gate — lower conf, skip strict peer |
| **Config** | `filter_mode=relaxed`, conf_floor=0.58, max_positions=5 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -0.158% / -0.389% / -0.042% |
| **Hit rate** | 7.0% (pooled) |
| **Trades/day** | 3.58 |
| **Days >=10%** | 0/12 |
| **Verdict** | More trades than strict, steady small bleed after ~30bps RT costs. |

#### A3. relaxed_scalp

| Field | Value |
|-------|-------|
| **Method** | Relaxed + tight scalp TP/SL |
| **Config** | `filter_mode=relaxed`, conf_floor=0.52, max_positions=6, tp=1.2%, sl=0.6%, horizon=4 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -0.112% / -0.325% / +0.001% |
| **Hit rate** | 4.6% |
| **Trades/day** | 3.67 |
| **Days >=10%** | 0/12 |
| **Verdict** | Tighter exits do not overcome chop; identical path to orb scalp variant. |

#### A4. relaxed_max_freq

| Field | Value |
|-------|-------|
| **Method** | Relaxed max frequency — skip peer gate |
| **Config** | `filter_mode=relaxed`, conf_floor=0.48, max_positions=6, min_fire=0.48, skip_peer_gate=true |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -0.134% / -0.324% / -0.035% |
| **Hit rate** | 6.8% |
| **Trades/day** | 3.67 |
| **Days >=10%** | 0/12 |
| **Verdict** | Higher fire rate, same loss profile as orb_only_low. |

#### A5. relaxed_trend_only

| Field | Value |
|-------|-------|
| **Method** | Relaxed + regime filter trend_up only |
| **Config** | `filter_mode=relaxed`, conf_floor=0.55, max_positions=5, regime_allow=[trend_up] |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | 0.00% / 0.00% / 0.00% |
| **Hit rate** | n/a |
| **Trades/day** | 0.0 |
| **Days >=10%** | 0/12 |
| **Verdict** | No trend_up regime days in window; filter too tight, flat book. |

#### A6. orb_scalp_15pct *(best filter sweep)*

| Field | Value |
|-------|-------|
| **Method** | ORB-only scalp — 1.5% TP |
| **Config** | `filter_mode=orb_only`, conf_floor=0.52, max_positions=6, tp=1.5%, sl=0.7%, horizon=4 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -0.112% / -0.325% / +0.001% |
| **Hit rate** | 4.6% |
| **Trades/day** | 3.67 |
| **Days >=10%** | 0/12 |
| **Verdict** | Best filter-sweep score but still net negative; ORB breakouts fail in range-bound tape. |

#### A7. orb_scalp_1pct

| Field | Value |
|-------|-------|
| **Method** | ORB-only ultra-tight scalp |
| **Config** | `filter_mode=orb_only`, conf_floor=0.52, max_positions=6, tp=1.0%, sl=0.5%, horizon=3 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -0.116% / -0.309% / -0.037% |
| **Hit rate** | 2.3% |
| **Trades/day** | 3.67 |
| **Days >=10%** | 0/12 |
| **Verdict** | Tighter TP reduces hit rate further; no day positive. |

#### A8. orb_max_freq

| Field | Value |
|-------|-------|
| **Method** | ORB max frequency — low conf, tight TP |
| **Config** | `filter_mode=orb_only`, conf_floor=0.45, max_positions=6, tp=0.8%, sl=0.4%, horizon=3 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -0.116% / -0.309% / -0.037% |
| **Hit rate** | 2.3% |
| **Trades/day** | 3.67 |
| **Days >=10%** | 0/12 |
| **Verdict** | Same outcome as orb_scalp_1pct; frequency without edge adds costs. |

#### A9. orb_only_low

| Field | Value |
|-------|-------|
| **Method** | ORB-only default exits, low conf |
| **Config** | `filter_mode=orb_only`, conf_floor=0.50, max_positions=6 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -0.134% / -0.324% / -0.035% |
| **Hit rate** | 6.8% |
| **Trades/day** | 3.67 |
| **Days >=10%** | 0/12 |
| **Verdict** | Default TP/SL with low conf still loses after costs. |

#### A10. orb_only_mid

| Field | Value |
|-------|-------|
| **Method** | ORB-only mid conf |
| **Config** | `filter_mode=orb_only`, conf_floor=0.55, max_positions=5 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -0.158% / -0.389% / -0.042% |
| **Hit rate** | 7.0% |
| **Trades/day** | 3.58 |
| **Days >=10%** | 0/12 |
| **Verdict** | Matches relaxed_default losses — ORB path dominates. |

#### A11. orb_swing_2pct

| Field | Value |
|-------|-------|
| **Method** | ORB swing — wider TP/SL |
| **Config** | `filter_mode=orb_only`, conf_floor=0.55, max_positions=4, tp=2.0%, sl=1.0%, horizon=8 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -0.193% / -0.370% / -0.019% |
| **Hit rate** | 5.3% |
| **Trades/day** | 3.17 |
| **Days >=10%** | 0/12 |
| **Verdict** | Widest filter-sweep losses; swing horizon does not help in chop. |

#### A12. orb_trend_only

| Field | Value |
|-------|-------|
| **Method** | ORB + trend_up regime only |
| **Config** | `filter_mode=orb_only`, conf_floor=0.52, max_positions=5, tp=1.5%, sl=0.7%, horizon=5, regime_allow=[trend_up] |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | 0.00% / 0.00% / 0.00% |
| **Hit rate** | n/a |
| **Trades/day** | 0.0 |
| **Days >=10%** | 0/12 |
| **Verdict** | Regime gate blocks all trades; same as relaxed_trend_only. |

#### A13. aggressive_default

| Field | Value |
|-------|-------|
| **Method** | Aggressive filter — lowest conf, max positions |
| **Config** | `filter_mode=aggressive`, conf_floor=0.48, max_positions=6 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -0.112% / -0.325% / +0.001% |
| **Hit rate** | 4.6% |
| **Trades/day** | 3.67 |
| **Days >=10%** | 0/12 |
| **Verdict** | Collapses to same path as orb scalp; aggression without edge is noise. |

#### A14. aggressive_wide_tp

| Field | Value |
|-------|-------|
| **Method** | Aggressive + wide TP/SL |
| **Config** | `filter_mode=aggressive`, conf_floor=0.48, max_positions=6, tp=2.5%, sl=1.2%, horizon=6 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -0.133% / -0.242% / -0.054% |
| **Hit rate** | 6.8% |
| **Trades/day** | 3.67 |
| **Days >=10%** | 0/12 |
| **Verdict** | Slightly higher hit rate, still all days negative; costs dominate. |

---

### B. Leverage experiments (confidence-scaled, 1x-30x)

Report: `models/day_sim_leverage_experiment_report.json` (generated 2026-08-28T16:14:54+05:30)  
Script: `scripts/run_day_sim_experiments.py`  
**Sim-only margin model — not live-eligible.**

#### B1. baseline_1x_top1 *(best leverage sweep)*

| Field | Value |
|-------|-------|
| **Method** | 1x baseline — top-1 ORB position |
| **Config** | `filter_mode=orb_only`, conf_floor=0.55, max_positions=1, tp=1.5%, sl=0.7%, horizon=4, max_leverage=1.0 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -0.253% / -0.490% / +0.003% |
| **Hit rate** | 0.0% |
| **Trades/day** | 1.0 |
| **Days >=10%** | 0/12 |
| **Verdict** | Best leverage-sweep score; concentration reduces bleed vs multi-pos but no TP hits recorded. |

#### B2. baseline_1x_scalp

| Field | Value |
|-------|-------|
| **Method** | 1x baseline — 3-position scalp |
| **Config** | `filter_mode=orb_only`, conf_floor=0.52, max_positions=3, tp=1.5%, sl=0.7%, horizon=4, max_leverage=1.0 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -0.202% / -0.420% / -0.093% |
| **Hit rate** | 0.0% |
| **Trades/day** | 2.58 |
| **Days >=10%** | 0/12 |
| **Verdict** | Multi-pos 1x still net negative every day. |

#### B3. lev5x_scalp_3pos

| Field | Value |
|-------|-------|
| **Method** | 5x leverage — 3-position scalp |
| **Config** | `filter_mode=orb_only`, conf_floor=0.52, max_positions=3, tp=1.5%, sl=0.7%, horizon=4, max_leverage=5.0 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -0.474% / -1.310% / -0.135% |
| **Hit rate** | 0.0% |
| **Trades/day** | 2.58 |
| **Days >=10%** | 0/12 |
| **Verdict** | 5x amplifies losses; worst day -1.31%. |

#### B4. lev10x_top1

| Field | Value |
|-------|-------|
| **Method** | 10x confidence-scaled — top-1 |
| **Config** | `filter_mode=orb_only`, conf_floor=0.52, max_positions=1, tp=1.5%, sl=0.7%, horizon=4, max_leverage=10.0, leverage_conf_full=0.75 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -1.943% / -4.903% / +0.030% |
| **Hit rate** | 0.0% |
| **Trades/day** | 1.0 |
| **Days >=10%** | 0/12 |
| **Verdict** | Worst day nearly -5%; leverage on zero hit rate is destructive. |

#### B5. lev10x_wide_tp_top1

| Field | Value |
|-------|-------|
| **Method** | 10x — wide TP (3%) top-1 |
| **Config** | `filter_mode=orb_only`, conf_floor=0.55, max_positions=1, tp=3.0%, sl=1.2%, horizon=8, max_leverage=10.0 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -1.430% / -4.394% / 0.00% |
| **Hit rate** | 0.0% |
| **Trades/day** | 0.75 |
| **Days >=10%** | 0/12 |
| **Verdict** | Wide TP at 10x produces deeper drawdowns without TP hits. |

#### B6. lev15x_top1

| Field | Value |
|-------|-------|
| **Method** | 15x confidence-scaled — top-1 |
| **Config** | `filter_mode=orb_only`, conf_floor=0.55, max_positions=1, tp=1.5%, sl=0.7%, horizon=4, max_leverage=15.0, leverage_conf_full=0.78 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -1.809% / -7.355% / +0.045% |
| **Hit rate** | 0.0% |
| **Trades/day** | 1.0 |
| **Days >=10%** | 0/12 |
| **Verdict** | Single day -7.4%; margin call territory in sim. |

#### B7. lev15x_high_conf

| Field | Value |
|-------|-------|
| **Method** | 15x — relaxed filter + high-conf floor |
| **Config** | `filter_mode=relaxed`, conf_floor=0.58, high_conf_floor=0.72, max_positions=1, tp=1.8%, sl=0.8%, horizon=5, max_leverage=15.0 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -0.226% / -0.968% / +0.129% |
| **Hit rate** | 0.0% |
| **Trades/day** | 0.75 |
| **Days >=10%** | 0/12 |
| **Verdict** | Best single-day return in leverage sweep (+0.129%) but sparse trades and -0.97% worst day. |

#### B8. lev20x_top1

| Field | Value |
|-------|-------|
| **Method** | 20x confidence-scaled — top-1 |
| **Config** | `filter_mode=orb_only`, conf_floor=0.55, max_positions=1, tp=2.0%, sl=0.8%, horizon=5, max_leverage=20.0, leverage_conf_full=0.80 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -2.840% / -8.375% / -0.097% |
| **Hit rate** | 0.0% |
| **Trades/day** | 1.0 |
| **Days >=10%** | 0/12 |
| **Verdict** | No positive days; -8.4% session loss on worst day. |

#### B9. lev20x_top2

| Field | Value |
|-------|-------|
| **Method** | 20x — top-2 ORB positions |
| **Config** | `filter_mode=orb_only`, conf_floor=0.52, max_positions=2, tp=1.5%, sl=0.7%, horizon=4, max_leverage=20.0 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -1.984% / -5.879% / -0.434% |
| **Hit rate** | 0.0% |
| **Trades/day** | 1.92 |
| **Days >=10%** | 0/12 |
| **Verdict** | Diversification at 20x does not help; all days negative. |

#### B10. lev20x_wide_tp_top1

| Field | Value |
|-------|-------|
| **Method** | 20x — wide TP (4%) top-1 |
| **Config** | `filter_mode=orb_only`, conf_floor=0.55, max_positions=1, tp=4.0%, sl=1.5%, horizon=10, max_leverage=20.0 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -2.565% / -8.654% / 0.00% |
| **Hit rate** | 0.0% |
| **Trades/day** | 0.75 |
| **Days >=10%** | 0/12 |
| **Verdict** | Worst day -8.65%; wide TP never triggers at 20x. |

#### B11. lev25x_aggressive_top1

| Field | Value |
|-------|-------|
| **Method** | 25x — aggressive filter top-1 |
| **Config** | `filter_mode=aggressive`, conf_floor=0.50, max_positions=1, tp=2.0%, sl=0.8%, horizon=5, max_leverage=25.0 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -1.194% / -2.259% / 0.00% |
| **Hit rate** | 3.7% |
| **Trades/day** | 2.25 |
| **Days >=10%** | 0/12 |
| **Verdict** | Only leverage config with any pooled hits, still deeply negative avg. |

#### B12. lev25x_top1_high

| Field | Value |
|-------|-------|
| **Method** | 25x — high conf floor |
| **Config** | `filter_mode=orb_only`, conf_floor=0.58, high_conf_floor=0.68, max_positions=1, tp=2.0%, sl=0.8%, horizon=5, max_leverage=25.0 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -4.130% / -12.028% / 0.00% |
| **Hit rate** | 0.0% |
| **Trades/day** | 0.67 |
| **Days >=10%** | 0/12 |
| **Verdict** | Worst day -12%; high conf does not prevent blow-ups at 25x. |

#### B13. lev30x_allin_best

| Field | Value |
|-------|-------|
| **Method** | 30x all-in — wide TP best guess |
| **Config** | `filter_mode=orb_only`, conf_floor=0.50, max_positions=1, tp=3.5%, sl=1.2%, horizon=8, max_leverage=30.0 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -6.832% / -17.983% / 0.00% |
| **Hit rate** | 0.0% |
| **Trades/day** | 0.75 |
| **Days >=10%** | 0/12 |
| **Verdict** | Catastrophic tail — worst day -18%; sim-only curiosity, not a strategy. |

#### B14. lev30x_extreme_top1

| Field | Value |
|-------|-------|
| **Method** | 30x extreme — high conf gates |
| **Config** | `filter_mode=orb_only`, conf_floor=0.60, high_conf_floor=0.70, max_positions=1, tp=2.5%, sl=1.0%, horizon=6, max_leverage=30.0 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -7.163% / -16.596% / 0.00% |
| **Hit rate** | 0.0% |
| **Trades/day** | 0.67 |
| **Days >=10%** | 0/12 |
| **Verdict** | Worst leverage sweep avg (-7.16%); extreme sizing without edge erases capital in sim. |

---

### C. Target-return filter (vol-momentum universe + HL exits + leverage_for_target)

Report: `models/target_10_search_report.json` (generated 2026-08-28T17:25:12+05:30)  
Script: `scripts/run_target_10_search.py`  
**Pass criterion:** >=10% on **every** session day. Uses `filter_mode=target_return`, vol-ranked universe, HL bar exits, leverage sized to 10% on TP hit.

#### C1. tr10_in_25x

| Field | Value |
|-------|-------|
| **Method** | IN target_return — 25x cap |
| **Config** | `filter_mode=target_return`, market=IN, max_leverage=25, conf_floor=0.55, min_or_pct=0.003, target_return_pct=10, HL exits |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -4.001% / -13.223% / +6.363% |
| **Hit rate** | n/a (per-trade exits vary) |
| **Trades/day** | ~1.0 |
| **Days >=10%** | 0/12 |
| **Verdict** | IN vol names lose even with target-sized leverage; max day 6.4% misses floor. |

#### C2. tr10_in_50x

| Field | Value |
|-------|-------|
| **Method** | IN target_return — 50x cap |
| **Config** | `filter_mode=target_return`, market=IN, max_leverage=50, conf_floor=0.52, min_or_pct=0.0025, target_return_pct=10 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -4.074% / -13.493% / +6.493% |
| **Hit rate** | n/a |
| **Trades/day** | ~1.0 |
| **Days >=10%** | 0/12 |
| **Verdict** | Higher leverage cap does not improve IN path vs 25x; same failure mode. |

#### C3. tr10_in_50x_tight_or

| Field | Value |
|-------|-------|
| **Method** | IN target_return — tight opening range + tight TP |
| **Config** | `filter_mode=target_return`, market=IN, max_leverage=50, conf_floor=0.58, min_or_pct=0.005, tp_override=0.008, target_return_pct=10 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -1.534% / -8.623% / +3.657% |
| **Hit rate** | n/a |
| **Trades/day** | ~0.8 (some zero-trade days) |
| **Days >=10%** | 0/12 |
| **Verdict** | Tighter OR filter reduces trades but not losses; best IN target_return min-day still -8.6%. |

#### C4. tr10_in_75x

| Field | Value |
|-------|-------|
| **Method** | IN target_return — 75x cap |
| **Config** | `filter_mode=target_return`, market=IN, max_leverage=75, conf_floor=0.52, min_or_pct=0.002, target_return_pct=10 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -4.074% / -13.493% / +6.493% |
| **Hit rate** | n/a |
| **Trades/day** | ~1.0 |
| **Days >=10%** | 0/12 |
| **Verdict** | Identical to 50x IN — leverage cap not binding on this path. |

#### C5. tr10_in_100x

| Field | Value |
|-------|-------|
| **Method** | IN target_return — 100x cap |
| **Config** | `filter_mode=target_return`, market=IN, max_leverage=100, conf_floor=0.50, min_or_pct=0.002, target_return_pct=10 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -4.074% / -13.493% / +6.493% |
| **Hit rate** | n/a |
| **Trades/day** | ~1.0 |
| **Days >=10%** | 0/12 |
| **Verdict** | 100x cap still cannot force 10%/day when TP is not hit. |

#### C6. tr10_us_50x *(best target-return search)*

| Field | Value |
|-------|-------|
| **Method** | US target_return — 50x cap |
| **Config** | `filter_mode=target_return`, market=US, max_leverage=50, conf_floor=0.52, min_or_pct=0.002, target_return_pct=10, currency=USD |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (US) |
| **Avg / min / max return** | +0.107% / -6.870% / +9.249% |
| **Hit rate** | n/a |
| **Trades/day** | 1.0 |
| **Days >=10%** | 0/12 |
| **Verdict** | Closest to goal — max day 9.25% and positive avg — but 12/12 days below 10% floor. |

#### C7. tr10_us_75x

| Field | Value |
|-------|-------|
| **Method** | US target_return — 75x cap |
| **Config** | `filter_mode=target_return`, market=US, max_leverage=75, conf_floor=0.50, min_or_pct=0.0015, target_return_pct=10 |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (US) |
| **Avg / min / max return** | +0.107% / -6.870% / +9.249% |
| **Hit rate** | n/a |
| **Trades/day** | 1.0 |
| **Days >=10%** | 0/12 |
| **Verdict** | Same daily path as US 50x in this window; higher cap unused. |

#### C8. tr10_in_50x_session_end

| Field | Value |
|-------|-------|
| **Method** | IN target_return — hold to session close |
| **Config** | `filter_mode=target_return`, market=IN, max_leverage=50, conf_floor=0.52, min_or_pct=0.002, target_return_pct=10, exit_at_session_end=true |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -1.880% / -37.637% / +84.735% |
| **Hit rate** | n/a |
| **Trades/day** | ~1.0 |
| **Days >=10%** | 0/12 (per strict every-day criterion) |
| **Verdict** | Wild sim swings (+85% max) but -38% min day; not live-eligible, fails every-day floor. |

#### C9. tr10_in_75x_session_end

| Field | Value |
|-------|-------|
| **Method** | IN target_return — 75x + session-end exit |
| **Config** | `filter_mode=target_return`, market=IN, max_leverage=75, conf_floor=0.50, min_or_pct=0.002, target_return_pct=10, exit_at_session_end=true |
| **Date tested** | 2026-08-28 |
| **Status** | VALIDATED / **FAILED** |
| **Benchmark** | 2026-08-13 -> 2026-08-28, 12 sessions (IN) |
| **Avg / min / max return** | -1.880% / -37.637% / +84.735% |
| **Hit rate** | n/a |
| **Trades/day** | ~1.0 |
| **Days >=10%** | 0/12 |
| **Verdict** | Identical to 50x session_end; session-close mark-to-market creates unrealistic tail risk in sim. |

---

## IN compound search (8% floor / 10% ambition)

Compounded daily pool on **IN only**. End-of-day cash becomes next session capital.

<!-- AUTO:IN_COMPOUND_START -->
Generated: 2026-08-28T23:13:58.732802+05:30

**Market:** IN (compounded daily pool)
**Pass criterion:** every day >= 8.0% | **Ambition:** >= 10.0%
**Configs passing 8% every day:** 0
**Configs passing 10% every day:** 0

| Config | Min/day% | Avg/day% | Compound% | Final INR | ALL>=8% | ALL>=10% |
|--------|----------|----------|-----------|-----------|---------|----------|
| in_tr8_100x_tight | -7.516 | -2.916 | -30.541 | 6945.85 | no | no |
| in_tr10_100x_tight | -9.394 | -3.645 | -36.895 | 6310.53 | no | no |
| in_tr8_chase3_50x | -18.789 | -3.871 | -41.098 | 5890.23 | no | no |
| in_tr8_75x | -18.789 | -5.12 | -48.808 | 5119.21 | no | no |
| in_tr8_50x | -18.789 | -6.486 | -56.956 | 4304.42 | no | no |
| in_tr10_chase3_50x | -23.486 | -4.839 | -49.587 | 5041.31 | no | no |
| in_tr10_75x | -23.486 | -6.399 | -57.554 | 4244.61 | no | no |
| in_tr10_50x | -23.486 | -6.513 | -58.178 | 4182.25 | no | no |
| in_tr8_chase5_75x_sess | -30.11 | 3.573 | 6.518 | 10651.77 | no | no |
| in_tr8_50x_sess_end | -30.11 | -1.504 | -37.372 | 6262.82 | no | no |
| in_tr10_chase5_75x_sess | -37.637 | 4.467 | -2.349 | 9765.15 | no | no |
| in_tr10_50x_sess_end | -37.637 | -1.88 | -48.641 | 5135.88 | no | no |
<!-- AUTO:IN_COMPOUND_END -->

### F. IN OR-width compound (post-oracle configs)

Rank by widest opening range; session-end exit; compounded pool.

<!-- AUTO:IN_ORWIDTH_START -->
Generated: 2026-08-28T23:08:15.054269+05:30

**Market:** IN (compounded daily pool)
**Pass criterion:** every day >= 8.0% | **Ambition:** >= 10.0%
**Configs passing 8% every day:** 0
**Configs passing 10% every day:** 0

| Config | Min/day% | Avg/day% | Compound% | Final INR | ALL>=8% | ALL>=10% |
|--------|----------|----------|-----------|-----------|---------|----------|
| in_tr8_orwidth_chase5_75x | -20.485 | 7.29 | 77.272 | 17727.25 | no | no |
| in_tr10_orwidth_chase5_75x | -25.606 | 9.113 | 89.573 | 18957.32 | no | no |
| in_tr8_orwidth_sess_50x | -30.11 | 0.29 | -21.529 | 7847.13 | no | no |
| in_tr10_orwidth_sess_50x | -37.637 | 0.363 | -31.642 | 6835.8 | no | no |
<!-- AUTO:IN_ORWIDTH_END -->

## OR-width stress test (15-day windows)

Hero configs stress-tested across random + NIFTY bad/good 15-session windows (5m data floor ~2026-06-08).

<!-- AUTO:ORWIDTH_STRESS_START -->
(pending — stress test running; see breakpoint report below)
<!-- AUTO:ORWIDTH_STRESS_END -->

### OR-width break-point analysis

Generated from `scripts/run_orwidth_breakpoint.py` — day-by-day worst sessions.

| Window | NIFTY | tr10 compound | tr8 compound | Where it breaks |
|--------|-------|---------------|--------------|-----------------|
| March crash (1h) | -10.6% | 0% (no trades) | 0% (no trades) | Strategy flat — 1h ORB never fires in crash |
| July chop | -2.7% | **-71.7%** | **-62.0%** | Jul 8/9/17: wrong OR-width pick + ~25x lev, -1.5% moves |
| Aug chop | -2.1% | -6.5% | -1.3% | Aug 5 TCS -34.6%; Aug 18 ADANIENT -21% |
| Benchmark 15d | -1.7% | **+45.1%** | **+43.5%** | Aug 24-26 tail: VEDL/BAJFINANCE -23/-26% after big win |

**Leverage ceiling:** 50x–200x identical results — effective lev caps ~25x via `leverage_for_target()` + buying power.

**Push limit:** Cannot lever past ~25x on these configs; losses scale with wrong ticker at session-end, not max_leverage knob.

---

### E. Oracle upper bound (ORB entry -> session high, no costs)

| Field | Value |
|-------|-------|
| **Script** | `scripts/run_in_oracle_bounds.py` |
| **Status** | VALIDATED (diagnostic only — not tradable) |
| **Finding** | Every day in window has a ticker with ORB->high move >= 0.63%; at 50x that's >=31% theoretical |
| **Implication** | Move exists intraday but **exit at high is not realizable**; session-close oracle below is the honest ceiling |
| **Worst oracle day** | 2026-08-18 BAJFINANCE 0.631% move to high (0.11% to close) |

### G. Oracle-realistic (session-close + costs)

| Field | Value |
|-------|-------|
| **Script** | `scripts/run_in_oracle_realistic.py` |
| **Status** | VALIDATED (diagnostic — perfect ticker, session-close exit, costs, 75x max lev) |
| **8% target** | min day **+5.83%** (2026-08-13); **0/12 days >=8%**; compound +76.2% |
| **10% target** | min day **+7.29%** (2026-08-13); **0/12 days >=10%**; compound +101.9% |
| **Worst day** | 2026-08-18 BAJFINANCE +0.11% move → **-3.80%** return (fee drag on oversize lev) |
| **Verdict** | **8%/10% every session day is not achievable** on this universe/window with ORB + session-end exit, even with perfect selection |

---

### H. Product guardrails (fix lows, paper-month path)

| Field | Value |
|-------|-------|
| **Problem** | Raw heroes (`in_tr10/tr8_orwidth_chase5_75x`) had +45% compound on benchmark but **-25% to -72%** tails (July) — one bad day wiped the book |
| **Root cause** | `exit_at_session_end=True` skipped intraday SL; leverage sized for upside only; no daily loss halt |
| **Fix** | `packages/processor/session_guard.py` + day_sim: (1) honor SL while winners hold to session close, (2) cap lev so SL ≤ risk budget, (3) halt new entries after daily loss floor |
| **Product config** | `in_tr10_orwidth_chase5_75x_guard` — `max_daily_loss_pct=6`, `max_trade_risk_pct=6`, chase≤2, close-based stops |
| **Paper month** | `python scripts/run_paper_month_orwidth.py --days 22` |
| **Honesty** | Caps wipe the lottery +50–80% days; expect lower compound. Goal is **survivable** paper month, not every-day 10%. No live capital until a full month passes kill-switch checks. |

---

### D. Multi-chase (target_return + max_chase_attempts)

| Field | Value |
|-------|-------|
| **Method** | Same-day retries on next vol-ranked ticker until daily target or attempts exhausted |
| **Code** | `day_sim.py` — `max_chase_attempts` |
| **Status** | **VALIDATED / FAILED** — chase does not fix the floor |
| **tr10_chase_3x50** | min -13.49%, avg -2.83%, max +6.49% — 3 retries hurt vs single IN 50x |
| **tr10_chase_5x75** | min -37.64%, avg +1.05%, max +84.74% — session-end + chase = same tail risk |
| **Days >=10%** | 0/12 both chase configs |
| **Verdict** | Retrying losers same day amplifies drawdown; no path to every-day 10%. |

---

## Target-10 search summary (single-day, no compound)

<!-- AUTO:TARGET10_START -->
Generated: 2026-08-28T18:03:23.306965+05:30

**Goal met:** NO

| Config | Min% | Avg% | Max% | ALL>=10% |
|--------|------|------|------|----------|
| tr10_us_50x | -6.87 | 0.107 | 9.249 | no |
| tr10_us_75x | -6.87 | 0.107 | 9.249 | no |
| tr10_in_50x_tight_or | -8.623 | -1.534 | 3.657 | no |
| tr10_in_25x | -13.223 | -4.001 | 6.363 | no |
| tr10_chase_3x50 | -13.493 | -2.829 | 6.493 | no |
| tr10_in_50x | -13.493 | -4.074 | 6.493 | no |
| tr10_in_75x | -13.493 | -4.074 | 6.493 | no |
| tr10_in_100x | -13.493 | -4.074 | 6.493 | no |
| tr10_chase_5x75 | -37.637 | 1.05 | 84.735 | no |
| tr10_in_50x_session_end | -37.637 | -1.88 | 84.735 | no |
| tr10_in_75x_session_end | -37.637 | -1.88 | 84.735 | no |
<!-- AUTO:TARGET10_END -->

---

## How to update this log

1. **Leverage sweep (1x-30x, confidence-scaled)**  
   ```bash
   python scripts/run_day_sim_experiments.py
   ```  
   Or `--grid leverage` (default). Output: `models/day_sim_leverage_experiment_report.json`

2. **Filter-mode sweep (1x, strict/relaxed/orb/aggressive)**  
   ```bash
   python scripts/run_day_sim_experiments.py --grid filter
   ```  
   Output: `models/day_sim_experiment_report.json`

3. **IN compound search (8% pass / 10% ambition, pool rolls daily)**  
   ```bash
   python scripts/run_in_compound_search.py
   ```  
   Output: `models/in_compound_search_report.json` — patches `AUTO:IN_COMPOUND` block.

4. **Target 10% minimum search (vol-momentum + target_return sizing)**  
   ```bash
   python scripts/run_target_10_search.py
   ```  
   Output: `models/target_10_search_report.json`  
   Replace the block between `AUTO:TARGET10_START` / `AUTO:TARGET10_END`; append **Section C** (and **D** for chase) entries.

5. **Single-day smoke test**  
   ```bash
   python scripts/run_today_in_sim.py
   ```  
   Use for debugging one session before adding to multi-day grid.

6. **New method checklist**  
   - Copy the table template above (Method, Config, Date, Status, Benchmark, Results, Verdict).  
   - Set Status to `IN_PROGRESS` before the run.  
   - After JSON report lands, fill numbers from report only (no hand-edited PnL).  
   - Set `VALIDATED / FAILED`; update **Goal status** and **Current best** if needed.  
   - Add a row to **Changelog** below.

---

---

## I. Push experiment — 4%/5% daily + multi-trade hybrid

> Generated: 2026-08-29 18:20 IST  
> Script: `scripts/run_push_4_5_experiment.py`  
> Window: **2026-08-13 -> 2026-08-28** (12 sessions) · Capital INR 10,000  
> Status: **VALIDATED / research** — not live-eligible. Goal = maximize hit@4 / hit@5 + compound; not every-day floor.

### I1. Oracle ceiling at 4% / 5% / 8% (perfect ticker, session-close, costs, 75x)

| Target | Min/day% | Avg/day% | Max/day% | Compound% | Hit@4 | Hit@5 | Hit@8 | ALL>=4 | ALL>=5 |
|--------|----------|----------|----------|-----------|-------|-------|-------|--------|--------|
| 4% | -1.90 | 2.44 | 3.69 | 33.4 | 0/12 | 0/12 | 0/12 | False | False |
| 5% | -2.38 | 3.05 | 4.62 | 43.1 | 5/12 | 0/12 | 0/12 | False | False |
| 8% | -3.80 | 4.88 | 7.39 | 76.2 | 9/12 | 8/12 | 0/12 | False | False |

**Per-day oracle (target 4% sizing)** — move = best ORB→session-close %:

| Day | Ticker | Move% | Ret% | >=4? | >=5? |
|-----|--------|-------|------|------|------|
| 2026-08-13 | TCS.NS | 1.107 | +2.92 | N | N |
| 2026-08-14 | ADANIENT.NS | 2.144 | +3.44 | N | N |
| 2026-08-17 | TATASTEEL.NS | 1.712 | +3.30 | N | N |
| 2026-08-18 | BAJFINANCE.NS | 0.110 | -1.90 | N | N |
| 2026-08-19 | JSWSTEEL.NS | 1.492 | +3.19 | N | N |
| 2026-08-20 | MARUTI.NS | 0.502 | +1.61 | N | N |
| 2026-08-21 | VEDL.NS | 1.160 | +2.96 | N | N |
| 2026-08-24 | JSWSTEEL.NS | 1.733 | +3.31 | N | N |
| 2026-08-25 | ADANIENT.NS | 3.947 | +3.69 | N | N |
| 2026-08-26 | VEDL.NS | 2.066 | +3.42 | N | N |
| 2026-08-27 | ADANIENT.NS | 0.416 | +1.12 | N | N |
| 2026-08-28 | HDFCBANK.NS | 0.671 | +2.21 | N | N |

**Oracle-unreachable at 4% (this window):** 2026-08-13, 2026-08-14, 2026-08-17, 2026-08-18, 2026-08-19, 2026-08-20, 2026-08-21, 2026-08-24, 2026-08-25, 2026-08-26, 2026-08-27, 2026-08-28

### I2. Multi-trade OR-width push grid

Policies: `raw` = `in_tr10_orwidth_chase5_75x`; `guard` = guarded product. `max_positions` raised (day_sim no longer forces 1 in target_return). `max_chase_attempts = 5` when positions=1 (classic chase); `= 1` when positions>1 (parallel equal-slot). Target return sizing 4% or 5%.

| Policy | Target% | Positions | Compound% | Hit@4 | Hit@5 | Min/day% | Max/day% | Trades/day | MaxDD% |
|--------|---------|-----------|-----------|-------|-------|----------|----------|------------|--------|
| raw | 5 | 1 | +52.19 | 5/12 | 4/12 | -12.80 | +42.37 | 1.00 | 15.0 |
| raw | 4 | 1 | +42.47 | 4/12 | 3/12 | -10.24 | +33.90 | 1.00 | 12.0 |
| raw | 5 | 5 | +2.20 | 2/12 | 2/12 | -3.75 | +8.47 | 4.08 | 11.5 |
| raw | 4 | 5 | +1.90 | 2/12 | 2/12 | -3.00 | +6.78 | 4.08 | 9.2 |
| guard | 5 | 1 | -3.42 | 2/12 | 2/12 | -10.23 | +13.52 | 1.00 | 22.8 |
| guard | 4 | 1 | -3.44 | 2/12 | 2/12 | -10.23 | +13.52 | 1.00 | 22.8 |
| raw | 5 | 3 | -8.59 | 2/12 | 1/12 | -6.14 | +14.12 | 2.67 | 18.8 |
| raw | 5 | 8 | -12.64 | 2/12 | 1/12 | -5.69 | +5.30 | 5.33 | 16.4 |
| raw | 4 | 3 | -6.67 | 1/12 | 1/12 | -4.91 | +11.30 | 2.67 | 15.2 |
| raw | 4 | 8 | -10.15 | 1/12 | 0/12 | -4.55 | +4.24 | 5.33 | 13.3 |
| guard | 5 | 5 | -8.29 | 0/12 | 0/12 | -3.49 | +3.96 | 4.08 | 12.0 |
| guard | 4 | 5 | -8.32 | 0/12 | 0/12 | -3.49 | +3.96 | 4.08 | 12.0 |
| guard | 4 | 8 | -10.79 | 0/12 | 0/12 | -3.22 | +2.48 | 5.33 | 12.4 |
| guard | 5 | 8 | -10.83 | 0/12 | 0/12 | -3.22 | +2.48 | 5.33 | 12.4 |
| guard | 5 | 3 | -14.65 | 0/12 | 0/12 | -4.08 | +3.07 | 2.67 | 15.9 |
| guard | 4 | 3 | -14.71 | 0/12 | 0/12 | -4.08 | +3.07 | 2.67 | 15.6 |

### I3. Verdict

- **Best by hit@4 then compound:** `raw` target=5.0% positions=1 → hit@4=5/12 (41.7%), compound=+52.19%, min/day=-12.80%, trades/day=1.0.
- **Oracle at 4% target sizing:** hit@4=0/12, ALL>=4=False, compound=33.4%, min/day=-1.90%.
- **Takeaway:** Raising trade count cannot beat the oracle move ceiling on dead sessions. Promote to product only if a guard config beats prior `primary_score` without worse tails; otherwise keep as research ceiling map.
- Reports: `models/oracle_4_5_ceiling.json`, `models/push_4_5_experiment.json`.



## J. Break-even bake-off — ORB vs copy-pro

> Generated: 2026-08-29 19:39 IST
> Script: `scripts/run_break_even_bakeoff.py`
> Capital INR 10,000 · capital_use=50% · Status: research / paper

### J1. Method rating (pre-bake-off)

| Rank | Method | Grade | Why |
|------|--------|-------|-----|
| 1 | Oracle session-close | Ceiling only | Move limit; not tradable |
| 2 | Raw OR-width 75x | Lottery A / keepable F | Huge compound / July wipeouts |
| 3 | Push raw tgt=5% 1-pos | Research B+ | +52% window; bad tails |
| 4 | Guarded ORB + sit-out | Product C+ | Aug ~−7% before bake-off |
| 5 | Guarded ORB pre-fix | D | Forced daily bleed |
| 6 | Hybrid product Aug MTD | D | −23.6% |
| 7 | adaptive_edge / TA stubs | Incomplete | Not month-compound wired |
| 8 | Filter / lev sweeps | F for 8–10% goal | No every-day pass |

### J2. Bake-off results

Coverage: `{"ok": true, "total_buys": 13144, "window_buys": 1812, "window_min": "2026-07-01T18:30:00+00:00", "window_max": "2026-07-20T18:30:00+00:00", "data_gap": false}`

| Lane | Window | Compound | PnL INR | Trades | Sit-outs | Avg trade-day PnL | MaxDD | Pass≥0 |
|------|--------|----------|---------|--------|----------|-------------------|-------|--------|
| C | august | -7.22% | -722 | 24 | 8 | -60.18 | 8.8% | False |
| A | august | +0.00% | +0 | 0 | 20 | None | 0.0% | False |
| B | august | +0.00% | +0 | 0 | 20 | None | 0.0% | False |
| A | july_bulk_window | +0.00% | +0 | 0 | 13 | None | 0.0% | False |
| B | july_bulk_window | +5.39% | +539 | 12 | 1 | 44.91 | 4.6% | True |

**Promoted:** `copy_bulk_pro`
**Reports:** `models/break_even_bakeoff.json`

### J3. Verdict

PASS — Lane B (july_bulk_window) compound +5.39% with avg trade-day PnL 44.91. Promoted=copy_bulk_pro.




## K. Copy-pro push — double down on what works

> Generated: 2026-08-29 19:58 IST  
> Script: `scripts/run_copy_pro_push.py`  
> Baseline: bake-off Lane B July +5.39%. Hardening = min investor n≥2, deal ≥₹2.5cr, SL cooldown.

| Config | Window | Compound | PnL | Trades | Avg trade-day | MaxDD | Pass≥0 |
|--------|--------|----------|-----|--------|---------------|-------|--------|
| baseline_bakeoff | july | +5.39% | +539 | 12 | 44.91 | 4.6% | True |
| quality_v1 | july | -6.59% | -659 | 13 | -50.68 | 7.8% | False |
| quality_size60 | july | -7.90% | -790 | 13 | -60.76 | 9.3% | False |
| quality_2slot | july | +4.64% | +464 | 25 | 35.68 | 3.8% | True |
| quality_wr60 | july | -7.25% | -724 | 13 | -55.73 | 8.5% | False |
| baseline_bakeoff | august | +0.00% | +0 | 0 | None | 0.0% | False |
| quality_v1 | august | +0.00% | +0 | 0 | None | 0.0% | False |
| quality_size60 | august | +0.00% | +0 | 0 | None | 0.0% | False |
| quality_2slot | august | +0.00% | +0 | 0 | None | 0.0% | False |
| quality_wr60 | august | +0.00% | +0 | 0 | None | 0.0% | False |

**Best:** `baseline_bakeoff@july`  
**Report:** `models/copy_pro_push.json`



### K2. Scale baseline (no over-filter) — July

Tight WR/n/value filters **hurt**. Scaling only size/slots/cooldown:

| Config | Compound | PnL | Trades | AvgTD | MaxDD |
|--------|----------|-----|--------|-------|-------|
| use60 | +6.39% | +639 | 12 | 53.29 | 5.6% |
| baseline | +5.39% | +539 | 12 | 44.91 | 4.6% |
| use60_cd1 | +4.57% | +457 | 11 | 41.51 | 7.2% |
| scale_best | +4.11% | +411 | 17 | 37.35 | 3.0% |
| lookback2 | +4.01% | +401 | 13 | 30.83 | 7.7% |
| cooldown1 | +3.87% | +387 | 11 | 35.19 | 6.0% |
| slots2_cd1 | +3.36% | +336 | 17 | 30.58 | 2.6% |
| slots2 | -2.49% | -249 | 19 | -20.71 | 3.9% |

**Best scale config:** `use60` (+6.39%). Report: `models/copy_pro_scale.json`.

### K3. August with backfilled bulk + use60

NSE historical backfill added Aug coverage (through 2026-08-27). Promoted `copy_bulk_pro` at **capital_use=60%**:

| Window | Compound | PnL INR | Trades | End equity |
|--------|----------|---------|--------|------------|
| Aug 1–28 | **+13.42%** | **+1,342** | 20 | ₹11,342 |

Report: `models/copy_pro_august_use60.json`. Registry defaults updated to `capital_use_frac=0.6`.

## L. Returns push toward 10%/month (hit-rate)

> Generated: 2026-08-29  
> **Full method write-up:** [`COPY_PRO_10PCT_MONTHLY_METHOD.md`](COPY_PRO_10PCT_MONTHLY_METHOD.md)  
> Scripts: `scripts/run_copy_pro_return_gap.py`, `scripts/run_copy_pro_returns_push.py`  
> Goal: ≥2 of 4 calendar months compound ≥10% on ₹10k; monthly DD ≤25%; mean > ablation (~−6.2%).

### L1. Return-gap audit (ablation baseline)

| Month | Compound | WR | Expectancy ₹ | Margin util | Winner giveback (MFE−realized) |
|-------|----------|-----|--------------|-------------|-------------------------------|
| May | −5.9% | 31% | −74 | 60% | (sparse 5m cache) |
| June | −14.6% | 29% | −117 | 60% | (sparse 5m cache) |
| July | −3.6% | 30% | −65 | 60% | ~3.5% avg |
| August | −0.7% | 40% | −47 | 60% | ~3.9% avg |

Pooled: idle cash ~40%, avg winner giveback ~3.9% → primary lever **soft trail**, then sizing / selective 2nd slot.  
Report: `models/copy_pro_return_gap.json`.

### L2. Push grid (locked: lookback=1, wr_pseudo_n=0, ticker+entity CD=1)

Wave1 = capital_use × soft trail (sit=0). Wave2 = sitout=1 on top-3 (hurt runners). Wave3 = selective 2nd slot (top WR≥0.65 + score gap≥0.5).

| Config | Hit≥10% | Mean | MaxDD | Gate |
|--------|---------|------|-------|------|
| use60 trail off | 0/4 | −6.2% | 32.6% | N |
| use60 trail arm2.5%/1% | 1/4 | +6.9% | 25.3% | N |
| use75 trail arm2.5%/1% | 2/4 | +7.9% | 30.8% | N (DD) |
| use85 trail arm2.5%/1% | 2/4 | +8.5% | 34.4% | N (DD) |
| sitout=1 variants | 0/4 | ~0–1% | ≤25% | N (kills Jul/Aug) |
| **use85 + trail2.5 + sel2** | **3/4** | **+11.2%** | **14.8%** | **Y** |
| use75 + trail2.5 + sel2 | 3/4 | +10.1% | 13.1% | Y |
| use60 + trail2.5 + sel2 | 2/4 | +8.3% | 10.6% | Y |

Winner months (use85 sel2): May −3.4%, June +14.9%, July +12.9%, August +20.5%.

**Promoted product defaults:** `capital_use_frac=0.85`, `soft_trail_arm_pct=0.025`, `soft_trail_pct=0.01`, `max_positions=2` with `bulk_second_min_wr=0.65` / `bulk_second_min_score_gap=0.5`, sitout=0.  
Report: `models/copy_pro_returns_push.json`.

**Honesty:** paper/sim only; May still red; 10%/month is a **hit-rate** (3/4 here), not a guarantee every month. Do not revive pre-lookback Aug +13.4% / July bake-off as current truth without this config.

## M. Pattern Forge + recognition-swarm (2026-08-30)

> Clean-PIT reboot after copy-pro leak. Trace: [`docs/METHOD_BREAK_TRACE.md`](METHOD_BREAK_TRACE.md).

| Item | Status |
|------|--------|
| Recognition swarm port | `packages/processor/hybrid/recognition/` from `godfather/recognition-swarm` |
| No-ruin floor | `packages/processor/no_ruin.py` — ≤40% peak or ≤50% start → cash |
| F&O shorts only | `models/universes/nse_fo_underliers.json` + `fo_universe.py` |
| Two-sided path math | `packages/processor/two_sided.py` |
| Families | `pattern_candle`, `pattern_analog`, `orb_two_sided`, **`hybrid_stock_market`** |
| Hybrid chooser | `packages/processor/pattern_forge/hybrid_chooser.py` — picks family from market regime + stock OR/candle/analog features |
| Unit tests | `tests/test_recognition_stack.py` + `tests/test_pattern_forge_harness.py` + `tests/test_hybrid_stock_chooser.py` |
| Synthetic bake-off | `scripts/run_pattern_forge_bakeoff.py` → `models/method_family_bakeoff.json` |

**Rule:** no real-network backtest until unit tests green. Contaminated +511% is stretch label only.

### M1. Hybrid stock+market chooser (2026-08-30)

| Field | Value |
|-------|-------|
| **Method** | Per-session pick among candle / ORB / analog / cash from regime + stock features |
| **Config** | `family=hybrid_stock_market`, long_only=True, sleeve≈25%, no-ruin on |
| **Market regime** | RELIANCE.NS daily proxy (`market_regime_proxy.py`); soft regime if 20–49 bars |
| **Oct–Dec 2025 (v1, regime=unknown)** | −1.49%, 0/3 green, 53 trades / 1 win-month tally |
| **Oct–Dec 2025 (v2, regime fixed)** | −1.41%, 0/3 green (Oct −0.48 / Nov −0.32 / Dec −0.61), report `benchmark_2025_hybrid_stock_market_c69e25f0-c99.json` |
| **Best knob so far** | `hybrid_sitout` (min_score=0.28, conf≥0.62): **−0.89%**, 0/3 green, fewer trades (41) — still FAIL |
| **Status** | VALIDATED / **FAILED** monthly greens — session 1h ORB→close structurally < ~30bps costs (oracle best-of-12 ≈23bps) |
| **Code** | `hybrid_chooser.py` → `primary_signal` → decision ledger `hybrid_choice` |

### M2. Daily FO swing (clean PIT) — 2026-08-30

| Field | Value |
|-------|-------|
| **Method** | Next-day long: cross-sectional max 1d return in band, r5≥−3%, skip risk_off |
| **Horizon** | Close[T] → close[T+1] on FO underliers (full list ~49) |
| **Costs** | `IN_FO_COST` ~12bps RT (F&O-modeled; **not** cash equity 30bps) |
| **Promoted** | sleeve=30%, lev=8×, band 0.5–6%, daily loss clamp 8% |
| **2025 full year (push8)** | **+41.96%**, **8/12 green**, goal_met=True — `benchmark_2025_daily_swing_9bbe50e5-4fe.json` |
| **Prior conservative** | sleeve=20% lev=2× → only +7.17% (too weak vs ambition) |
| **Red months** | Feb ≈−25% (main DD), Jul/Aug mild, Dec ≈−4.5% |
| **vs contaminated +511%** | That number used live WR with `pit_n=0` — **not a clean target**. Clean push is ~40%/yr class, not 500%. |
| **Status** | VALIDATED / **PASS** gate (≥8/12 + positive year); ambition = keep lifting annual without WR leak |
| **Code** | `daily_swing.py` + `scripts/run_pattern_forge_daily_swing_2025.py` |

### M3. Pattern Forge v2.1 research (2026-08-30)

| Field | Value |
|-------|-------|
| **Locked hero** | `v2` — `models/pattern_forge/v2_latest.json` (+103% 2025, profit_guard, long-only) |
| **Challenger lane** | `v2_1` — FO shorts + hard swarm vetoes + overnight feeds |
| **Hard veto agents** | Regime / CrossMarketOpen / CrossSectionSimilarity / BreadthRegime → cash |
| **Feeds** | `overnight_feeds.py` (SPY / EWJ / ^NSEI PIT; Lab `feed_status`) |
| **Charts** | `GET /exec/pattern-forge/chart` + Pattern Lab DetailPriceChart markers + v2 vs v2_1 equity |
| **Bakeoff** | `scripts/run_v2_1_bakeoff.py` → `v2_1_bakeoff.json`; OOS via `run_pattern_forge_daily_swing_oos.py` |
| **Promote rule** | Clean 2025 ≥ v2 return, loss≤profits, ≥8 green; OOS claim; **never** silent overwrite of `v2_latest.json` |
| **Bakeoff result** | **Do not promote.** Full v2_1 2025 **+86.3%** / 10/12 / worst −10.3% — below locked v2 **+103.2%**. Artefact: `v2_1_bakeoff.json` |
| **Ablation 2025** | frozen_v2 +103.2%; shorts_only +99.9% (worst −17.9%); hard_swarm +100.6%; full v2_1 +86.3% |
| **OOS** | 2023: v2 +130.8% / v2_1 +135.4% (7/12 green); 2024: v2 +59.7% (worst −28.9%) / v2_1 +2.7% (3/12) |
| **Status** | RESEARCH / **not eligible** to replace locked v2 |

### M4. Scrutiny + missing years + v3 attempt (2026-08-30)

| Check | Result |
|-------|--------|
| **Lane of multi-year** | **11×** locked v2 (not product ≤3 / stretch ≤5) |
| **ADANIENT 2023-05-19** | **REAL NSE move** — entry ~₹1956 (LiveMint), exit ~₹2326 (~+18%, Hindu BL / BusinessToday); verify JSON `adani_2023_05_19_verify.json`. Concentration = event risk, not Yahoo artifact. |
| **Why 2019/2021 missing initially** | **Never run** (user list was 2018,2020,2022–2025) — **not** cherry-pick after failure. Later filled: **2019 +37.7%** / **2021 −18.5%**. |
| **Full 8-year standalone** | 6/8 green; red = **2021 (−18.5%)**, **2022 (−15.7%)**. Scorecard: `v2_multi_year.json` (lead with year table; compound = footnote). |
| **v3 confirmed OOS?** | **No.** Pass1 (TS-mom+breadth+vol) → flat/~0%. Pass2 (top_k diversify only) → **destroys** v2 edge (OOS mostly red). Honest: **v2’s return IS single-name concentration**; diversifying removes the headline without a replacement edge. Artefacts: `v3_bakeoff.json`, `v3_bakeoff_pass2.json`, `v3_latest.json` (`confirmed_oos=false`). **`v2_latest.json` untouched.** |

### M5. v3.1 indicator filters — VWAP / volume / 200 EMA (2026-08-31)

| Field | Value |
|-------|-------|
| **Indicators** | 20d rolling **VWAP** (typical price × volume), **rel_volume** (today / 20d avg), **200 EMA** trend filter |
| **Code** | `daily_swing.py` (`stock_daily_features`, `choose_daily_candidate`); OHLCV via `day_sim._fetch_history_ohlcv`; bakeoff `scripts/run_v3_bakeoff_pass3.py` |
| **Hard all-three** | **Too strict** — 2025 **−18%** (127 trades, 2/12 green); early months often 0 trades |
| **Best so far** | **200 EMA only** (`require_above_ema200`): 2023 **+33%**, 2024 **−7%**, 2025 **+8.8%** — beats pass2 (+0.97% on 2025) but **still fails** OOS gate (2024 red, green months) |
| **Soft volume / VWAP** | `min_rel_volume=0.75` + `vol_soft_penalty`; `vwap_score_boost=0.001` — ranking tie-breaks, not hard vetoes |
| **Status** | RESEARCH / **not confirmed OOS**; v2 remains locked hero |

### M6. v4 dual-mode attack/defense (2026-08-31)

| Field | Value |
|-------|-------|
| **Thesis** | v2 concentration in **attack**; **defense** on Nifty&lt;200EMA, breadth stress, October + optional VWAP/vol |
| **Scoring** | `rs_vs_nifty`, `rs_times_r1`, or `raw_r1` |
| **Bakeoff** | `scripts/run_v4_bakeoff.py` → `v4_bakeoff.json`, `v4_latest.json` |
| **Status** | RESEARCH; **`v2_latest.json` never overwritten** |

### M7. v5 frequency + NewsEdge off-market (2026-08-31)

| Field | Value |
|-------|-------|
| **Thesis** | Keep v2 signal; cut bad months via **frequency** (cooldown, loss-streak sit, month cap) + **NewsEdgeScan** (US/Asia overnight tape as news proxy — not NLP headlines) + October size soft |
| **Gates** | max single-trade share **55%**; 2026 YTD uses 2/3 green-month rule |
| **Bakeoff** | `scripts/run_v5_bakeoff.py` → `v5_bakeoff.json` (incl. bad-month delta vs v2) |
| **Status** | RESEARCH; locked v2 untouched |

### M8. Adaptive fingerprints + walk-forward (2026-08-31)

| Field | Value |
|-------|-------|
| **Goal** | Forward-capable learning: remember *failure contexts* (regime/breadth/underwater/streak), not July/October hardcodes |
| **Evidence gate** | ≥3 repeats before size-down; ≥6 before sit — never amplify |
| **Eval** | `scripts/run_walkforward_adaptive.py` — carry ledger across years; compare reset-each-year vs adaptive carry |
| **Artefact** | `models/pattern_forge/walkforward_adaptive.json` |
| **Status** | RESEARCH; locked `v2_latest.json` untouched |

## Changelog

| Date | Change |
|------|--------|
| 2026-08-31 | **Adaptive fingerprints + walk-forward:** see §M8 / `adaptive_learn.py` / `run_walkforward_adaptive.py`. |
| 2026-08-31 | **v4 dual-mode:** attack/defense + RS scoring; see §M6 / `run_v4_bakeoff.py`. |
| 2026-08-31 | **v3.1 indicators:** VWAP + rel volume + 200 EMA filters; EMA-only best pass3 variant; see §M5 / `run_v3_bakeoff_pass3.py`. |
| 2026-08-30 | **ADANIENT verify + 2019/2021 fill + v3 OOS fail:** real fill; missing years were unrun not cherry-picked; v3 cannot clear confirmed OOS without killing edge; see §M4. |
| 2026-08-30 | **v2.1 bakeoff:** full lane +86.3% vs locked v2 +103.2% — **no promote**; OOS logged; see §M3 / `v2_1_bakeoff.json`. |
| 2026-08-30 | **v2.1 research lane:** shorts + hard swarm veto + overnight feeds + Lab charts + bakeoff/OOS gate; see §M3. |
| 2026-08-30 | **Daily FO swing push:** full FO uni + lev8 → **+42% / 8/12** clean 2025 (IN_FO costs); see §M2. Prior +7% was under-levered. |
| 2026-08-30 | **Daily FO swing:** clean-PIT next-day momentum band; **+7.17% / 8/12 green** on 2025 under IN_FO ~12bps; see §M2. |
| 2026-08-30 | **Hybrid stock+market chooser:** `hybrid_stock_market` family; see §M1. |
| 2026-08-30 | **Pattern Forge:** recognition-swarm port, no-ruin, F&O shorts, two-sided path, candle/analog/ORB2s; see §M. |
| 2026-08-29 | **Returns push 10%/mo:** soft trail + selective 2nd slot; promoted use85/trail2.5/sel2 (3/4 months ≥10%, mean +11.2%, DD 14.8%); see §L. |
| 2026-08-29 | **Ablation:** lookback+ticker+entity cooldown, WR shrink off → July **+8.4%**, last week **+8.1%**; product `bulk_wr_pseudo_n=0`. |
| 2026-08-29 | **Rules ledger:** self-learning anti-repeat rules (`hybrid_rules_ledger.json`); briefing read before every hybrid session; learn from daily P&L. |
| 2026-08-29 | **Copy-pro failure fixes:** prior-session lookback, WR shrink, SL ticker/entity cooldown, sitout-after-SL. Last week −8.3%→−0.08%; see `copy_pro_last_week_fixed.json`. |
| 2026-08-29 | **Copy-pro scale:** use60 July +6.39%; Aug after bulk backfill **+13.42%**; see §K2/K3. |
| 2026-08-29 | **Copy-pro push:** quality filters + SL cooldown grid; best=baseline_bakeoff@july; see §K; `copy_pro_push.json`. |
| 2026-08-29 | **Break-even bake-off:** lanes A/B/C; promoted=copy_bulk_pro; see §J; `break_even_bakeoff.json`. |
| 2026-08-28 | Initial log populated: 14 filter + 14 leverage + 9 target_return methods |
| 2026-08-28 | Ran `run_target_10_search.py`; goal_met=false, best min-day tr10_us_50x (-6.87%) |
| 2026-08-28 | Follow-up: `--grid filter` restored; intraday yfinance retry; IN compound + chase sections; 8% pass floor documented |
| 2026-08-29 | **Product guardrails:** SL during session-end, risk-capped leverage, daily loss halt. Product `in_tr10_orwidth_chase5_75x_guard`. Paper-month runner `scripts/run_paper_month_orwidth.py`. |
| 2026-08-29 | **Push 4%/5% + multi-trade:** oracle ceiling + OR-width position grid; logged §I; JSON `oracle_4_5_ceiling.json` / `push_4_5_experiment.json`. |
