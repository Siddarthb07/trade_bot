"""v2.4 bakeoff — soft similarity + fingerprint dedup + top-k corr cap + asymmetric attack.

Target stretch: push 2025 return toward 618% (contact benchmark) without overwriting v2_latest.
Never overwrite v2_latest.json.
"""

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
from run_v3_bakeoff import _gates, _max_trade_share  # noqa: E402

PF = ROOT / "models" / "pattern_forge"
OUT = PF / "v2_4_bakeoff.json"
V24 = PF / "v2_4_latest.json"
V2 = PF / "v2_latest.json"

TARGET_RETURN_PCT = 618.0


def v2_exact(**over: Any) -> dict[str, Any]:
  """Locked v2 knobs — no extra gates unless explicitly overridden."""
  k: dict[str, Any] = {
    "lane": "v2_4",
    "leverage": 11.0,
    "sleeve_frac": 0.24,
    "learn_mistakes": True,
    "profit_guard": True,
    "profit_guard_floor_pct": 2.0,
    "reset_mistakes": True,
    "long_only": True,
    "min_score": 0.005,
    "r1_lo": 0.005,
    "r1_hi": 0.06,
    "top_k": 1,
    "use_breadth_veto": False,
    "breadth_scale": False,
    "max_daily_loss_pct": 8.0,
    "promote_summary": False,
    "write_lab_summary": False,
    "allow_overwrite_v2": False,
    "include_trades": False,
    "mistake_mark_read": False,
    "lookback_days": 520,
    "adaptive_fingerprints": True,
    "similarity_soft": False,
    "indicator_mode": "off",
    "use_ohlcv": False,
  }
  if V2.exists():
    kn = json.loads(V2.read_text(encoding="utf-8")).get("knobs") or {}
    for key in ("leverage", "sleeve_frac", "profit_guard", "min_score", "r1_lo", "r1_hi", "max_daily_loss_pct"):
      if key in kn:
        k[key] = kn[key]
  k.update(over)
  return k


ASYM_ATTACK = dict(
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

SIM_SOFT = dict(
  similarity_soft=True,
  similarity_hard_skip=False,
  similarity_iqr_soft=0.004,
  similarity_soft_mult=0.55,
)

VARIANTS = [
  ("v2_replay", v2_exact(lane="v2_replay")),
  ("v2_4_sim", v2_exact(lane="v2_4_sim", **SIM_SOFT)),
  ("v2_4_asym", v2_exact(lane="v2_4_asym", **ASYM_ATTACK)),
  (
    "v2_4_asym_sim",
    v2_exact(lane="v2_4_asym_sim", **ASYM_ATTACK, **SIM_SOFT),
  ),
  (
    "v2_4_top3",
    v2_exact(
      lane="v2_4_top3",
      **ASYM_ATTACK,
      **SIM_SOFT,
      top_k=3,
      correlation_cap=True,
      max_pairwise_corr=0.70,
      max_single_name_day_frac=0.38,
    ),
  ),
  (
    "v2_4_blitz",
    v2_exact(
      lane="v2_4_blitz",
      **ASYM_ATTACK,
      **SIM_SOFT,
      top_k=3,
      correlation_cap=True,
      max_pairwise_corr=0.72,
      max_single_name_day_frac=0.35,
      attack_r1_hi=0.09,
      attack_boost_52w=True,
      attack_sleeve_frac=0.32,
      attack_leverage=16.0,
      leverage=16.0,
      r1_hi=0.07,
    ),
  ),
  (
    "v2_4_ultra",
    v2_exact(
      lane="v2_4_ultra",
      **ASYM_ATTACK,
      similarity_soft=True,
      similarity_hard_skip=False,
      similarity_iqr_soft=0.003,
      similarity_soft_mult=0.65,
      top_k=5,
      correlation_cap=True,
      max_pairwise_corr=0.68,
      max_single_name_day_frac=0.22,
      attack_r1_hi=0.10,
      attack_boost_52w=True,
      attack_sleeve_frac=0.38,
      attack_leverage=20.0,
      leverage=20.0,
      r1_hi=0.08,
      max_daily_loss_pct=12.0,
      profit_guard=False,
    ),
  ),
]


def run_year(name: str, knobs: dict, year: int, *, reset: bool) -> dict[str, Any]:
  print(f"\n=== {name} {year} ===", flush=True)
  rep = run_daily_benchmark(
    year=year,
    knobs={**knobs, "year": year, "lane": f"{name}_{year}", "reset_mistakes": reset},
  )
  trades = list(rep.get("trades") or [])
  conc = _max_trade_share(trades, float(rep.get("year_pnl") or 0)) if trades else 0.0
  n_months = int(rep.get("months_total") or len(rep.get("months") or []))
  if n_months < 12:
    reasons: list[str] = []
    if float(rep.get("total_return_pct") or -999) <= 0:
      reasons.append("return<=0")
    if not rep.get("loss_lte_profits"):
      reasons.append("loss_lte_profits=False")
    need_green = max(1, (n_months * 2 + 2) // 3)
    if int(rep.get("green_months") or 0) < need_green:
      reasons.append(f"green={rep.get('green_months')}<{need_green}_ytd")
    ok, reasons = (len(reasons) == 0, reasons)
  else:
    ok, reasons = _gates({**rep, "concentration": conc}, max_conc=65.0)
  ret = float(rep.get("total_return_pct") or 0)
  return {
    "total_return_pct": ret,
    "capital_end": rep.get("capital_end"),
    "year_pnl": rep.get("year_pnl"),
    "green_months": rep.get("green_months"),
    "months_total": n_months,
    "worst_month_pct": rep.get("worst_month_pct"),
    "best_month_pct": rep.get("best_month_pct"),
    "loss_lte_profits": rep.get("loss_lte_profits"),
    "n_trades": rep.get("n_trades"),
    "concentration": conc,
    "gate_ok": ok,
    "gate_fail": reasons,
    "run_id": rep.get("run_id"),
    "pct_of_target": round(100.0 * ret / TARGET_RETURN_PCT, 1),
  }


def main() -> None:
  v2_2025 = float(json.loads(V2.read_text(encoding="utf-8"))["total_return_pct"]) if V2.exists() else 103.0
  rows = []
  for name, knobs in VARIANTS:
    y25 = run_year(name, knobs, 2025, reset=True)
    ret25 = float(y25["total_return_pct"] or 0)
    rows.append(
      {
        "variant": name,
        "ret_2025": ret25,
        "beats_v2_2025": ret25 >= v2_2025,
        "pct_of_618_target": y25.get("pct_of_target"),
        "green_months": y25.get("green_months"),
        "worst_month_pct": y25.get("worst_month_pct"),
        "best_month_pct": y25.get("best_month_pct"),
        "loss_lte_profits": y25.get("loss_lte_profits"),
        "n_trades": y25.get("n_trades"),
        "gate_ok": y25.get("gate_ok"),
        "gate_fail": y25.get("gate_fail"),
        "knobs": {
          k: knobs[k]
          for k in sorted(knobs)
          if k not in ("promote_summary", "write_lab_summary", "allow_overwrite_v2")
        },
      }
    )

  rows.sort(key=lambda r: (-float(r["ret_2025"] or 0), not r["beats_v2_2025"]))
  best = rows[0]
  best_name = best["variant"]
  best_knobs = dict(next(k for n, k in VARIANTS if n == best_name))
  y25 = run_year(best_name, best_knobs, 2025, reset=True)

  payload = {
    "lane": "v2_4",
    "variant": best_name,
    "parent": "v2",
    "target_return_pct": TARGET_RETURN_PCT,
    "pct_of_target": best.get("pct_of_618_target"),
    "strategy": "daily_swing",
    "capital_start": 10000.0,
    "capital_end": y25["capital_end"],
    "total_return_pct": y25["total_return_pct"],
    "green_months": y25["green_months"],
    "months_total": 12,
    "worst_month_pct": y25["worst_month_pct"],
    "best_month_pct": y25.get("best_month_pct"),
    "year_pnl": y25["year_pnl"],
    "loss_lte_profits": y25["loss_lte_profits"],
    "n_trades": y25["n_trades"],
    "knobs": best_knobs,
    "locked_v2_untouched": True,
    "beats_v2_2025": bool(best["beats_v2_2025"]),
    "claim": (
      f"paper/sim v2.4={best_name}; soft similarity (no hard skip) + corr top-k + asymmetric attack; "
      f"2025={y25['total_return_pct']}% vs v2 {v2_2025}% / target {TARGET_RETURN_PCT}%"
    ),
  }
  V24.write_text(json.dumps(payload, indent=2), encoding="utf-8")
  bake = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "note": "v2.4 rev2: preserve v2 fire rate; similarity size-down only; attack lane for stretch",
    "v2_2025": v2_2025,
    "target_618_pct": TARGET_RETURN_PCT,
    "variants": rows,
    "best": best,
    "promote_to_v2": False,
  }
  OUT.write_text(json.dumps(bake, indent=2), encoding="utf-8")
  print(
    f"\nwrote {OUT} best={best_name} ret_2025={best['ret_2025']}% "
    f"({best.get('pct_of_618_target')}% of 618 target) beats_v2={best['beats_v2_2025']}",
    flush=True,
  )


if __name__ == "__main__":
  main()
