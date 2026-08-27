"""Unit tests for Stage A–B readiness helpers."""

from __future__ import annotations

from processor.costs import cost_fraction, cost_model_for
from processor.profile_validate import validate_profiles


def test_cost_models_positive():
  assert cost_fraction("IN") > 0
  assert cost_fraction("US") > 0
  assert cost_model_for("IN").round_trip_fraction > cost_model_for("US").round_trip_fraction


def test_validate_profiles_min_oos():
  data = {
    "eligible_tickers": ["QQQ"],
    "profiles": {
      "QQQ": {
        "ambition_pass": True,
        "regime": "trend",
        "holdout_oos": {"n_trades": 7, "hit_rate_pct": 85.7, "expectancy": 0.01},
      }
    },
  }
  errs = validate_profiles(data)
  assert any("n_trades" in e for e in errs)


def test_validate_profiles_ok():
  data = {
    "eligible_tickers": ["QQQ"],
    "profiles": {
      "QQQ": {
        "ambition_pass": True,
        "regime": "trend",
        "holdout_oos": {"n_trades": 32, "hit_rate_pct": 87.5, "expectancy": 0.004},
      }
    },
  }
  assert validate_profiles(data) == []


def test_ablation_peer_gate_runs():
  # Synthetic trending series — enough bars for warm+holdout
  closes = [100.0]
  for i in range(250):
    closes.append(closes[-1] * (1.002 if i % 7 else 0.995))
  from processor.adaptive_edge import ablation_peer_gate

  rep = ablation_peer_gate(closes, tp=0.01, sl=0.02, horizon=5)
  assert "gated" in rep and "ungated" in rep
  assert "demote_gate_claim" in rep
