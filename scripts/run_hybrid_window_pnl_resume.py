"""Resume hybrid window PnL from where the prior run crashed (aug_chop stretch)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.hybrid.engine import simulate_hybrid_window

CAPITAL = 10_000.0

# Prior completed rows (from crashed run terminal + known july)
PRIOR = [
  {
    "window": "july_chop",
    "label": "BAD — July chop",
    "lane": "product",
    "capital_start": 10000.0,
    "capital_end": 9290.0,
    "pnl_inr": -710.0,
    "pnl_margin_pct": -7.1,
    "worst_day_pct": -7.2,
    "best_day_pct": 20.6,
    "max_dd_pct": 18.4,
    "primary_score": -16.5837,
  },
  {
    "window": "july_chop",
    "label": "BAD — July chop",
    "lane": "stretch",
    "capital_start": 10000.0,
    "capital_end": 7832.0,
    "pnl_inr": -2168.0,
    "pnl_margin_pct": -21.68,
    "worst_day_pct": -10.1,
    "best_day_pct": 11.3,
    "max_dd_pct": 29.2,
    "primary_score": -42.1059,
  },
  {
    "window": "july_chop",
    "label": "BAD — July chop",
    "lane": "research",
    "capital_start": 10000.0,
    "capital_end": 2827.0,
    "pnl_inr": -7173.0,
    "pnl_margin_pct": -71.73,
    "worst_day_pct": -32.5,
    "best_day_pct": 19.9,
    "max_dd_pct": 76.0,
    "primary_score": -164.5961,
  },
  {
    "window": "aug_chop",
    "label": "MIXED — Aug chop",
    "lane": "product",
    "capital_start": 10000.0,
    "capital_end": 8021.0,
    "pnl_inr": -1979.0,
    "pnl_margin_pct": -19.79,
    "worst_day_pct": -8.4,
    "best_day_pct": 6.8,
    "max_dd_pct": 25.5,
    "primary_score": -34.7097,
  },
]

REMAINING = [
  ("aug_chop", "MIXED — Aug chop", "stretch"),
  ("aug_chop", "MIXED — Aug chop", "research"),
  ("benchmark_15d", "GOOD — Aug benchmark", "product"),
  ("benchmark_15d", "GOOD — Aug benchmark", "stretch"),
  ("benchmark_15d", "GOOD — Aug benchmark", "research"),
]


def main() -> None:
  rows = list(PRIOR)
  print(f"Resume window PnL | ₹{CAPITAL:,.0f} | {len(REMAINING)} remaining runs\n", flush=True)
  for wid, label, lane in REMAINING:
    print(f"=== {label} ({wid}) lane={lane} ===", flush=True)
    r = simulate_hybrid_window(
      window_id=wid,
      capital=CAPITAL,
      market="IN",
      lane=lane,
      record_learning=False,
    )
    if r.get("error"):
      print(f"  ERROR: {r['error']}", flush=True)
      continue
    start = float(r["capital_start"])
    end = float(r["capital_end"])
    pnl = end - start
    margin_pct = 100.0 * pnl / start
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
    }
    rows.append(row)
    print(
      f"  {lane:8s}  PnL ₹{pnl:+,.0f}  margin {margin_pct:+.2f}%  "
      f"end ₹{end:,.0f}  worst {r.get('worst_day_pct'):+.1f}%  "
      f"best {r.get('best_day_pct'):+.1f}%  DD {r.get('max_dd_pct'):.1f}%",
      flush=True,
    )

  out = ROOT / "models" / "hybrid_window_pnl_report.json"
  out.write_text(json.dumps({"capital": CAPITAL, "runs": rows, "resumed": True}, indent=2), encoding="utf-8")
  print(f"\nWrote {out}", flush=True)
  print("\n========== PnL MARGIN SUMMARY (₹10,000 start) ==========", flush=True)
  print(f"{'Window':<16} {'Lane':<10} {'PnL ₹':>10} {'Margin%':>9} {'Worst%':>8} {'Best%':>8} {'MaxDD%':>8}", flush=True)
  for row in rows:
    print(
      f"{row['window']:<16} {row['lane']:<10} "
      f"{row['pnl_inr']:>+10,.0f} {row['pnl_margin_pct']:>+8.2f}% "
      f"{row.get('worst_day_pct', 0):>+7.1f}% {row.get('best_day_pct', 0):>+7.1f}% {row.get('max_dd_pct', 0):>7.1f}%",
      flush=True,
    )


if __name__ == "__main__":
  main()
