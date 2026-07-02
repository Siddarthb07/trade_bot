"""Aggregate NSE bulk/block investor backing for a ticker."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from core.models import InvestorStat, Signal
from core.tickers import normalize_entity

BULK_SOURCES = ("nse_bulk", "nse_block")
BUY_ACTIONS = ("BUY", "P", "A")


def bulk_investor_breakdown(
  db: Session,
  ticker: str,
  market: str,
  *,
  since_days: int = 14,
  limit: int = 12,
) -> dict[str, Any]:
  """Who bought how much — grouped by investor, sorted by total value."""
  since = datetime.now(timezone.utc) - timedelta(days=since_days)
  deals = (
    db.query(Signal)
    .filter(
      Signal.ticker == ticker,
      Signal.market == market.upper(),
      Signal.source.in_(BULK_SOURCES),
      Signal.disclosed_at >= since,
      Signal.action.in_(BUY_ACTIONS),
    )
    .order_by(Signal.disclosed_at.desc())
    .all()
  )

  by_entity: dict[str, dict[str, Any]] = {}
  total = 0.0
  for deal in deals:
    val = float(deal.value or 0)
    total += val
    row = by_entity.get(deal.entity)
    if row is None:
      row = {
        "entity": deal.entity,
        "entity_normalized": deal.entity_normalized,
        "total_value": 0.0,
        "deal_count": 0,
        "latest_at": deal.disclosed_at.isoformat(),
        "action": deal.action,
        "qty": deal.qty,
        "source": deal.source,
      }
      by_entity[deal.entity] = row
    row["total_value"] += val
    row["deal_count"] += 1
    if deal.disclosed_at >= datetime.fromisoformat(row["latest_at"].replace("Z", "+00:00")):
      row["latest_at"] = deal.disclosed_at.isoformat()
      row["action"] = deal.action
      row["qty"] = deal.qty
      row["source"] = deal.source

  investors = sorted(by_entity.values(), key=lambda x: x["total_value"], reverse=True)[:limit]
  tracked_wr: list[float] = []
  tracked_med: list[float] = []
  tracked_n = 0
  for inv in investors:
    inv["total_value"] = round(inv["total_value"], 2)
    qty = inv.get("qty")
    val = inv["total_value"]
    if qty and qty > 0 and val > 0:
      inv["implied_price"] = round(val / float(qty), 2)
    norm = inv.get("entity_normalized") or normalize_entity(inv["entity"])
    stat = (
      db.query(InvestorStat)
      .filter(InvestorStat.entity_normalized == norm, InvestorStat.market == market.upper())
      .first()
    )
    if stat and stat.n_trades:
      inv["win_rate"] = stat.win_rate
      inv["median_return"] = stat.median_return
      inv["n_trades"] = stat.n_trades
      tracked_n += stat.n_trades
      if stat.win_rate is not None:
        tracked_wr.append(stat.win_rate)
      if stat.median_return is not None:
        tracked_med.append(stat.median_return)
    else:
      inv["win_rate"] = None
      inv["median_return"] = None
      inv["n_trades"] = 0

  aggregate_win_rate = sum(tracked_wr) / len(tracked_wr) if tracked_wr else None
  aggregate_median = sum(tracked_med) / len(tracked_med) if tracked_med else None
  latest_bulk_at = max((d.disclosed_at for d in deals), default=None)

  return {
    "investors": investors,
    "total_value": round(total, 2),
    "investor_count": len(by_entity),
    "deal_count": len(deals),
    "window_days": since_days,
    "latest_bulk_at": latest_bulk_at.isoformat() if latest_bulk_at else None,
    "aggregate_win_rate": round(aggregate_win_rate, 4) if aggregate_win_rate is not None else None,
    "aggregate_median_return": round(aggregate_median, 4) if aggregate_median is not None else None,
    "tracked_past_trades": tracked_n,
  }
