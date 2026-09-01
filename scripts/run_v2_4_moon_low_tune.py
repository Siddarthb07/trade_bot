"""Tune moon_15x for lower worst-month drawdown while keeping stretch return."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_pattern_forge_daily_swing_2025 import run_daily_benchmark  # noqa: E402

OUT = ROOT / "models" / "pattern_forge" / "v2_4_moon_low_tune.json"
STRETCH = ROOT / "models" / "pattern_forge" / "v2_4_stretch_latest.json"

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

MOON15 = dict(
  leverage=15,
  sleeve_frac=0.30,
  profit_guard=True,
  attack_leverage=18,
  attack_sleeve_frac=0.34,
  attack_r1_hi=0.09,
  r1_hi=0.07,
  attack_boost_52w=True,
  similarity_soft=True,
  similarity_hard_skip=False,
  adaptive_fingerprints=True,
  learn_mistakes=True,
  long_only=True,
  min_score=0.005,
  top_k=1,
  **ASYM,
)

VARIANTS = [
  ("moon_15x_base", {}),
  ("moon_15x_def11", dict(defense_leverage=11, defense_sleeve_frac=0.22)),
  ("moon_15x_def12", dict(defense_leverage=12, defense_sleeve_frac=0.24, defense_loss_streak_sitout=2)),
  ("moon_15x_oct", dict(october_defense=True, october_size_mult=0.40)),
  (
    "moon_15x_combo",
    dict(
      defense_leverage=11,
      defense_sleeve_frac=0.22,
      defense_similarity_mult=0.65,
      attack_red_day_size_mult=0.65,
      october_defense=True,
      october_size_mult=0.45,
      defense_size_mult=0.45,
      defense_sitout=False,
    ),
  ),
  (
    "moon_15x_combo2",
    dict(
      defense_leverage=12,
      defense_sleeve_frac=0.24,
      defense_similarity_mult=0.70,
      attack_red_day_size_mult=0.70,
      october_defense=True,
      october_size_mult=0.50,
      max_daily_loss_pct=6.0,
    ),
  ),
]


def score_row(row: dict) -> tuple:
  """Prefer high return with shallow worst month."""
  ret = float(row["total_return_pct"] or 0)
  worst = float(row["worst_month_pct"] or 0)
  return (ret, worst, -abs(worst))


def main() -> None:
  rows = []
  for i, (label, extra) in enumerate(VARIANTS):
    rep = run_daily_benchmark(
      year=2025,
      knobs={"lane": label, **MOON15, **extra, "reset_mistakes": True},
    )
    row = {
      "variant": label,
      "total_return_pct": rep["total_return_pct"],
      "capital_end": rep["capital_end"],
      "green_months": rep["green_months"],
      "worst_month_pct": rep["worst_month_pct"],
      "best_month_pct": rep.get("best_month_pct"),
      "loss_lte_profits": rep["loss_lte_profits"],
      "n_trades": rep["n_trades"],
      "pct_of_618": round(100.0 * float(rep["total_return_pct"] or 0) / 618.0, 1),
      "extra": extra,
    }
    rows.append(row)
    print(
      f"{label}: {row['total_return_pct']:+.2f}% worst={row['worst_month_pct']:+.2f}% "
      f"green={row['green_months']}/12 end={row['capital_end']}",
      flush=True,
    )

  base = next(r for r in rows if r["variant"] == "moon_15x_base")
  base_worst = float(base["worst_month_pct"] or 0)
  improved = [r for r in rows if float(r["worst_month_pct"] or 0) > base_worst]
  rows.sort(key=score_row, reverse=True)
  best = rows[0]

  payload = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "base": base,
    "worst_month_improved_variants": [r["variant"] for r in improved],
    "rows": rows,
    "best": best,
  }
  OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

  best_knobs = {**MOON15, **(best.get("extra") or {}), "lane": "v2_4_stretch"}
  STRETCH.write_text(
    json.dumps(
      {
        "lane": "v2_4_stretch",
        "variant": best["variant"],
        "parent": "moon_15x",
        "target_return_pct": 618.0,
        "pct_of_target": best["pct_of_618"],
        "strategy": "daily_swing",
        "benchmark": "2025",
        "capital_start": 10000.0,
        "capital_end": best["capital_end"],
        "total_return_pct": best["total_return_pct"],
        "green_months": best["green_months"],
        "months_total": 12,
        "worst_month_pct": best["worst_month_pct"],
        "best_month_pct": best.get("best_month_pct"),
        "year_pnl": round(float(best["capital_end"] or 10000) - 10000, 2),
        "loss_lte_profits": best["loss_lte_profits"],
        "n_trades": best["n_trades"],
        "knobs": best_knobs,
        "base_worst_month_pct": base_worst,
        "worst_month_delta_pp": round(float(best["worst_month_pct"] or 0) - base_worst, 3),
        "claim": (
          f"moon_15x low-tuned {best['variant']}; 2025 {best['total_return_pct']}% "
          f"worst {best['worst_month_pct']}% (base worst {base_worst}%)"
        ),
      },
      indent=2,
    ),
    encoding="utf-8",
  )
  print(
    f"\nbest={best['variant']} ret={best['total_return_pct']}% worst={best['worst_month_pct']}% "
    f"(base worst {base_worst}%) wrote {OUT}",
    flush=True,
  )


if __name__ == "__main__":
  main()
