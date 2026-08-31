"""GHLZ clock helpers — NSE session map 09:15–15:30."""

from __future__ import annotations

from typing import Any, Sequence


def early_session_return(bars: Sequence[dict[str, Any]], *, n: int = 6) -> float | None:
  if len(bars) < 2:
    return None
  c0 = float(bars[0].get("close") or 0)
  idx = min(n, len(bars)) - 1
  c1 = float(bars[idx].get("close") or 0)
  if c0 <= 0:
    return None
  return float(c1 / c0 - 1.0)
