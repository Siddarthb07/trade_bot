"""Day-by-day break-point report for hero OR-width configs on worst windows."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

import run_in_compound_search as compound

BREAK_WINDOWS = [
  {
    "id": "march_crash",
    "label": "historical_bad",
    "start": "2026-03-09",
    "end": "2026-03-27",
    "nifty_return_pct": -10.59,
    "bar_interval": "1h",
  },
  {
    "id": "july_chop",
    "label": "bad_market",
    "start": "2026-07-06",
    "end": "2026-07-24",
    "nifty_return_pct": -2.71,
    "bar_interval": "auto",
  },
  {
    "id": "aug_chop",
    "label": "bad_market",
    "start": "2026-08-03",
    "end": "2026-08-21",
    "nifty_return_pct": -2.11,
    "bar_interval": "auto",
  },
  {
    "id": "benchmark_15d",
    "label": "benchmark",
    "start": "2026-08-10",
    "end": "2026-08-28",
    "nifty_return_pct": -1.66,
    "bar_interval": "auto",
  },
]

CONFIGS = [
  {
    "name": "in_tr10_orwidth_chase5_75x",
    "filter_mode": "target_return",
    "max_leverage": 75.0,
    "conf_floor": 0.48,
    "min_or_pct": 0.0015,
    "target_return_pct": 10.0,
    "exit_at_session_end": True,
    "rank_by": "or_width",
    "max_chase_attempts": 5,
    "bar_interval": "auto",
  },
  {
    "name": "in_tr8_orwidth_chase5_75x",
    "filter_mode": "target_return",
    "max_leverage": 75.0,
    "conf_floor": 0.48,
    "min_or_pct": 0.0015,
    "target_return_pct": 8.0,
    "exit_at_session_end": True,
    "rank_by": "or_width",
    "max_chase_attempts": 5,
    "bar_interval": "auto",
  },
]


def _sessions(start: str, end: str) -> list[str]:
  sd, ed = date.fromisoformat(start), date.fromisoformat(end)
  out: list[str] = []
  d = sd
  while d <= ed:
    if d.weekday() < 5:
      out.append(d.isoformat())
    d += timedelta(days=1)
  return out[-15:]


def main() -> None:
  report: dict = {"windows": []}
  print("OR-width break-point analysis\n")
  for win in BREAK_WINDOWS:
    days = _sessions(win["start"], win["end"])
    print(f"=== {win['id']} {win['start']}->{win['end']} NIFTY {win['nifty_return_pct']}% ({win['bar_interval']}) ===")
    block = {**win, "sessions": days, "configs": {}}
    for cfg in CONFIGS:
      kw = {k: v for k, v in cfg.items() if k != "name"}
      kw["bar_interval"] = win["bar_interval"]
      r = compound._eval_compound(cfg["name"], days, kw)
      block["configs"][cfg["name"]] = r
      losers = [d for d in r["days"] if d["return_pct"] < -5]
      print(
        f"  {cfg['name']}: compound {r['compound_total_pct']:+.1f}% | "
        f"min {r['min_daily_return_pct']:+.1f}% | worst days {len(losers)}"
      )
      for d in sorted(r["days"], key=lambda x: x["return_pct"])[:3]:
        tr = (d.get("trades") or [{}])[0]
        print(
          f"    BREAK {d['asof']}: {d['return_pct']:+.1f}% | {tr.get('ticker','?')} "
          f"lev={tr.get('lev')} move={tr.get('pnl_pct')}% exit={tr.get('exit')}"
        )
    report["windows"].append(block)
    print()

  out = ROOT / "models" / "orwidth_breakpoint_report.json"
  out.write_text(json.dumps(report, indent=2), encoding="utf-8")
  print(f"Report: {out}")


if __name__ == "__main__":
  main()
