"""Public fundamentals from yfinance (cached)."""

from __future__ import annotations

import logging
import time
from typing import Any

import yfinance as yf

logger = logging.getLogger(__name__)

_CACHE_TTL_SEC = 3600
_fund_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_YF_TIMEOUT = 8

_FIELDS = (
  "trailingPE",
  "forwardPE",
  "priceToBook",
  "profitMargins",
  "ebitdaMargins",
  "operatingMargins",
  "returnOnEquity",
  "revenueGrowth",
  "earningsGrowth",
  "debtToEquity",
  "currentRatio",
  "marketCap",
  "enterpriseToEbitda",
  "ebitda",
  "totalRevenue",
)


def _safe_float(v: Any) -> float | None:
  if v is None:
    return None
  try:
    f = float(v)
    if f != f:  # NaN
      return None
    return f
  except (TypeError, ValueError):
    return None


def fetch_fundamentals(ticker_normalized: str) -> dict[str, Any]:
  cached = _fund_cache.get(ticker_normalized)
  if cached and time.monotonic() - cached[0] < _CACHE_TTL_SEC:
    return cached[1]

  out: dict[str, Any] = {
    "trailing_pe": None,
    "forward_pe": None,
    "price_to_book": None,
    "profit_margin": None,
    "ebitda_margin": None,
    "operating_margin": None,
    "return_on_equity": None,
    "revenue_growth": None,
    "earnings_growth": None,
    "debt_to_equity": None,
    "current_ratio": None,
    "market_cap": None,
    "ev_to_ebitda": None,
    "ebitda": None,
    "revenue": None,
    "sector": None,
    "industry": None,
  }

  try:
    t = yf.Ticker(ticker_normalized)
    info = t.info or {}
    out["trailing_pe"] = _safe_float(info.get("trailingPE"))
    out["forward_pe"] = _safe_float(info.get("forwardPE"))
    out["price_to_book"] = _safe_float(info.get("priceToBook"))
    out["profit_margin"] = _safe_float(info.get("profitMargins"))
    out["ebitda_margin"] = _safe_float(info.get("ebitdaMargins"))
    out["operating_margin"] = _safe_float(info.get("operatingMargins"))
    out["return_on_equity"] = _safe_float(info.get("returnOnEquity"))
    out["revenue_growth"] = _safe_float(info.get("revenueGrowth"))
    out["earnings_growth"] = _safe_float(info.get("earningsGrowth"))
    out["debt_to_equity"] = _safe_float(info.get("debtToEquity"))
    out["current_ratio"] = _safe_float(info.get("currentRatio"))
    out["market_cap"] = _safe_float(info.get("marketCap"))
    out["ev_to_ebitda"] = _safe_float(info.get("enterpriseToEbitda"))
    out["ebitda"] = _safe_float(info.get("ebitda"))
    out["revenue"] = _safe_float(info.get("totalRevenue"))
    out["sector"] = info.get("sector")
    out["industry"] = info.get("industry")
  except Exception as exc:
    logger.warning("fundamentals fetch failed for %s: %s", ticker_normalized, exc)

  _fund_cache[ticker_normalized] = (time.monotonic(), out)
  return out


def fundamentals_score(fund: dict[str, Any]) -> float:
  """0–1 quality score from public ratios."""
  score = 0.5
  pe = fund.get("trailing_pe")
  if pe is not None:
    if 8 <= pe <= 28:
      score += 0.12
    elif pe > 45:
      score -= 0.12
    elif pe < 0:
      score -= 0.08

  margin = fund.get("profit_margin")
  if margin is not None:
    if margin >= 0.15:
      score += 0.1
    elif margin >= 0.08:
      score += 0.05
    elif margin < 0:
      score -= 0.1

  rev_g = fund.get("revenue_growth")
  if rev_g is not None:
    if rev_g >= 0.15:
      score += 0.1
    elif rev_g >= 0.05:
      score += 0.05
    elif rev_g < -0.05:
      score -= 0.08

  roe = fund.get("return_on_equity")
  if roe is not None:
    if roe >= 0.18:
      score += 0.06
    elif roe < 0.05:
      score -= 0.05

  return max(0.0, min(1.0, score))
