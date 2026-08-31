"""Pattern Forge bake-off runner.

Default: --synthetic (no network) for CI / pre-sim gates.
Real mode: --real --start --end (uses yfinance / disk cache) only after unit tests pass.
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
from processor.no_ruin import NoRuinConfig, update_peak
from processor.pattern_forge.session import simulate_pattern_session
from processor.pattern_forge.analogs import build_library_from_paths

OUT = ROOT / "models" / "method_family_bakeoff.json"
FAMILIES = ("pattern_candle", "pattern_analog", "orb_two_sided")


def _synthetic_bars(trend: float = 0.002, n: int = 24, start: float = 100.0) -> list[dict]:
  """Wide opening range so Cost agent does not hard-skip (or_width >= 0.35%)."""
  bars = []
  # OR: ~1% width
  opens = [start, start * 1.004, start * 0.996, start * 1.002, start * 0.998]
  for o in opens:
    bars.append({"open": o, "high": o * 1.003, "low": o * 0.997, "close": o, "volume": 1000})
  px = start
  for i in range(n - 5):
    o = px
    c = px * (1.0 + trend)
    h = max(o, c) * 1.004
    l = min(o, c) * 0.996
    bars.append({"open": o, "high": h, "low": l, "close": c, "volume": 1000})
    px = c
  return bars


def _synthetic_library() -> list[dict]:
  paths = [[100 + i * 0.25 for i in range(20)] for _ in range(10)]
  fwds = [0.008] * 10
  return build_library_from_paths(paths, fwds)


def run_synthetic() -> dict:
  """Deterministic offline bake-off smoke — proves plumbing, not edge."""
  cfg = NoRuinConfig()
  lib = _synthetic_library()
  daily_hammer = [{"open": 100, "high": 101, "low": 94, "close": 100.3}]
  daily_star = [{"open": 100, "high": 106, "low": 99.5, "close": 100.1}]
  results = {}
  for fam in FAMILIES:
    cap = 10_000.0
    start = cap
    peak = cap
    trades = 0
    wins = 0
    green_days = 0
    days = 0
    floor_hits = 0
    for d in range(5):
      asof = (date(2026, 7, 1) + timedelta(days=d)).isoformat()
      days += 1
      if fam == "pattern_candle":
        daily = daily_hammer if d % 2 == 0 else daily_star
        bars = _synthetic_bars(trend=0.003 if d % 2 == 0 else -0.003)
        ticker = "RELIANCE.NS"
      elif fam == "orb_two_sided":
        bars = _synthetic_bars(trend=0.004)
        daily = daily_hammer
        ticker = "TCS.NS"
      else:
        bars = _synthetic_bars(trend=0.003)
        daily = daily_hammer
        ticker = "INFY.NS"
      out = simulate_pattern_session(
        asof=asof,
        ticker=ticker,
        session_bars=bars,
        capital=cap,
        starting_capital=start,
        peak_equity=peak,
        family=fam,
        daily_bars_before=daily,
        analog_library=lib,
        sleeve_frac=0.25,
        no_ruin_cfg=cfg,
        tau=0.0,  # synthetic: open swarm gate to exercise fill path
      )
      if out.get("no_ruin", {}).get("halted"):
        floor_hits += 1
      day_trades = out.get("trades") or []
      trades += len(day_trades)
      wins += sum(1 for t in day_trades if float(t.get("pnl") or 0) > 0)
      end = float(out.get("capital_end") or cap)
      if end > cap:
        green_days += 1
      peak = update_peak(peak, end)
      cap = end
    results[fam] = {
      "mode": "synthetic",
      "capital_start": start,
      "capital_end": round(cap, 2),
      "total_return_pct": round(100.0 * (cap - start) / start, 3),
      "n_trades": trades,
      "wins": wins,
      "green_days": green_days,
      "days": days,
      "floor_hits": floor_hits,
      "claim": "synthetic plumbing only — not an edge claim",
    }
  return {
    "generated_at": date.today().isoformat(),
    "mode": "synthetic",
    "families": results,
    "fo_universe_n": len(fo_universe_list()),
  }


def main() -> None:
  ap = argparse.ArgumentParser()
  ap.add_argument("--synthetic", action="store_true", default=True)
  ap.add_argument("--real", action="store_true", help="Reserved; refuse until unit gate documented")
  args = ap.parse_args()
  if args.real:
    raise SystemExit(
      "Real bake-off disabled until unit tests pass and oracle ceiling is logged. "
      "Run: pytest tests/test_pattern_forge_harness.py tests/test_recognition_stack.py -q"
    )
  report = run_synthetic()
  OUT.parent.mkdir(parents=True, exist_ok=True)
  OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
  print(json.dumps(report, indent=2))
  print(f"wrote {OUT}")


if __name__ == "__main__":
  main()
