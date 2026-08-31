"""Run hybrid lanes on bad/good windows @ ₹10k — print PnL margins."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.hybrid.engine import simulate_hybrid_window

CAPITAL = 10_000.0
WINDOWS = [
  ("july_chop", "BAD — July chop"),
  ("aug_chop", "MIXED — Aug chop"),
  ("benchmark_15d", "GOOD — Aug benchmark"),
]
LANES = ["product", "stretch", "research"]


def main() -> None:
  rows = []
  print(f"Capital start: ₹{CAPITAL:,.0f}\n", flush=True)
  for wid, label in WINDOWS:
    print(f"=== {label} ({wid}) ===", flush=True)
    for lane in LANES:
      print(f"  running lane={lane} ...", flush=True)
      r = simulate_hybrid_window(
        window_id=wid,
        capital=CAPITAL,
        market="IN",
        lane=lane,
        record_learning=False,
      )
      if r.get("error"):
        print(f"  ERROR {lane}: {r['error']}", flush=True)
        continue
      start = float(r["capital_start"])
      end = float(r["capital_end"])
      pnl = end - start
      margin_pct = 100.0 * pnl / start
      bench = r.get("benchmark") or {}
      row = {
        "window": wid,
        "label": label,
        "lane": lane,
        "capital_start": start,
        "capital_end": end,
        "pnl_inr": round(pnl, 2),
        "pnl_margin_pct": round(margin_pct, 3),
        "worst_day_pct": r.get("worst_day_pct"),
        "best_day_pct": r.get("best_day_pct"),
        "max_dd_pct": r.get("max_dd_pct"),
        "primary_score": r.get("primary_score"),
        "n_days": r.get("n_days"),
        "strategy_counts": r.get("strategy_counts"),
        "gap_to_ceiling_pct": bench.get("gap_to_ceiling_pct"),
        "vs_floor_pct": bench.get("vs_floor_pct"),
        "pct_of_ceiling": bench.get("pct_of_ceiling"),
      }
      rows.append(row)
      print(
        f"  {lane:8s}  PnL ₹{pnl:+,.0f}  margin {margin_pct:+.2f}%  "
        f"end ₹{end:,.0f}  worst {r.get('worst_day_pct'):+.1f}%  "
        f"best {r.get('best_day_pct'):+.1f}%  DD {r.get('max_dd_pct'):.1f}%  "
        f"score {r.get('primary_score')}",
        flush=True,
      )
    print(flush=True)

  out = ROOT / "models" / "hybrid_window_pnl_report.json"
  out.write_text(json.dumps({"capital": CAPITAL, "runs": rows}, indent=2), encoding="utf-8")
  print(f"Wrote {out}", flush=True)

  # Summary table
  print("\n========== PnL MARGIN SUMMARY (₹10,000 start) ==========", flush=True)
  print(f"{'Window':<16} {'Lane':<10} {'PnL ₹':>10} {'Margin%':>9} {'Worst%':>8} {'Best%':>8} {'MaxDD%':>8}", flush=True)
  for row in rows:
    print(
      f"{row['window']:<16} {row['lane']:<10} "
      f"{row['pnl_inr']:>+10,.0f} {row['pnl_margin_pct']:>+8.2f}% "
      f"{row['worst_day_pct']:>+7.1f}% {row['best_day_pct']:>+7.1f}% {row['max_dd_pct']:>7.1f}%",
      flush=True,
    )


if __name__ == "__main__":
  main()
