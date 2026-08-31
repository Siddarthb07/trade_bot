"""Jump vs diffusion flag via bipower-variation style ratio (Barndorff-Nielsen & Shephard light)."""

from __future__ import annotations

import numpy as np


def jump_day_flag(closes: list[float] | np.ndarray, *, z_thresh: float = 3.5) -> bool:
  arr = np.asarray(closes, dtype=float)
  if len(arr) < 8:
    return False
  r = np.diff(np.log(np.maximum(arr, 1e-12)))
  rv = float(np.sum(r**2))
  # bipower variation
  bv = float(np.sum(np.abs(r[1:]) * np.abs(r[:-1])) * (np.pi / 2.0))
  if bv <= 1e-12:
    return abs(r).max() > 0.02
  jump_comp = max(0.0, rv - bv)
  # crude z: jump share
  return (jump_comp / rv) > 0.35 or float(np.max(np.abs(r))) > z_thresh * float(np.std(r) or 1e-9)
