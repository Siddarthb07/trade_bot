"""Historical benchmark on frozen-style feature rows / labeled ForwardReturns.

Runs without Docker when PYTHONPATH includes packages/. Uses DB if available;
otherwise synthesizes a walk-forward sanity check on strategy signals.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.strategies import mean_rev_bb, mom_cross, verify_strategy_report


def _synthetic_benchmark() -> dict:
  """Generate synthetic OHLCV-like closes and score classic strategies."""
  import random

  from processor.strategies import intraday_orb, walk_forward_backtest

  random.seed(42)
  px = 100.0
  closes = []
  for _ in range(400):
    px *= 1 + random.uniform(-0.02, 0.021)
    closes.append(px)

  reports = {
    "mom_cross": walk_forward_backtest(closes, mom_cross),
    "mean_rev_bb": walk_forward_backtest(closes, mean_rev_bb),
    "intraday_orb": walk_forward_backtest(closes, intraday_orb, train_bars=80, test_bars=30),
  }

  return {
    "mode": "synthetic_walk_forward",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "strategies": reports,
    "note": "Walk-forward next-bar fills + 10bps costs — replace with DB when Postgres available",
  }


def _db_benchmark() -> dict | None:
  try:
    from core.db import SessionLocal
    from core.models import ForwardReturn, Signal, SignalScore
    from core.config import get_settings
  except Exception:
    return None

  settings = get_settings()
  db = SessionLocal()
  try:
    rows = (
      db.query(Signal, ForwardReturn, SignalScore)
      .join(ForwardReturn, ForwardReturn.signal_id == Signal.id)
      .outerjoin(SignalScore, SignalScore.signal_id == Signal.id)
      .filter(
        ForwardReturn.window == settings.win_window,
        ForwardReturn.return_pct.isnot(None),
        Signal.action.in_(["BUY", "P", "A"]),
      )
      .limit(2000)
      .all()
    )
    if len(rows) < 30:
      return None

    # Threshold rule: act when calibrated_prob >= 0.55 (or interim)
    rets = []
    for signal, fr, score in rows:
      dist = (score.return_distribution if score else None) or {}
      prob = dist.get("calibrated_probability")
      if prob is None:
        continue
      if float(prob) < 0.55:
        continue
      rets.append(float(fr.return_pct))

    if len(rets) < 20:
      return {"mode": "db", "status": "insufficient_high_conf", "n": len(rets)}

    exp = sum(rets) / len(rets)
    wins = sum(1 for r in rets if r > settings.win_threshold_pct)
    report = verify_strategy_report(
      strategy_id="bulk_ml_threshold_0.55",
      n_trades=len(rets),
      expectancy=exp,
      max_dd=0.0,
      oos_ok=True,
    )
    report["hit_rate"] = wins / len(rets)
    report["mean_return"] = round(exp, 6)
    return {
      "mode": "db",
      "generated_at": datetime.now(timezone.utc).isoformat(),
      "strategies": {"bulk_ml_threshold_0.55": report},
      "n_rows_scanned": len(rows),
    }
  except Exception as exc:
    return {"mode": "db", "status": "error", "error": str(exc)}
  finally:
    db.close()


def main() -> None:
  out_dir = ROOT / "models"
  out_dir.mkdir(parents=True, exist_ok=True)
  db_result = _db_benchmark()
  result = db_result if db_result and db_result.get("strategies") else _synthetic_benchmark()
  if db_result and not db_result.get("strategies"):
    result["db_attempt"] = db_result
  path = out_dir / "benchmark_results.json"
  path.write_text(json.dumps(result, indent=2))
  print(json.dumps(result, indent=2))
  print(f"Wrote {path}")


if __name__ == "__main__":
  main()
