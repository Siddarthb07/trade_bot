"""Export operator desk tape: trades + why + OHLC windows from cache.

Writes models/godfather_desk_tape.json and copies to GodFather-core public/tape.json.
Default window: last ~15 weekdays ending 2026-08-28 (cached bars available).
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
  register_copy_pro_outcomes,
  rank_pro_buys,
)

CACHE = ROOT / "models" / "intraday_cache"
OUT = ROOT / "models" / "godfather_desk_tape.json"
DASH_PUBLIC = Path(r"C:\Users\siddu\Projects\GodFather-core\apps\dashboard\public")
PAD = 4
START_CAP = 10_000.0
END = date(2026, 8, 28)
DAYS = 15


def sessions(end: date, n_weekdays: int) -> list[str]:
  out: list[str] = []
  d = end
  while len(out) < n_weekdays:
    if d.weekday() < 5:
      out.append(d.isoformat())
    d -= timedelta(days=1)
  return list(reversed(out))


def load_bars(ticker: str, asof: str) -> list[dict]:
  path = CACHE / ticker / f"{asof}_5m.json"
  if not path.exists():
    # try without .NS
    alt = ticker.replace(".NS", "")
    path = CACHE / f"{alt}.NS" / f"{asof}_5m.json"
  if not path.exists():
    return []
  try:
    raw = json.loads(path.read_text(encoding="utf-8"))
  except Exception:
    return []
  bars = []
  for b in raw:
    bars.append(
      {
        "ts": b.get("ts") or b.get("date"),
        "open": float(b.get("open") or b.get("close") or 0),
        "high": float(b.get("high") or b.get("close") or 0),
        "low": float(b.get("low") or b.get("close") or 0),
        "close": float(b.get("close") or 0),
        "volume": float(b.get("volume") or 0),
      }
    )
  return bars


def slice_bars(bars: list[dict], entry_i: int | None, exit_i: int | None) -> tuple[list[dict], int, int, int]:
  if not bars:
    return [], 0, 0, 0
  ei = int(entry_i) if entry_i is not None else 0
  xi = int(exit_i) if exit_i is not None else len(bars) - 1
  ei = max(0, min(ei, len(bars) - 1))
  xi = max(ei, min(xi, len(bars) - 1))
  lo = max(0, ei - PAD)
  hi = min(len(bars), xi + PAD + 1)
  window = bars[lo:hi]
  return window, ei - lo, xi - lo, PAD


def loss_note(t: dict) -> str:
  pnl = float(t.get("pnl") or 0)
  reason = str(t.get("exit_reason") or t.get("exit") or "")
  pnl_pct = float(t.get("pnl_pct") or 0)
  lev = float(t.get("leverage") or t.get("lev") or 0)
  if pnl >= 0:
    return f"Closed green via {reason} ({pnl_pct:+.2f}% on notional, lev {lev:.1f}x)."
  if "stop" in reason:
    return (
      f"Stop hit ({reason}). Price moved against entry; leverage {lev:.1f}x "
      f"amplified notional to {pnl_pct:+.2f}% / ₹{pnl:,.2f}."
    )
  if "trail" in reason:
    return f"Trail exit after giveback ({reason}). Final {pnl_pct:+.2f}% / ₹{pnl:,.2f}."
  if "session" in reason or "close" in reason:
    return (
      f"Held to session end red. Underlying path did not recover; fees "
      f"₹{float(t.get('fees') or 0):.2f}. Final {pnl_pct:+.2f}%."
    )
  return f"Loss via {reason}: {pnl_pct:+.2f}% / ₹{pnl:,.2f}."


def choice_note(pick: dict | None, alts: list[dict], t: dict) -> str:
  parts = []
  if pick:
    parts.append(
      f"Ranked #1 by bulk score {pick.get('score')} "
      f"(WR {pick.get('win_rate_eff') or pick.get('win_rate')}, "
      f"deal ₹{float(pick.get('value') or 0):,.0f}, "
      f"entity {pick.get('entity_normalized')})."
    )
  else:
    parts.append(
      f"Copy-pro pick {t.get('ticker')} score={t.get('bulk_score')} "
      f"WR={t.get('bulk_wr')} entity={t.get('bulk_entity')}."
    )
  if alts:
    top = ", ".join(f"{a.get('ticker')}({a.get('score')})" for a in alts[:3])
    parts.append(f"Next ranks: {top}.")
  reason = t.get("signal_reason") or t.get("reason")
  if reason:
    parts.append(f"Signal: {reason}.")
  return " ".join(parts)


def main() -> None:
  dates = sessions(END, DAYS)
  cov = bulk_data_coverage(since=dates[0])
  print("coverage", cov, flush=True)
  kw = sim_kwargs_for_strategy("copy_bulk_pro", "product")
  kw.pop("bar_interval", None)
  sl = int(kw.pop("sl_cooldown_days", 1) or 1)
  ent = int(kw.pop("entity_cooldown_days", 1) or 1)
  sit = int(kw.pop("sitout_after_sl_days", 0) or 0)

  cap = START_CAP
  cd = empty_copy_pro_cooldown()
  sessions_out: list[dict] = []
  trades_flat: list[dict] = []

  for asof in dates:
    print(f"=== {asof} cap={cap:.2f} ===", flush=True)
    if copy_pro_should_sitout(cd):
      cd = register_copy_pro_outcomes(
        cd, [], ticker_cooldown_days=sl, entity_cooldown_days=ent, sitout_after_sl_days=sit
      )
      sessions_out.append(
        {
          "asof": asof,
          "capital_start": round(cap, 2),
          "capital_end": round(cap, 2),
          "sitout": True,
          "picks": [],
          "skipped": [],
          "trades": [],
        }
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
    skipped = list(res.get("skipped") or [])
    enriched = []
    for t in day_trades:
      ticker = str(t.get("ticker") or "")
      bars_full = load_bars(ticker, asof)
      entry_i = t.get("entry_bar_i")
      exit_i = t.get("exit_bar_i")
      window, ei_rel, xi_rel, pad = slice_bars(bars_full, entry_i, exit_i)
      pick = next((p for p in picks if str(p.get("ticker")) == ticker), None)
      alts = [p for p in picks if str(p.get("ticker")) != ticker]
      row = {
        "asof": asof,
        "trade_id": t.get("trade_id"),
        "ticker": ticker,
        "side": t.get("side") or "long",
        "entry_price": t.get("entry_price") or t.get("entry_px"),
        "exit_price": t.get("exit_price") or t.get("exit_px"),
        "entry_notional": t.get("entry_notional") or t.get("money_put"),
        "exit_notional": t.get("exit_notional") or t.get("money_returned"),
        "qty": t.get("qty"),
        "leverage": t.get("leverage") or t.get("lev"),
        "pnl": t.get("pnl"),
        "pnl_pct": t.get("pnl_pct"),
        "fees": t.get("fees"),
        "exit_reason": t.get("exit_reason") or t.get("exit"),
        "signal_reason": t.get("signal_reason") or t.get("reason"),
        "bulk_entity": t.get("bulk_entity") or (pick or {}).get("entity_normalized"),
        "bulk_score": t.get("bulk_score") if t.get("bulk_score") is not None else (pick or {}).get("score"),
        "bulk_wr": t.get("bulk_wr")
        if t.get("bulk_wr") is not None
        else (pick or {}).get("win_rate_eff") or (pick or {}).get("win_rate"),
        "slot_capital": t.get("slot_capital"),
        "entry_bar_i": ei_rel,
        "exit_bar_i": xi_rel,
        "pad_before": pad,
        "pad_after": pad,
        "choice_notes": choice_note(pick, alts, t),
        "loss_analysis": loss_note(t),
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
        "bars": window,
        "bars_source": "intraday_cache" if window else "missing",
      }
      enriched.append(row)
      trades_flat.append(row)

    cd = register_copy_pro_outcomes(
      cd, day_trades, ticker_cooldown_days=sl, entity_cooldown_days=ent, sitout_after_sl_days=sit
    )
    sessions_out.append(
      {
        "asof": asof,
        "capital_start": round(cap, 2),
        "capital_end": round(end_cap, 2),
        "picks": picks,
        "skipped": skipped,
        "trades": enriched,
        "rank_window": {"start": rank.get("window_start"), "end": rank.get("window_end")},
      }
    )
    print(
      f"  → {end_cap:.2f} trades={len(enriched)} picks={len(picks)} bars_ok="
      f"{sum(1 for x in enriched if x['bars'])}",
      flush=True,
    )
    cap = end_cap

  wins = sum(1 for t in trades_flat if float(t.get("pnl") or 0) > 0)
  out = {
    "generated_at": date.today().isoformat(),
    "claim": "paper/session-sim only; modeled India costs ~30 bps RT; not live fills",
    "window": {"start": dates[0], "end": dates[-1], "n_sessions": len(dates)},
    "params": {
      **{k: kw.get(k) for k in (
        "capital_use_frac",
        "soft_trail_arm_pct",
        "soft_trail_pct",
        "max_positions",
        "bulk_second_min_wr",
        "bulk_second_min_score_gap",
        "max_leverage",
      )},
      "sitout_after_sl_days": sit,
    },
    "bulk_coverage": cov,
    "summary": {
      "capital_start": START_CAP,
      "capital_end": round(cap, 2),
      "total_pnl": round(cap - START_CAP, 2),
      "total_return_pct": round(100.0 * (cap - START_CAP) / START_CAP, 3),
      "n_trades": len(trades_flat),
      "wins": wins,
      "losses": len(trades_flat) - wins,
    },
    "sessions": sessions_out,
    "trades": trades_flat,
  }
  OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
  print("WROTE", OUT, flush=True)
  DASH_PUBLIC.mkdir(parents=True, exist_ok=True)
  shutil.copy2(OUT, DASH_PUBLIC / "tape.json")
  print("COPIED", DASH_PUBLIC / "tape.json", flush=True)


if __name__ == "__main__":
  main()
