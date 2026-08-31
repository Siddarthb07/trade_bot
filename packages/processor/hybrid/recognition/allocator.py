"""L4 allocator overlays — may only reduce size vs session guards."""

from __future__ import annotations

from processor.session_guard import apply_session_guards


def vol_target_mult(*, realized_vol: float | None, target_vol: float = 0.01) -> float:
  if realized_vol is None or realized_vol <= 0:
    return 1.0
  return float(min(1.5, max(0.25, target_vol / realized_vol)))


def fractional_kelly(*, p_take: float | None, payoff_odds: float = 1.5, fraction: float = 0.25) -> float:
  """f* = p - (1-p)/b, then take fraction of Kelly; floor at 0."""
  if p_take is None:
    return 0.0
  b = max(payoff_odds, 1e-6)
  f = p_take - (1.0 - p_take) / b
  return float(max(0.0, min(1.0, f * fraction)))


def apply_size_overlays(
  leverage: float,
  *,
  sl_frac: float,
  equity: float,
  cash_start: float,
  max_trade_risk_pct: float | None,
  max_daily_loss_pct: float | None,
  size_mult: float,
) -> tuple[float, list[str]]:
  """Multiply proposed lev by size_mult (≤1 for skip), then session_guard caps."""
  notes: list[str] = []
  lev = max(0.0, leverage * max(0.0, min(1.0, size_mult)))
  if size_mult < 1.0 - 1e-12:
    notes.append(f"recognition_size_mult:{size_mult:.3f}")
  if lev <= 0:
    return 0.0, notes + ["cash"]
  capped, guard_notes = apply_session_guards(
    lev,
    sl_frac=sl_frac,
    equity=equity,
    cash_start=cash_start,
    max_trade_risk_pct=max_trade_risk_pct,
    max_daily_loss_pct=max_daily_loss_pct,
  )
  return capped, notes + guard_notes
