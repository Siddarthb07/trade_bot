# Improvement Plan — Trade Bot

A phased roadmap focused on **clear hold/sell timeframes**, then data quality, UI, and alerts.

---

## Current Gap (Timeframes)

Today the system stores `sell_horizon_days` and labels like `"~2 weeks (trend)"`, but the dashboard mostly shows vague text. WhatsApp computes `Exit ~08 Jul` internally — that logic isn't surfaced consistently in the UI.

**Goal:** explicit **days, weeks, months**, plus **calendar sell-by dates** on every pick.

---

## Phase 1 — Clear Holding & Selling Timeframes (Highest Priority)

### 1.1 Standardize the Timeframe Model

Extend `return_distribution` (and macro picks) with one consistent schema:

| Field | Example | Purpose |
|-------|---------|---------|
| `hold_days` | `21` | Primary hold period |
| `hold_label_short` | `3 weeks` | Human-readable |
| `hold_label_long` | `Hold 21 days · ~3 weeks` | Full line for UI/WhatsApp |
| `entry_date` | signal `disclosed_at` | When the pick was issued |
| `review_date` | entry + 50% of hold | Mid-hold check-in |
| `exit_date` | entry + hold_days | Target sell-by date |
| `exit_window_start` / `exit_window_end` | ±3 days | Range, not a single day |
| `timeframe_tier` | `short` / `medium` / `long` | For filtering & color |

**Rules by pick type:**

| Type | Typical hold | Logic |
|------|--------------|--------|
| **Bulk deal (hot)** | 5–14 days | Cluster + strong 1mo momentum |
| **Bulk deal (normal)** | 14–45 days | Current `horizon.py` rules |
| **Demand/theme pick** | 45–90 days | Macro cycles (storage, defense, infra) |

Centralize in `horizon.py` + `macro_themes.py` via a shared `format_timeframe(days) → {days, weeks, months, exit_date, labels}` helper.

### 1.2 Dashboard — Make Timeframes Impossible to Miss

**Every stock row (Demand + Bulk):**

```
HOLD 21 days (~3 weeks)  ·  SELL BY 22 Jul 2026  ·  Review 12 Jul
Est. +18%  ·  68% conf
```

**Visual:**

- **Timeline bar** on each row: Entry → Review → Exit (today marked if in hold)
- **Countdown badge**: "12 days left" or "Exit window — review now"
- **Signal detail page**: dedicated "Hold & exit plan" card (not buried in KPIs)

**Filters/sorts:**

- Sort by `exit_date` (soonest exit first)
- Filter: "Exiting this week" / "Long holds (60+ days)"

### 1.3 WhatsApp — Same Format as Dashboard

Replace mixed labels with a fixed block:

```
HOLD: 21 days (~3 weeks)
SELL BY: 22 Jul 2026
REVIEW: 12 Jul (mid-hold)
Est +18% · not guaranteed
```

Links unchanged (`/s/{id}/{token}`).

### 1.4 Exit Reminders (Automated)

| Alert | When |
|-------|------|
| **Review ping** | 50% of hold period |
| **Exit ping** | `exit_date` |
| **Overdue** | exit + 3 days if no manual dismiss |

Store in `alert_log` with dedup keys like `exit_reminder:{signal_id}:exit`.

---

## Phase 2 — Data Quality & Pick Accuracy

### 2.1 Deduplicate Bulk Top Picks

- One row per **ticker** (not 5× same stock from different bulk deals)
- Keep highest composite score; show "3 bulk deals this week" as subtext

### 2.2 Stronger Demand vs Bulk Separation

- **Demand tab:** only `has_bulk_deal = false` (already partial)
- Badge: "Bulk confirmed" when both signals align (boost confidence)

### 2.3 Historical Backfill for ML

- Multi-day NSE archive → train LightGBM on real 3mo outcomes
- Retrain weekly when enough labeled data exists
- Timeframes then blend **rule-based + learned median hold** per tier/investor

---

## Phase 3 — UI Simplification + More Info

### 3.1 Keep What Works

- Per-stock mini charts on list rows
- Simple top nav: Demand | Bulk | Themes
- Remove aggregate bar charts that replace per-stock detail

### 3.2 Add Without Clutter

- **Expand row** (click) → inline full thesis + bulk investor table (no extra page hop)
- **Compare mode** — select 2–3 picks, side-by-side charts + hold timelines
- **Mobile:** stack chart above metrics; sticky hold/exit banner at top

### 3.3 Theme Explorer

- Each theme: proxy chart + top stocks with **same hold/exit format**
- One-line "why now" from `world_context` (already in backend)

---

## Phase 4 — Scoring & Timeframe Intelligence

### 4.1 Investor-Specific Hold Periods

- From `investor_stats`: median days to peak return per entity
- e.g. "This investor's past bulk buys peaked in ~18 days (median)"

### 4.2 Volatility-Adjusted Exits

- High vol → wider exit window (e.g. 21 days ±5)
- Low vol + strong trend → tighter window

### 4.3 Partial Exit Suggestion (Optional)

```
Day 0:   Enter
Day 10:  Consider trimming 25% if +8%
Day 21:  Target full exit
Day 28:  Hard stop review
```

Optional Phase 4+ — only if staged exits are desired.

---

## Phase 5 — Access & Ops

| Item | Why |
|------|-----|
| HTTPS (Tailscale / Cloudflare) | Links work off WiFi |
| WhatsApp group (`WHATSAPP_GROUP_ID`) | Picks to group, not DM |
| Persist ML model volume | Survive Docker rebuilds |
| Settings UI for hold prefs | Min/max days, alert on/off |

---

## Recommended Build Order

| Order | Phase | Deliverable |
|-------|-------|-------------|
| 1 | Phase 1 backend | Timeframe schema in `horizon.py` + API |
| 2 | Phase 1 dashboard | Hold/exit badges + timeline on every row |
| 3 | Phase 1 alerts | WhatsApp format + exit reminder jobs |
| 4 | Phase 2 | Dedupe bulk picks |
| 5 | Phase 2 | NSE backfill + ML retrain |
| 6 | Phase 3 | Expand rows + compare mode |
| 7 | Phase 4 | Investor-specific hold stats |

**Week 1 (do first):** Phase 1 — clear **X days / Y weeks / sell-by date** everywhere.  
**Week 2:** Dedupe + exit reminder WhatsApp messages.  
**Week 3+:** ML backfill and smarter per-investor holds.

---

## Target UX (After Phase 1)

**Demand pick — WDC**

```
┌─────────────────────────────────────────────────────────┐
│ [6mo chart]  WDC · AI Storage Demand          HIGH      │
│              No bulk deal                               │
│  HOLD 63 days (~2 months)                               │
│  REVIEW 31 Jul 2026  ·  SELL BY 01 Sep 2026             │
│  Est +32%  ·  72% conf  ·  Theme heat 81%               │
│  ████████░░░░░░░░  41 days remaining                    │
└─────────────────────────────────────────────────────────┘
```

**Bulk pick — RAMCOSYS**

```
HOLD 7 days (~1 week)
SELL BY 08 Jul 2026
Est +30%  ·  ₹44 Cr deal  ·  3-investor cluster
```

---

## Config Knobs to Add (Settings)

- Default hold display: **days** | weeks | both
- Exit alert: on/off
- Minimum hold before showing pick (filter noise)
- Theme hold multiplier (e.g. 1.5× for macro vs bulk)

---

## Key Files to Touch (Phase 1)

| Area | Files |
|------|-------|
| Timeframe logic | `packages/processor/horizon.py`, `packages/processor/macro_themes.py` |
| Scoring | `packages/processor/scoring.py` |
| API | `packages/api/main.py` |
| WhatsApp | `packages/notifier/templates.py`, `packages/notifier/daily_picks.py` |
| Scheduler | `packages/ingest/scheduler.py` (exit reminder job) |
| Dashboard | `apps/dashboard/src/components/StockPanel.tsx`, `SignalPage.tsx`, `HomePage.tsx` |
| Config | `packages/core/config.py`, `.env.example` |

---

*Not investment advice. Timeframes are estimates based on rules and public data — not guaranteed.*
