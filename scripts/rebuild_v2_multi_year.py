"""Rebuild v2_multi_year.json from per-year artefacts without re-simulating."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

PF = Path(__file__).resolve().parents[1] / "models" / "pattern_forge"
YEARS = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]
capital = 10_000.0


def main() -> None:
  blocks = []
  all_trades = []
  bar_rows = []
  compound = capital
  for y in YEARS:
    path = PF / f"v2_year_{y}.json"
    if not path.exists():
      raise SystemExit(f"missing {path}")
    d = json.loads(path.read_text(encoding="utf-8"))
    trades = list(d.get("trades") or [])
    # older files may miss year on trades
    for t in trades:
      t.setdefault("year", y)
    all_trades.extend(trades)
    ret = float(d.get("total_return_pct") or 0)
    compound_start = compound
    compound = round(compound * (1.0 + ret / 100.0), 2)
    block = {
      "year": y,
      "run_id": d.get("run_id"),
      "capital_start": float(d.get("capital_start") or capital),
      "capital_end": d.get("capital_end"),
      "year_pnl": d.get("year_pnl"),
      "total_return_pct": ret,
      "green_months": d.get("green_months"),
      "months_total": d.get("months_total") or 12,
      "worst_month_pct": d.get("worst_month_pct"),
      "best_month_pct": d.get("best_month_pct"),
      "worst_month_pnl": d.get("worst_month_pnl"),
      "loss_lte_profits": d.get("loss_lte_profits"),
      "goal_met": d.get("goal_met"),
      "n_trades": d.get("n_trades") or len(trades),
      "months": d.get("months"),
      "compound_capital_start": compound_start,
      "compound_capital_end": compound,
      "compound_year_pnl": round(compound - compound_start, 2),
    }
    blocks.append(block)
    bar_rows.append(
      {
        "year": str(y),
        "return_pct": ret,
        "end_capital": d.get("capital_end"),
        "green_months": d.get("green_months"),
        "n_trades": block["n_trades"],
        "worst_month_pct": d.get("worst_month_pct"),
      }
    )
  wins = sum(1 for t in all_trades if float(t.get("pnl") or 0) > 0)
  losses = sum(1 for t in all_trades if float(t.get("pnl") or 0) < 0)
  knobs = {}
  if (PF / "v2_latest.json").exists():
    knobs = json.loads((PF / "v2_latest.json").read_text()).get("knobs") or {}
  payload = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "strategy": "daily_swing",
    "lane": "v2",
    "claim": "paper/sim clean-PIT multi-year; locked v2 knobs; rebuilt from v2_year_*.json; standalone ₹10k/year is the scorecard; compound is footnote only; not live fills",
    "years": YEARS,
    "capital_start_per_year": capital,
    "knobs": knobs,
    "summary": {
      "n_years": len(YEARS),
      "n_trades": len(all_trades),
      "wins": wins,
      "losses": losses,
      "win_rate_pct": round(100.0 * wins / max(1, wins + losses), 2),
      "sum_standalone_pnl": round(sum(float(b.get("year_pnl") or 0) for b in blocks), 2),
      "mean_year_return_pct": round(sum(float(b["total_return_pct"]) for b in blocks) / len(blocks), 3),
      "compound_end": compound,
      "compound_return_pct": round(100.0 * (compound - capital) / capital, 3),
      "years_positive": sum(1 for b in blocks if float(b["total_return_pct"]) > 0),
      "note": "Lead with year_returns standalone table; compound is sequential footnote only",
    },
    "year_returns": bar_rows,
    "years_detail": blocks,
    "trades": all_trades,
  }
  out = PF / "v2_multi_year.json"
  out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
  print(f"wrote {out} years={YEARS} trades={len(all_trades)} compound_end={compound}")
  print("standalone:", [(b["year"], b["total_return_pct"]) for b in blocks])


if __name__ == "__main__":
  main()
