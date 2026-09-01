"""Adaptive feature-fingerprint learning for Pattern Forge.

Design goals (forward-testable, not backtest month-fitting):
- Learn *contexts* that preceded meaningful losses (regime, breadth, underwater, streak).
- When the same context reappears, only *reduce* risk (size / sit) — never amplify.
- No calendar month hardcodes. October is not special; fingerprints are.
- Rules need repeated evidence before they bite; they expire / decay.

This is the learning substrate for walk-forward eval, not a guarantee to beat locked v2.
"""

from __future__ import annotations

from typing import Any

# Evidence thresholds — require repeats so one bad day cannot overfit a year
MIN_FP_HITS_TO_SIZE = 3
MIN_FP_HITS_TO_SIT = 6
FP_SIZE_MULT = 0.55
FP_EXPIRE_SESSIONS = 8  # soft memory; re-learn if pattern returns
MIN_DAY_RET_FOR_FP = -0.8  # %; ignore tiny reds


def context_fingerprint(
  *,
  regime: str | None,
  breadth_frac: float | None = None,
  breadth_stress: bool | None = None,
  ytd_underwater: bool = False,
  loss_streak: int = 0,
  market_mode: str | None = None,
) -> dict[str, Any]:
  """PIT-safe context vector → stable id for learning."""
  reg = str(regime or "unknown")
  bf = float(breadth_frac) if breadth_frac is not None else None
  if bf is None:
    b_bucket = "na"
  elif bf < 0.35:
    b_bucket = "stress"
  elif bf < 0.50:
    b_bucket = "weak"
  elif bf < 0.65:
    b_bucket = "ok"
  else:
    b_bucket = "strong"
  if breadth_stress is True:
    b_bucket = "stress"
  streak_bucket = "0" if loss_streak <= 0 else ("1" if loss_streak == 1 else ("2" if loss_streak == 2 else "3p"))
  uw = "1" if ytd_underwater else "0"
  mode = str(market_mode or "na")
  fid = f"fp::{reg}::b_{b_bucket}::uw_{uw}::st_{streak_bucket}::m_{mode}"
  return {
    "id": fid,
    "regime": reg,
    "breadth_bucket": b_bucket,
    "breadth_frac": round(bf, 4) if bf is not None else None,
    "ytd_underwater": ytd_underwater,
    "loss_streak": int(loss_streak),
    "streak_bucket": streak_bucket,
    "market_mode": mode,
  }


def fingerprint_rule_from_failure(
  *,
  fp: dict[str, Any],
  asof: str,
  day_return_pct: float,
  expires_on: str,
  prior_hits: int = 0,
) -> dict[str, Any]:
  """Build / refresh a fingerprint rule after a meaningful red day."""
  hits = int(prior_hits) + 1
  if hits >= MIN_FP_HITS_TO_SIT:
    kind = "fingerprint_sitout"
    size_mult = 0.0
    title = f"Sit out recurring failure context {fp['id']}"
    lesson = (
      f"Context {fp['id']} failed ≥{MIN_FP_HITS_TO_SIT} times "
      f"(latest {asof} day_ret={day_return_pct:.2f}%). Sit one session."
    )
  else:
    kind = "fingerprint_size_down"
    size_mult = FP_SIZE_MULT
    title = f"Size-down recurring failure context {fp['id']}"
    lesson = (
      f"Context {fp['id']} failed {hits}× "
      f"(latest {asof} day_ret={day_return_pct:.2f}%). Soft size×{FP_SIZE_MULT}."
    )
  return {
    "id": fp["id"],
    "kind": kind,
    "title": title,
    "reason": lesson,
    "source_asof": asof,
    "expires_on": expires_on,
    "status": "active",
    "permanent": False,
    "family": "daily_swing",
    "size_mult": size_mult,
    "fingerprint": fp,
    "evidence_hits": hits,
    "min_hits_to_act": MIN_FP_HITS_TO_SIZE,
    "active_defense": hits >= MIN_FP_HITS_TO_SIZE,
  }


def match_fingerprint_rules(
  rules: list[dict[str, Any]],
  *,
  fp: dict[str, Any],
) -> dict[str, Any]:
  """Apply matching fingerprint rules (never amplify)."""
  size_mult = 1.0
  sitout = False
  matched: list[dict[str, Any]] = []
  for r in rules:
    kind = str(r.get("kind") or "")
    if kind not in ("fingerprint_size_down", "fingerprint_sitout"):
      continue
    if str(r.get("id")) != str(fp.get("id")):
      continue
    if not r.get("active_defense") and int(r.get("evidence_hits") or 0) < MIN_FP_HITS_TO_SIZE:
      # Still learning — annotate only
      matched.append({**r, "applied": False})
      continue
    matched.append({**r, "applied": True})
    if kind == "fingerprint_sitout":
      sitout = True
      size_mult = 0.0
    else:
      try:
        size_mult = min(size_mult, float(r.get("size_mult") or FP_SIZE_MULT))
      except (TypeError, ValueError):
        size_mult = min(size_mult, FP_SIZE_MULT)
  return {
    "size_mult": max(0.0, min(1.0, size_mult)),
    "sitout": sitout,
    "matched": matched,
    "fingerprint": fp,
  }
