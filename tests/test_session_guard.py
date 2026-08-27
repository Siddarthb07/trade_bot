"""Unit tests for session risk guardrails."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.session_guard import (
  apply_session_guards,
  cap_leverage_for_sl_risk,
  daily_loss_halted,
  remaining_daily_risk_pct,
)


def test_daily_loss_halt_triggers_at_floor():
  assert daily_loss_halted(9650.0, 10_000.0, 3.5) is True
  assert daily_loss_halted(9700.0, 10_000.0, 3.5) is False


def test_trade_risk_caps_leverage():
  # 5% equity risk * 0.9 / 1% SL => max 4.5x
  assert cap_leverage_for_sl_risk(25.0, 0.01, 5.0) == 4.5
  assert cap_leverage_for_sl_risk(3.0, 0.01, 5.0) == 3.0


def test_apply_session_guards_stacks_daily_budget():
  lev, notes = apply_session_guards(
    20.0,
    sl_frac=0.01,
    equity=9800.0,
    cash_start=10_000.0,
    max_trade_risk_pct=5.0,
    max_daily_loss_pct=5.0,
  )
  # already down 2%, remaining daily risk 3% => lev <= 3x
  assert lev <= 3.0 + 1e-9
  assert remaining_daily_risk_pct(9800.0, 10_000.0, 5.0) == 3.0
  assert notes
