"""Investor-specific hold period stats (Phase 4.1)."""

from __future__ import annotations

import statistics

from sqlalchemy.orm import Session

from core.config import get_settings
from core.models import ForwardReturn, Signal

settings = get_settings()
WINDOW_DAYS = {"1w": 7, "1mo": 30, "3mo": 90}


def investor_median_peak_days(db: Session, entity_normalized: str, market: str) -> dict:
  """Median days to first positive forward return for an investor's bulk buys."""
  signals = (
    db.query(Signal)
    .filter(
      Signal.entity_normalized == entity_normalized,
      Signal.market == market,
      Signal.source.in_(["nse_bulk", "nse_block"]),
    )
    .all()
  )
  peak_days: list[int] = []
  for signal in signals:
    for window in ("1w", "1mo", "3mo"):
      fr = (
        db.query(ForwardReturn)
        .filter(ForwardReturn.signal_id == signal.id, ForwardReturn.window == window)
        .first()
      )
      if fr and fr.return_pct is not None and fr.return_pct > settings.win_threshold_pct:
        peak_days.append(WINDOW_DAYS[window])
        break

  if not peak_days:
    return {
      "median_peak_days": None,
      "n_labeled": 0,
      "label": None,
    }

  median = int(statistics.median(peak_days))
  return {
    "median_peak_days": median,
    "n_labeled": len(peak_days),
    "label": f"This investor's past bulk buys peaked in ~{median} days (median)",
  }


def blend_investor_hold_days(rule_days: int, investor_median: int | None, weight: float = 0.25) -> int:
  if investor_median is None or investor_median < 1:
    return rule_days
  return int(round((1 - weight) * rule_days + weight * investor_median))
