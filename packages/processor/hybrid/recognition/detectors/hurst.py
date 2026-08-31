"""Rolling Hurst exponent (R/S) — Peters FMH persistence hint."""

from __future__ import annotations

import numpy as np


def hurst_rs(closes: list[float] | np.ndarray, *, min_n: int = 32) -> float | None:
  arr = np.asarray(closes, dtype=float)
  if len(arr) < min_n:
    return None
  x = np.diff(np.log(np.maximum(arr, 1e-12)))
  n = len(x)
  if n < min_n - 1:
    return None
  mean = x.mean()
  y = np.cumsum(x - mean)
  r = float(y.max() - y.min())
  s = float(x.std(ddof=1))
  if s <= 1e-12 or r <= 0:
    return 0.5
  return float(np.log(r / s) / np.log(n))
