"""Hard no-ruin controller — never trade the book to zero.

Fail closed: any breach forces cash / blocks new risk.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class NoRuinConfig:
  """Defaults match Pattern Method Hunt plan locks."""

  min_frac_of_peak: float = 0.40
  min_frac_of_start: float = 0.50
  max_sleeve_frac: float = 0.50
  default_sleeve_frac: float = 0.25
  max_daily_loss_pct: float = 4.0
  max_trade_risk_pct: float = 3.0
  max_leverage: float = 5.0


@dataclass(frozen=True)
class NoRuinState:
  starting_capital: float
  peak_equity: float
  equity: float
  halted: bool
  reason: str
  sleeve_frac: float
  risk_budget: float


def update_peak(peak: float, equity: float) -> float:
  return max(float(peak), float(equity))


def check_equity_floor(
  *,
  equity: float,
  starting_capital: float,
  peak_equity: float,
  cfg: NoRuinConfig | None = None,
) -> tuple[bool, str]:
  """Return (ok_to_risk, reason). ok_to_risk False => force cash."""
  cfg = cfg or NoRuinConfig()
  eq = float(equity)
  start = max(float(starting_capital), 1e-9)
  peak = max(float(peak_equity), start, eq)
  if eq <= start * cfg.min_frac_of_start:
    return False, f"floor_vs_start:{eq:.2f}<={start * cfg.min_frac_of_start:.2f}"
  if eq <= peak * cfg.min_frac_of_peak:
    return False, f"floor_vs_peak:{eq:.2f}<={peak * cfg.min_frac_of_peak:.2f}"
  return True, "ok"


def clamp_sleeve(sleeve_frac: float | None, cfg: NoRuinConfig | None = None) -> float:
  cfg = cfg or NoRuinConfig()
  s = cfg.default_sleeve_frac if sleeve_frac is None else float(sleeve_frac)
  return max(0.05, min(cfg.max_sleeve_frac, s))


def risk_budget(
  *,
  equity: float,
  starting_capital: float,
  peak_equity: float,
  sleeve_frac: float | None = None,
  cfg: NoRuinConfig | None = None,
) -> NoRuinState:
  cfg = cfg or NoRuinConfig()
  peak = update_peak(peak_equity, equity)
  ok, reason = check_equity_floor(
    equity=equity,
    starting_capital=starting_capital,
    peak_equity=peak,
    cfg=cfg,
  )
  sleeve = clamp_sleeve(sleeve_frac, cfg)
  if not ok:
    return NoRuinState(
      starting_capital=float(starting_capital),
      peak_equity=peak,
      equity=float(equity),
      halted=True,
      reason=reason,
      sleeve_frac=sleeve,
      risk_budget=0.0,
    )
  budget = float(equity) * sleeve
  return NoRuinState(
    starting_capital=float(starting_capital),
    peak_equity=peak,
    equity=float(equity),
    halted=False,
    reason=reason,
    sleeve_frac=sleeve,
    risk_budget=round(budget, 2),
  )


def apply_no_ruin_to_leverage(
  leverage: float,
  *,
  state: NoRuinState,
  cfg: NoRuinConfig | None = None,
) -> tuple[float, list[str]]:
  """Cap leverage; zero if halted."""
  cfg = cfg or NoRuinConfig()
  notes: list[str] = []
  if state.halted or state.risk_budget <= 0:
    return 0.0, [f"no_ruin_halt:{state.reason}"]
  lev = min(float(leverage), cfg.max_leverage)
  if lev < float(leverage):
    notes.append(f"no_ruin_max_lev:{lev:.2f}x")
  return lev, notes


def state_dict(state: NoRuinState) -> dict[str, Any]:
  return asdict(state)
