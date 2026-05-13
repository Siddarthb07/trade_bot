"""Estimated hold period and expected return (rule-based, not guaranteed)."""

from __future__ import annotations

from core.models import Signal


def estimate_sell_horizon(features: dict, signal: Signal) -> dict:
  action = signal.action.upper()
  if action not in ("BUY", "P", "A"):
    return {
      "days": None,
      "label": "Not a BUY signal",
      "expected_return_pct": None,
      "sell_by_hint": None,
    }

  ret_1m = float(features.get("return_1m") or 0)
  ret_3m = float(features.get("return_3m") or 0)
  median = float(features.get("median_return") or 0.06)
  prob = float(features.get("win_rate") or 0.5)
  cluster = int(features.get("cluster_count") or 0)

  if ret_1m > 0.12 and cluster >= 2:
    days = 5
    label = "~1 week (hot momentum + cluster)"
  elif ret_1m > 0.05:
    days = 14
    label = "~2 weeks"
  elif ret_3m > 0.12:
    days = 21
    label = "~3 weeks (trend)"
  elif median > 0.08:
    days = 30
    label = "~1 month"
  else:
    days = 45
    label = "~6 weeks (slow build)"

  momentum_boost = max(0, ret_1m) * 0.25
  cluster_boost = 0.02 if cluster >= 2 else 0
  expected = min(0.30, max(0.04, median + momentum_boost + cluster_boost))
  if prob < 0.5:
    expected *= 0.85

  return {
    "days": days,
    "label": label,
    "expected_return_pct": round(expected, 4),
    "sell_by_hint": f"Review exit around {days} days",
  }
