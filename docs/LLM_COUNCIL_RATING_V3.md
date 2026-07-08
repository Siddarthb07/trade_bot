# LLM Council Review V3 — Post Links, Ranking & Free-Data Ingest

**Date:** 2026-07-05  
**Subject:** Trade Bot after unified ranking, share landing, investor intel everywhere, and free-API ingest  
**Prior review:** [LLM_COUNCIL_RATING_V2.md](./LLM_COUNCIL_RATING_V2.md) — **7.2/10 (A−)**  
**Method:** Same 6-expert council; scores reflect **delta** since V2

---

## Council roster

| Expert | Lens |
|--------|------|
| **Atlas** | Systems & service architecture |
| **Nova** | ML / scoring / calibration |
| **Ridge** | DevOps, reliability, deployment |
| **Cipher** | Security & compliance |
| **Mira** | Product, UX, trust for real money |
| **Quill** | Markets domain & data quality |

---

## 1. Atlas — Systems Architecture

**Score: 8.0 / 10** *(was 7.8, +0.2)*

**Improvements since V2**

- **`notifier/ranking.py`** — shared ranking logic for API, WhatsApp, and share landing (DRY win)
- **`GET /share/ranked-picks`** — dedicated read model for phone links with pre-built URLs
- **`ingest/pull_free.py`** — orchestrated 10-job free-data pull with partial-failure tolerance
- **Migration 004** — `market_snapshots` + `eod_prices` tables; schema evolution continues cleanly
- **`_attach_investor_intel()`** centralized on demand, bulk, top-picks, and share endpoints
- Live code volume mounts on `api` / `worker` / `processor` reduce rebuild friction

**Remaining gaps**

- **Three runtimes** (`api`, `worker`, `processor`) still share logic without a formal job registry
- `eod_prices` / `market_snapshots` **stored but not wired** into features or ML (still yfinance at scoring time)
- No event bus; ranking recomputed ad hoc per request
- Order execution bounded context still unstarted

**Verdict:** Architecture **mature for a personal monolith**. Next leap is either wire stored EOD into features or extract a thin `picks` read service.

---

## 2. Nova — ML & Scoring

**Score: 6.0 / 10** *(was 6.1, −0.1)*

**Improvements since V2**

- NSE archive backfill landed **123 scored bulk deals** (real IN labels incoming)
- Free-data pull stores **~3k+ EOD rows** — foundation for offline feature cache
- Unified ranking surfaces **investor backing before est. return** — correct product prior even when ML is weak
- Data maturity badges + prediction meta block remain honest

**Still broken / risky**

- `model_meta.json` unchanged: **`positive_rate: 0.0`**, **188 samples**, `test_accuracy: 1.0` (trivial classifier)
- **`train.py` still has no abort gate** — council V1/V2 recommendation unimplemented
- Random `train_test_split` — no date-based walk-forward
- Scoring path still hits **yfinance live**; stored EOD unused
- SEC 13F dominates DB (~14k signals) while IN bulk remains thin — training distribution skewed

**Verdict:** **More data plumbing, same statistical trust.** Rule-based tiers + investor intel are the honest signal today; do not treat LightGBM output as edge.

---

## 3. Ridge — DevOps & Reliability

**Score: 6.7 / 10** *(was 6.8, −0.1)*

**Improvements**

- Explicit **DNS 8.8.8.8 / 1.1.1.1** on compose services (NSE/BSE fetch reliability)
- Postgres bound to **127.0.0.1:5433** — safer host exposure
- **`scripts/pull_all_free_data.py`** + scheduler hook + System page button — operable ingest
- Live package mounts — faster iteration without full image rebuild

**Regressions / gaps observed**

- **Redis DNS failure** on `api` restart → nginx **502** (`Temporary failure in name resolution`)
- NSE historical API returned **503** on 90-day backfill; archive CSV capped at **123 valid rows**
- BSE bulk ingest often blocked by network
- **Laptop sleep = outage**; no catch-up queue for missed cron (still open since V1)
- WAHA session fragility unchanged
- Large uncommitted batch — no CI gate on the diff

**Verdict:** **Better developer ergonomics**, **same homelab SLOs**. Fix Redis/network stability before calling it always-on.

---

## 4. Cipher — Security & Compliance

**Score: 5.9 / 10** *(unchanged)*

**New surface area**

- **`/share` landing** and **`/share/ranked-picks`** expose ranked picks + investor backing to anyone with share token
- Share URLs in WhatsApp list full pick detail links — token leakage = read access to all picks
- Query fallback `/open?s=&k=` — token in URL (browser history / referrer risk)

**Unchanged risks**

- Default `admin/changeme`; predictable share token pattern
- Dashboard on LAN `0.0.0.0:80`; HTTP unless Tailscale/CF
- Portfolio CRUD without per-user scoping
- WAHA credentials in plaintext `.env`

**Verdict:** **Acceptable for private LAN + rotated secrets.** Share token is now the critical secret — treat like an API key.

---

## 5. Mira — Product / UX

**Score: 9.1 / 10** *(was 8.8, +0.3)*

**Major wins**

- **Share landing (`/h/{token}`, `/share`)** — numbered ranked index with tap-to-open links; no blind redirect
- **Unified WhatsApp digest** — single `1…N` list (bulk + demand merged) instead of split bulk / `T1` sections
- **Investor intel on Demand + All Signals** — same backing table as Bulk tab
- **`rank_index` on live-picks** — smart-money backing → est. return, consistent with HomePage sort
- **IST calendar dates** across backend + dashboard — fixes “2 days old but shows 7/1” trust bug
- sslip.io + query fallback for WhatsApp linkify pain

**Still missing**

- Broker sync / live P&L
- Push when data maturity flips to “labeled”
- Offline / HTTPS without same-WiFi caveat
- README still references `:3000` while prod links use port 80

**Verdict:** **Near best-in-class for a solo operator.** Phone-first share flow is now complete; remaining gaps are deployment and broker integration.

---

## 6. Quill — Markets Domain & Data

**Score: 7.6 / 10** *(was 7.4, +0.2)*

**Improvements**

- **10 free ingest jobs**: NSE EOD, FII/DII, announcements, bhavcopy, BSE bulk, SEC Form4/13F/8-K, macro themes, FRED/World Bank
- **123 NSE bulk deals** backfilled and rescored — IN path no longer SEC-only in practice
- Ranking prioritizes **investor count / deal confluence** before headline return — domain-correct
- Bulk-backed demand picks prepend with full investor intel block

**Domain gaps**

- DB still **SEC-heavy** (~14k 13F vs ~123 IN bulk) — US noise dilutes training
- NSE historical API **503**; archive CSV quality limits backfill depth
- BSE bulk unreliable; no ASM/GSM surveillance filter
- Expected returns remain **heuristic** — not backtested portfolio simulation
- Stored EOD not yet used to replace yfinance gaps on delisted tickers

**Verdict:** **Richer public-data surface**; IN bulk path finally live but **not yet deep enough** for confident ML.

---

## Score summary

| Expert | Area | V1 | V2 | V3 | Δ vs V2 |
|--------|------|---:|---:|---:|--------:|
| Atlas | Architecture | 7.4 | 7.8 | 8.0 | +0.2 |
| Nova | ML / scoring | 5.8 | 6.1 | 6.0 | −0.1 |
| Ridge | DevOps | 6.6 | 6.8 | 6.7 | −0.1 |
| Cipher | Security | 6.2 | 5.9 | 5.9 | 0.0 |
| Mira | Product / UX | 8.1 | 8.8 | 9.1 | +0.3 |
| Quill | Domain / data | 7.0 | 7.4 | 7.6 | +0.2 |
| **Council mean** | | **6.9** | **7.2** | **7.2** | **0.0** |

**Letter grade (personal-use tool): A−**  
**Letter grade (institutional / automated trading): D+**

---

## Synthesized verdict

V3 council consensus: Trade Bot **held its overall grade** while **shifting weight toward product excellence**. Mira (+0.3) and Quill (+0.2) reflect a system that now **explains, ranks, and links picks the way a human trader expects** — numbered WhatsApp digest, share landing, investor backing everywhere, IST dates.

Nova (−0.1) and Ridge (−0.1) remind that **infrastructure and statistics did not keep pace with UX**. Storing EOD prices without using them, training on a 0% positive-rate set, and Redis DNS flaps are the gap between “beautiful dashboard” and “trustworthy edge.”

**Unanimous top priority (unchanged from V1/V2):**

> Fix ML training gate — refuse deploy if `positive_rate < 5%`; switch to date-based CV; prioritize IN bulk labels over SEC 13F flood.

**New V3 priorities (ordered):**

1. **Wire `eod_prices` into `features.py`** — stop live yfinance on every score; use stored cache with fallback
2. **Redis / Docker network hardening** — fix DNS resolution failures that cause 502 on API restart
3. **Retry NSE historical backfill** when API recovers; target ≥500 IN bulk labels
4. **Commit + CI smoke** — pytest + `stress_test_api.py` on the current uncommitted batch
5. **Rotate share token** — it now gates the entire ranked pick index

**Blockers before live automated trading (unchanged):**

1. ML label quality + time-split validation  
2. Paper trading with slippage measurement  
3. Cipher security pass on credentials + order path  

---

## Improvement roadmap (V3 → V4)

| Priority | Item | Owner | ETA |
|----------|------|-------|-----|
| P0 | ML training abort if `positive_rate < 5%` | Nova | 2 days |
| P0 | Fix Redis DNS / api 502 on restart | Ridge | 1 day |
| P1 | Wire `eod_prices` → feature builder | Atlas/Nova | 1 week |
| P1 | NSE historical backfill retry + label count dashboard | Quill | 1 week |
| P2 | Filter SEC 13F from IN bulk training set | Nova | 3 days |
| P2 | HTTPS via Tailscale (see [HTTPS_SETUP.md](./HTTPS_SETUP.md)) | Ridge/Cipher | 1 week |
| P3 | Paper order drafts | Atlas | 2 weeks |

---

## What changed since V2 (changelog for council)

| Area | Shipped |
|------|---------|
| Ranking | `notifier/ranking.py`, live-picks re-sort, `rank_index`, unified daily WhatsApp |
| Links | Share landing page, `/share/ranked-picks`, sslip.io + `/open?k=` fallback |
| Investor intel | `_attach_investor_intel()` on demand, all-signals, bulk-backed demand prepend |
| Data | `pull_free.py`, migration 004, System page pull button, 123 NSE bulk backfill |
| Dates | IST anchoring for maturity, disclosure labels, hold windows |
| Ops | Compose DNS, volume mounts, postgres localhost bind |

| Area | Not yet shipped |
|------|-----------------|
| ML | Training gate, time-split CV, EOD-driven features |
| Ops | Catch-up cron, Prometheus/uptime, CI on PR |
| Domain | ASM/GSM block list, BSE reliability |
| Product | Broker sync, maturity-flip push alerts |

---

*Council V3 complete. Next review after: (a) ML gate + 500 IN bulk labels, or (b) paper trading Phase A, or (c) EOD wired into scoring.*
