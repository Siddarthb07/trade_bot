"""Freeze prediction snapshots for online learning (no look-ahead at train time)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.config import get_settings
from core.models import PredictionEvent, Signal
from processor.features import FEATURE_KEYS, features_to_vector
from processor.train import _load_meta

settings = get_settings()


def upsert_bulk_prediction_event(
  db: Session,
  signal: Signal,
  *,
  features: dict,
  predicted_prob: float | None,
  predicted_tier: str | None,
  scorer_version: str,
) -> PredictionEvent | None:
  """Snapshot features + prob at score time for bulk ML / interim scorers."""
  if signal.source == "macro_theme":
    return None
  if signal.action.upper() not in ("BUY", "P", "A"):
    return None

  meta = _load_meta()
  model_trained_at = meta.get("trained_at") if isinstance(meta, dict) else None
  vec = features_to_vector(features)
  # Keep only serializable feature keys
  feat_payload = {k: features.get(k) for k in FEATURE_KEYS}

  existing = (
    db.query(PredictionEvent)
    .filter(
      PredictionEvent.signal_id == signal.id,
      PredictionEvent.kind == "bulk_ml",
      PredictionEvent.scorer_version == scorer_version,
      PredictionEvent.labeled.is_(False),
    )
    .order_by(PredictionEvent.created_at.desc())
    .first()
  )
  if existing is None:
    existing = PredictionEvent(
      signal_id=signal.id,
      kind="bulk_ml",
      scorer_version=scorer_version,
    )
    db.add(existing)

  existing.model_trained_at = model_trained_at
  existing.features = feat_payload
  existing.feature_vector = vec
  existing.predicted_prob = predicted_prob
  existing.predicted_tier = predicted_tier
  db.flush()
  return existing


def label_prediction_events_for_signal(
  db: Session,
  signal_id,
  *,
  return_pct: float,
  price_source: str,
  window: str | None = None,
) -> int:
  """Attach outcome to unlabeled bulk_ml events for this signal."""
  if (price_source or "").lower() in ("", "missing", "immature"):
    return 0
  window = window or settings.win_window
  win = return_pct > settings.win_threshold_pct
  now = datetime.now(timezone.utc)
  events = (
    db.query(PredictionEvent)
    .filter(
      PredictionEvent.signal_id == signal_id,
      PredictionEvent.kind == "bulk_ml",
      PredictionEvent.labeled.is_(False),
    )
    .all()
  )
  n = 0
  for ev in events:
    ev.labeled = True
    ev.actual_return_pct = return_pct
    ev.actual_win = win
    ev.label_window = window
    ev.labeled_at = now
    n += 1
  return n


def record_live_pnl_event(
  db: Session,
  *,
  position_id,
  signal_id,
  predicted_prob: float | None,
  actual_return_pct: float,
  features: dict | None = None,
) -> PredictionEvent:
  """Overlay label from a closed portfolio/broker position (not mixed into LightGBM)."""
  win = actual_return_pct > settings.win_threshold_pct
  ev = PredictionEvent(
    signal_id=signal_id,
    position_id=position_id,
    kind="live_pnl",
    scorer_version="live-pnl-v1",
    features=features,
    feature_vector=features_to_vector(features) if features else None,
    predicted_prob=predicted_prob,
    labeled=True,
    actual_return_pct=actual_return_pct,
    actual_win=win,
    label_window="position",
    labeled_at=datetime.now(timezone.utc),
  )
  db.add(ev)
  db.flush()
  return ev
