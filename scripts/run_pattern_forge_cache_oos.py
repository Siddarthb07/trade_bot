"""Cache-only Pattern Forge month runner (no network).

Uses models/intraday_cache only. Skips days/tickers with missing bars.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.fo_universe import fo_universe_list
from processor.intraday_bars import load_disk_session_bars
from processor.no_ruin import NoRuinConfig, update_peak
from processor.pattern_forge.session import simulate_pattern_session

OUT_DEFAULT = ROOT / "models" / "pattern_forge_cache_oos.json"


def sessions(a: str, b: str) -> list[str]:
  sd, ed = date.fromisoformat(a), date.fromisoformat(b)
  out = []
  d = sd
  while d <= ed:
    if d.weekday() < 5:
      out.append(d.isoformat())
    d += timedelta(days=1)
  return out


def pick_ticker_for_day(asof: str, universe: list[str], family: str) -> tuple[str, list[dict]] | None:
  # Prefer first FO name with cached bars that day
  for t in universe:
    bars = load_disk_session_bars(t, asof, interval="5m")
    if len(bars) >= 12:
      return t, bars
  return None


def build_analog_library(
  ticker: str,
  asof: str,
  *,
  lookback_sessions: int = 40,
  path_len: int = 20,
) -> list[dict]:
  """Expanding-window library from disk cache strictly before asof."""
  lib: list[dict] = []
  d = date.fromisoformat(asof) - timedelta(days=1)
  used = 0
  while used < lookback_sessions:
    if d.weekday() < 5:
      bars = load_disk_session_bars(ticker, d.isoformat())
      if len(bars) >= path_len + 2:
        closes = [float(b["close"]) for b in bars]
        path = closes[:path_len]
        fwd = closes[-1] / closes[path_len] - 1.0 if closes[path_len] else 0.0
        lib.append({"id": f"{ticker}:{d.isoformat()}", "path": path, "forward_ret": fwd})
        used += 1
    d -= timedelta(days=1)
    if (date.fromisoformat(asof) - d).days > 180:
      break
  return lib


def run_window(
  *,
  family: str,
  start: str,
  end: str,
  capital: float = 10_000.0,
  universe: list[str] | None = None,
) -> dict:
  cfg = NoRuinConfig()
  uni = universe or fo_universe_list()[:15]
  cap = capital
  book_start = capital
  peak = capital
  trades_n = 0
  wins = 0
  skips = 0
  floor_hits = 0
  day_rows = []
  for asof in sessions(start, end):
    picked = pick_ticker_for_day(asof, uni, family)
    if not picked:
      skips += 1
      day_rows.append({"asof": asof, "skip": "no_cache_bars"})
      continue
    ticker, bars = picked
    # prior-day daily proxy from earlier session closes if available
    daily = []
    prev = date.fromisoformat(asof) - timedelta(days=1)
    for _ in range(5):
      if prev.weekday() < 5:
        pb = load_disk_session_bars(ticker, prev.isoformat())
        if pb:
          daily = [
            {
              "open": float(pb[0]["open"]),
              "high": max(float(b["high"]) for b in pb),
              "low": min(float(b["low"]) for b in pb),
              "close": float(pb[-1]["close"]),
            }
          ]
          break
      prev -= timedelta(days=1)
    analog_lib = build_analog_library(ticker, asof) if family == "pattern_analog" else None
    out = simulate_pattern_session(
      asof=asof,
      ticker=ticker,
      session_bars=bars,
      capital=cap,
      starting_capital=book_start,
      peak_equity=peak,
      family=family,
      daily_bars_before=daily,
      analog_library=analog_lib,
      sleeve_frac=0.25,
      no_ruin_cfg=cfg,
    )
    if out.get("no_ruin", {}).get("halted"):
      floor_hits += 1
    day_trades = out.get("trades") or []
    trades_n += len(day_trades)
    wins += sum(1 for t in day_trades if float(t.get("pnl") or 0) > 0)
    end_cap = float(out.get("capital_end") or cap)
    day_rows.append(
      {
        "asof": asof,
        "ticker": ticker,
        "pnl": round(end_cap - cap, 2),
        "n_trades": len(day_trades),
        "skip": out.get("skip_reason"),
        "exit": day_trades[0].get("exit_reason") if day_trades else None,
      }
    )
    if not day_trades:
      skips += 1
    peak = update_peak(peak, end_cap)
    cap = end_cap
    if floor_hits and out.get("no_ruin", {}).get("halted"):
      break
  return {
    "family": family,
    "window": {"start": start, "end": end},
    "capital_start": book_start,
    "capital_end": round(cap, 2),
    "total_return_pct": round(100.0 * (cap - book_start) / book_start, 3),
    "n_trades": trades_n,
    "wins": wins,
    "skips": skips,
    "floor_hits": floor_hits,
    "days": day_rows,
    "claim": "cache-only paper path; modeled ~30bps RT; not live fills",
  }


def main() -> None:
  ap = argparse.ArgumentParser()
  ap.add_argument("--start", default="2026-07-01")
  ap.add_argument("--end", default="2026-08-28")
  ap.add_argument("--family", default="all", choices=["all", *("pattern_candle", "pattern_analog", "orb_two_sided")])
  ap.add_argument("--out", default=str(OUT_DEFAULT))
  args = ap.parse_args()
  fams = ("pattern_candle", "pattern_analog", "orb_two_sided") if args.family == "all" else (args.family,)
  report = {
    "generated_at": date.today().isoformat(),
    "mode": "cache_only",
    "families": {},
  }
  for fam in fams:
    print(f"=== {fam} {args.start}->{args.end} ===", flush=True)
    row = run_window(family=fam, start=args.start, end=args.end)
    report["families"][fam] = row
    print(
      f"  end=₹{row['capital_end']:,.2f} ret={row['total_return_pct']:+.2f}% "
      f"trades={row['n_trades']} floor_hits={row['floor_hits']}",
      flush=True,
    )
  Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
  print("wrote", args.out)


if __name__ == "__main__":
  main()
