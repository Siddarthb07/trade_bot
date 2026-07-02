"""Standardized hold / sell timeframe model (Phase 1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def _short_period(days: int) -> str:
  if days < 7:
    return f"{days} days"
  if days < 30:
    weeks = days / 7
    return f"~{weeks:.0f} weeks" if weeks >= 1.5 else "~1 week"
  if days >= 30:
    m = round(days / 30)
    return f"~{m} month" if m == 1 else f"~{m} months"


def timeframe_tier(days: int) -> str:
  if days <= 14:
    return "short"
  if days <= 45:
    return "medium"
  return "long"


def _fmt_date(dt: datetime, short: bool = False) -> str:
  local = dt.astimezone(IST)
  return local.strftime("%d %b") if short else local.strftime("%d %b %Y")


def signal_entry_anchor(disclosed_at: datetime) -> datetime:
  """Hold window starts at 00:00 IST on the disclosure trading day."""
  if disclosed_at.tzinfo is None:
    disclosed_at = disclosed_at.replace(tzinfo=timezone.utc)
  local = disclosed_at.astimezone(IST)
  stable = local.replace(hour=0, minute=0, second=0, microsecond=0)
  return stable.astimezone(timezone.utc)


def disclosed_date_labels(disclosed_at: datetime) -> dict[str, str]:
  """IST calendar labels for raw disclosure timestamp (deal filed)."""
  anchor = signal_entry_anchor(disclosed_at)
  return {
    "disclosed_date_label": _fmt_date(anchor, short=True),
    "disclosed_date_full": _fmt_date(anchor, short=False),
  }


def build_timeframe(
  hold_days: int,
  entry: datetime,
  *,
  window_days: int = 3,
  volatility_annualized: float | None = None,
  now: datetime | None = None,
) -> dict[str, Any]:
  """Build full timeframe block for return_distribution."""
  if hold_days < 1:
    hold_days = 1

  # Phase 4.2: widen exit window for high vol, tighten for low vol + trend
  if volatility_annualized is not None:
    if volatility_annualized > 0.45:
      window_days = max(window_days, 5)
    elif volatility_annualized < 0.20:
      window_days = max(2, window_days - 1)

  entry_utc = entry.astimezone(timezone.utc)
  local_entry = entry.astimezone(IST)
  review_days = max(1, hold_days // 2)
  review_dt = entry_utc + timedelta(days=review_days)
  exit_dt = entry_utc + timedelta(days=hold_days)
  window_start = exit_dt - timedelta(days=window_days)
  window_end = exit_dt + timedelta(days=window_days)

  now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
  local_now = now_utc.astimezone(IST)
  elapsed = max(0, (local_now.date() - local_entry.date()).days)
  remaining = hold_days - elapsed

  if remaining > window_days:
    status = "review_due" if elapsed >= review_days else "active"
  elif remaining >= 0:
    status = "exit_window"
  elif (now_utc.date() - window_end.date()).days <= 0:
    status = "exit_window"
  else:
    status = "overdue"

  if elapsed >= review_days and remaining > window_days:
    status = "review_due"

  if remaining > 1:
    countdown = f"{remaining} days left"
  elif remaining == 1:
    countdown = "1 day left"
  elif remaining == 0:
    countdown = "Exit today"
  elif remaining >= -window_days:
    countdown = "Exit window — review now"
  else:
    countdown = f"Overdue by {abs(remaining)} days"

  short = _short_period(hold_days)
  hold_label_long = f"Hold {hold_days} days · {short}"

  return {
    "hold_days": hold_days,
    "hold_label_short": short,
    "hold_label_long": hold_label_long,
    "entry_date": entry_utc.isoformat(),
    "entry_date_label": _fmt_date(entry_utc, short=True),
    "entry_date_full": _fmt_date(entry_utc, short=False),
    "review_date": review_dt.isoformat(),
    "review_date_label": _fmt_date(review_dt, short=True),
    "exit_date": exit_dt.isoformat(),
    "exit_date_label": _fmt_date(exit_dt, short=True),
    "exit_date_full": _fmt_date(exit_dt, short=False),
    "exit_window_start": window_start.isoformat(),
    "exit_window_end": window_end.isoformat(),
    "exit_window_label": f"{_fmt_date(window_start, short=True)} – {_fmt_date(window_end, short=True)}",
    "timeframe_tier": timeframe_tier(hold_days),
    "days_elapsed": elapsed,
    "days_remaining": remaining,
    "countdown_label": countdown,
    "hold_status": status,
    # legacy fields kept in sync
    "sell_horizon_days": hold_days,
    "sell_horizon_label": hold_label_long,
    "sell_by_hint": f"Sell by {_fmt_date(exit_dt, short=True)} ({hold_days} days)",
    "exit_window_days": window_days,
    "volatility_adjusted": volatility_annualized is not None,
  }


def merge_timeframe_into_distribution(
  distribution: dict[str, Any],
  entry: datetime,
  hold_days: int | None,
) -> dict[str, Any]:
  days = hold_days or distribution.get("hold_days") or distribution.get("sell_horizon_days")
  if days is None:
    return distribution
  tf = build_timeframe(int(days), entry)
  out = {**distribution, **tf}
  return out
