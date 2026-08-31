"""Unit tests for CrossMarketOpen + CrossSectionSimilarity agents."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.hybrid.recognition.swarm.cross_market import (
  cross_market_open_message,
  cross_section_similarity_message,
)
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
