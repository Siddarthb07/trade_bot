"""Staged partial exit suggestions (Phase 4.3)."""

from __future__ import annotations

from typing import Any


def build_partial_exit_plan(hold_days: int, *, trim_pct: float = 0.25, trim_return_pct: float = 0.08) -> list[dict[str, Any]]:
  if hold_days < 7:
    return []

  review = max(1, hold_days // 2)
  trim_day = max(7, hold_days // 3)
  hard_review = hold_days + max(3, hold_days // 7)

  return [
    {"day": 0, "action": "Enter full position", "note": "At signal disclosure price"},
    {
      "day": trim_day,
      "action": f"Consider trimming {int(trim_pct * 100)}%",
      "note": f"If up ~{int(trim_return_pct * 100)}% from entry",
    },
    {"day": review, "action": "Mid-hold review", "note": "Check thesis vs price action"},
    {"day": hold_days, "action": "Target full exit", "note": "Primary sell-by date"},
    {"day": hard_review, "action": "Hard stop review", "note": "Exit or reset thesis if still holding"},
  ]
