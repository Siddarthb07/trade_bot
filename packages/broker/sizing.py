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
