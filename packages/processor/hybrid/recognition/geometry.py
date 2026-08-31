"""L0 session geometry — features only, not signals."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from processor.hybrid.recognition.types import SessionGeometry


def _closes(bars: Sequence[dict[str, Any]]) -> np.ndarray:
  return np.array([float(b.get("close") or 0) for b in bars], dtype=float)


def overnight_gap_pct(prev_close: float | None, open_px: float | None) -> float | None:
  if prev_close is None or open_px is None or prev_close <= 0:
    return None
  return float((open_px / prev_close) - 1.0)


def or_width_from_bars(bars: Sequence[dict[str, Any]], *, or_bars: int = 5) -> float | None:
  if len(bars) < or_bars:
    return None
  hi = max(float(b.get("high") or b.get("close") or 0) for b in bars[:or_bars])
  lo = min(float(b.get("low") or b.get("close") or 0) for b in bars[:or_bars])
  mid = (hi + lo) / 2.0
  if mid <= 0:
    return None
  return float((hi - lo) / mid)


def realized_vol(closes: np.ndarray) -> float | None:
  if len(closes) < 3:
    return None
  rets = np.diff(closes) / np.maximum(closes[:-1], 1e-12)
  return float(np.std(rets))


def ghlz_r1(prev_close: float | None, first_half_close: float | None) -> float | None:
  """Gao-Han-Li-Zhou first half-hour return proxy (close→early session)."""
  if prev_close is None or first_half_close is None or prev_close <= 0:
    return None
  return float((first_half_close / prev_close) - 1.0)


def build_geometry(
  bars: Sequence[dict[str, Any]],
  *,
  prev_close: float | None = None,
  universe_ret: float | None = None,
  btc_overnight_pct: float | None = None,
  or_bars: int = 5,
) -> SessionGeometry:
  notes: list[str] = []
  if not bars:
    return SessionGeometry(status="missing", notes=("no_bars",))

  opens = float(bars[0].get("open") or bars[0].get("close") or 0)
  gap = overnight_gap_pct(prev_close, opens if opens > 0 else None)
  orw = or_width_from_bars(bars, or_bars=or_bars)
  closes = _closes(bars)
  rv = realized_vol(closes)
  half = min(len(bars), max(or_bars, 6))
  r1 = ghlz_r1(prev_close, float(closes[half - 1]) if half else None)

  residual = None
  if universe_ret is not None and len(closes) >= 2 and closes[0] > 0:
    session_ret = float(closes[-1] / closes[0] - 1.0)
    residual = session_ret - float(universe_ret)

  if btc_overnight_pct is None:
    notes.append("btc_overnight_missing")

  status = "ok" if orw is not None else "cold_start"
  return SessionGeometry(
    overnight_gap_pct=None if gap is None else round(gap, 6),
    or_width_pct=None if orw is None else round(orw, 6),
    ghlz_r1=None if r1 is None else round(r1, 6),
    rv_1d=None if rv is None else round(rv, 6),
    rv_5d=None,
    cross_section_residual=None if residual is None else round(residual, 6),
    btc_overnight_pct=btc_overnight_pct,
    status=status,
    notes=tuple(notes),
  )
