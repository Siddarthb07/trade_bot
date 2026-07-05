#!/usr/bin/env python3
"""Backfill NSE archive + historical data."""

from __future__ import annotations

import sys
import time

from ingest.nse import backfill_nse_archive, backfill_nse_historical


def _retry_historical(days: int, max_attempts: int, pause_sec: int) -> dict:
  last: dict = {"rows_in": 0, "rows_new": 0}
  for attempt in range(1, max_attempts + 1):
    print(f"historical attempt {attempt}/{max_attempts} (days={days})")
    last = backfill_nse_historical(days=days)
    print(last)
    if last.get("rows_new", 0) > 0:
      return last
    if last.get("status") == "ok" and last.get("rows_in", 0) > 0:
      return last
    if attempt < max_attempts:
      print(f"sleeping {pause_sec}s before retry…")
      time.sleep(pause_sec)
  return last


def main() -> None:
  if len(sys.argv) > 1 and sys.argv[1] == "historical":
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    result = backfill_nse_historical(days=days)
  elif len(sys.argv) > 1 and sys.argv[1] == "retry":
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 180
    attempts = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    pause = int(sys.argv[4]) if len(sys.argv) > 4 else 30
    result = _retry_historical(days, attempts, pause)
  else:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    result = backfill_nse_archive(limit=limit)
  print(result)


if __name__ == "__main__":
  main()
