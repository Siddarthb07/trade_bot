"""Hybrid multi-strategy engine — alpha chooser + risk budget + learning."""

from __future__ import annotations

from processor.hybrid.engine import simulate_hybrid_day, simulate_hybrid_window
from processor.hybrid.ledger import load_chooser_state, load_recent_outcomes
from processor.hybrid.rules_ledger import load_rules_ledger, read_daily_briefing
from processor.hybrid.wins import list_wins

try:
  from processor.hybrid.recognition import recognize_session
except Exception:  # noqa: BLE001 — optional until package wired
  recognize_session = None  # type: ignore[assignment]

__all__ = [
  "simulate_hybrid_day",
  "simulate_hybrid_window",
  "load_chooser_state",
  "load_recent_outcomes",
  "load_rules_ledger",
  "read_daily_briefing",
  "list_wins",
  "recognize_session",
]
