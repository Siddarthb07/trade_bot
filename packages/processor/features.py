"""Feature engineering for ML scorer and explanations."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.models import ForwardReturn, InvestorStat, Signal
from processor.market_data import compute_trend_features


def build_features(db: Session, signal: Signal) -> dict[str, float | int | bool | None]:
  stat = (
    db.query(InvestorStat)
    .filter(InvestorStat.entity_normalized == signal.entity_normalized, InvestorStat.market == signal.market)
    .first()
  )
  since = signal.disclosed_at - timedelta(days=90)
  ticker_values = [
    r[0]
    for r in db.query(Signal.value)
    .filter(Signal.ticker == signal.ticker, Signal.market == signal.market, Signal.disclosed_at >= since, Signal.value.isnot(None))
    .all()
    if r[0]
  ]
  deal_pct = None
  if ticker_values and signal.value:
    ticker_values.sort()
    rank = sum(1 for v in ticker_values if v <= signal.value) / len(ticker_values)
    deal_pct = rank

  cluster = (
    db.query(func.count(func.distinct(Signal.entity_normalized)))
    .filter(
      Signal.ticker == signal.ticker,
      Signal.market == signal.market,
      Signal.disclosed_at >= signal.disclosed_at - timedelta(days=7),
      Signal.disclosed_at <= signal.disclosed_at,
    )
    .scalar()
  ) or 0

  trend = compute_trend_features(signal.ticker_normalized, db=db, market=signal.market)
  action_buy = 1 if signal.action.upper() in ("BUY", "P", "A") else 0

  return {
    "win_rate": stat.win_rate if stat and stat.win_rate is not None else 0.5,
    "n_trades": stat.n_trades if stat else 0,
    "median_return": stat.median_return if stat and stat.median_return is not None else 0.0,
    "deal_size_pctile": deal_pct if deal_pct is not None else 0.5,
    "cluster_count": int(cluster),
    "action_buy": action_buy,
    "log_value": float(__import__("math").log10(signal.value + 1)) if signal.value else 0.0,
    "return_1m": trend.get("return_1m") or 0.0,
    "return_3m": trend.get("return_3m") or 0.0,
    "above_ma50": 1 if trend.get("above_ma50") else 0,
    "market_in": 1 if signal.market == "IN" else 0,
  }


def features_to_vector(features: dict) -> list[float]:
  keys = ["win_rate", "n_trades", "median_return", "deal_size_pctile", "cluster_count", "action_buy", "log_value", "return_1m", "return_3m", "above_ma50", "market_in"]
  return [float(features.get(k, 0) or 0) for k in keys]


def estimate_interim_probability(features: dict) -> float:
  """Feature-based estimate when ML labels are unavailable."""
  prob = 0.48
  n = int(features.get("n_trades") or 0)
  wr = float(features.get("win_rate") or 0.5)
  if n >= 10:
    prob += (wr - 0.5) * 0.35
  if features.get("cluster_count", 0) >= 2:
    prob += 0.07
  if float(features.get("deal_size_pctile") or 0) >= 0.75:
    prob += 0.05
  if features.get("action_buy"):
    prob += 0.03
  if features.get("above_ma50"):
    prob += 0.04
  ret_1m = float(features.get("return_1m") or 0)
  if ret_1m > 0.02:
    prob += 0.04
  elif ret_1m < -0.02:
    prob -= 0.05
  return max(0.32, min(0.72, prob))
