#!/usr/bin/env python3
"""Label matured BUY signals until we have enough 1mo training rows."""

from __future__ import annotations

import time

from sqlalchemy import func

from core.config import get_settings
from core.db import SessionLocal
from core.models import ForwardReturn, Signal
from processor.forward_backfill import backfill_mature_forward_returns
from processor.returns import clear_hist_cache


def _label_stats() -> dict:
  settings = get_settings()
  db = SessionLocal()
  try:
    q = (
      db.query(func.count(ForwardReturn.id))
      .join(Signal, Signal.id == ForwardReturn.signal_id)
      .filter(
        Signal.market == "IN",
        Signal.source.in_(["nse_bulk", "nse_block", "bse_bulk"]),
        Signal.action.in_(["BUY", "P", "A"]),
        ForwardReturn.window == settings.win_window,
        ForwardReturn.return_pct.isnot(None),
        ~ForwardReturn.price_source.in_(["", "missing", "immature"]),
      )
    )
    n = q.scalar() or 0
    wins = (
      db.query(func.count(ForwardReturn.id))
      .join(Signal, Signal.id == ForwardReturn.signal_id)
      .filter(
        Signal.market == "IN",
        Signal.source.in_(["nse_bulk", "nse_block", "bse_bulk"]),
        Signal.action.in_(["BUY", "P", "A"]),
        ForwardReturn.window == settings.win_window,
        ForwardReturn.return_pct > settings.win_threshold_pct,
        ~ForwardReturn.price_source.in_(["", "missing", "immature"]),
      )
      .scalar()
      or 0
    )
    return {
      "window": settings.win_window,
      "labeled": n,
      "wins": wins,
      "positive_rate": (wins / n) if n else 0.0,
    }
  finally:
    db.close()


def main() -> None:
  settings = get_settings()
  target = max(settings.ml_train_min_samples * 3, 150)
  max_rounds = 40
  for round_i in range(1, max_rounds + 1):
    clear_hist_cache()
    result = backfill_mature_forward_returns(batch_size=120, markets=["IN"])
    stats = _label_stats()
    print({"round": round_i, "backfill": result, "stats": stats})
    if stats["labeled"] >= target and stats["positive_rate"] >= settings.ml_min_positive_rate:
      print({"done": True, "reason": "enough_labels"})
      return
    if result.get("processed_signals", 0) == 0:
      print({"done": True, "reason": "no_more_candidates"})
      return
    time.sleep(1)
  print({"done": False, "reason": "max_rounds", "stats": _label_stats()})


if __name__ == "__main__":
  main()
