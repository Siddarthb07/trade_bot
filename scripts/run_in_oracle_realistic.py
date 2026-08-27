"""Realistic oracle sim: perfect ticker pick + session-end exit + costs + leverage.

Diagnostic only — uses same-day best ORB->session-close move (not high) to bound
what a perfect selector could earn with the paper broker model.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from broker.paper import PaperBroker
from processor.costs import cost_model_for
from processor.day_sim import IN_UNIVERSE_VOLATILE
from processor.intraday_bars import fetch_intraday_bars
from processor.strategies import session_or_breakout
from broker.sizing import leverage_for_target

START = 10_000.0
N_DAYS = 12
TARGETS = (8.0, 10.0)
MAX_LEV = 75.0


def _days(end: date, n: int) -> list[str]:
  out: list[str] = []
  d = end
  while len(out) < n:
    if d.weekday() < 5:
      out.append(d.isoformat())
    d -= timedelta(days=1)
  return list(reversed(out))


def _best_close_move(asof: str) -> tuple[str, float, float]:
  """Return (ticker, move_to_session_close_pct, or_width_pct) for best buy breakout."""
  best = ("-", 0.0, 0.0)
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
    close_px = float(bars[-1].get("close") or entry)
    move = 100.0 * (close_px / entry - 1.0)
    or_w = float(sob.get("or_width_pct") or 0)
    if move > best[1]:
      best = (ticker, move, or_w)
  return best


def _sim_day(asof: str, capital: float, target_pct: float) -> dict:
  ticker, move_pct, or_w = _best_close_move(asof)
  if ticker == "-" or move_pct <= 0:
    return {"asof": asof, "return_pct": 0.0, "capital_end": capital, "ticker": None, "move_pct": 0.0}

  cm = cost_model_for("IN")
  broker = PaperBroker("IN", starting_cash=capital, currency="INR", leverage_max=MAX_LEV)
  exp = max(or_w, abs(move_pct) / 100.0, 0.004)
  lev = leverage_for_target(target_pct / 100.0, exp, max_leverage=MAX_LEV)
  notional = capital * lev
  notional = min(notional, broker.buying_power() * 0.98)
  px = 100.0  # normalized; PnL from move_pct
  qty = notional / px
  fee = cm.fee_on_notional(notional, sides=2)
  gross = notional * (move_pct / 100.0)
  pnl = gross - fee
  cap_end = max(broker.cash + pnl - broker.borrowed, 0.0)
  ret = 100.0 * (cap_end - capital) / capital
  return {
    "asof": asof,
    "return_pct": round(ret, 3),
    "capital_end": round(cap_end, 2),
    "ticker": ticker,
    "move_pct": round(move_pct, 3),
    "lev": round(lev, 2),
    "target_pct": target_pct,
  }


def main() -> None:
  ist = ZoneInfo("Asia/Kolkata")
  end = datetime.now(ist).date()
  while end.weekday() >= 5:
    end -= timedelta(days=1)
  days = _days(end, N_DAYS)
  print(f"IN oracle-realistic (session-close, costs) | {days[0]} -> {days[-1]}")
  report: dict = {"sessions": days, "targets": {}}
  for tgt in TARGETS:
    cap = START
    rows = []
    for asof in days:
      row = _sim_day(asof, cap, tgt)
      cap = float(row["capital_end"])
      rows.append(row)
    mins = min(r["return_pct"] for r in rows)
    ge8 = sum(1 for r in rows if r["return_pct"] >= 8.0)
    ge10 = sum(1 for r in rows if r["return_pct"] >= 10.0)
    report["targets"][str(tgt)] = {
      "min_daily_return_pct": mins,
      "days_ge_8": ge8,
      "days_ge_10": ge10,
      "all_ge_8": ge8 == len(days),
      "all_ge_10": ge10 == len(days),
      "compound_pct": round(100.0 * (cap - START) / START, 2),
      "days": rows,
    }
    print(f"\nTarget {tgt}%/day @ max {MAX_LEV}x lev")
    print(f"  min/day {mins:.2f}% | compound {report['targets'][str(tgt)]['compound_pct']:.1f}% | ALL>=8% {report['targets'][str(tgt)]['all_ge_8']}")
    for r in rows:
      print(f"  {r['asof']} {str(r.get('ticker') or '-'):<14} move={r.get('move_pct', 0):>6.2f}% ret={r['return_pct']:>7.2f}%")

  out = ROOT / "models" / "in_oracle_realistic_report.json"
  out.write_text(json.dumps(report, indent=2), encoding="utf-8")
  print(f"\nReport: {out}")


if __name__ == "__main__":
  main()
