"""Daily swing unit tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.pattern_forge.daily_swing import (
  choose_daily_candidate,
  next_day_pnl_frac,
  score_daily_long,
  stock_daily_features,
)


def test_features_and_score_trend():
  closes = [100 + i * 0.4 for i in range(60)]
  feats = stock_daily_features(closes)
  assert feats["ok"]
  sig = score_daily_long(feats, regime="trend", long_only=True)
  assert sig["side"] in ("buy", "flat")
  assert "score" in sig


def test_choose_cash_when_weak():
  flat = {f"T{i}.NS": [100.0] * 40 for i in range(5)}
  out = choose_daily_candidate(flat, market_closes=[100.0] * 40, long_only=True, min_score=0.5)
  assert out["picked"] == "cash"


def test_breadth_stress_veto():
  # All names in downtrend → frac_above_ma20 ~ 0 → cash sit-out
  uni = {f"T{i}.NS": [200.0 - j * 0.5 for j in range(40)] for i in range(8)}
  out = choose_daily_candidate(
    uni, market_closes=[100.0 + i * 0.1 for i in range(40)], long_only=True, use_breadth_veto=True
  )
  assert out["picked"] == "cash"
  assert out.get("stress_veto") is True


def test_top_k_picks():
  # Build one clear momentum name + flat peers (breadth healthy)
  uni = {f"T{i}.NS": [100.0 + (0.3 if i < 3 else 0.0) * j for j in range(40)] for i in range(6)}
  out = choose_daily_candidate(
    uni,
    market_closes=[100.0 + 0.2 * i for i in range(40)],
    long_only=True,
    top_k=3,
    use_breadth_veto=False,
    min_score=0.001,
  )
  if out["picked"] != "cash":
    assert len(out.get("picks") or []) <= 3


def test_next_day_pnl():
  out = next_day_pnl_frac([100.0, 101.0], side="buy")
  assert out["ok"]
  assert abs(out["pnl_frac"] - 0.01) < 1e-9
