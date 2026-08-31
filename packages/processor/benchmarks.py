"""Frozen benchmark windows: aspiration ceiling + survivable floor."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_CANDIDATES = [
  ROOT / "models" / "benchmarks" / "orwidth_ceiling_floor.json",
  Path(__file__).resolve().parent / "data" / "orwidth_ceiling_floor.json",
]


def _fixture_path() -> Path:
  for p in FIXTURE_CANDIDATES:
    if p.exists():
      return p
  return FIXTURE_CANDIDATES[0]


FIXTURE_PATH = _fixture_path()

# Primary score: reward compound, heavily penalize worst days below -6%, soft DD penalty.
WORST_DAY_SOFT_CAP = -6.0
WORST_PENALTY = 2.5
DD_PENALTY = 0.35


def primary_score(
  *,
  compound_pct: float,
  worst_day_pct: float,
  max_dd_pct: float | None = None,
) -> float:
  """Higher is better. Most-profits direction under survivable risk."""
  tail = min(0.0, worst_day_pct - WORST_DAY_SOFT_CAP)
  dd = float(max_dd_pct if max_dd_pct is not None else abs(min(0.0, worst_day_pct)))
  return round(compound_pct + WORST_PENALTY * tail - DD_PENALTY * dd, 4)


def load_fixtures() -> dict[str, Any]:
  path = _fixture_path()
  if not path.exists():
    return {"windows": [], "meta": {"error": "fixture_missing"}}
  return json.loads(path.read_text(encoding="utf-8"))


def window_specs() -> list[dict[str, Any]]:
  data = load_fixtures()
  return list(data.get("windows") or [])


def ceiling_for(window_id: str, config: str = "in_tr10_orwidth_chase5_75x") -> dict[str, Any] | None:
  for w in window_specs():
    if w.get("id") == window_id:
      return (w.get("ceiling") or {}).get(config)
  return None


def floor_for(window_id: str, config: str = "in_tr10_orwidth_chase5_75x_guard") -> dict[str, Any] | None:
  for w in window_specs():
    if w.get("id") == window_id:
      return (w.get("floor") or {}).get(config)
  return None


def compare_to_benchmarks(
  *,
  window_id: str,
  compound_pct: float,
  worst_day_pct: float,
  best_day_pct: float,
  max_dd_pct: float | None = None,
) -> dict[str, Any]:
  ceil = ceiling_for(window_id) or {}
  floor = floor_for(window_id) or {}
  score = primary_score(
    compound_pct=compound_pct,
    worst_day_pct=worst_day_pct,
    max_dd_pct=max_dd_pct,
  )
  ceil_c = float(ceil.get("compound_pct") or 0)
  floor_c = float(floor.get("compound_pct") or 0)
  gap_to_ceiling = round(ceil_c - compound_pct, 4) if ceil else None
  vs_floor = round(compound_pct - floor_c, 4) if floor else None
  pct_of_ceiling = None
  if ceil and abs(ceil_c) > 1e-9:
    pct_of_ceiling = round(100.0 * compound_pct / ceil_c, 2)
  return {
    "window_id": window_id,
    "run": {
      "compound_pct": compound_pct,
      "worst_day_pct": worst_day_pct,
      "best_day_pct": best_day_pct,
      "max_dd_pct": max_dd_pct,
      "primary_score": score,
    },
    "ceiling": ceil,
    "floor": floor,
    "gap_to_ceiling_pct": gap_to_ceiling,
    "vs_floor_pct": vs_floor,
    "pct_of_ceiling": pct_of_ceiling,
    "beats_ceiling": bool(ceil) and compound_pct > ceil_c and worst_day_pct >= float(ceil.get("worst_day_pct") or -999),
    "beats_floor_compound": bool(floor) and compound_pct >= floor_c,
    "north_star": "most_profits",
    "disclaimer": (
      "Ceiling rows are research-only lottery heroes (not live-eligible). "
      "Primary score optimizes keepable profit under risk caps."
    ),
  }
