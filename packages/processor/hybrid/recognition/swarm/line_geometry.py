"""Line geometry agent — OR / VWAP / pivots / trendline break-retest (not a TA strategy)."""

from __future__ import annotations

from typing import Any, Sequence

from processor.hybrid.recognition.types import AgentMessage


def _vwap(bars: Sequence[dict[str, Any]]) -> float | None:
  num = 0.0
  den = 0.0
  for b in bars:
    typ = (float(b.get("high") or 0) + float(b.get("low") or 0) + float(b.get("close") or 0)) / 3.0
    vol = float(b.get("volume") or 1.0)
    num += typ * vol
    den += vol
  if den <= 0:
    return None
  return num / den


def line_geometry_message(bars: Sequence[dict[str, Any]], *, or_bars: int = 5) -> AgentMessage:
  if len(bars) < or_bars + 2:
    return AgentMessage(agent="LineGeometry", vote="annotate", status="insufficient_data", reason="short_path")

  or_hi = max(float(b.get("high") or b.get("close") or 0) for b in bars[:or_bars])
  or_lo = min(float(b.get("low") or b.get("close") or 0) for b in bars[:or_bars])
  last = float(bars[-1].get("close") or 0)
  vwap = _vwap(bars)

  # simple slope of closes in OR window
  closes_or = [float(b.get("close") or 0) for b in bars[:or_bars]]
  slope = (closes_or[-1] - closes_or[0]) / max(or_bars - 1, 1)

  above_or = last > or_hi
  below_or = last < or_lo
  above_vwap = vwap is not None and last > vwap

  payload = {
    "or_hi": or_hi,
    "or_lo": or_lo,
    "vwap": vwap,
    "slope": slope,
    "above_or": above_or,
    "below_or": below_or,
    "above_vwap": above_vwap,
  }

  # Structured continuation: break above OR with rising slope and above VWAP
  if above_or and slope > 0 and above_vwap:
    return AgentMessage(agent="LineGeometry", vote="take", reason="break_above_rising_line", payload=payload)
  if below_or or (vwap is not None and last < vwap and slope < 0):
    return AgentMessage(agent="LineGeometry", vote="skip", reason="into_ceiling_or_weak", payload=payload)
  return AgentMessage(agent="LineGeometry", vote="annotate", reason="neutral_geometry", payload=payload)
