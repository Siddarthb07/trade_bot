"""Label matured signals with forward returns (Phase 2.3)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from core.db import SessionLocal
from core.models import ForwardReturn, Signal
from ingest.common import finish_ingestion_run, start_ingestion_run
from processor.returns import WINDOW_DAYS, compute_forward_returns
from processor.stats import recompute_investor_stats

logger = logging.getLogger(__name__)


def _needs_label(db: Session, signal: Signal, window: str, now: datetime) -> bool:
  age_days = (now - signal.disclosed_at).days
  if age_days < WINDOW_DAYS[window]:
    return False
  fr = (
    db.query(ForwardReturn)
    .filter(ForwardReturn.signal_id == signal.id, ForwardReturn.window == window)
    .first()
  )
  return fr is None or fr.return_pct is None


def backfill_mature_forward_returns(
  db: Session | None = None,
  *,
  batch_size: int = 40,
  markets: list[str] | None = None,
) -> dict:
  """Compute forward returns for signals whose outcome windows have matured."""
  own_db = db is None
  if own_db:
    db = SessionLocal()
  run = start_ingestion_run(db, "forward_return_backfill")
  processed = 0
  windows_labeled = 0
  errors = 0
  now = datetime.now(timezone.utc)
  markets_seen: set[str] = set()

  try:
    min_age = now - timedelta(days=min(WINDOW_DAYS.values()))
    query = db.query(Signal).filter(Signal.disclosed_at <= min_age)
    if markets:
      query = query.filter(Signal.market.in_([m.upper() for m in markets]))
    candidates = query.order_by(Signal.disclosed_at.asc()).limit(batch_size * 5).all()

    for signal in candidates:
      if processed >= batch_size:
        break
      windows = [w for w in WINDOW_DAYS if _needs_label(db, signal, w, now)]
      if not windows:
        continue
      try:
        returns = compute_forward_returns(signal.ticker_normalized, signal.disclosed_at)
        for window in windows:
          return_pct, price_source = returns.get(window, (None, "missing"))
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
          windows_labeled += 1
        db.commit()
        markets_seen.add(signal.market)
        processed += 1
      except Exception as exc:
        logger.exception("Forward backfill failed for %s: %s", signal.id, exc)
        db.rollback()
        errors += 1

    for market in markets_seen:
      recompute_investor_stats(db, market)

    finish_ingestion_run(
      db,
      run,
      rows_in=len(candidates),
      rows_new=windows_labeled,
      status="success" if errors == 0 else "partial",
      error=f"{errors} signal errors" if errors else None,
    )
    result = {"processed_signals": processed, "windows_labeled": windows_labeled, "errors": errors}
    logger.info("Forward return backfill: %s", result)
    return result
  except Exception as exc:
    finish_ingestion_run(db, run, rows_in=0, rows_new=0, status="failed", error=str(exc))
    raise
  finally:
    if own_db:
      db.close()


def run_scheduled_forward_backfill() -> dict:
  db = SessionLocal()
  try:
    return backfill_mature_forward_returns(db, batch_size=50)
  finally:
    db.close()
