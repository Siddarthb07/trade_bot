"""StrategyChooser — softmax over expectancy + regime priors."""

from __future__ import annotations

import math
from typing import Any

from processor.hybrid.registry import REGIME_PRIORS, STRATEGY_META, list_strategies


def _softmax(scores: dict[str, float], temperature: float = 0.75) -> dict[str, float]:
  if not scores:
    return {}
  t = max(0.15, float(temperature))
  mx = max(scores.values())
  exps = {k: math.exp((v - mx) / t) for k, v in scores.items()}
  z = sum(exps.values()) or 1.0
  return {k: round(v / z, 6) for k, v in exps.items()}


def choose_strategy(
  *,
  lane: str = "product",
  regime: str = "unknown",
  chooser_state: dict[str, Any] | None = None,
  force_strategy: str | None = None,
) -> dict[str, Any]:
  """Pick one strategy for the session with full rationale."""
  state = chooser_state or {}
  per = state.get("strategies") or {}
  available = [s["id"] for s in list_strategies(lane)]
  if force_strategy:
    if force_strategy not in STRATEGY_META:
      raise KeyError(f"unknown strategy: {force_strategy}")
    return {
      "picked": force_strategy,
      "weights": {force_strategy: 1.0},
      "scores": {force_strategy: 1.0},
      "regime": regime,
      "lane": lane,
      "reason": "forced",
    }

  if lane == "research":
    # Research lane defaults to raw OR-width hero
    return {
      "picked": "orwidth_orb",
      "weights": {"orwidth_orb": 1.0},
      "scores": {"orwidth_orb": 1.0},
      "regime": regime,
      "lane": lane,
      "reason": "research_orwidth_default",
    }

  priors = REGIME_PRIORS.get(regime) or REGIME_PRIORS.get("unknown") or {}
  scores: dict[str, float] = {}
  for sid in available:
    exp = float((per.get(sid) or {}).get("expectancy") or 0.0)
    n = int((per.get(sid) or {}).get("n") or 0)
    # Shrinkage toward 0 until enough samples
    shrink = min(1.0, n / 20.0)
    base = exp * shrink
    scores[sid] = base + float(priors.get(sid) or 0.0)
    # Mild prior toward orwidth on product until learned otherwise
    if sid == "orwidth_orb" and n < 5:
      scores[sid] += 0.08

  # Cold start: no outcomes yet → product/stretch default to orwidth (hero path)
  total_n = sum(int((per.get(s) or {}).get("n") or 0) for s in available)
  if total_n == 0 and "orwidth_orb" in available and lane in ("product", "stretch"):
    return {
      "picked": "orwidth_orb",
      "weights": {s: (1.0 if s == "orwidth_orb" else 0.0) for s in available},
      "scores": {k: round(v, 6) for k, v in scores.items()},
      "regime": regime,
      "lane": lane,
      "reason": "cold_start_orwidth",
    }

  weights = _softmax(scores)
  # Never cold-pick a zero-sample strategy over orwidth when orwidth is available.
  picked = max(weights, key=weights.get) if weights else (available[0] if available else "orwidth_orb")
  if (
    picked != "orwidth_orb"
    and "orwidth_orb" in available
    and int((per.get(picked) or {}).get("n") or 0) == 0
    and int((per.get("orwidth_orb") or {}).get("n") or 0) >= 0
  ):
    # Prefer orwidth until the challenger has real samples (avoids idle adaptive_edge).
    if int((per.get(picked) or {}).get("n") or 0) == 0:
      picked = "orwidth_orb"
  return {
    "picked": picked,
    "weights": weights,
    "scores": {k: round(v, 6) for k, v in scores.items()},
    "regime": regime,
    "lane": lane,
    "reason": "softmax_expectancy_regime",
  }
