"""Interim + ML tier scoring."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.models import InvestorStat, Signal, SignalScore
from processor.features import build_features, estimate_interim_probability
from processor.horizon import estimate_sell_horizon


def _percentile_value(db: Session, ticker: str, market: str, disclosed_at: datetime) -> float | None:
  since = disclosed_at - timedelta(days=90)
  values = [
    row[0]
    for row in db.query(Signal.value)
    .filter(
      Signal.ticker == ticker,
      Signal.market == market,
      Signal.disclosed_at >= since,
      Signal.value.isnot(None),
    )
    .all()
    if row[0] is not None
  ]
  if not values:
    return None
  values.sort()
  idx = int(0.75 * (len(values) - 1))
  return values[idx]


def _has_cluster(db: Session, signal: Signal) -> bool:
  since = signal.disclosed_at - timedelta(days=7)
  count = (
    db.query(func.count(func.distinct(Signal.entity_normalized)))
    .filter(
      Signal.ticker == signal.ticker,
      Signal.market == signal.market,
      Signal.disclosed_at >= since,
      Signal.disclosed_at <= signal.disclosed_at,
    )
    .scalar()
  )
  return (count or 0) >= 2


def score_macro_signal(db: Session, signal: Signal) -> SignalScore:
  from processor.macro_themes import evaluate_pick, get_theme

  raw = signal.raw_json or {}
  slug = raw.get("theme_slug")
  theme = get_theme(slug) if slug else None
  pick = None
  if theme:
    from processor.macro_themes import ThemeStock

    stock = ThemeStock(signal.ticker, signal.market, raw.get("company_name") or signal.ticker)
    pick = evaluate_pick(theme, stock)

  prob = (pick or {}).get("calibrated_probability") or 0.52
  expected = (pick or {}).get("expected_return_pct") or 0.06
  tier = (pick or {}).get("tier") or "MEDIUM"
  days = (pick or {}).get("sell_horizon_days") or 60
  from core.hold_prefs import effective_hold_prefs

  days = int(days * effective_hold_prefs(db).theme_hold_multiplier)

  from processor.confluence import apply_bulk_confidence_boost, bulk_confluence

  conf = bulk_confluence(db, signal.ticker, signal.market, since_days=30)
  prob = apply_bulk_confidence_boost(prob, bulk_confirmed=conf["bulk_confirmed"]) or prob
  if conf["bulk_confirmed"] and tier == "MEDIUM" and prob >= 0.58:
    tier = "HIGH"

  from processor.market_data import compute_trend_features
  from processor.partial_exit import build_partial_exit_plan
  from processor.timeframe import build_timeframe, signal_entry_anchor

  trend = compute_trend_features(signal.ticker_normalized, db=db, market=signal.market)
  tf = build_timeframe(int(days), signal_entry_anchor(signal.disclosed_at), volatility_annualized=trend.get("volatility_20d"))
  tf["partial_exit_plan"] = build_partial_exit_plan(int(days))
  distribution = {
    "median": None,
    "win_rate": None,
    "calibrated_probability": prob,
    "p10": None,
    "p90": None,
    "expected_return_pct": expected,
    "theme_heat": (pick or {}).get("theme_heat"),
    "alignment_score": (pick or {}).get("alignment_score"),
    "composite_score": (pick or {}).get("composite_score"),
    "bulk_confirmed": conf["bulk_confirmed"],
    "bulk_deal_count": conf["bulk_deal_count"],
    "return_breakdown": (pick or {}).get("return_breakdown"),
    "return_rationale": (pick or {}).get("return_rationale"),
    "fundamentals": (pick or {}).get("fundamentals"),
    **tf,
  }

  score = (
    db.query(SignalScore)
    .filter(SignalScore.signal_id == signal.id)
    .order_by(SignalScore.scored_at.desc())
    .first()
  )
  if score is None:
    score = SignalScore(signal_id=signal.id)
    db.add(score)
  score.tier = tier
  score.historical_win_rate = None
  score.n_trades = 0
  score.return_distribution = distribution
  score.scored_at = datetime.now(timezone.utc)
  score.scorer_version = "macro-theme-v1"
  db.commit()
  db.refresh(score)
  return score


def score_signal_ml(db: Session, signal: Signal) -> SignalScore:
  if signal.source == "macro_theme":
    return score_macro_signal(db, signal)
  stat = (
    db.query(InvestorStat)
    .filter(InvestorStat.entity_normalized == signal.entity_normalized, InvestorStat.market == signal.market)
    .first()
  )
  n_trades = stat.n_trades if stat else 0
  win_rate = stat.win_rate if stat else None
  p75 = _percentile_value(db, signal.ticker, signal.market, signal.disclosed_at)
  value = signal.value or 0

  ml = None
  try:
    from processor.train import model_is_trained, predict_signal

    if model_is_trained():
      ml = predict_signal(db, signal)
  except Exception:
    ml = None
  scorer_version = "interim-v1"
  calibrated_prob = None
  if ml:
    calibrated_prob = ml["calibrated_probability"]
    scorer_version = "lgbm-platt-v1"
  else:
    feats = build_features(db, signal)
    calibrated_prob = estimate_interim_probability(feats)
    scorer_version = "interim-features-v1"

  tier = "LOW"
  prob_for_tier = calibrated_prob if calibrated_prob is not None else win_rate
  if prob_for_tier is not None and prob_for_tier >= 0.60 and n_trades >= 20:
    tier = "HIGH"
  elif prob_for_tier is not None and prob_for_tier >= 0.52 and (n_trades >= 10 or _has_cluster(db, signal)):
    tier = "MEDIUM"
  elif n_trades >= 30 and win_rate is not None and win_rate >= 0.55 and p75 is not None and value >= p75:
    tier = "HIGH"
  elif n_trades >= 10 or _has_cluster(db, signal):
    tier = "MEDIUM"

  distribution = {
    "median": stat.median_return if stat else None,
    "win_rate": win_rate,
    "calibrated_probability": calibrated_prob,
    "p10": None,
    "p90": None,
  }
  feats = build_features(db, signal)
  horizon = estimate_sell_horizon(feats, signal, db=db)
  distribution.update({k: v for k, v in horizon.items() if k not in distribution or k in horizon})
  if horizon.get("expected_return_pct") is not None:
    distribution["expected_return_pct"] = horizon["expected_return_pct"]

  score = (
    db.query(SignalScore)
    .filter(SignalScore.signal_id == signal.id)
    .order_by(SignalScore.scored_at.desc())
    .first()
  )
  if score is None:
    score = SignalScore(signal_id=signal.id)
    db.add(score)
  score.tier = tier
  score.historical_win_rate = win_rate
  score.n_trades = n_trades
  score.return_distribution = distribution
  score.scored_at = datetime.now(timezone.utc)
  score.scorer_version = scorer_version
  db.commit()
  db.refresh(score)
  return score


def score_signal(db: Session, signal: Signal) -> SignalScore:
  return score_signal_ml(db, signal)
