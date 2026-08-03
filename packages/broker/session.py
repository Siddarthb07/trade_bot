"""Session arming and market-window helpers (IST-centric)."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
ET = ZoneInfo("America/New_York")


def now_ist() -> datetime:
  return datetime.now(IST)


def in_cash_session(dt: datetime | None = None) -> bool:
  """NSE cash approx 09:15–15:30 IST."""
  d = dt or now_ist()
  if d.tzinfo is None:
    d = d.replace(tzinfo=IST)
  else:
    d = d.astimezone(IST)
  if d.weekday() >= 5:
    return False
  t = d.time()
  return time(9, 15) <= t <= time(15, 30)


def should_flatten_in_day(dt: datetime | None = None) -> bool:
  d = (dt or now_ist()).astimezone(IST)
  if d.weekday() >= 5:
    return False
  return d.time() >= time(15, 15)


def in_us_regular_session(dt: datetime | None = None) -> bool:
  d = dt or datetime.now(ET)
  if d.tzinfo is None:
    d = d.replace(tzinfo=ET)
  else:
    d = d.astimezone(ET)
  if d.weekday() >= 5:
    return False
  t = d.time()
  return time(9, 30) <= t <= time(16, 0)


def should_flatten_us_day(dt: datetime | None = None) -> bool:
  d = (dt or datetime.now(ET)).astimezone(ET)
  if d.weekday() >= 5:
    return False
  return d.time() >= time(15, 45)


def session_snapshot() -> dict:
  ist = now_ist()
  return {
    "ist_now": ist.isoformat(),
    "in_cash_open": in_cash_session(ist),
    "should_flatten_in_day": should_flatten_in_day(ist),
    "us_regular_open": in_us_regular_session(),
    "should_flatten_us_day": should_flatten_us_day(),
  }
