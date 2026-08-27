"""July + benchmark: raw vs guard vs guard@8% risk."""

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
  report: dict = {"windows": []}
  for label, start, end in [
    ("july_chop", "2026-07-06", "2026-07-24"),
    ("benchmark_15d", "2026-08-10", "2026-08-28"),
  ]:
    days = sessions(start, end)
    print(f"=== {label} n={len(days)} ===", flush=True)
    row = {"id": label, "configs": {}}
    for name in ["in_tr10_orwidth_chase5_75x", "in_tr10_orwidth_chase5_75x_guard"]:
      kw = {k: v for k, v in ORWIDTH_HERO_CONFIGS[name].items() if k != "bar_interval"}
      variants = [(name, kw)]
      if "guard" in name:
        kw8 = dict(kw)
        kw8["max_trade_risk_pct"] = 8.0
        kw8["max_daily_loss_pct"] = 8.0
        variants.append((name + "_r8", kw8))
      for n, p in variants:
        print(f"  eval {n} ...", flush=True)
        ev = compound._eval_compound(n, days, p)
        row["configs"][n] = {
          "compound_pct": ev["compound_total_pct"],
          "worst_day_pct": ev["min_daily_return_pct"],
          "best_day_pct": ev["max_daily_return_pct"],
          "avg_daily_pct": ev["avg_daily_return_pct"],
          "final_capital": ev["final_capital_inr"],
        }
        c = row["configs"][n]
        print(
          f"  {n}: compound={c['compound_pct']:+.1f}% "
          f"worst={c['worst_day_pct']:+.1f}% best={c['best_day_pct']:+.1f}%",
          flush=True,
        )
    report["windows"].append(row)

  out = ROOT / "models" / "orwidth_guard_compare.json"
  out.write_text(json.dumps(report, indent=2), encoding="utf-8")
  print(f"Wrote {out}", flush=True)


if __name__ == "__main__":
  main()
