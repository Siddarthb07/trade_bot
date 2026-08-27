"""Validate adaptive profile freezes (Stage B)."""

from __future__ import annotations

from typing import Any

MIN_OOS = 30
TARGET_HIT = 85.0


def validate_profiles(data: dict[str, Any], *, require_eligible: bool = False) -> list[str]:
  errors: list[str] = []
  profiles = data.get("profiles") or {}
  eligible = data.get("eligible_tickers") or []
  if require_eligible and not eligible:
    errors.append("eligible_tickers empty — refuse publish")
  for t in eligible:
    p = profiles.get(t)
    if not p:
      errors.append(f"{t}: listed eligible but missing profile")
      continue
    if not p.get("ambition_pass"):
      errors.append(f"{t}: eligible but ambition_pass=false")
    oos = p.get("holdout_oos") or {}
    n = int(oos.get("n_trades") or 0)
    hit = oos.get("hit_rate_pct")
    exp = oos.get("expectancy")
    if n < MIN_OOS:
      errors.append(f"{t}: n_trades={n} < {MIN_OOS}")
    if hit is None or float(hit) < TARGET_HIT:
      errors.append(f"{t}: hit_rate_pct={hit} < {TARGET_HIT}")
    if exp is None or float(exp) <= 0:
      errors.append(f"{t}: expectancy={exp} not > 0")
    if not p.get("regime"):
      errors.append(f"{t}: missing regime tag")
  for t, p in profiles.items():
    if p.get("ambition_pass") and t not in eligible:
      errors.append(f"{t}: ambition_pass true but not in eligible_tickers")
  return errors
