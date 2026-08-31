"""Summarize hit rate / made / lost from August MTD + hybrid trade book."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
  aug = json.loads((ROOT / "models" / "hybrid_august_mtd_pnl.json").read_text(encoding="utf-8"))
  print("=== AUGUST MTD (compounded INR 10,000 | sessions 2026-08-03 -> 2026-08-28) ===")
  for r in aug["runs"]:
    daily = [d for d in (r.get("daily") or []) if "return_pct" in d]
    # reconstruct day PnL from equity path
    prev = float(r["capital_start"])
    for d in daily:
      end = float(d["capital_end"])
      d["pnl_inr"] = round(end - prev, 2)
      prev = end
    wins = [d for d in daily if d["return_pct"] > 0]
    losses = [d for d in daily if d["return_pct"] < 0]
    flats = [d for d in daily if d["return_pct"] == 0]
    win_pnl = sum(d["pnl_inr"] for d in wins)
    loss_pnl = sum(d["pnl_inr"] for d in losses)
    hit = 100.0 * len(wins) / len(daily) if daily else 0.0
    print(f"\nLANE {r['lane']}")
    print(f"  sessions={r['n_days']}  hit_rate={hit:.1f}% ({len(wins)}W / {len(losses)}L / {len(flats)}F)")
    print(f"  start=INR {r['capital_start']:,.2f}  end=INR {r['capital_end']:,.2f}")
    print(f"  NET PnL=INR {r['pnl_inr']:+,.2f}  compound={r['compound_pct']:+.2f}%")
    print(f"  GROSS made (winning days)=INR {win_pnl:+,.2f}")
    print(f"  GROSS lost (losing days)=INR {loss_pnl:+,.2f}")
    print(
      f"  worst_day={r['worst_day_pct']:+.2f}%  best_day={r['best_day_pct']:+.2f}%  "
      f"maxDD={r['max_dd_pct']:.2f}%"
    )
    print(f"  strategies={r.get('strategy_counts')}")
    print("  daily:")
    for d in daily:
      print(
        f"    {d['asof']}  ret={d['return_pct']:+7.2f}%  "
        f"pnl=INR {d['pnl_inr']:+9,.2f}  eq=INR {d['capital_end']:,.2f}  "
        f"{d.get('strategy_id','')}  trades={d.get('n_trades')}"
      )

  tp = ROOT / "models" / "hybrid_trades.jsonl"
  if not tp.exists():
    print("\n(no hybrid_trades.jsonl)")
    return
  rows = []
  for line in tp.read_text(encoding="utf-8").strip().splitlines():
    try:
      rows.append(json.loads(line))
    except json.JSONDecodeError:
      pass
  print(f"\n=== HYBRID TRADE BOOK ({len(rows)} fills recorded) ===")
  by_lane: dict[str, list] = defaultdict(list)
  for t in rows:
    by_lane[str(t.get("lane") or "unknown")].append(t)

  def summarize(label: str, ts: list) -> None:
    w = [t for t in ts if float(t.get("pnl") or 0) > 0]
    l = [t for t in ts if float(t.get("pnl") or 0) < 0]
    f = [t for t in ts if float(t.get("pnl") or 0) == 0]
    made = sum(float(t.get("pnl") or 0) for t in w)
    lost = sum(float(t.get("pnl") or 0) for t in l)
    net = sum(float(t.get("pnl") or 0) for t in ts)
    put = sum(float(t.get("money_put") or t.get("entry_notional") or 0) for t in ts)
    ret = sum(float(t.get("money_returned") or t.get("exit_notional") or 0) for t in ts)
    hit = 100.0 * len(w) / len(ts) if ts else 0.0
    avg_win = made / len(w) if w else 0.0
    avg_loss = lost / len(l) if l else 0.0
    print(f"\n  {label}: n={len(ts)}  hit={hit:.1f}% ({len(w)}W / {len(l)}L / {len(f)}F)")
    print(f"    money put sum=INR {put:,.2f}  money returned=INR {ret:,.2f}")
    print(f"    GROSS made=INR {made:+,.2f}  GROSS lost=INR {lost:+,.2f}  NET=INR {net:+,.2f}")
    print(f"    avg win=INR {avg_win:+,.2f}  avg loss=INR {avg_loss:+,.2f}")

  for lane, ts in sorted(by_lane.items()):
    summarize(lane, ts)
  summarize("ALL LANES", rows)


if __name__ == "__main__":
  main()
