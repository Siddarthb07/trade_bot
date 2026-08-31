# Pattern Forge v2 Design — After v1 Daily FO Swing

> **Date:** 2026-08-30  
> **v2 status:** **LOCKED / PROMOTED** — see [`PATTERN_FORGE_CURRENT_METHOD.md`](PATTERN_FORGE_CURRENT_METHOD.md)  
> **v2.1 status:** **RESEARCH** — shorts + hard swarm vetoes + overnight feeds + Lab charts; promote only via bakeoff gate  
> **v1 status:** frozen stretch baseline (`daily_fo_push10`)  
> **v2 north star:** bigger clean return with **loss ≤ profits** (profit_guard), not max annual via naked leverage

---

## 1. Why v2

v1 (`daily_fo_push10`) is a **good start**: clean-PIT +45% / 8/12 green on 2025 under F&O costs.  
It is **not** a finished product because:

| Issue | Evidence |
|-------|----------|
| High lev = high left-tail | Feb ≈ **−26%** at lev 10; same signal at lev 2 was only +7% with tiny reds |
| Bad-year amplification | A second Feb-like month would erase a “good” year |
| Session ORB unfinished | 1h ORB failed vs costs; frequency / soft-trail not exhausted |
| Swarm incomplete for opens | No overnight / Asia / GIFT-style cue agent until now |

**Principle:** leverage is a *knob*, not a strategy. v2 optimizes **worst-month** and **green-month count at lev ≤ 3**, with optional stretch lane ≤ 5.

---

## 2. Design principles (locked)

1. **v1 stays the stretch baseline** — never delete; always compare on same PIT window.  
2. **Product lane lev ≤ 3**; stretch ≤ 5; research may go higher but cannot auto-promote.  
3. **No LLM on the fire path** — agents stay deterministic; LLMs only for offline design critique.  
4. **One risk budget** — daily swing sleeve + session ORB sleeve must share a day/week cap (no double book).  
5. **Cross-market cues are veto/confirm, never sole fire.**  
6. **Kill criteria** (≤2 weeks): if lev≤3 cannot beat cash flat on worst-month *and* ≥6/12 greens, abort that branch.  
7. **No WR leak** — clean PIT only.  
8. **Dash compares lanes** — v1 stretch vs v2 product side-by-side on Pattern Lab.

---

## 3. Research anchors (cross-market)

- Legacy **SGX Nifty** → **GIFT Nifty** (NSE IX, Jul 2023) is the live pre-open cue for Nifty cash.  
- Cue explains **open direction** better than **gap magnitude**; India-specific events (Budget, RBI) weaken it.  
- Supporting overnight tape: US (ES/NQ), Asia (NKY/HSI), USDINR, crude.  
- Implementation: agent `CrossMarketOpen` consumes `overnight_gap_pct` / `asia_ret_pct` / `us_ret_pct` known **before** NSE open (PIT).

Sources consulted: GIFT/SGX pre-open guides (NiftyTrader, MarketNetra, Oquilia migration note).

---

## 4. New agents (v2)

| Agent | Role | Vote semantics | PIT |
|-------|------|----------------|-----|
| **CrossMarketOpen** | GIFT/SG-style overnight gap vs primary | take if agrees (≥25 bps composite); skip if strong oppose (≥40 bps); else annotate | Overnight proxies only |
| **CrossSectionSimilarity** | Peer dispersion / quartile rank | take if long+top quartile & IQR≥40 bps; skip if crowded (low IQR) or long+laggard | Prior closes ≤ T |

Wired into `recognize_session` (`packages/processor/hybrid/recognition/stack.py`).  
Code: `packages/processor/hybrid/recognition/swarm/cross_market.py`.

**Planned next (not yet coded):**

| Agent | Intent |
|-------|--------|
| **OpenAuctionQuality** | Gap size vs OR width — skip chase on huge gaps |
| **FrequencyORB** | Prefer 5m/15m ORB when OR pays friction; soft-trail exits |
| **AsiaBasket** | NKY+HSI+KS11 composite overnight (separate from GIFT gap) |
| **BadMonthGuard** | Size-down after 2 consecutive red sessions / peak DD |

---

## 5. Frequency + ORB experiments (v2 backlog)

| # | Experiment | Lev | Horizon | Status |
|---|------------|-----|---------|--------|
| A | `daily_swing` product | ≤3 | next-day | **PASS** — +11% / 9/12 / Feb −6.6% |
| B | Session ORB / 5m ORB + trail | ≤2 | intraday | **KILLED** — costs > edge (council unanimous) |
| C | CrossMarket as **sit-out gate only** | ≤3 | next-day | NEXT |
| D | Multi-day hold 2–3 (lev ≤2) | ≤2 | swing | NEXT — frequency *down* |
| E | Top-k (3–5) names not argmax-1 | ≤3 | next-day | NEXT |

**Cost reality:** session-close on 1h alone cannot clear ~30 bps cash RT. **Do not resurrect session ORB mutations.**

---

## 6. Risk budget (shared)

```
day_risk_cap = 4% equity (product)
  ├─ sleeve_daily_swing ≤ 20% × lev≤3
  └─ (session ORB sleeve = 0 for product until costs clear)
sum notional_risk ≤ day_risk_cap
week_dd_halt = 12% → cash until next week
```

v1 stretch (lev 8–10) remains **research badge only** on the dash.

---

## 7. Success metrics (replace “beat 500%”)

| Metric | Product target | Stretch (research) |
|--------|----------------|--------------------|
| Green months / 12 | ≥ 8 | ≥ 8 |
| Worst month | > −12% (**primary**) | > −20% |
| Annual (clean PIT) | > +15% at lev≤3 | compare to v1 +45% honestly |
| Max DD | < 25% | < 40% |
| Calmar (ann / maxDD) | ≥ 2.0 | secondary |
| OOS | 2023 + 2024 required before “method” claim | — |

Contaminated +511% is **out of scope**.

---

## 8. Multi-model design consult (this cycle)

| Model | Role | Link |
|-------|------|------|
| Claude Opus | Architecture | [Opus v2 hybrid critique](287369c7-6df8-43cf-8f3f-12252effe789) |
| Kimi | Product / markets | [Kimi v2 market critique](ca8a1b70-b4fe-4178-8bbb-aa900e7550f1) |
| GPT-5.4 | Adversarial | [GPT v2 adversarial critique](38f010c2-5a2d-4d78-9732-02fd498f2da0) |

DeepSeek was **not** available in this workspace’s model router; GPT filled the adversarial seat.

LLMs do **not** vote on live fires.

---

## 9. Council consensus (locked 2026-08-30)

### Agreement (all three)

1. **Optimize worst-month / Calmar at lev ≤ 3**, not annual via leverage. Lev10 +45% and lev2 +7% are the *same edge* — leverage only scales the Feb hole.  
2. **GIFT / cross-market = size or sit-out gate**, never a stock picker. Index-gap ≠ single-name FO alpha.  
3. **Kill session / 5m ORB frequency chase** — oracle ~23 bps vs costs is structural; more bars raise friction, not edge.  
4. **Don’t pile correlated agents** — votes on the same price state are pseudo-diversification. Prefer one primary model + one independent veto.  
5. **Mandate 2023/2024 OOS** before calling anything a method (one year overfits Feb or May).

### Nuance

| Source | Push |
|--------|------|
| [Opus](287369c7-6df8-43cf-8f3f-12252effe789) | Top-k (3–5) names; BreadthRegime to replace RELIANCE monoculture; agents may only *reduce* risk |
| [Kimi](ca8a1b70-b4fe-4178-8bbb-aa900e7550f1) | Multi-day hold (T→T+3/5) beats higher frequency; predictive sit-out ≠ reactive cooldown |
| [GPT](38f010c2-5a2d-4d78-9732-02fd498f2da0) | Keep one primary (`daily_swing`) + one pre-declared stress filter; 2-week kill if PIT unclean or agent correlation > 0.6 |

### Revised agent plan

| Agent | Keep? | Role |
|-------|-------|------|
| CrossMarketOpen | Yes — **veto/scale only** on open/session path; careful on close→close | Gate |
| CrossSectionSimilarity | Yes — dispersion / crowded skip | Soft veto |
| FrequencyORB | **No** — killed | — |
| BreadthRegime | **Yes — next** | Replace RELIANCE-only risk_off |
| StressVeto | **Yes — next** | Pre-declared: high vol + weak breadth → size 0 |
| AnalogSimilarity library | Later — embargo/PIT audit first | Scale only |

### 2-week kill criteria (adopted)

Abort a v2 branch if any of:

1. Feature cannot prove PIT timestamp at decision time  
2. Agent helps in-sample but not OOS expectancy **and** worst-month **and** trade Sharpe  
3. Pairwise agent vote correlation > 0.6 or removing agent barely changes decisions  
4. Intraday ORB gross edge < 1.5× modeled RT friction  
5. < 30 independent trade events supporting a claim  

---

## 10. Self-learning mistake ledger (locked)

After each traded day closes (exit known), `learn_from_day` writes:

| Mistake | Rule written | Next-day effect |
|---------|--------------|-----------------|
| Losing name | `exclude_ticker` | Ban re-buy 3–5 sessions |
| Red book day | `size_down` 0.5 | Half size next session |
| 2+ consecutive red days | `sitout_session` | Flat next session |
| Chase-band loss ≤ −1.5% | soft `size_down` 0.75 | Smaller sleeve briefly |

Paths: `models/pattern_forge/mistake_rules.json`, `mistakes.jsonl`, `mistake_history.jsonl`.  
Briefing is read **before** every fire (`read_briefing`). Agents / ledger **never amplify** size.  
Dash: Pattern Lab → Mistake ledger + `/exec/pattern-forge/mistakes`.

---

## 11. Implementation status

| Item | Status |
|------|--------|
| v1 method doc | Done — `PATTERN_FORGE_CURRENT_METHOD.md` |
| CrossMarketOpen agent | Done |
| CrossSectionSimilarity agent | Done |
| **Mistake ledger (anti-repeat)** | **Done** — `pattern_forge/mistake_ledger.py` |
| Unit tests | `tests/test_cross_market_agents.py` + `tests/test_mistake_ledger.py` + `tests/test_v2_1_pattern_forge.py` |
| **Product lane lev3 bench** | **Done — +10.96% / 9/12 green / Feb −6.6%** (`benchmark_2025_daily_swing_fe73b956-72d.json`) |
| Shared risk budget enforcer | TODO |
| Frequency ORB 5m path | **KILLED** |
| Pattern Lab v1 vs v2 compare | Done — ending-capital board + v2 vs v2_1 equity + trade markers |
| Dash | Vite Pattern Lab `/pattern-lab`; API on :8000 |

### v2.1 research checklist

| Gap | Status |
|-----|--------|
| FO two-sided (`long_only=False`) | Done — lane `v2_1` |
| Hard swarm veto (Regime / CrossMarket / Similarity / Breadth) | Done — `swarm_hard_veto` |
| ProfitGuard agent message | Done |
| PIT overnight / Asia / US feeds | Done — `overnight_feeds.py` |
| Lab DetailPriceChart + markers | Done — `GET /exec/pattern-forge/chart` |
| Ablation + OOS 2023/2024 | `scripts/run_v2_1_bakeoff.py` → `v2_1_bakeoff.json` |
| Promote to locked v2 | **Never silent** — only if bakeoff beats v2 on 2025 + OOS claim |

Artefacts: locked `v2_latest.json`; challenger `v2_1_latest.json`.

### Aim band 40–50% (clean PIT 2025)

Same `daily_swing` edge — leverage is the dial. Soft mistake ledger on.

| Lane | Lev | Sleeve | Year | End ₹ | Green | Worst mo | Loss≤profits |
|------|-----|--------|------|-------|-------|----------|--------------|
| Conservative product | 3× | 20% | +11.0% | 11.1k | 9/12 | −6.0% | yes |
| **v2_aim40_lev8** | **8×** | **27%** | **+42.6%** | **14.3k** | **8/12** | **−20.6%** | yes |
| lev10 no guard | 10× | 25% | +50.1% | 15.0k | 9/12 | −24.0% | yes |
| **v2 (LOCKED)** | **11×** | **24%** | **+103%** | **20.3k** | **10/12** | **−5.7%** | **yes** |

Canonical file: `models/pattern_forge/v2_latest.json` · Lab hero prefers `v2`.

**Profit guard:** once YTD is green, a single day cannot lose more than YTD profits; while underwater, size×0.5 and floor risk at 2% capital.

**Honest claim:** still the same FO daily signal + risk overlay — not new alpha. OOS 2023/2024 required. Contaminated +511% out of scope.

---

## 12. Immediate next commands

```bash
set PYTHONPATH=packages
python -m pytest tests/test_v2_1_pattern_forge.py tests/test_daily_swing.py -q
python scripts/run_v2_1_bakeoff.py
# OOS only: python scripts/run_pattern_forge_daily_swing_oos.py --year 2023 --lane v2_1_oos
```
