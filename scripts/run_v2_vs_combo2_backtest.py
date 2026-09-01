"""Full multi-year backtest: locked v2 vs moon_15x_combo2 + push-until-break grid."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_pattern_forge_daily_swing_2025 import run_daily_benchmark  # noqa: E402
from run_v2_multi_year import _v2_knobs  # noqa: E402

PF = ROOT / "models" / "pattern_forge"
OUT = PF / "v2_vs_combo2_backtest.json"
STRETCH_PATH = PF / "v2_4_stretch_latest.json"
V2_PATH = PF / "v2_latest.json"

YEARS = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]

ASYM = dict(
  asymmetric_freq=True,
  defense_cooldown_days=1,
  defense_loss_streak_sitout=3,
  defense_max_trades_per_month=14,
  attack_cooldown_days=0,
  attack_loss_streak_sitout=0,
  attack_max_trades_per_month=0,
  calendar_soft_months=["october"],
  calendar_soft_mult=0.5,
  calendar_soft_only_underwater=True,
  ignore_briefing_size_in_attack=True,
)

COMBO2 = dict(
  lane="v2_4_stretch",
  leverage=15,
  sleeve_frac=0.30,
  profit_guard=True,
  attack_leverage=18,
  attack_sleeve_frac=0.34,
  attack_r1_hi=0.09,
  r1_hi=0.07,
  attack_boost_52w=True,
  defense_leverage=12,
  defense_sleeve_frac=0.24,
  defense_similarity_mult=0.70,
  attack_red_day_size_mult=0.70,
  october_defense=True,
  october_size_mult=0.50,
  max_daily_loss_pct=6.0,
  similarity_soft=True,
  similarity_hard_skip=False,
  adaptive_fingerprints=True,
  learn_mistakes=True,
  long_only=True,
  min_score=0.005,
  top_k=1,
  include_trades=True,
  promote_summary=False,
  write_lab_summary=False,
  **ASYM,
)

PUSH_VARIANTS = [
  ("combo2_push_a", dict(attack_leverage=19, attack_sleeve_frac=0.36, leverage=16)),
  ("combo2_push_b", dict(attack_leverage=20, attack_sleeve_frac=0.37, leverage=17, max_daily_loss_pct=7.0)),
  ("combo2_push_c", dict(attack_leverage=20, attack_sleeve_frac=0.38, leverage=18, r1_hi=0.08, attack_r1_hi=0.10, max_daily_loss_pct=7.5)),
  ("combo2_push_d", dict(attack_leverage=22, attack_sleeve_frac=0.40, leverage=20, r1_hi=0.08, attack_r1_hi=0.10, max_daily_loss_pct=8.0, profit_guard=False)),
]


def _load_combo2_from_file() -> dict[str, Any]:
  if STRETCH_PATH.exists():
    kn = json.loads(STRETCH_PATH.read_text(encoding="utf-8")).get("knobs") or {}
    base = dict(COMBO2)
    base.update({k: v for k, v in kn.items() if v is not None})
    base["include_trades"] = True
    return base
  return dict(COMBO2)


def run_lane(name: str, knobs: dict[str, Any], years: list[int]) -> dict[str, Any]:
  year_rows: list[dict[str, Any]] = []
  compound = 10_000.0
  all_trades: list[dict] = []
  for i, y in enumerate(years):
    print(f"\n=== {name} {y} ===", flush=True)
    rep = run_daily_benchmark(
      year=y,
      capital=10_000.0,
      knobs={
        **knobs,
        "year": y,
        "lane": f"{name}_{y}",
        "reset_mistakes": i == 0,
        "include_trades": True,
        "promote_summary": False,
        "write_lab_summary": False,
      },
    )
    ret = float(rep.get("total_return_pct") or 0)
    compound = round(compound * (1.0 + ret / 100.0), 2)
    trades = list(rep.get("trades") or [])
    all_trades.extend(trades)
    row = {
      "year": y,
      "total_return_pct": ret,
      "capital_end": rep.get("capital_end"),
      "year_pnl": rep.get("year_pnl"),
      "green_months": rep.get("green_months"),
      "worst_month_pct": rep.get("worst_month_pct"),
      "best_month_pct": rep.get("best_month_pct"),
      "loss_lte_profits": rep.get("loss_lte_profits"),
      "goal_met": rep.get("goal_met"),
      "n_trades": rep.get("n_trades"),
      "run_id": rep.get("run_id"),
      "months": rep.get("months"),
    }
    year_rows.append(row)
    print(
      f"  -> {ret:+.2f}% green={row['green_months']}/12 worst={row['worst_month_pct']:+.2f}%",
      flush=True,
    )

  wins = sum(1 for t in all_trades if float(t.get("pnl") or 0) > 0)
  losses = sum(1 for t in all_trades if float(t.get("pnl") or 0) < 0)
  rets = [float(r["total_return_pct"] or 0) for r in year_rows]
  worst_months = [float(r["worst_month_pct"] or 0) for r in year_rows]
  summary = {
    "n_years": len(years),
    "mean_year_return_pct": round(sum(rets) / max(1, len(rets)), 3),
    "sum_standalone_pnl": round(sum(float(r.get("year_pnl") or 0) for r in year_rows), 2),
    "years_positive": sum(1 for r in rets if r > 0),
    "compound_end": compound,
    "compound_return_pct": round(100.0 * (compound - 10_000) / 10_000, 3),
    "mean_worst_month_pct": round(sum(worst_months) / max(1, len(worst_months)), 3),
    "min_worst_month_pct": round(min(worst_months) if worst_months else 0, 3),
    "n_trades": len(all_trades),
    "win_rate_pct": round(100.0 * wins / max(1, wins + losses), 2),
    "loss_lte_profits_years": sum(1 for r in year_rows if r.get("loss_lte_profits")),
  }
  return {"name": name, "knobs": knobs, "years": year_rows, "summary": summary, "trades": all_trades}


def compare(v2: dict, combo: dict) -> dict[str, Any]:
  s2 = v2["summary"]
  sc = combo["summary"]
  beats = {
    "mean_return": sc["mean_year_return_pct"] > s2["mean_year_return_pct"],
    "compound": sc["compound_return_pct"] > s2["compound_return_pct"],
    "sum_pnl": sc["sum_standalone_pnl"] > s2["sum_standalone_pnl"],
    "years_positive": sc["years_positive"] >= s2["years_positive"],
    "shallower_worst_month": sc["min_worst_month_pct"] > s2["min_worst_month_pct"],
  }
  beats["overall"] = sum(1 for v in beats.values() if v) >= 3
  per_year = []
  for yv, yc in zip(v2["years"], combo["years"]):
    if yv["year"] != yc["year"]:
      continue
    per_year.append(
      {
        "year": yv["year"],
        "v2_pct": yv["total_return_pct"],
        "combo2_pct": yc["total_return_pct"],
        "delta_pp": round(float(yc["total_return_pct"] or 0) - float(yv["total_return_pct"] or 0), 3),
        "v2_worst": yv["worst_month_pct"],
        "combo2_worst": yc["worst_month_pct"],
      }
    )
  return {"beats_v2": beats, "per_year": per_year}


def score_push(row: dict) -> tuple:
  s = row["summary"]
  return (
    float(s["compound_return_pct"] or 0),
    float(s["mean_year_return_pct"] or 0),
    float(s["min_worst_month_pct"] or -999),
    int(s["years_positive"] or 0),
  )


def main() -> None:
  combo_knobs = _load_combo2_from_file()
  print("Running locked v2 multi-year...", flush=True)
  v2 = run_lane("v2_locked", _v2_knobs(year=YEARS[0]), YEARS)
  print("\nRunning moon_15x_combo2 multi-year...", flush=True)
  combo = run_lane("moon_15x_combo2", combo_knobs, YEARS)
  cmp = compare(v2, combo)

  push_rows: list[dict] = []
  best_push = None
  if cmp["beats_v2"]["overall"]:
    print("\ncombo2 beats v2 on aggregate — pushing until break...", flush=True)
    for label, extra in PUSH_VARIANTS:
      knobs = {**combo_knobs, **extra}
      row = run_lane(label, knobs, YEARS)
      push_rows.append(row)
    push_rows.sort(key=score_push, reverse=True)
    best_push = push_rows[0] if push_rows else None
    # mark break: first variant where years_positive drops below v2 or compound below combo base
    for pr in push_rows:
      s = pr["summary"]
      pr["broke"] = (
        s["years_positive"] < v2["summary"]["years_positive"]
        or s["compound_return_pct"] < combo["summary"]["compound_return_pct"] * 0.85
        or float(s["min_worst_month_pct"] or 0) < -35.0
      )

  payload = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "years": YEARS,
    "v2_locked": v2,
    "moon_15x_combo2": combo,
    "comparison": cmp,
    "combo2_beats_v2": cmp["beats_v2"]["overall"],
    "push_variants": push_rows,
    "best_push": best_push,
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
            "end_capital": r["capital_end"],
            "green_months": r["green_months"],
            "worst_month_pct": r["worst_month_pct"],
            "n_trades": r["n_trades"],
          }
          for r in combo["years"]
        ],
        "comparison_vs_v2": cmp,
      },
      indent=2,
    ),
    encoding="utf-8",
  )
  print(f"\nwrote {OUT}", flush=True)
  print(payload["verdict"], flush=True)


def _verdict(v2: dict, combo: dict, cmp: dict, push: list) -> str:
  s2 = v2["summary"]
  sc = combo["summary"]
  lines = [
    f"v2 mean={s2['mean_year_return_pct']}% compound={s2['compound_return_pct']}% "
    f"years+={s2['years_positive']}/{s2['n_years']} min_worst_mo={s2['min_worst_month_pct']}%",
    f"combo2 mean={sc['mean_year_return_pct']}% compound={sc['compound_return_pct']}% "
    f"years+={sc['years_positive']}/{sc['n_years']} min_worst_mo={sc['min_worst_month_pct']}%",
  ]
  if cmp["beats_v2"]["overall"]:
    lines.append("combo2 WINS aggregate vs v2 on multi-year standalone years.")
    if push:
      ok = [p for p in push if not p.get("broke")]
      if ok:
        b = max(ok, key=score_push)
        lines.append(
          f"Best push before break: {b['name']} compound={b['summary']['compound_return_pct']}% "
          f"min_worst_mo={b['summary']['min_worst_month_pct']}%"
        )
      broke = [p for p in push if p.get("broke")]
      if broke:
        lines.append(f"Breaks at: {', '.join(p['name'] for p in broke)}")
  else:
    lines.append("combo2 does NOT beat v2 on aggregate — keep v2 locked; combo2 stretch-only.")
  return " | ".join(lines)


if __name__ == "__main__":
  main()
