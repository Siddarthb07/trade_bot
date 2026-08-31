"""Triple-barrier labeling (López de Prado AFML Ch. 3) — first touch wins."""

from __future__ import annotations

from typing import Literal

BarrierHit = Literal["tp", "sl", "time", "none"]


def first_barrier_touch(
  path: list[float],
  *,
  entry: float,
  side: str,
  tp_pct: float,
  sl_pct: float,
  max_bars: int,
) -> tuple[BarrierHit, int]:
  if entry <= 0 or not path:
    return "none", -1
  direction = 1.0 if side == "buy" else -1.0
  tp = entry * (1.0 + direction * tp_pct)
  sl = entry * (1.0 - direction * sl_pct)
  n = min(len(path), max_bars)
  for i in range(n):
    px = path[i]
    if side == "buy":
      if px >= tp:
        return "tp", i
      if px <= sl:
        return "sl", i
    else:
      if px <= tp:
        return "tp", i
      if px >= sl:
        return "sl", i
  return "time", n - 1 if n else -1


def meta_label_from_barrier(hit: BarrierHit) -> int:
  return 1 if hit == "tp" else 0
