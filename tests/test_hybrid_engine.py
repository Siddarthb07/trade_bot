"""Thorough tests for hybrid engine, benchmarks, chooser, wins, ledger."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.benchmarks import compare_to_benchmarks, load_fixtures, primary_score
from processor.hybrid.chooser import choose_strategy
from processor.hybrid.ledger import (
  LEDGER_PATH,
  STATE_PATH,
  TRADES_PATH,
  load_chooser_state,
  record_session_outcomes,
  update_chooser_from_outcomes,
)
from processor.hybrid.registry import list_strategies, sim_kwargs_for_strategy
from processor.hybrid.wins import WINS_PATH, detect_wins_from_run, list_wins


@pytest.fixture(autouse=True)
def _isolate_hybrid_files(tmp_path, monkeypatch):
  """Redirect hybrid persistence into tmp so tests don't pollute models/."""
  monkeypatch.setattr("processor.hybrid.ledger.LEDGER_PATH", tmp_path / "ledger.jsonl")
  monkeypatch.setattr("processor.hybrid.ledger.STATE_PATH", tmp_path / "state.json")
  monkeypatch.setattr("processor.hybrid.ledger.TRADES_PATH", tmp_path / "trades.jsonl")
  monkeypatch.setattr("processor.hybrid.wins.WINS_PATH", tmp_path / "wins.jsonl")
  yield


def test_fixtures_load_three_windows():
  data = load_fixtures()
  ids = [w["id"] for w in data["windows"]]
  assert "july_chop" in ids
  assert "benchmark_15d" in ids
  ceil = data["windows"][2]["ceiling"]["in_tr10_orwidth_chase5_75x"]
  assert ceil["compound_pct"] > 40


def test_primary_score_penalizes_bad_worst_day():
  good = primary_score(compound_pct=10.0, worst_day_pct=-3.0)
  bad = primary_score(compound_pct=10.0, worst_day_pct=-25.0)
  assert good > bad


def test_compare_benchmark_benchmark_15d():
  cmp = compare_to_benchmarks(
    window_id="benchmark_15d",
    compound_pct=10.0,
    worst_day_pct=-5.0,
    best_day_pct=12.0,
  )
  assert cmp["ceiling"]["compound_pct"] == pytest.approx(45.064)
  assert cmp["gap_to_ceiling_pct"] == pytest.approx(35.064)
  assert cmp["north_star"] == "most_profits"


def test_strategy_registry_lanes():
  product = {s["id"] for s in list_strategies("product")}
  research = {s["id"] for s in list_strategies("research")}
  assert {"orwidth_orb", "adaptive_edge", "copy_bulk_pro"} <= product
  assert {"pattern_candle", "pattern_analog", "orb_two_sided"} <= product
  assert "orwidth_orb" in research
  assert "pattern_candle" in research
  all_reg = {s["id"] for s in list_strategies("product", sim_ready_only=False)}
  assert "mom_cross" in all_reg


def test_pattern_forge_sim_kwargs():
  kw = sim_kwargs_for_strategy("pattern_candle", "product")
  assert kw.get("fo_shorts_only") is True
  assert kw.get("no_ruin") is True
  assert kw.get("sleeve_frac") == 0.25
  assert kw.get("max_daily_loss_pct") == 4.0


def test_sim_kwargs_product_has_guards():
  kw = sim_kwargs_for_strategy("orwidth_orb", "product")
  assert kw.get("max_daily_loss_pct")
  assert kw.get("intraday_stop_with_session_end") is True
  research = sim_kwargs_for_strategy("orwidth_orb", "research")
  assert "max_daily_loss_pct" not in research or research.get("max_daily_loss_pct") is None


def test_chooser_research_defaults_orwidth():
  c = choose_strategy(lane="research", regime="chop")
  assert c["picked"] == "orwidth_orb"
  assert c["reason"] == "research_orwidth_default"


def test_chooser_cold_start_orwidth():
  c = choose_strategy(lane="product", regime="chop", chooser_state={"strategies": {}})
  assert c["picked"] == "orwidth_orb"
  assert c["reason"] == "cold_start_orwidth"


def test_chooser_forced():
  c = choose_strategy(lane="product", force_strategy="adaptive_edge")
  assert c["picked"] == "adaptive_edge"
  assert c["reason"] == "forced"


def test_chooser_softmax_uses_expectancy():
  state = {
    "strategies": {
      "orwidth_orb": {"n": 30, "expectancy": -2.0},
      "adaptive_edge": {"n": 30, "expectancy": 1.5},
    }
  }
  c = choose_strategy(lane="product", regime="chop", chooser_state=state)
  assert c["picked"] == "adaptive_edge"
  assert sum(c["weights"].values()) == pytest.approx(1.0, abs=1e-4)


def test_ledger_updates_chooser_and_trades(tmp_path):
  state = record_session_outcomes(
    asof="2026-08-26",
    lane="product",
    strategy_id="orwidth_orb",
    regime="trend",
    session_return_pct=2.5,
    trades=[
      {
        "trade_id": "t-1",
        "ticker": "RELIANCE.NS",
        "pnl_pct": 2.5,
        "pnl": 250,
        "exit_reason": "session_close",
        "entry_price": 100,
        "exit_price": 102.5,
        "entry_date": "2026-08-26",
        "exit_date": "2026-08-26",
        "leverage": 5.0,
      }
    ],
    chooser={"picked": "orwidth_orb"},
  )
  assert state["strategies"]["orwidth_orb"]["n"] >= 1
  assert load_chooser_state()["strategies"]["orwidth_orb"]["expectancy"] == pytest.approx(2.5)


def test_wins_lane_labels_and_research_disclaimer():
  wins = detect_wins_from_run(
    lane="research",
    asof="2026-08-26",
    window_id="benchmark_15d",
    compound_pct=12.0,
    worst_day_pct=-4.0,
    best_day_pct=12.0,
    primary_score=8.0,
    prev_best_primary=1.0,
    prev_equity_high=10000,
    final_capital=11200,
    start_capital=10000,
    beats_ceiling=False,
    gap_to_ceiling_pct=30,
    trade_ids=["t-1"],
  )
  assert wins
  listed = list_wins()
  assert listed
  assert "not live-eligible" in (listed[0].get("disclaimer") or "").lower() or listed[0]["lane"] == "research"


def test_wins_beat_ceiling_product():
  wins = detect_wins_from_run(
    lane="product",
    asof=None,
    window_id="benchmark_15d",
    compound_pct=50.0,
    worst_day_pct=-5.0,
    best_day_pct=20.0,
    primary_score=40.0,
    prev_best_primary=None,
    prev_equity_high=None,
    final_capital=15000,
    start_capital=10000,
    beats_ceiling=True,
    gap_to_ceiling_pct=-5,
    trade_ids=[],
  )
  kinds = {w["kind"] for w in wins}
  assert "beat_ceiling" in kinds
