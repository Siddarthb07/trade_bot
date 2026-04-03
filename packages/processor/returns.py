"""Forward return computation via yfinance."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import yfinance as yf

WINDOW_DAYS = {"1w": 7, "1mo": 30, "3mo": 90, "6mo": 180}


def compute_forward_returns(ticker_normalized: str, disclosed_at: datetime) -> dict[str, tuple[float | None, str]]:
  results: dict[str, tuple[float | None, str]] = {}
  try:
    ticker = yf.Ticker(ticker_normalized)
    start = disclosed_at.date() - timedelta(days=5)
    end = disclosed_at.date() + timedelta(days=200)
    hist = ticker.history(start=start, end=end, auto_adjust=True)
    if hist.empty:
      for window in WINDOW_DAYS:
        results[window] = (None, "missing")
      return results
    hist = hist.sort_index()
    if hist.index.tz is not None:
      disclosed_cmp = disclosed_at.astimezone(hist.index.tz)
    else:
      disclosed_cmp = disclosed_at.replace(tzinfo=None)
    base_idx = int(hist.index.searchsorted(disclosed_cmp))
    if base_idx >= len(hist):
      base_idx = len(hist) - 1
    base_price = float(hist.iloc[base_idx]["Close"])
    for window, days in WINDOW_DAYS.items():
      target_idx = min(base_idx + days, len(hist) - 1)
      future_price = float(hist.iloc[target_idx]["Close"])
      return_pct = (future_price - base_price) / base_price if base_price else None
      results[window] = (return_pct, "yfinance")
  except Exception:
    for window in WINDOW_DAYS:
      results[window] = (None, "missing")
  return results
