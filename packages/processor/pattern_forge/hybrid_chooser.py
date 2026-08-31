"""Stock + market hybrid chooser for Pattern Forge families.

Picks among pattern_candle / orb_two_sided / pattern_analog / cash using:
- market regime (trend / chop / risk_off) from daily closes
- stock session features (OR width, early return, candle hit, analog mean_fwd)

No LLM. Deterministic. Logged for the dash.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from processor.pattern_forge.analogs import analog_signal
from processor.pattern_forge.candles import candle_signal
from processor.strategies import session_or_breakout
from processor.two_sided import normalize_side

FAMILIES = ("pattern_candle", "orb_two_sided", "pattern_analog")

# Soft priors: which family fits which market regime
REGIME_FAMILY_PRIOR: dict[str, dict[str, float]] = {
  "trend": {"orb_two_sided": 0.35, "pattern_analog": 0.1, "pattern_candle": -0.05},
  "chop": {"pattern_candle": 0.3, "pattern_analog": 0.15, "orb_two_sided": -0.1},
  "risk_off": {"pattern_candle": -0.2, "orb_two_sided": -0.35, "pattern_analog": -0.15},
  "unknown": {"orb_two_sided": 0.05, "pattern_candle": 0.05, "pattern_analog": 0.0},
}


def _closes(bars: Sequence[dict[str, Any]]) -> list[float]:
  return [float(b.get("close") or 0) for b in bars]


def stock_features(
  session_bars: Sequence[dict[str, Any]],
  *,
  daily_bars_before: Sequence[dict[str, Any]] | None = None,
  analog_library: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
  sob = session_or_breakout(list(session_bars))
  candle = candle_signal(daily_bars_before or [], session_bars=session_bars)
  analog = analog_signal(_closes(session_bars), analog_library or [])
  closes = _closes(session_bars)
  early = 0.0
  if len(closes) >= 6 and closes[0] > 0:
    early = closes[min(5, len(closes) - 1)] / closes[0] - 1.0
  if len(closes) >= 13:
    c = np.asarray(closes[-13:], dtype=float)
    rets = np.diff(c) / np.maximum(c[:-1], 1e-9)
  else:
    rets = np.array([0.0])
  vol = float(np.std(rets)) if len(rets) else 0.0
  return {
    "or_width_pct": float(sob.get("or_width_pct") or 0),
    "orb_side": str(sob.get("side") or "flat"),
    "orb_conf": float(sob.get("confidence") or 0.5),
    "orb_score": float(sob.get("score") or 0),
    "candle_side": str(candle.get("side") or "flat"),
    "candle_conf": float(candle.get("confidence") or 0.5),
    "candle_reason": str(candle.get("reason") or ""),
    "analog_side": str(analog.get("side") or "flat"),
    "analog_conf": float(analog.get("confidence") or 0.5),
    "analog_mean_fwd": analog.get("mean_fwd"),
    "early_ret": early,
    "session_vol": vol,
    "signals": {"orb": sob, "candle": candle, "analog": analog},
  }


def score_families(
  feats: dict[str, Any],
  *,
  regime: str,
  long_only: bool = True,
) -> dict[str, float]:
  priors = REGIME_FAMILY_PRIOR.get(regime) or REGIME_FAMILY_PRIOR["unknown"]
  scores = {f: float(priors.get(f) or 0.0) for f in FAMILIES}

  orw = float(feats["or_width_pct"])
  # Wide OR + directional break → ORB
  if feats["orb_side"] in ("buy", "sell") and orw >= 0.004:
    bonus = 0.25 + min(0.35, orw * 20.0)
    if long_only and feats["orb_side"] != "buy":
      bonus = -0.3
    scores["orb_two_sided"] += bonus

  # Candle hit → candle family
  if feats["candle_side"] in ("buy", "sell"):
    bonus = 0.2 + (float(feats["candle_conf"]) - 0.5)
    if long_only and feats["candle_side"] != "buy":
      bonus = -0.25
    scores["pattern_candle"] += bonus

  # Analog edge → analog family
  mf = feats.get("analog_mean_fwd")
  if mf is not None and abs(float(mf)) >= 0.003:
    bonus = 0.15 + min(0.4, abs(float(mf)) * 12.0)
    if long_only and float(mf) < 0:
      bonus = -0.2
    scores["pattern_analog"] += bonus

  # Risk-off: prefer cash unless strong long candle
  if regime == "risk_off":
    for f in FAMILIES:
      scores[f] -= 0.25
    if feats["candle_side"] == "buy" and feats["candle_conf"] >= 0.6:
      scores["pattern_candle"] += 0.2

  # High session vol → prefer ORB / trail path over candle
  if float(feats["session_vol"]) >= 0.004:
    scores["orb_two_sided"] += 0.1
    scores["pattern_candle"] -= 0.05

  return scores


def choose_family_for_stock(
  session_bars: Sequence[dict[str, Any]],
  *,
  daily_closes: Sequence[float] | None = None,
  daily_bars_before: Sequence[dict[str, Any]] | None = None,
  analog_library: Sequence[dict[str, Any]] | None = None,
  long_only: bool = True,
  min_score: float = 0.15,
) -> dict[str, Any]:
  """Return picked family or cash, with scores + features for the ledger."""
  regime = "unknown"
  if daily_closes and len(daily_closes) >= 20:
    from processor.pattern_forge.market_regime_proxy import soft_regime

    regime = soft_regime(list(daily_closes))
  elif session_bars and len(session_bars) >= 20:
    # Weak fallback: use session closes only (short series → often unknown)
    from processor.pattern_forge.market_regime_proxy import soft_regime

    regime = soft_regime(_closes(session_bars)[-60:])

  feats = stock_features(
    session_bars,
    daily_bars_before=daily_bars_before,
    analog_library=analog_library,
  )
  scores = score_families(feats, regime=regime, long_only=long_only)
  picked = max(scores, key=scores.get)
  top = float(scores[picked])
  if top < min_score:
    return {
      "picked": "cash",
      "scores": {k: round(v, 4) for k, v in scores.items()},
      "regime": regime,
      "features": feats,
      "reason": f"below_min_score:{top:.3f}",
      "primary": {"side": "flat", "confidence": 0.5, "reason": "hybrid_cash"},
    }

  # Build primary from the winning family's own signal
  sig_map = feats["signals"]
  key = "orb" if picked == "orb_two_sided" else ("candle" if picked == "pattern_candle" else "analog")
  raw = sig_map[key]
  side = normalize_side(str(raw.get("side")))
  if side is None or (long_only and side != "long"):
    return {
      "picked": "cash",
      "scores": {k: round(v, 4) for k, v in scores.items()},
      "regime": regime,
      "features": feats,
      "reason": "winner_flat_or_short_blocked",
      "primary": {"side": "flat", "confidence": 0.5, "reason": "hybrid_no_side"},
    }

  primary = {
    "side": "buy" if side == "long" else "sell",
    "confidence": float(raw.get("confidence") or 0.55),
    "reason": f"hybrid|{picked}|{raw.get('reason')}",
    "or_width_pct": raw.get("or_width_pct") or feats["or_width_pct"],
    "entry_i": raw.get("entry_i"),
    "entry_px": raw.get("entry_px"),
  }
  return {
    "picked": picked,
    "scores": {k: round(v, 4) for k, v in scores.items()},
    "regime": regime,
    "features": {k: v for k, v in feats.items() if k != "signals"},
    "reason": f"stock_market_chooser|{regime}|{picked}",
    "primary": primary,
  }
