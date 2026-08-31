"""Run locked Pattern Forge v2 across multiple clean-PIT years.

Writes a single JSON with per-year summaries, month equity, full trade tape,
and a continuous equity curve (₹10k restart each year + compounded path).
Does not overwrite v2_latest.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_pattern_forge_daily_swing_2025 import run_daily_benchmark  # noqa: E402

PF = ROOT / "models" / "pattern_forge"
V2_PATH = PF / "v2_latest.json"
DEFAULT_YEARS = [2018, 2020, 2022, 2023, 2024, 2025]


def _v2_knobs(*, year: int) -> dict[str, Any]:
  base: dict[str, Any] = {
    "leverage": 11.0,
    "sleeve_frac": 0.24,
    "learn_mistakes": True,
    "profit_guard": True,
    "profit_guard_floor_pct": 2.0,
    "reset_mistakes": True,
    "long_only": True,
    "swarm_hard_veto": False,
    "overnight_feeds": False,
    "min_score": 0.005,
    "r1_lo": 0.005,
    "r1_hi": 0.06,
    "top_k": 1,
    "use_breadth_veto": False,
    "breadth_scale": False,
    "promote_summary": False,
    "write_lab_summary": False,
    "allow_overwrite_v2": False,
    "include_trades": True,
    "max_daily_loss_pct": 8.0,
    "universe_n": 0,
    "year": year,
    "lane": f"v2_multi_{year}",
  }
  if V2_PATH.exists():
    try:
      locked = json.loads(V2_PATH.read_text(encoding="utf-8"))
      kn = dict(locked.get("knobs") or {})
      for k in (
        "leverage",
        "sleeve_frac",
        "profit_guard",
        "profit_guard_floor_pct",
        "learn_mistakes",
        "min_score",
        "r1_lo",
        "r1_hi",
        "top_k",
        "max_daily_loss_pct",
      ):
        if k in kn:
          base[k] = kn[k]
      base["long_only"] = True  # locked v2 is long-only
    except Exception:
      pass
  return base


def _slim_trade(t: dict[str, Any]) -> dict[str, Any]:
  return {
    "year": t.get("year"),
    "month": t.get("month"),
    "asof": t.get("asof"),
    "exit_asof": t.get("exit_asof"),
    "ticker": t.get("ticker"),
    "side": t.get("side"),
    "entry_price": t.get("entry_price"),
    "exit_price": t.get("exit_price"),
    "entry_notional": t.get("entry_notional"),
    "fees": t.get("fees"),
    "pnl": t.get("pnl"),
    "pnl_pct": t.get("pnl_pct"),
    "leverage": t.get("leverage"),
    "size_mult": t.get("size_mult"),
    "exit_reason": t.get("exit_reason"),
    "signal_reason": t.get("signal_reason"),
    "family": t.get("family"),
    "run_id": t.get("run_id"),
  }


def run_years(years: list[int], *, capital: float = 10_000.0) -> dict[str, Any]:
  year_blocks: list[dict[str, Any]] = []
  all_trades: list[dict[str, Any]] = []
  equity_by_year: list[dict[str, Any]] = []
  compound_cap = capital
  compound_curve: list[dict[str, Any]] = [{"date": f"{years[0]}-01-01", "capital": capital, "year": years[0], "mode": "start"}]
  bar_rows: list[dict[str, Any]] = []

  for y in years:
    print(f"\n======== v2 clean-PIT year={y} ========", flush=True)
    rep = run_daily_benchmark(year=y, capital=capital, knobs=_v2_knobs(year=y))
    trades = [_slim_trade(t) for t in (rep.get("trades") or [])]
    eq = list(rep.get("equity_curve") or [])
    all_trades.extend(trades)
    equity_by_year.append({"year": y, "points": eq})

    y_start = float(rep.get("capital_start") or capital)
    y_end = float(rep.get("capital_end") or y_start)
    y_ret = float(rep.get("total_return_pct") or 0)
    # Compound: apply same year return to rolling capital
    compound_start = compound_cap
    compound_cap = round(compound_cap * (1.0 + y_ret / 100.0), 2)
    for pt in eq:
      if not pt.get("date"):
        continue
      # Scale intra-year path onto compound book
      frac = (float(pt["capital"]) / y_start) if y_start else 1.0
      compound_curve.append(
        {
          "date": pt["date"],
          "capital": round(compound_start * frac, 2),
          "year": y,
          "mode": "compound",
          "standalone_capital": pt["capital"],
        }
      )

    block = {
      "year": y,
      "run_id": rep.get("run_id"),
      "capital_start": y_start,
      "capital_end": y_end,
      "year_pnl": rep.get("year_pnl"),
      "total_return_pct": y_ret,
      "green_months": rep.get("green_months"),
      "months_total": rep.get("months_total"),
      "worst_month_pct": rep.get("worst_month_pct"),
      "best_month_pct": rep.get("best_month_pct"),
      "worst_month_pnl": rep.get("worst_month_pnl"),
      "loss_lte_profits": rep.get("loss_lte_profits"),
      "goal_met": rep.get("goal_met"),
      "n_trades": rep.get("n_trades"),
      "months": rep.get("months"),
      "compound_capital_start": compound_start,
      "compound_capital_end": compound_cap,
      "compound_year_pnl": round(compound_cap - compound_start, 2),
    }
    year_blocks.append(block)
    bar_rows.append(
      {
        "year": str(y),
        "return_pct": y_ret,
        "end_capital": y_end,
        "green_months": rep.get("green_months"),
        "n_trades": rep.get("n_trades"),
        "worst_month_pct": rep.get("worst_month_pct"),
      }
    )
    # Persist per-year artefact
    out_y = PF / f"v2_year_{y}.json"
    out_y.write_text(
      json.dumps({**block, "trades": trades, "equity_curve": eq, "knobs": rep.get("knobs")}, indent=2),
      encoding="utf-8",
    )
    print(f"wrote {out_y}", flush=True)

  wins = sum(1 for t in all_trades if float(t.get("pnl") or 0) > 0)
  losses = sum(1 for t in all_trades if float(t.get("pnl") or 0) < 0)
  payload = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "strategy": "daily_swing",
    "lane": "v2",
    "claim": "paper/sim clean-PIT multi-year; locked v2 knobs (lev11/sleeve24/learn/profit_guard/long_only); IN_FO ~12bps RT; each year starts at ₹10k standalone; compound path applies year returns sequentially; not live fills",
    "years": years,
    "capital_start_per_year": capital,
    "knobs": _v2_knobs(year=years[0]),
    "summary": {
      "n_years": len(years),
      "n_trades": len(all_trades),
      "wins": wins,
      "losses": losses,
      "win_rate_pct": round(100.0 * wins / max(1, wins + losses), 2),
      "sum_standalone_pnl": round(sum(float(b.get("year_pnl") or 0) for b in year_blocks), 2),
      "mean_year_return_pct": round(sum(float(b.get("total_return_pct") or 0) for b in year_blocks) / max(1, len(year_blocks)), 3),
      "compound_end": compound_cap,
      "compound_return_pct": round(100.0 * (compound_cap - capital) / capital, 3),
      "years_positive": sum(1 for b in year_blocks if float(b.get("total_return_pct") or 0) > 0),
    },
    "year_returns": bar_rows,
    "years_detail": year_blocks,
    "trades": all_trades,
    "equity_curve_by_year": equity_by_year,
    "compound_equity_curve": compound_curve,
  }
  out = PF / "v2_multi_year.json"
  out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
  print(f"\nwrote {out} trades={len(all_trades)} compound_end={compound_cap:,.2f}", flush=True)
  return payload


def main() -> None:
  ap = argparse.ArgumentParser()
  ap.add_argument("--years", default=",".join(str(y) for y in DEFAULT_YEARS))
  ap.add_argument("--capital", type=float, default=10_000.0)
  args = ap.parse_args()
  years = [int(x.strip()) for x in args.years.split(",") if x.strip()]
  run_years(years, capital=args.capital)


if __name__ == "__main__":
  main()
