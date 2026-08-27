"""Quick leverage push on hero OR-width config — single 15d window."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

import run_in_compound_search as compound

BASE = {
  "filter_mode": "target_return",
  "conf_floor": 0.48,
  "min_or_pct": 0.0015,
  "target_return_pct": 10.0,
  "exit_at_session_end": True,
  "rank_by": "or_width",
  "max_chase_attempts": 5,
  "bar_interval": "auto",
}

# Latest 15 sessions (same as benchmark)
LEVS = [50, 75, 100, 125, 150, 175, 200]


def main() -> None:
  from datetime import timedelta

  ist = ZoneInfo("Asia/Kolkata")
  end = datetime.now(ist).date()
  while end.weekday() >= 5:
    end -= timedelta(days=1)
  days = compound._trading_days(end, 15)
  print(f"Leverage push tr10 orwidth chase5 | {days[0]} -> {days[-1]}")
  rows = []
  for lev in LEVS:
    name = f"tr10_orwidth_chase5_{lev}x"
    kw = {**BASE, "max_leverage": float(lev)}
    r = compound._eval_compound(name, days, kw)
    rows.append(r)
    print(
      f"  {lev}x: compound {r['compound_total_pct']:+.1f}% | min-day {r['min_daily_return_pct']:+.1f}% | "
      f"max-day {r['max_daily_return_pct']:+.1f}% | final INR {r['final_capital_inr']}"
    )
  out = ROOT / "models" / "orwidth_leverage_push_report.json"
  out.write_text(json.dumps({"sessions": days, "results": rows}, indent=2), encoding="utf-8")
  print(f"Report: {out}")


if __name__ == "__main__":
  main()
