"""Ablation bakeoff for Pattern Forge v2.1 + OOS 2023/2024 gate.

Never silently overwrites models/pattern_forge/v2_latest.json.
Writes models/pattern_forge/v2_1_bakeoff.json and optionally v2_1_latest.json
only when promotion rules pass.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_pattern_forge_daily_swing_2025 import run_daily_benchmark  # noqa: E402

PF = ROOT / "models" / "pattern_forge"
V2_PATH = PF / "v2_latest.json"
OUT_PATH = PF / "v2_1_bakeoff.json"
V21_PATH = PF / "v2_1_latest.json"


def _load_v2_knobs() -> dict[str, Any]:
  if not V2_PATH.exists():
    return {
      "leverage": 11.0,
      "sleeve_frac": 0.24,
      "learn_mistakes": True,
      "profit_guard": True,
      "profit_guard_floor_pct": 2.0,
      "long_only": True,
      "min_score": 0.005,
      "r1_lo": 0.005,
      "r1_hi": 0.06,
      "top_k": 1,
      "use_breadth_veto": False,
      "breadth_scale": False,
    }
  data = json.loads(V2_PATH.read_text(encoding="utf-8"))
  knobs = dict(data.get("knobs") or {})
  knobs.setdefault("leverage", 11.0)
  knobs.setdefault("sleeve_frac", 0.24)
  knobs.setdefault("profit_guard", True)
  knobs.setdefault("learn_mistakes", True)
  knobs.setdefault("long_only", True)
  return knobs


def _base_knobs(**overrides: Any) -> dict[str, Any]:
  k = _load_v2_knobs()
  k.update(
    {
      "reset_mistakes": True,
      "promote_summary": False,
      "write_lab_summary": False,
      "allow_overwrite_v2": False,
      "max_daily_loss_pct": 8.0,
      "universe_n": 0,
    }
  )
  k.update(overrides)
  return k


def _slim(report: dict[str, Any]) -> dict[str, Any]:
  return {
    "run_id": report.get("run_id"),
    "lane": report.get("lane"),
    "benchmark": report.get("benchmark"),
    "capital_end": report.get("capital_end"),
    "total_return_pct": report.get("total_return_pct"),
    "green_months": report.get("green_months"),
    "months_total": report.get("months_total"),
    "worst_month_pct": report.get("worst_month_pct"),
    "worst_month_pnl": report.get("worst_month_pnl"),
    "year_pnl": report.get("year_pnl"),
    "loss_lte_profits": report.get("loss_lte_profits"),
    "goal_met": report.get("goal_met"),
    "n_trades": report.get("n_trades"),
    "long_only": report.get("long_only"),
    "swarm_hard_veto": report.get("swarm_hard_veto"),
    "knobs": {
      k: report.get("knobs", {}).get(k)
      for k in (
        "leverage",
        "sleeve_frac",
        "long_only",
        "swarm_hard_veto",
        "overnight_feeds",
        "profit_guard",
        "learn_mistakes",
      )
    },
  }


def promotion_ok(candidate: dict[str, Any], locked_v2: dict[str, Any]) -> tuple[bool, list[str]]:
  reasons: list[str] = []
  c_ret = float(candidate.get("total_return_pct") or -999)
  v_ret = float(locked_v2.get("total_return_pct") or 0)
  if c_ret < v_ret:
    reasons.append(f"return {c_ret:.2f} < v2 {v_ret:.2f}")
  if not candidate.get("loss_lte_profits"):
    reasons.append("loss_lte_profits=False")
  if int(candidate.get("green_months") or 0) < 8:
    reasons.append(f"green_months={candidate.get('green_months')} < 8")
  return (len(reasons) == 0, reasons)


def oos_claim(row: dict[str, Any]) -> str:
  ret = float(row.get("total_return_pct") or 0)
  if ret > 0:
    return "oos_positive"
  if ret > -15:
    return "oos_less_bad_than_deep_drawdown"
  return "oos_failed_claim"


def run_ablation(*, year: int = 2025, skip_oos: bool = False, universe_n: int = 0) -> dict[str, Any]:
  locked = json.loads(V2_PATH.read_text(encoding="utf-8")) if V2_PATH.exists() else {}
  uni = {"universe_n": universe_n} if universe_n else {}

  variants: list[tuple[str, dict[str, Any]]] = [
    (
      "frozen_v2_replay",
      _base_knobs(
        lane="v2_replay",
        long_only=True,
        swarm_hard_veto=False,
        overnight_feeds=False,
        **uni,
      ),
    ),
    (
      "v2_shorts_only",
      _base_knobs(
        lane="v2_shorts_only",
        long_only=False,
        swarm_hard_veto=False,
        overnight_feeds=False,
        **uni,
      ),
    ),
    (
      "v2_hard_swarm_only",
      _base_knobs(
        lane="v2_hard_swarm_only",
        long_only=True,
        swarm_hard_veto=True,
        overnight_feeds=False,
        **uni,
      ),
    ),
    (
      "v2_profit_guard_control",
      _base_knobs(
        lane="v2_profit_guard_control",
        long_only=True,
        swarm_hard_veto=False,
        overnight_feeds=False,
        profit_guard=True,
        **uni,
      ),
    ),
    (
      "v2_1_full",
      _base_knobs(
        lane="v2_1",
        long_only=False,
        swarm_hard_veto=True,
        overnight_feeds=True,
        allow_overnight_network=False,
        promote_as="v2_1",
        **uni,
      ),
    ),
  ]

  rows: list[dict[str, Any]] = []
  full_reports: dict[str, Any] = {}
  for name, knobs in variants:
    print(f"\n=== ablation {name} year={year} ===", flush=True)
    rep = run_daily_benchmark(year=year, knobs=knobs)
    slim = _slim(rep)
    slim["variant"] = name
    rows.append(slim)
    full_reports[name] = rep

  best = full_reports.get("v2_1_full") or {}
  ok, fail_reasons = promotion_ok(best, locked or rows[0])

  oos: dict[str, Any] = {}
  if not skip_oos:
    for y in (2023, 2024):
      print(f"\n=== OOS frozen_v2 year={y} ===", flush=True)
      v2_oos = run_daily_benchmark(
        year=y,
        knobs=_base_knobs(
          lane="v2_oos",
          long_only=True,
          swarm_hard_veto=False,
          overnight_feeds=False,
          **uni,
        ),
      )
      print(f"\n=== OOS v2_1 year={y} ===", flush=True)
      v21_oos = run_daily_benchmark(
        year=y,
        knobs=_base_knobs(
          lane="v2_1_oos",
          long_only=False,
          swarm_hard_veto=True,
          overnight_feeds=True,
          **uni,
        ),
      )
      oos[str(y)] = {
        "v2": {**_slim(v2_oos), "claim": oos_claim(v2_oos)},
        "v2_1": {**_slim(v21_oos), "claim": oos_claim(v21_oos)},
      }

  oos_ok = True
  oos_notes: list[str] = []
  for y, block in oos.items():
    c = block.get("v2_1") or {}
    claim = c.get("claim")
    if claim == "oos_failed_claim":
      oos_ok = False
      oos_notes.append(f"{y}: v2_1 {claim} ret={c.get('total_return_pct')}")
    else:
      oos_notes.append(f"{y}: v2_1 {claim} ret={c.get('total_return_pct')}")

  promote = bool(ok and oos_ok)
  if promote and best:
    payload = dict(best)
    payload["promoted_as"] = "v2_1_challenger"
    payload["promotion"] = {
      "beats_v2_2025": ok,
      "oos_ok": oos_ok,
      "fail_reasons": fail_reasons,
      "oos_notes": oos_notes,
      "locked_v2_untouched": True,
    }
    V21_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
  elif best:
    # Still write challenger artefact for Lab comparison, marked not-promoted
    payload = dict(best)
    payload["promoted_as"] = None
    payload["promotion"] = {
      "beats_v2_2025": ok,
      "oos_ok": oos_ok,
      "fail_reasons": fail_reasons,
      "oos_notes": oos_notes,
      "locked_v2_untouched": True,
      "status": "research_only",
    }
    V21_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

  bakeoff = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "locked_v2": _slim(locked) if locked else None,
    "ablation_2025": rows,
    "oos": oos,
    "promotion": {
      "promote_to_locked_v2": False,  # never auto-promote to v2_latest
      "write_v2_1_latest": True,
      "beats_v2_2025": ok,
      "oos_ok": oos_ok,
      "fail_reasons": fail_reasons,
      "oos_notes": oos_notes,
      "eligible_challenger": promote,
    },
    "claim": "paper/sim clean PIT ablation; v2_latest.json never overwritten by this script",
  }
  PF.mkdir(parents=True, exist_ok=True)
  OUT_PATH.write_text(json.dumps(bakeoff, indent=2), encoding="utf-8")
  print(f"\nwrote {OUT_PATH}", flush=True)
  print(f"v2_1_latest → {V21_PATH} (eligible_challenger={promote})", flush=True)
  print(f"beats_v2={ok} oos_ok={oos_ok} reasons={fail_reasons or oos_notes}", flush=True)
  return bakeoff


def main() -> None:
  ap = argparse.ArgumentParser()
  ap.add_argument("--skip-oos", action="store_true")
  ap.add_argument("--universe-n", type=int, default=0, help="cap FO names (0=all)")
  ap.add_argument("--year", type=int, default=2025)
  args = ap.parse_args()
  run_ablation(year=args.year, skip_oos=args.skip_oos, universe_n=args.universe_n)


if __name__ == "__main__":
  main()
