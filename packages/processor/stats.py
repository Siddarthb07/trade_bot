"""Investor statistics aggregation."""

from __future__ import annotations

import statistics
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.config import get_settings
from core.models import ForwardReturn, InvestorStat, Signal

settings = get_settings()


def recompute_investor_stats(db: Session, market: str | None = None) -> int:
  query = db.query(Signal)
  if market:
    query = query.filter(Signal.market == market)
  signals = query.all()
  grouped: dict[tuple[str, str], list[float]] = {}
  for signal in signals:
    fr = (
      db.query(ForwardReturn)
      .filter(ForwardReturn.signal_id == signal.id, ForwardReturn.window == settings.win_window)
      .first()
    )
    if fr is None or fr.return_pct is None:
      continue
    key = (signal.entity_normalized, signal.market)
    grouped.setdefault(key, []).append(fr.return_pct)

  updated = 0
  for (entity, mkt), returns in grouped.items():
    wins = [r for r in returns if r > settings.win_threshold_pct]
    win_rate = len(wins) / len(returns) if returns else None
    median_return = statistics.median(returns) if returns else None
    stat = (
      db.query(InvestorStat)
      .filter(InvestorStat.entity_normalized == entity, InvestorStat.market == mkt)
      .first()
    )
    if stat is None:
      stat = InvestorStat(entity_normalized=entity, market=mkt)
      db.add(stat)
    stat.win_rate = win_rate
    stat.median_return = median_return
    stat.n_trades = len(returns)
    stat.updated_at = datetime.now(timezone.utc)
    updated += 1
  db.commit()
  return updated
