# Copy-pro method: toward 10% monthly (hit-rate)

> **Date:** 2026-08-29  
> **Strategy:** `copy_bulk_pro` (NSE bulk/block BUY copy, prior session, no lookahead)  
> **Status:** paper / session-sim only — not live capital, not investment advice  
> **Companion log:** abbreviated in [`DAY_SIM_METHODS_LOG.md`](DAY_SIM_METHODS_LOG.md) §L  
> **Artifacts:** `models/copy_pro_return_gap.json`, `models/copy_pro_returns_push.json`

---

## 1. Goal (locked framing)

| Item | Value |
|------|--------|
| Book | ₹10,000 start, compound per **calendar month** |
| Target | Maximize months with compound **≥ 10%** |
| Windows | May, June, July, August **2026** (honest prior-session lookback) |
| Promotion gate | (1) ≥ **2 of 4** months ≥10%, (2) **no** month DD > **25%**, (3) mean compound **>** ablation baseline (~−6.2%) |
| Not the goal | 10% every single day; 10% forced every month (June under honest lookback was deeply negative without new exits/slots) |

**Standing claim after this work:** paper/sim hit-rate **3/4** months ≥10% under the promoted config; May still red; do **not** treat older Aug +13.4% / July bake-off +6% (looser lookback) as current product truth.

---

## 2. Baseline locked before the push

Ablation winner (2026-08-29) — **do not relax these** when re-running:

| Knob | Value | Why |
|------|--------|-----|
| `filter_mode` | `copy_bulk_pro` | Copy prior-session NSE bulk/block BUYs |
| `bulk_lookback_sessions` | `1` | Strict prior session only (no lookahead / stale multi-day) |
| `bulk_wr_pseudo_n` | `0.0` | WR shrink off (pseudo_n=5 hurt vs 0) |
| `bulk_min_win_rate` | `0.55` | Floor only; over-filtering (n≥2, deal floors) hurt July |
| `bulk_min_n_trades` | `1` | |
| `bulk_min_deal_value` | `0.0` | |
| `sl_cooldown_days` | `1` | Ticker cooldown after stop-loss |
| `entity_cooldown_days` | `1` | Investor/entity cooldown after SL |
| `sitout_after_sl_days` | `0` | Full sitout streak / rules-ledger sitout hurt August |
| `max_leverage` | `5.0` | Cap |
| `max_trade_risk_pct` | `3` | |
| `max_daily_loss_pct` | `4` | |
| Exit path | `exit_at_session_end` + `intraday_stop_with_session_end` | **protect_only**: cut losers on SL; winners ride to session close (hard TP off) |

**Pre-push month compounds (capital_use=0.6, 1 slot, no trail):**

| Month | Compound | PnL | Trades | Max DD |
|-------|----------|-----|--------|--------|
| May | −5.9% | −591 | 16 | 22% |
| June | −14.6% | −1,458 | 21 | 33% |
| July | −3.6% | −360 | 23 | 19% |
| August | −0.7% | −70 | 20 | 19% |
| **Mean** | **≈ −6.2%** | | | |

Sources: `models/copy_pro_may_june_july.json`, `models/copy_pro_august_ablation.json`.

---

## 3. Phase 1 — Return-gap diagnosis

**Script:** `scripts/run_copy_pro_return_gap.py`  
**Output:** `models/copy_pro_return_gap.json`

### 3.1 Metrics computed

From existing month tapes:

1. Win rate, avg win / avg loss, expectancy (₹/trade)
2. Exit mix (`session_close` vs `stop_loss`)
3. Capital utilization: margin / book → idle cash %
4. For winners with disk-cached bars: **MFE** (max favorable excursion from entry) vs **realized** % → **giveback** = max(0, MFE − realized)

Bars: **disk cache only** for older months (Yahoo 5m ≈ 60-day window; May/June often sparse). July–August cache denser.

### 3.2 Findings

| Signal | Observation | Implication |
|--------|-------------|-------------|
| Idle cash | ~**40%** at `capital_use_frac=0.6` | Room to raise use **if** edge exists |
| Selection | WR ~28–40%, negative expectancy all four months | Edge weak under 1-slot / session-close path |
| Giveback | Pooled avg winner giveback **~3.9%** (MFE often 6–12%, close gives back) | Soft trail can lock part of MFE without hard TP capping runners |
| Primary lever (audit) | `trail` (then sizing / selective 2nd slot) | Do not only crank leverage |

---

## 4. Phase 2 — Soft trail (new exit under protect_only)

**Code:** `packages/processor/day_sim.py` (`_simulate_session_day` exit loop)

### 4.1 Behavior

Under product **protect_only** (copy-pro / target-return with session-end + intraday stops):

1. Still exit immediately on **stop_loss** (hard floor).
2. **Do not** fire hard take-profit (winners are not capped at `st.tp`).
3. If `soft_trail_arm_pct` and `soft_trail_pct` are set:
   - Track peak return from entry (close path when `use_hl_exits=False`).
   - When peak ≥ **arm**, trail is **armed**.
   - If close return ≤ peak − **trail**, exit reason = `soft_trail`.
4. If never trailed or stopped → exit `session_close`.

### 4.2 Grid values tested

| Arm | Trail | Label |
|-----|-------|--------|
| off | — | `trailoff` |
| 1.5% (`0.015`) | 1.0% (`0.01`) | `trailarm15_tr10` |
| 2.5% (`0.025`) | 1.0% (`0.01`) | `trailarm25_tr10` |

**Kwargs:** `soft_trail_arm_pct`, `soft_trail_pct` (fractions). Both required; either missing/≤0 disables trail.

**Smoke:** 2026-08-05 with promoted kwargs exited `soft_trail`, realized PnL ≈ +697 on ₹10k book.

---

## 5. Phase 2b — Selective second slot

**Code:** `packages/processor/day_sim.py` (copy_bulk buy selection)

### 5.1 Behavior

- Rank buys by `bulk_score` (same as before).
- If `max_positions ≥ 2` **and** `bulk_second_min_wr` / `bulk_second_min_score_gap` set:
  - Always keep #1.
  - Open #2 **only if** top pick `bulk_wr` (win_rate_eff) ≥ min WR **and** score(#1) − score(#2) ≥ gap.
  - Else stay at **1** slot (margin not split unnecessarily).
- Without those mins: take up to `max_positions` as before.

### 5.2 Grid values

| Param | Value |
|-------|--------|
| `bulk_second_min_wr` | `0.65` |
| `bulk_second_min_score_gap` | `0.5` |
| `max_positions` | `2` (capacity; selective gate decides 1 vs 2) |

Score definition (unchanged):  
`score = wr_eff * log1p(deal_value) * (1 + 0.2 * log1p(n_trades))` in `smart_money_gate.rank_pro_buys`.

---

## 6. Phase 2c — Capital use and mild sitout

| Lever | Values | Result |
|-------|--------|--------|
| `capital_use_frac` | 0.60, 0.75, 0.85 | Alone scales both returns **and** DD (trail-off use85 mean worse) |
| `sitout_after_sl_days` | 0 vs 1 | Sit=1 cut June DD but **killed** July/Aug runners → 0/4 hit 10% |

**Keep sitout = 0** for product. (Rules-ledger multi-day sitout streak also hurt August earlier — stay off.)

---

## 7. Experiment harness

**Script:** `scripts/run_copy_pro_returns_push.py`  
**Output:** `models/copy_pro_returns_push.json`

### 7.1 Month runners

For each config × each month:

1. Weekday sessions in window (Aug: 2026-08-03 … 2026-08-28).
2. Compound equity; ticker + entity cooldowns via `register_copy_pro_outcomes`.
3. Optional `copy_pro_should_sitout` when sit≥1.
4. Record compound %, PnL, trades, wins/losses, max DD, sitout days.

Months run in parallel (thread pool) per config for wall-clock.

### 7.2 Wave order

1. **Wave 1:** `capital_use` × trail × sit=0 × 1 slot (9 configs).
2. **Wave 2** (if gate miss): sit=1 on top-3 by rank.
3. **Wave 3** (if still miss): selective 2nd slot on top seeds.

### 7.3 Ranking key

`gate_pass` → `months_hit_10` → `mean_compound_pct` → lower `max_month_dd_pct`.

---

## 8. Full grid results (summary)

### Wave 1 — sizing × trail (1 slot)

| Config | Hit ≥10% | Mean | Max month DD | Gate |
|--------|----------|------|--------------|------|
| use60 trail off | 0/4 | −6.2% | 32.6% | N |
| use60 trail arm1.5% | 1/4 | +2.8% | 25.3% | N |
| use60 trail arm2.5% | 1/4 | +6.9% | 25.3% | N |
| use75 trail off | 0/4 | −8.3% | 39.2% | N |
| use75 trail arm1.5% | 1/4 | +2.8% | 30.8% | N |
| use75 trail arm2.5% | 2/4 | +7.9% | 30.8% | N (DD) |
| use85 trail off | 0/4 | −9.8% | 43.3% | N |
| use85 trail arm1.5% | 1/4 | +2.6% | 34.4% | N |
| use85 trail arm2.5% | 2/4 | +8.5% | 34.4% | N (DD) |

Trail alone got **2× months ≥10%** at higher use, but June DD blew past 25%.

### Wave 2 — sitout=1 on top seeds

All hit **0/4**; mean ~0–1%. Sitout after SL skipped too many strong days in July/August.

### Wave 3 — selective 2nd slot + trail

| Config | Hit ≥10% | Mean | Max DD | Gate |
|--------|----------|------|--------|------|
| **use85 + trail 2.5% + sel2** | **3/4** | **+11.2%** | **14.8%** | **Y** |
| use75 + trail 2.5% + sel2 | 3/4 | +10.1% | 13.1% | Y |
| use60 + trail 2.5% + sel2 | 2/4 | +8.3% | 10.6% | Y |
| use60 + trail 1.5% + sel2 | 2/4 | +7.2% | 10.6% | Y |

**Winner month tape (use85 / arm2.5 / sel2):**

| Month | Compound | Max DD | Trades (approx) |
|-------|----------|--------|-----------------|
| May | −3.4% | 14.8% | 20 |
| June | **+14.9%** | 8.6% | 32 |
| July | **+12.9%** | 5.8% | 38 |
| August | **+20.5%** | 11.0% | 30 |

Second slot + trail **also cut peak DD** vs single-slot high use (diversification + earlier locks), which is why DD cleared the gate.

---

## 9. Promoted product defaults

**File:** `packages/processor/hybrid/registry.py` → `sim_kwargs_for_strategy("copy_bulk_pro", "product")`

```text
filter_mode                 = copy_bulk_pro
max_leverage                = 5.0
conf_floor                  = 0.55
max_daily_loss_pct          = 4.0
max_trade_risk_pct          = 3.0
intraday_stop_with_session_end = True
exit_at_session_end         = True
use_hl_exits                = False
max_positions               = 2          # capacity; selective gate
bulk_lookback_sessions      = 1
bulk_min_win_rate           = 0.55
bulk_min_n_trades           = 1
bulk_min_deal_value         = 0.0
capital_use_frac            = 0.85
soft_trail_arm_pct          = 0.025
soft_trail_pct              = 0.01
bulk_second_min_wr          = 0.65
bulk_second_min_score_gap   = 0.5
bulk_wr_prior               = 0.55
bulk_wr_pseudo_n            = 0.0
sl_cooldown_days            = 1
entity_cooldown_days        = 1
sitout_after_sl_days        = 0
```

Research lane keeps smaller size (`capital_use_frac=0.6`, `max_positions=1`) for safer exploration.

Hybrid engine strips window-only keys (`sl_cooldown_days`, `entity_cooldown_days`, `sitout_after_sl_days`) before `simulate_day`; trail / second-slot kwargs pass through.

---

## 10. How to reproduce

```powershell
cd C:\Users\siddu\projects\trade_bot
$env:POSTGRES_URL = "postgresql://smartmoney:changeme@127.0.0.1:5433/smartmoney"

# Gap audit (disk-cache MFE; no Yahoo hammer)
python scripts/run_copy_pro_return_gap.py

# Full push grid (May–Aug × waves)
python scripts/run_copy_pro_returns_push.py
```

Requires: Postgres with NSE bulk signals (~2026-05-03 → 2026-08-27), `models/intraday_cache` for session bars (1h fallback outside Yahoo 5m window).

---

## 11. What failed (do not re-promote)

| Idea | Outcome |
|------|---------|
| Over-filter (min n≥2, deal-value floors, higher WR) | Hurt July vs open copy |
| WR shrink `bulk_wr_pseudo_n=5` | Lost to `pseudo_n=0` |
| Rules-ledger / sitout streak | August worse (−9% vs ~flat) |
| Mild sitout_after_sl_days=1 in push | Flattened Jul/Aug ≥10% months |
| Capital use alone (no trail) | Scaled losses; June DD 33–43% |
| Hard TP on winners | Not used; would cap runners that trail is meant to protect partially |

---

## 12. Honesty / limits

1. **Paper session-sim only** — modeled fees/leverage; not broker fills.
2. **Yahoo / cache path-sensitive** — re-runs can drift; treat JSON artifacts as the recorded run.
3. **May still red** under the winner; gate is hit-rate, not every-month floor.
4. **June rescue** in winner relied on more fills (2nd slot) + trail — edge quality still fragile.
5. **Not 10%/day** — earlier day-sim work showed structural ceilings; this doc is **monthly compound hit-rate** only.
6. Do not cite pre-ablation Aug +13.4% or loose-lookback July bake-off as the current product line without re-running under lookback=1 + this exit/slot stack.

---

## 13. File map

| Path | Role |
|------|------|
| `docs/COPY_PRO_10PCT_MONTHLY_METHOD.md` | This method (canonical write-up) |
| `docs/DAY_SIM_METHODS_LOG.md` §L | Short log entry + changelog |
| `packages/processor/day_sim.py` | Soft trail + selective 2nd slot |
| `packages/processor/smart_money_gate.py` | Prior-session rank, WR, cooldowns |
| `packages/processor/hybrid/registry.py` | Product defaults |
| `scripts/run_copy_pro_return_gap.py` | Gap audit |
| `scripts/run_copy_pro_returns_push.py` | Push grid |
| `models/copy_pro_return_gap.json` | Audit numbers |
| `models/copy_pro_returns_push.json` | Full grid + `promoted` block |

---

*End of method. Update this file when defaults or gate results change materially.*
