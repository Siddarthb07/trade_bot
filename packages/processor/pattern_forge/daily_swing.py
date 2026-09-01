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


def _ema_last(closes: Sequence[float], period: int) -> float | None:
  c = [float(x) for x in closes if float(x) > 0]
  if len(c) < period:
    return None
  k = 2.0 / (period + 1)
  ema = c[0]
  for px in c[1:]:
    ema = px * k + ema * (1.0 - k)
  return float(ema)


def _rolling_vwap(
  closes: Sequence[float],
  highs: Sequence[float],
  lows: Sequence[float],
  volumes: Sequence[float],
  *,
  window: int = 20,
) -> float | None:
  n = min(len(closes), len(highs), len(lows), len(volumes), window)
  if n < 5:
    return None
  num = 0.0
  den = 0.0
  for i in range(-n, 0):
    c = float(closes[i])
    h = float(highs[i])
    l = float(lows[i])
    v = float(volumes[i])
    if c <= 0 or v <= 0:
      continue
    if h <= 0:
      h = c
    if l <= 0:
      l = c
    tp = (h + l + c) / 3.0
    num += tp * v
    den += v
  return float(num / den) if den > 0 else None


def _dist_from_52w_high(closes: Sequence[float]) -> tuple[float | None, bool | None]:
  c = [float(x) for x in closes if float(x) > 0]
  if len(c) < 126:
    return None, None
  window = min(252, len(c))
  hi = max(c[-window:])
  if hi <= 0:
    return None, None
  dist = float(c[-1] / hi - 1.0)
  return dist, dist >= -0.08


def resolve_market_mode(
  *,
  regime: str,
  breadth: dict[str, Any],
  market_closes: Sequence[float],
  asof: str | None = None,
  nifty_ema_period: int = 200,
  defense_on_risk_off: bool = True,
  defense_on_breadth_stress: bool = True,
  defense_on_nifty_below_ema: bool = True,
  october_defense: bool = False,
) -> tuple[str, dict[str, Any]]:
  """Attack = v2-style aggression; defense = tighten / sit out."""
  reasons: list[str] = []
  mkt = [float(x) for x in market_closes if float(x) > 0]
  nifty_above_ema: bool | None = None
  if len(mkt) >= nifty_ema_period:
    ema = _ema_last(mkt, nifty_ema_period)
    if ema and ema > 0:
      nifty_above_ema = mkt[-1] > ema

  mode = "attack"
  if defense_on_risk_off and regime == "risk_off":
    mode = "defense"
    reasons.append("risk_off")
  if defense_on_breadth_stress and breadth.get("stress"):
    mode = "defense"
    reasons.append("breadth_stress")
  if defense_on_nifty_below_ema and nifty_above_ema is False:
    mode = "defense"
    reasons.append("nifty_below_ema200")
  if october_defense and asof and len(asof) >= 7 and asof[5:7] == "10":
    mode = "defense"
    reasons.append("october")

  return mode, {
    "mode": mode,
    "reasons": reasons,
    "nifty_above_ema200": nifty_above_ema,
    "regime": regime,
    "breadth_frac": breadth.get("frac_above_ma20"),
  }


def _apply_score_mode(
  score: float,
  *,
  score_mode: str,
  stock_r1: float,
  market_r1: float | None,
) -> float:
  if score <= 0:
    return score
  mkt = float(market_r1 or 0.0)
  if score_mode == "rs_vs_nifty":
    return max(0.0005, stock_r1 - mkt)
  if score_mode == "rs_times_r1":
    rs = stock_r1 - mkt
    return max(0.0005, stock_r1 * (1.0 + max(-0.5, min(0.5, rs * 8.0))))
  return score


def stock_daily_features(
  closes: Sequence[float],
  *,
  volumes: Sequence[float] | None = None,
  highs: Sequence[float] | None = None,
  lows: Sequence[float] | None = None,
  vwap_window: int = 20,
  ema_period: int = 200,
) -> dict[str, Any]:
  c = [float(x) for x in closes if float(x) > 0]
  if len(c) < 25:
    return {"ok": False, "reason": "short_history"}
  r1 = _rets(c, 1)
  r5 = _rets(c, 5)
  r20 = _rets(c, 20)
  ma20 = float(np.mean(c[-20:]))
  dist_ma = c[-1] / ma20 - 1.0 if ma20 > 0 else 0.0
  vol = float(np.std(np.diff(c[-21:]) / np.maximum(c[-21:-1], 1e-9))) if len(c) >= 22 else 0.0
  ema200 = _ema_last(c, ema_period)
  above_ema200: bool | None = None
  dist_ema200: float | None = None
  if ema200 is not None and ema200 > 0:
    dist_ema200 = c[-1] / ema200 - 1.0
    above_ema200 = c[-1] > ema200

  rel_volume: float | None = None
  vwap_n: float | None = None
  above_vwap: bool | None = None
  dist_vwap: float | None = None
  vols = [float(x) for x in (volumes or []) if x is not None and float(x) >= 0]
  if len(vols) == len(c) and len(vols) >= 21:
    base = float(np.mean(vols[-21:-1])) if float(np.mean(vols[-21:-1])) > 0 else None
    if base and vols[-1] > 0:
      rel_volume = float(vols[-1] / base)
  hs = [float(x) for x in (highs or []) if float(x) > 0]
  ls = [float(x) for x in (lows or []) if float(x) > 0]
  if len(hs) == len(c) and len(ls) == len(c) and len(vols) == len(c):
    vwap_n = _rolling_vwap(c, hs, ls, vols, window=vwap_window)
    if vwap_n is not None and vwap_n > 0:
      dist_vwap = c[-1] / vwap_n - 1.0
      above_vwap = c[-1] > vwap_n

  dist_52w, near_52w = _dist_from_52w_high(c)

  return {
    "ok": True,
    "ret_1": r1,
    "ret_5": r5,
    "ret_20": r20,
    "dist_ma20": dist_ma,
    "vol_20": vol,
    "last": c[-1],
    "ema200": ema200,
    "dist_ema200": dist_ema200,
    "above_ema200": above_ema200,
    "rel_volume": rel_volume,
    "vwap": vwap_n,
    "dist_vwap": dist_vwap,
    "above_vwap": above_vwap,
    "dist_52w_high": dist_52w,
    "near_52w_high": near_52w,
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
      "features": {
        k: feats[k]
        for k in (
          "ret_1",
          "ret_5",
          "ret_20",
          "dist_ma20",
          "vol_20",
          "above_ema200",
          "rel_volume",
          "above_vwap",
          "dist_ema200",
          "dist_vwap",
        )
        if k in feats
      },
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
    "features": {
      k: feats[k]
      for k in (
        "ret_1",
        "ret_5",
        "ret_20",
        "dist_ma20",
        "vol_20",
        "above_ema200",
        "rel_volume",
        "above_vwap",
        "dist_ema200",
        "dist_vwap",
      )
      if k in feats
    },
  }


# Alias — two-sided name for callers / docs
score_daily_candidate = score_daily_long


def _daily_rets(closes: Sequence[float], window: int = 20) -> list[float]:
  c = [float(x) for x in closes if float(x) > 0]
  if len(c) < window + 1:
    return []
  out: list[float] = []
  for i in range(-window, 0):
    if c[i - 1] > 0:
      out.append(c[i] / c[i - 1] - 1.0)
  return out


def _pairwise_corr(closes_a: Sequence[float], closes_b: Sequence[float], *, window: int = 20) -> float | None:
  ra = _daily_rets(closes_a, window)
  rb = _daily_rets(closes_b, window)
  n = min(len(ra), len(rb))
  if n < 8:
    return None
  ra = ra[-n:]
  rb = rb[-n:]
  ca = float(np.corrcoef(ra, rb)[0, 1])
  if ca != ca:  # NaN
    return None
  return float(ca)


def filter_uncorrelated_picks(
  eligible: list[dict[str, Any]],
  universe_closes: dict[str, list[float]],
  *,
  top_k: int,
  max_pairwise_corr: float = 0.65,
) -> list[dict[str, Any]]:
  """Greedy top-k with pairwise return-correlation cap (dedup similar names)."""
  k = max(1, int(top_k))
  picks: list[dict[str, Any]] = []
  for row in eligible:
    if len(picks) >= k:
      break
    ticker = str(row.get("ticker") or "")
    closes = universe_closes.get(ticker) or []
    if len(closes) < 25:
      continue
    ok = True
    for prev in picks:
      pt = str(prev.get("ticker") or "")
      pc = universe_closes.get(pt) or []
      corr = _pairwise_corr(closes, pc)
      if corr is not None and corr > max_pairwise_corr:
        ok = False
        break
    if ok:
      picks.append(row)
  return picks


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
  # v3.1 indicator gates (VWAP / volume / 200 EMA)
  require_above_ema200: bool = False,
  min_rel_volume: float | None = None,
  require_above_vwap: bool = False,
  vwap_score_boost: float = 0.0,
  vol_soft_penalty: bool = False,
  universe_ohlcv: dict[str, dict[str, list[float]]] | None = None,
  # v4 dual-mode engine
  score_mode: str = "raw_r1",
  indicator_mode: str = "off",
  defense_sitout: bool = False,
  defense_size_mult: float = 0.5,
  defense_on_risk_off: bool = True,
  defense_on_breadth_stress: bool = True,
  defense_on_nifty_below_ema: bool = True,
  nifty_ema_period: int = 200,
  october_defense: bool = False,
  october_size_mult: float = 0.5,
  r1_hi_trend: float | None = None,
  boost_near_52w_high: bool = False,
  asof: str | None = None,
  correlation_cap: bool = False,
  max_pairwise_corr: float = 0.65,
) -> dict[str, Any]:
  """Pick top-k FO names for next-day swing (or cash).

  Agents / mistake ledger may only reduce risk (never amplify).
  v3 extras: vol-scaled rank, skip already-extended names, market TS mom gate,
  optional VWAP / relative-volume / 200 EMA confirmation filters.
  v4: attack/defense mode — pure v2 in attack; filters / sit-out in defense.
  """
  banned = {str(t).upper() for t in (exclude_tickers or []) if t}
  regime = soft_regime(list(market_closes or []))
  breadth = breadth_above_ma20(universe_closes)
  mkt = list(market_closes or [])
  market_ts = None
  if require_market_ts_mom and len(mkt) > market_ts_lookback and mkt[-1 - market_ts_lookback] > 0:
    market_ts = float(mkt[-1] / mkt[-1 - market_ts_lookback] - 1.0)
  market_r1 = _rets(mkt, 1) if len(mkt) >= 2 else None

  market_mode, mode_meta = resolve_market_mode(
    regime=regime,
    breadth=breadth,
    market_closes=mkt,
    asof=asof,
    nifty_ema_period=nifty_ema_period,
    defense_on_risk_off=defense_on_risk_off,
    defense_on_breadth_stress=defense_on_breadth_stress,
    defense_on_nifty_below_ema=defense_on_nifty_below_ema,
    october_defense=october_defense,
  )

  eff_r1_hi = float(r1_hi_trend if (r1_hi_trend is not None and regime == "trend") else r1_hi)
  legacy_indicators = require_above_ema200 or require_above_vwap or min_rel_volume is not None
  use_indicators = indicator_mode == "always" or (
    indicator_mode == "defense_only" and market_mode == "defense"
  ) or (indicator_mode == "off" and legacy_indicators)
  eff_require_ema = require_above_ema200 if use_indicators else False
  eff_require_vwap = require_above_vwap if use_indicators else False
  eff_min_vol = min_rel_volume if use_indicators else None

  if market_mode == "defense" and defense_sitout:
    return {
      "picked": "cash",
      "picks": [],
      "regime": regime,
      "breadth": breadth,
      "size_mult": 0.0,
      "reason": f"v4_defense_sitout:{','.join(mode_meta.get('reasons') or [])}",
      "primary": {"side": "flat", "confidence": 0.5, "reason": "defense_sitout"},
      "ranked_top": [],
      "stress_veto": True,
      "exclude_tickers": sorted(banned),
      "market_mode": market_mode,
      "mode_meta": mode_meta,
    }

  ranked: list[dict[str, Any]] = []
  for ticker, closes in universe_closes.items():
    ohlcv = (universe_ohlcv or {}).get(ticker) or {}
    feats = stock_daily_features(
      closes,
      volumes=ohlcv.get("volumes"),
      highs=ohlcv.get("highs"),
      lows=ohlcv.get("lows"),
    )
    sig = score_daily_long(
      feats, regime=regime, long_only=long_only, r1_lo=r1_lo, r1_hi=eff_r1_hi
    )
    score = float(sig.get("score") or -1.0)
    stock_r1 = float(feats.get("ret_1") or 0)
    score = _apply_score_mode(score, score_mode=score_mode, stock_r1=stock_r1, market_r1=market_r1)
    if boost_near_52w_high and score > 0 and feats.get("near_52w_high") is True:
      score = score + 0.001
    if vol_scale_rank and feats.get("ok") and float(feats.get("vol_20") or 0) > 1e-6 and score > 0:
      # Prefer milder paths (risk-managed momentum) — never amplify score above raw
      score = score / max(float(feats["vol_20"]), 0.005)
    if vol_soft_penalty and score > 0:
      rv = feats.get("rel_volume")
      if rv is not None:
        rvf = float(rv)
        if rvf < 1.0:
          score = score * max(0.55, rvf)
        elif rvf >= 1.25:
          score = score + 0.0008
    if vwap_score_boost > 0 and score > 0 and feats.get("above_vwap") is True:
      score = score + min(float(vwap_score_boost), 0.002)
    extended = False
    if skip_extended_r5 is not None and feats.get("ok"):
      r5 = float(feats.get("ret_5") or 0)
      if sig.get("side") == "buy" and r5 >= float(skip_extended_r5):
        extended = True
      if sig.get("side") == "sell" and r5 <= -float(skip_extended_r5):
        extended = True
    indicator_fail = False
    indicator_reason: str | None = None
    if eff_min_vol is not None and not indicator_fail:
      rv = feats.get("rel_volume")
      if rv is None or float(rv) < float(eff_min_vol):
        indicator_fail = True
        indicator_reason = indicator_reason or "low_volume"
    if eff_require_ema and not indicator_fail:
      if feats.get("above_ema200") is not True:
        indicator_fail = True
        indicator_reason = indicator_reason or "below_ema200"
    if eff_require_vwap and not indicator_fail:
      if feats.get("above_vwap") is not True:
        indicator_fail = True
        indicator_reason = indicator_reason or "below_vwap"
    row = {
      "ticker": ticker,
      **sig,
      "score": round(score, 4) if score > 0 else score,
      "banned": ticker.upper() in banned,
      "extended": extended,
      "indicator_fail": indicator_fail,
      "indicator_reason": indicator_reason,
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
    and not r.get("indicator_fail")
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

  if market_mode == "defense" and not defense_sitout:
    size_mult = min(size_mult, max(0.0, min(1.0, float(defense_size_mult))))
  if october_defense and asof and len(asof) >= 7 and asof[5:7] == "10":
    size_mult = min(size_mult, max(0.0, min(1.0, float(october_size_mult))))

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
  if correlation_cap and k > 1:
    picks = filter_uncorrelated_picks(
      eligible, universe_closes, top_k=k, max_pairwise_corr=max_pairwise_corr
    )
  else:
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
    "market_mode": market_mode,
    "mode_meta": mode_meta,
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
