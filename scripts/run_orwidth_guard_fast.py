"""Fast raw vs guard compare — one window, unbuffered progress."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_in_compound_search as compound
from processor.orwidth_product import ORWIDTH_HERO_CONFIGS

WINDOW = ("benchmark_15d", "2026-08-10", "2026-08-28")
NAMES = ["in_tr10_orwidth_chase5_75x", "in_tr10_orwidth_chase5_75x_guard"]


def sessions(start: str, end: str) -> list[str]:
  sd, ed = date.fromisoformat(start), date.fromisoformat(end)
  out: list[str] = []
  d = sd
  while d <= ed:
    if d.weekday() < 5:
      out.append(d.isoformat())
    d += timedelta(days=1)
  return out


def main() -> None:
  wid, start, end = WINDOW
  days = sessions(start, end)
  print(f"window={wid} days={len(days)}", flush=True)
  report = {"id": wid, "configs": {}}
  for name in NAMES:
    print(f"eval {name} ...", flush=True)
    kw = {k: v for k, v in ORWIDTH_HERO_CONFIGS[name].items() if k != "bar_interval"}
    ev = compound._eval_compound(name, days, kw)
    row = {
      "compound_pct": ev["compound_total_pct"],
      "final_capital": ev["final_capital_inr"],
      "avg_daily_pct": ev["avg_daily_return_pct"],
      "worst_day_pct": ev["min_daily_return_pct"],
      "best_day_pct": ev["max_daily_return_pct"],
      "days": [
        {"asof": d["asof"], "ret": d["return_pct"], "n": d["n_trades"]} for d in ev["days"]
      ],
    }
    report["configs"][name] = row
    print(
      f"  compound={row['compound_pct']:+.1f}% worst={row['worst_day_pct']:+.1f}% "
      f"best={row['best_day_pct']:+.1f}%",
      flush=True,
    )
  out = ROOT / "models" / "orwidth_guard_fast.json"
  out.write_text(json.dumps(report, indent=2), encoding="utf-8")
  print(f"Wrote {out}", flush=True)


if __name__ == "__main__":
  main()
