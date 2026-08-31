"""Sweep leverage for 40–50% annual aim on clean 2025 daily_swing."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_pattern_forge_daily_swing_2025 import run_daily_benchmark  # noqa: E402

ROWS = []


def main() -> None:
  for lev in (5, 6, 7, 8, 9, 10):
    sleeve = 0.25 if lev >= 8 else 0.22
    print(f"\n=== lev {lev} sleeve {sleeve} ===", flush=True)
    r = run_daily_benchmark(
      knobs={
        "leverage": float(lev),
        "sleeve_frac": sleeve,
        "long_only": True,
        "min_score": 0.005,
        "r1_lo": 0.005,
        "r1_hi": 0.06,
        "top_k": 1,
        "learn_mistakes": True,
        "breadth_scale": False,
        "use_breadth_veto": False,
        "reset_mistakes": True,
        "promote_summary": False,
        "lane": f"v2_aim40_lev{lev}",
        "max_daily_loss_pct": 6.0 if lev <= 6 else 8.0,
      }
    )
    row = {
      "lev": lev,
      "sleeve": sleeve,
      "total_return_pct": r["total_return_pct"],
      "green_months": r["green_months"],
      "worst_month_pct": r["worst_month_pct"],
      "best_month_pct": r["best_month_pct"],
      "n_trades": r["n_trades"],
      "run_id": r["run_id"],
      "goal_met_product": r["goal_met"],
      "in_40_50": 40.0 <= float(r["total_return_pct"]) <= 50.0,
    }
    ROWS.append(row)
    print(
      f"RESULT lev={lev} ret={r['total_return_pct']:+.2f}% "
      f"green={r['green_months']}/{r['months_total']} "
      f"worst={r['worst_month_pct']:+.2f}% in40_50={row['in_40_50']}",
      flush=True,
    )

  out = ROOT / "models" / "pattern_forge" / "aim40_leverage_sweep.json"
  out.write_text(json.dumps({"rows": ROWS, "claim": "clean PIT 2025; soft mistake ledger; not OOS"}, indent=2), encoding="utf-8")
  print(f"\nwrote {out}", flush=True)
  for row in ROWS:
    print(row)


if __name__ == "__main__":
  main()
