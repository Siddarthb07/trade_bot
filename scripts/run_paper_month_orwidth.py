"""Paper-month OR-width product runner (sim replay, guarded config).

Replays recent IN sessions with the product guardrails so you can
validate a calendar month on paper before any live capital.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_in_compound_search as compound
from processor.orwidth_product import DEFAULT_PAPER_PRODUCT, product_kwargs


def _sessions(n_days: int, end: date | None = None) -> list[str]:
  end = end or date.today()
  out: list[str] = []
  d = end
  while len(out) < n_days:
    if d.weekday() < 5:
      out.append(d.isoformat())
    d -= timedelta(days=1)
  return list(reversed(out))


def main() -> None:
  import argparse

  ap = argparse.ArgumentParser()
  ap.add_argument("--product", default=DEFAULT_PAPER_PRODUCT)
  ap.add_argument("--days", type=int, default=22, help="trading days (~1 month)")
  ap.add_argument("--end", default=None, help="YYYY-MM-DD end date (default today)")
  args = ap.parse_args()

  end = date.fromisoformat(args.end) if args.end else date.today()
  days = _sessions(args.days, end)
  kw = product_kwargs(args.product)
  kw.pop("bar_interval", None)
  print(f"product={args.product} days={len(days)} {days[0]}..{days[-1]}", flush=True)
  print(f"params={kw}", flush=True)

  ev = compound._eval_compound(args.product, days, kw)
  report = {
    "generated_at": date.today().isoformat(),
    "product": args.product,
    "params": kw,
    "window": {"start": days[0], "end": days[-1], "n_days": len(days)},
    "summary": {
      "compound_pct": ev["compound_total_pct"],
      "final_capital_inr": ev["final_capital_inr"],
      "worst_day_pct": ev["min_daily_return_pct"],
      "best_day_pct": ev["max_daily_return_pct"],
      "avg_daily_pct": ev["avg_daily_return_pct"],
    },
    "days": ev["days"],
    "disclaimer": (
      "Paper/sim only — not live fills, not investment advice. "
      "Run a full calendar month before any real capital."
    ),
  }
  out = ROOT / "models" / "orwidth_paper_month_report.json"
  out.write_text(json.dumps(report, indent=2), encoding="utf-8")
  s = report["summary"]
  print(
    f"compound={s['compound_pct']:+.1f}% worst={s['worst_day_pct']:+.1f}% "
    f"best={s['best_day_pct']:+.1f}% final=₹{s['final_capital_inr']:,.0f}",
    flush=True,
  )
  print(f"Wrote {out}", flush=True)


if __name__ == "__main__":
  main()
