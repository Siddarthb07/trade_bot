"""Export full Jan–Aug 2026 copy-pro book trades for GodFather desk tape.

Writes:
  models/copy_pro_jan_aug_oneshot_10k.json  (with per-month trades)
  models/godfather_desk_tape.json
  GodFather-core/apps/dashboard/public/{tape.json,oneshot_2026.json}
"""
from __future__ import annotations

import json
import os
import shutil
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
  rank_pro_buys,
  register_copy_pro_outcomes,
)

START = 10_000.0
PAD = 4
CACHE = ROOT / "models" / "intraday_cache"
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
DASH = Path(r"C:\Users\siddu\Projects\GodFather-core\apps\dashboard\public")


def sessions(a: str, b: str) -> list[str]:
  sd, ed = date.fromisoformat(a), date.fromisoformat(b)
  out = []
  d = sd
  while d <= ed:
    if d.weekday() < 5:
      out.append(d.isoformat())
    d += timedelta(days=1)
  return out


def load_bars(ticker: str, asof: str) -> list[dict]:
  keys = [
    ticker,
    ticker if str(ticker).endswith(".NS") else f"{ticker}.NS",
    str(ticker).replace(".NS", "") + ".NS",
  ]
  for key in keys:
    for interval in ("5m", "15m", "1h", "1m"):
      path = CACHE / key / f"{asof}_{interval}.json"
      if not path.exists():
        continue
      try:
        raw = json.loads(path.read_text(encoding="utf-8"))
      except Exception:
        continue
      return [
        {
          "ts": b.get("ts") or b.get("date"),
          "open": float(b.get("open") or b.get("close") or 0),
          "high": float(b.get("high") or b.get("close") or 0),
          "low": float(b.get("low") or b.get("close") or 0),
          "close": float(b.get("close") or 0),
          "volume": float(b.get("volume") or 0),
        }
        for b in raw
      ]
  return []


def slice_bars(bars: list[dict], entry_i: int | None, exit_i: int | None) -> tuple[list[dict], int, int]:
  if not bars:
    return [], 0, 0
  ei = int(entry_i) if entry_i is not None else 0
  xi = int(exit_i) if exit_i is not None else len(bars) - 1
  ei = max(0, min(ei, len(bars) - 1))
  xi = max(ei, min(xi, len(bars) - 1))
  lo = max(0, ei - PAD)
  hi = min(len(bars), xi + PAD + 1)
  window = bars[lo:hi]
  return window, ei - lo, xi - lo


def loss_analysis(t: dict) -> str:
  pnl = float(t.get("pnl") or 0)
  reason = str(t.get("exit_reason") or "")
  pnl_pct = float(t.get("pnl_pct") or 0)
  lev = float(t.get("leverage") or 0)
  fees = float(t.get("fees") or 0)
  if pnl >= 0:
    return f"Closed green via {reason or 'exit'} ({pnl_pct:+.2f}% on notional, lev {lev:.1f}x, fees ₹{fees:.2f})."
  if "stop" in reason:
    return (
      f"Stop hit ({reason}). Leverage {lev:.1f}x amplified adverse move to "
      f"{pnl_pct:+.2f}% / ₹{pnl:,.2f} (fees ₹{fees:.2f})."
    )
  if "trail" in reason:
    return f"Trail exit after giveback ({reason}). Final {pnl_pct:+.2f}% / ₹{pnl:,.2f}."
  if "session" in reason or "close" in reason:
    return f"Held to session end red; fees ₹{fees:.2f}. Final {pnl_pct:+.2f}% / ₹{pnl:,.2f}."
  return f"Loss via {reason or 'unknown'}: {pnl_pct:+.2f}% / ₹{pnl:,.2f}."


def normalize_trade(t: dict, asof: str, month: str, picks: list[dict]) -> dict:
  invested = float(t.get("money_put") or t.get("entry_notional") or 0)
  returned = float(t.get("money_returned") or t.get("exit_notional") or 0)
  fees = float(t.get("fees") or 0)
  pnl = float(t.get("pnl") or 0)
  if returned <= 0 and invested > 0:
    returned = round(invested + pnl + fees, 2)
  ticker = str(t.get("ticker") or "")
  pick = next((p for p in picks if str(p.get("ticker")) == ticker), None)
  alts = [p for p in picks if str(p.get("ticker")) != ticker]
  if pick:
    choice = (
      f"Prior-session bulk BUY ranked score={pick.get('score')} "
      f"WR={pick.get('win_rate_eff') or pick.get('win_rate')} "
      f"deal=₹{float(pick.get('value') or 0):,.0f} entity={pick.get('entity_normalized')}."
    )
  else:
    choice = t.get("why_selected") or t.get("signal_reason") or "copy_bulk_pro fill"
  if alts:
    choice += " Next ranks: " + ", ".join(f"{a.get('ticker')}({a.get('score')})" for a in alts[:3]) + "."

  bars_full = load_bars(ticker, asof)
  window, ei, xi = slice_bars(bars_full, t.get("entry_bar_i"), t.get("exit_bar_i"))
  if not window and bars_full:
    window = bars_full
    entry_px = float(t.get("entry_price") or t.get("entry_px") or 0)
    exit_px = float(t.get("exit_price") or t.get("exit_px") or 0)
    if entry_px:
      ei = min(range(len(window)), key=lambda i: abs(float(window[i]["close"]) - entry_px))
    if exit_px:
      xi = min(range(len(window)), key=lambda i: abs(float(window[i]["close"]) - exit_px))
      xi = max(ei, xi)

  row = {
    "asof": asof,
    "month": month,
    "year": 2026,
    "ticker": ticker,
    "side": t.get("side") or "long",
    "entry_price": t.get("entry_price") or t.get("entry_px"),
    "exit_price": t.get("exit_price") or t.get("exit_px"),
    "entry_notional": round(invested, 2),
    "exit_notional": round(returned, 2),
    "money_put": round(invested, 2),
    "money_returned": round(returned, 2),
    "fees": round(fees, 4),
    "qty": t.get("qty"),
    "leverage": t.get("leverage") or t.get("lev"),
    "pnl": round(pnl, 2),
    "pnl_pct": t.get("pnl_pct"),
    "exit_reason": t.get("exit_reason") or t.get("exit"),
    "signal_reason": t.get("signal_reason") or t.get("reason"),
    "bulk_entity": t.get("bulk_entity") or (pick or {}).get("entity_normalized"),
    "bulk_score": t.get("bulk_score") if t.get("bulk_score") is not None else (pick or {}).get("score"),
    "bulk_wr": t.get("bulk_wr")
    if t.get("bulk_wr") is not None
    else (pick or {}).get("win_rate_eff") or (pick or {}).get("win_rate"),
    "rank": next((i + 1 for i, p in enumerate(picks) if str(p.get("ticker")) == ticker), None),
    "slot_capital": t.get("slot_capital"),
    "choice_notes": choice,
    "loss_analysis": loss_analysis(
      {
        "pnl": pnl,
        "pnl_pct": t.get("pnl_pct"),
        "exit_reason": t.get("exit_reason") or t.get("exit"),
        "leverage": t.get("leverage") or t.get("lev"),
        "fees": fees,
      }
    ),
    "alternates": [
      {
        "ticker": a.get("ticker"),
        "score": a.get("score"),
        "win_rate": a.get("win_rate_eff") or a.get("win_rate"),
        "entity": a.get("entity_normalized"),
        "value": a.get("value"),
      }
      for a in alts[:5]
    ],
    "entry_bar_i": ei,
    "exit_bar_i": xi,
    "pad_before": PAD,
    "pad_after": PAD,
    "bars": window,
    "bars_source": "intraday_cache" if window else "missing",
    "entry_ts": window[ei]["ts"] if window and 0 <= ei < len(window) else None,
    "exit_ts": window[xi]["ts"] if window and 0 <= xi < len(window) else None,
    "trade_id": t.get("trade_id"),
  }
  return row


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
  months_out = []
  all_trades: list[dict] = []

  for name, start, end in MONTHS:
    month_start = cap
    peak = cap
    max_dd = 0.0
    month_trades: list[dict] = []
    print(f"\n===== {name.upper()} 2026 start=₹{month_start:,.2f} =====", flush=True)
    for asof in sessions(start, end):
      if copy_pro_should_sitout(cd):
        cd = register_copy_pro_outcomes(
          cd, [], ticker_cooldown_days=sl, entity_cooldown_days=ent, sitout_after_sl_days=sit
        )
        continue
      ex_t, ex_e = cooldown_excludes(cd)
      rank = rank_pro_buys(
        asof,
        lookback_sessions=int(kw.get("bulk_lookback_sessions") or 1),
        min_win_rate=float(kw.get("bulk_min_win_rate") or 0.55),
        min_n_trades=int(kw.get("bulk_min_n_trades") or 1),
        min_deal_value=float(kw.get("bulk_min_deal_value") or 0),
        exclude_tickers=ex_t or None,
        exclude_entities=ex_e or None,
        wr_prior=float(kw.get("bulk_wr_prior") or 0.55),
        wr_pseudo_n=float(kw.get("bulk_wr_pseudo_n") or 0),
        limit=8,
      )
      picks = list(rank.get("picks") or [])
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
      for raw in day_trades:
        row = normalize_trade(raw, asof, name, picks)
        month_trades.append(row)
        all_trades.append(row)
      cd = register_copy_pro_outcomes(
        cd, day_trades, ticker_cooldown_days=sl, entity_cooldown_days=ent, sitout_after_sl_days=sit
      )
      peak = max(peak, end_cap)
      max_dd = max(max_dd, 100.0 * (peak - end_cap) / peak if peak else 0.0)
      cap = end_cap

    pnl = round(cap - month_start, 2)
    pct = round(100.0 * pnl / month_start, 3) if month_start else 0.0
    wins = sum(1 for t in month_trades if float(t.get("pnl") or 0) > 0)
    months_out.append(
      {
        "month": name,
        "year": 2026,
        "capital_start": round(month_start, 2),
        "capital_end": round(cap, 2),
        "month_pnl": pnl,
        "month_return_pct": pct,
        "max_dd_pct": round(max_dd, 2),
        "n_trades": len(month_trades),
        "wins": wins,
        "losses": len(month_trades) - wins,
        "trades": month_trades,
      }
    )
    print(
      f"  {month_start:,.0f}→{cap:,.2f} ({pct:+.2f}%) trades={len(month_trades)}",
      flush=True,
    )

  total_pnl = round(cap - START, 2)
  oneshot = {
    "generated_at": date.today().isoformat(),
    "year": 2026,
    "window": {"start": "2026-01-01", "end": "2026-08-28"},
    "rule": "one_shot_10k_no_monthly_deposits",
    "strategy": "copy_bulk_pro product (use85 + soft_trail 2.5%/1% + selective 2nd slot)",
    "claim": "paper/session-sim only; modeled India costs ~30 bps RT; not live fills",
    "params": {**kw, "sl_cooldown_days": sl, "entity_cooldown_days": ent, "sitout_after_sl_days": sit},
    "bulk_coverage": cov,
    "capital_start": START,
    "capital_end": round(cap, 2),
    "total_pnl": total_pnl,
    "total_return_pct": round(100.0 * total_pnl / START, 3),
    "months": months_out,
    "n_trades": len(all_trades),
  }
  oneshot_path = ROOT / "models" / "copy_pro_jan_aug_oneshot_10k.json"
  oneshot_path.write_text(json.dumps(oneshot, indent=2, default=str), encoding="utf-8")

  tape = {
    "generated_at": date.today().isoformat(),
    "claim": oneshot["claim"],
    "source": "copy_pro_jan_aug_oneshot full book",
    "year": 2026,
    "window": oneshot["window"],
    "summary": {
      "n_trades": len(all_trades),
      "wins": sum(1 for t in all_trades if float(t["pnl"]) > 0),
      "losses": sum(1 for t in all_trades if float(t["pnl"]) <= 0),
      "invested_total": round(sum(float(t["money_put"]) for t in all_trades), 2),
      "note": "Full Jan–Aug 2026 book fills; book capital on oneshot report",
    },
    "trades": all_trades,
    "sessions": [],
  }
  tape_path = ROOT / "models" / "godfather_desk_tape.json"
  tape_path.write_text(json.dumps(tape, indent=2, default=str), encoding="utf-8")

  print(f"\nWROTE {oneshot_path}", flush=True)
  print(f"WROTE {tape_path} n_trades={len(all_trades)} end=₹{cap:,.2f}", flush=True)
  if DASH.exists():
    shutil.copy2(oneshot_path, DASH / "oneshot_2026.json")
    shutil.copy2(tape_path, DASH / "tape.json")
    print(f"COPIED → {DASH}", flush=True)
  else:
    print(f"SKIP public copy (missing {DASH}) — copy models/*.json onto host desk public/", flush=True)


if __name__ == "__main__":
  main()
