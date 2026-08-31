# Method Break Trace — copy-pro + recognition-swarm

> Generated: 2026-08-30  
> Machine: [`models/method_break_trace.json`](../models/method_break_trace.json)  
> Status: research log — not live claims

## 1. What looked like it worked (contaminated)

| Artifact | Result | Why invalid |
|----------|--------|-------------|
| `copy_pro_year_2025_oneshot_10k.json` | **+511%** | WR leak: `pit_n=0` but live investor WR scored (`copy_pro_2025_leak_audit.json`) |
| Leak PnL on audited rows | ~₹49k of leaked-path PnL | Future / thin-sample monopoly WR |

**Stretch label only:** unclean ~500% is a ceiling fantasy, not a product claim.

## 2. Clean PIT truth

| Artifact | Result |
|----------|--------|
| `copy_pro_year_2025_oneshot_10k_clean_pit.json` | **−67.4%**, **1/12** green months (October only) |
| `copy_pro_fresh_oos_compare.json` | 2018/2023/2025/2026 all red (−27% to −75%) |

## 3. Root break

- **Horizon mismatch:** 3-month investor WR ≠ same-day MIS edge.
- Thin n + no matured PIT outcomes still got high confidence under leaky ranking.

## 4. Transferable habits (keep)

- Soft trail (arm 2.5% / trail 1%)
- `capital_use_frac` / selective 2nd slot
- `sitout_after_sl_days=0` for product (sit=1 killed Jul/Aug runners)
- Session guards: trade risk + daily loss caps

## 5. Recognition-swarm lessons (`godfather/recognition-swarm`)

| Lesson | Action |
|--------|--------|
| Skip quality > frequency | Keep MetaLabel / Cost / RulesClerk hard vetoes |
| Full-book every day bled (−23% hybrid) vs sleeve (~25%) | Max sleeve 25–50%; no-ruin floor |
| Hard Decay veto → cash death spiral | Decay = weighted vote only |
| Steady MIS peeked ticker | **Do not port** (fragile / lookahead-shaped) |
| DTW similarity | Port — maps to analog family |
| VPIN/Hawkes/Kyle | Leave stubs (insufficient_data on NSE 5m) |

## 6. No-ruin (locked)

Halt new risk if equity ≤ 40% of peak **or** ≤ 50% of start → force cash.  
Daily loss ≤4–5%, trade risk ≤3% at SL, allocator reduce-only.

## 7. What we build next

Selective swarm port + F&O-only shorts + candle/analog/ORB2s bake-off under clean PIT.

## 8. First cache-only OOS (2026-07-01 → 2026-08-28, sleeve 25%, no-ruin on)

| Family | Return | Trades | Floor hits |
|--------|--------|--------|------------|
| pattern_candle | **+0.24%** | 17 | 0 |
| pattern_analog | 0.00% | 0 | 0 (swarm/flat — needs richer library) |
| orb_two_sided | −1.87% | 39 | 0 |

Artifact: `models/pattern_forge_cache_oos.json`. Synthetic plumbing bake-off: `models/method_family_bakeoff.json`.  
**Not** close to monthly consistency or 500% stretch — iterate families next under same no-ruin gate.

## 9. Hands-free 2025 loop + Pattern Lab dash (2026-08-30)

- Ledger: `models/pattern_forge/{decisions,trades,runs,iterations}.jsonl` + `latest_summary.json`
- API: `/exec/pattern-forge/{summary,decisions,trades,iterations}`
- Dash: **/pattern-lab** (Apple materials: glass, press scale, decision tape + swarm votes)
- Loop: `scripts/pattern_forge_iterate_loop.py` (+ Glass Automation hourly)
- First Oct–Dec 2025 slice (`candle_tau50`): **0/3 green**, end ≈ ₹9,947 (−0.5%) — continue mutating
