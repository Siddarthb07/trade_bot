"""Modeled round-trip trading costs (spread + slippage + fees) for IN / US paper sims."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
  market: str
  # Half-spread + slippage applied once per side (entry or exit), as fraction of notional
  side_friction_bps: float
  # Extra round-trip fee fraction of notional (brokerage / STT / exchange / SEC-ish)
  round_trip_fee_bps: float

  @property
  def round_trip_fraction(self) -> float:
    """Total cost as fraction of entry notional for a round trip."""
    return (2.0 * self.side_friction_bps + self.round_trip_fee_bps) / 10_000.0

  def fee_on_notional(self, notional: float, *, sides: int = 1) -> float:
    friction = abs(notional) * (self.side_friction_bps / 10_000.0) * sides
    # Attribute round-trip fee proportionally to sides (1 = half RT, 2 = full)
    fee = abs(notional) * (self.round_trip_fee_bps / 10_000.0) * (sides / 2.0)
    return round(friction + fee, 6)


# Conservative retail-ish defaults (not broker quotes)
IN_COST = CostModel(market="IN", side_friction_bps=5.0, round_trip_fee_bps=20.0)  # ~30 bps RT
US_COST = CostModel(market="US", side_friction_bps=3.0, round_trip_fee_bps=4.0)  # ~10 bps RT


def cost_model_for(market: str) -> CostModel:
  return IN_COST if market.upper() == "IN" else US_COST


def cost_fraction(market: str) -> float:
  """Alias used by path_outcome / adaptive sims (round-trip as single subtract)."""
  return cost_model_for(market).round_trip_fraction
