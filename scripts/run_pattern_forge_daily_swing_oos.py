"""Dedicated daily_swing OOS runner for years 2023 / 2024 (and any year).

Uses the same engine as 2025 benches. Does not overwrite v2_latest.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_pattern_forge_daily_swing_2025 import run_daily_benchmark  # noqa: E402


def main() -> None:
  ap = argparse.ArgumentParser()
  ap.add_argument("--year", type=int, required=True, choices=[2023, 2024, 2025, 2026])
  ap.add_argument("--lane", default="v2_oos", choices=["v2_oos", "v2_1_oos", "v2", "v2_1"])
  ap.add_argument("--universe-n", type=int, default=0)
  ap.add_argument("--no-promote", action="store_true", default=True)
  args = ap.parse_args()
  is_v21 = "v2_1" in args.lane
  knobs = {
    "lane": args.lane,
    "year": args.year,
    "leverage": 11.0,
    "sleeve_frac": 0.24,
    "learn_mistakes": True,
    "profit_guard": True,
    "profit_guard_floor_pct": 2.0,
    "reset_mistakes": True,
    "long_only": not is_v21,
    "swarm_hard_veto": is_v21,
    "overnight_feeds": is_v21,
    "allow_overnight_network": False,
    "min_score": 0.005,
    "r1_lo": 0.005,
    "r1_hi": 0.06,
    "top_k": 1,
    "use_breadth_veto": False,
    "breadth_scale": False,
    "promote_summary": False,
    "write_lab_summary": False,
    "allow_overwrite_v2": False,
    "universe_n": args.universe_n,
    "max_daily_loss_pct": 8.0,
  }
  rep = run_daily_benchmark(year=args.year, knobs=knobs)
  out = ROOT / "models" / "pattern_forge" / f"oos_{args.year}_{args.lane}.json"
  out.write_text(json.dumps(rep, indent=2), encoding="utf-8")
  print(f"wrote {out}", flush=True)


if __name__ == "__main__":
  main()
