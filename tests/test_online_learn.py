"""Unit tests for sizing, strategies, session, paper broker (no SQLAlchemy models)."""

from datetime import datetime
from zoneinfo import ZoneInfo

from broker.base import OrderRequest
from broker.paper import PaperBroker
from broker.session import in_cash_session, should_flatten_in_day
from broker.sizing import qty_from_notional, size_notional
from processor.strategies import mean_rev_bb, mom_cross, verify_strategy_report


def test_size_notional_scales_with_confidence():
  low, reason = size_notional(prob=0.52, max_notional=10.0, min_prob=0.52, min_size_frac=0.25)
  assert reason is None
  assert low == 2.5
  high, _ = size_notional(prob=0.95, max_notional=10.0, min_prob=0.52, min_size_frac=0.25)
  assert high is not None and high > low
  skip, why = size_notional(prob=0.40, max_notional=10.0, min_prob=0.52)
  assert skip is None
  assert why and "prob_below_min" in why


def test_qty_rejects_expensive_share_without_fractional():
  qty, reason = qty_from_notional(10.0, 50.0, allow_fractional=False)
  assert qty is None
  assert reason == "share_above_sized_notional"
  qty_f, _ = qty_from_notional(10.0, 50.0, allow_fractional=True)
  assert qty_f is not None and qty_f > 0


def test_mom_cross_and_mean_rev_run():
  closes = [100 + i * 0.5 for i in range(40)]
  sig = mom_cross(closes)
  assert sig.strategy_id == "mom_cross"
  assert sig.side in ("buy", "sell", "flat")
  # Non-cross bars must stay flat (no ma_state spam)
  assert sig.reason in ("golden_cross", "death_cross", "no_cross", "insufficient_bars")
  base = [100.0] * 19 + [80.0]
  mr = mean_rev_bb(base)
  assert mr.strategy_id == "mean_rev_bb"


def test_mom_cross_no_continuous_ma_state():
  # Steady uptrend after warm-up without a fresh cross at the last bar → flat
  closes = [100.0 + i for i in range(50)]
  sig = mom_cross(closes)
  assert sig.side == "flat"
  assert sig.reason == "no_cross"


def test_verify_strategy_rejects_thin_sample():
  report = verify_strategy_report(
    strategy_id="mom_cross",
    n_trades=10,
    expectancy=0.01,
    max_dd=0.1,
    oos_ok=True,
  )
  assert report["status"] == "rejected"
  assert "too_few_trades" in report["reasons"]


def test_session_helpers_weekday():
  ist = ZoneInfo("Asia/Kolkata")
  dt = datetime(2026, 8, 25, 10, 0, tzinfo=ist)
  assert in_cash_session(dt) is True
  flat = datetime(2026, 8, 25, 15, 20, tzinfo=ist)
  assert should_flatten_in_day(flat) is True


def test_paper_broker_round_trip():
  b = PaperBroker("US", starting_cash=100.0, currency="USD")
  buy = b.place_order(
    OrderRequest(
      market="US",
      ticker="AAA",
      ticker_normalized="AAA",
      side="buy",
      qty=2,
      limit_price=10.0,
    )
  )
  assert buy.status == "filled"
  assert len(b.list_positions()) == 1
  sell = b.place_order(
    OrderRequest(
      market="US",
      ticker="AAA",
      ticker_normalized="AAA",
      side="sell",
      qty=2,
      limit_price=11.0,
    )
  )
  assert sell.status == "filled"
  assert len(b.list_positions()) == 0
  assert b.cash > 100.0


def test_intraday_orb_and_walk_forward():
  closes = [100.0] * 5 + [101, 102, 103, 104, 105] + [100 + i * 0.2 for i in range(200)]
  from processor.strategies import intraday_orb, walk_forward_backtest

  # Daily misuse refused
  refused = intraday_orb(closes[:12], open_range_bars=5)
  assert refused.reason == "needs_intraday_session_bars"
  session = [100.0] * 5 + [101, 102, 103, 104, 105]
  sig = intraday_orb([], open_range_bars=5, session_bars=session)
  assert sig.strategy_id == "intraday_orb"
  assert sig.side in ("buy", "sell", "flat")
  report = walk_forward_backtest(closes, mom_cross, train_bars=80, test_bars=30)
  assert "status" in report
  assert report["n_trades"] >= 0
  assert "ambition_pass" in report


def test_inr_cap_sizing():
  n, _ = size_notional(prob=1.0, max_notional=1000.0, min_prob=0.52, min_size_frac=0.25)
  assert n == 1000.0
