"""August MTD hybrid: compound ₹10k every session day from Aug 1 through today."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.hybrid.engine import _sessions, simulate_hybrid_day

CAPITAL = 10_000.0
START = "2026-08-01"
END = date.today().isoformat()
# Product first (keepable); stretch/research after for comparison.
LANES = ["product", "stretch", "research"]


def run_lane_compounded(lane: str) -> dict:
  days = _sessions(START, END)
  cap = float(CAPITAL)
  start_cap = cap
  daily = []
  min_ret, max_ret = 999.0, -999.0
  peak, max_dd = cap, 0.0
  strategy_counts: dict[str, int] = {}
  # Force OR-width path so chop priors don't idle on adaptive_edge (0 trades).
  # Lane still maps risk via sim_kwargs_for_strategy (guard / stretch / research).
  force = "orwidth_orb"

  print(f"=== lane={lane} | force={force} | {len(days)} sessions {START} → {END} ===", flush=True)
  for i, asof in enumerate(days, 1):
    print(f"  [{i}/{len(days)}] {asof} capital=₹{cap:,.2f} ...", flush=True)
    day = simulate_hybrid_day(
      asof=asof,
      capital=cap,
      market="IN",
      lane=lane,
      force_strategy=force,
      include_ticker_ranks=False,
      include_bars=False,
      record_learning=False,
    )
    if day.get("error"):
      print(f"       ERROR {day['error']}", flush=True)
      daily.append({"asof": asof, "error": day["error"]})
      continue
    ret = float(day.get("return_pct") or 0)
    cap = float(day.get("capital_end") or cap)
    peak = max(peak, cap)
    dd = 100.0 * (peak - cap) / peak if peak else 0.0
    max_dd = max(max_dd, dd)
    min_ret = min(min_ret, ret)
    max_ret = max(max_ret, ret)
    sid = str(day.get("strategy_id") or "")
    strategy_counts[sid] = strategy_counts.get(sid, 0) + 1
    daily.append(
      {
        "asof": asof,
        "return_pct": ret,
        "pnl_inr": round(float(day.get("realized_pnl") or 0), 2),
        "capital_end": round(cap, 2),
        "strategy_id": sid,
        "n_trades": day.get("n_trades"),
      }
    )
    print(
      f"       ret {ret:+.2f}%  day_pnl ₹{float(day.get('realized_pnl') or 0):+,.2f}  "
      f"equity ₹{cap:,.2f}  strat={sid}  trades={day.get('n_trades')}",
      flush=True,
    )

  if min_ret > 100:
    min_ret = 0.0
  if max_ret < -100:
    max_ret = 0.0
  compound = round(100.0 * (cap - start_cap) / start_cap, 4) if start_cap else 0.0
  pnl = round(cap - start_cap, 2)
  print(
    f"  DONE {lane}: PnL ₹{pnl:+,.2f}  compound {compound:+.2f}%  "
    f"worst {min_ret:+.2f}%  best {max_ret:+.2f}%  maxDD {max_dd:.2f}%  end ₹{cap:,.2f}\n",
    flush=True,
  )
  return {
    "lane": lane,
    "start": START,
    "end": END,
    "capital_start": start_cap,
    "capital_end": round(cap, 2),
    "pnl_inr": pnl,
    "compound_pct": compound,
    "worst_day_pct": round(min_ret, 4),
    "best_day_pct": round(max_ret, 4),
    "max_dd_pct": round(max_dd, 4),
    "n_days": len(days),
    "strategy_counts": strategy_counts,
    "daily": daily,
  }


def main() -> None:
  print(f"August MTD compound | ₹{CAPITAL:,.0f} start | {START} → {END}\n", flush=True)
  all_runs = []
  for lane in LANES:
    all_runs.append(run_lane_compounded(lane))

  out = ROOT / "models" / "hybrid_august_mtd_pnl.json"
  out.write_text(json.dumps({"capital": CAPITAL, "runs": all_runs}, indent=2), encoding="utf-8")
  print(f"Wrote {out}", flush=True)
  print("\n========== AUGUST MTD SUMMARY (₹10,000 start, compounded daily) ==========", flush=True)
  print(f"{'Lane':<10} {'PnL ₹':>12} {'Compound%':>10} {'Worst%':>8} {'Best%':>8} {'MaxDD%':>8} {'End ₹':>12}", flush=True)
  for row in all_runs:
    print(
      f"{row['lane']:<10} {row['pnl_inr']:>+12,.0f} {row['compound_pct']:>+9.2f}% "
      f"{row['worst_day_pct']:>+7.1f}% {row['best_day_pct']:>+7.1f}% {row['max_dd_pct']:>7.1f}% "
      f"{row['capital_end']:>12,.0f}",
      flush=True,
    )


if __name__ == "__main__":
  main()
