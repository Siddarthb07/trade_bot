"""RQ processor jobs."""

from __future__ import annotations

import logging
import uuid

from core.config import get_settings
from core.db import SessionLocal
from core.models import ForwardReturn, Signal
from notifier.dispatch import maybe_notify_signal
from processor.returns import compute_forward_returns
from processor.scoring import score_signal
from processor.stats import recompute_investor_stats

logger = logging.getLogger(__name__)
settings = get_settings()


def process_batch(signal_ids: list[str]) -> dict:
  db = SessionLocal()
  processed = 0
  try:
    for sid in signal_ids:
      try:
        signal = db.query(Signal).filter(Signal.id == uuid.UUID(sid)).first()
        if not signal:
          continue
        returns = compute_forward_returns(signal.ticker_normalized, signal.disclosed_at)
        for window, (return_pct, price_source) in returns.items():
          # Never persist immature/missing as 0.0 — wait until the window matures.
          if return_pct is None:
            continue
          fr = (
            db.query(ForwardReturn)
            .filter(ForwardReturn.signal_id == signal.id, ForwardReturn.window == window)
            .first()
          )
          if fr is None:
            fr = ForwardReturn(signal_id=signal.id, window=window)
            db.add(fr)
          fr.return_pct = return_pct
          fr.price_source = price_source
        db.commit()
        recompute_investor_stats(db, signal.market)
        score = score_signal(db, signal)
        try:
          from broker.executor import try_auto_trade_signal
          from processor.market_data import compute_trend_features

          dist = score.return_distribution or {}
          prob = dist.get("calibrated_probability")
          trend = compute_trend_features(signal.ticker_normalized, db=db, market=signal.market)
          last_px = trend.get("current_price")
          if prob is not None and last_px:
            try_auto_trade_signal(db, signal, float(prob), float(last_px))
        except Exception as exc:
          logger.debug("Auto-trade skip for %s: %s", sid, exc)
        maybe_notify_signal(db, signal, score)
        processed += 1
      except Exception as exc:
        logger.exception("Failed processing signal %s: %s", sid, exc)
        db.rollback()
  finally:
    db.close()
  return {"processed": processed}
