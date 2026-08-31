"""Jan–Aug 2026 copy-pro year run with monthly deposits.

Rule: start ₹10k. After each calendar month's trading:
  deposit = ₹10,000 + 50% of that month's profit (0 if month PnL ≤ 0)
  next book = capital_end + deposit

Uses promoted product defaults (use85 + soft trail + selective 2nd slot).
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

START_CAPITAL = 10_000.0
MONTHLY_TOP_UP = 10_000.0
PROFIT_REINVEST_FRAC = 0.5

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
  out: list[str] = []
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
  print("params", {**kw, "sl_cooldown_days": sl, "entity_cooldown_days": ent, "sitout": sit}, flush=True)

  cap = START_CAPITAL
  cd = empty_copy_pro_cooldown()
  months_out: list[dict] = []
  total_deposited = START_CAPITAL
  total_profit_reinvested = 0.0

  for name, start, end in MONTHS:
    days = sessions(start, end)
    month_start = cap
    trades_n = 0
    wins = 0
    peak = cap
    max_dd = 0.0
    n_flat = 0
    n_sit = 0

    print(f"\n===== {name.upper()} {start}..{end} start=₹{month_start:,.2f} =====", flush=True)
    for asof in days:
      if copy_pro_should_sitout(cd):
        n_sit += 1
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
      if not day_trades:
        n_flat += 1
      trades_n += len(day_trades)
      wins += sum(1 for t in day_trades if float(t.get("pnl") or 0) > 0)
      cd = register_copy_pro_outcomes(
        cd,
        day_trades,
        ticker_cooldown_days=sl,
        entity_cooldown_days=ent,
        sitout_after_sl_days=sit,
      )
      peak = max(peak, end_cap)
      max_dd = max(max_dd, 100.0 * (peak - end_cap) / peak if peak else 0.0)
      cap = end_cap

    month_end_trade = cap
    month_pnl = round(month_end_trade - month_start, 2)
    month_pct = round(100.0 * month_pnl / month_start, 3) if month_start else 0.0
    profit_bonus = round(PROFIT_REINVEST_FRAC * month_pnl, 2) if month_pnl > 0 else 0.0
    deposit = round(MONTHLY_TOP_UP + profit_bonus, 2)
    cap = round(month_end_trade + deposit, 2)
    total_deposited += MONTHLY_TOP_UP
    total_profit_reinvested += profit_bonus

    row = {
      "month": name,
      "window": {"start": start, "end": end, "n_sessions": len(days)},
      "capital_start": round(month_start, 2),
      "capital_end_trading": round(month_end_trade, 2),
      "month_pnl": month_pnl,
      "month_return_pct": month_pct,
      "max_dd_pct": round(max_dd, 2),
      "n_trades": trades_n,
      "wins": wins,
      "losses": trades_n - wins,
      "n_flat_days": n_flat,
      "n_sitout_days": n_sit,
      "deposit_top_up": MONTHLY_TOP_UP,
      "deposit_profit_bonus_50pct": profit_bonus,
      "deposit_total": deposit,
      "capital_after_deposit": cap,
    }
    months_out.append(row)
    print(
      f"  trade {month_start:,.0f}→{month_end_trade:,.2f} pnl={month_pnl:+.2f} ({month_pct:+.2f}%) "
      f"dd={max_dd:.1f}% trades={trades_n}",
      flush=True,
    )
    print(
      f"  deposit +₹{MONTHLY_TOP_UP:,.0f} +50%profit ₹{profit_bonus:,.2f} = ₹{deposit:,.2f} "
      f"→ book ₹{cap:,.2f}",
      flush=True,
    )

  final = months_out[-1]["capital_after_deposit"] if months_out else START_CAPITAL
  # Cash put in by user = start + 7 more month-end top-ups after Jan..Jul? 
  # We add top-up after EVERY month including August.
  # Start 10k + 8 monthly top-ups = 90k external cash; profit bonuses are from trading.
  external_cash = START_CAPITAL + MONTHLY_TOP_UP * len(MONTHS)
  trading_pnl_sum = round(sum(m["month_pnl"] for m in months_out), 2)
  out = {
    "generated_at": date.today().isoformat(),
    "rule": {
      "start_capital": START_CAPITAL,
      "monthly_top_up": MONTHLY_TOP_UP,
      "profit_reinvest_frac": PROFIT_REINVEST_FRAC,
      "profit_bonus": "0.5 * max(0, month_pnl) added with the 10k at each month end",
      "final_includes_august_deposit": True,
    },
    "strategy": "copy_bulk_pro product (use85 + soft_trail 2.5%/1% + selective 2nd slot)",
    "params": {**kw, "sl_cooldown_days": sl, "entity_cooldown_days": ent, "sitout_after_sl_days": sit},
    "bulk_coverage": cov,
    "months": months_out,
    "summary": {
      "final_book_after_august_deposit": round(final, 2),
      "external_cash_in": round(external_cash, 2),
      "sum_month_trading_pnl": trading_pnl_sum,
      "sum_profit_bonuses_reinvested": round(total_profit_reinvested, 2),
      "gain_vs_external_cash": round(final - external_cash, 2),
      "gain_vs_external_pct": round(100.0 * (final - external_cash) / external_cash, 3) if external_cash else None,
    },
  }
  path = ROOT / "models" / "copy_pro_jan_aug_deposit_compound.json"
  path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")

  print("\n===== MONTH-END BOOK (after ₹10k + 50% profit deposit) =====", flush=True)
  for m in months_out:
    print(
      f"{m['month']:10} trade_pnl={m['month_pnl']:+8.2f}  "
      f"after_trade=₹{m['capital_end_trading']:>10,.2f}  "
      f"deposit=₹{m['deposit_total']:>8,.2f}  "
      f"BOOK=₹{m['capital_after_deposit']:>10,.2f}",
      flush=True,
    )
  print("\n===== YEAR END (through Aug) =====", flush=True)
  print(f"Final book:        ₹{final:,.2f}", flush=True)
  print(f"External cash in:  ₹{external_cash:,.2f} (start 10k + 8×10k top-ups)", flush=True)
  print(f"Sum trading PnL:   ₹{trading_pnl_sum:+,.2f}", flush=True)
  print(f"vs external:       ₹{final - external_cash:+,.2f}", flush=True)
  print("Wrote", path, flush=True)


if __name__ == "__main__":
  main()
