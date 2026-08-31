"""CUSUM change-point on log-vol — Adams/MacKay-style online break hint (simplified)."""

from __future__ import annotations

import numpy as np


def cusum_break_prob(closes: list[float] | np.ndarray, *, threshold: float = 3.0) -> tuple[float, int]:
  """Return (break_prob in [0,1], regime_age bars since last trip)."""
  arr = np.asarray(closes, dtype=float)
  if len(arr) < 10:
    return 0.0, 0
  rets = np.diff(arr) / np.maximum(arr[:-1], 1e-12)
  vol = np.abs(rets)
  mu = float(vol.mean())
  s = float(vol.std()) or 1e-9
  z = (vol - mu) / s
  g_plus = 0.0
  last_trip = 0
  for i, zi in enumerate(z):
    g_plus = max(0.0, g_plus + float(zi))
    if g_plus > threshold:
      last_trip = i
      g_plus = 0.0
  age = len(z) - last_trip
  # map current g to soft break prob
  prob = float(min(1.0, g_plus / threshold))
  return round(prob, 4), int(age)
