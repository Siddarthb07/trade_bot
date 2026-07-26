"""Live P&L calibration overlay (shift on top of LightGBM prob)."""

from __future__ import annotations

from core.config import get_settings
from core.db import SessionLocal
from core.models import PredictionEvent
from processor.train import _load_meta, _write_meta

settings = get_settings()


def _clip(v: float, lo: float, hi: float) -> float:
  return max(lo, min(hi, v))


def fit_live_calibration(db=None) -> dict:
  """Fit mean residual (actual_win - predicted_prob) on closed live_pnl rows."""
  own = db is None
  if own:
    db = SessionLocal()
  try:
    rows = (
      db.query(PredictionEvent)
      .filter(
        PredictionEvent.kind == "live_pnl",
        PredictionEvent.labeled.is_(True),
        PredictionEvent.actual_win.isnot(None),
        PredictionEvent.predicted_prob.isnot(None),
      )
      .all()
    )
    n = len(rows)
    meta = _load_meta()
    if n < settings.ml_live_cal_min_trades:
      cal = {
        "status": "inactive",
        "n_closed": n,
        "min_trades": settings.ml_live_cal_min_trades,
        "shift": 0.0,
      }
      meta["live_calibration"] = cal
      _write_meta(meta)
      return cal

    residuals = [(1.0 if r.actual_win else 0.0) - float(r.predicted_prob or 0.5) for r in rows]
    raw_shift = sum(residuals) / len(residuals)
    shift = _clip(raw_shift, -settings.ml_live_cal_max_shift, settings.ml_live_cal_max_shift)
    cal = {
      "status": "active",
      "n_closed": n,
      "shift": round(shift, 4),
      "raw_shift": round(raw_shift, 4),
      "max_shift": settings.ml_live_cal_max_shift,
    }
    meta["live_calibration"] = cal
    _write_meta(meta)
    return cal
  finally:
    if own:
      db.close()


def apply_live_calibration(prob: float | None) -> tuple[float | None, float]:
  """Return (calibrated_prob, shift_applied)."""
  if prob is None:
    return None, 0.0
  meta = _load_meta()
  cal = meta.get("live_calibration") or {}
  if cal.get("status") != "active":
    return float(prob), 0.0
  shift = float(cal.get("shift") or 0.0)
  return _clip(float(prob) + shift, 0.01, 0.99), shift
