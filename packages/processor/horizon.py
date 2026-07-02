"""Estimated hold period and expected return (rule-based, not guaranteed)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from core.models import Signal
from processor.investor_hold import blend_investor_hold_days, investor_median_peak_days
from processor.market_data import compute_trend_features
from processor.partial_exit import build_partial_exit_plan
from processor.timeframe import build_timeframe
from processor.train import load_hold_priors


def estimate_sell_horizon(features: dict, signal: Signal, db: Session | None = None) -> dict:
  action = signal.action.upper()
  if action not in ("BUY", "P", "A"):
    return {
      "days": None,
      "label": "Not a BUY signal",
      "expected_return_pct": None,
      "sell_by_hint": None,
    }

  ret_1m = float(features.get("return_1m") or 0)
  ret_3m = float(features.get("return_3m") or 0)
  median = float(features.get("median_return") or 0.06)
  prob = float(features.get("win_rate") or 0.5)
  cluster = int(features.get("cluster_count") or 0)

  if ret_1m > 0.12 and cluster >= 2:
    days = 7
    reason = "hot momentum + cluster"
  elif ret_1m > 0.05:
    days = 14
    reason = "positive momentum"
  elif ret_3m > 0.12:
    days = 21
    reason = "3mo trend"
  elif median > 0.08:
    days = 30
    reason = "strong investor history"
  else:
    days = 45
    reason = "slow build"

  from processor.fundamentals import fetch_fundamentals
  from processor.return_model import estimate_bulk_returns

  bulk_ret = estimate_bulk_returns(
    median_return=median if median else None,
    win_rate=prob,
    return_1m=ret_1m,
    return_3m=ret_3m,
    cluster_count=cluster,
    fundamentals=fetch_fundamentals(signal.ticker_normalized),
  )
  expected = bulk_ret["expected_return_pct"]

  tier = "HIGH" if prob >= 0.65 else "MEDIUM" if prob >= 0.52 else "LOW"
  priors = load_hold_priors()
  learned = priors.get(tier) or priors.get("default")
  if learned:
    days = int(round(0.65 * days + 0.35 * learned))

  if db is not None and signal.entity_normalized:
    inv = investor_median_peak_days(db, signal.entity_normalized, signal.market)
    days = blend_investor_hold_days(days, inv.get("median_peak_days"))
    investor_label = inv.get("label")
  else:
    investor_label = None

  trend = compute_trend_features(signal.ticker_normalized)
  vol = trend.get("volatility_20d")

  tf = build_timeframe(days, signal_entry_anchor(signal.disclosed_at), volatility_annualized=vol)
  tf["expected_return_pct"] = expected
  tf["return_breakdown"] = bulk_ret["return_breakdown"]
  tf["return_rationale"] = bulk_ret["return_rationale"]
  tf["hold_reason"] = reason
  if investor_label:
    tf["investor_hold_label"] = investor_label
  tf["partial_exit_plan"] = build_partial_exit_plan(days)
  return tf
