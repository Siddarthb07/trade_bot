"""LightGBM training with Platt calibration."""

from __future__ import annotations

import json
import os
import pickle
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import train_test_split

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


def _load_training_data() -> tuple[np.ndarray, np.ndarray] | None:
  db = SessionLocal()
  X, y = [], []
  try:
    signals = db.query(Signal).all()
    for signal in signals:
      fr = (
        db.query(ForwardReturn)
        .filter(ForwardReturn.signal_id == signal.id, ForwardReturn.window == settings.win_window)
        .first()
      )
      if fr is None or fr.return_pct is None:
        continue
      feats = build_features(db, signal)
      X.append(features_to_vector(feats))
      y.append(1 if fr.return_pct > settings.win_threshold_pct else 0)
  finally:
    db.close()
  if len(X) < settings.ml_train_min_samples:
    return None
  return np.array(X), np.array(y)


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
  if META_PATH.exists():
    try:
      meta = json.loads(META_PATH.read_text())
      priors = meta.get("hold_priors")
      if isinstance(priors, dict) and priors:
        return {k: int(v) for k, v in priors.items()}
    except Exception:
      pass
  return dict(DEFAULT_HOLD_PRIORS)


def train_model() -> dict:
  data = _load_training_data()
  MODEL_DIR.mkdir(parents=True, exist_ok=True)
  if data is None:
    meta = {"status": "skipped", "reason": "insufficient_labeled_data", "n_samples": 0}
    META_PATH.write_text(json.dumps(meta))
    return meta

  X, y = data
  try:
    import lightgbm as lgb
  except ImportError:
    meta = {"status": "skipped", "reason": "lightgbm_not_installed", "n_samples": len(y)}
    META_PATH.write_text(json.dumps(meta))
    return meta

  X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
  base = lgb.LGBMClassifier(
    n_estimators=100,
    max_depth=5,
    learning_rate=0.05,
    random_state=42,
    verbose=-1,
  )
  model = CalibratedClassifierCV(base, method="sigmoid", cv=3)
  model.fit(X_train, y_train)
  acc = float(model.score(X_test, y_test)) if len(X_test) else None

  with open(MODEL_PATH, "wb") as f:
    pickle.dump(model, f)

  hold_priors = compute_hold_priors()
  meta = {
    "status": "trained",
    "scorer_version": "lgbm-platt-v1",
    "n_samples": int(len(y)),
    "test_accuracy": acc,
    "positive_rate": float(y.mean()),
    "hold_priors": hold_priors,
    "trained_at": datetime.now(timezone.utc).isoformat(),
  }
  META_PATH.write_text(json.dumps(meta, indent=2))
  return meta


def load_model():
  if not MODEL_PATH.exists():
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
