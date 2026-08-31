"""Full August copy_bulk_pro use60 with current product defaults + rules ledger."""
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
from processor.hybrid.rules_ledger import (
  RULES_PATH,
  learn_from_session,
  merge_excludes,
  read_daily_briefing,
  seed_standing_policies,
)

CAPITAL = 10_000.0
START = date(2026, 8, 1)
END = date(2026, 8, 29)


def sessions(a: date, b: date) -> list[str]:
  out: list[str] = []
  d = a
  while d <= b:
    if d.weekday() < 5:
      out.append(d.isoformat())
    d += timedelta(days=1)
  return out


def main() -> None:
  # Fresh rules ledger for clean August learn loop
  if RULES_PATH.exists():
    RULES_PATH.unlink()
  seed_standing_policies()

  kw = sim_kwargs_for_strategy("copy_bulk_pro", "product")
  kw.pop("bar_interval", None)
  sl_cd = int(kw.pop("sl_cooldown_days", 1) or 1)
  ent_cd = int(kw.pop("entity_cooldown_days", 1) or 1)
  kw.pop("sitout_after_sl_days", None)

  days = sessions(START, END)
  # Only through last closed session (Fri 28 if today Sat 29)
  today = date.today()
  days = [d for d in days if date.fromisoformat(d) <= today and date.fromisoformat(d).weekday() < 5]
  # If weekend, last Fri already included via weekday filter

  cap = CAPITAL
  start = cap
  peak = cap
  max_dd = 0.0
  daily = []
  all_trades = []
  sitouts = 0

  print("params", {**kw, "sl_cooldown_days": sl_cd, "entity_cooldown_days": ent_cd}, flush=True)
  print(f"sessions {days[0]}..{days[-1]} n={len(days)}", flush=True)

  for asof in days:
    briefing = read_daily_briefing(asof, mark_read=True)
    ex_t, ex_e, sitout = merge_excludes(briefing)
    if sitout:
      sitouts += 1
      print(f"{asof} SITOUT rules | {briefing['summary']}", flush=True)
      daily.append(
        {
          "asof": asof,
          "pnl_inr": 0.0,
          "return_pct": 0.0,
          "capital_start": round(cap, 2),
          "capital_end": round(cap, 2),
          "n_trades": 0,
          "sitout": True,
          "rules_summary": briefing["summary"],
        }
      )
      learn_from_session(
        asof=asof,
        trades=[],
        session_return_pct=0.0,
        strategy_id="copy_bulk_pro",
        ticker_cooldown_sessions=sl_cd,
        entity_cooldown_sessions=ent_cd,
      )
      continue

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
    ret = round(100.0 * pnl / cap, 3) if cap else 0.0
    trades = res.get("trades") or []
    for t in trades:
      row = {
        "asof": asof,
        "ticker": t.get("ticker"),
        "pnl": t.get("pnl"),
        "pnl_pct": t.get("pnl_pct"),
        "exit": t.get("exit_reason") or t.get("exit"),
        "lev": t.get("leverage") or t.get("lev"),
        "margin_slot_inr": t.get("slot_capital"),
        "notional_invested_inr": t.get("entry_notional") or t.get("money_put"),
        "notional_returned_inr": t.get("exit_notional") or t.get("money_returned"),
        "entry_px": t.get("entry_price") or t.get("entry_px"),
        "exit_px": t.get("exit_price") or t.get("exit_px"),
        "qty": t.get("qty"),
        "fees": t.get("fees"),
        "entity": t.get("bulk_entity"),
        "capital_at_entry": round(cap, 2),
        "cash_idle_inr": round(cap * (1.0 - float(kw.get("capital_use_frac") or 0.6)), 2),
      }
      all_trades.append(row)
      print(
        f"{asof} {row['ticker']} margin={row['margin_slot_inr']:.0f} "
        f"notional={row['notional_invested_inr']:.0f} lev={row['lev']} "
        f"pnl={row['pnl']:+.1f} exit={row['exit']}",
        flush=True,
      )
    if not trades:
      print(f"{asof} NO TRADE excludes_tk={ex_t[:3]} ent={len(ex_e)}", flush=True)

    learn_from_session(
      asof=asof,
      trades=list(trades),
      session_return_pct=ret,
      strategy_id="copy_bulk_pro",
      ticker_cooldown_sessions=max(1, sl_cd),
      entity_cooldown_sessions=max(0, ent_cd),
    )

    peak = max(peak, end)
    dd = 100.0 * (peak - end) / peak if peak else 0.0
    max_dd = max(max_dd, dd)
    daily.append(
      {
        "asof": asof,
        "pnl_inr": pnl,
        "return_pct": ret,
        "capital_start": round(cap, 2),
        "capital_end": round(end, 2),
        "n_trades": len(trades),
        "sitout": False,
        "exclude_tickers": ex_t,
        "exclude_entities": ex_e,
        "rules_summary": briefing["summary"],
      }
    )
    cap = end

  compound = round(100.0 * (cap - start) / start, 3)
  wins = [t for t in all_trades if float(t.get("pnl") or 0) > 0]
  losses = [t for t in all_trades if float(t.get("pnl") or 0) <= 0]
  margins = [float(t["margin_slot_inr"] or 0) for t in all_trades]
  notionals = [float(t["notional_invested_inr"] or 0) for t in all_trades]

  out = {
    "window": {"start": days[0], "end": days[-1], "n_sessions": len(days)},
    "params": {**kw, "sl_cooldown_days": sl_cd, "entity_cooldown_days": ent_cd},
    "capital_start": start,
    "capital_end": round(cap, 2),
    "pnl_inr": round(cap - start, 2),
    "compound_pct": compound,
    "max_dd_pct": round(max_dd, 3),
    "n_trades": len(all_trades),
    "n_sitouts": sitouts,
    "win_trades": len(wins),
    "loss_trades": len(losses),
    "avg_margin_inr": round(sum(margins) / len(margins), 2) if margins else 0,
    "avg_notional_inr": round(sum(notionals) / len(notionals), 2) if notionals else 0,
    "total_notional_deployed_inr": round(sum(notionals), 2),
    "total_fees_inr": round(sum(float(t.get("fees") or 0) for t in all_trades), 2),
    "sum_win_pnl": round(sum(float(t["pnl"]) for t in wins), 2),
    "sum_loss_pnl": round(sum(float(t["pnl"]) for t in losses), 2),
    "trades": all_trades,
    "daily": daily,
  }
  path = ROOT / "models" / "copy_pro_august_full.json"
  path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
  print("\n===== AUGUST FULL =====", flush=True)
  print(
    f"{start:.0f} → {cap:.2f}  compound={compound:+.2f}%  pnl={cap-start:+.2f}  "
    f"trades={len(all_trades)} sitouts={sitouts} dd={max_dd:.1f}%",
    flush=True,
  )
  print(
    f"avg margin ₹{out['avg_margin_inr']:.0f}  avg notional ₹{out['avg_notional_inr']:.0f}  "
    f"total notional-days ₹{out['total_notional_deployed_inr']:.0f}",
    flush=True,
  )
  print("Wrote", path, flush=True)


if __name__ == "__main__":
  main()
