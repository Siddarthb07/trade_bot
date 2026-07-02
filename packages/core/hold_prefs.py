"""Effective hold/exit preferences (DB overrides with env defaults)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from core.config import get_settings
from core.models import HoldPrefs

settings = get_settings()


@dataclass(frozen=True)
class EffectiveHoldPrefs:
  hold_display_mode: str
  min_hold_days_filter: int
  exit_reminders_enabled: bool
  theme_hold_multiplier: float


def effective_hold_prefs(db: Session | None = None) -> EffectiveHoldPrefs:
  prefs: HoldPrefs | None = None
  if db is not None:
    prefs = db.query(HoldPrefs).filter(HoldPrefs.id == 1).first()
  if prefs is None:
    return EffectiveHoldPrefs(
      hold_display_mode=settings.hold_display_mode,
      min_hold_days_filter=settings.min_hold_days_filter,
      exit_reminders_enabled=settings.exit_reminders_enabled,
      theme_hold_multiplier=settings.theme_hold_multiplier,
    )
  return EffectiveHoldPrefs(
    hold_display_mode=prefs.hold_display_mode or settings.hold_display_mode,
    min_hold_days_filter=prefs.min_hold_days_filter,
    exit_reminders_enabled=prefs.exit_reminders_enabled,
    theme_hold_multiplier=prefs.theme_hold_multiplier or settings.theme_hold_multiplier,
  )


def passes_min_hold_filter(hold_days: int | None, db: Session | None = None) -> bool:
  min_days = effective_hold_prefs(db).min_hold_days_filter
  if min_days <= 0:
    return True
  if hold_days is None:
    return True
  return int(hold_days) >= min_days
