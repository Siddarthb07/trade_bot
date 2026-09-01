"""Complete v2 vs combo2 backtest — push variants + write report (v2/combo2 from prior run)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_v2_vs_combo2_backtest import (  # noqa: E402
  COMBO2,
  OUT,
  PUSH_VARIANTS,
  YEARS,
  _load_combo2_from_file,
  _verdict,
  compare,
  run_lane,
  score_push,
)
from run_v2_multi_year import _v2_knobs  # noqa: E402

PF = ROOT / "models" / "pattern_forge"

# From completed run 2026-09-01 (terminal 856442) — standalone ₹10k/year
V2_SUMMARY = {
  "years": [
    {"year": 2018, "total_return_pct": 10.70, "worst_month_pct": -11.23, "green_months": 6, "loss_lte_profits": True},
    {"year": 2019, "total_return_pct": 59.82, "worst_month_pct": -16.84, "green_months": 6, "loss_lte_profits": True},
    {"year": 2020, "total_return_pct": 9.54, "worst_month_pct": -13.03, "green_months": 7, "loss_lte_profits": True},
    {"year": 2021, "total_return_pct": -2.64, "worst_month_pct": -30.29, "green_months": 4, "loss_lte_profits": False},
    {"year": 2022, "total_return_pct": 13.57, "worst_month_pct": -15.04, "green_months": 6, "loss_lte_profits": True},
    {"year": 2023, "total_return_pct": 20.79, "worst_month_pct": -10.04, "green_months": 7, "loss_lte_profits": True},
    {"year": 2024, "total_return_pct": 57.06, "worst_month_pct": -16.44, "green_months": 6, "loss_lte_profits": True},
    {"year": 2025, "total_return_pct": 27.44, "worst_month_pct": -4.00, "green_months": 7, "loss_lte_profits": True},
  ]
}

COMBO2_SUMMARY = {
  "years": [
    {"year": 2018, "total_return_pct": 170.03, "worst_month_pct": -19.43, "green_months": 7, "loss_lte_profits": True},
    {"year": 2019, "total_return_pct": 465.51, "worst_month_pct": -11.72, "green_months": 7, "loss_lte_profits": True},
    {"year": 2020, "total_return_pct": 323.90, "worst_month_pct": -11.95, "green_months": 7, "loss_lte_profits": True},
    {"year": 2021, "total_return_pct": 530.19, "worst_month_pct": -15.85, "green_months": 8, "loss_lte_profits": True},
    {"year": 2022, "total_return_pct": -7.70, "worst_month_pct": -15.43, "green_months": 6, "loss_lte_profits": False},
    {"year": 2023, "total_return_pct": 26.90, "worst_month_pct": -12.02, "green_months": 5, "loss_lte_profits": True},
    {"year": 2024, "total_return_pct": 185.88, "worst_month_pct": -27.95, "green_months": 6, "loss_lte_profits": True},
    {"year": 2025, "total_return_pct": 111.57, "worst_month_pct": -19.03, "green_months": 8, "loss_lte_profits": True},
  ]
}


def _aggregate(name: str, year_rows: list[dict], knobs: dict | None = None) -> dict:
  rets = [float(r["total_return_pct"] or 0) for r in year_rows]
  worst_months = [float(r["worst_month_pct"] or 0) for r in year_rows]
  compound = 10_000.0
  for r in rets:
    compound = round(compound * (1.0 + r / 100.0), 2)
  return {
    "name": name,
    "knobs": knobs or {},
    "years": year_rows,
    "summary": {
      "n_years": len(year_rows),
      "mean_year_return_pct": round(sum(rets) / max(1, len(rets)), 3),
      "sum_standalone_pnl": round(sum(10_000.0 * r / 100.0 for r in rets), 2),
      "years_positive": sum(1 for r in rets if r > 0),
      "compound_end": compound,
      "compound_return_pct": round(100.0 * (compound - 10_000) / 10_000, 3),
      "mean_worst_month_pct": round(sum(worst_months) / max(1, len(worst_months)), 3),
      "min_worst_month_pct": round(min(worst_months) if worst_months else 0, 3),
      "loss_lte_profits_years": sum(1 for r in year_rows if r.get("loss_lte_profits")),
    },
  }


def main() -> None:
  v2 = _aggregate("v2_locked", V2_SUMMARY["years"], _v2_knobs(year=2025))
  combo = _aggregate("moon_15x_combo2", COMBO2_SUMMARY["years"], _load_combo2_from_file())
  cmp = compare(v2, combo)

  push_rows: list[dict] = []
  combo_knobs = _load_combo2_from_file()
  if cmp["beats_v2"]["overall"]:
    print("combo2 beats v2 — running push grid...", flush=True)
    for i, (label, extra) in enumerate(PUSH_VARIANTS):
      knobs = {**combo_knobs, **extra}
      row = run_lane(label, knobs, YEARS)
      s = row["summary"]
      row["broke"] = (
        s["years_positive"] < v2["summary"]["years_positive"]
        or s["compound_return_pct"] < combo["summary"]["compound_return_pct"] * 0.85
        or float(s["min_worst_month_pct"] or 0) < -35.0
      )
      push_rows.append(row)
    push_rows.sort(key=score_push, reverse=True)

  payload = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "years": YEARS,
    "v2_locked": v2,
    "moon_15x_combo2": combo,
    "comparison": cmp,
    "combo2_beats_v2": cmp["beats_v2"]["overall"],
    "push_variants": push_rows,
    "best_push": push_rows[0] if push_rows else None,
    "verdict": _verdict(v2, combo, cmp, push_rows),
  }
  OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
  PF.joinpath("v2_4_multi_year.json").write_text(
    json.dumps(
      {
        "ts": payload["ts"],
        "lane": "moon_15x_combo2",
        "years": YEARS,
        "summary": combo["summary"],
        "year_returns": [
          {
            "year": str(r["year"]),
            "return_pct": r["total_return_pct"],
            "green_months": r["green_months"],
            "worst_month_pct": r["worst_month_pct"],
          }
          for r in combo["years"]
        ],
        "comparison_vs_v2": cmp,
        "push_best": push_rows[0]["summary"] if push_rows else None,
      },
      indent=2,
    ),
    encoding="utf-8",
  )
  print(payload["verdict"], flush=True)
  print(f"wrote {OUT}", flush=True)


if __name__ == "__main__":
  main()
