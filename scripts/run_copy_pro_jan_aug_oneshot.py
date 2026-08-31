"""Jan–Aug 2026 copy-pro: one-shot ₹10k, no monthly deposits."""
from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
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
from processor.smart_money_gate import (
  bulk_data_coverage,
  copy_pro_should_sitout,
  cooldown_excludes,
  empty_copy_pro_cooldown,
  register_copy_pro_outcomes,
)

START = 10_000.0
MONTHS = [
  ("january", "2026-01-01", "2026-01-31"),
  ("february", "2026-02-01", "2026-02-28"),
  ("march", "2026-03-01", "2026-03-31"),
  ("april", "2026-04-01", "2026-04-30"),
  ("may", "2026-05-01", "2026-05-31"),
  ("june", "2026-06-01", "2026-06-30"),
  ("july", "2026-07-01", "2026-07-31"),
  ("august", "2026-08-03", "2026-08-28"),
]


def sessions(a: str, b: str) -> list[str]:
  sd, ed = date.fromisoformat(a), date.fromisoformat(b)
  out = []
  d = sd
  while d <= ed:
    if d.weekday() < 5:
      out.append(d.isoformat())
    d += timedelta(days=1)
  return out


def main() -> None:
  cov = bulk_data_coverage(since="2026-01-01")
  print("bulk_coverage", cov, flush=True)
  kw = sim_kwargs_for_strategy("copy_bulk_pro", "product")
  kw.pop("bar_interval", None)
  sl = int(kw.pop("sl_cooldown_days", 1) or 1)
  ent = int(kw.pop("entity_cooldown_days", 1) or 1)
  sit = int(kw.pop("sitout_after_sl_days", 0) or 0)

  cap = START
  cd = empty_copy_pro_cooldown()
  months = []

  for name, start, end in MONTHS:
    month_start = cap
    peak = cap
    max_dd = 0.0
    trades_n = 0
    wins = 0
    print(f"\n===== {name.upper()} start=₹{month_start:,.2f} =====", flush=True)
    for asof in sessions(start, end):
      if copy_pro_should_sitout(cd):
        cd = register_copy_pro_outcomes(
          cd, [], ticker_cooldown_days=sl, entity_cooldown_days=ent, sitout_after_sl_days=sit
        )
        continue
      ex_t, ex_e = cooldown_excludes(cd)
      res = simulate_day(
        asof=asof,
        capital=cap,
        currency="INR",
        market="IN",
        path_mode="session",
        allow_demo_fallback=False,
        exclude_tickers=ex_t or None,
        exclude_entities=ex_e or None,
        **deepcopy(kw),
      )
      end_cap = float(res.get("capital_end") or cap)
      day_trades = list(res.get("trades") or [])
      trades_n += len(day_trades)
      wins += sum(1 for t in day_trades if float(t.get("pnl") or 0) > 0)
      cd = register_copy_pro_outcomes(
        cd, day_trades, ticker_cooldown_days=sl, entity_cooldown_days=ent, sitout_after_sl_days=sit
      )
      peak = max(peak, end_cap)
      max_dd = max(max_dd, 100.0 * (peak - end_cap) / peak if peak else 0.0)
      cap = end_cap

    pnl = round(cap - month_start, 2)
    pct = round(100.0 * pnl / month_start, 3) if month_start else 0.0
    row = {
      "month": name,
      "capital_start": round(month_start, 2),
      "capital_end": round(cap, 2),
      "month_pnl": pnl,
      "month_return_pct": pct,
      "max_dd_pct": round(max_dd, 2),
      "n_trades": trades_n,
      "wins": wins,
      "losses": trades_n - wins,
    }
    months.append(row)
    print(
      f"  {month_start:,.0f}→{cap:,.2f} pnl={pnl:+.2f} ({pct:+.2f}%) "
      f"dd={max_dd:.1f}% trades={trades_n}",
      flush=True,
    )

  total_pnl = round(cap - START, 2)
  out = {
    "generated_at": date.today().isoformat(),
    "rule": "one_shot_10k_no_monthly_deposits",
    "strategy": "copy_bulk_pro product (use85 + soft_trail 2.5%/1% + selective 2nd slot)",
    "params": {**kw, "sl_cooldown_days": sl, "entity_cooldown_days": ent, "sitout_after_sl_days": sit},
    "bulk_coverage": cov,
    "capital_start": START,
    "capital_end": round(cap, 2),
    "total_pnl": total_pnl,
    "total_return_pct": round(100.0 * total_pnl / START, 3),
    "months": months,
  }
  path = ROOT / "models" / "copy_pro_jan_aug_oneshot_10k.json"
  path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
  print("\n===== ONE-SHOT ₹10k =====", flush=True)
  for m in months:
    print(
      f"{m['month']:10} ₹{m['capital_start']:>10,.2f} → ₹{m['capital_end']:>10,.2f}  "
      f"({m['month_return_pct']:+.2f}%)",
      flush=True,
    )
  print(f"\nFinal: ₹{cap:,.2f}  (from ₹{START:,.0f})  pnl={total_pnl:+,.2f}  "
        f"({out['total_return_pct']:+.1f}%)", flush=True)
  print("Wrote", path, flush=True)


if __name__ == "__main__":
  main()
