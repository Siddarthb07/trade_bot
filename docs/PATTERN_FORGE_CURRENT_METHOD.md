# Pattern Forge — Current Method Spec

> **Last updated:** 2026-08-30  
> **Status:** Paper / clean-PIT research only — **not live fills** · **not OOS-validated**  
> **Promoted label (v2):** `v2` — `daily_swing` + soft mistake ledger + **profit_guard**  
> **Research challenger (v2.1):** shorts + hard swarm vetoes + overnight feeds — see bakeoff; does **not** replace this doc until promotion gate passes  
> **v1 stretch (frozen):** `daily_fo_push10` — see §5  
> **Design notes:** [`PATTERN_FORGE_V2_DESIGN.md`](PATTERN_FORGE_V2_DESIGN.md)

This is the source-of-truth write-up for the **promoted v2** method after the clean-PIT reboot.

---

## 1. One-line summary

**Cross-sectional next-day FO momentum** with sleeve×leverage sizing, ~12 bps F&O RT costs, no-ruin, a **mistake ledger** (ban losers / soft size-down), and a **profit guard** so a single day cannot erase more than YTD profits once ahead (half-size while underwater).

---

## 2. Promoted v2 config (locked)

| Knob | Value |
|------|-------|
| Family | `daily_swing` |
| Lane | `v2` |
| Leverage | **11×** |
| Sleeve | **24%** |
| Top-k | 1 |
| Learn mistakes | on (soft) |
| Breadth veto / scale | off |
| Profit guard | **on** (floor 2% capital while YTD ≤ 0) |
| Costs | `IN_FO_COST` ~12 bps RT |
| Universe | NSE F&O list (excl. TATAMOTORS) |
| Horizon | close[T] → close[T+1] |

### Clean PIT 2025 (₹10k start)

| Metric | Result |
|--------|--------|
| End capital | **₹20,325** |
| Year return | **+103.2%** |
| Green months | **10/12** |
| Worst month | **−5.7%** (₹−997) |
| Year PnL | **₹+10,325** |
| Loss ≤ profits | **yes** |
| Run id | `2b906e47-2e8` |

Artefacts: `models/pattern_forge/v2_latest.json`, `latest_summary.json`.

**Honest limits:** same signal as v1 stretch — guard + leverage change the path, they do not invent new alpha. OOS 2023/2024 still required. Contaminated +511% is not a claim.

---

## 3. Why this method (not session ORB / not copy-pro)

| Prior approach | Clean result | Diagnosis |
|----------------|--------------|-----------|
| Copy-pro (contaminated WR) | ~+511% 2025 | Live WR with `pit_n=0` — **leak**. Same knobs clean ≈ **−67%**. |
| Session hybrid `hybrid_stock_market` | Oct–Dec underwater | 1h oracle ~23 bps vs cash RT ~30 bps. |
| v1 stretch push10 | +45% / Feb **−26%** | Same edge, raw lev — left-tail too large for “keepable”. |
| **v2 (this doc)** | **+103% / Feb −5.7%** | Profit guard caps hole; compounds after. |

**Hard rules still in force**

- Clean PIT only (no future labels, no WR leak).
- No-ruin floor always on.
- F&O universe for leveraged paths.
- Agents / ledger **never amplify** size.

---

## 4. Re-run

```bash
set PYTHONPATH=packages
python scripts/run_pattern_forge_daily_swing_2025.py --leverage 11 --sleeve 0.24 --lane v2
# or iterate loop first mutation = v2
python scripts/pattern_forge_iterate_loop.py
```

Ensure knobs include `profit_guard=True`, `learn_mistakes=True`, `promote_as=v2`.

---

## 5. Legacy v1 stretch (frozen)

| Knob | Value |
|------|-------|
| Label | `daily_fo_push10` |
| Leverage | 10× |
| Sleeve | 25% |
| 2025 | ~+45% / 8/12 / Feb ~−26% |

Kept for comparison only — not the Lab hero.

Trace: [`docs/METHOD_BREAK_TRACE.md`](METHOD_BREAK_TRACE.md) · log: [`docs/DAY_SIM_METHODS_LOG.md`](DAY_SIM_METHODS_LOG.md).
