"""LightGBM training with Platt calibration."""

from __future__ import annotations

import json
import os
import pickle
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.calibration import CalibratedClassifierCV

from core.config import get_settings
from core.db import SessionLocal
from core.models import ForwardReturn, Signal, SignalScore
from processor.features import build_features, features_to_vector

MODEL_DIR = Path(os.environ.get("MODEL_DIR", "/app/models"))
MODEL_PATH = MODEL_DIR / "lgbm_calibrated.pkl"
META_PATH = MODEL_DIR / "model_meta.json"

settings = get_settings()


WINDOW_DAYS = {"1w": 7, "1mo": 30, "3mo": 90, "6mo": 180}
DEFAULT_HOLD_PRIORS = {"HIGH": 14, "MEDIUM": 28, "LOW": 42, "default": 30}


def training_allowed(positive_rate: float, *, min_rate: float | None = None) -> bool:
  threshold = settings.ml_min_positive_rate if min_rate is None else min_rate
  return positive_rate >= threshold


def _train_markets() -> set[str]:
  return {m.strip().upper() for m in settings.ml_train_markets.split(",") if m.strip()}


def _train_sources() -> set[str]:
  return {s.strip() for s in settings.ml_train_sources.split(",") if s.strip()}


def _load_meta() -> dict:
  if not META_PATH.exists():
    return {}
  try:
    return json.loads(META_PATH.read_text())
  except Exception:
    return {}


def _write_meta(meta: dict) -> dict:
  MODEL_DIR.mkdir(parents=True, exist_ok=True)
  META_PATH.write_text(json.dumps(meta, indent=2))
  return meta


def _load_training_rows() -> list[tuple[datetime, list[float], int]] | None:
  markets = _train_markets()
  sources = _train_sources()
  db = SessionLocal()
  rows: list[tuple[datetime, list[float], int]] = []
  try:
    signals = (
      db.query(Signal)
      .filter(Signal.market.in_(list(markets)), Signal.source.in_(list(sources)))
      .order_by(Signal.disclosed_at.asc())
      .all()
    )
    for signal in signals:
      fr = (
        db.query(ForwardReturn)
        .filter(ForwardReturn.signal_id == signal.id, ForwardReturn.window == settings.win_window)
        .first()
      )
      if fr is None or fr.return_pct is None:
        continue
      feats = build_features(db, signal)
      disclosed = signal.disclosed_at or datetime.now(timezone.utc)
      rows.append((
        disclosed,
        features_to_vector(feats),
        1 if fr.return_pct > settings.win_threshold_pct else 0,
      ))
  finally:
    db.close()

  if len(rows) < settings.ml_train_min_samples:
    return None
  return rows


def _date_split(rows: list[tuple[datetime, list[float], int]], test_ratio: float = 0.2):
  n_test = max(1, int(len(rows) * test_ratio))
  train_rows = rows[:-n_test]
  test_rows = rows[-n_test:]
  train_cutoff = train_rows[-1][0].isoformat() if train_rows else None
  X_train = np.array([r[1] for r in train_rows])
  y_train = np.array([r[2] for r in train_rows])
  X_test = np.array([r[1] for r in test_rows])
  y_test = np.array([r[2] for r in test_rows])
  return X_train, X_test, y_train, y_test, train_cutoff


def compute_hold_priors(db=None) -> dict[str, int]:
  """Median optimal hold days per tier from labeled forward returns (Phase 2.3)."""
  import statistics

  close_db = False
  if db is None:
    db = SessionLocal()
    close_db = True
  tier_days: dict[str, list[int]] = {k: [] for k in DEFAULT_HOLD_PRIORS if k != "default"}
  try:
    signals = db.query(Signal).filter(Signal.source.in_(["nse_bulk", "nse_block"])).all()
    for signal in signals:
      fr_win = (
        db.query(ForwardReturn)
        .filter(ForwardReturn.signal_id == signal.id, ForwardReturn.window == settings.win_window)
        .first()
      )
      if fr_win is None or fr_win.return_pct is None or fr_win.return_pct <= settings.win_threshold_pct:
        continue
      score = (
        db.query(SignalScore)
        .filter(SignalScore.signal_id == signal.id)
        .order_by(SignalScore.scored_at.desc())
        .first()
      )
      tier = (score.tier if score else None) or "MEDIUM"
      if tier not in tier_days:
        tier = "MEDIUM"
      for window in ("1w", "1mo", "3mo"):
        fr = (
          db.query(ForwardReturn)
          .filter(ForwardReturn.signal_id == signal.id, ForwardReturn.window == window)
          .first()
        )
        if fr and fr.return_pct is not None and fr.return_pct > settings.win_threshold_pct:
          tier_days[tier].append(WINDOW_DAYS[window])
          break
  finally:
    if close_db:
      db.close()

  priors: dict[str, int] = {}
  for tier, days_list in tier_days.items():
    priors[tier] = int(statistics.median(days_list)) if days_list else DEFAULT_HOLD_PRIORS[tier]
  priors["default"] = int(statistics.median([d for lst in tier_days.values() for d in lst])) if any(tier_days.values()) else DEFAULT_HOLD_PRIORS["default"]
  return priors


def load_hold_priors() -> dict[str, int]:
  meta = _load_meta()
  priors = meta.get("hold_priors")
  if isinstance(priors, dict) and priors:
    return {k: int(v) for k, v in priors.items()}
  return dict(DEFAULT_HOLD_PRIORS)


def model_is_trained() -> bool:
  meta = _load_meta()
  if meta.get("status") != "trained":
    return False
  if not MODEL_PATH.exists():
    return False
  pos = meta.get("positive_rate")
  if pos is None:
    return False
  return training_allowed(float(pos))


def train_model() -> dict:
  rows = _load_training_rows()
  MODEL_DIR.mkdir(parents=True, exist_ok=True)

  if rows is None:
    prev = _load_meta()
    meta = {
      "status": "skipped",
      "reason": "insufficient_labeled_data",
      "n_samples": 0,
      "train_markets": sorted(_train_markets()),
      "train_sources": sorted(_train_sources()),
    }
    if prev.get("status") == "trained" and MODEL_PATH.exists():
      meta["note"] = "kept_previous_model"
      meta["previous_trained_at"] = prev.get("trained_at")
    return _write_meta(meta)

  y_all = np.array([r[2] for r in rows])
  pos_rate = float(y_all.mean())
  n_pos = int(y_all.sum())
  n_neg = int(len(y_all) - n_pos)

  base_meta = {
    "n_samples": int(len(rows)),
    "n_positive": n_pos,
    "n_negative": n_neg,
    "positive_rate": pos_rate,
    "train_markets": sorted(_train_markets()),
    "train_sources": sorted(_train_sources()),
    "win_window": settings.win_window,
    "win_threshold_pct": settings.win_threshold_pct,
  }

  if not training_allowed(pos_rate):
    prev = _load_meta()
    meta = {
      **base_meta,
      "status": "skipped",
      "reason": "positive_rate_too_low",
      "min_positive_rate": settings.ml_min_positive_rate,
    }
    if prev.get("status") == "trained" and MODEL_PATH.exists():
      meta["note"] = "kept_previous_model"
      meta["previous_trained_at"] = prev.get("trained_at")
      return _write_meta(meta)
    return _write_meta(meta)

  try:
    import lightgbm as lgb
  except ImportError:
    meta = {**base_meta, "status": "skipped", "reason": "lightgbm_not_installed"}
    return _write_meta(meta)

  X_train, X_test, y_train, y_test, train_cutoff = _date_split(rows)
  base = lgb.LGBMClassifier(
    n_estimators=100,
    max_depth=5,
    learning_rate=0.05,
    random_state=42,
    verbose=-1,
  )
  model = CalibratedClassifierCV(base, method="sigmoid", cv=3)
  model.fit(X_train, y_train)
  acc = float(model.score(X_test, y_test)) if len(y_test) else None

  with open(MODEL_PATH, "wb") as f:
    pickle.dump(model, f)

  hold_priors = compute_hold_priors()
  meta = {
    **base_meta,
    "status": "trained",
    "scorer_version": "lgbm-platt-v1",
    "test_accuracy": acc,
    "train_cutoff_date": train_cutoff,
    "split_method": "date_holdout_80_20",
    "hold_priors": hold_priors,
    "trained_at": datetime.now(timezone.utc).isoformat(),
  }
  return _write_meta(meta)


def load_model():
  if not model_is_trained():
    return None
  try:
    with open(MODEL_PATH, "rb") as f:
      return pickle.load(f)
  except Exception:
    return None


def predict_signal(db, signal: Signal) -> dict | None:
  model = load_model()
  if model is None:
    return None
  feats = build_features(db, signal)
  vec = np.array([features_to_vector(feats)])
  prob = float(model.predict_proba(vec)[0][1])
  return {"calibrated_probability": prob, "features": feats}


def rescore_all() -> int:
  from processor.scoring import score_signal_ml

  db = SessionLocal()
  count = 0
  try:
    for signal in db.query(Signal).all():
      score_signal_ml(db, signal)
      count += 1
  finally:
    db.close()
  return count
