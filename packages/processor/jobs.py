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
        maybe_notify_signal(db, signal, score)
        processed += 1
      except Exception as exc:
        logger.exception("Failed processing signal %s: %s", sid, exc)
        db.rollback()
  finally:
    db.close()
  return {"processed": processed}
