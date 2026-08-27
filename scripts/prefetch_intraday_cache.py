"""Bulk-download intraday bars to disk cache for stress-test windows."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.day_sim import IN_UNIVERSE_VOLATILE
from processor.intraday_bars import fetch_intraday_bars, pick_interval_for_date

CACHE_DIR = ROOT / "models" / "intraday_cache"


def _trading_days_between(start: date, end: date) -> list[str]:
  out: list[str] = []
  d = start
  while d <= end:
    if d.weekday() < 5:
      out.append(d.isoformat())
    d += timedelta(days=1)
  return out


def main() -> None:
  ap = argparse.ArgumentParser(description="Prefetch intraday bars for OR-width stress windows")
  ap.add_argument("--from-report", type=str, default="", help="orwidth_stress_report or checkpoint JSON")
  ap.add_argument("--start", type=str, default="2026-03-01")
  ap.add_argument("--end", type=str, default="")
  ap.add_argument("--interval", type=str, default="auto", choices=["auto", "5m", "1h"])
  ap.add_argument("--sleep", type=float, default=0.35, help="seconds between tickers")
  args = ap.parse_args()

  ist = ZoneInfo("Asia/Kolkata")
  end = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else datetime.now(ist).date()
  days: set[str] = set()

  if args.from_report:
    p = Path(args.from_report)
    if not p.is_absolute():
      p = ROOT / p
    data = json.loads(p.read_text(encoding="utf-8"))
    for w in data.get("windows") or []:
      for d in w.get("sessions") or []:
        days.add(d)
  else:
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    days = set(_trading_days_between(start, end))

  tickers = IN_UNIVERSE_VOLATILE
  print(f"Prefetch {len(days)} sessions x {len(tickers)} tickers | interval={args.interval}")
  ok = miss = 0
  for i, day in enumerate(sorted(days)):
    iv = "1h" if args.interval == "1h" else pick_interval_for_date(day, args.interval)
    for ticker in tickers:
      bars = fetch_intraday_bars(ticker, session_date=day, interval=iv, market="IN", lookback_days=10)
      if bars:
        ok += 1
      else:
        miss += 1
      time.sleep(args.sleep)
    if (i + 1) % 5 == 0:
      print(f"  ... {i + 1}/{len(days)} days | cached_ok={ok} miss={miss}", flush=True)

  n_files = sum(1 for _ in CACHE_DIR.rglob("*.json"))
  print(f"Done. fetches ok={ok} miss={miss} | disk files={n_files} | cache={CACHE_DIR}")


if __name__ == "__main__":
  main()
