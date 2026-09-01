"""Unit tests for CrossMarketOpen + CrossSectionSimilarity agents."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.hybrid.recognition.swarm.cross_market import (
  cross_market_open_message,
  cross_section_similarity_message,
  similarity_size_mult,
)
from processor.pattern_forge.daily_swing import filter_uncorrelated_picks
from processor.hybrid.recognition.stack import recognize_session


def test_cross_market_cold_start():
  m = cross_market_open_message()
  assert m.agent == "CrossMarketOpen"
  assert m.status == "cold_start"


def test_cross_market_agrees_long():
  m = cross_market_open_message(overnight_gap_pct=0.006, us_ret_pct=0.004, primary_side="buy")
  assert m.vote == "take"


def test_cross_market_opposes():
  m = cross_market_open_message(overnight_gap_pct=-0.008, primary_side="buy")
  assert m.vote == "skip"


def test_cross_section_low_dispersion_skip():
  peers = [0.001] * 10
  m = cross_section_similarity_message(candidate_ret_1=0.0012, peer_rets=peers, primary_side="buy")
  assert m.vote == "skip"


def test_cross_section_top_quartile_take():
  peers = [i * 0.002 for i in range(-5, 6)]  # spread
  m = cross_section_similarity_message(candidate_ret_1=0.012, peer_rets=peers, primary_side="buy")
  assert m.vote == "take"


def test_recognize_session_includes_new_agents():
  bars = [
    {"open": 100, "high": 101, "low": 99.5, "close": 100.5, "volume": 1},
  ] * 24
  snap = recognize_session(
    asof="2025-06-01",
    bars=bars,
    daily_closes=[100 + i * 0.1 for i in range(60)],
    primary_side="buy",
    overnight_gap_pct=0.005,
    peer_rets=[0.01 * (i - 5) for i in range(12)],
    candidate_ret_1=0.02,
  )
  names = {m.agent for m in snap.messages}
  assert "CrossMarketOpen" in names
  assert "CrossSectionSimilarity" in names


def test_similarity_size_mult_crowded_skip():
  peers = [0.001] * 12
  mult, reason, iqr = similarity_size_mult(peer_rets=peers)
  assert mult == 0.0
  assert "skip" in reason
  assert iqr is not None and iqr < 0.0025


def test_similarity_size_mult_ok():
  peers = [i * 0.003 for i in range(-6, 7)]
  mult, reason, _ = similarity_size_mult(peer_rets=peers)
  assert mult == 1.0
  assert reason == "similarity_ok"


def test_filter_uncorrelated_picks():
  uni = {
    "A.NS": [100.0 + i * 0.5 + (0.1 if i % 2 else -0.1) for i in range(40)],
    "B.NS": [200.0 + (10.0 if i % 5 == 0 else -2.0) for i in range(40)],
    "C.NS": [100.0 + i * 0.5 + (0.1 if i % 2 else -0.1) for i in range(40)],
  }
  eligible = [
    {"ticker": "A.NS", "score": 0.02, "side": "buy"},
    {"ticker": "B.NS", "score": 0.018, "side": "buy"},
    {"ticker": "C.NS", "score": 0.017, "side": "buy"},
  ]
  picks = filter_uncorrelated_picks(eligible, uni, top_k=3, max_pairwise_corr=0.85)
  tickers = {p["ticker"] for p in picks}
  assert len(picks) >= 2
  assert "A.NS" in tickers
  assert "C.NS" not in tickers or "A.NS" not in tickers  # A and C are identical series
