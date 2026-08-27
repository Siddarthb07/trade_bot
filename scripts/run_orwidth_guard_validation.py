"""Compare raw vs guarded OR-width heroes on breakpoint windows."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

import run_in_compound_search as compound
from processor.orwidth_product import ORWIDTH_HERO_CONFIGS

BREAK_WINDOWS = [
  {"id": "july_chop", "start": "2026-07-06", "end": "2026-07-24", "bar_interval": "auto"},
  {"id": "aug_chop", "start": "2026-08-03", "end": "2026-08-21", "bar_interval": "auto"},
  {"id": "benchmark_15d", "start": "2026-08-10", "end": "2026-08-28", "bar_interval": "auto"},
]

NAMES = [
  "in_tr10_orwidth_chase5_75x",
  "in_tr10_orwidth_chase5_75x_guard",
  "in_tr8_orwidth_chase5_75x",
  "in_tr8_orwidth_chase5_75x_guard",
]


def _sessions(start: str, end: str) -> list[str]:
  sd, ed = date.fromisoformat(start), date.fromisoformat(end)
  out: list[str] = []
  d = sd
  while d <= ed:
    if d.weekday() < 5:
      out.append(d.isoformat())
    d += timedelta(days=1)
  return out


def main() -> None:
  report: dict = {"windows": []}
  for w in BREAK_WINDOWS:
    days = _sessions(w["start"], w["end"])
    row = {"id": w["id"], "n_days": len(days), "configs": {}}
    for name in NAMES:
      kw = dict(ORWIDTH_HERO_CONFIGS[name])
      bi = w.get("bar_interval") or kw.pop("bar_interval", "auto")
      if bi != "auto":
        kw["bar_interval"] = bi
      elif "bar_interval" in kw and kw["bar_interval"] == "auto":
        kw.pop("bar_interval")
      ev = compound._eval_compound(name, days, kw)
      row["configs"][name] = {
        "compound_pct": ev["compound_total_pct"],
        "final_capital": ev["final_capital_inr"],
        "avg_daily_pct": ev["avg_daily_return_pct"],
        "worst_day_pct": ev["min_daily_return_pct"],
        "best_day_pct": ev["max_daily_return_pct"],
        "n_trades": sum(d.get("n_trades") or 0 for d in ev["days"]),
      }
    report["windows"].append(row)
    print(f"\n=== {w['id']} ===")
    for name in NAMES:
      c = row["configs"][name]
      print(
        f"  {name}: compound={c['compound_pct']:+.1f}% "
        f"worst={c['worst_day_pct']:+.1f}% best={c['best_day_pct']:+.1f}%"
      )

  out = ROOT / "models" / "orwidth_guard_validation.json"
  out.write_text(json.dumps(report, indent=2), encoding="utf-8")
  print(f"\nWrote {out}")


if __name__ == "__main__":
  main()
