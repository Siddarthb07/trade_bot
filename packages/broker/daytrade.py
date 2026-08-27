"""Day-book flatten + opening-range breakout scan jobs (session bars required)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from broker.executor import get_adapter, submit_sized_order
from broker.session import should_flatten_in_day, should_flatten_us_day
from core.db import SessionLocal
from core.models import PortfolioPosition
from processor.intraday_bars import fetch_intraday_bars, session_closes
from processor.strategies import intraday_orb

logger = logging.getLogger(__name__)


def flatten_day_book(db: Session, market: str, *, reason: str) -> dict:
  """Close open auto day-book positions for a market."""
  m = market.upper()
  adapter = get_adapter(m)
  broker_results = []
  try:
    broker_results = [
      {"status": r.status, "reject": r.reject_reason, "broker_order_id": r.broker_order_id}
      for r in adapter.flatten_all(reason)
    ]
  except Exception as exc:
    logger.exception("Broker flatten failed for %s: %s", m, exc)

  closed = 0
  positions = (
    db.query(PortfolioPosition)
    .filter(PortfolioPosition.market == m, PortfolioPosition.status == "open", PortfolioPosition.source == "auto")
    .all()
  )
  now = datetime.now(timezone.utc)
  for pos in positions:
    notes = pos.notes or ""
    if "book=day" not in notes and "strategy=intraday_orb" not in notes:
      continue
    pos.status = "sold"
    pos.exit_date = now
    pos.exit_price = pos.entry_price
    pos.notes = notes + f" | flattened:{reason}"
    pos.updated_at = now
    closed += 1
  db.commit()
  return {"market": m, "local_closed": closed, "broker": broker_results, "disarmed": True}


def run_in_day_flatten_if_due() -> dict:
  if not should_flatten_in_day():
    return {"status": "skip", "reason": "not_flatten_window"}
  db = SessionLocal()
  try:
    out = flatten_day_book(db, "IN", reason="in_session_close")
    from broker.risk import end_session_disarm

    end_session_disarm(db, "IN")
    return out
  finally:
    db.close()


def run_us_day_flatten_if_due() -> dict:
  if not should_flatten_us_day():
    return {"status": "skip", "reason": "not_flatten_window"}
  db = SessionLocal()
  try:
    out = flatten_day_book(db, "US", reason="us_session_close")
    from broker.risk import end_session_disarm

    end_session_disarm(db, "US")
    return out
  finally:
    db.close()


def scan_orb_candidates(db: Session, *, market: str, tickers: list[str], book_cap_prob: float = 0.62) -> list[dict]:
  """Evaluate ORB on same-session intraday bars only; refuse daily closes."""
  out = []
  today = date.today().isoformat()
  for ticker in tickers:
    bars = fetch_intraday_bars(ticker, session_date=today, interval="5m", market=market)
    closes = session_closes(bars)
    if len(closes) < 12:
      out.append({"ticker": ticker, "signal": "flat", "conf": 0.5, "reason": "needs_intraday_session_bars"})
      continue
    sig = intraday_orb(closes, open_range_bars=5, session_bars=closes)
    out.append({"ticker": ticker, "signal": sig.side, "conf": sig.confidence, "reason": sig.reason})
    if sig.side == "buy" and sig.confidence >= book_cap_prob:
      submit_sized_order(
        db,
        market=market,
        ticker=ticker.split(".")[0],
        ticker_normalized=ticker,
        side="buy",
        last_price=closes[-1],
        predicted_prob=sig.confidence,
        strategy_id="intraday_orb",
        book="day",
      )
  return out
