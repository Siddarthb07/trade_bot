"""Honest, feature-based trade thesis (no LLM)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from core.models import Signal
from processor.features import build_features
from processor.market_data import compute_trend_features, explain_trend_narrative


def build_thesis(db: Session, signal: Signal, score: dict) -> dict:
  if signal.source == "macro_theme":
    return _build_macro_thesis(signal, score)

  features = build_features(db, signal)
  trend = compute_trend_features(signal.ticker_normalized)
  bullets: list[str] = []
  risks: list[str] = []

  entity = signal.entity
  action = signal.action
  wr = score.get("historical_win_rate") or features.get("win_rate")
  n = score.get("n_trades") or features.get("n_trades", 0)

  if n >= 30 and wr and wr >= 0.55:
    bullets.append(f"{entity} has a {wr*100:.0f}% historical win rate over {int(n)} past similar trades (3mo horizon).")
  elif n >= 10:
    bullets.append(f"{entity} has limited history ({int(n)} trades, {wr*100:.0f}% win rate) — treat as exploratory.")
  else:
    risks.append(f"Small sample: only {int(n)} historical trades for {entity}.")

  if features.get("deal_size_pctile", 0) >= 0.75:
    bullets.append(f"This is a large deal — top quartile by value for {signal.ticker} in the last 90 days.")
  if features.get("cluster_count", 0) >= 2:
    bullets.append(f"Smart-money cluster: {int(features['cluster_count'])} distinct investors active on {signal.ticker} within 7 days.")

  if trend.get("momentum") == "bullish":
    bullets.append(f"Price momentum is positive: +{trend.get('return_1m', 0)*100:.1f}% over ~1 month.")
  elif trend.get("momentum") == "bearish":
    risks.append(f"Recent price trend is weak: {trend.get('return_1m', 0)*100:.1f}% over ~1 month.")

  if trend.get("above_ma50"):
    bullets.append(f"Stock trades above its 50-day average (₹{trend.get('ma50')} vs ₹{trend.get('current_price')}).")
  else:
    risks.append("Stock is below its 50-day moving average — counter-trend bet.")

  if action.upper() == "BUY":
    bullets.append("Disclosed action is BUY — institutional accumulation signal.")
    horizon = score.get("return_distribution") or {}
    if isinstance(horizon, dict):
      hlabel = horizon.get("sell_horizon_label")
      exp = horizon.get("expected_return_pct")
      if hlabel and exp is not None:
        bullets.append(f"Suggested hold: {hlabel} (est. +{exp * 100:.0f}% — not guaranteed).")
  else:
    risks.append(f"Disclosed action is {action} — may indicate distribution, not accumulation.")

  prob = score.get("calibrated_probability") or score.get("historical_win_rate")
  if score.get("scorer_version", "").startswith("lgbm"):
    summary = f"Model estimates {prob*100:.0f}% chance of positive 3-month return based on backtested patterns."
  elif score.get("scorer_version") == "interim-features-v1" and prob is not None:
    summary = (
      f"Feature-based estimate: {prob*100:.0f}% likelihood of positive 3-month return "
      f"(deal size, cluster, price trend, investor history). ML training pending more historical outcomes."
    )
  elif prob is not None:
    summary = f"Interim score: {prob*100:.0f}% historical win rate for this investor (not yet fully calibrated)."
  else:
    summary = "Interim score based on deal size, investor cluster, and price trend."

  return {
    "summary": summary,
    "bull_case": bullets,
    "risks": risks,
    "market_trend": trend,
    "trend_explanation": explain_trend_narrative(trend, signal.ticker),
    "features": features,
    "disclaimer": "Statistical pattern from public disclosures — not investment advice or a guaranteed prediction.",
  }


def _build_macro_thesis(signal: Signal, score: dict) -> dict:
  from processor.macro_themes import theme_narrative

  raw = signal.raw_json or {}
  trend = compute_trend_features(signal.ticker_normalized)
  dist = score.get("return_distribution") or {}
  theme_block = theme_narrative(raw)
  bullets: list[str] = []
  risks: list[str] = []

  if raw.get("demand_driver"):
    bullets.append(raw["demand_driver"])
  heat = dist.get("theme_heat") or raw.get("theme_heat")
  align = dist.get("alignment_score") or raw.get("alignment_score")
  if heat is not None:
    bullets.append(f"Theme momentum heat: {float(heat) * 100:.0f}/100 (sector proxy trend).")
  if align is not None:
    bullets.append(f"Stock aligned with theme: {float(align) * 100:.0f}/100 vs sector proxy.")
  if trend.get("momentum") == "bullish":
    bullets.append(f"Price momentum positive: +{(trend.get('return_1m') or 0) * 100:.1f}% over ~1 month.")
  elif trend.get("momentum") == "bearish":
    risks.append(f"Stock lagging recently: {(trend.get('return_1m') or 0) * 100:.1f}% over ~1 month.")
  if not trend.get("above_ma50"):
    risks.append("Below 50-day average — theme tailwind but stock not yet in uptrend.")

  exp = dist.get("expected_return_pct")
  hlabel = dist.get("sell_horizon_label")
  if exp is not None and hlabel:
    bullets.append(f"Theme-based hold window: {hlabel} (est. +{exp * 100:.0f}% — not guaranteed).")

  prob = dist.get("calibrated_probability")
  summary = (
    f"Macro theme pick ({raw.get('theme_name', signal.entity)}): "
    f"{prob * 100:.0f}% estimated likelihood of positive return if the demand trend persists."
    if prob is not None
    else f"Macro theme pick based on public demand drivers for {raw.get('theme_name', signal.entity)}."
  )
  risks.append("Theme trades can reverse quickly if macro narrative shifts or sector de-rates.")
  risks.append("No institutional bulk-deal confirmation — this is demand/trend research, not smart-money disclosure.")

  return {
    "summary": summary,
    "bull_case": bullets,
    "risks": risks,
    "market_trend": trend,
    "trend_explanation": explain_trend_narrative(trend, signal.ticker),
    "theme": theme_block,
    "features": {},
    "disclaimer": "Thematic hypothesis from public market data — not investment advice.",
  }
