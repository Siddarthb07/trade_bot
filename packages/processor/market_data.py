"""Market price history and trend features."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

_CACHE_TTL_SEC = 900  # 15 minutes
_price_cache: dict[str, tuple[float, list[dict]]] = {}
_YF_TIMEOUT = 8


def _cache_get(key: str) -> list[dict] | None:
  hit = _price_cache.get(key)
  if not hit:
    return None
  ts, data = hit
  if time.monotonic() - ts > _CACHE_TTL_SEC:
    _price_cache.pop(key, None)
    return None
  return data


def _cache_set(key: str, data: list[dict]) -> None:
  _price_cache[key] = (time.monotonic(), data)


def fetch_price_history(
  ticker_normalized: str,
  days: int = 180,
  *,
  db=None,
  market: str | None = None,
) -> list[dict]:
  cache_key = f"{ticker_normalized}:{days}"
  cached = _cache_get(cache_key)
  if cached is not None:
    return cached

  if db is not None:
    try:
      from processor.eod_cache import fetch_eod_history, infer_market

      mkt = infer_market(ticker_normalized, market)
      eod = fetch_eod_history(db, ticker_normalized, mkt, days=days)
      if len(eod) >= 20:
        _cache_set(cache_key, eod)
        return eod
    except Exception as exc:
      logger.debug("EOD cache miss for %s: %s", ticker_normalized, exc)

  try:
    ticker = yf.Ticker(ticker_normalized)
    end = datetime.utcnow().date()
    start = end - timedelta(days=days)
    hist = ticker.history(start=start, end=end, auto_adjust=True, timeout=_YF_TIMEOUT)
    if hist.empty:
      _cache_set(cache_key, [])
      return []
    hist = hist.sort_index()
    out: list[dict] = []
    for idx, row in hist.iterrows():
      out.append({
        "date": idx.strftime("%Y-%m-%d"),
        "close": round(float(row["Close"]), 2),
        "volume": int(row["Volume"]) if pd.notna(row["Volume"]) else 0,
      })
    _cache_set(cache_key, out)
    return out
  except Exception as exc:
    logger.warning("price fetch failed for %s: %s", ticker_normalized, exc)
    return []


def _trend_from_closes(closes: list[float]) -> dict:
  if len(closes) < 20:
    return {
      "trend": "unknown", "return_1m": None, "return_3m": None, "above_ma50": None,
      "momentum": None, "volatility_20d": None,
    }
  current = closes[-1]
  ma50 = sum(closes[-50:]) / min(50, len(closes))
  ret_1m = (current - closes[-22]) / closes[-22] if len(closes) >= 22 else None
  ret_3m = (current - closes[-66]) / closes[-66] if len(closes) >= 66 else None
  momentum = "bullish" if ret_1m and ret_1m > 0.02 else "bearish" if ret_1m and ret_1m < -0.02 else "neutral"
  vol = _volatility_20d(closes)
  return {
    "trend": "uptrend" if current > ma50 else "downtrend",
    "return_1m": round(ret_1m, 4) if ret_1m is not None else None,
    "return_3m": round(ret_3m, 4) if ret_3m is not None else None,
    "above_ma50": current > ma50,
    "momentum": momentum,
    "current_price": current,
    "ma50": round(ma50, 2),
    "volatility_20d": vol,
  }


def trend_from_prices(prices: list[dict]) -> dict:
  """Trend features from an existing price series (avoids duplicate yfinance calls)."""
  if len(prices) < 20:
    return {
      "trend": "unknown", "return_1m": None, "return_3m": None, "above_ma50": None,
      "momentum": None, "volatility_20d": None,
    }
  window = prices[-120:] if len(prices) > 120 else prices
  closes = [p["close"] for p in window]
  return _trend_from_closes(closes)


def compute_trend_features(
  ticker_normalized: str,
  *,
  db=None,
  market: str | None = None,
) -> dict:
  prices = fetch_price_history(ticker_normalized, days=120, db=db, market=market)
  return trend_from_prices(prices)


def _volatility_20d(closes: list[float]) -> float | None:
  """Annualized 20-day volatility from daily closes."""
  if len(closes) < 21:
    return None
  import math

  rets = []
  window = closes[-21:]
  for i in range(1, len(window)):
    if window[i - 1] > 0:
      rets.append((window[i] - window[i - 1]) / window[i - 1])
  if len(rets) < 5:
    return None
  mean = sum(rets) / len(rets)
  var = sum((r - mean) ** 2 for r in rets) / len(rets)
  return round(math.sqrt(var) * (252 ** 0.5), 4)


def explain_trend_narrative(trend: dict, ticker: str) -> dict:
  """Plain-language chart/trend explanation for the dashboard."""
  if trend.get("trend") == "unknown":
    return {
      "headline": f"Not enough price data for {ticker}",
      "paragraphs": ["We could not load enough recent prices to explain the trend."],
      "signals": [],
    }

  current = trend.get("current_price")
  ma50 = trend.get("ma50")
  ret_1m = trend.get("return_1m")
  ret_3m = trend.get("return_3m")
  momentum = trend.get("momentum") or "neutral"
  above = trend.get("above_ma50")

  paragraphs: list[str] = []
  signals: list[str] = []

  if ret_1m is not None:
    direction = "risen" if ret_1m > 0 else "fallen"
    paragraphs.append(
      f"Over the last ~1 month, {ticker} has {direction} about {abs(ret_1m) * 100:.1f}%. "
      f"This short-term move is labelled '{momentum}' momentum."
    )
  if ret_3m is not None:
    paragraphs.append(
      f"Over ~3 months the stock is {'up' if ret_3m > 0 else 'down'} {abs(ret_3m) * 100:.1f}%, "
      f"which shows whether the broader trend supports or fights the bulk-deal signal."
    )
  if current is not None and ma50 is not None:
    if above:
      paragraphs.append(
        f"Price (₹{current}) is above the 50-day average (₹{ma50}) — buyers have been willing to pay "
        f"more than the recent norm, often seen in accumulation phases."
      )
      signals.append("Above 50-day MA — trend tailwind")
    else:
      paragraphs.append(
        f"Price (₹{current}) is below the 50-day average (₹{ma50}) — the stock is in a weaker phase; "
        f"any bounce would be a counter-trend recovery, not a confirmed uptrend."
      )
      signals.append("Below 50-day MA — trend headwind")

  if momentum == "bullish" and above:
    headline = "Uptrend with positive momentum"
    signals.append("Bullish momentum + price above MA50")
  elif momentum == "bearish":
    headline = "Weak or falling near-term trend"
    signals.append("Bearish short-term momentum")
  else:
    headline = "Mixed / neutral trend"

  return {"headline": headline, "paragraphs": paragraphs, "signals": signals}
