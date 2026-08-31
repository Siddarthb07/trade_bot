"""Market-regime close series for Pattern Forge hybrid chooser.

Uses a liquid IN proxy (RELIANCE.NS). Prefer disk cache; optionally refresh via yfinance.
Always truncates to asof (PIT-safe).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
CACHE_PATH = ROOT / "models" / "pattern_forge" / "market_closes_RELIANCE.json"
PROXY = "RELIANCE.NS"


def _load_disk() -> list[tuple[str, float]]:
  if not CACHE_PATH.exists():
    return []
  try:
    raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    rows = raw.get("closes") or []
    out: list[tuple[str, float]] = []
    for r in rows:
      if isinstance(r, (list, tuple)) and len(r) >= 2:
        out.append((str(r[0])[:10], float(r[1])))
      elif isinstance(r, dict) and r.get("d") is not None:
        out.append((str(r["d"])[:10], float(r["c"])))
    return out
  except Exception:
    return []


def _save_disk(closes: list[tuple[str, float]]) -> None:
  CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
  payload: dict[str, Any] = {
    "ticker": PROXY,
    "closes": [[d, c] for d, c in closes],
    "n": len(closes),
  }
  CACHE_PATH.write_text(json.dumps(payload), encoding="utf-8")


def refresh_market_closes(*, lookback_days: int = 500) -> list[tuple[str, float]]:
  from processor.day_sim import _fetch_history

  end = datetime.now(timezone.utc)
  hist = _fetch_history(PROXY, end, lookback_days=lookback_days)
  if hist:
    _save_disk(hist)
  return hist


def market_closes_asof(asof: str, *, allow_network: bool = True) -> list[float]:
  """Return proxy closes with date <= asof (oldest→newest)."""
  rows = _load_disk()
  need = not rows or rows[-1][0] < asof
  if need and allow_network:
    rows = refresh_market_closes() or rows
  if not rows and allow_network:
    rows = refresh_market_closes()
  closes = [c for d, c in rows if d <= asof]
  return closes


def soft_regime(closes: list[float]) -> str:
  """Regime label that works with shorter series (20+) when full 50 unavailable."""
  from processor.strategies import market_regime

  if len(closes) >= 50:
    return market_regime(closes)
  if len(closes) < 20:
    return "unknown"
  arr = closes
  ret10 = arr[-1] / arr[-11] - 1.0 if len(arr) >= 11 else 0.0
  import numpy as np

  vol = float(np.std(np.diff(arr[-15:]) / np.maximum(arr[-15:-1], 1e-9))) if len(arr) >= 16 else 0.0
  if ret10 < -0.05 or vol > 0.035:
    return "risk_off"
  if ret10 > 0.015:
    return "trend"
  return "chop"
