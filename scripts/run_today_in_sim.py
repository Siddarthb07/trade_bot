"""One-day INR paper sim for hit rate + PnL."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.day_sim import simulate_day

ist = ZoneInfo("Asia/Kolkata")
day = datetime.now(ist).date()
while day.weekday() >= 5:
    day -= timedelta(days=1)
asof = day.isoformat()

runs = [
    ("strict", False),
    ("relaxed", False),
    ("strict", True),
]

for filter_mode, demo in runs:
    res = simulate_day(
        asof=asof,
        capital=10_000.0,
        currency="INR",
        market="IN",
        max_positions=3,
        path_mode="session",
        allow_demo_fallback=demo,
        filter_mode=filter_mode,
    )
    ps = res.get("pnl_statement") or {}
    print("---")
    print(f"asof={asof} filter={filter_mode} demo_fallback={demo}")
    print(f"mode={res.get('mode')} n_trades={res.get('n_trades')}")
    print(f"capital INR {res.get('capital_start'):,.2f} -> INR {res.get('capital_end'):,.2f}")
    print(f"realized_pnl=INR {res.get('realized_pnl'):,.2f} return={res.get('return_pct')}%")
    print(f"hit_rate={ps.get('hit_rate_pct')}% wins={ps.get('wins')} losses={ps.get('losses')} fees=INR {ps.get('fees_total')}")
    print(f"edge_valid={res.get('edge_metrics_valid')} demo={res.get('used_demo_fallback')}")
    for t in res.get("trades") or []:
        reason = (t.get("signal_reason") or "")[:90]
        print(
            f"  {t['ticker']}: put INR {t['money_put']:.2f} returned INR {t['money_returned']:.2f} "
            f"pnl INR {t['pnl']:.2f} ({t['pnl_pct']}%) exit={t['exit_reason']} | {reason}"
        )
    if not res.get("trades"):
        skips = res.get("skipped") or []
        print("  no trades; skips sample:", json.dumps(skips[:4], default=str)[:600])
