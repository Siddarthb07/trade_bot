"""Full calendar 2025 copy-pro: one-shot ₹10k, no monthly deposits.

Requires NSE bulk coverage across 2025 (signals.disclosed_at). Promoted knobs
come from hybrid registry product profile for copy_bulk_pro.
"""
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
  ("january", "2025-01-01", "2025-01-31"),
  ("february", "2025-02-01", "2025-02-28"),
  ("march", "2025-03-01", "2025-03-31"),
  ("april", "2025-04-01", "2025-04-30"),
  ("may", "2025-05-01", "2025-05-31"),
  ("june", "2025-06-01", "2025-06-30"),
  ("july", "2025-07-01", "2025-07-31"),
  ("august", "2025-08-01", "2025-08-31"),
  ("september", "2025-09-01", "2025-09-30"),
  ("october", "2025-10-01", "2025-10-31"),
  ("november", "2025-11-01", "2025-11-30"),
  ("december", "2025-12-01", "2025-12-31"),
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
  cov = bulk_data_coverage(since="2025-01-01")
  print("bulk_coverage", cov, flush=True)
  if not cov.get("ok") or cov.get("data_gap"):
    raise SystemExit(f"bulk coverage gap: {cov}")

  kw = sim_kwargs_for_strategy("copy_bulk_pro", "product")
  kw.pop("bar_interval", None)
  sl = int(kw.pop("sl_cooldown_days", 1) or 1)
  ent = int(kw.pop("entity_cooldown_days", 1) or 1)
  sit = int(kw.pop("sitout_after_sl_days", 0) or 0)

  cap = START
  cd = empty_copy_pro_cooldown()
  months = []
  all_trades: list[dict] = []

  for name, start, end in MONTHS:
    month_start = cap
    peak = cap
    max_dd = 0.0
    trades_n = 0
    wins = 0
    month_trades: list[dict] = []
    print(f"\n===== {name.upper()} 2025 start=₹{month_start:,.2f} =====", flush=True)
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
      for t in day_trades:
        row_t = dict(t)
        row_t.setdefault("asof", asof)
        month_trades.append(row_t)
        all_trades.append(row_t)
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
      "compound_pct": pct,
      "max_dd_pct": round(max_dd, 2),
      "n_trades": trades_n,
      "wins": wins,
      "losses": trades_n - wins,
      "trades": month_trades,
    }
    months.append(row)
    print(
      f"  {month_start:,.0f}→{cap:,.2f} pnl={pnl:+.2f} ({pct:+.2f}%) "
      f"dd={max_dd:.1f}% trades={trades_n}",
      flush=True,
    )

  total_pnl = round(cap - START, 2)
  total_pct = round(100.0 * total_pnl / START, 3)
  out = {
    "generated_at": date.today().isoformat(),
    "strategy": "copy_bulk_pro",
    "claim": "paper/session-sim only; modeled India costs ~30 bps RT; not live fills",
    "window": {"start": "2025-01-01", "end": "2025-12-31"},
    "capital_start": START,
    "capital_end": round(cap, 2),
    "total_pnl": total_pnl,
    "total_return_pct": total_pct,
    "params": {
      "capital_use_frac": kw.get("capital_use_frac"),
      "soft_trail_arm_pct": kw.get("soft_trail_arm_pct"),
      "soft_trail_pct": kw.get("soft_trail_pct"),
      "sitout_after_sl_days": sit,
      "max_positions": kw.get("max_positions"),
      "bulk_second_min_wr": kw.get("bulk_second_min_wr"),
      "bulk_second_min_score_gap": kw.get("bulk_second_min_score_gap"),
    },
    "bulk_coverage": cov,
    "months": months,
    "n_trades": len(all_trades),
  }
  out["integrity"] = {
    "wr_source": "pit_3mo_matured_before_asof",
    "prior_session_window": "ist_deal_date_prior_weekday",
    "auto_adjust": False,
    "bulk_wr_pseudo_n": kw.get("bulk_wr_pseudo_n"),
    "bulk_min_n_trades": kw.get("bulk_min_n_trades"),
  }
  path = ROOT / "models" / "copy_pro_year_2025_oneshot_10k_clean_pit.json"
  path.write_text(json.dumps(out, indent=2), encoding="utf-8")
  print(f"\nWROTE {path}", flush=True)
  print(f"START ₹{START:,.0f} → END ₹{cap:,.2f} ({total_pct:+.2f}%) trades={len(all_trades)}", flush=True)


if __name__ == "__main__":
  main()
