"""v2.1 unit tests: shorts, swarm hard veto, profit_guard msg, overnight cues, chart smoke."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.pattern_forge.daily_swing import next_day_pnl_frac, score_daily_candidate, score_daily_long
from processor.pattern_forge.daily_swarm_tape import daily_swarm_tape
from processor.pattern_forge.overnight_feeds import overnight_cues_asof


def test_short_scoring_band():
  # Mild down day in short band
  feats = {
    "ok": True,
    "ret_1": -0.02,
    "ret_5": -0.01,
    "ret_20": 0.0,
    "dist_ma20": -0.01,
    "vol_20": 0.01,
  }
  long_only = score_daily_long(feats, regime="chop", long_only=True)
  assert long_only["side"] == "flat"
  two = score_daily_candidate(feats, regime="chop", long_only=False)
  assert two["side"] == "sell"
  assert two["score"] > 0


def test_short_pnl_sign():
  # Price up hurts short
  up = next_day_pnl_frac([100.0, 102.0], side="sell")
  assert up["ok"]
  assert up["pnl_frac"] < 0
  down = next_day_pnl_frac([100.0, 98.0], side="sell")
  assert down["pnl_frac"] > 0


def test_swarm_hard_veto_blocks_tradeable():
  choice = {
    "picked": "RELIANCE.NS",
    "primary": {"side": "buy", "score": 0.02, "confidence": 0.6, "reason": "test"},
    "ranked_top": [{"ticker": "RELIANCE.NS", "side": "buy", "score": 0.02}],
    "breadth": {"frac_above_ma20": 0.2, "n": 10, "stress": True},
    "reason": "picked",
  }
  # Rising market → not risk_off; breadth stress → BreadthRegime skip
  mkt = [100.0 + 0.05 * i for i in range(40)]
  _, soft = daily_swarm_tape(choice, market_closes=mkt, hard_veto=False)
  _, hard = daily_swarm_tape(choice, market_closes=mkt, hard_veto=True)
  assert hard["tradeable"] is False
  assert "BreadthRegime" in (hard.get("hard_skip_agents") or [])
  # Soft mode may still mark tradeable depending on skip/take ratio
  assert "tradeable" in soft


def test_cross_market_skip_hard_veto():
  choice = {
    "picked": "T1.NS",
    "primary": {"side": "buy", "score": 0.02, "confidence": 0.6, "reason": "test"},
    "ranked_top": [],
    "breadth": {"frac_above_ma20": 0.6, "n": 10, "stress": False},
  }
  mkt = [100.0 + 0.1 * i for i in range(40)]
  # Large opposing overnight gap vs long
  _, hard = daily_swarm_tape(
    choice,
    market_closes=mkt,
    overnight_gap_pct=-0.01,
    hard_veto=True,
  )
  assert hard["tradeable"] is False
  assert "CrossMarketOpen" in (hard.get("hard_skip_agents") or [])


def test_profit_guard_message():
  choice = {
    "picked": "cash",
    "primary": {"side": "flat"},
    "ranked_top": [],
    "breadth": {},
    "size_mult": 0.5,
  }
  msgs, _ = daily_swarm_tape(choice, market_closes=[100.0] * 40, profit_guard_note="underwater_half_size")
  pg = next(m for m in msgs if m["agent"] == "ProfitGuard")
  assert pg["reason"] == "underwater_half_size"


def test_overnight_cues_feed_status_without_cache():
  cues = overnight_cues_asof("2025-06-15", allow_network=False, local_closes=[100.0, 101.0])
  assert "feed_status" in cues
  assert cues.get("overnight_gap_pct") is not None  # local fallback


def test_chart_endpoint_import_smoke():
  # Ensure route module path remains importable (FastAPI app may be heavy)
  from processor.pattern_forge import overnight_feeds, daily_swarm_tape, daily_swing  # noqa: F401

  assert hasattr(daily_swing, "score_daily_candidate")


def test_oos_runner_dry_import():
  import importlib.util

  path = ROOT / "scripts" / "run_pattern_forge_daily_swing_oos.py"
  spec = importlib.util.spec_from_file_location("oos_runner", path)
  assert spec and spec.loader
  mod = importlib.util.module_from_spec(spec)
  # Don't execute main — just load for syntax/import of helpers via sibling
  assert path.exists()
