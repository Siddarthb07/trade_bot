"""Verify copy-pro failure fixes on last week (24–28 Aug)."""
from __future__ import annotations

import json
import os
import sys
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
  copy_pro_should_sitout,
  cooldown_excludes,
  empty_copy_pro_cooldown,
  rank_pro_buys,
  register_copy_pro_outcomes,
)

DAYS = ["2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28"]
CAPITAL = 10_000.0
BASELINE_COMPOUND = -8.293


def main() -> None:
  kw = sim_kwargs_for_strategy("copy_bulk_pro", "product")
  kw.pop("bar_interval", None)
  sl_cd = int(kw.pop("sl_cooldown_days", 1) or 1)
  ent_cd = int(kw.pop("entity_cooldown_days", 1) or 1)
  sit_cd = int(kw.pop("sitout_after_sl_days", 1) or 1)

  cap = CAPITAL
  cd = empty_copy_pro_cooldown()
  daily = []
  for asof in DAYS:
    ex_t, ex_e = cooldown_excludes(cd)
    if copy_pro_should_sitout(cd):
      print(f"\n=== {asof} SITOUT after SL ===", flush=True)
      daily.append(
        {
          "asof": asof,
          "pnl_inr": 0.0,
          "return_pct": 0.0,
          "capital_end": round(cap, 2),
          "n_trades": 0,
          "sitout_after_sl": True,
          "trades": [],
        }
      )
      cd = register_copy_pro_outcomes(
        cd, [], ticker_cooldown_days=sl_cd, entity_cooldown_days=ent_cd, sitout_after_sl_days=sit_cd
      )
      continue
    ranked = rank_pro_buys(
      asof,
      lookback_sessions=int(kw["bulk_lookback_sessions"]),
      min_win_rate=float(kw["bulk_min_win_rate"]),
      min_n_trades=int(kw["bulk_min_n_trades"]),
      min_deal_value=float(kw["bulk_min_deal_value"]),
      exclude_tickers=ex_t or None,
      exclude_entities=ex_e or None,
      wr_prior=float(kw.get("bulk_wr_prior", 0.55)),
      wr_pseudo_n=float(kw.get("bulk_wr_pseudo_n", 5.0)),
      limit=5,
    )
    print(f"\n=== {asof} exclude_tk={ex_t} exclude_ent={ex_e[:1] if ex_e else []} ===", flush=True)
    print(
      " top:",
      [(p["ticker"], p.get("win_rate_eff"), p.get("entity_normalized"), p.get("disclosed_at")) for p in (ranked.get("picks") or [])[:3]],
      flush=True,
    )
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
    trades = res.get("trades") or []
    for t in trades:
      print(
        f"  {t.get('ticker')} pnl={t.get('pnl'):+.1f} exit={t.get('exit_reason')} "
        f"entity={t.get('bulk_entity')} sl={t.get('sl_pct')}",
        flush=True,
      )
    if not trades:
      print("  NO TRADE", flush=True)
    daily.append(
      {
        "asof": asof,
        "pnl_inr": pnl,
        "return_pct": round(100.0 * pnl / cap, 3) if cap else 0,
        "capital_end": round(end, 2),
        "n_trades": len(trades),
        "exclude_tickers": ex_t,
        "exclude_entities": ex_e,
        "top_picks": (ranked.get("picks") or [])[:3],
        "trades": [
          {
            "ticker": t.get("ticker"),
            "pnl": t.get("pnl"),
            "exit": t.get("exit_reason"),
            "entity": t.get("bulk_entity"),
            "sl_pct": t.get("sl_pct"),
          }
          for t in trades
        ],
      }
    )
    cd = register_copy_pro_outcomes(
      cd,
      list(trades),
      ticker_cooldown_days=sl_cd,
      entity_cooldown_days=ent_cd,
      sitout_after_sl_days=sit_cd,
    )
    cap = end

  compound = round(100.0 * (cap - CAPITAL) / CAPITAL, 3)
  out = {
    "baseline_compound_pct": BASELINE_COMPOUND,
    "fixed_compound_pct": compound,
    "delta_pp": round(compound - BASELINE_COMPOUND, 3),
    "capital_end": round(cap, 2),
    "pnl_inr": round(cap - CAPITAL, 2),
    "daily": daily,
    "params": {
      **kw,
      "sl_cooldown_days": sl_cd,
      "entity_cooldown_days": ent_cd,
      "sitout_after_sl_days": sit_cd,
    },
  }
  path = ROOT / "models" / "copy_pro_last_week_fixed.json"
  path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
  print("\n===== FIXED WEEK =====", flush=True)
  print(
    f"baseline {BASELINE_COMPOUND:+.3f}% → fixed {compound:+.3f}% (Δ {out['delta_pp']:+.3f}pp) end={cap:,.0f}",
    flush=True,
  )
  print("Wrote", path, flush=True)


if __name__ == "__main__":
  main()
