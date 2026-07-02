"""Label readiness for forward-return / win-rate stats."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from processor.timeframe import IST, signal_entry_anchor

MATURITY_WINDOWS = {"1w": 7, "1mo": 30, "3mo": 90, "6mo": 180}


def data_maturity(
  disclosed_at: datetime,
  *,
  forward_returns: dict[str, float | None] | None = None,
  label_window: str = "3mo",
  now: datetime | None = None,
) -> dict[str, Any]:
  """How trustworthy track-record stats are for this pick."""
  now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
  entry = signal_entry_anchor(disclosed_at)
  local_now = now_utc.astimezone(IST)
  local_entry = entry.astimezone(IST)
  age_days = max(0, (local_now.date() - local_entry.date()).days)
  need_days = MATURITY_WINDOWS.get(label_window, 90)
  fr = forward_returns or {}
  ret_3mo = fr.get("3mo") if label_window == "3mo" else fr.get(label_window)
  if ret_3mo is None and label_window == "3mo":
    ret_3mo = fr.get("3mo")

  days_until = max(0, need_days - age_days)
  pct_ready = min(100, int((age_days / need_days) * 100)) if need_days else 100

  if age_days < 3:
    status = "too_new"
    if age_days == 0:
      label = "Deal from today — win rate not meaningful yet"
    elif age_days == 1:
      label = "Deal 1d old — win rate not meaningful yet"
    else:
      label = f"Deal {age_days}d old — win rate not meaningful yet"
    detail = "Investor stats need matured 3-month outcomes after similar bulk buys."
  elif days_until > 0 and ret_3mo is None:
    status = "maturing"
    label = f"{days_until}d until {label_window} outcome is final"
    detail = f"Track record updates automatically after {need_days} days from deal date."
  elif ret_3mo is not None:
    status = "labeled"
    label = f"{label_window} outcome recorded: {ret_3mo * 100:+.1f}%"
    detail = "Win rate includes this deal's realized forward return."
  else:
    status = "partial"
    label = f"{age_days}d elapsed — outcome pending price data"
    detail = "Forward return backfill runs on the worker after ingest."

  return {
    "status": status,
    "label": label,
    "detail": detail,
    "age_days": age_days,
    "days_until_label": days_until if ret_3mo is None else 0,
    "label_window": label_window,
    "readiness_pct": pct_ready,
    "forward_return_3mo": ret_3mo,
  }
