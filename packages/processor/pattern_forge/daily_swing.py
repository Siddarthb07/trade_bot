"""Clean-PIT daily swing helpers for Pattern Forge.

Session 1h ORB→close cannot clear ~30bps RT on FO Q4'25 (oracle best≈23bps).
Daily best-of-12 moves average ~200bps — enough room after costs if selection has any edge.

Signal at day T close uses only closes ≤ T. Position: enter close[T], exit close[T+1]
(close-to-close; no open print required).
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from processor.pattern_forge.market_regime_proxy import soft_regime
from processor.two_sided import normalize_side


def _rets(closes: Sequence[float], n: int) -> float | None:
  if len(closes) <= n or closes[-1 - n] <= 0:
    return None
  return float(closes[-1] / closes[-1 - n] - 1.0)


def stock_daily_features(closes: Sequence[float]) -> dict[str, Any]:
  c = [float(x) for x in closes if float(x) > 0]
  if len(c) < 25:
    return {"ok": False, "reason": "short_history"}
  r1 = _rets(c, 1)
  r5 = _rets(c, 5)
  r20 = _rets(c, 20)
  ma20 = float(np.mean(c[-20:]))
  dist_ma = c[-1] / ma20 - 1.0 if ma20 > 0 else 0.0
  vol = float(np.std(np.diff(c[-21:]) / np.maximum(c[-21:-1], 1e-9))) if len(c) >= 22 else 0.0
  return {
    "ok": True,
    "ret_1": r1,
    "ret_5": r5,
    "ret_20": r20,
    "dist_ma20": dist_ma,
    "vol_20": vol,
    "last": c[-1],
  }


def score_daily_long(
  feats: dict[str, Any],
  *,
  regime: str,
  long_only: bool = True,
  r1_lo: float = 0.005,
  r1_hi: float = 0.06,
) -> dict[str, Any]:
  """Score long (or optional short) daily continuation in the mild r1 band.

  Shorts require long_only=False and are FO-universe only at the runner layer.
  """
  if not feats.get("ok"):
    return {"side": "flat", "score": -1.0, "confidence": 0.5, "reason": feats.get("reason") or "bad"}
  r1 = float(feats.get("ret_1") or 0)
  r5 = float(feats.get("ret_5") or 0)

  if regime == "risk_off":
    return {
      "side": "flat",
      "score": -1.0,
      "confidence": 0.5,
      "reason": f"daily_swing|risk_off|r1={r1:.3f}",
      "features": {k: feats[k] for k in ("ret_1", "ret_5", "ret_20", "dist_ma20", "vol_20") if k in feats},
    }

  # Primary rank key = r1 inside mild-momentum band (not a chase, not flat)
  in_band_long = r1_lo <= r1 <= r1_hi and r5 >= -0.03
  score = r1 if in_band_long else -1.0
  if regime == "trend" and in_band_long:
    score += 0.002

  side = "flat"
  if in_band_long and score > 0:
    side = "buy"
  # Mirror band for shorts: down day in [-r1_hi, -r1_lo], r5 not exploding up
  in_band_short = (not long_only) and (-r1_hi <= r1 <= -r1_lo) and r5 <= 0.03
  if in_band_short:
    side = "sell"
    score = abs(r1)
    if regime == "trend":
      score += 0.001

  conf = min(0.85, 0.52 + abs(r1) * 6.0) if side != "flat" else 0.5
  return {
    "side": side,
    "score": round(float(score), 4),
    "confidence": round(conf, 4),
    "reason": f"daily_swing|{regime}|{side}|r1={r1:.3f}|r5={r5:.3f}",
    "features": {k: feats[k] for k in ("ret_1", "ret_5", "ret_20", "dist_ma20", "vol_20") if k in feats},
  }


# Alias — two-sided name for callers / docs
score_daily_candidate = score_daily_long


def breadth_above_ma20(universe_closes: dict[str, list[float]]) -> dict[str, Any]:
  """Fraction of names with last close > MA20 — independent of RELIANCE proxy."""
  ok = 0
  n = 0
  for closes in universe_closes.values():
    c = [float(x) for x in closes if float(x) > 0]
    if len(c) < 20:
      continue
    n += 1
    ma = float(np.mean(c[-20:]))
    if c[-1] > ma:
      ok += 1
  frac = (ok / n) if n else 0.5
  # Stress: very few names above MA20
  stress = frac < 0.35
  return {"frac_above_ma20": round(frac, 4), "n": n, "stress": stress}


def choose_daily_candidate(
  universe_closes: dict[str, list[float]],
  *,
  market_closes: Sequence[float] | None = None,
  long_only: bool = True,
  min_score: float = 0.005,
  r1_lo: float = 0.005,
  r1_hi: float = 0.06,
  top_k: int = 1,
  use_breadth_veto: bool = False,
  breadth_scale: bool = True,
  exclude_tickers: Sequence[str] | None = None,
  mistake_size_mult: float = 1.0,
  sitout: bool = False,
  # v3 risk-managed momentum knobs (never amplify)
  vol_scale_rank: bool = False,
  skip_extended_r5: float | None = None,
  require_market_ts_mom: bool = False,
  market_ts_lookback: int = 20,
  market_ts_min: float = 0.0,
) -> dict[str, Any]:
  """Pick top-k FO names for next-day swing (or cash).

  Agents / mistake ledger may only reduce risk (never amplify).
  v3 extras: vol-scaled rank, skip already-extended names, market TS mom gate.
  """
  banned = {str(t).upper() for t in (exclude_tickers or []) if t}
  regime = soft_regime(list(market_closes or []))
  breadth = breadth_above_ma20(universe_closes)
  mkt = list(market_closes or [])
  market_ts = None
  if require_market_ts_mom and len(mkt) > market_ts_lookback and mkt[-1 - market_ts_lookback] > 0:
    market_ts = float(mkt[-1] / mkt[-1 - market_ts_lookback] - 1.0)

  ranked: list[dict[str, Any]] = []
  for ticker, closes in universe_closes.items():
    feats = stock_daily_features(closes)
    sig = score_daily_long(
      feats, regime=regime, long_only=long_only, r1_lo=r1_lo, r1_hi=r1_hi
    )
    score = float(sig.get("score") or -1.0)
    if vol_scale_rank and feats.get("ok") and float(feats.get("vol_20") or 0) > 1e-6 and score > 0:
      # Prefer milder paths (risk-managed momentum) — never amplify score above raw
      score = score / max(float(feats["vol_20"]), 0.005)
    extended = False
    if skip_extended_r5 is not None and feats.get("ok"):
      r5 = float(feats.get("ret_5") or 0)
      if sig.get("side") == "buy" and r5 >= float(skip_extended_r5):
        extended = True
      if sig.get("side") == "sell" and r5 <= -float(skip_extended_r5):
        extended = True
    row = {
      "ticker": ticker,
      **sig,
      "score": round(score, 4) if score > 0 else score,
      "banned": ticker.upper() in banned,
      "extended": extended,
    }
    ranked.append(row)

  ranked.sort(key=lambda r: float(r.get("score") or -999), reverse=True)
  eligible = [
    r
    for r in ranked
    if r.get("side") != "flat"
    and float(r.get("score") or -999) >= min_score
    and not r.get("banned")
    and not r.get("extended")
  ]

  size_mult = max(0.0, min(1.0, float(mistake_size_mult)))
  if breadth_scale and not use_breadth_veto:
    # Soft sit-out: frac 0.25→0, 0.50→1 (never amplify above 1)
    frac = float(breadth.get("frac_above_ma20") or 0.5)
    size_mult = min(size_mult, max(0.0, min(1.0, (frac - 0.25) / 0.25)))

  if require_market_ts_mom and market_ts is not None and market_ts < market_ts_min:
    # Soft: half size in weak TS mom; hard sit if deep negative
    if market_ts < market_ts_min - 0.03:
      size_mult = 0.0
    else:
      size_mult = min(size_mult, 0.5)

  if sitout:
    return {
      "picked": "cash",
      "picks": [],
      "regime": regime,
      "breadth": breadth,
      "size_mult": 0.0,
      "reason": "mistake_ledger_sitout",
      "primary": {"side": "flat", "confidence": 0.5, "reason": "mistake_sitout"},
      "ranked_top": ranked[:5],
      "stress_veto": True,
      "exclude_tickers": sorted(banned),
    }

  if use_breadth_veto and breadth.get("stress"):
    return {
      "picked": "cash",
      "picks": [],
      "regime": regime,
      "breadth": breadth,
      "size_mult": 0.0,
      "reason": f"breadth_stress:{breadth.get('frac_above_ma20')}",
      "primary": {"side": "flat", "confidence": 0.5, "reason": "breadth_veto"},
      "ranked_top": ranked[:5],
      "stress_veto": True,
      "exclude_tickers": sorted(banned),
    }

  if size_mult <= 0.05:
    return {
      "picked": "cash",
      "picks": [],
      "regime": regime,
      "breadth": breadth,
      "size_mult": 0.0,
      "reason": f"size_flat:{size_mult}",
      "primary": {"side": "flat", "confidence": 0.5, "reason": "size_flat"},
      "ranked_top": ranked[:5],
      "stress_veto": True,
      "exclude_tickers": sorted(banned),
    }

  if regime == "risk_off":
    return {
      "picked": "cash",
      "picks": [],
      "regime": regime,
      "breadth": breadth,
      "size_mult": 0.0,
      "reason": "risk_off_veto",
      "primary": {"side": "flat", "confidence": 0.5, "reason": "risk_off"},
      "ranked_top": ranked[:5],
      "stress_veto": True,
      "exclude_tickers": sorted(banned),
    }

  k = max(1, int(top_k))
  picks = eligible[:k]
  if not picks:
    reason = "no_daily_candidate"
    if banned and any(r.get("banned") and r.get("side") != "flat" for r in ranked[:k]):
      reason = "mistake_ledger_blocked"
    return {
      "picked": "cash",
      "picks": [],
      "regime": regime,
      "breadth": breadth,
      "size_mult": size_mult,
      "reason": reason,
      "primary": {"side": "flat", "confidence": 0.5, "reason": reason},
      "ranked_top": ranked[:5],
      "stress_veto": False,
      "exclude_tickers": sorted(banned),
    }

  best = picks[0]
  return {
    "picked": best["ticker"],
    "picks": [{"ticker": p["ticker"], "side": p["side"], "score": p["score"], "confidence": p["confidence"]} for p in picks],
    "regime": regime,
    "breadth": breadth,
    "size_mult": round(size_mult, 4),
    "reason": best.get("reason"),
    "primary": {
      "side": best["side"],
      "confidence": best["confidence"],
      "reason": best.get("reason"),
      "score": best["score"],
    },
    "hybrid_choice": {
      "picked": "daily_swing",
      "regime": regime,
      "reason": best.get("reason"),
      "scores": {
        "daily_swing": best["score"],
        "breadth": breadth.get("frac_above_ma20"),
        "size_mult": size_mult,
        "market_ts": market_ts,
      },
    },
    "ranked_top": ranked[:5],
    "stress_veto": False,
    "exclude_tickers": sorted(banned),
    "market_ts": market_ts,
  }


def next_day_pnl_frac(
  closes: Sequence[float],
  *,
  side: str,
) -> dict[str, Any]:
  """Apply close[T] → close[T+1] using last two points of series that includes T+1."""
  if len(closes) < 2:
    return {"ok": False, "reason": "need_t1"}
  entry = float(closes[-2])
  exit_px = float(closes[-1])
  ns = normalize_side(side)
  if ns is None or entry <= 0:
    return {"ok": False, "reason": "bad_side"}
  raw = exit_px / entry - 1.0
  pnl = raw if ns == "long" else -raw
  return {
    "ok": True,
    "entry_px": entry,
    "exit_px": exit_px,
    "pnl_frac": pnl,
    "exit_reason": "next_close",
    "side": ns,
  }
