"""August copy-pro — ablation winner config (no sitout streak): lookback+tk+entity, wr0."""
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
  cooldown_excludes,
  empty_copy_pro_cooldown,
  register_copy_pro_outcomes,
)

CAPITAL = 10_000.0


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
  kw = sim_kwargs_for_strategy("copy_bulk_pro", "product")
  kw.pop("bar_interval", None)
  sl = int(kw.pop("sl_cooldown_days", 1) or 1)
  ent = int(kw.pop("entity_cooldown_days", 1) or 1)
  kw.pop("sitout_after_sl_days", None)

  days = sessions("2026-08-03", "2026-08-28")
  cap = CAPITAL
  cd = empty_copy_pro_cooldown()
  trades_out = []
  daily = []
  peak = cap
  max_dd = 0.0

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
    end = float(res.get("capital_end") or cap)
    pnl = round(end - cap, 2)
    for t in res.get("trades") or []:
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
        "entry_px": t.get("entry_price"),
        "exit_px": t.get("exit_price"),
        "qty": t.get("qty"),
        "fees": t.get("fees"),
        "entity": t.get("bulk_entity"),
        "book_before": round(cap, 2),
        "cash_idle_inr": round(cap * 0.4, 2),
      }
      trades_out.append(row)
      print(
        f"{asof} {row['ticker']} margin=₹{row['margin_inr']:.0f} "
        f"invested=₹{row['invested_notional_inr']:.0f} lev={row['lev']} "
        f"pnl={row['pnl']:+.1f} {row['exit']}",
        flush=True,
      )
    if not (res.get("trades") or []):
      print(f"{asof} flat excludes={ex_t[:2]}", flush=True)
    cd = register_copy_pro_outcomes(
      cd,
      list(res.get("trades") or []),
      ticker_cooldown_days=sl,
      entity_cooldown_days=ent,
      sitout_after_sl_days=0,
    )
    peak = max(peak, end)
    max_dd = max(max_dd, 100 * (peak - end) / peak if peak else 0)
    daily.append(
      {
        "asof": asof,
        "pnl": pnl,
        "end": round(end, 2),
        "n": len(res.get("trades") or []),
      }
    )
    cap = end

  notionals = [float(t["invested_notional_inr"] or 0) for t in trades_out]
  margins = [float(t["margin_inr"] or 0) for t in trades_out]
  wins = [t for t in trades_out if float(t["pnl"] or 0) > 0]
  losses = [t for t in trades_out if float(t["pnl"] or 0) <= 0]
  out = {
    "label": "august_ablation_winner",
    "compound_pct": round(100 * (cap - CAPITAL) / CAPITAL, 3),
    "pnl_inr": round(cap - CAPITAL, 2),
    "capital_end": round(cap, 2),
    "max_dd_pct": round(max_dd, 2),
    "n_trades": len(trades_out),
    "wins": len(wins),
    "losses": len(losses),
    "avg_margin_inr": round(sum(margins) / len(margins), 2) if margins else 0,
    "avg_invested_notional_inr": round(sum(notionals) / len(notionals), 2) if notionals else 0,
    "total_invested_notional_inr": round(sum(notionals), 2),
    "total_fees_inr": round(sum(float(t.get("fees") or 0) for t in trades_out), 2),
    "trades": trades_out,
    "daily": daily,
    "params": {**kw, "sl_cooldown_days": sl, "entity_cooldown_days": ent},
  }
  path = ROOT / "models" / "copy_pro_august_ablation.json"
  path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
  print(
    f"\nAUGUST {CAPITAL:.0f}→{cap:.2f} compound={out['compound_pct']:+.2f}% "
    f"trades={out['n_trades']} avg_margin=₹{out['avg_margin_inr']:.0f} "
    f"avg_invested=₹{out['avg_invested_notional_inr']:.0f}",
    flush=True,
  )
  print("Wrote", path, flush=True)


if __name__ == "__main__":
  main()
