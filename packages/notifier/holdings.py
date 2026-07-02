"""WhatsApp digest of stocks currently in an active hold window."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc

from core.config import get_settings
from core.db import SessionLocal
from core.models import AlertLog, Signal, SignalScore
from notifier.ntfy import send_ntfy
from notifier.templates import holdings_message
from notifier.waha import send_whatsapp, waha_healthy
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
settings = get_settings()
IST = ZoneInfo("Asia/Kolkata")

ACTIVE_STATUSES = ("active", "review_due", "exit_window")


def _latest_score(db, signal_id) -> SignalScore | None:
  return (
    db.query(SignalScore)
    .filter(SignalScore.signal_id == signal_id)
    .order_by(desc(SignalScore.scored_at))
    .first()
  )


def _collect_holdings(db, market: str | None, limit: int) -> list[tuple[Signal, SignalScore]]:
  since = datetime.now(timezone.utc) - timedelta(days=120)
  signals = (
    db.query(Signal)
    .filter(
      Signal.disclosed_at >= since,
      Signal.action.in_(["BUY", "P", "A"]),
    )
    .order_by(desc(Signal.disclosed_at))
    .all()
  )

  ranked: list[tuple[float, Signal, SignalScore]] = []
  for signal in signals:
    if market and signal.market != market.upper():
      continue
    score = _latest_score(db, signal.id)
    if not score or not score.return_distribution:
      continue
    dist = score.return_distribution
    if dist.get("hold_status") not in ACTIVE_STATUSES:
      continue
    if not dist.get("hold_days"):
      continue
    rem = float(dist.get("days_remaining") if dist.get("days_remaining") is not None else 999)
    exp = float(dist.get("expected_return_pct") or 0)
    ranked.append((rem * 0.6 - exp * 100 * 0.4, signal, score))

  ranked.sort(key=lambda x: x[0])

  # One row per ticker (most urgent hold)
  best: dict[str, tuple[Signal, SignalScore]] = {}
  order: list[str] = []
  for _, signal, score in ranked:
    if signal.ticker in best:
      continue
    best[signal.ticker] = (signal, score)
    order.append(signal.ticker)

  return [best[t] for t in order[:limit]]


def send_holdings_digest(market: str = "IN", *, force: bool = False, limit: int | None = None) -> dict:
  if not settings.alerts_enabled:
    return {"sent": False, "reason": "disabled"}

  max_items = limit or settings.holdings_whatsapp_max
  db = SessionLocal()
  try:
    holdings = _collect_holdings(db, market, max_items)
    day = datetime.now(IST).date().isoformat()
    dedup = f"holdings_digest:{market}:{day}"
    if not force and db.query(AlertLog).filter(AlertLog.dedup_key == dedup).first():
      return {"sent": False, "reason": "already_sent_today", "holdings": len(holdings)}

    url = settings.dashboard_public_url.rstrip("/")
    text = holdings_message(holdings, url, market=market)

    if force:
      db.query(AlertLog).filter(AlertLog.dedup_key == dedup).delete()
      db.commit()

    log = AlertLog(dedup_key=dedup, channel="whatsapp", payload=text, status="pending")
    db.add(log)
    db.commit()

    sent = send_whatsapp(text) if waha_healthy() else send_ntfy(text)
    log.channel = "whatsapp" if waha_healthy() else "ntfy"
    log.status = "sent" if sent else "failed"
    log.sent_at = datetime.now(timezone.utc) if sent else None
    db.commit()

    return {
      "sent": sent,
      "holdings": len(holdings),
      "market": market,
      "tickers": [s.ticker for s, _ in holdings],
    }
  finally:
    db.close()
