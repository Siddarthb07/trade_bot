"""Next iteration: bigger return + loss_lte_profits via profit_guard."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_pattern_forge_daily_swing_2025 import run_daily_benchmark

CANDS = [
  {"leverage": 10.0, "sleeve_frac": 0.25, "lane": "v2_aim_next_lev10_guard"},
  {"leverage": 11.0, "sleeve_frac": 0.24, "lane": "v2_aim_next_lev11_guard"},
  {"leverage": 12.0, "sleeve_frac": 0.22, "lane": "v2_aim_next_lev12_guard"},
  {"leverage": 9.0, "sleeve_frac": 0.28, "lane": "v2_aim_next_lev9_guard"},
]


def main() -> None:
  rows = []
  for c in CANDS:
    print(f"\n=== {c['lane']} ===", flush=True)
    r = run_daily_benchmark(
      knobs={
        **c,
        "long_only": True,
        "min_score": 0.005,
        "r1_lo": 0.005,
        "r1_hi": 0.06,
        "top_k": 1,
        "learn_mistakes": True,
        "breadth_scale": False,
        "use_breadth_veto": False,
        "profit_guard": True,
        "profit_guard_floor_pct": 2.0,
        "reset_mistakes": True,
        "promote_summary": False,
        "promote_as": "aim_next",
        "max_daily_loss_pct": 8.0,
      }
    )
    row = {
      "lane": c["lane"],
      "lev": c["leverage"],
      "sleeve": c["sleeve_frac"],
      "ret": r["total_return_pct"],
      "end": r["capital_end"],
      "green": r["green_months"],
      "worst_pct": r["worst_month_pct"],
      "worst_pnl": r["worst_month_pnl"],
      "year_pnl": r["year_pnl"],
      "loss_lte_profits": r["loss_lte_profits"],
      "run_id": r["run_id"],
      "beats_aim40": float(r["total_return_pct"]) > 42.578 and r["loss_lte_profits"],
    }
    rows.append((row, r))
    print(
      f"RESULT ret={row['ret']:+.2f}% end={row['end']:.0f} "
      f"worst={row['worst_pct']:+.2f}% ({row['worst_pnl']}) "
      f"loss_lte={row['loss_lte_profits']} beats40={row['beats_aim40']}",
      flush=True,
    )

  # Prefer: loss_lte_profits, then higher return than aim40, then max return
  eligible = [x for x in rows if x[0]["loss_lte_profits"] and x[0]["ret"] > 42.0]
  if not eligible:
    eligible = [x for x in rows if x[0]["loss_lte_profits"]]
  if not eligible:
    eligible = rows
  pick_row, pick_r = max(eligible, key=lambda x: x[0]["ret"])
  pick_r = {**pick_r, "lane": "v2_aim_next", "knobs": {**(pick_r.get("knobs") or {}), "promote_as": "aim_next"}}
  out = ROOT / "models" / "pattern_forge" / "v2_aim_next_latest.json"
  out.write_text(json.dumps(pick_r, indent=2), encoding="utf-8")
  Path(ROOT / "models" / "pattern_forge" / "aim_next_sweep.json").write_text(
    json.dumps({"rows": [r for r, _ in rows], "pick": pick_row}, indent=2), encoding="utf-8"
  )
  print("PICK", pick_row, flush=True)
  print(f"wrote {out}", flush=True)


if __name__ == "__main__":
  main()
