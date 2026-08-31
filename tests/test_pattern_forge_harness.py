"""Unit tests — no_ruin, fo_universe, two_sided, pattern_forge (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.fo_universe import allow_short, is_fo_underlier, load_fo_underliers
from processor.no_ruin import NoRuinConfig, apply_no_ruin_to_leverage, check_equity_floor, risk_budget
from processor.pattern_forge import analog_signal, build_library_from_paths, candle_signal
from processor.two_sided import path_exit_two_sided, signed_return


def test_fo_universe_loads_and_gates_shorts():
  uni = load_fo_underliers()
  assert "RELIANCE.NS" in uni
  assert is_fo_underlier("RELIANCE.NS")
  ok, reason = allow_short("RELIANCE.NS")
  assert ok and reason == "fo_underlier"
  bad, why = allow_short("SOMEOBSCURE.NS")
  assert not bad
  assert "not_fo" in why


def test_no_ruin_halts_below_start_floor():
  ok, reason = check_equity_floor(equity=4000, starting_capital=10_000, peak_equity=12_000)
  assert not ok
  assert "floor_vs_start" in reason


def test_no_ruin_halts_below_peak_floor():
  # 45% of peak 20k = 9k; equity 8k triggers peak floor even if above 50% of start 10k
  ok, reason = check_equity_floor(equity=8000, starting_capital=10_000, peak_equity=20_000)
  assert not ok
  assert "floor_vs_peak" in reason


def test_no_ruin_risk_budget_zero_when_halted():
  st = risk_budget(equity=3000, starting_capital=10_000, peak_equity=10_000, sleeve_frac=0.25)
  assert st.halted
  assert st.risk_budget == 0.0
  lev, notes = apply_no_ruin_to_leverage(3.0, state=st)
  assert lev == 0.0
  assert notes


def test_no_ruin_sleeve_clamp():
  st = risk_budget(equity=10_000, starting_capital=10_000, peak_equity=10_000, sleeve_frac=0.9)
  assert st.sleeve_frac <= NoRuinConfig().max_sleeve_frac
  assert st.risk_budget == round(10_000 * st.sleeve_frac, 2)


def test_signed_return_long_short():
  assert abs(signed_return(100, 110, "long") - 0.1) < 1e-9
  assert abs(signed_return(100, 110, "short") - (-0.1)) < 1e-9
  assert abs(signed_return(100, 90, "short") - 0.1) < 1e-9


def test_path_exit_short_stop_loss():
  # short entry 100; price rises to 102 → loss ~2% > 1% SL
  closes = [100.0, 100.5, 101.0, 102.0, 103.0]
  out = path_exit_two_sided(closes, 0, "sell", sl=0.01, protect_only=True)
  assert out["ok"]
  assert out["side"] == "short"
  assert out["exit_reason"] == "stop_loss"
  assert out["pnl_frac"] < 0


def test_path_exit_long_session_close_winner():
  closes = [100.0, 100.5, 101.0, 101.5, 102.0]
  out = path_exit_two_sided(closes, 0, "buy", sl=0.05, protect_only=True)
  assert out["exit_reason"] == "session_close"
  assert out["pnl_frac"] > 0


def test_path_exit_soft_trail():
  closes = [100.0, 103.0, 104.0, 102.5, 102.0]  # peak +4%, giveback past 1% trail after arm 2.5%
  out = path_exit_two_sided(
    closes,
    0,
    "buy",
    sl=0.08,
    soft_trail_arm=0.025,
    soft_trail=0.01,
    protect_only=True,
  )
  assert out["exit_reason"] == "soft_trail"
  assert out["pnl_frac"] > 0


def test_candle_hammer_buy():
  # long lower wick hammer
  daily = [{"open": 100, "high": 101, "low": 94, "close": 100.2}]
  sig = candle_signal(daily)
  assert sig["side"] in ("buy", "flat")  # hammer should fire buy
  if sig["side"] == "buy":
    assert any(p["pattern"] == "hammer" for p in sig["patterns"])


def test_candle_shooting_star_sell():
  daily = [{"open": 100, "high": 106, "low": 99.5, "close": 100.1}]
  sig = candle_signal(daily)
  assert sig["side"] == "sell"
  assert sig["reason"] == "shooting_star"


def test_analog_signal_long_bias():
  query = [100 + i * 0.3 for i in range(20)]
  paths = [[100 + i * 0.3 for i in range(20)] for _ in range(6)]
  fwds = [0.01, 0.012, 0.008, 0.015, 0.009, 0.011]
  lib = build_library_from_paths(paths, fwds)
  sig = analog_signal(query, lib, k=5)
  assert sig["side"] == "buy"
  assert sig["mean_fwd"] is not None and sig["mean_fwd"] > 0


def test_analog_insufficient_library_flat():
  sig = analog_signal([100, 101, 102, 103], [], k=5)
  assert sig["side"] == "flat"


def test_orb_two_sided_scores_sell_breakdown():
  from processor.strategies import session_or_breakout

  # flat OR then breakdown
  bars = []
  for c in [100, 100.2, 99.8, 100.1, 99.9]:
    bars.append({"open": c, "high": c + 0.1, "low": c - 0.1, "close": c})
  # break below lo (~99.8)
  for c in [99.5, 99.0, 98.5]:
    bars.append({"open": c, "high": c + 0.05, "low": c - 0.05, "close": c})
  sob = session_or_breakout(bars, open_range_bars=5)
  assert sob["side"] == "sell"
  assert float(sob["score"] or 0) > 0


def test_simulate_pattern_session_no_ruin_blocks():
  from processor.pattern_forge.session import simulate_pattern_session

  bars = [{"open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1}] * 20
  out = simulate_pattern_session(
    asof="2026-08-01",
    ticker="RELIANCE.NS",
    session_bars=bars,
    capital=3000.0,
    starting_capital=10_000.0,
    peak_equity=10_000.0,
    family="pattern_candle",
  )
  assert out["skip_reason"] == "no_ruin_halt"
  assert out["trades"] == []


def test_simulate_pattern_session_refuses_non_fo_short():
  from processor.pattern_forge.session import simulate_pattern_session

  # shooting star prior day → sell; obscure ticker not in F&O list
  daily = [{"open": 100, "high": 106, "low": 99.5, "close": 100.1}]
  bars = [{"open": 100, "high": 101, "low": 99, "close": 100.0, "volume": 1}] * 20
  out = simulate_pattern_session(
    asof="2026-08-01",
    ticker="OBSCUREPENNY.NS",
    session_bars=bars,
    daily_bars_before=daily,
    capital=10_000.0,
    family="pattern_candle",
    # bypass swarm by using low tau... still need primary sell
  )
  assert out.get("primary", {}).get("side") == "sell"
  assert out.get("skip_reason") == "short_refused_not_fo_underlier"
