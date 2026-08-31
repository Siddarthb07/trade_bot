"""Strategy registry for hybrid engine."""

from __future__ import annotations

from typing import Any

from processor.orwidth_product import ORWIDTH_HERO_CONFIGS, product_kwargs

STRATEGY_META: dict[str, dict[str, Any]] = {
  "orwidth_orb": {
    "family": "intraday",
    "description": "OR-width ranked open-range breakout (hero / product)",
    "lanes": ["product", "stretch", "research"],
    "sim_ready": True,
  },
  "copy_bulk_pro": {
    "family": "smart_money",
    "description": "Copy NSE bulk/block BUYs from high win-rate investors (prior session, no lookahead)",
    "lanes": ["product", "stretch", "research"],
    "sim_ready": True,
  },
  "adaptive_edge": {
    "family": "adaptive",
    "description": "Peer-gated adaptive edge on daily context",
    "lanes": ["product", "stretch"],
    "sim_ready": True,
  },
  "mom_cross": {
    "family": "momentum",
    "description": "MA cross momentum (playbook) — registry only until hybrid path wires daily signals",
    "lanes": ["product", "stretch"],
    "sim_ready": False,
  },
  "mean_rev_bb": {
    "family": "mean_reversion",
    "description": "Bollinger mean reversion — registry only until wired",
    "lanes": ["product", "stretch"],
    "sim_ready": False,
  },
  "trend_follow": {
    "family": "momentum",
    "description": "Trend follow — registry only until wired",
    "lanes": ["product", "stretch"],
    "sim_ready": False,
  },
  "mean_rev_chop": {
    "family": "mean_reversion",
    "description": "Mean rev in chop — registry only until wired",
    "lanes": ["product", "stretch"],
    "sim_ready": False,
  },
  "pattern_candle": {
    "family": "pattern_forge",
    "description": "Candle/structure patterns + recognition swarm gate (F&O shorts only)",
    "lanes": ["product", "stretch", "research"],
    "sim_ready": True,
  },
  "pattern_analog": {
    "family": "pattern_forge",
    "description": "DTW/analog session match + recognition swarm gate",
    "lanes": ["product", "stretch", "research"],
    "sim_ready": True,
  },
  "orb_two_sided": {
    "family": "intraday",
    "description": "Two-sided ORB breakout/breakdown; F&O shorts on sell",
    "lanes": ["product", "stretch", "research"],
    "sim_ready": True,
  },
  "hybrid_stock_market": {
    "family": "pattern_forge",
    "description": "Per-stock + market-regime chooser across candle/ORB/analog (cash when weak)",
    "lanes": ["product", "stretch", "research"],
    "sim_ready": True,
  },
  "daily_swing": {
    "family": "pattern_forge",
    "description": "Clean-PIT daily momentum swing (close→next close) with regime gate",
    "lanes": ["product", "stretch", "research"],
    "sim_ready": True,
  },
}

# Regime priors: boost strategies that historically fit the regime label
REGIME_PRIORS: dict[str, dict[str, float]] = {
  "trend": {"orwidth_orb": 0.15, "trend_follow": 0.25, "mom_cross": 0.15, "adaptive_edge": 0.1},
  "chop": {"mean_rev_bb": 0.2, "mean_rev_chop": 0.25, "adaptive_edge": 0.15, "orwidth_orb": -0.05},
  "risk_off": {"adaptive_edge": -0.3, "orwidth_orb": -0.4, "mom_cross": -0.2},
  "unknown": {},
}


def list_strategies(lane: str | None = None, *, sim_ready_only: bool = True) -> list[dict[str, Any]]:
  out = []
  for sid, meta in STRATEGY_META.items():
    if lane and lane not in meta["lanes"]:
      continue
    if sim_ready_only and not meta.get("sim_ready", False):
      continue
    out.append({"id": sid, **meta})
  return out


def sim_kwargs_for_strategy(strategy_id: str, lane: str) -> dict[str, Any]:
  """Map strategy + lane to day_sim kwargs."""
  if strategy_id == "orwidth_orb":
    if lane == "research":
      return product_kwargs("in_tr10_orwidth_chase5_75x")
    if lane == "stretch":
      kw = product_kwargs("in_tr10_orwidth_chase5_75x_guard")
      kw["max_trade_risk_pct"] = 8.0
      kw["max_daily_loss_pct"] = 8.0
      kw["max_chase_attempts"] = 3
      return kw
    return product_kwargs("in_tr10_orwidth_chase5_75x_guard")

  if strategy_id == "copy_bulk_pro":
    return {
      "filter_mode": "copy_bulk_pro",
      "max_leverage": 5.0 if lane != "research" else 3.0,
      "conf_floor": 0.55,
      "max_daily_loss_pct": 4.0,
      "max_trade_risk_pct": 3.0,
      "intraday_stop_with_session_end": True,
      "exit_at_session_end": True,
      "max_chase_attempts": 1,
      "use_hl_exits": False,
      # Returns push 2026-08-29: selective 2nd slot (WR≥0.65 + score gap≥0.5).
      "max_positions": 2 if lane != "research" else 1,
      "bulk_lookback_sessions": 1,
      "bulk_min_win_rate": 0.55,
      # min_n=1 + shrink: sparse forward_returns can't support n>=3 on most days;
      # thin-sample WR=1.0 is handled by bulk_wr_pseudo_n (not by excluding everyone).
      "bulk_min_n_trades": 1,
      "bulk_min_deal_value": 0.0,
      # Push winner: use85 + soft trail arm 2.5% / trail 1.0% → 3/4 months ≥10%, mean +11.2%, DD 14.8%.
      "capital_use_frac": 0.85 if lane != "research" else 0.6,
      "soft_trail_arm_pct": 0.025,
      "soft_trail_pct": 0.01,
      "bulk_second_min_wr": 0.65,
      "bulk_second_min_score_gap": 0.5,
      # Shrink thin-sample WR; PIT ranking requires n>=3 matured outcomes before asof.
      "bulk_wr_prior": 0.55,
      "bulk_wr_pseudo_n": 5.0,
      # Window-level (hybrid engine / multi-day runners); stripped before simulate_day.
      "sl_cooldown_days": 1,
      "entity_cooldown_days": 1,
      "sitout_after_sl_days": 0,
    }

  if strategy_id in ("pattern_candle", "pattern_analog", "orb_two_sided", "hybrid_stock_market"):
    return {
      "filter_mode": "pattern_forge",
      "pattern_family": strategy_id,
      "max_leverage": 3.0 if lane == "product" else (5.0 if lane == "stretch" else 2.0),
      "conf_floor": 0.55,
      "max_daily_loss_pct": 4.0,
      "max_trade_risk_pct": 3.0,
      "intraday_stop_with_session_end": True,
      "exit_at_session_end": True,
      "max_chase_attempts": 1,
      "use_hl_exits": False,
      "max_positions": 1,
      "capital_use_frac": 0.25 if lane == "product" else 0.4,
      "soft_trail_arm_pct": 0.025,
      "soft_trail_pct": 0.01,
      "sleeve_frac": 0.25 if lane == "product" else 0.4,
      "no_ruin": True,
      "fo_shorts_only": True,
      "long_only": strategy_id == "hybrid_stock_market",
    }

  # Non-OR strategies: session modes with guards; always one slot in hybrid
  base = {
    "filter_mode": "orb_only" if strategy_id == "orwidth_orb" else "relaxed",
    "max_leverage": 5.0 if lane == "product" else (8.0 if lane == "stretch" else 1.0),
    "conf_floor": 0.55,
    "max_daily_loss_pct": 4.0,
    "max_trade_risk_pct": 3.0,
    "intraday_stop_with_session_end": True,
    "max_chase_attempts": 1,
    "use_hl_exits": False,
    "max_positions": 1,
  }
  if strategy_id == "adaptive_edge":
    base["filter_mode"] = "strict"
    base["conf_floor"] = 0.70
  if strategy_id == "orwidth_orb":
    # already returned above for orwidth
    pass
  return base


def available_orwidth_products() -> list[str]:
  return list(ORWIDTH_HERO_CONFIGS.keys())
