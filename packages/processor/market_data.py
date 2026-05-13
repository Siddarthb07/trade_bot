"""Market price history and trend features."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf


def fetch_price_history(ticker_normalized: str, days: int = 180) -> list[dict]:
  try:
    ticker = yf.Ticker(ticker_normalized)
    end = datetime.utcnow().date()
    start = end - timedelta(days=days)
    hist = ticker.history(start=start, end=end, auto_adjust=True)
    if hist.empty:
      return []
    hist = hist.sort_index()
    out = []
    for idx, row in hist.iterrows():
      out.append({
        "date": idx.strftime("%Y-%m-%d"),
        "close": round(float(row["Close"]), 2),
        "volume": int(row["Volume"]) if pd.notna(row["Volume"]) else 0,
      })
    return out
  except Exception:
    return []


def compute_trend_features(ticker_normalized: str) -> dict:
  prices = fetch_price_history(ticker_normalized, days=120)
  if len(prices) < 20:
    return {"trend": "unknown", "return_1m": None, "return_3m": None, "above_ma50": None, "momentum": None}
  closes = [p["close"] for p in prices]
  current = closes[-1]
  ma50 = sum(closes[-50:]) / min(50, len(closes))
  ret_1m = (current - closes[-22]) / closes[-22] if len(closes) >= 22 else None
  ret_3m = (current - closes[-66]) / closes[-66] if len(closes) >= 66 else None
  momentum = "bullish" if ret_1m and ret_1m > 0.02 else "bearish" if ret_1m and ret_1m < -0.02 else "neutral"
  return {
    "trend": "uptrend" if current > ma50 else "downtrend",
    "return_1m": round(ret_1m, 4) if ret_1m is not None else None,
    "return_3m": round(ret_3m, 4) if ret_3m is not None else None,
    "above_ma50": current > ma50,
    "momentum": momentum,
    "current_price": current,
    "ma50": round(ma50, 2),
  }


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
