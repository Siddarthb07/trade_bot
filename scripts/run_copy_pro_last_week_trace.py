"""Last-week copy_bulk_pro use60 — day-by-day + loss root-cause trace."""
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
from processor.smart_money_gate import rank_pro_buys

CAPITAL = 10_000.0


def week_sessions(today: date | None = None) -> list[str]:
  """Mon–Fri of the calendar week containing the last NSE session before today."""
  d = today or date.today()
  while d.weekday() >= 5:
    d -= timedelta(days=1)
  # Monday of that week
  mon = d - timedelta(days=d.weekday())
  out: list[str] = []
  for i in range(5):
    day = mon + timedelta(days=i)
    if day <= d:
      out.append(day.isoformat())
  return out


def cause_for_trade(t: dict, pick_meta: dict | None) -> dict:
  entry = float(t.get("entry_price") or 0)
  exit_px = float(t.get("exit_price") or 0)
  fees = float(t.get("fees") or 0)
  entry_n = float(t.get("entry_notional") or 0)
  exit_n = float(t.get("exit_notional") or 0)
  pnl = float(t.get("pnl") or 0)
  raw_move = (exit_n - entry_n) if entry_n else 0.0
  move_pct = 100.0 * (exit_px / entry - 1.0) if entry else 0.0
  fee_drag_pct = 100.0 * fees / entry_n if entry_n else 0.0
  exit_reason = str(t.get("exit_reason") or t.get("exit") or "")
  sl_pct = float(t.get("sl_pct") or 0)

  buckets: list[str] = []
  if exit_reason == "stop_loss":
    buckets.append("stop_loss_hit")
    buckets.append(f"sl_band_~{sl_pct:.2f}%_of_price→amplified_by_{t.get('leverage')}x_lev")
  elif exit_reason in ("session_close", "session_horizon"):
    if move_pct < 0:
      buckets.append("held_to_close_red")
    else:
      buckets.append("held_to_close_green_but_fees_or_slip")
  if fees > abs(raw_move) and pnl < 0 and raw_move > 0:
    buckets.append("fee_turned_green_red")
  elif fee_drag_pct > 0.25 and pnl < 0:
    buckets.append(f"fee_drag_{fee_drag_pct:.2f}pct_of_notional")
  if pick_meta:
    buckets.append(
      f"bulk_pick_wr={pick_meta.get('win_rate')} n={pick_meta.get('n_trades')} "
      f"deal₹={pick_meta.get('value')} entity={pick_meta.get('entity_normalized')}"
    )

  # Primary one-liner
  if exit_reason == "stop_loss":
    primary = (
      f"Price hit stop (~{sl_pct:.2f}% adverse). Lev {t.get('leverage')}x turned "
      f"{move_pct:.2f}% price move into {t.get('pnl_pct')}% on notional / ₹{pnl}."
    )
  elif move_pct < 0:
    primary = (
      f"Held to close: underlying {move_pct:.2f}%. Fees ₹{fees:.0f} "
      f"({fee_drag_pct:.2f}% notional). No SL — slow bleed / wrong-direction day."
    )
  else:
    primary = (
      f"Underlying +{move_pct:.2f}% but net ₹{pnl} after fees ₹{fees:.0f} "
      f"— fee/rounding drag."
    )

  return {
    "primary": primary,
    "buckets": buckets,
    "underlying_move_pct": round(move_pct, 3),
    "gross_pnl_before_fees": round(raw_move, 2),
    "fees": round(fees, 2),
    "fee_drag_pct_notional": round(fee_drag_pct, 3),
    "exit_reason": exit_reason,
    "sl_pct": sl_pct,
    "leverage": t.get("leverage") or t.get("lev"),
  }


def main() -> None:
  days = week_sessions()
  kw = sim_kwargs_for_strategy("copy_bulk_pro", "product")
  kw.pop("bar_interval", None)
  kw.pop("sl_cooldown_days", None)
  kw.pop("entity_cooldown_days", None)
  kw.pop("sitout_after_sl_days", None)
  print("week_sessions", days, flush=True)
  print("params", kw, flush=True)

  cap = CAPITAL
  daily = []
  for asof in days:
    print(f"\n=== {asof} capital={cap:,.0f} ===", flush=True)
    ranked = rank_pro_buys(
      asof,
      lookback_sessions=int(kw["bulk_lookback_sessions"]),
      min_win_rate=float(kw["bulk_min_win_rate"]),
      min_n_trades=int(kw["bulk_min_n_trades"]),
      min_deal_value=float(kw["bulk_min_deal_value"]),
      limit=8,
    )
    picks = ranked.get("picks") or []
    pick_by_tk = {p["ticker"]: p for p in picks}

    res = simulate_day(
      asof=asof,
      capital=cap,
      currency="INR",
      market="IN",
      path_mode="session",
      allow_demo_fallback=False,
      **kw,
    )
    end = float(res.get("capital_end") or cap)
    pnl = round(end - cap, 2)
    trades = res.get("trades") or []
    trade_traces = []
    for t in trades:
      # normalize field names
      t_norm = {
        **t,
        "entry_price": t.get("entry_price") or t.get("entry_px"),
        "exit_price": t.get("exit_price") or t.get("exit_px"),
        "exit_reason": t.get("exit_reason") or t.get("exit"),
        "leverage": t.get("leverage") or t.get("lev"),
      }
      meta = pick_by_tk.get(str(t.get("ticker") or ""))
      cause = cause_for_trade(t_norm, meta)
      trade_traces.append(
        {
          "ticker": t.get("ticker"),
          "pnl": t.get("pnl"),
          "pnl_pct": t.get("pnl_pct"),
          "entry_price": t_norm["entry_price"],
          "exit_price": t_norm["exit_price"],
          "entry_notional": t.get("entry_notional"),
          "slot_capital": t.get("slot_capital"),
          "leverage": t_norm["leverage"],
          "fees": t.get("fees"),
          "exit_reason": t_norm["exit_reason"],
          "sl_pct": t.get("sl_pct"),
          "tp_pct": t.get("tp_pct"),
          "signal_reason": t.get("signal_reason"),
          "bulk_meta": meta,
          "cause": cause,
        }
      )
      print(
        f"  {t.get('ticker')} pnl={t.get('pnl'):+.1f} exit={t_norm['exit_reason']} "
        f"move={cause['underlying_move_pct']:+.2f}% lev={t_norm['leverage']}",
        flush=True,
      )
      print(f"    CAUSE: {cause['primary']}", flush=True)

    if not trades:
      print("  NO TRADE", ranked.get("data_gap"), (picks[:3] if picks else None), flush=True)

    row = {
      "asof": asof,
      "capital_start": round(cap, 2),
      "capital_end": round(end, 2),
      "pnl_inr": pnl,
      "return_pct": round(100.0 * pnl / cap, 3) if cap else 0,
      "n_trades": len(trades),
      "top_bulk_picks": picks[:5],
      "n_raw_deals": ranked.get("n_raw_deals"),
      "data_gap": ranked.get("data_gap"),
      "trades": trade_traces,
      "skipped_sample": (res.get("skipped") or [])[:5],
    }
    daily.append(row)
    cap = end

  losses = [d for d in daily if d["pnl_inr"] < 0]
  wins = [d for d in daily if d["pnl_inr"] > 0]
  exit_counts: dict[str, int] = {}
  loss_buckets: dict[str, int] = {}
  for d in daily:
    for t in d["trades"]:
      er = t.get("exit_reason") or "?"
      exit_counts[er] = exit_counts.get(er, 0) + 1
      if float(t.get("pnl") or 0) < 0:
        for b in t["cause"]["buckets"]:
          key = b.split("=")[0].split("~")[0]
          if key.startswith("bulk_pick"):
            key = "bulk_pick_attached"
          loss_buckets[key] = loss_buckets.get(key, 0) + 1

  # Root-cause synthesis
  sl_losses = sum(
    1
    for d in daily
    for t in d["trades"]
    if float(t.get("pnl") or 0) < 0 and t.get("exit_reason") == "stop_loss"
  )
  close_losses = sum(
    1
    for d in daily
    for t in d["trades"]
    if float(t.get("pnl") or 0) < 0 and t.get("exit_reason") in ("session_close", "session_horizon")
  )
  total_fees = sum(float(t.get("fees") or 0) for d in daily for t in d["trades"])
  total_pnl = round(cap - CAPITAL, 2)

  synthesis = {
    "week_compound_pct": round(100.0 * (cap - CAPITAL) / CAPITAL, 3),
    "pnl_inr": total_pnl,
    "capital_end": round(cap, 2),
    "n_sessions": len(daily),
    "win_days": len(wins),
    "loss_days": len(losses),
    "exit_counts": exit_counts,
    "loss_exit_split": {"stop_loss": sl_losses, "session_close": close_losses},
    "total_fees_inr": round(total_fees, 2),
    "loss_bucket_hits": loss_buckets,
    "break_points": [
      {
        "asof": d["asof"],
        "pnl_inr": d["pnl_inr"],
        "ticker": d["trades"][0]["ticker"] if d["trades"] else None,
        "primary": d["trades"][0]["cause"]["primary"] if d["trades"] else "no trade",
      }
      for d in losses
    ],
    "verdict": None,
  }

  if sl_losses >= close_losses and sl_losses > 0:
    synthesis["verdict"] = (
      "Primary break: stop-outs. Bulk pick direction wrong early; risk band + leverage "
      "locks ~1–2.5% notional hits before any recovery. Not fee-driven."
    )
  elif close_losses > sl_losses:
    synthesis["verdict"] = (
      "Primary break: held-to-close red days. Signal was wrong-direction for the full "
      "session (or weak drift); fees add ~0.3% drag but are secondary."
    )
  else:
    synthesis["verdict"] = "Mixed / sparse week — inspect break_points."

  out = {
    "generated_for_calendar": date.today().isoformat(),
    "sessions": days,
    "params": kw,
    "capital_start": CAPITAL,
    "synthesis": synthesis,
    "daily": daily,
  }
  path = ROOT / "models" / "copy_pro_last_week_trace.json"
  path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
  print("\n===== WEEK SYNTHESIS =====", flush=True)
  print(json.dumps(synthesis, indent=2), flush=True)
  print("Wrote", path, flush=True)


if __name__ == "__main__":
  main()
