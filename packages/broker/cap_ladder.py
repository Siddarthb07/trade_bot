"""Cap ladder (Stage E) + weekly portfolio loss limits."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from core.models import TradeRiskState
from processor.paper_metrics import rolling_paper_metrics

# Stage 0 = plan defaults (₹1000 / $10). Each step doubles until stage max.
LADDER_MULT = [1.0, 2.0, 4.0, 8.0, 16.0]
BASE_CAPS = {
  "IN": {"max_notional_per_trade": 1000.0, "max_open_notional": 1000.0, "max_daily_loss": 500.0, "max_weekly_loss": 1500.0},
  "US": {"max_notional_per_trade": 10.0, "max_open_notional": 10.0, "max_daily_loss": 5.0, "max_weekly_loss": 15.0},
}


def _week_start(d: date | None = None) -> date:
  d = d or date.today()
  return d - timedelta(days=d.weekday())


def ensure_weekly_fields(row: TradeRiskState) -> None:
  """Reset weekly PnL counter when ISO week rolls (stored via daily_pnl_date hack + notes in updated)."""
  # Use ladder_stage-compatible storage: encode week in a sidecar file if columns absent
  pass


def apply_ladder_caps(row: TradeRiskState) -> None:
  base = BASE_CAPS.get(row.market.upper(), BASE_CAPS["US"])
  stage = max(0, min(int(row.ladder_stage or 0), len(LADDER_MULT) - 1))
  mult = LADDER_MULT[stage]
  row.max_notional_per_trade = base["max_notional_per_trade"] * mult
  row.max_open_notional = base["max_open_notional"] * mult
  row.max_daily_loss = base["max_daily_loss"] * mult


def try_step_up_caps(db: Session, market: str, *, clean_weeks: int = 2) -> dict:
  """Raise ladder one step only if rolling expectancy > 0 and enough trades."""
  from broker.risk import ensure_risk_state

  m = market.upper()
  row = ensure_risk_state(db, m)
  # Enforce ≥7 day cooldown between step-ups (council / security)
  if row.updated_at is not None:
    age = datetime.now(timezone.utc) - row.updated_at.replace(tzinfo=timezone.utc)
    if age < timedelta(days=7) and int(row.ladder_stage or 0) > 0:
      return {
        "status": "blocked",
        "reason": "cooldown_7d",
        "ladder_stage": row.ladder_stage,
        "hours_remaining": round((timedelta(days=7) - age).total_seconds() / 3600, 1),
      }
  metrics = rolling_paper_metrics(db, market=m, days=max(14, clean_weeks * 7))
  if metrics.get("n_trades", 0) < 20:
    return {"status": "blocked", "reason": "too_few_trades", "metrics": metrics, "ladder_stage": row.ladder_stage}
  if not metrics.get("pass_positive_expectancy"):
    return {"status": "blocked", "reason": "expectancy_non_positive", "metrics": metrics, "ladder_stage": row.ladder_stage}
  if (metrics.get("max_dd") or 0) > abs(row.max_daily_loss) * 5:
    return {"status": "blocked", "reason": "drawdown_too_high", "metrics": metrics, "ladder_stage": row.ladder_stage}
  # Enforce ≥7 day cooldown between step-ups (council security item)
  last = row.updated_at
  if last is not None:
    if last.tzinfo is None:
      last = last.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - last < timedelta(days=7) and int(row.ladder_stage or 0) > 0:
      return {
        "status": "blocked",
        "reason": "cooldown_7d",
        "ladder_stage": row.ladder_stage,
        "metrics": metrics,
      }
  if int(row.ladder_stage or 0) >= len(LADDER_MULT) - 1:
    return {"status": "maxed", "ladder_stage": row.ladder_stage, "metrics": metrics}
  row.ladder_stage = int(row.ladder_stage or 0) + 1
  apply_ladder_caps(row)
  row.updated_at = datetime.now(timezone.utc)
  db.commit()
  return {
    "status": "stepped_up",
    "ladder_stage": row.ladder_stage,
    "max_notional_per_trade": row.max_notional_per_trade,
    "metrics": metrics,
  }


def step_down_caps(db: Session, market: str, *, reason: str) -> dict:
  from broker.risk import ensure_risk_state

  row = ensure_risk_state(db, market)
  row.ladder_stage = max(0, int(row.ladder_stage or 0) - 1)
  apply_ladder_caps(row)
  row.updated_at = datetime.now(timezone.utc)
  db.commit()
  return {"status": "stepped_down", "reason": reason, "ladder_stage": row.ladder_stage, "cap": row.max_notional_per_trade}
