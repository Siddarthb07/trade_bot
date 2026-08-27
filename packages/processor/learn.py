"""Gated online retrain on frozen prediction_events (champion / challenger)."""

from __future__ import annotations

import logging
import os
import pickle
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from core.config import get_settings
from core.db import SessionLocal
from core.models import PredictionEvent
from processor.train import (
  MODEL_DIR,
  MODEL_PATH,
  META_PATH,
  _date_split,
  _load_meta,
  _load_training_rows,
  _write_meta,
  compute_hold_priors,
  training_allowed,
)

logger = logging.getLogger(__name__)
settings = get_settings()

PREV_MODEL_PATH = MODEL_DIR / "lgbm_calibrated.prev.pkl"
LOCK_KEY = "ml_learn"


def _redis_lock(ttl_sec: int = 600):
  try:
    import redis

    r = redis.from_url(settings.redis_url)
    ok = r.set(LOCK_KEY, "1", nx=True, ex=ttl_sec)
    return r if ok else None
  except Exception:
    return object()  # no redis → proceed without lock


def _redis_unlock(client) -> None:
  if client is None or type(client) is object:
    return
  try:
    client.delete(LOCK_KEY)
  except Exception:
    pass


def _frozen_rows() -> list[tuple[datetime, list[float], int]] | None:
  db = SessionLocal()
  try:
    events = (
      db.query(PredictionEvent)
      .filter(
        PredictionEvent.kind == "bulk_ml",
        PredictionEvent.labeled.is_(True),
        PredictionEvent.actual_win.isnot(None),
        PredictionEvent.feature_vector.isnot(None),
      )
      .order_by(PredictionEvent.created_at.asc())
      .all()
    )
    rows: list[tuple[datetime, list[float], int]] = []
    for ev in events:
      vec = ev.feature_vector
      if not isinstance(vec, list) or len(vec) < 5:
        continue
      ts = ev.created_at or datetime.now(timezone.utc)
      rows.append((ts, [float(x) for x in vec], 1 if ev.actual_win else 0))
    if len(rows) < settings.ml_train_min_samples:
      return None
    return rows
  finally:
    db.close()


def _update_adaptive_from_events() -> dict:
  """Feed labeled adaptive / live_pnl outcomes into expanding-window bins.

  Stage B hard rule: online learn may update peers / effective_target / min_peers only.
  Never retune TP/SL/horizon from live labels — those come from offline
  scripts/run_adaptive_edge_search.py on expanding validation windows only.
  """
  try:
    from processor.adaptive_edge import record_outcome
  except Exception as e:
    return {"status": "skipped", "reason": str(e)}

  db = SessionLocal()
  updated = 0
  try:
    events = (
      db.query(PredictionEvent)
      .filter(
        PredictionEvent.labeled.is_(True),
        PredictionEvent.actual_win.isnot(None),
        PredictionEvent.kind.in_(("live_pnl", "adaptive_edge", "bulk_ml")),
      )
      .order_by(PredictionEvent.created_at.asc())
      .all()
    )
    for ev in events:
      bin_key = None
      side = "buy"
      feats = ev.features if isinstance(ev.features, dict) else {}
      bin_key = feats.get("adaptive_bin") or feats.get("bin")
      side = feats.get("adaptive_side") or feats.get("side") or "buy"
      if not bin_key:
        continue
      record_outcome(str(bin_key), str(side), bool(ev.actual_win))
      updated += 1
    return {"status": "ok", "updated": updated}
  except Exception as e:
    logger.exception("adaptive_edge update failed")
    return {"status": "error", "reason": str(e)}
  finally:
    db.close()


def learn_from_outcomes(*, force: bool = False) -> dict:
  """Full retrain on frozen labels; swap only if gates pass. Also updates adaptive_edge bins."""
  adaptive_meta = _update_adaptive_from_events()

  if not settings.ml_online_learn_enabled and not force:
    return {"status": "skipped", "reason": "disabled", "adaptive_edge": adaptive_meta}

  lock = _redis_lock()
  if lock is None:
    return {"status": "skipped", "reason": "lock_held"}

  try:
    rows = _frozen_rows()
    source = "frozen"
    if rows is None:
      rows = _load_training_rows()
      source = "live_rebuild"
    if rows is None:
      meta = {
        "status": "skipped",
        "reason": "insufficient_labeled_data",
        "learn_source": source,
        "last_learn_at": datetime.now(timezone.utc).isoformat(),
      }
      prev = _load_meta()
      if prev.get("status") == "trained":
        meta["note"] = "kept_previous_model"
      _write_meta({**prev, **{k: v for k, v in meta.items() if k != "status"}, "learn_status": meta["status"], "learn_reason": meta["reason"], "last_learn_at": meta["last_learn_at"]})
      return meta

    y_all = np.array([r[2] for r in rows])
    pos_rate = float(y_all.mean())
    base = {
      "n_samples": int(len(rows)),
      "n_positive": int(y_all.sum()),
      "n_negative": int(len(y_all) - y_all.sum()),
      "positive_rate": pos_rate,
      "learn_source": source,
      "win_window": settings.win_window,
      "win_threshold_pct": settings.win_threshold_pct,
    }
    if not training_allowed(pos_rate):
      out = {**base, "status": "skipped", "reason": "positive_rate_too_low", "learn_status": "skipped"}
      prev = _load_meta()
      _write_meta({**prev, **out, "last_learn_at": datetime.now(timezone.utc).isoformat()})
      return out

    try:
      import lightgbm as lgb
      from sklearn.calibration import CalibratedClassifierCV
    except ImportError:
      return {**base, "status": "skipped", "reason": "lightgbm_not_installed"}

    X_train, X_test, y_train, y_test, train_cutoff = _date_split(rows)
    clf = CalibratedClassifierCV(
      lgb.LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.05, random_state=42, verbose=-1),
      method="sigmoid",
      cv=3,
    )
    clf.fit(X_train, y_train)
    acc = float(clf.score(X_test, y_test)) if len(y_test) else None

    prev = _load_meta()
    prev_acc = prev.get("test_accuracy")
    if (
      prev.get("status") == "trained"
      and prev_acc is not None
      and acc is not None
      and float(acc) < float(prev_acc) - settings.ml_max_accuracy_drop
      and MODEL_PATH.exists()
    ):
      out = {
        **base,
        "status": "kept_previous",
        "learn_status": "kept_previous",
        "reason": "accuracy_drop",
        "challenger_accuracy": acc,
        "champion_accuracy": prev_acc,
        "max_accuracy_drop": settings.ml_max_accuracy_drop,
        "last_learn_at": datetime.now(timezone.utc).isoformat(),
      }
      _write_meta({**prev, **out})
      logger.info("Learn kept previous model: %s", out)
      return out

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    tmp = MODEL_DIR / "lgbm_calibrated.pkl.tmp"
    with open(tmp, "wb") as f:
      pickle.dump(clf, f)
    if MODEL_PATH.exists():
      shutil.copy2(MODEL_PATH, PREV_MODEL_PATH)
    os.replace(tmp, MODEL_PATH)

    hold_priors = compute_hold_priors()
    meta = {
      **base,
      "status": "trained",
      "learn_status": "trained",
      "scorer_version": "lgbm-platt-v1",
      "test_accuracy": acc,
      "train_cutoff_date": train_cutoff,
      "split_method": "date_holdout_80_20",
      "hold_priors": hold_priors,
      "trained_at": datetime.now(timezone.utc).isoformat(),
      "last_learn_at": datetime.now(timezone.utc).isoformat(),
    }
    # preserve live_calibration if present
    if prev.get("live_calibration"):
      meta["live_calibration"] = prev["live_calibration"]
    _write_meta(meta)
    logger.info("Learn swapped challenger model: %s", meta)
    meta["adaptive_edge"] = adaptive_meta
    return meta
  finally:
    _redis_unlock(lock)
