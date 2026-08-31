# Live constraints (IN)

Documented before any live expansion. Update when broker/account terms change.

## Equity cash / MIS (retail, typical)

- Peak margin rules (SEBI): effective leverage on cash equities is commonly **well below** sim heroes (often ~5× MIS on select names — **verify with your broker**).
- Sim `max_leverage=75` / effective ~20–25× target-return sizing is **research-only** and not assumed available live.

## Product lane caps (this repo)

- Session guards: `max_daily_loss_pct` / `max_trade_risk_pct` (see `ORWIDTH_GUARD_DEFAULTS`).
- Live executor: `packages/broker/risk.py` notional caps (e.g. ₹1000/trade IN base) + dual ACK for live.

## Instrument path

Default product path: **NSE cash equities**, paper first.

F&O / higher leverage: only after explicit account confirmation and a separate sim with real contract costs — do not silently map 75× heroes onto live.

## Paper month

Treat paper as **infra + behavior** shakeout. Strategy edge needs longer OOS than ~22 sessions for statistical confidence.
