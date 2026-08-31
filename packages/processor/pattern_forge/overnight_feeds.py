"""PIT overnight / Asia / US proxies for daily_swing CrossMarket agent.

At Indian decision asof T (cash close), use foreign sessions with date < asof
(already finished before NSE close that calendar day in most cases; we still
require strict date < asof for safety).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = ROOT / "models" / "pattern_forge" / "overnight_cache"

# Yahoo symbols — liquid ETFs / indices
PROXIES = {
  "us": "SPY",
  "asia": "EWJ",  # Japan ETF as Asia overnight proxy
  "in_gap": "^NSEI",  # Nifty for local gap context when available
}


def _cache_path(key: str) -> Path:
  return CACHE_DIR / f"{key}.json"


def _load_rows(key: str) -> list[tuple[str, float]]:
  path = _cache_path(key)
  if not path.exists():
    return []
  try:
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw.get("closes") or []
    out: list[tuple[str, float]] = []
    for r in rows:
      if isinstance(r, (list, tuple)) and len(r) >= 2:
        out.append((str(r[0])[:10], float(r[1])))
    return out
  except Exception:
    return []


def _save_rows(key: str, ticker: str, closes: list[tuple[str, float]]) -> None:
  CACHE_DIR.mkdir(parents=True, exist_ok=True)
  _cache_path(key).write_text(
    json.dumps({"ticker": ticker, "closes": [[d, c] for d, c in closes], "n": len(closes)}),
    encoding="utf-8",
  )


def refresh_proxy(key: str, *, lookback_days: int = 520) -> list[tuple[str, float]]:
  from processor.day_sim import _fetch_history

  ticker = PROXIES[key]
  end = datetime.now(timezone.utc)
  hist = _fetch_history(ticker, end, lookback_days=lookback_days)
  if hist:
    _save_rows(key, ticker, hist)
  return hist


def _ret_before(asof: str, rows: list[tuple[str, float]]) -> float | None:
  """Last 1-day return with both bars dated strictly before asof."""
  prior = [(d, c) for d, c in rows if d < asof and c > 0]
  if len(prior) < 2:
    return None
  a, b = prior[-2][1], prior[-1][1]
  if a <= 0:
    return None
  return float(b / a - 1.0)


def overnight_cues_asof(
  asof: str,
  *,
  allow_network: bool = False,
  local_closes: list[float] | None = None,
) -> dict[str, Any]:
  """Return overnight cue fractions + feed_status for swarm tape."""
  status: dict[str, str] = {}
  us = asia = in_gap = None

  for key in ("us", "asia", "in_gap"):
    rows = _load_rows(key)
    if (not rows or rows[-1][0] < asof) and allow_network:
      try:
        rows = refresh_proxy(key) or rows
      except Exception:
        status[key] = "fetch_failed"
        continue
    if not rows:
      status[key] = "missing"
      continue
    ret = _ret_before(asof, rows)
    if ret is None:
      status[key] = "short_history"
    else:
      status[key] = "ok"
      if key == "us":
        us = ret
      elif key == "asia":
        asia = ret
      else:
        in_gap = ret

  # Fallback local gap from market proxy closes already in-hand (PIT ≤ asof)
  if in_gap is None and local_closes and len(local_closes) >= 2 and local_closes[-2] > 0:
    in_gap = float(local_closes[-1] / local_closes[-2] - 1.0)
    status["in_gap"] = status.get("in_gap") or "local_proxy"

  overnight = in_gap if in_gap is not None else us
  return {
    "overnight_gap_pct": overnight,
    "us_ret_pct": us,
    "asia_ret_pct": asia,
    "feed_status": status,
  }
