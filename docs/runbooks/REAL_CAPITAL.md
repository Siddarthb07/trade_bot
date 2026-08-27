# Real-capital readiness runbook (personal use)

**Not investment advice.** This system is a personal research / paper lab. Do not market it as advice to others without proper registration.

## Gates (fail closed)

| Stage | Pass criteria | Block until |
|-------|---------------|-------------|
| A Intraday truth | Session day-sim uses 5m bars + cost model; no edge metrics from `setup_fallback` | Done in code |
| B Walk-forward | ≥3 tickers ambition-pass with **n≥30** OOS, hit≥85%, expectancy>0, regime tag | `scripts/validate_adaptive_profiles.py --require-eligible` — **see [STAGE_B_STATUS.md](../STAGE_B_STATUS.md)** |
| C Live paper | ≥60–90 trading days, expectancy>0 after costs, ≥50 closed trades | `/exec/paper-metrics` + Sunday `paper_weekly_freeze` |
| D Micro live | Dual ACK + phrase `I_ACCEPT_MICRO_LIVE_RISK`; caps ₹1000 / $10 | Env + `/exec/enable-live` |
| E Scale | Cap ladder step-up only if rolling expectancy>0 | `/exec/cap-ladder/step-up` |
| F Ops | Receipts + model pin + this runbook | `/exec/receipts`, `/exec/model-pin` |

## Session arm / kill

1. Default: `kill_switch=true`, `session_armed=false`.
2. `POST /exec/arm` — arms IN+US, clears kill for the session.
3. `POST /exec/kill?market=ALL` — immediate halt.
4. Session flatten (IN 15:16 IST / US 01:15 IST) closes day book **and re-arms kill** until next manual arm.

## Flatten failure

- If broker `flatten_all` errors, local day positions are still marked sold; check broker UI manually.
- Data gap / no intraday bars → ORB returns `needs_intraday_session_bars` → **no trade**.

## Broker outage

- Live mode without ACK / phrase falls back to **paper**.
- Reject reasons appear on `/exec/live` tape and `models/decision_receipts.jsonl`.

## Model pin / rollback

1. After a green adaptive search: `POST /exec/model-pin` → writes `models/model_pin.json`.
2. Every order appends a receipt with the pin snapshot.
3. To rollback eligibility: restore prior `ticker_adaptive_profiles.json` from git, re-pin, kill sessions.

## Enable micro-live (Stage D)

```env
EXEC_MODE_IN=live
EXEC_LIVE_ACK_IN=true
EXEC_LIVE_CONFIRM_PHRASE=I_ACCEPT_MICRO_LIVE_RISK
```

Then `POST /exec/enable-live?market=IN&phrase=I_ACCEPT_MICRO_LIVE_RISK&ack=true` to verify.
Caps stay at Stage-0 until Stage E ladder steps.

## Weekly freeze (Stage C)

Sunday 06:00 IST job calls `apply_weekly_freeze_if_needed`: if 30d (≥20 trades) or 90d (≥50) expectancy ≤ 0 → kill ALL + revoke `ambition_pass`.

## Cap ladder (Stage E)

Never size to a ₹/day income target. Step up only via `/exec/cap-ladder/step-up` when metrics pass; any breach → `/exec/cap-ladder/step-down`.

## Disclaimer

Personal capital only. Public UI and READMEs must keep **Not investment advice**.
