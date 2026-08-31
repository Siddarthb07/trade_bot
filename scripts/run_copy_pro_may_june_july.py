"""Run copy_bulk_pro ablation-winner config for May / June / July separately."""
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
from processor.smart_money_gate import (
  bulk_data_coverage,
  cooldown_excludes,
  empty_copy_pro_cooldown,
  register_copy_pro_outcomes,
)

CAPITAL = 10_000.0

MONTHS = [
  ("may", "2026-05-01", "2026-05-31"),
  ("june", "2026-06-01", "2026-06-30"),
  ("july", "2026-07-01", "2026-07-31"),
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


def run_month(name: str, start: str, end: str, kw: dict, sl: int, ent: int) -> dict:
  days = sessions(start, end)
  cap = CAPITAL
  cd = empty_copy_pro_cooldown()
  trades_out: list[dict] = []
  daily: list[dict] = []
  peak = cap
  max_dd = 0.0
  no_trade = 0

  print(f"\n===== {name.upper()} {start}..{end} ({len(days)} sessions) =====", flush=True)
  for asof in days:
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
      **kw,
    )
    end_cap = float(res.get("capital_end") or cap)
    pnl = round(end_cap - cap, 2)
    day_trades = res.get("trades") or []
    if not day_trades:
      no_trade += 1
      print(f"  {asof} flat", flush=True)
    for t in day_trades:
      row = {
        "asof": asof,
        "ticker": t.get("ticker"),
        "pnl": t.get("pnl"),
        "pnl_pct": t.get("pnl_pct"),
        "exit": t.get("exit_reason"),
        "lev": t.get("leverage"),
        "margin_inr": t.get("slot_capital"),
        "invested_notional_inr": t.get("entry_notional") or t.get("money_put"),
        "returned_notional_inr": t.get("exit_notional") or t.get("money_returned"),
        "fees": t.get("fees"),
        "entity": t.get("bulk_entity"),
        "book_before": round(cap, 2),
      }
      trades_out.append(row)
      print(
        f"  {asof} {row['ticker']} margin=₹{float(row['margin_inr'] or 0):.0f} "
        f"inv=₹{float(row['invested_notional_inr'] or 0):.0f} "
        f"pnl={float(row['pnl'] or 0):+.1f} {row['exit']}",
        flush=True,
      )
    cd = register_copy_pro_outcomes(
      cd,
      list(day_trades),
      ticker_cooldown_days=sl,
      entity_cooldown_days=ent,
      sitout_after_sl_days=0,
    )
    peak = max(peak, end_cap)
    max_dd = max(max_dd, 100.0 * (peak - end_cap) / peak if peak else 0.0)
    daily.append({"asof": asof, "pnl": pnl, "end": round(end_cap, 2), "n": len(day_trades)})
    cap = end_cap

  notionals = [float(t["invested_notional_inr"] or 0) for t in trades_out]
  margins = [float(t["margin_inr"] or 0) for t in trades_out]
  wins = [t for t in trades_out if float(t.get("pnl") or 0) > 0]
  losses = [t for t in trades_out if float(t.get("pnl") or 0) <= 0]
  return {
    "month": name,
    "window": {"start": start, "end": end, "n_sessions": len(days)},
    "capital_start": CAPITAL,
    "capital_end": round(cap, 2),
    "pnl_inr": round(cap - CAPITAL, 2),
    "compound_pct": round(100.0 * (cap - CAPITAL) / CAPITAL, 3),
    "max_dd_pct": round(max_dd, 2),
    "n_trades": len(trades_out),
    "n_flat_days": no_trade,
    "wins": len(wins),
    "losses": len(losses),
    "avg_margin_inr": round(sum(margins) / len(margins), 2) if margins else 0,
    "avg_invested_notional_inr": round(sum(notionals) / len(notionals), 2) if notionals else 0,
    "total_invested_notional_inr": round(sum(notionals), 2),
    "total_fees_inr": round(sum(float(t.get("fees") or 0) for t in trades_out), 2),
    "sum_win_pnl": round(sum(float(t["pnl"]) for t in wins), 2),
    "sum_loss_pnl": round(sum(float(t["pnl"]) for t in losses), 2),
    "trades": trades_out,
    "daily": daily,
  }


def main() -> None:
  cov = bulk_data_coverage(since="2026-05-01")
  print("bulk_coverage", cov, flush=True)

  kw = sim_kwargs_for_strategy("copy_bulk_pro", "product")
  kw.pop("bar_interval", None)
  sl = int(kw.pop("sl_cooldown_days", 1) or 1)
  ent = int(kw.pop("entity_cooldown_days", 1) or 1)
  kw.pop("sitout_after_sl_days", None)
  print("params", {**kw, "sl_cooldown_days": sl, "entity_cooldown_days": ent}, flush=True)

  months = []
  for name, start, end in MONTHS:
    m = run_month(name, start, end, kw, sl, ent)
    months.append(m)
    print(
      f">>> {name.upper()} {m['capital_start']:.0f}→{m['capital_end']:.2f} "
      f"compound={m['compound_pct']:+.2f}% trades={m['n_trades']} "
      f"avg_inv=₹{m['avg_invested_notional_inr']:.0f} dd={m['max_dd_pct']:.1f}%",
      flush=True,
    )

  out = {
    "generated_at": date.today().isoformat(),
    "bulk_coverage": cov,
    "params": {**kw, "sl_cooldown_days": sl, "entity_cooldown_days": ent},
    "months": months,
    "summary": [
      {
        "month": m["month"],
        "compound_pct": m["compound_pct"],
        "pnl_inr": m["pnl_inr"],
        "n_trades": m["n_trades"],
        "wins": m["wins"],
        "losses": m["losses"],
        "avg_margin_inr": m["avg_margin_inr"],
        "avg_invested_notional_inr": m["avg_invested_notional_inr"],
        "max_dd_pct": m["max_dd_pct"],
        "n_flat_days": m["n_flat_days"],
      }
      for m in months
    ],
  }
  path = ROOT / "models" / "copy_pro_may_june_july.json"
  path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
  print("\n===== SUMMARY =====", flush=True)
  for s in out["summary"]:
    print(
      f"{s['month']:5} {s['compound_pct']:+7.2f}% pnl={s['pnl_inr']:+8.0f} "
      f"trades={s['n_trades']:3} W/L={s['wins']}/{s['losses']} "
      f"avg_inv=₹{s['avg_invested_notional_inr']:.0f} dd={s['max_dd_pct']:.1f}%",
      flush=True,
    )
  print("Wrote", path, flush=True)


if __name__ == "__main__":
  main()
