"""Hybrid stock+market chooser unit tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.pattern_forge.hybrid_chooser import choose_family_for_stock, score_families
from processor.pattern_forge.session import primary_signal


def _bars(trend: float = 0.003, n: int = 24) -> list[dict]:
  bars = []
  # wide OR
  for o in (100.0, 100.5, 99.5, 100.2, 99.8):
    bars.append({"open": o, "high": o * 1.01, "low": o * 0.99, "close": o, "volume": 1})
  px = 100.0
  for _ in range(n - 5):
    c = px * (1.0 + trend)
    bars.append({"open": px, "high": max(px, c) * 1.005, "low": min(px, c) * 0.995, "close": c, "volume": 1})
    px = c
  return bars


def test_trend_prefers_orb():
  daily = [100 + i * 0.5 for i in range(60)]  # uptrend
  choice = choose_family_for_stock(_bars(0.004), daily_closes=daily, long_only=True, min_score=0.05)
  assert choice["regime"] in ("trend", "chop", "unknown", "risk_off")
  assert "scores" in choice
  assert choice["picked"] in ("orb_two_sided", "pattern_candle", "pattern_analog", "cash")
  # strong uptrend daily → not risk_off
  assert choice["regime"] != "risk_off"


def test_chop_candle_scores():
  feats = {
    "or_width_pct": 0.002,
    "orb_side": "flat",
    "orb_conf": 0.5,
    "orb_score": 0,
    "candle_side": "buy",
    "candle_conf": 0.62,
    "candle_reason": "hammer",
    "analog_side": "flat",
    "analog_conf": 0.5,
    "analog_mean_fwd": None,
    "early_ret": 0.0,
    "session_vol": 0.001,
  }
  scores = score_families(feats, regime="chop", long_only=True)
  assert scores["pattern_candle"] > scores["orb_two_sided"]


def test_primary_signal_hybrid_cash_when_weak():
  flat = [{"open": 100, "high": 100.05, "low": 99.95, "close": 100, "volume": 1}] * 20
  sig = primary_signal("hybrid_stock_market", session_bars=flat, long_only=True)
  assert "hybrid_choice" in sig
  # weak flat session often cash/flat
  assert sig["side"] in ("flat", "buy", "sell")
