"""Bulk-deal confluence with macro/demand picks (Phase 2.2)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from core.models import Signal

BULK_SOURCES = ("nse_bulk", "nse_block")


def bulk_confluence(
  db: Session,
  ticker: str,
  market: str,
  *,
  since_days: int = 30,
) -> dict:
  since = datetime.now(timezone.utc) - timedelta(days=since_days)
  deals = (
    db.query(Signal)
    .filter(
      Signal.ticker == ticker,
      Signal.market == market,
      Signal.source.in_(BULK_SOURCES),
      Signal.disclosed_at >= since,
      Signal.action.in_(["BUY", "P", "A"]),
    )
    .order_by(Signal.disclosed_at.desc())
    .all()
  )
  investors = list({d.entity for d in deals})[:5]
  return {
    "has_bulk_deal": len(deals) > 0,
    "bulk_deal_count": len(deals),
    "bulk_confirmed": len(deals) > 0,
    "bulk_investors": investors,
    "latest_bulk_at": deals[0].disclosed_at.isoformat() if deals else None,
  }


def apply_bulk_confidence_boost(probability: float | None, *, bulk_confirmed: bool, boost: float = 0.05) -> float | None:
  if probability is None:
    return None
  if not bulk_confirmed:
    return probability
  return min(0.85, float(probability) + boost)
