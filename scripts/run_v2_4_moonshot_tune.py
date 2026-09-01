"""Tune moon_15x band toward 618% stretch target."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_pattern_forge_daily_swing_2025 import run_daily_benchmark  # noqa: E402

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

BASE = dict(
  learn_mistakes=True,
  long_only=True,
  min_score=0.005,
  top_k=1,
  similarity_soft=True,
  similarity_hard_skip=False,
  adaptive_fingerprints=True,
  profit_guard=True,
  attack_boost_52w=True,
  attack_r1_hi=0.09,
  r1_hi=0.07,
  **ASYM,
)

OUT = ROOT / "models" / "pattern_forge" / "v2_4_moonshot_tune.json"


def run_one(label: str, lev: float, sleeve: float, atk_lev: float, atk_sleeve: float, *, reset: bool) -> dict:
  rep = run_daily_benchmark(
    year=2025,
    knobs={
      "lane": label,
      "reset_mistakes": reset,
      "leverage": lev,
      "sleeve_frac": sleeve,
      "attack_leverage": atk_lev,
      "attack_sleeve_frac": atk_sleeve,
      **BASE,
    },
  )
  return {
    "label": label,
    "leverage": lev,
    "sleeve_frac": sleeve,
    "attack_leverage": atk_lev,
    "attack_sleeve_frac": atk_sleeve,
    "total_return_pct": rep["total_return_pct"],
    "capital_end": rep["capital_end"],
    "green_months": rep["green_months"],
    "worst_month_pct": rep["worst_month_pct"],
    "loss_lte_profits": rep["loss_lte_profits"],
    "n_trades": rep["n_trades"],
    "pct_of_618": round(100.0 * float(rep["total_return_pct"] or 0) / 618.0, 1),
  }


def main() -> None:
  grid = [
    ("m14", 14, 0.28, 16, 0.32),
    ("m15", 15, 0.30, 18, 0.34),
    ("m16", 16, 0.31, 18, 0.35),
    ("m17", 17, 0.32, 19, 0.36),
    ("m18", 18, 0.33, 20, 0.37),
    ("m16_wide", 16, 0.31, 19, 0.36),
  ]
  rows = []
  for i, (label, lev, sl, al, asl) in enumerate(grid):
    row = run_one(label, lev, sl, al, asl, reset=(i == 0))
    print(
      f"{label}: {row['total_return_pct']:+.2f}% ({row['pct_of_618']}% of 618) "
      f"green={row['green_months']}/12 worst={row['worst_month_pct']:+.2f}% end={row['capital_end']}",
      flush=True,
    )
    rows.append(row)
  rows.sort(key=lambda r: -float(r["total_return_pct"] or 0))
  best = rows[0]
  payload = {"ts": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), "rows": rows, "best": best}
  OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
  print(f"\nbest={best['label']} ret={best['total_return_pct']}% wrote {OUT}", flush=True)


if __name__ == "__main__":
  main()
