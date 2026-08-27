"""Session sim guardrails — cap tail risk while preserving target-return sizing headroom."""

from __future__ import annotations


def session_return_pct(equity: float, cash_start: float) -> float:
  if cash_start <= 0:
    return 0.0
  return 100.0 * (equity - cash_start) / cash_start


def daily_loss_halted(equity: float, cash_start: float, max_daily_loss_pct: float) -> bool:
  if max_daily_loss_pct <= 0:
    return False
  return session_return_pct(equity, cash_start) <= -abs(max_daily_loss_pct)


def remaining_daily_risk_pct(equity: float, cash_start: float, max_daily_loss_pct: float) -> float:
  """How much further loss (in % of session start equity) is allowed today."""
  if max_daily_loss_pct <= 0:
    return 999.0
  used = -min(0.0, session_return_pct(equity, cash_start))
  return max(0.0, abs(max_daily_loss_pct) - used)


def cap_leverage_for_sl_risk(
  leverage: float,
  sl_frac: float,
  max_trade_risk_pct: float,
) -> float:
  """Cap lev so a full SL hit loses at most max_trade_risk_pct of equity.

  Uses a 0.9 haircut so fees/slippage stay inside the budget.
  """
  if max_trade_risk_pct <= 0 or sl_frac <= 0:
    return leverage
  cap = (max_trade_risk_pct * 0.9) / 100.0 / sl_frac
  return min(leverage, max(1.0, round(cap, 3)))


def cap_leverage_for_remaining_day(
  leverage: float,
  sl_frac: float,
  remaining_daily_risk_pct: float,
) -> float:
  if remaining_daily_risk_pct <= 0 or sl_frac <= 0:
    return 1.0
  cap = (remaining_daily_risk_pct * 0.9) / 100.0 / sl_frac
  return min(leverage, max(1.0, round(cap, 3)))


def apply_session_guards(
  leverage: float,
  *,
  sl_frac: float,
  equity: float,
  cash_start: float,
  max_trade_risk_pct: float | None,
  max_daily_loss_pct: float | None,
) -> tuple[float, list[str]]:
  """Return (capped_leverage, list of guard reasons applied)."""
  notes: list[str] = []
  lev = leverage
  if max_trade_risk_pct and max_trade_risk_pct > 0:
    capped = cap_leverage_for_sl_risk(lev, sl_frac, max_trade_risk_pct)
    if capped < lev - 1e-9:
      notes.append(f"trade_risk_cap:{capped:.2f}x")
      lev = capped
  if max_daily_loss_pct and max_daily_loss_pct > 0:
    rem = remaining_daily_risk_pct(equity, cash_start, max_daily_loss_pct)
    capped = cap_leverage_for_remaining_day(lev, sl_frac, rem)
    if capped < lev - 1e-9:
      notes.append(f"daily_budget_cap:{capped:.2f}x")
      lev = capped
  return lev, notes
