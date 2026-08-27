"""Confidence-scaled notional under per-market caps."""

from __future__ import annotations

import math

from core.config import get_settings

settings = get_settings()


def size_notional(
  *,
  prob: float,
  max_notional: float,
  min_prob: float,
  min_size_frac: float | None = None,
) -> tuple[float | None, str | None]:
  """Return (notional, reject_reason). None notional means skip."""
  if prob < min_prob:
    return None, f"prob_below_min:{prob:.3f}<{min_prob:.3f}"
  denom = max(1e-6, 1.0 - min_prob)
  frac = (prob - min_prob) / denom
  frac = max(0.0, min(1.0, frac))
  floor = settings.exec_min_size_frac if min_size_frac is None else min_size_frac
  frac = max(frac, floor)
  return round(frac * max_notional, 4), None


def confidence_leverage(
  conf: float,
  *,
  max_leverage: float = 10.0,
  min_leverage: float = 1.0,
  conf_floor: float = 0.58,
  conf_full: float = 0.82,
  curve: float = 1.8,
) -> float:
  """Map confidence to leverage multiplier (sim-only; not live caps).

  Below conf_floor -> min_leverage. At/above conf_full -> max_leverage.
  curve > 1 keeps leverage low until confidence is genuinely high.
  """
  if max_leverage <= min_leverage:
    return min_leverage
  if conf < conf_floor:
    return min_leverage
  span = max(1e-6, conf_full - conf_floor)
  t = max(0.0, min(1.0, (conf - conf_floor) / span))
  t = t**curve
  return round(min_leverage + t * (max_leverage - min_leverage), 3)


def leverage_for_target(
  target_return_frac: float,
  tp_frac: float,
  *,
  max_leverage: float = 50.0,
  min_leverage: float = 1.0,
) -> float:
  """Leverage needed so a TP hit at tp_frac ~= target_return on equity (sim-only)."""
  if tp_frac <= 0 or target_return_frac <= 0:
    return min_leverage
  lev = target_return_frac / tp_frac
  return round(max(min_leverage, min(max_leverage, lev)), 3)


def qty_from_notional(notional: float, last_price: float, *, allow_fractional: bool) -> tuple[float | None, str | None]:
  if last_price <= 0:
    return None, "invalid_price"
  if allow_fractional:
    qty = round(notional / last_price, 4)
    if qty <= 0:
      return None, "qty_too_small"
    return qty, None
  qty = math.floor(notional / last_price)
  if qty < 1:
    return None, "share_above_sized_notional"
  return float(qty), None
