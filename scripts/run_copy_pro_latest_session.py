"""Run copy_bulk_pro use60 for the latest completed NSE session."""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
os.environ.setdefault(
  "POSTGRES_URL",
  "postgresql://smartmoney:changeme@127.0.0.1:5433/smartmoney",
)

from processor.day_sim import simulate_day
from processor.hybrid.registry import sim_kwargs_for_strategy
from processor.smart_money_gate import bulk_data_coverage

CAPITAL = 10_000.0


def last_nse_session(today: date | None = None) -> date:
  d = today or date.today()
  # walk back to Fri if weekend; skip Sat/Sun
  while d.weekday() >= 5:
    d -= timedelta(days=1)
  return d


def main() -> None:
  today = date.today()
  asof_d = last_nse_session(today)
  asof = asof_d.isoformat()
  note = None
  if today != asof_d:
    note = f"Calendar is {today.isoformat()} ({today.strftime('%A')}); NSE closed. Using last session {asof}."

  kw = sim_kwargs_for_strategy("copy_bulk_pro", "product")
  kw.pop("bar_interval", None)
  kw.pop("sl_cooldown_days", None)
  kw.pop("entity_cooldown_days", None)
  kw.pop("sitout_after_sl_days", None)

  cov = bulk_data_coverage()
  print("NOTE:", note or f"Running for today {asof}", flush=True)
  print("bulk_coverage:", cov, flush=True)
  print("params:", kw, flush=True)
  print(f"simulate_day asof={asof} capital={CAPITAL}", flush=True)

  res = simulate_day(
    asof=asof,
    capital=CAPITAL,
    currency="INR",
    market="IN",
    path_mode="session",
    allow_demo_fallback=False,
    **kw,
  )

  trades = res.get("trades") or []
  out = {
    "calendar_today": today.isoformat(),
    "session_asof": asof,
    "session_note": note,
    "capital_start": CAPITAL,
    "capital_end": res.get("capital_end"),
    "pnl_inr": round(float(res.get("capital_end") or CAPITAL) - CAPITAL, 2),
    "return_pct": res.get("return_pct"),
    "n_trades": res.get("n_trades"),
    "skipped": res.get("skipped") or res.get("skip_reasons"),
    "params": kw,
    "bulk_coverage": cov,
    "trades": [
      {
        "ticker": t.get("ticker"),
        "pnl": t.get("pnl"),
        "pnl_pct": t.get("pnl_pct"),
        "lev": t.get("lev") or t.get("leverage"),
        "entry_px": t.get("entry_px") or t.get("entry_price"),
        "exit_px": t.get("exit_px") or t.get("exit_price"),
        "entry_notional": t.get("entry_notional") or t.get("money_put"),
        "exit_notional": t.get("exit_notional") or t.get("money_returned"),
        "slot_capital": t.get("slot_capital"),
        "qty": t.get("qty"),
        "exit": t.get("exit") or t.get("exit_reason"),
        "fees": t.get("fees"),
        "entry_ts": t.get("entry_ts"),
        "exit_ts": t.get("exit_ts"),
      }
      for t in trades
    ],
    "raw_keys": sorted(res.keys()),
  }
  path = ROOT / "models" / "copy_pro_session_latest.json"
  path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
  print(json.dumps({k: out[k] for k in out if k != "raw_keys"}, indent=2, default=str))
  print("Wrote", path, flush=True)


if __name__ == "__main__":
  main()
