"""copy_bulk_pro integrity audit: concentration, sizing proxies, costs, bootstrap, 2018 fresh OOS.

Does NOT read the stolen/live Postgres bulk DB for the 2018 leg — pulls NSE historicalOR CSV.
Writes models/copy_pro_audit_integrity.json
"""
from __future__ import annotations

import json
import math
import random
import statistics as stats
import sys
import time
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

import yfinance as yf  # noqa: E402

from ingest.nse_client import NSEClient  # noqa: E402

OUT = ROOT / "models" / "copy_pro_audit_integrity.json"
FRESH_2018 = ROOT / "models" / "nse_bulk_fresh_2018.csv"
ONESHOT_2025 = ROOT / "models" / "copy_pro_year_2025_oneshot_10k.json"
COST_BPS_RT = 30.0
START = 10_000.0


def load_2025_trades() -> tuple[dict, list[dict]]:
  d = json.loads(ONESHOT_2025.read_text(encoding="utf-8"))
  trades: list[dict] = []
  for m in d.get("months") or []:
    for t in m.get("trades") or []:
      row = dict(t)
      row["month"] = m.get("month")
      trades.append(row)
  return d, trades


def concentration(trades: list[dict], months: list[dict]) -> dict:
  pnls = [float(t.get("pnl") or 0) for t in trades]
  total = sum(pnls)
  wins = [x for x in pnls if x > 0]
  losses = [x for x in pnls if x <= 0]
  avg_win = sum(wins) / len(wins) if wins else 0.0
  avg_loss = sum(losses) / len(losses) if losses else 0.0
  payoff = abs(avg_win / avg_loss) if avg_loss else None
  ranked = sorted(pnls, reverse=True)
  n5 = max(1, int(0.05 * len(pnls)))
  by_t = Counter(t.get("ticker") for t in trades)
  by_e = Counter((t.get("bulk_entity") or t.get("entity_normalized") or "?") for t in trades)
  month_rets = [float(m.get("month_return_pct") or 0) for m in months]
  mu = stats.mean(month_rets) / 100.0
  sd = stats.pstdev(month_rets) / 100.0 if len(month_rets) > 1 else 0.0
  neg = [r / 100.0 for r in month_rets if r < 0]
  downside = math.sqrt(sum(r * r for r in neg) / len(month_rets)) if month_rets else 0.0
  return {
    "n_trades": len(trades),
    "sum_trade_pnl": round(total, 2),
    "win_rate": round(len(wins) / len(pnls), 4) if pnls else None,
    "avg_win": round(avg_win, 2),
    "avg_loss": round(avg_loss, 2),
    "payoff_ratio": round(payoff, 3) if payoff else None,
    "top5_share_pct": round(100 * sum(ranked[:5]) / total, 1) if total else None,
    "top10_share_pct": round(100 * sum(ranked[:10]) / total, 1) if total else None,
    "top20_share_pct": round(100 * sum(ranked[:20]) / total, 1) if total else None,
    "top5pct_share_pct": round(100 * sum(ranked[:n5]) / total, 1) if total else None,
    "pnl_without_top10": round(total - sum(ranked[:10]), 2),
    "pnl_without_top20": round(total - sum(ranked[:20]), 2),
    "unique_tickers": len(by_t),
    "unique_entities": len(by_e),
    "top_tickers": by_t.most_common(8),
    "top_entities": by_e.most_common(6),
    "herfindahl_ticker": round(sum((c / len(trades)) ** 2 for c in by_t.values()), 4),
    "herfindahl_entity": round(sum((c / len(trades)) ** 2 for c in by_e.values()), 4),
    "effective_n_tickers": round(1 / sum((c / len(trades)) ** 2 for c in by_t.values()), 1)
    if trades
    else None,
    "effective_n_entities": round(1 / sum((c / len(trades)) ** 2 for c in by_e.values()), 1)
    if trades
    else None,
    "monthly_return_pct": [
      {"month": m["month"], "ret_pct": m.get("month_return_pct"), "pnl": m.get("month_pnl"), "n": m.get("n_trades")}
      for m in months
    ],
    "monthly_sharpe_approx": round((mu / sd) * math.sqrt(12), 2) if sd else None,
    "monthly_sortino_approx": round((mu / downside) * math.sqrt(12), 2) if downside else None,
    "dec_share_of_book_pnl_pct": round(
      100 * float(next(m["month_pnl"] for m in months if m["month"] == "december")) / float(
        sum(float(x.get("month_pnl") or 0) for x in months) or 1
      ),
      1,
    ),
  }


def sizing_proxies(trades: list[dict], months: list[dict], book_pnl: float) -> dict:
  # Flat monthly: apply each month's return% to a fresh ₹10k book (no cross-month compound).
  flat_pnl = sum(START * float(m.get("month_return_pct") or 0) / 100.0 for m in months)
  # Fixed ₹5k notional per fill using pnl_pct.
  fixed = []
  for t in trades:
    pct = t.get("pnl_pct")
    if pct is None and t.get("entry_notional"):
      pct = 100.0 * float(t["pnl"]) / float(t["entry_notional"])
    if pct is None:
      continue
    fixed.append(5000.0 * float(pct) / 100.0)
  # Cost stress: subtract extra 30 bps RT on entry notional (double modeled cost).
  extra = []
  for t in trades:
    notional = float(t.get("entry_notional") or 0)
    pnl = float(t.get("pnl") or 0)
    fees = float(t.get("fees") or 0)
    # modeled already ~30bps; double => subtract another ~30bps of notional
    stressed = pnl - notional * (COST_BPS_RT / 10000.0)
    extra.append(stressed)
  return {
    "oneshot_compound_book_pnl": round(book_pnl, 2),
    "note_capital_rule": "2025 oneshot = ₹10k once, P&L compounds in-book. NOT monthly ₹10k+50% profit deposits.",
    "flat_monthly_10k_proxy_pnl": round(flat_pnl, 2),
    "flat_vs_compound_ratio": round(flat_pnl / book_pnl, 3) if book_pnl else None,
    "fixed_5k_notional_proxy_pnl": round(sum(fixed), 2),
    "fixed_5k_mean_pnl": round(sum(fixed) / len(fixed), 2) if fixed else None,
    "cost_double_proxy_sum_trade_pnl": round(sum(extra), 2),
    "cost_double_vs_raw_trade_sum": round(sum(extra) / sum(float(t.get("pnl") or 0) for t in trades), 3)
    if trades
    else None,
  }


def bootstrap_paths(trades: list[dict], n: int = 400, seed: int = 7) -> dict:
  """Resample trade pnl_pct sequence; compound on fixed use85-ish capital path approx."""
  rng = random.Random(seed)
  pcts = []
  for t in trades:
    pct = t.get("pnl_pct")
    if pct is None and t.get("entry_notional"):
      pct = 100.0 * float(t["pnl"]) / float(t["entry_notional"])
    if pct is not None:
      pcts.append(float(pct) / 100.0)
  finals = []
  for _ in range(n):
    cap = START
    sample = [rng.choice(pcts) for _ in pcts]
    for r in sample:
      # rough: deploy 85% at 2.7x lev → notional impact ~ capital * use * (pnl_pct on notional)
      # pnl_pct in tape is on notional; capital impact ≈ use_frac * pnl_pct (lev cancels with slot)
      cap *= 1.0 + 0.85 * r
      if cap <= 100:
        break
    finals.append(cap)
  finals.sort()
  return {
    "n_boot": n,
    "final_p5": round(finals[int(0.05 * n)], 2),
    "final_p25": round(finals[int(0.25 * n)], 2),
    "final_p50": round(finals[int(0.50 * n)], 2),
    "final_p75": round(finals[int(0.75 * n)], 2),
    "final_p95": round(finals[int(0.95 * n)], 2),
    "pct_below_start": round(100 * sum(1 for x in finals if x < START) / n, 1),
    "caveat": "Bootstrap resamples observed trade returns; does not fix leakage in ranking.",
  }


def walk_forward_split(months: list[dict]) -> dict:
  first = [m for m in months if m["month"] in ("january", "february", "march", "april", "may", "june")]
  second = [m for m in months if m["month"] in ("july", "august", "september", "october", "november", "december")]
  def path(ms):
    cap = START
    for m in ms:
      cap *= 1.0 + float(m.get("month_return_pct") or 0) / 100.0
    return round(cap, 2)
  return {
    "note": "NOT true walk-forward (knobs were tuned on 2026, not H1-2025). Split shows 2025 path concentration.",
    "h1_end_if_10k": path(first),
    "h2_end_if_10k": path(second),
    "h1_mean_month_ret_pct": round(stats.mean(float(m["month_return_pct"]) for m in first), 2),
    "h2_mean_month_ret_pct": round(stats.mean(float(m["month_return_pct"]) for m in second), 2),
  }


def top_winners(trades: list[dict], n: int = 15) -> list[dict]:
  top = sorted(trades, key=lambda t: float(t.get("pnl") or 0), reverse=True)[:n]
  out = []
  for t in top:
    out.append(
      {
        "asof": (t.get("asof") or str(t.get("entry_date") or ""))[:10],
        "ticker": t.get("ticker"),
        "pnl": round(float(t.get("pnl") or 0), 2),
        "pnl_pct": t.get("pnl_pct"),
        "exit_reason": t.get("exit_reason"),
        "entity": t.get("bulk_entity"),
        "entry": t.get("entry_price"),
        "exit": t.get("exit_price"),
        "spot_check": "MANUAL — verify NSE bulk page for prior session + unadjusted chart",
      }
    )
  return out


def pull_fresh_2018() -> list[dict]:
  client = NSEClient()
  rows: list[dict] = []
  windows = [
    (datetime(2018, 1, 1), datetime(2018, 3, 31)),
    (datetime(2018, 4, 1), datetime(2018, 6, 30)),
    (datetime(2018, 7, 1), datetime(2018, 9, 30)),
    (datetime(2018, 10, 1), datetime(2018, 12, 31)),
  ]
  for a, b in windows:
    print(f"NSE historicalOR bulk {a.date()} -> {b.date()}", flush=True)
    part = client.fetch_historical_deals("bulk_deals", a, b)
    print(f"  rows={len(part)}", flush=True)
    rows.extend(part)
    time.sleep(1.2)
  for a, b in windows:
    print(f"NSE historicalOR block {a.date()} -> {b.date()}", flush=True)
    try:
      part = client.fetch_historical_deals("block_deals", a, b)
      print(f"  rows={len(part)}", flush=True)
      rows.extend(part)
    except Exception as exc:  # noqa: BLE001
      print(f"  block fail: {exc}", flush=True)
    time.sleep(1.2)
  import csv

  if rows:
    keys = sorted({k for r in rows for k in r.keys()})
    with FRESH_2018.open("w", encoding="utf-8", newline="") as f:
      w = csv.DictWriter(f, fieldnames=keys)
      w.writeheader()
      for r in rows:
        w.writerow({k: r.get(k) for k in keys})
  print(f"WROTE {FRESH_2018} n={len(rows)}", flush=True)
  return rows


def _norm_entity(s: str) -> str:
  return " ".join(str(s or "").upper().split())


def backtest_2018_fresh(rows: list[dict]) -> dict:
  """Frozen-knob-ish OOS on fresh 2018 deals — NO Postgres investor_stats.

  Ranking: prior-session BUY value × PIT win-rate from earlier deals' next-day open→close
  (Yahoo daily, auto_adjust=False for this audit leg).
  Execution: next session open → close, cost 30bps RT, use 85% capital, max 2 names, lev 1x daily proxy.
  """
  buys = []
  for r in rows:
    action = str(r.get("action") or "").upper()
    if action not in ("BUY", "B"):
      continue
    disc = r.get("disclosed_at")
    if isinstance(disc, datetime):
      d = disc.astimezone().date()
      # disclosed_at is IST midnight stored as prior UTC evening → deal calendar date ≈ disc IST date
      # NSEClient stores as UTC; deal date for IST midnight is disc.date() in IST
      from zoneinfo import ZoneInfo

      d = disc.astimezone(ZoneInfo("Asia/Kolkata")).date()
    else:
      continue
    ticker = str(r.get("ticker_normalized") or r.get("ticker") or "").upper()
    if not ticker.endswith(".NS"):
      ticker = f"{ticker}.NS"
    val = float(r.get("value") or 0)
    if val <= 0:
      qty = float(r.get("qty") or 0)
      # archive rows may need price*qty — skip if no value
      continue
    buys.append(
      {
        "deal_date": d.isoformat(),
        "ticker": ticker,
        "entity": _norm_entity(r.get("entity_normalized") or r.get("entity") or ""),
        "value": val,
      }
    )
  buys.sort(key=lambda x: x["deal_date"])
  print(f"2018 BUY deals usable={len(buys)}", flush=True)

  # group by deal_date
  by_day: dict[str, list[dict]] = defaultdict(list)
  for b in buys:
    by_day[b["deal_date"]].append(b)

  # trading calendar weekdays 2018
  sessions = []
  d0 = date(2018, 1, 1)
  while d0 <= date(2018, 12, 31):
    if d0.weekday() < 5:
      sessions.append(d0)
    d0 += timedelta(days=1)

  def prior_weekday(d: date) -> date:
    x = d - timedelta(days=1)
    while x.weekday() >= 5:
      x -= timedelta(days=1)
    return x

  # cache daily OHLC auto_adjust=False
  ohlc_cache: dict[str, dict[str, tuple[float, float]]] = {}

  def day_oc(ticker: str, day: date) -> tuple[float, float] | None:
    if ticker not in ohlc_cache:
      try:
        hist = yf.Ticker(ticker).history(start="2017-12-01", end="2019-01-15", auto_adjust=False)
      except Exception:
        ohlc_cache[ticker] = {}
        return None
      mp: dict[str, tuple[float, float]] = {}
      for idx, row in hist.iterrows():
        key = str(idx.date())
        o = float(row.get("Open") or 0)
        c = float(row.get("Close") or 0)
        if o > 0 and c > 0:
          mp[key] = (o, c)
      ohlc_cache[ticker] = mp
      time.sleep(0.15)
    return ohlc_cache[ticker].get(day.isoformat())

  # PIT entity stats: after observing a next-day return, update
  ent_w: dict[str, list[float]] = defaultdict(list)

  def pit_wr(entity: str) -> float:
    xs = ent_w.get(entity) or []
    if len(xs) < 1:
      return 0.55  # prior
    wins = sum(1 for x in xs if x > 0)
    raw = wins / len(xs)
    # shrink toward 0.55 with pseudo_n=5 like product intent (product uses 0 for pseudo in registry!)
    return (raw * len(xs) + 0.55 * 5) / (len(xs) + 5)

  cap = START
  trades_out = []
  months_pnl = defaultdict(float)
  peak = cap
  max_dd = 0.0

  for asof in sessions:
    prior = prior_weekday(asof)
    deals = by_day.get(prior.isoformat()) or []
    if not deals:
      continue
    # aggregate value by ticker+entity
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
      ret = (c - o) / o
      # 30 bps RT
      ret_net = ret - (COST_BPS_RT / 10000.0)
      pnl = slot * ret_net
      day_pnl += pnl
      trades_out.append(
        {
          "asof": asof.isoformat(),
          "ticker": ticker,
          "entity": entity,
          "deal_value": value,
          "pit_wr": round(wr, 4),
          "score": round(score, 4),
          "open": o,
          "close": c,
          "ret_net": round(ret_net, 5),
          "pnl": round(pnl, 2),
          "slot": round(slot, 2),
        }
      )
      # update PIT after observing this next-day move (for future ranks only)
      ent_w[entity].append(ret_net)
    cap = round(cap + day_pnl, 2)
    months_pnl[asof.strftime("%Y-%m")] += day_pnl
    peak = max(peak, cap)
    max_dd = max(max_dd, 100.0 * (peak - cap) / peak if peak else 0.0)

  wins = sum(1 for t in trades_out if t["pnl"] > 0)
  return {
    "source": "NSE historicalOR fresh pull — not Postgres signals DB",
    "claim": "Daily open→close proxy; auto_adjust=False; PIT entity WR from CSV only; frozen-ish filters (min WR 0.55 after n>=3)",
    "n_deal_rows": len(rows),
    "n_buy_deals": len(buys),
    "n_trades": len(trades_out),
    "wins": wins,
    "losses": len(trades_out) - wins,
    "capital_start": START,
    "capital_end": round(cap, 2),
    "total_pnl": round(cap - START, 2),
    "total_return_pct": round(100.0 * (cap - START) / START, 3),
    "max_dd_pct": round(max_dd, 2),
    "monthly_pnl": {k: round(v, 2) for k, v in sorted(months_pnl.items())},
    "top_trades": sorted(trades_out, key=lambda t: t["pnl"], reverse=True)[:10],
    "bottom_trades": sorted(trades_out, key=lambda t: t["pnl"])[:10],
  }


def code_verdicts() -> dict:
  return {
    "publish_time": {
      "verdict": "FAIL",
      "detail": "disclosed_at = deal DATE at 00:00 IST → UTC, not NSE publish/scrape clock. Late posts indistinguishable.",
    },
    "investor_wr_lookahead": {
      "verdict": "FAIL",
      "detail": "investor_stats is full-sample live table (3mo forward returns). rank_pro_buys joins current WR — not PIT as-of trade date.",
    },
    "same_day_window": {
      "verdict": "FAIL_INTENT",
      "detail": "prior_session_window uses asof 00:00 UTC vs IST-midnight stamps → same IST day deals can enter; true prior IST day can drop.",
    },
    "yahoo_auto_adjust": {
      "verdict": "FAIL",
      "detail": "intraday_bars + day_sim use auto_adjust=True — splits/bonuses can distort OHLC path PnL.",
    },
    "knob_selection": {
      "verdict": "TUNED_ON_2026",
      "detail": "Product knobs from May–Aug 2026 ablation/returns-push (docs 2026-08-29). 2025 is evaluate-after-tune, not selection window — but WR leakage still contaminates 2025.",
    },
    "capital_rule_2025": {
      "verdict": "ONESHOT_10K_COMPOUND",
      "detail": "run_copy_pro_year_2025_oneshot.py: one-shot ₹10k, no monthly deposits. ₹10k+50% profit deposit is ONLY run_copy_pro_jan_aug_deposit.py (2026).",
    },
  }


def main() -> None:
  report: dict = {
    "generated_at": date.today().isoformat(),
    "verdicts": code_verdicts(),
  }
  d2025, trades = load_2025_trades()
  months = d2025.get("months") or []
  report["concentration_2025"] = concentration(trades, months)
  report["sizing_2025"] = sizing_proxies(trades, months, float(d2025.get("total_pnl") or 0))
  report["bootstrap_2025"] = bootstrap_paths(trades)
  report["walk_forward_split_2025"] = walk_forward_split(months)
  report["top_winners_spotcheck_queue"] = top_winners(trades)
  report["robustness"] = {
    "entry_shift_sl_perturbation": "NOT_RUN — needs re-sim grid (±10–20% trail/stop, entry bar ±N).",
    "walk_forward_true": "NOT_RUN — would require retuning knobs on H1 only then freeze for H2; knobs already from 2026.",
  }

  print("Pulling fresh 2018 NSE bulk/block (no DB)…", flush=True)
  rows = pull_fresh_2018()
  report["oos_2018_fresh"] = backtest_2018_fresh(rows)

  OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
  print(f"WROTE {OUT}", flush=True)
  oos = report["oos_2018_fresh"]
  print(
    f"2018 fresh: {oos['capital_start']}->{oos['capital_end']} ({oos['total_return_pct']}%) "
    f"trades={oos['n_trades']}",
    flush=True,
  )


if __name__ == "__main__":
  main()
