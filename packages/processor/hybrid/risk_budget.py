"""Portfolio risk budget — caps leverage before alpha sizing."""

from __future__ import annotations

from processor.session_guard import (
  apply_session_guards,
  daily_loss_halted,
  remaining_daily_risk_pct,
  session_return_pct,
)


def budget_snapshot(equity: float, cash_start: float, max_daily_loss_pct: float) -> dict:
  return {
    "session_return_pct": round(session_return_pct(equity, cash_start), 4),
    "remaining_daily_risk_pct": round(remaining_daily_risk_pct(equity, cash_start, max_daily_loss_pct), 4),
    "halted": daily_loss_halted(equity, cash_start, max_daily_loss_pct),
    "max_daily_loss_pct": max_daily_loss_pct,
  }


def cap_leverage(
  leverage: float,
  *,
  sl_frac: float,
  equity: float,
  cash_start: float,
  max_trade_risk_pct: float | None,
  max_daily_loss_pct: float | None,
) -> tuple[float, list[str]]:
  return apply_session_guards(
    leverage,
    sl_frac=sl_frac,
    equity=equity,
    cash_start=cash_start,
    max_trade_risk_pct=max_trade_risk_pct,
    max_daily_loss_pct=max_daily_loss_pct,
  )
