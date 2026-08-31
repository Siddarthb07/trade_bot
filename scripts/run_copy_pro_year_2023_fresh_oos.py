"""Fresh NSE historicalOR 2023 OOS — no Postgres bulk DB.

Same method as 2018 audit leg: prior-session BUY × PIT entity WR, daily open→close,
auto_adjust=False, 30bps RT, capital = start + sum(pnl).
Writes models/copy_pro_year_2023_fresh_oos.json and public/year_2023.json
"""
from __future__ import annotations

import csv
import json
import math
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

import yfinance as yf
from ingest.nse_client import NSEClient
from zoneinfo import ZoneInfo

OUT = ROOT / "models" / "copy_pro_year_2023_fresh_oos.json"
CSV_OUT = ROOT / "models" / "nse_bulk_fresh_2023.csv"
DASH = Path(r"C:\Users\siddu\Projects\GodFather-core\apps\dashboard\public")
START = 10_000.0
COST_BPS_RT = 30.0
YEAR = 2023


def pull_year(year: int) -> list[dict]:
  client = NSEClient()
  rows: list[dict] = []
  windows = [
    (datetime(year, 1, 1), datetime(year, 3, 31)),
    (datetime(year, 4, 1), datetime(year, 6, 30)),
    (datetime(year, 7, 1), datetime(year, 9, 30)),
    (datetime(year, 10, 1), datetime(year, 12, 31)),
  ]
  for a, b in windows:
    print(f"bulk {a.date()} -> {b.date()}", flush=True)
    part = client.fetch_historical_deals("bulk_deals", a, b)
    print(f"  rows={len(part)}", flush=True)
    rows.extend(part)
    time.sleep(1.2)
  for a, b in windows:
    print(f"block {a.date()} -> {b.date()}", flush=True)
    try:
      part = client.fetch_historical_deals("block_deals", a, b)
      print(f"  rows={len(part)}", flush=True)
      rows.extend(part)
    except Exception as exc:  # noqa: BLE001
      print(f"  block fail: {exc}", flush=True)
    time.sleep(1.2)
  if rows:
    keys = sorted({k for r in rows for k in r.keys()})
    with CSV_OUT.open("w", encoding="utf-8", newline="") as f:
      w = csv.DictWriter(f, fieldnames=keys)
      w.writeheader()
      for r in rows:
        w.writerow({k: r.get(k) for k in keys})
  print(f"WROTE {CSV_OUT} n={len(rows)}", flush=True)
  return rows


def _norm_entity(s: str) -> str:
  return " ".join(str(s or "").upper().split())


def backtest(rows: list[dict], year: int) -> dict:
  buys = []
  for r in rows:
    action = str(r.get("action") or "").upper()
    if action not in ("BUY", "B"):
      continue
    disc = r.get("disclosed_at")
    if not isinstance(disc, datetime):
      continue
    d = disc.astimezone(ZoneInfo("Asia/Kolkata")).date()
    ticker = str(r.get("ticker_normalized") or r.get("ticker") or "").upper()
    if not ticker.endswith(".NS"):
      ticker = f"{ticker}.NS"
    val = float(r.get("value") or 0)
    if val <= 0:
      continue
    buys.append(
      {
        "deal_date": d.isoformat(),
        "ticker": ticker,
        "entity": _norm_entity(r.get("entity_normalized") or r.get("entity") or ""),
        "value": val,
      }
    )
  by_day: dict[str, list[dict]] = defaultdict(list)
  for b in buys:
    by_day[b["deal_date"]].append(b)

  sessions = []
  d0 = date(year, 1, 1)
  while d0 <= date(year, 12, 31):
    if d0.weekday() < 5:
      sessions.append(d0)
    d0 += timedelta(days=1)

  def prior_weekday(d: date) -> date:
    x = d - timedelta(days=1)
    while x.weekday() >= 5:
      x -= timedelta(days=1)
    return x

  ohlc_cache: dict[str, dict[str, tuple[float, float]]] = {}

  def day_oc(ticker: str, day: date) -> tuple[float, float] | None:
    if ticker not in ohlc_cache:
      try:
        hist = yf.Ticker(ticker).history(
          start=f"{year - 1}-12-01", end=f"{year + 1}-01-15", auto_adjust=False
        )
      except Exception:
        ohlc_cache[ticker] = {}
        return None
      mp: dict[str, tuple[float, float]] = {}
      for idx, row in hist.iterrows():
        o = float(row.get("Open") or 0)
        c = float(row.get("Close") or 0)
        if o > 0 and c > 0:
          mp[str(idx.date())] = (o, c)
      ohlc_cache[ticker] = mp
      time.sleep(0.12)
    return ohlc_cache[ticker].get(day.isoformat())

  ent_w: dict[str, list[float]] = defaultdict(list)

  def pit_wr(entity: str) -> float:
    xs = ent_w.get(entity) or []
    if len(xs) < 1:
      return 0.55
    raw = sum(1 for x in xs if x > 0) / len(xs)
    return (raw * len(xs) + 0.55 * 5) / (len(xs) + 5)

  cap = START
  trades_out = []
  months_out = []
  month_trades: list[dict] = []
  month_start = cap
  cur_month = None
  peak = cap
  max_dd = 0.0

  def flush_month(name: str):
    nonlocal month_trades, month_start, cap, max_dd, peak
    pnl = round(cap - month_start, 2)
    months_out.append(
      {
        "month": name,
        "year": year,
        "capital_start": round(month_start, 2),
        "capital_end": round(cap, 2),
        "month_pnl": pnl,
        "month_return_pct": round(100.0 * pnl / month_start, 3) if month_start else 0.0,
        "max_dd_pct": round(max_dd, 2),
        "n_trades": len(month_trades),
        "wins": sum(1 for t in month_trades if t["pnl"] > 0),
        "losses": sum(1 for t in month_trades if t["pnl"] <= 0),
        "trades": list(month_trades),
      }
    )
    month_trades = []
    month_start = cap
    peak = cap
    max_dd = 0.0

  month_names = [
    "",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
  ]

  for asof in sessions:
    mname = month_names[asof.month]
    if cur_month is None:
      cur_month = mname
    elif mname != cur_month:
      flush_month(cur_month)
      cur_month = mname

    prior = prior_weekday(asof)
    deals = by_day.get(prior.isoformat()) or []
    if not deals:
      continue
    agg: dict[tuple[str, str], float] = defaultdict(float)
    for drow in deals:
      agg[(drow["ticker"], drow["entity"])] += drow["value"]
    scored = []
    for (ticker, entity), value in agg.items():
      wr = pit_wr(entity)
      if wr < 0.55 and len(ent_w.get(entity) or []) >= 3:
        continue
      score = wr * math.log10(max(value, 1.0))
      scored.append((score, ticker, entity, value, wr))
    scored.sort(reverse=True)
    picks = scored[:2]
    if not picks:
      continue
    slot = cap * 0.85 / max(1, len(picks))
    day_pnl = 0.0
    for score, ticker, entity, value, wr in picks:
      oc = day_oc(ticker, asof)
      if not oc:
        continue
      o, c = oc
      ret_net = (c - o) / o - (COST_BPS_RT / 10000.0)
      pnl = round(slot * ret_net, 2)
      day_pnl += pnl
      row = {
        "asof": asof.isoformat(),
        "month": mname,
        "year": year,
        "ticker": ticker,
        "entity": entity,
        "deal_value": value,
        "pit_wr": round(wr, 4),
        "open": o,
        "close": c,
        "pnl": pnl,
        "pnl_pct": round(100.0 * ret_net, 3),
        "slot_capital": round(slot, 2),
        "entry_notional": round(slot, 2),
        "exit_notional": round(slot * (1 + ret_net), 2),
        "fees": round(slot * (COST_BPS_RT / 10000.0), 4),
        "money_put": round(slot, 2),
        "money_returned": round(slot * (1 + ret_net), 2),
        "choice_notes": f"Fresh {year} PIT rank score={score:.3f} WR={wr:.3f} deal=₹{value:,.0f}",
        "loss_analysis": f"{'Win' if pnl > 0 else 'Loss'} open→close {ret_net*100:+.2f}% after 30bps",
      }
      trades_out.append(row)
      month_trades.append(row)
      ent_w[entity].append(ret_net)
    # Ledger identity: book moves by sum of trade pnls only
    cap = round(cap + day_pnl, 2)
    peak = max(peak, cap)
    max_dd = max(max_dd, 100.0 * (peak - cap) / peak if peak else 0.0)

  if cur_month:
    flush_month(cur_month)

  total_pnl = round(cap - START, 2)
  return {
    "generated_at": date.today().isoformat(),
    "year": year,
    "window": {"start": f"{year}-01-01", "end": f"{year}-12-31"},
    "rule": "fresh_nse_historicalOR_pit_daily_open_close",
    "strategy": "copy_bulk_pro-like OOS (PIT WR, no Postgres investor_stats)",
    "claim": (
      "Fresh NSE historicalOR pull — not stolen/Postgres DB. "
      "Daily open→close proxy; auto_adjust=False; capital=start+sum(pnl)."
    ),
    "capital_start": START,
    "capital_end": round(cap, 2),
    "total_pnl": total_pnl,
    "total_return_pct": round(100.0 * total_pnl / START, 3),
    "n_trades": len(trades_out),
    "wins": sum(1 for t in trades_out if t["pnl"] > 0),
    "losses": sum(1 for t in trades_out if t["pnl"] <= 0),
    "n_deal_rows": len(rows),
    "n_buy_deals": len(buys),
    "capital_accounting": {
      "rule": "capital_end = capital_start + sum(trade.pnl)",
      "sum_trade_pnl": round(sum(t["pnl"] for t in trades_out), 2),
    },
    "months": months_out,
  }


def main() -> None:
  rows = pull_year(YEAR)
  report = backtest(rows, YEAR)
  OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
  if DASH.exists():
    (DASH / f"year_{YEAR}.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
  print(
    f"WROTE {OUT}: {report['capital_start']} -> {report['capital_end']} "
    f"({report['total_return_pct']}%) trades={report['n_trades']} "
    f"sum_pnl={report['capital_accounting']['sum_trade_pnl']}",
    flush=True,
  )


if __name__ == "__main__":
  main()
