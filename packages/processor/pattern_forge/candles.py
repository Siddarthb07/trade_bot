"""Candle / structure pattern signals — prior-day + session OHLC, no lookahead."""

from __future__ import annotations

from typing import Any, Sequence


def _c(bar: dict[str, Any], key: str) -> float:
  return float(bar.get(key) or 0.0)


def prior_day_candle(daily_bars: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
  """Last fully closed daily bar (caller must pass bars strictly before asof)."""
  if not daily_bars:
    return None
  b = daily_bars[-1]
  o, h, l, c = _c(b, "open"), _c(b, "high"), _c(b, "low"), _c(b, "close")
  if min(o, h, l, c) <= 0:
    return None
  body = c - o
  rng = max(h - l, 1e-9)
  upper = h - max(o, c)
  lower = min(o, c) - l
  return {
    "open": o,
    "high": h,
    "low": l,
    "close": c,
    "body": body,
    "range": rng,
    "body_frac": body / rng,
    "upper_frac": upper / rng,
    "lower_frac": lower / rng,
    "bullish": c > o,
    "bearish": c < o,
  }


def detect_patterns(candle: dict[str, Any]) -> list[dict[str, Any]]:
  """Return pattern hits with suggested side buy|sell|flat."""
  if not candle:
    return []
  hits: list[dict[str, Any]] = []
  bf = float(candle["body_frac"])
  uf = float(candle["upper_frac"])
  lf = float(candle["lower_frac"])
  # Hammer / shooting star
  if lf >= 0.55 and abs(bf) <= 0.25 and uf <= 0.2:
    hits.append({"pattern": "hammer", "side": "buy", "confidence": 0.62})
  if uf >= 0.55 and abs(bf) <= 0.25 and lf <= 0.2:
    hits.append({"pattern": "shooting_star", "side": "sell", "confidence": 0.62})
  # Marubozu-ish
  if bf >= 0.7 and uf <= 0.15 and lf <= 0.15:
    hits.append({"pattern": "bull_marubozu", "side": "buy", "confidence": 0.58})
  if bf <= -0.7 and uf <= 0.15 and lf <= 0.15:
    hits.append({"pattern": "bear_marubozu", "side": "sell", "confidence": 0.58})
  # Range expansion (wide body)
  if abs(bf) >= 0.55 and candle["range"] / max(candle["close"], 1e-9) >= 0.02:
    side = "buy" if candle["bullish"] else "sell"
    hits.append({"pattern": "range_expansion", "side": side, "confidence": 0.56})
  return hits


def session_engulf(
  prior: dict[str, Any] | None,
  session_open: float,
  session_px: float,
) -> dict[str, Any] | None:
  """Intraday engulf vs prior day body midpoint — causal on session_px."""
  if not prior or session_open <= 0 or session_px <= 0:
    return None
  mid = (prior["open"] + prior["close"]) / 2.0
  if prior["bearish"] and session_px > mid and session_px > session_open:
    return {"pattern": "bull_engulf_session", "side": "buy", "confidence": 0.6}
  if prior["bullish"] and session_px < mid and session_px < session_open:
    return {"pattern": "bear_engulf_session", "side": "sell", "confidence": 0.6}
  return None


def candle_signal(
  daily_bars_before_asof: Sequence[dict[str, Any]],
  *,
  session_bars: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
  """Aggregate candle vote. Flat if no pattern."""
  prior = prior_day_candle(daily_bars_before_asof)
  hits = detect_patterns(prior) if prior else []
  if session_bars and len(session_bars) >= 2 and prior:
    eng = session_engulf(prior, _c(session_bars[0], "open"), _c(session_bars[-1], "close"))
    if eng:
      hits.append(eng)
  if not hits:
    return {"side": "flat", "confidence": 0.5, "patterns": [], "reason": "no_candle_pattern"}
  # Prefer highest confidence; break ties toward last hit
  best = max(hits, key=lambda h: float(h["confidence"]))
  return {
    "side": best["side"],
    "confidence": float(best["confidence"]),
    "patterns": hits,
    "reason": best["pattern"],
  }
