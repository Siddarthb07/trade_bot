"""Rebuild oneshot / year book capital from trade ledger (ground truth).

Bug: capital_end previously tracked PaperBroker.cash which omitted CostModel India
fees (~30bps RT) while trade.pnl included them. True book = start + sum(pnl).

Rewrites:
  models/copy_pro_jan_aug_oneshot_10k.json
  models/copy_pro_year_2025_oneshot_10k.json
  GodFather-core public oneshot_2026.json + year_2025.json
  models/godfather_desk_tape.json summary capital fields
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASH = Path(r"C:\Users\siddu\Projects\GodFather-core\apps\dashboard\public")
START = 10_000.0


def rebuild(path: Path, *, year: int | None = None) -> dict:
  data = json.loads(path.read_text(encoding="utf-8"))
  months = list(data.get("months") or [])
  cap = float(data.get("capital_start") or START)
  all_trades = []
  for m in months:
    trades = list(m.get("trades") or [])
    month_pnl = round(sum(float(t.get("pnl") or 0) for t in trades), 2)
    wins = sum(1 for t in trades if float(t.get("pnl") or 0) > 0)
    start = cap
    end = round(start + month_pnl, 2)
    ret = round(100.0 * month_pnl / start, 3) if start else 0.0
    m["capital_start"] = round(start, 2)
    m["capital_end"] = end
    m["month_pnl"] = month_pnl
    m["month_return_pct"] = ret
    m["compound_pct"] = ret
    m["n_trades"] = len(trades)
    m["wins"] = wins
    m["losses"] = len(trades) - wins
    if year is not None:
      m["year"] = year
    # keep max_dd_pct if present (path-based; optional)
    cap = end
    all_trades.extend(trades)

  total_pnl = round(cap - float(data.get("capital_start") or START), 2)
  data["capital_end"] = round(cap, 2)
  data["total_pnl"] = total_pnl
  data["total_return_pct"] = round(100.0 * total_pnl / float(data.get("capital_start") or START), 3)
  data["n_trades"] = len(all_trades)
  data["capital_accounting"] = {
    "rule": "capital_end = capital_start + sum(trade.pnl)",
    "note": "Rebuilt after CostModel fee / broker.cash divergence fix",
    "sum_trade_pnl": round(sum(float(t.get("pnl") or 0) for t in all_trades), 2),
    "inflated_capital_end_before_fix": None,
  }
  data["claim"] = (
    "paper/session-sim only; modeled India costs ~30 bps RT in trade.pnl; "
    "book capital = start + sum(trade.pnl) (ledger identity)"
  )
  path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
  print(
    f"{path.name}: {data.get('capital_start')} -> {data['capital_end']} "
    f"({data['total_return_pct']}%) trades={data['n_trades']} "
    f"sum_pnl={data['capital_accounting']['sum_trade_pnl']}",
    flush=True,
  )
  return data


def main() -> None:
  jan_aug = ROOT / "models" / "copy_pro_jan_aug_oneshot_10k.json"
  y2025 = ROOT / "models" / "copy_pro_year_2025_oneshot_10k.json"

  # preserve pre-fix inflated ends for the audit note
  before_ja = json.loads(jan_aug.read_text(encoding="utf-8")).get("capital_end")
  before_25 = json.loads(y2025.read_text(encoding="utf-8")).get("capital_end") if y2025.exists() else None

  d_ja = rebuild(jan_aug, year=2026)
  d_ja["capital_accounting"]["inflated_capital_end_before_fix"] = before_ja
  jan_aug.write_text(json.dumps(d_ja, indent=2, default=str), encoding="utf-8")

  if y2025.exists():
    d25 = rebuild(y2025, year=2025)
    d25["capital_accounting"]["inflated_capital_end_before_fix"] = before_25
    y2025.write_text(json.dumps(d25, indent=2, default=str), encoding="utf-8")

  if DASH.exists():
    shutil.copy2(jan_aug, DASH / "oneshot_2026.json")
    if y2025.exists():
      shutil.copy2(y2025, DASH / "year_2025.json")
    print(f"copied -> {DASH}", flush=True)

  # Sync tape summary capital from rebuilt oneshot (trades already ledger-true)
  tape_path = ROOT / "models" / "godfather_desk_tape.json"
  if tape_path.exists():
    tape = json.loads(tape_path.read_text(encoding="utf-8"))
    tape["summary"] = {
      **(tape.get("summary") or {}),
      "n_trades": d_ja.get("n_trades"),
      "capital_start": d_ja.get("capital_start"),
      "capital_end": d_ja.get("capital_end"),
      "total_pnl": d_ja.get("total_pnl"),
      "total_return_pct": d_ja.get("total_return_pct"),
      "note": "Book capital = start + sum(trade.pnl); fees included in pnl",
    }
    tape["claim"] = d_ja.get("claim")
    tape_path.write_text(json.dumps(tape, indent=2, default=str), encoding="utf-8")
    if DASH.exists():
      shutil.copy2(tape_path, DASH / "tape.json")
    print(f"tape summary synced end={d_ja.get('capital_end')}", flush=True)


if __name__ == "__main__":
  main()
