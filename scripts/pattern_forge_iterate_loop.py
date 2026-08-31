"""Hands-free Pattern Forge iteration loop (stage-gated R&D).

Each cycle:
1. Pick next method / knob mutation from the method portfolio
2. Run 2025 benchmark (subset or full)
3. Log iteration + decide KEEP/DISCARD vs best green-month score
4. Sleep and repeat until goal_met or max iterations

research-finance discipline: kill criterion after N non-improving runs;
never disable no-ruin; never resurrect WR leakage.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.pattern_forge.ledger import log_iteration, load_summary, write_summary

# Call benchmark module directly
sys.path.insert(0, str(ROOT / "scripts"))
from run_pattern_forge_2025_benchmark import MONTHS_2025, run_benchmark  # noqa: E402
from run_pattern_forge_daily_swing_2025 import run_daily_benchmark  # noqa: E402

STATE_PATH = ROOT / ".autoresearch" / "trading" / "pattern-forge" / "loop_state.json"
RESULTS_TSV = ROOT / ".autoresearch" / "trading" / "pattern-forge" / "results.tsv"
PROGRAM = ROOT / ".autoresearch" / "trading" / "pattern-forge" / "program.md"

# Method portfolio — daily FO swing first (session 1h structurally < equity costs)
MUTATIONS: list[dict] = [
  {"family": "daily_swing", "knobs": {"sleeve_frac": 0.24, "leverage": 11.0, "long_only": True, "min_score": 0.005, "r1_lo": 0.005, "r1_hi": 0.06, "universe_n": 0, "max_daily_loss_pct": 8.0, "top_k": 1, "learn_mistakes": True, "breadth_scale": False, "use_breadth_veto": False, "profit_guard": True, "profit_guard_floor_pct": 2.0, "lane": "v2", "promote_as": "v2", "promote_summary": True}, "label": "v2", "runner": "daily"},
  {"family": "daily_swing", "knobs": {"sleeve_frac": 0.27, "leverage": 8.0, "long_only": True, "min_score": 0.005, "r1_lo": 0.005, "r1_hi": 0.06, "universe_n": 0, "max_daily_loss_pct": 8.0, "top_k": 1, "learn_mistakes": True, "breadth_scale": False, "use_breadth_veto": False, "lane": "v2_aim40_lev8", "promote_as": "aim40", "promote_summary": False}, "label": "v2_aim40_lev8", "runner": "daily"},
  {"family": "daily_swing", "knobs": {"sleeve_frac": 0.2, "leverage": 3.0, "long_only": True, "min_score": 0.005, "r1_lo": 0.005, "r1_hi": 0.06, "universe_n": 0, "max_daily_loss_pct": 4.0, "top_k": 1, "learn_mistakes": True, "breadth_scale": False, "use_breadth_veto": False, "lane": "v2_product_lev3", "promote_summary": False}, "label": "v2_product_lev3", "runner": "daily"},
  {"family": "daily_swing", "knobs": {"sleeve_frac": 0.25, "leverage": 2.0, "long_only": True, "min_score": 0.005, "r1_lo": 0.005, "r1_hi": 0.06, "universe_n": 0, "max_daily_loss_pct": 4.0, "top_k": 1, "learn_mistakes": True, "breadth_scale": False, "lane": "v2_product_lev2"}, "label": "v2_product_lev2", "runner": "daily"},
  {"family": "daily_swing", "knobs": {"sleeve_frac": 0.25, "leverage": 10.0, "long_only": True, "min_score": 0.005, "r1_lo": 0.005, "r1_hi": 0.06, "universe_n": 0, "max_daily_loss_pct": 8.0, "learn_mistakes": True, "lane": "v1_stretch_push10"}, "label": "v1_stretch_push10", "runner": "daily"},
  {"family": "hybrid_stock_market", "knobs": {"sleeve_frac": 0.2, "tau": 0.55, "long_only": True, "min_confidence": 0.62, "hybrid_min_score": 0.28}, "label": "hybrid_sitout"},
]


def _load_state() -> dict:
  if STATE_PATH.exists():
    try:
      return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
      pass
  return {"i": 0, "best_green": -1, "best_return": -999.0, "no_improve": 0, "best_label": None}


def _save_state(st: dict) -> None:
  STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
  STATE_PATH.write_text(json.dumps(st, indent=2), encoding="utf-8")


def _append_tsv(row: dict) -> None:
  RESULTS_TSV.parent.mkdir(parents=True, exist_ok=True)
  if not RESULTS_TSV.exists():
    RESULTS_TSV.write_text(
      "ts\tlabel\tfamily\tgreen_months\ttotal_return_pct\tkeep\tgoal_met\n",
      encoding="utf-8",
    )
  with RESULTS_TSV.open("a", encoding="utf-8") as f:
    f.write(
      f"{row['ts']}\t{row['label']}\t{row['family']}\t{row['green_months']}\t"
      f"{row['total_return_pct']}\t{row['keep']}\t{row['goal_met']}\n"
    )


def ensure_program() -> None:
  PROGRAM.parent.mkdir(parents=True, exist_ok=True)
  if PROGRAM.exists():
    return
  PROGRAM.write_text(
    """# Pattern Forge autoresearch

## Goal
Consistent monthly profits on **clean-PIT 2025** (≥8/12 green months, positive year).
Stretch: maximize annual toward unclean ~500% label — never claim leaky numbers.

## Constraints
- No-ruin floor always on
- F&O shorts only
- One mutation per iteration
- Kill after 5 non-improving runs (reset mutation cursor, continue)

## Strategy escalation
Candle → tighter SL → sleeve → ORB2s → analog → stricter day halt → selective ORB
""",
    encoding="utf-8",
  )


def one_iteration(*, allow_network: bool, months_subset: bool) -> dict:
  ensure_program()
  st = _load_state()
  mut = MUTATIONS[st["i"] % len(MUTATIONS)]
  iteration_id = str(uuid.uuid4())[:10]
  months = MONTHS_2025
  if months_subset:
    # Faster cycle: Oct–Dec 2025 (still 2025 benchmark slice)
    months = [m for m in MONTHS_2025 if m[0] in ("october", "november", "december")]
  print(
    f"\n=== iteration {st['i']} label={mut['label']} family={mut['family']} ===",
    flush=True,
  )
  if mut.get("runner") == "daily" or mut["family"] == "daily_swing":
    report = run_daily_benchmark(
      months=months,
      iteration_id=iteration_id,
      knobs=mut["knobs"],
    )
  else:
    report = run_benchmark(
      family=mut["family"],
      allow_network=allow_network,
      months=months,
      iteration_id=iteration_id,
      knobs=mut["knobs"],
    )
  green = int(report.get("green_months") or 0)
  ret = float(report.get("total_return_pct") or 0)
  keep = green > st["best_green"] or (green == st["best_green"] and ret > st["best_return"])
  if keep:
    st["best_green"] = green
    st["best_return"] = ret
    st["best_label"] = mut["label"]
    st["no_improve"] = 0
  else:
    st["no_improve"] = int(st.get("no_improve") or 0) + 1
  st["i"] = int(st["i"]) + 1
  if st["no_improve"] >= 5:
    st["no_improve"] = 0
    # advance past current family cluster
    st["i"] = int(st["i"]) + 1
  _save_state(st)
  row = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "label": mut["label"],
    "family": mut["family"],
    "green_months": green,
    "total_return_pct": ret,
    "keep": keep,
    "goal_met": bool(report.get("goal_met")),
  }
  _append_tsv(row)
  log_iteration({**row, "iteration_id": iteration_id, "run_id": report.get("run_id"), "knobs": mut["knobs"]})
  write_summary(
    {
      "status": "looping",
      "best_label": st.get("best_label"),
      "best_green_months": st.get("best_green"),
      "best_return_pct": st.get("best_return"),
      "latest_label": mut["label"],
      "latest_green_months": green,
      "latest_return_pct": ret,
      "goal_met": bool(report.get("goal_met")),
      "iteration": st["i"],
      "benchmark": "2025",
    }
  )
  return {**row, "state": st}


def main() -> None:
  ap = argparse.ArgumentParser()
  ap.add_argument("--once", action="store_true")
  ap.add_argument("--interval-sec", type=int, default=3600)
  ap.add_argument("--max-iters", type=int, default=48)
  ap.add_argument("--cache-only", action="store_true")
  ap.add_argument("--fast", action="store_true", help="Oct–Dec 2025 slice only")
  args = ap.parse_args()
  n = 0
  while n < args.max_iters:
    one_iteration(allow_network=not args.cache_only, months_subset=args.fast)
    n += 1
    summary = load_summary()
    if summary.get("goal_met"):
      print("GOAL MET — stopping loop", flush=True)
      break
    if args.once:
      break
    print(f"sleep {args.interval_sec}s …", flush=True)
    time.sleep(max(30, args.interval_sec))


if __name__ == "__main__":
  main()
