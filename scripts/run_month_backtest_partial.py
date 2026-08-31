"""Full calendar-month paper backtest: ₹10k, never deploy full equity.

Uses guarded OR-width product with capital_use_frac < 1 so margin base
is a fraction of book (cash buffer stays untraded). Prints per-day PnL,
trade counts, and month totals.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.day_sim import simulate_day
from processor.orwidth_product import DEFAULT_PAPER_PRODUCT, product_kwargs

CAPITAL = 10_000.0
# Never put the full book behind a trade — 50% equity as margin base.
CAPITAL_USE_FRAC = 0.50


def _sessions(start: str, end: str) -> list[str]:
  sd, ed = date.fromisoformat(start), date.fromisoformat(end)
  out: list[str] = []
  d = sd
  while d <= ed:
    if d.weekday() < 5:
      out.append(d.isoformat())
    d += timedelta(days=1)
  return out


def main() -> None:
  import argparse

  ap = argparse.ArgumentParser()
  ap.add_argument("--product", default=DEFAULT_PAPER_PRODUCT)
  ap.add_argument("--start", default="2026-08-01")
  ap.add_argument("--end", default="2026-08-28")
  ap.add_argument("--capital", type=float, default=CAPITAL)
  ap.add_argument(
    "--capital-use",
    type=float,
    default=CAPITAL_USE_FRAC,
    help="Fraction of equity used as margin base (≤1; default 0.50)",
  )
  args = ap.parse_args()

  days = _sessions(args.start, args.end)
  kw = product_kwargs(args.product)
  kw.pop("bar_interval", None)
  use_frac = max(0.05, min(1.0, float(args.capital_use)))

  print(
    f"MONTH BACKTEST | product={args.product} | INR {args.capital:,.0f} start | "
    f"capital_use={use_frac:.0%} | {days[0]} -> {days[-1]} ({len(days)} sessions)",
    flush=True,
  )
  print(f"params={kw}", flush=True)
  print(
    f"{'Day':<12} {'Start':>10} {'End':>10} {'Day PnL':>12} {'Ret%':>8} "
    f"{'Trades':>6} {'Money put':>12}",
    flush=True,
  )
  print("-" * 78, flush=True)

  cap = float(args.capital)
  start_cap = cap
  daily: list[dict] = []
  total_trades = 0
  peak, max_dd = cap, 0.0
  min_ret, max_ret = 999.0, -999.0

  for i, asof in enumerate(days, 1):
    print(f"  [{i}/{len(days)}] {asof} ...", flush=True)
    res = simulate_day(
      asof=asof,
      capital=cap,
      currency="INR",
      market="IN",
      path_mode="session",
      max_positions=1,
      allow_demo_fallback=False,
      capital_use_frac=use_frac,
      **kw,
    )
    cap_start = cap
    ret = float(res.get("return_pct") or 0)
    cap_end = float(res.get("capital_end") or cap_start)
    # Equity change is the compounding truth (realized trade pnl can diverge with borrow/fees).
    pnl = round(cap_end - cap_start, 2)
    n_trades = int(res.get("n_trades") or 0)
    trades = res.get("trades") or []
    money_put = round(sum(float(t.get("money_put") or t.get("entry_notional") or 0) for t in trades), 2)
    slot_caps = [float(t.get("slot_capital") or 0) for t in trades]
    max_slot = max(slot_caps) if slot_caps else 0.0
    full_book = max_slot >= cap_start * 0.99 if cap_start else False

    cap = cap_end
    peak = max(peak, cap)
    dd = 100.0 * (peak - cap) / peak if peak else 0.0
    max_dd = max(max_dd, dd)
    min_ret = min(min_ret, ret)
    max_ret = max(max_ret, ret)
    total_trades += n_trades

    row = {
      "asof": asof,
      "capital_start": round(cap_start, 2),
      "capital_end": round(cap_end, 2),
      "pnl_inr": pnl,
      "return_pct": ret,
      "n_trades": n_trades,
      "money_put": money_put,
      "max_slot_capital": round(max_slot, 2),
      "used_full_book": full_book,
      "sit_out": n_trades == 0,
      "skip_reasons": sorted(
        {
          str(s.get("reason"))
          for s in (res.get("skipped") or [])
          if s.get("reason") in ("sit_out_or_edge_below_cost",)
        }
      ),
      "trades": [
        {
          "ticker": t.get("ticker"),
          "pnl": t.get("pnl"),
          "pnl_pct": t.get("pnl_pct"),
          "lev": t.get("leverage"),
          "money_put": t.get("money_put"),
          "slot_capital": t.get("slot_capital"),
          "exit": t.get("exit_reason"),
        }
        for t in trades
      ],
    }
    daily.append(row)
    print(
      f"{asof:<12} {cap_start:>10,.0f} {cap_end:>10,.0f} {pnl:>+12,.2f} {ret:>+7.2f}% "
      f"{n_trades:>6} {money_put:>12,.0f}",
      flush=True,
    )

  month_pnl = round(cap - start_cap, 2)
  compound = round(100.0 * (cap - start_cap) / start_cap, 3) if start_cap else 0.0
  if min_ret > 100:
    min_ret = 0.0
  if max_ret < -100:
    max_ret = 0.0

  print("-" * 78, flush=True)
  print(
    f"MONTH TOTAL | start INR {start_cap:,.0f} -> end INR {cap:,.2f} | "
    f"PnL INR {month_pnl:+,.2f} ({compound:+.2f}%) | "
    f"trades={total_trades} | worst {min_ret:+.2f}% | best {max_ret:+.2f}% | "
    f"maxDD {max_dd:.1f}% | capital_use={use_frac:.0%} (never full book)",
    flush=True,
  )

  report = {
    "generated_at": date.today().isoformat(),
    "product": args.product,
    "params": {**kw, "capital_use_frac": use_frac},
    "window": {"start": days[0], "end": days[-1], "n_days": len(days)},
    "capital_start": start_cap,
    "capital_end": round(cap, 2),
    "month_pnl_inr": month_pnl,
    "compound_pct": compound,
    "total_trades": total_trades,
    "worst_day_pct": round(min_ret, 3),
    "best_day_pct": round(max_ret, 3),
    "max_dd_pct": round(max_dd, 3),
    "days_traded": sum(1 for d in daily if d["n_trades"] > 0),
    "any_full_book_day": any(d["used_full_book"] for d in daily),
    "daily": daily,
    "disclaimer": "Paper/sim only — not live fills, not investment advice.",
  }
  out = ROOT / "models" / "month_backtest_partial_10k.json"
  out.write_text(json.dumps(report, indent=2), encoding="utf-8")
  print(f"Wrote {out}", flush=True)


if __name__ == "__main__":
  main()
