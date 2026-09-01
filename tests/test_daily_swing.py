"""Daily swing unit tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.pattern_forge.daily_swing import (
  _apply_score_mode,
  choose_daily_candidate,
  next_day_pnl_frac,
  resolve_market_mode,
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


def test_indicator_features():
  n = 260
  closes = [100.0 + i * 0.15 for i in range(n)]
  volumes = [1_000_000.0 + (500_000.0 if i == n - 1 else 0.0) for i in range(n)]
  highs = [c * 1.01 for c in closes]
  lows = [c * 0.99 for c in closes]
  feats = stock_daily_features(closes, volumes=volumes, highs=highs, lows=lows)
  assert feats["ok"]
  assert feats.get("above_ema200") is True
  assert feats.get("above_vwap") is True
  assert float(feats.get("rel_volume") or 0) > 1.0


def test_indicator_gate_blocks_weak_volume():
  n = 260
  base = [100.0 + i * 0.05 for i in range(n - 1)]
  closes = base + [base[-1] * 1.015]  # ~1.5% up day in band
  volumes = [1_000_000.0] * (n - 1) + [100_000.0]
  highs = [c * 1.01 for c in closes]
  lows = [c * 0.99 for c in closes]
  uni = {"WIN.NS": closes}
  ohlcv = {"WIN.NS": {"closes": closes, "volumes": volumes, "highs": highs, "lows": lows}}
  out = choose_daily_candidate(
    uni,
    market_closes=closes,
    long_only=True,
    min_score=0.001,
    require_above_ema200=True,
    require_above_vwap=True,
    min_rel_volume=1.0,
    universe_ohlcv=ohlcv,
  )
  assert out["picked"] == "cash"
  assert any((r.get("indicator_reason") == "low_volume") for r in (out.get("ranked_top") or []))


def test_resolve_market_mode_defense_on_breadth():
  mkt = [100.0 + i * 0.1 for i in range(220)]
  mode, meta = resolve_market_mode(
    regime="trend",
    breadth={"stress": True, "frac_above_ma20": 0.2},
    market_closes=mkt,
    defense_on_breadth_stress=True,
  )
  assert mode == "defense"
  assert "breadth_stress" in meta["reasons"]


def test_apply_score_mode_rs_vs_nifty():
  assert _apply_score_mode(0.01, score_mode="rs_vs_nifty", stock_r1=0.02, market_r1=0.005) == 0.015
  assert _apply_score_mode(0.01, score_mode="raw_r1", stock_r1=0.02, market_r1=0.005) == 0.01


def test_v4_defense_sitout():
  n = 260
  closes = [100.0 + i * 0.08 for i in range(n)]
  uni = {f"T{i}.NS": closes for i in range(6)}
  mode, _ = resolve_market_mode(
    regime="trend",
    breadth={"stress": False, "frac_above_ma20": 0.6},
    market_closes=closes,
    asof="2024-10-15",
    october_defense=True,
  )
  assert mode == "defense"
  out = choose_daily_candidate(
    uni,
    market_closes=closes,
    long_only=True,
    min_score=0.001,
    defense_sitout=True,
    october_defense=True,
    asof="2024-10-15",
    use_breadth_veto=False,
  )
  assert out["picked"] == "cash"
  assert out.get("market_mode") == "defense"


def test_news_edge_skip_on_us_dump():
  from processor.pattern_forge.news_edge import news_edge_message, news_edge_size_mult

  msg = news_edge_message(
    us_ret_pct=-0.015,
    asia_ret_pct=-0.005,
    overnight_gap_pct=-0.004,
    candidate_ret_1=0.01,
    peer_rets=[0.005, 0.004, 0.006],
    primary_side="buy",
  )
  assert msg.vote == "skip"
  assert news_edge_size_mult("skip", soft_mult=0.4) == 0.4


def test_news_edge_take_on_flow():
  from processor.pattern_forge.news_edge import news_edge_message

  msg = news_edge_message(
    us_ret_pct=0.004,
    asia_ret_pct=0.002,
    overnight_gap_pct=0.001,
    candidate_ret_1=0.025,
    peer_rets=[0.005, 0.004, 0.006, 0.003],
    primary_side="buy",
  )
  assert msg.vote in ("take", "annotate")
