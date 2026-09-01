"""moon_15x stretch lane — v2.4 low-tuned (combo2).

Run: PYTHONPATH=packages python scripts/run_v2_4_moonshot.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_pattern_forge_daily_swing_2025 import run_daily_benchmark  # noqa: E402

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

MOON15_COMBO2 = dict(
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
  reset_mistakes=True,
  **ASYM,
)


def main() -> None:
  rep = run_daily_benchmark(year=2025, knobs=MOON15_COMBO2)
  print(
    f"moon_15x_combo2: {rep['total_return_pct']:+.2f}% "
    f"green={rep['green_months']}/12 worst={rep['worst_month_pct']:+.2f}% "
    f"end={rep['capital_end']}",
    flush=True,
  )
  payload = {
    "lane": "v2_4_stretch",
    "variant": "moon_15x_combo2",
    "parent": "moon_15x",
    "target_return_pct": 618.0,
    "pct_of_target": round(100.0 * float(rep["total_return_pct"] or 0) / 618.0, 1),
    "strategy": "daily_swing",
    "benchmark": "2025",
    "capital_start": 10000.0,
    "capital_end": rep["capital_end"],
    "total_return_pct": rep["total_return_pct"],
    "green_months": rep["green_months"],
    "months_total": 12,
    "worst_month_pct": rep["worst_month_pct"],
    "best_month_pct": rep.get("best_month_pct"),
    "year_pnl": rep["year_pnl"],
    "loss_lte_profits": rep["loss_lte_profits"],
    "n_trades": rep["n_trades"],
    "knobs": MOON15_COMBO2,
    "claim": (
      f"moon_15x_combo2: defense 12x + oct soft + red-day cap + 6% daily loss clamp; "
      f"2025 {rep['total_return_pct']}% worst {rep['worst_month_pct']}%"
    ),
  }
  STRETCH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
  print(f"wrote {STRETCH}", flush=True)


if __name__ == "__main__":
  main()
