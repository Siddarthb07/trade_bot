"""Upper-bound diagnostic: best achievable same-day return per session (IN).

Uses vol-universe ORB entry -> session high (no costs). Informs whether 8%/10% daily is
reachable on historical bars before leverage/sizing.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.day_sim import IN_UNIVERSE_VOLATILE
from processor.intraday_bars import fetch_intraday_bars
from processor.strategies import session_or_breakout

N_DAYS = 12


def _days(end: date, n: int) -> list[str]:
  out: list[str] = []
  d = end
  while len(out) < n:
    if d.weekday() < 5:
      out.append(d.isoformat())
    d -= timedelta(days=1)
  return list(reversed(out))


def main() -> None:
  ist = ZoneInfo("Asia/Kolkata")
  end = datetime.now(ist).date()
  while end.weekday() >= 5:
    end -= timedelta(days=1)
  days = _days(end, N_DAYS)
  print(f"IN oracle upper bound | {days[0]} -> {days[-1]} | universe={len(IN_UNIVERSE_VOLATILE)}")
  print(f"{'date':<12} {'best':<14} {'move%':>8} {'@10x':>8} {'@25x':>8} {'@50x':>8}")
  mins: list[float] = []
  for asof in days:
    best_move = 0.0
    best_t = "-"
    for ticker in IN_UNIVERSE_VOLATILE:
      bars = fetch_intraday_bars(ticker, session_date=asof, interval="5m", market="IN")
      if len(bars) < 12:
        continue
      sob = session_or_breakout(bars)
      if sob.get("side") != "buy":
        continue
      entry_i = int(sob.get("entry_i") or 0)
      entry = float(sob.get("entry_px") or 0)
      if entry <= 0:
        continue
      highs = [float(b.get("high") or b["close"]) for b in bars]
      max_hi = max(highs[entry_i:], default=entry)
      move = 100.0 * (max_hi / entry - 1.0)
      if move > best_move:
        best_move = move
        best_t = ticker
    mins.append(best_move)
    print(
      f"{asof:<12} {best_t:<14} {best_move:>7.3f}% "
      f"{best_move*10:>7.1f}% {best_move*25:>7.1f}% {best_move*50:>7.1f}%"
    )
  ge8 = sum(1 for m in mins if m * 50 >= 8.0)  # rough: 50x on move
  ge10 = sum(1 for m in mins if m * 50 >= 10.0)
  print()
  print(f"Days where best ORB->high move * 50x >= 8%: {ge8}/{len(days)}")
  print(f"Days where best ORB->high move * 50x >= 10%: {ge10}/{len(days)}")
  print(f"Min best-move day: {min(mins):.3f}% ticker-oracle (before costs/slippage)")


if __name__ == "__main__":
  main()
