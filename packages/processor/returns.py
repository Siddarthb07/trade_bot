"""Forward return computation (EOD cache first, yfinance fallback)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pandas as pd
import yfinance as yf
from sqlalchemy.orm import Session

WINDOW_DAYS = {"1w": 7, "1mo": 30, "3mo": 90, "6mo": 180}
# Require at least this many trading bars after entry before labeling a window.
MIN_BARS = {"1w": 4, "1mo": 15, "3mo": 45, "6mo": 90}

_HIST_CACHE: dict[str, pd.DataFrame] = {}


def clear_hist_cache() -> None:
  _HIST_CACHE.clear()


def _empty_results(source: str = "missing") -> dict[str, tuple[float | None, str]]:
  return {window: (None, source) for window in WINDOW_DAYS}


def _hist_from_eod(db: Session, ticker_normalized: str) -> pd.DataFrame | None:
  try:
    from processor.eod_cache import fetch_eod_history, infer_market

    market = infer_market(ticker_normalized)
    rows = fetch_eod_history(db, ticker_normalized, market, days=400)
    if len(rows) < 30:
      return None
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.set_index("date").sort_index()
    frame = frame.rename(columns={"close": "Close"})
    return frame[["Close"]]
  except Exception:
    return None


def _hist_from_yfinance(ticker_normalized: str, disclosed_at: datetime) -> pd.DataFrame:
  ticker = yf.Ticker(ticker_normalized)
  start = disclosed_at.date() - timedelta(days=10)
  end = datetime.now(timezone.utc).date() + timedelta(days=2)
  hist = ticker.history(start=start, end=end, auto_adjust=True)
  if hist.empty:
    return hist
  return hist.sort_index()


def load_price_history(
  ticker_normalized: str,
  disclosed_at: datetime,
  *,
  db: Session | None = None,
) -> tuple[pd.DataFrame, str]:
  """Load OHLC history once per ticker (process-local cache)."""
  cached = _HIST_CACHE.get(ticker_normalized)
  if cached is not None:
    source = "eod" if cached.attrs.get("source") == "eod" else "yfinance"
    return cached, source

  hist = None
  source = "missing"
  if db is not None:
    hist = _hist_from_eod(db, ticker_normalized)
    if hist is not None and not hist.empty:
      source = "eod"
  if hist is None or hist.empty:
    hist = _hist_from_yfinance(ticker_normalized, disclosed_at)
    source = "yfinance" if not hist.empty else "missing"

  if not hist.empty:
    hist.attrs["source"] = source
    _HIST_CACHE[ticker_normalized] = hist
  return hist, source


def compute_forward_returns_from_hist(
  hist: pd.DataFrame,
  disclosed_at: datetime,
  *,
  price_source: str = "yfinance",
) -> dict[str, tuple[float | None, str]]:
  if hist is None or hist.empty:
    return _empty_results("missing")

  hist = hist.sort_index()
  if hist.index.tz is not None:
    disclosed_cmp = disclosed_at.astimezone(hist.index.tz)
  else:
    disclosed_cmp = disclosed_at.replace(tzinfo=None) if disclosed_at.tzinfo else disclosed_at

  base_idx = int(hist.index.searchsorted(disclosed_cmp))
  if base_idx >= len(hist):
    return _empty_results("immature")
  base_price = float(hist.iloc[base_idx]["Close"])
  if not base_price:
    return _empty_results("missing")

  now = datetime.now(timezone.utc)
  age_days = (now - disclosed_at.astimezone(timezone.utc)).days
  results: dict[str, tuple[float | None, str]] = {}

  for window, days in WINDOW_DAYS.items():
    if age_days < days:
      results[window] = (None, "immature")
      continue
    target = disclosed_cmp + timedelta(days=days)
    target_idx = int(hist.index.searchsorted(target))
    if target_idx >= len(hist):
      results[window] = (None, "immature")
      continue
    bars_ahead = target_idx - base_idx
    if bars_ahead < MIN_BARS[window]:
      results[window] = (None, "immature")
      continue
    future_price = float(hist.iloc[target_idx]["Close"])
    return_pct = (future_price - base_price) / base_price
    results[window] = (return_pct, price_source)
  return results


def compute_forward_returns(
  ticker_normalized: str,
  disclosed_at: datetime,
  *,
  db: Session | None = None,
) -> dict[str, tuple[float | None, str]]:
  try:
    hist, source = load_price_history(ticker_normalized, disclosed_at, db=db)
    if hist.empty:
      return _empty_results(source)
    return compute_forward_returns_from_hist(hist, disclosed_at, price_source=source)
  except Exception:
    return _empty_results("missing")
